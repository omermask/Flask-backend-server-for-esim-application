from __future__ import annotations

import base64
import logging

import requests

from app.core.errors import AppError, ErrorCode
from app.providers.base import PaymentProviderBase
from app.providers.registry import payment_provider
from config import settings

logger = logging.getLogger("esim-ego")

_QICARD_STATUS_CREATED = "CREATED"
_QICARD_STATUS_FORM_SHOWED = "FORM_SHOWED"
_QICARD_STATUS_THREEDS_METHOD_CALL = "THREE_DS_METHOD_CALL_REQUIRED"
_QICARD_STATUS_AUTH_REQUIRED = "AUTHENTICATION_REQUIRED"
_QICARD_STATUS_AUTH_STARTED = "AUTHENTICATION_STARTED"
_QICARD_STATUS_AUTH_FAILED = "AUTHENTICATION_FAILED"
_QICARD_STATUS_AUTHENTICATED = "AUTHENTICATED"
_QICARD_STATUS_INITIALIZED = "INITIALIZED"
_QICARD_STATUS_STARTED = "STARTED"
_QICARD_STATUS_SUCCESS = "SUCCESS"
_QICARD_STATUS_FAILED = "FAILED"
_QICARD_STATUS_ERROR = "ERROR"
_QICARD_STATUS_EXPIRED = "EXPIRED"

_QICARD_RESULT_CODE_SUCCESS = "0"

_REFUND_STATUS_SUCCESS = "SUCCESS"
_REFUND_STATUS_FAILED = "FAILED"
_REFUND_STATUS_PROCESSING = "PROCESSING"


