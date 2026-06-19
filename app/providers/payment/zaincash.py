from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import jwt
import requests

from app.core.errors import AppError, ErrorCode
from app.providers.base import PaymentProviderBase
from app.providers.registry import payment_provider
from config import settings

logger = logging.getLogger("esim-ego")

_ZAINCASH_JWT_ALGORITHM = "HS256"
_ZAINCALLBACK_TIMEOUT = 15
_ZAINCASH_SERVICE_TYPE = "Other"


@payment_provider("zaincash")
class ZainCashProvider(PaymentProviderBase):

    @property
    def _base_url(self) -> str:
        if settings.ZAINCASH_TEST:
            return "https://pg-api-uat.zaincash.iq"
        return "https://pg-api.zaincash.iq"

    @property
    def _is_simulated(self) -> bool:
        return (
            settings.ZAINCASH_TEST
            and not settings.ZAINCASH_CLIENT_ID
            and not settings.ZAINCASH_CLIENT_SECRET
        )

    def _get_jwt_secret(self) -> str:
        return settings.ZAINCASH_SECRET or settings.ZAINCASH_CLIENT_SECRET or ""

    def _get_access_token(self) -> str:
        if self._is_simulated:
            return "sim_access_token"
        client_id = settings.ZAINCASH_CLIENT_ID or settings.ZAINCASH_MERCHANT_ID
        client_secret = settings.ZAINCASH_CLIENT_SECRET or settings.ZAINCASH_SECRET
        if not client_id or not client_secret:
            raise AppError(ErrorCode.PROVIDER_AUTH_FAILED)
        try:
            resp = requests.post(
                f"{self._base_url}/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scope": "payment:read payment:write reverse:write",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=_ZAINCALLBACK_TIMEOUT,
                verify=not settings.ZAINCASH_TEST,
            )
            if resp.status_code == 200:
                data = resp.json()
                token = data.get("access_token", "")
                if not token:
                    logger.error("ZainCash OAuth missing access_token: %s", resp.text[:300])
                    raise AppError(ErrorCode.PROVIDER_AUTH_FAILED)
                return token
            logger.error(
                "ZainCash OAuth failed: %s %s",
                resp.status_code, resp.text[:300],
            )
            raise AppError(ErrorCode.PROVIDER_AUTH_FAILED)
        except requests.RequestException as e:
            logger.error("ZainCash OAuth connection failed: %s", e)
            raise AppError(ErrorCode.PROVIDER_UNAVAILABLE)

    def initiate_payment(
        self,
        amount: int,
        order_id: str,
        callback_url: str,
    ) -> dict:
        if self._is_simulated:
            txn_id = f"sim_{uuid.uuid4().hex[:12]}"
            logger.info("[SIMULATED] ZainCash v2 initiate_payment amount=%d order=%s", amount, order_id)
            redirect_url = f"{self._base_url}/transaction/pay?id={txn_id}&token=sim_token"
            return {
                "transaction_id": txn_id,
                "redirect_url": redirect_url,
                "payment_url": redirect_url,
                "simulated": True,
            }

        token = self._get_access_token()
        ref_id = str(uuid.uuid4())
        customer_phone = settings.ZAINCASH_MSISDN
        language = "en"

        try:
            resp = requests.post(
                f"{self._base_url}/api/v2/payment-gateway/transaction/init",
                json={
                    "language": language,
                    "externalReferenceId": ref_id,
                    "orderId": order_id,
                    "serviceType": _ZAINCASH_SERVICE_TYPE,
                    "amount": {
                        "value": str(amount),
                        "currency": "IQD",
                    },
                    "customer": {
                        "phone": customer_phone,
                    } if customer_phone else {},
                    "redirectUrls": {
                        "successUrl": callback_url,
                        "failureUrl": callback_url,
                    },
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=_ZAINCALLBACK_TIMEOUT,
                verify=not settings.ZAINCASH_TEST,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") != "SUCCESS":
                    logger.error("ZainCash init not SUCCESS: %s", resp.text[:300])
                    raise AppError(ErrorCode.ZAINCASH_INIT_FAILED)
                txn_details = data.get("transactionDetails", {})
                txn_id = txn_details.get("transactionId", "")
                redirect_url = data.get("redirectUrl", "")
                if not txn_id or not redirect_url:
                    logger.error("ZainCash init missing fields: %s", resp.text[:300])
                    raise AppError(ErrorCode.ZAINCASH_INIT_FAILED)
                return {
                    "transaction_id": txn_id,
                    "redirect_url": redirect_url,
                    "payment_url": redirect_url,
                    "external_reference_id": ref_id,
                    "expiry_time": data.get("expiryTime", ""),
                }
            logger.error(
                "ZainCash init failed: %s %s",
                resp.status_code, resp.text[:300],
            )
            raise AppError(ErrorCode.ZAINCASH_INIT_FAILED)
        except requests.RequestException as e:
            logger.error("ZainCash init connection failed: %s", e)
            raise AppError(ErrorCode.PROVIDER_UNAVAILABLE)

    def _verify_jwt(self, token_str: str) -> dict:
        secret = self._get_jwt_secret()
        if self._is_simulated:
            if token_str == "sim_token":
                return {
                    "eventType": "STATUS_CHANGED",
                    "eventId": str(uuid.uuid4()),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "data": {
                        "transactionId": f"sim_{uuid.uuid4().hex[:12]}",
                        "merchantReferenceId": "",
                        "customerMsisdn": "96478xxxxxxx",
                        "orderId": "sim_order",
                        "currentStatus": "SUCCESS",
                        "amount": {"currency": "IQD", "value": 0, "feeValue": 0},
                    },
                }
        if not secret:
            raise AppError(ErrorCode.PROVIDER_AUTH_FAILED)
        try:
            result = jwt.decode(
                token_str,
                secret,
                algorithms=[_ZAINCASH_JWT_ALGORITHM],
                options={"require": ["eventType", "eventId", "data"]},
            )
            return result
        except jwt.ExpiredSignatureError:
            raise AppError(ErrorCode.ZAINCASH_CALLBACK_INVALID)
        except jwt.InvalidTokenError:
            raise AppError(ErrorCode.ZAINCASH_CALLBACK_INVALID)

    def verify_callback(self, token_str: str) -> dict:
        payload = self._verify_jwt(token_str)
        data = payload.get("data", {})
        current_status = data.get("currentStatus", "FAILED")
        status_map = {
            "SUCCESS": "success",
            "FAILED": "failed",
            "EXPIRED": "expired",
            "REFUNDED": "refunded",
        }
        status = status_map.get(current_status, "failed")
        error_msg = data.get("errorMessage") or ""
        return {
            "status": status,
            "order_id": data.get("orderId", ""),
            "transaction_id": data.get("transactionId", ""),
            "customer_msisdn": data.get("customerMsisdn", ""),
            "operation_id": data.get("operationId"),
            "msg": error_msg,
            "event_id": payload.get("eventId", ""),
            "event_type": payload.get("eventType", ""),
            "amount": data.get("amount", {}).get("value"),
            "currency": data.get("amount", {}).get("currency", "IQD"),
        }

    def check_transaction(self, transaction_id: str) -> dict:
        if not transaction_id:
            raise AppError(ErrorCode.ZAINCASH_TRANSACTION_NOT_FOUND)
        if transaction_id.startswith("sim_") and self._is_simulated:
            logger.info("[SIMULATED] ZainCash check_transaction %s", transaction_id)
            return {"status": "SUCCESS", "simulated": True}

        token = self._get_access_token()
        try:
            resp = requests.get(
                f"{self._base_url}/api/v2/payment-gateway/transaction/inquiry/{transaction_id}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=_ZAINCALLBACK_TIMEOUT,
                verify=not settings.ZAINCASH_TEST,
            )
            if resp.status_code == 200:
                return resp.json()
            logger.error(
                "ZainCash inquiry failed: %s %s",
                resp.status_code, resp.text[:200],
            )
            return {"status": "UNKNOWN"}
        except requests.RequestException as e:
            logger.error("ZainCash inquiry error: %s", e)
            raise AppError(ErrorCode.PROVIDER_UNAVAILABLE)

    def reverse_transaction(self, transaction_id: str, reason: str = "") -> dict:
        if transaction_id.startswith("sim_") and self._is_simulated:
            logger.info("[SIMULATED] ZainCash reverse %s", transaction_id)
            return {
                "status": "COMPLETED",
                "reversalReferenceId": f"rev_{uuid.uuid4().hex[:12]}",
                "simulated": True,
            }

        token = self._get_access_token()
        try:
            resp = requests.post(
                f"{self._base_url}/api/v2/payment-gateway/transaction/reverse",
                json={
                    "transactionId": transaction_id,
                    "reason": reason or "merchant_initiated_refund",
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=_ZAINCALLBACK_TIMEOUT,
                verify=not settings.ZAINCASH_TEST,
            )
            if resp.status_code == 200:
                return resp.json()
            logger.error(
                "ZainCash reverse failed: %s %s",
                resp.status_code, resp.text[:200],
            )
            raise AppError(ErrorCode.PAYMENT_REFUND_FAILED)
        except requests.RequestException as e:
            logger.error("ZainCash reverse error: %s", e)
            raise AppError(ErrorCode.PROVIDER_UNAVAILABLE)

    def verify_webhook(self, data: dict, signature: str) -> bool:
        token = data.get("token") or data.get("webhook_token") or ""
        if not token:
            return False
        try:
            self.verify_callback(token)
            return True
        except AppError:
            return False
