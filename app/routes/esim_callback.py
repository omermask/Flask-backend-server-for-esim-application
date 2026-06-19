from __future__ import annotations

import hmac
import logging

from flask import Blueprint, request

from app.core.database import get_session
from app.core.errors import AppError, ErrorCode
from app.core.response import UnifiedResponse
from app.models.esim import EsimProviderTransaction
from app.models.inventory import EsimInventory
from app.models.order import OrderItem
from app.providers.registry import ProviderRegistry
from config import settings

logger = logging.getLogger("esim-ego")
esim_callback_routes = Blueprint("esim_callback", __name__, url_prefix="/api/v1/esim")


@esim_callback_routes.route("/callback", methods=["POST"])
def esim_callback():
    raw_body = request.get_data()
    if not raw_body:
        return UnifiedResponse.from_error_code(ErrorCode.ESIM_CALLBACK_INVALID)

    api_key = request.headers.get("X-API-KEY", "")
    signature = request.headers.get("X-API-Signature", "")
    if signature:
        try:
            provider = ProviderRegistry.get_esim(settings.ESIM_PROVIDER)
            if provider and hasattr(provider, "validate_callback_signature"):
                if not provider.validate_callback_signature(raw_body, signature):
                    logger.warning("eSIM callback with invalid HMAC signature")
                    return UnifiedResponse.from_error_code(ErrorCode.ESIM_CALLBACK_INVALID)
        except Exception:
            logger.warning("eSIM callback signature validation failed")
            return UnifiedResponse.from_error_code(ErrorCode.ESIM_CALLBACK_INVALID)
    elif not api_key or not hmac.compare_digest(api_key, settings.ESIMGO_API_KEY):
        logger.warning("eSIM callback with invalid API key")
        return UnifiedResponse.from_error_code(ErrorCode.ESIM_CALLBACK_INVALID)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return UnifiedResponse.from_error_code(ErrorCode.ESIM_CALLBACK_INVALID)

    alert_type = data.get("alertType", "")

    provider = ProviderRegistry.get_esim(settings.ESIM_PROVIDER)
    if not provider:
        return UnifiedResponse.from_error_code(ErrorCode.PROVIDER_UNAVAILABLE)

    try:
        if alert_type in ("DataUsage", "DataWarning"):
            return _process_usage_callback(provider, data)
        elif alert_type in ("Topup", "AutoTopup", "eSIMGoTopup"):
            return _process_topup_callback(provider, data)
        elif alert_type == "FirstAttachment":
            return _process_first_attachment_callback(provider, data)
        elif alert_type == "CountryChange":
            return _process_location_update_callback(provider, data)
        elif alert_type == "FirstUse":
            return _process_first_use_callback(provider, data)
        elif alert_type in ("LowBalance", "InsufficientBalance"):
            return _process_balance_notification(provider, data)
        elif alert_type == "MSISDNEnabled":
            return _process_msisdn_enabled(provider, data)
        elif alert_type == "MSISDNDisabled":
            return _process_msisdn_disabled(provider, data)
        else:
            logger.warning("Unknown eSIM callback alertType=%s", alert_type)
            _log_callback("", "unknown_alert_type", data, {"alert_type": alert_type})
            return UnifiedResponse.success(data={"status": "ignored", "reason": f"unknown alertType: {alert_type}"})
    except AppError as e:
        return UnifiedResponse.from_error_code(e.code)


def _log_callback(
    iccid: str,
    status: str,
    request_data: dict,
    response_data: dict,
    action_type: str = "usage_callback",
) -> None:
    try:
        with get_session() as session:
            txn = EsimProviderTransaction(
                iccid=iccid,
                provider="esimgo",
                action_type=action_type,
                status=status,
                request_data=request_data,
                response_data=response_data,
            )
            session.add(txn)
            session.flush()
    except Exception as e:
        logger.error("Failed to log callback transaction: %s", e)


def _find_user_by_iccid(iccid: str) -> str | None:
    with get_session() as session:
        record = session.query(EsimInventory).filter(
            EsimInventory.iccid == iccid,
        ).first()
        if not record or not record.order_item_id:
            return None
        order_item = session.query(OrderItem).filter(
            OrderItem.id == record.order_item_id,
        ).first()
        if not order_item or not order_item.order:
            return None
        return str(order_item.order.user_id)


def _send_push(user_id: str, template_key: str, data: dict | None = None) -> None:
    try:
        from app.services.notification_template_service import NotificationTemplateService
        rendered = NotificationTemplateService.render_for_user(
            template_key, user_id, **(data or {}),
        )
        if not rendered:
            return
        title, body = rendered
        from app.tasks.push_tasks import send_push_notification
        send_push_notification.delay(
            user_id=user_id,
            title=title,
            body=body,
            data=data,
        )
    except Exception:
        logger.debug("Push notification skipped for user %s: %s", user_id, template_key)