@payment_provider("qicard")
class QiCardProvider(PaymentProviderBase):

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.auth = (settings.QICARD_USERNAME, settings.QICARD_PASSWORD)
        self._session.headers.update(
            {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Terminal-Id": settings.QICARD_TERMINAL_ID,
            }
        )

    @property
    def _base_url(self) -> str:
        url = settings.QICARD_BASE_URL.rstrip("/")
        if settings.QICARD_SANDBOX and "sandbox" not in url and "uat" not in url:
            return "https://uat-sandbox-3ds-api.qi.iq/api/v1"
        return url

    @property
    def _is_simulated(self) -> bool:
        return (
            settings.QICARD_TEST
            and not settings.QICARD_USERNAME
            and not settings.QICARD_PASSWORD
        )

    def _parse_error(self, resp: requests.Response, default_code: str = "qicard_init_failed") -> AppError:
        try:
            data = resp.json()
            err = data.get("error") or {}
            code = err.get("code", 0)
            message = err.get("message", "")
            logger.error(
                "QiCard API error: http=%d code=%d message=%s",
                resp.status_code, code, message,
            )
        except Exception:
            logger.error("QiCard API error: http=%d body=%s", resp.status_code, resp.text[:300])
        return AppError(ErrorCode(default_code))

    def _get(self, path: str) -> requests.Response:
        return self._session.get(
            f"{self._base_url}{path}",
            timeout=settings.QICARD_TIMEOUT,
        )

    def _post(self, path: str, json_data: dict | None = None) -> requests.Response:
        return self._session.post(
            f"{self._base_url}{path}",
            json=json_data or {},
            timeout=settings.QICARD_TIMEOUT,
        )

    def initiate_payment(
        self,
        amount: int | float,
        order_id: str,
        callback_url: str,
        customer_info: dict | None = None,
        additional_info: dict | None = None,
    ) -> dict:
        if self._is_simulated:
            return {
                "transaction_id": f"sim_{order_id[:16]}",
                "payment_url": f"{self._base_url}/payment/sim_{order_id[:16]}",
                "request_id": order_id,
                "status": "CREATED",
                "amount": amount,
                "currency": settings.QICARD_CURRENCY,
                "creation_date": "",
                "canceled": False,
            }
        if not settings.QICARD_USERNAME or not settings.QICARD_PASSWORD:
            raise AppError(ErrorCode.PROVIDER_AUTH_FAILED)
        if not settings.QICARD_TERMINAL_ID:
            raise AppError(ErrorCode.PROVIDER_AUTH_FAILED)
        finish_url = callback_url
        notification_url = callback_url
        if additional_info:
            notification_url = additional_info.get("notification_url", callback_url)
        payload: dict = {
            "requestId": order_id,
            "amount": float(amount),
            "currency": settings.QICARD_CURRENCY,
            "finishPaymentUrl": finish_url,
            "notificationUrl": notification_url,
            "locale": settings.QICARD_LOCALE,
        }
        if customer_info:
            payload["customerInfo"] = {k: v for k, v in customer_info.items() if v is not None}
        if additional_info:
            extra = {k: v for k, v in additional_info.items() if k != "notification_url"}
            if extra:
                payload["additionalInfo"] = extra
        try:
            resp = self._post("/payment", payload)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("error"):
                    self._parse_error(resp, "qicard_init_failed")
                    raise AppError(ErrorCode.QICARD_INIT_FAILED)
                form_url = data.get("formUrl", "")
                payment_id = data.get("paymentId", "")
                if not form_url:
                    logger.error("QiCard init missing formUrl: %s", resp.text[:300])
                    raise AppError(ErrorCode.QICARD_INIT_FAILED)
                return {
                    "transaction_id": payment_id or "",
                    "payment_url": form_url,
                    "request_id": data.get("requestId", order_id),
                    "status": data.get("status", ""),
                    "amount": data.get("amount", amount),
                    "currency": data.get("currency", settings.QICARD_CURRENCY),
                    "creation_date": data.get("creationDate", ""),
                    "canceled": data.get("canceled", False),
                }
            self._parse_error(resp, "qicard_init_failed")
            raise AppError(ErrorCode.QICARD_INIT_FAILED)
        except requests.RequestException as e:
            logger.error("QiCard connection failed: %s", e)
            raise AppError(ErrorCode.PROVIDER_UNAVAILABLE)

    def get_payment_status(self, payment_id: str) -> dict:
        if self._is_simulated:
            return {"status": "SUCCESS", "is_success": True, "payment_id": payment_id}
        if not payment_id:
            raise AppError(ErrorCode.QICARD_TRANSACTION_NOT_FOUND)
        try:
            resp = self._get(f"/payment/{payment_id}/status")
            if resp.status_code == 200:
                data = resp.json()
                if data.get("error"):
                    self._parse_error(resp, "qicard_verification_failed")
                    return {"status": "UNKNOWN", "is_success": False}
                return self._build_status_response(data)
            logger.error("QiCard status by payment_id failed: %s %s", resp.status_code, resp.text[:200])
            return {"status": "UNKNOWN", "is_success": False}
        except requests.RequestException as e:
            logger.error("QiCard status check error: %s", e)
            raise AppError(ErrorCode.PROVIDER_UNAVAILABLE)

    def verify_payment(self, request_id: str) -> dict:
        if self._is_simulated:
            return {"status": "SUCCESS", "is_success": True, "request_id": request_id}
        if not request_id:
            raise AppError(ErrorCode.QICARD_TRANSACTION_NOT_FOUND)
        try:
            resp = self._get(f"/payment/status/by/request/{request_id}")
            if resp.status_code == 200:
                data = resp.json()
                if data.get("error"):
                    self._parse_error(resp, "qicard_verification_failed")
                    return {"status": "UNKNOWN", "is_success": False}
                return self._build_status_response(data)
            logger.error("QiCard status by request failed: %s %s", resp.status_code, resp.text[:200])
            return {"status": "UNKNOWN", "is_success": False}
        except requests.RequestException as e:
            logger.error("QiCard status check error: %s", e)
            raise AppError(ErrorCode.PROVIDER_UNAVAILABLE)

    def _build_status_response(self, data: dict) -> dict:
        status = data.get("status", "UNKNOWN")
        is_success = status == _QICARD_STATUS_SUCCESS
        details = data.get("details") or {}
        return {
            "status": status,
            "is_success": is_success,
            "request_id": data.get("requestId", ""),
            "payment_id": data.get("paymentId", ""),
            "amount": data.get("confirmedAmount") or data.get("amount"),
            "confirmed_amount": data.get("confirmedAmount"),
            "currency": data.get("currency", ""),
            "canceled": data.get("canceled", False),
            "payment_type": data.get("paymentType", ""),
            "creation_date": data.get("creationDate", ""),
            "without_authenticate": data.get("withoutAuthenticate", False),
            "details": details,
            "additional_info": data.get("additionalInfo"),
            "card_masked_pan": details.get("maskedPan", ""),
            "card_payment_system": details.get("paymentSystem", ""),
            "card_auth_id": details.get("authId", ""),
            "card_rrn": details.get("rrn", ""),
            "card_result_code": details.get("resultCode", ""),
        }

    def _build_cancel_response(self, data: dict, amount: int | float = 0) -> dict:
        return {
            "request_id": data.get("requestId", ""),
            "payment_id": data.get("paymentId", ""),
            "status": data.get("status", ""),
            "canceled": data.get("canceled", False),
            "amount": data.get("amount", amount),
            "currency": data.get("currency", ""),
            "cancels": data.get("cancels", []),
            "without_authenticate": data.get("withoutAuthenticate", False),
        }

    def _build_refund_response(self, data: dict, amount: int | float = 0) -> dict:
        details = data.get("details") or {}
        return {
            "refund_id": data.get("refundId", ""),
            "request_id": data.get("requestId", ""),
            "payment_id": data.get("paymentId", ""),
            "status": data.get("status", ""),
            "amount": data.get("amount", amount),
            "currency": data.get("currency", ""),
            "message": data.get("message", ""),
            "creation_date": data.get("creationDate", ""),
            "canceled": data.get("canceled", False),
            "cancels": data.get("cancels", []),
            "card_masked_pan": details.get("maskedPan", ""),
            "card_payment_system": details.get("paymentSystem", ""),
            "card_rrn": details.get("rrn", ""),
        }

    def cancel_payment(self, payment_id: str, cancel_request_id: str, amount: int | float = 0) -> dict:
        return self._cancel_or_refund("cancel", payment_id, cancel_request_id, amount)

    def cancel_payment_by_request(self, request_id: str, cancel_request_id: str, amount: int | float = 0) -> dict:
        if not request_id:
            raise AppError(ErrorCode.QICARD_TRANSACTION_NOT_FOUND)
        return self._cancel_or_refund("cancel", request_id, cancel_request_id, amount, by_request=True)

    def refund_payment(self, payment_id: str, refund_request_id: str, amount: int | float = 0, message: str = "") -> dict:
        return self._cancel_or_refund("refund", payment_id, refund_request_id, amount, message)

    def refund_payment_by_request(self, request_id: str, refund_request_id: str, amount: int | float = 0, message: str = "") -> dict:
        if not request_id:
            raise AppError(ErrorCode.QICARD_TRANSACTION_NOT_FOUND)
        return self._cancel_or_refund("refund", request_id, refund_request_id, amount, message, by_request=True)

    def _cancel_or_refund(
        self, action: str, identifier: str, idem_id: str, amount: int | float = 0,
        message: str = "", by_request: bool = False,
    ) -> dict:
        is_refund = action == "refund"
        err_code = ErrorCode.QICARD_REFUND_FAILED if is_refund else ErrorCode.QICARD_CANCEL_FAILED
        err_code_name = "qicard_refund_failed" if is_refund else "qicard_cancel_failed"
        if self._is_simulated:
            return {
                "request_id": idem_id,
                "payment_id": identifier,
                "status": "SUCCESS",
                "canceled": False,
                "amount": amount,
                "currency": settings.QICARD_CURRENCY,
            }
        if not identifier:
            raise AppError(ErrorCode.QICARD_TRANSACTION_NOT_FOUND)
        if not idem_id:
            raise AppError(err_code)
        if by_request:
            path = f"/payment/{action}/by/request/{identifier}"
        else:
            path = f"/payment/{identifier}/{action}"
        payload: dict = {"requestId": idem_id}
        if is_refund and amount > 0:
            payload["amount"] = float(amount)
        if is_refund and message:
            payload["message"] = message
        try:
            resp = self._post(path, payload)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("error"):
                    self._parse_error(resp, err_code_name)
                    raise AppError(err_code)
                if is_refund:
                    return self._build_refund_response(data, amount)
                return self._build_cancel_response(data, amount)
            self._parse_error(resp, err_code_name)
            raise AppError(err_code)
        except requests.RequestException as e:
            logger.error("QiCard %s connection error: %s", action, e)
            raise AppError(ErrorCode.PROVIDER_UNAVAILABLE)

    def handle_webhook(self, data: dict | None) -> dict:
        if not data:
            raise AppError(ErrorCode.QICARD_WEBHOOK_INVALID)
        status = data.get("status", "UNKNOWN")
        request_id = data.get("requestId", "")
        payment_id = data.get("paymentId", "")
        amount = data.get("confirmedAmount") or data.get("amount")
        details = data.get("details") or {}
        result_code = str(details.get("resultCode", "-1"))
        if not request_id:
            raise AppError(ErrorCode.QICARD_WEBHOOK_INVALID)
        is_success = status == _QICARD_STATUS_SUCCESS or result_code == _QICARD_RESULT_CODE_SUCCESS
        return {
            "status": "success" if is_success else "failed",
            "is_success": is_success,
            "request_id": request_id,
            "payment_id": payment_id,
            "amount": amount,
            "currency": data.get("currency", "IQD"),
            "confirmed_amount": data.get("confirmedAmount"),
            "result_code": result_code,
            "error_code": data.get("errorCode"),
            "error_message": data.get("errorMessage"),
            "card_masked_pan": details.get("maskedPan", ""),
            "card_payment_system": details.get("paymentSystem", ""),
            "card_auth_id": details.get("authId", ""),
            "card_rrn": details.get("rrn", ""),
            "without_authenticate": data.get("withoutAuthenticate", False),
        }

    def verify_webhook(self, data: dict, signature: str) -> bool:
        if not signature:
            logger.error("QiCard webhook missing X-Signature header")
            return False
        if not settings.QICARD_WEBHOOK_PUBLIC_KEY:
            logger.error("QiCard webhook public key not configured")
            return False
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
            payment_id = data.get("paymentId", "-")
            amount = data.get("amount", 0)
            currency = data.get("currency", "-")
            creation_date = data.get("creationDate", "-")
            status = data.get("status", "-")
            data_str = f"{payment_id}|{float(amount):.3f}|{currency}|{creation_date}|{status}"
            public_key = serialization.load_pem_public_key(
                settings.QICARD_WEBHOOK_PUBLIC_KEY.encode("utf-8")
            )
            sig_bytes = base64.b64decode(signature)
            public_key.verify(sig_bytes, data_str.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
            return True
        except Exception as e:
            logger.error("QiCard webhook signature verification failed: %s", e)
            return False
