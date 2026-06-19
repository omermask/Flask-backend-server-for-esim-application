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

SMS_ERROR_MAP: dict[str, ErrorCode] = {
    "1000": ErrorCode.SMS_INIT_FAILED,
    "1001": ErrorCode.SMS_INIT_FAILED,
    "1002": ErrorCode.SMS_PROVIDER_AUTH_FAILED,
    "1003": ErrorCode.SMS_INIT_FAILED,
    "1004": ErrorCode.SMS_INIT_FAILED,
    "1005": ErrorCode.SMS_PROVIDER_AUTH_FAILED,
    "1006": ErrorCode.NOT_FOUND,
    "1007": ErrorCode.SMS_INIT_FAILED,
    "1008": ErrorCode.PROVIDER_RATE_LIMITED,
    "1009": ErrorCode.PROVIDER_UNAVAILABLE,
    "1010": ErrorCode.SMS_INIT_FAILED,
    "1011": ErrorCode.SMS_INIT_FAILED,
    "1012": ErrorCode.SMS_INIT_FAILED,
    "1100": ErrorCode.SMS_PROVIDER_AUTH_FAILED,
    "1101": ErrorCode.SMS_PROVIDER_AUTH_FAILED,
    "1102": ErrorCode.SMS_PROVIDER_AUTH_FAILED,
    "1103": ErrorCode.SMS_PROVIDER_AUTH_FAILED,
    "1104": ErrorCode.SMS_PROVIDER_AUTH_FAILED,
    "1105": ErrorCode.SMS_PROVIDER_AUTH_FAILED,
    "1106": ErrorCode.SMS_PROVIDER_AUTH_FAILED,
    "1107": ErrorCode.SMS_PROVIDER_AUTH_FAILED,
    "1200": ErrorCode.SMS_INIT_FAILED,
    "1201": ErrorCode.SMS_INIT_FAILED,
    "1202": ErrorCode.SMS_INIT_FAILED,
    "1203": ErrorCode.SMS_INIT_FAILED,
    "1204": ErrorCode.VALIDATION_INVALID_PHONE,
    "1205": ErrorCode.SMS_INIT_FAILED,
    "1206": ErrorCode.SMS_INIT_FAILED,
    "1207": ErrorCode.SMS_INIT_FAILED,
    "1208": ErrorCode.SMS_SEND_FAILED,
    "1209": ErrorCode.SMS_INIT_FAILED,
    "1210": ErrorCode.SMS_INIT_FAILED,
    "1211": ErrorCode.SMS_INIT_FAILED,
    "1212": ErrorCode.SMS_INIT_FAILED,
    "1213": ErrorCode.SMS_INIT_FAILED,
    "1214": ErrorCode.SMS_INIT_FAILED,
    "1215": ErrorCode.SMS_INIT_FAILED,
    "1216": ErrorCode.VALIDATION_INVALID_PHONE,
    "1217": ErrorCode.SMS_INIT_FAILED,
    "1300": ErrorCode.PROVIDER_RATE_LIMITED,
    "1301": ErrorCode.PROVIDER_RATE_LIMITED,
    "1302": ErrorCode.PROVIDER_RATE_LIMITED,
    "1303": ErrorCode.PROVIDER_RATE_LIMITED,
    "1400": ErrorCode.PROVIDER_UNAVAILABLE,
    "1401": ErrorCode.PROVIDER_UNAVAILABLE,
    "1402": ErrorCode.NOT_FOUND,
    "1403": ErrorCode.SMS_SEND_FAILED,
    "1500": ErrorCode.SMS_SEND_FAILED,
    "1501": ErrorCode.SMS_SEND_FAILED,
    "1502": ErrorCode.SMS_SEND_FAILED,
    "1503": ErrorCode.SMS_PROVIDER_BALANCE_LOW,
    "1504": ErrorCode.PROVIDER_UNAVAILABLE,
    "1505": ErrorCode.SMS_SEND_FAILED,
    "1506": ErrorCode.SMS_OTP_VERIFICATION_FAILED,
    "1507": ErrorCode.SMS_OTP_VERIFICATION_FAILED,
    "1508": ErrorCode.SMS_OTP_VERIFICATION_FAILED,
    "1509": ErrorCode.SMS_OTP_VERIFICATION_FAILED,
    "1510": ErrorCode.SMS_OTP_VERIFICATION_FAILED,
    "1511": ErrorCode.VALIDATION_INVALID_PHONE,
    "1512": ErrorCode.SMS_OTP_VERIFICATION_FAILED,
    "1513": ErrorCode.SMS_SEND_FAILED,
    "1600": ErrorCode.SMS_INIT_FAILED,
    "1601": ErrorCode.SMS_INIT_FAILED,
    "1602": ErrorCode.SMS_INIT_FAILED,
    "1603": ErrorCode.PROVIDER_UNAVAILABLE,
    "1700": ErrorCode.SMS_PROVIDER_BALANCE_LOW,
    "1701": ErrorCode.SMS_PROVIDER_BALANCE_LOW,
    "1702": ErrorCode.SMS_PROVIDER_BALANCE_LOW,
    "1703": ErrorCode.SMS_PROVIDER_BALANCE_LOW,
    "1704": ErrorCode.SMS_PROVIDER_BALANCE_LOW,
    "1800": ErrorCode.PROVIDER_UNAVAILABLE,
    "1801": ErrorCode.PROVIDER_UNAVAILABLE,
    "1802": ErrorCode.PROVIDER_UNAVAILABLE,
    "1803": ErrorCode.PROVIDER_UNAVAILABLE,
    "1804": ErrorCode.PROVIDER_UNAVAILABLE,
    "1805": ErrorCode.PROVIDER_UNAVAILABLE,
    "1900": ErrorCode.SMS_PROVIDER_AUTH_FAILED,
    "1901": ErrorCode.SMS_PROVIDER_AUTH_FAILED,
    "1902": ErrorCode.SMS_PROVIDER_AUTH_FAILED,
    "1903": ErrorCode.SMS_PROVIDER_AUTH_FAILED,
    "1904": ErrorCode.SMS_PROVIDER_AUTH_FAILED,
    "1905": ErrorCode.PROVIDER_RATE_LIMITED,
    "1906": ErrorCode.PROVIDER_RATE_LIMITED,
}