def _process_usage_callback(provider, data: dict) -> UnifiedResponse:
    result = provider.handle_usage_callback(data)
    iccid = result.get("iccid", "")
    usage_mb = result.get("data_usage_mb", 0)
    if not iccid or usage_mb is None:
        return UnifiedResponse.from_error_code(ErrorCode.ESIM_CALLBACK_INVALID)

    with get_session() as session:
        record = session.query(EsimInventory).filter(
            EsimInventory.iccid == iccid,
        ).first()
        if not record:
            logger.warning("Usage callback for unknown ICCID=%s", iccid)
            _log_callback(iccid, "unknown_iccid", data, {"error": "ICCID not found"})
            return UnifiedResponse.success(data={"status": "ignored", "reason": "ICCID not found"})
        current = record.data_usage_mb or 0
        if usage_mb > current:
            record.data_usage_mb = usage_mb
        _log_callback(iccid, "success", data, {"iccid": iccid, "usage_mb": usage_mb})

    user_id = _find_user_by_iccid(iccid)
    if user_id:
        _send_push(
            user_id=user_id,
            template_key="data_usage",
            data={"type": "data_usage", "iccid": iccid, "usage_mb": usage_mb},
        )

    return UnifiedResponse.success(data={"status": "updated", "iccid": iccid, "data_usage_mb": usage_mb})


def _process_topup_callback(provider, data: dict) -> UnifiedResponse:
    result = provider.handle_topup_callback(data)
    alert_type = result.get("alert_type", "Topup")
    _log_callback("", "success", data, result, action_type="topup_callback")

    iccid = result.get("iccid", "")
    if iccid:
        user_id = _find_user_by_iccid(iccid)
        if user_id:
            _send_push(
                user_id=user_id,
                template_key="bundle_topup",
                data={"type": "topup", "iccid": iccid, "alert_type": alert_type},
            )

    return UnifiedResponse.success(data={
        "status": "received",
        "alert_type": alert_type,
        "old_amount": result.get("old_amount"),
        "new_amount": result.get("new_amount"),
    })


def _process_first_attachment_callback(provider, data: dict) -> UnifiedResponse:
    result = provider.handle_first_attachment_callback(data)
    iccid = result.get("iccid", "")
    with get_session() as session:
        record = session.query(EsimInventory).filter(
            EsimInventory.iccid == iccid,
        ).first()
        if record and record.status not in ("activated", "suspended", "revoked"):
            record.status = "activated"
            from datetime import datetime, timezone
            record.activated_at = datetime.now(timezone.utc)
    _log_callback(iccid, "success", data, result, action_type="first_attachment_callback")

    if iccid:
        user_id = _find_user_by_iccid(iccid)
        if user_id:
            _send_push(
                user_id=user_id,
                template_key="esim_activated",
                data={"type": "esim_activated", "iccid": iccid},
            )

    return UnifiedResponse.success(data={
        "status": "received",
        "iccid": iccid,
        "alert_type": result.get("alert_type"),
    })


def _process_location_update_callback(provider, data: dict) -> UnifiedResponse:
    result = provider.handle_location_update_callback(data)
    iccid = result.get("iccid", "")
    country_name = result.get("country_name", "")
    _log_callback(iccid, "success", data, result, action_type="location_update_callback")

    if iccid:
        user_id = _find_user_by_iccid(iccid)
        if user_id:
            _send_push(
                user_id=user_id,
                template_key="welcome_country",
                data={"type": "country_change", "iccid": iccid, "country_name": country_name},
            )

    return UnifiedResponse.success(data={
        "status": "received",
        "iccid": iccid,
        "country_code": result.get("country_code"),
        "country_name": country_name,
    })


def _process_first_use_callback(provider, data: dict) -> UnifiedResponse:
    result = provider.handle_first_use_callback(data)
    iccid = result.get("iccid", "")
    usage_mb = result.get("data_usage_mb", 0)
    with get_session() as session:
        record = session.query(EsimInventory).filter(
            EsimInventory.iccid == iccid,
        ).first()
        if record:
            current = record.data_usage_mb or 0
            if usage_mb > current:
                record.data_usage_mb = usage_mb
    _log_callback(iccid, "success", data, result, action_type="first_use_callback")

    if iccid:
        user_id = _find_user_by_iccid(iccid)
        if user_id:
            _send_push(
                user_id=user_id,
                template_key="bundle_started",
                data={"type": "bundle_started", "iccid": iccid, "usage_mb": usage_mb},
            )

    return UnifiedResponse.success(data={
        "status": "received",
        "iccid": iccid,
        "data_usage_mb": usage_mb,
        "bundle_name": result.get("bundle_name"),
    })


def _process_balance_notification(provider, data: dict) -> UnifiedResponse:
    result = provider.handle_balance_notification_callback(data)
    _log_callback("", "success", data, result, action_type="balance_notification_callback")
    return UnifiedResponse.success(data={
        "status": "received",
        "alert_type": result.get("alert_type"),
        "balance": result.get("balance"),
        "threshold": result.get("threshold"),
        "threshold_percent_remaining": result.get("threshold_percent_remaining"),
    })


def _process_msisdn_enabled(provider, data: dict) -> UnifiedResponse:
    result = provider.handle_msisdn_enabled_callback(data)
    iccid = result.get("iccid", "")
    _log_callback(iccid, "success", data, result, action_type="msisdn_enabled_callback")
    return UnifiedResponse.success(data={
        "status": "received",
        "iccid": iccid,
        "msisdn": result.get("msisdn"),
        "reason": result.get("reason"),
    })


def _process_msisdn_disabled(provider, data: dict) -> UnifiedResponse:
    result = provider.handle_msisdn_disabled_callback(data)
    iccid = result.get("iccid", "")
    _log_callback(iccid, "success", data, result, action_type="msisdn_disabled_callback")
    return UnifiedResponse.success(data={
        "status": "received",
        "iccid": iccid,
        "msisdn": result.get("msisdn"),
        "reason": result.get("reason"),
    })
