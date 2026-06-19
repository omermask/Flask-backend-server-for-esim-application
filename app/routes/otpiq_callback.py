from __future__ import annotations

import hmac
import logging
from typing import Any

from flask import Blueprint, request

from app.core.database import get_session
from app.core.errors import ErrorCode
from app.core.response import UnifiedResponse
from app.models.sms import SMSProviderTransaction
from config import settings

logger = logging.getLogger("esim-ego")

otpiq_callback_routes = Blueprint(
    "otpiq_callback", __name__, url_prefix="/api/v1/callback/otpiq",
)

OTPIQ_WEBHOOK_ALLOWED_IPS = {"52.0.0.0/8", "54.0.0.0/8"}


def _ip_in_allowed_ranges(ip: str) -> bool:
    import ipaddress
    try:
        addr = ipaddress.ip_address(ip)
        for cidr in OTPIQ_WEBHOOK_ALLOWED_IPS:
            if addr in ipaddress.ip_network(cidr):
                return True
    except ValueError:
        pass
    return False


def _verify_webhook_secret(headers: dict[str, str]) -> bool:
    webhook_secret = settings.OTPIQ_WEBHOOK_SECRET
    if not webhook_secret:
        return True
    received_secret = headers.get("X-OTPIQ-Webhook-Secret", "")
    if not received_secret:
        logger.warning("OTPIQ callback: missing X-OTPIQ-Webhook-Secret header")
        return False
    return hmac.compare_digest(webhook_secret, received_secret)


@otpiq_callback_routes.route("/delivery", methods=["POST"])
def delivery_callback():
    forwarded = request.headers.get("X-Forwarded-For", "")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (request.remote_addr or "")
    if not _ip_in_allowed_ranges(client_ip) and not settings.IS_DEVELOPMENT:
        logger.warning("OTPIQ callback from unexpected IP: %s", client_ip)
        return UnifiedResponse.from_error_code(ErrorCode.AUTH_UNAUTHORIZED)

    if not _verify_webhook_secret(dict(request.headers)):
        return UnifiedResponse.from_error_code(ErrorCode.AUTH_UNAUTHORIZED)

    data: dict[str, Any] = {}
    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        pass
    if not isinstance(data, dict) or not data:
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_INVALID_JSON)

    sms_id = data.get("smsId", "")
    status = data.get("status", "")
    if not sms_id or not status:
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_MISSING_FIELD)

    with get_session() as session:
        txns = session.query(SMSProviderTransaction).filter(
            SMSProviderTransaction.response_data["smsId"].as_string() == sms_id,
        ).order_by(SMSProviderTransaction.created_at.desc()).limit(1).all()
        if not txns:
            logger.warning("OTPIQ callback: no txn found for smsId %s", sms_id)
            return UnifiedResponse.success(data={"matched": False})
        txn = txns[0]
        old_status = txn.status
        if status in ("delivered", "sent", "failed", "expired", "rejected"):
            txn.status = status
        if not txn.response_data:
            txn.response_data = {}
        txn.response_data["callback"] = data
        txn.response_data["previous_status"] = old_status
        session.flush()

    logger.info("OTPIQ callback: smsId=%s status=%s (was %s)", sms_id, status, old_status)
    return UnifiedResponse.success(data={"matched": True, "status": status})