@sms_provider("bulksmsiraq")
class BulkSMSIraqProvider(SMSProviderBase):

    def __init__(self) -> None:
        self._api_key = settings.BULKSMSIRAQ_API_KEY
        self._sender_id = settings.BULKSMSIRAQ_SENDER_ID
        self._base_url = settings.BULKSMSIRAQ_BASE_URL.rstrip("/") + "/"
        self._timeout = settings.BULKSMSIRAQ_TIMEOUT
        self._simulated = False
        self._ready = True

        if not self._api_key:
            if settings.BULKSMSIRAQ_SANDBOX:
                logger.info("BULKSMSIRAQ_API_KEY not configured — operating in simulated mode")
                self._simulated = True
                return
            logger.error("BULKSMSIRAQ_API_KEY not configured and BULKSMSIRAQ_SANDBOX is False")
            self._ready = False
            return

        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    @property
    def _is_simulated(self) -> bool:
        return self._simulated

    def send_otp(self, phone: str, otp: str, lang: str = "en") -> dict[str, Any]:
        if self._is_simulated:
            return self._simulated_response(phone, otp, "send_otp")
        return self._send_otp_with_fallback(phone, otp, lang, fallback="sms")

    def send_otp_sms(self, phone: str, otp: str, lang: str = "en") -> dict[str, Any]:
        if self._is_simulated:
            return self._simulated_response(phone, otp, "send_otp_sms")
        return self._send_otp_without_fallback(phone, otp, lang, channel="sms")

    def send_otp_whatsapp(self, phone: str, otp: str, lang: str = "en") -> dict[str, Any]:
        if self._is_simulated:
            return self._simulated_response(phone, otp, "send_otp_whatsapp")
        return self._send_otp_without_fallback(phone, otp, lang, channel="whatsapp")

    def send_otp_telegram(self, phone: str, otp: str, lang: str = "en") -> dict[str, Any]:
        if self._is_simulated:
            return self._simulated_response(phone, otp, "send_otp_telegram")
        return self._send_otp_without_fallback(phone, otp, lang, channel="telegram")

    def send_sms(self, phone: str, message: str, lang: str = "en") -> dict[str, Any]:
        if self._is_simulated:
            return self._simulated_response(phone, message, "send_sms")
        if not self._ready:
            raise AppError(ErrorCode.SMS_INIT_FAILED)
        body: dict[str, Any] = {
            "recipient": phone,
            "sender_id": self._sender_id,
            "message": message,
        }
        return self._request("sms/send", body, "send_sms")

    def verify_otp(self, phone: str, code: str, request_id: str, expire: bool = True) -> dict[str, Any]:
        if self._is_simulated:
            return {"success": True, "status": "verified", "simulated": True}
        if not self._ready:
            raise AppError(ErrorCode.SMS_INIT_FAILED)
        body: dict[str, Any] = {
            "recipient": phone,
            "code": code,
            "id": request_id,
        }
        if expire:
            body["expire"] = "yes"
        return self._request("otp/verify", body, "verify_otp")

    def _send_otp_with_fallback(self, phone: str, otp: str, lang: str, fallback: str) -> dict[str, Any]:
        if not self._ready:
            raise AppError(ErrorCode.SMS_INIT_FAILED)
        body: dict[str, Any] = {
            "recipient": phone,
            "sender_id": self._sender_id,
            "channel": "whatsapp",
            "message": otp,
            "fallback": fallback,
            "lang": lang,
        }
        return self._request("otp/send", body, "send_otp")

    def _send_otp_without_fallback(self, phone: str, otp: str, lang: str, channel: str) -> dict[str, Any]:
        if not self._ready:
            raise AppError(ErrorCode.SMS_INIT_FAILED)
        body: dict[str, Any] = {
            "recipient": phone,
            "sender_id": self._sender_id,
            "channel": channel,
            "message": otp,
            "fallback": "none",
            "lang": lang,
        }
        return self._request("otp/send", body, f"send_otp_{channel}")

    def _simulated_response(self, phone: str, content: str, action: str) -> dict[str, Any]:
        sim_id = f"sim_{phone[-6:]}_{action}"
        logger.info("[BULKSMSIRAQ SIMULATED] %s to %s: %s", action, phone, content[:50])
        result = {
            "success": True,
            "status": "sent",
            "id": sim_id,
            "request_id": f"req_{sim_id}",
            "simulated": True,
        }
        self._log_transaction(
            {"recipient": phone},
            result,
            action,
            "sent",
        )
        return result

    def _request(self, endpoint: str, body: dict[str, Any], action: str) -> dict[str, Any]:
        url = self._base_url + endpoint
        try:
            resp = self._session.post(url, json=body, timeout=self._timeout)
            resp_data = self._parse_response(resp, action)
            self._log_transaction(body, resp_data, action, resp_data.get("status", "unknown"))
            if not resp_data.get("success", False):
                error_code = resp_data.get("error_code", "")
                err = SMS_ERROR_MAP.get(error_code, ErrorCode.SMS_SEND_FAILED)
                raise AppError(err)
            return resp_data
        except requests.RequestException as e:
            logger.error("BulkSMSIraq %s connection error: %s", action, e)
            self._log_transaction(body, {"error": str(e)}, action, "failed")
            raise AppError(ErrorCode.PROVIDER_UNAVAILABLE)

    def _parse_response(self, resp: requests.Response, action: str) -> dict[str, Any]:
        result: dict[str, Any] = {"success": False}
        try:
            data = resp.json()
        except ValueError:
            logger.error("BulkSMSIraq %s invalid JSON: %s", action, resp.text[:200])
            self._log_transaction({}, {"raw": resp.text[:500]}, action, "failed")
            raise AppError(ErrorCode.PROVIDER_INVALID_RESPONSE)

        result["raw"] = data

        if resp.status_code == 200:
            err_code = data.get("error", "")
            err_msg = data.get("message", "")
            status = data.get("status", "")
            response_id = data.get("id", "")
            request_id = data.get("request_id", data.get("data", {}).get("request_id", ""))

            if err_code:
                result.update({
                    "error_code": str(err_code),
                    "error_message": err_msg,
                })
            else:
                result.update({
                    "success": True,
                    "status": status,
                    "id": response_id,
                    "request_id": request_id,
                })
        else:
            err_code = data.get("error", str(resp.status_code))
            err_msg = data.get("message", data.get("error_description", ""))
            result.update({
                "error_code": str(err_code),
                "error_message": err_msg,
            })
            logger.error("BulkSMSIraq %s failed: %s %s", action, resp.status_code, resp.text[:200])

        return result

    def _log_transaction(self, request_data: dict, response_data: dict, message_type: str, status: str) -> None:
        try:
            phone = request_data.get("recipient", "")
            with get_session() as session:
                txn = SMSProviderTransaction(
                    phone=phone,
                    provider="bulksmsiraq",
                    message_type=message_type,
                    status=status,
                    request_data=request_data,
                    response_data=response_data,
                    error_code=response_data.get("error_code", ""),
                    lang=request_data.get("lang", "en"),
                )
                session.add(txn)
                session.flush()
        except Exception as e:
            logger.error("BulkSMSIraq failed to log transaction: %s", e)
