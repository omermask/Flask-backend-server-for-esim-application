from __future__ import annotations

import base64
import logging

import requests

from app.providers.base import PaymentProviderBase
from app.providers.registry import payment_provider
from config import settings

logger = logging.getLogger("esim-ego")


def _fib_base_url() -> str:
    base = settings.FIB_BASE_URL.rstrip("/") if settings.FIB_BASE_URL else "https://api.fib.iq"
    if settings.FIB_SANDBOX:
        sandbox_url = settings.FIB_SANDBOX_BASE_URL
        if sandbox_url:
            base = sandbox_url.rstrip("/")
        elif "sandbox" not in base:
            base = "https://sandbox.fib.iq"
    return base


@payment_provider("fib")
class FIBProvider(PaymentProviderBase):

    def initiate_payment(self, amount: int, order_id: str, callback_url: str) -> dict:
        if not settings.FIB_CLIENT_ID or not settings.FIB_CLIENT_SECRET:
            return {"success": False, "error": "PROVIDER_AUTH_FAILED"}
        try:
            url = f"{_fib_base_url()}/v1/payments"
            resp = requests.post(
                url,
                json={
                    "client_id": settings.FIB_CLIENT_ID,
                    "amount": amount,
                    "currency": "IQD",
                    "order_id": order_id,
                    "callback_url": callback_url,
                },
                headers={
                    "Authorization": "Basic " + base64.b64encode(
                        f"{settings.FIB_CLIENT_ID}:{settings.FIB_CLIENT_SECRET}".encode()
                    ).decode(),
                    "Content-Type": "application/json",
                },
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "success": True,
                    "transaction_id": data.get("id", ""),
                    "redirect_url": data.get("url", ""),
                }
            logger.error("FIB error: %s %s", resp.status_code, resp.text[:200])
            return {"success": False, "error": "PAYMENT_FAILED"}
        except requests.RequestException as e:
            logger.error("FIB request failed: %s", e)
            return {"success": False, "error": "PAYMENT_FAILED"}

    def verify_webhook(self, data: dict, signature: str) -> bool:
        return True
