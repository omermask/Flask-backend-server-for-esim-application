from __future__ import annotations

import logging
from typing import Any

import requests

from app.core.database import get_session
from app.core.errors import AppError, ErrorCode
from app.models.sms import SMSProviderTransaction
from app.providers.base import SMSProviderBase
from app.providers.registry import sms_provider
from config import settings

logger = logging.getLogger("esim-ego")


OTPIQ_ERROR_MAP: dict[str, ErrorCode] = {
    "insufficient_credit": ErrorCode.SMS_PROVIDER_BALANCE_LOW,
    "spending_threshold": ErrorCode.PROVIDER_INSUFFICIENT_BALANCE,
    "sender_not_found": ErrorCode.SMS_INIT_FAILED,
    "sender_not_accepted": ErrorCode.SMS_INIT_FAILED,
    "trial_mode": ErrorCode.SMS_PROVIDER_BALANCE_LOW,
    "invalid_phone": ErrorCode.VALIDATION_INVALID_PHONE,
    "rate_limited": ErrorCode.PROVIDER_RATE_LIMITED,
    "unauthorized": ErrorCode.SMS_PROVIDER_AUTH_FAILED,
}


@sms_provider("otpiq")
class OTPIQProvider(SMSProviderBase):

    def __init__(self) -> None:
        self._base_url = settings.OTPIQ_API_BASE_URL.rstrip("/")
        self._sender_id = settings.OTPIQ_SENDER_ID
        self._timeout = settings.OTPIQ_TIMEOUT
        self._api_key = settings.OTPIQ_API_KEY
        self._webhook_url = settings.OTPIQ_WEBHOOK_URL
        self._webhook_secret = settings.OTPIQ_WEBHOOK_SECRET
        self._simulated = False
        self._ready = True
        self._session = requests.Session()

        if not self._api_key:
            if settings.OTPIQ_SANDBOX:
                logger.info("OTPIQ_API_KEY not configured — operating in simulated mode")
                self._simulated = True
                return
            logger.error("OTPIQ_API_KEY not configured and OTPIQ_SANDBOX is False")
            self._ready = False
            return

        self._session.headers.update({
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    @property
    def _is_simulated(self) -> bool:
        return self._simulated

    def _build_delivery_report(self) -> dict[str, Any] | None:
        if not self._webhook_url:
            return None
        report: dict[str, Any] = {
            "webhookUrl": self._webhook_url,
            "deliveryReportType": "sms",
        }
        if self._webhook_secret:
            report["webhookSecret"] = self._webhook_secret
        return report

    def send_otp(self, phone: str, otp: str, lang: str = "en") -> dict[str, Any]:
        if self._is_simulated:
            return self._simulated_response(phone, otp, "send_otp")
        if not self._ready:
            raise AppError(ErrorCode.SMS_INIT_FAILED)
        body: dict[str, Any] = {
            "phoneNumber": phone,
            "smsType": "verification",
            "verificationCode": otp,
            "senderId": self._sender_id,
        }
        dr = self._build_delivery_report()
        if dr:
            body["deliveryReport"] = dr
        return self._request("sms", body, "send_otp")

    def send_sms(self, phone: str, message: str, lang: str = "en") -> dict[str, Any]:
        if self._is_simulated:
            return self._simulated_response(phone, message, "send_sms")
        if not self._ready:
            raise AppError(ErrorCode.SMS_INIT_FAILED)
        body: dict[str, Any] = {
            "phoneNumber": phone,
            "smsType": "custom",
            "customMessage": message,
            "senderId": self._sender_id,
        }
        dr = self._build_delivery_report()
        if dr:
            body["deliveryReport"] = dr
        return self._request("sms", body, "send_sms")

    def get_balance(self) -> dict[str, Any]:
        if self._is_simulated:
            return {
                "success": True,
                "balance": 999999,
                "project_name": "Simulated Project",
                "simulated": True,
            }
        if not self._ready:
            raise AppError(ErrorCode.SMS_INIT_FAILED)
        try:
            resp = self._session.get(
                f"{self._base_url}/info",
                timeout=self._timeout,
            )
        except requests.RequestException as e:
            logger.error("OTPIQ balance request failed: %s", e)
            raise AppError(ErrorCode.PROVIDER_UNAVAILABLE)

        if resp.status_code == 200:
            try:
                data = resp.json()
            except ValueError:
                raise AppError(ErrorCode.PROVIDER_INVALID_RESPONSE)
            return {
                "success": True,
                "balance": data.get("credit", 0),
                "project_name": data.get("projectName", ""),
            }

        if resp.status_code == 401:
            raise AppError(ErrorCode.SMS_PROVIDER_AUTH_FAILED)

        raise AppError(ErrorCode.PROVIDER_UNAVAILABLE)

    def track_sms(self, sms_id: str) -> dict[str, Any]:
        if self._is_simulated:
            return {
                "smsId": sms_id,
                "status": "delivered",
                "simulated": True,
            }
        if not self._ready:
            raise AppError(ErrorCode.SMS_INIT_FAILED)
        try:
            resp = self._session.get(
                f"{self._base_url}/sms/track/{sms_id}",
                timeout=self._timeout,
            )
        except requests.RequestException as e:
            logger.error("OTPIQ track request failed: %s", e)
            raise AppError(ErrorCode.PROVIDER_UNAVAILABLE)

        if resp.status_code == 200:
            try:
                return resp.json()
            except ValueError:
                raise AppError(ErrorCode.PROVIDER_INVALID_RESPONSE)

        if resp.status_code == 404:
            raise AppError(ErrorCode.NOT_FOUND)

        raise AppError(ErrorCode.PROVIDER_UNAVAILABLE)

    def _simulated_response(self, phone: str, content: str, action: str) -> dict[str, Any]:
        sms_id = f"sim_{phone[-6:]}_{action}"
        logger.info("[OTPIQ SIMULATED] %s to %s: %s", action, phone, content[:50])
        result = {
            "success": True,
            "status": "sent",
            "sms_id": sms_id,
            "cost": 0,
            "remaining_credit": 999999,
            "can_cover": True,
            "simulated": True,
        }
        self._log_transaction(
            {"phoneNumber": phone, "smsType": "verification" if "otp" in action else "custom"},
            result,
            action,
            "sent",
        )
        return result

    def _request(self, endpoint: str, body: dict[str, Any], action: str) -> dict[str, Any]:
        url = f"{self._base_url}/{endpoint.lstrip('/')}"
        try:
            resp = self._session.post(url, json=body, timeout=self._timeout)
            resp_data = self._parse_response(resp, action)
            self._log_transaction(body, resp_data, action, resp_data.get("status", "unknown"))
            if not resp_data.get("success", False):
                error_key = resp_data.get("error_key", "")
                err = OTPIQ_ERROR_MAP.get(error_key, ErrorCode.SMS_SEND_FAILED)
                raise AppError(err)
            return resp_data
        except requests.RequestException as e:
            logger.error("OTPIQ %s connection error: %s", action, e)
            self._log_transaction(body, {"error": str(e)}, action, "failed")
            raise AppError(ErrorCode.PROVIDER_UNAVAILABLE)

    def _parse_response(self, resp: requests.Response, action: str) -> dict[str, Any]:
        result: dict[str, Any] = {"success": False}
        try:
            data = resp.json()
        except ValueError:
            logger.error("OTPIQ %s invalid JSON: %s", action, resp.text[:200])
            raise AppError(ErrorCode.PROVIDER_INVALID_RESPONSE)

        result["raw"] = data

        if resp.status_code == 200:
            result.update({
                "success": True,
                "status": "sent",
                "sms_id": data.get("smsId", ""),
                "cost": data.get("cost", 0),
                "remaining_credit": data.get("remainingCredit", 0),
                "can_cover": data.get("canCover", True),
                "payment_type": data.get("paymentType", "prepaid"),
            })
            return result

        if resp.status_code == 401:
            logger.error("OTPIQ %s auth failed: %s", action, resp.text[:200])
            result.update({
                "error_key": "unauthorized",
                "error_message": data.get("message", "Unauthorized"),
            })
            return result

        if resp.status_code == 429:
            result.update({
                "error_key": "rate_limited",
                "error_message": data.get("message", "Rate limit exceeded"),
                "wait_minutes": data.get("waitMinutes", 0),
            })
            return result

        error_msg = data.get("error", data.get("message", "Unknown error"))

        if isinstance(error_msg, str) and "credit" in error_msg.lower():
            result.update({
                "error_key": "insufficient_credit",
                "error_message": error_msg,
                "your_credit": data.get("yourCredit", 0),
                "required_credit": data.get("requiredCredit", 0),
            })
        elif isinstance(error_msg, str) and "threshold" in error_msg.lower():
            result.update({
                "error_key": "spending_threshold",
                "error_message": error_msg,
            })
        elif isinstance(error_msg, str) and "sender" in error_msg.lower():
            result.update({
                "error_key": "sender_not_found",
                "error_message": error_msg,
            })
        elif isinstance(error_msg, str) and "phone" in error_msg.lower():
            result.update({
                "error_key": "invalid_phone",
                "error_message": error_msg,
            })
        elif isinstance(error_msg, str) and "trial" in error_msg.lower():
            result.update({
                "error_key": "trial_mode",
                "error_message": error_msg,
            })
        else:
            result.update({
                "error_key": "unknown",
                "error_message": error_msg,
            })

        logger.error("OTPIQ %s failed: %s %s", action, resp.status_code, resp.text[:200])
        return result

    def _log_transaction(
        self,
        request_data: dict,
        response_data: dict,
        message_type: str,
        status: str,
    ) -> None:
        try:
            phone = request_data.get("phoneNumber", "")
            with get_session() as session:
                txn = SMSProviderTransaction(
                    phone=phone,
                    provider="otpiq",
                    message_type=message_type,
                    status=status,
                    request_data=request_data,
                    response_data=response_data,
                    error_code=response_data.get("error_key", ""),
                    lang=request_data.get("lang", "en"),
                )
                session.add(txn)
                session.flush()
        except Exception as e:
            logger.error("OTPIQ failed to log transaction: %s", e)
