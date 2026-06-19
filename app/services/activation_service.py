from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from app.core.constants import MAX_RETRIES
from app.core.database import get_session
from app.core.errors import AppError, ErrorCode
from app.models.inventory import EsimInventory
from app.models.order import Order, OrderItem
from app.providers.registry import ProviderRegistry
from config import settings

logger = logging.getLogger("esim-ego")


class ActivationService:

    @staticmethod
    def _get_provider():
        provider_name = settings.ESIM_PROVIDER
        if not provider_name:
            raise AppError(ErrorCode.PROVIDER_AUTH_FAILED)
        provider = ProviderRegistry.get_esim(provider_name)
        if not provider:
            raise AppError(ErrorCode.ACTIVATION_FAILED)
        return provider

    @staticmethod
    def activate(iccid: str, bundle_id: str, inventory_id: UUID) -> dict:
        try:
            provider = ActivationService._get_provider()
            raw = provider.apply_bundle(iccid, bundle_id)
        except AppError:
            raise
        except Exception as exc:
            logger.error("Activation request failed for %s: %s", iccid, exc)
            raise AppError(ErrorCode.ACTIVATION_FAILED)

        status = ActivationService._normalize_status(raw)
        if status == "activated":
            with get_session() as session:
                record = session.query(EsimInventory).filter(
                    EsimInventory.id == inventory_id,
                ).first()
                if record:
                    record.status = "activated"
                    record.activated_at = datetime.now(timezone.utc)
                    record.activation_retries = 0
                    record.last_error = None
                    ActivationService._save_install_details(session, record, raw, provider)
            ActivationService._send_activation_push(iccid)
            return {"success": True, "status": "activated", "raw": raw}

        return {"success": False, "status": status, "raw": raw}

    @staticmethod
    def retry_activation(inventory_id: UUID) -> dict:
        with get_session() as session:
            record = session.query(EsimInventory).filter(
                EsimInventory.id == inventory_id,
                EsimInventory.status.in_(["sold", "processing"]),
            ).with_for_update().first()
            if not record:
                raise AppError(ErrorCode.INVENTORY_NOT_FOUND)

            if record.activation_retries >= MAX_RETRIES:
                raise AppError(ErrorCode.ACTIVATION_MAX_RETRIES)

            iccid = record.iccid
            order_item_id = record.order_item_id

            bundle_id = ActivationService._get_bundle_id_in_session(order_item_id, session)
            if not bundle_id:
                record.last_error = "No bundle id found for order_item"
                record.activation_retries += 1
                if record.activation_retries >= MAX_RETRIES:
                    record.status = "suspended"
                    record.suspended_at = datetime.now(timezone.utc)
                session.flush()
                return {"success": False, "error": "No bundle id found"}

            try:
                provider = ActivationService._get_provider()
                raw = provider.apply_bundle(iccid, bundle_id)
            except AppError as exc:
                record.activation_retries += 1
                record.last_error = str(exc.code)
                if record.activation_retries >= MAX_RETRIES:
                    record.status = "suspended"
                    record.suspended_at = datetime.now(timezone.utc)
                session.flush()
                return {"success": False, "error": str(exc.code)}
            except Exception as exc:
                logger.error("Activation request failed for %s: %s", iccid, exc)
                record.activation_retries += 1
                record.last_error = str(exc)
                if record.activation_retries >= MAX_RETRIES:
                    record.status = "suspended"
                    record.suspended_at = datetime.now(timezone.utc)
                session.flush()
                return {"success": False, "error": "activation_failed"}

            status = ActivationService._normalize_status(raw)
            if status == "activated":
                record.status = "activated"
                record.activated_at = datetime.now(timezone.utc)
                record.activation_retries = 0
                record.last_error = None
                ActivationService._save_install_details(session, record, raw, provider)
                session.flush()
                ActivationService._send_activation_push(iccid)
                return {"success": True, "status": "activated", "raw": raw}

            record.activation_retries += 1
            record.last_error = f"Provider returned status: {status}"
            if record.activation_retries >= MAX_RETRIES:
                record.status = "suspended"
                record.suspended_at = datetime.now(timezone.utc)
            session.flush()
            return {"success": False, "status": status}

    @staticmethod
    def check_expiry() -> list[dict]:
        with get_session() as session:
            expired = session.query(EsimInventory).filter(
                EsimInventory.status.in_(["activated", "active"]),
                EsimInventory.expires_at <= datetime.now(timezone.utc),
            ).all()
            results = []
            for item in expired:
                item.status = "expired"
                results.append({
                    "id": str(item.id),
                    "iccid": item.iccid,
                    "expired_at": item.expires_at.isoformat(),
                })
            session.flush()
            return results

    @staticmethod
    def sync_usage(inventory_id: UUID) -> dict:
        with get_session() as session:
            record = session.query(EsimInventory).filter(
                EsimInventory.id == inventory_id,
            ).first()
            if not record:
                raise AppError(ErrorCode.INVENTORY_NOT_FOUND)
            usage = record.data_usage_mb or 0

        return {"success": True, "data_usage_mb": usage}

    @staticmethod
    def _get_bundle_id_in_session(order_item_id: Optional[UUID], session) -> Optional[str]:
        if not order_item_id:
            return None
        oi = session.query(OrderItem).filter(
            OrderItem.id == order_item_id,
        ).first()
        if oi and oi.order and oi.order.plan:
            return oi.order.plan.provider_bundle_id
        return None

    @staticmethod
    def _save_install_details(session, record: EsimInventory, raw: dict, provider) -> None:
        apply_reference = raw.get("applyReference")
        if not apply_reference:
            return
        try:
            install_details = provider.get_install_details(apply_reference)
        except Exception:
            return
        if not install_details:
            return
        order_item_id = record.order_item_id
        if not order_item_id:
            return
        order_item = session.query(OrderItem).filter(
            OrderItem.id == order_item_id,
        ).first()
        if not order_item:
            return
        matching_id = install_details.get("matchingId")
        smdp_address = install_details.get("smdpAddress")
        if matching_id and smdp_address:
            order_item.activation_code = f"LPA:1${smdp_address}${matching_id}"
        else:
            activation_code = (
                install_details.get("activation_code")
                or install_details.get("code")
            )
            if activation_code:
                order_item.activation_code = str(activation_code)
        expiry = install_details.get("endTime") or install_details.get("expires_at") or install_details.get("expiry_date")
        if expiry:
            try:
                parsed = datetime.fromisoformat(
                    expiry.replace("Z", "+00:00")
                )
                order_item.expires_at = parsed
                record.expires_at = parsed
            except (ValueError, AttributeError):
                pass

    @staticmethod
    def _normalize_status(raw: dict) -> str:
        if raw.get("success") is False:
            return "failed"
        esims = raw.get("esims")
        if isinstance(esims, list) and esims and isinstance(esims[0], dict):
            esim_status = (esims[0].get("status") or "").lower()
            if esim_status in ("active", "activated"):
                return "activated"
            if esim_status in ("pending", "processing"):
                return "processing"
            if esim_status in ("failed", "error", "rejected"):
                return "failed"
        raw_status = (raw.get("status") or raw.get("result") or raw.get("state") or "").lower()
        if raw_status in ("activated", "active", "success", "completed"):
            return "activated"
        if raw_status in ("pending", "processing", "in_progress"):
            return "processing"
        if raw_status in ("failed", "error", "rejected"):
            return "failed"
        return raw_status

    @staticmethod
    def _send_activation_push(iccid: str) -> None:
        try:
            user_id = ActivationService._find_user_by_iccid(iccid)
            if not user_id:
                return
            from app.services.notification_template_service import NotificationTemplateService
            rendered = NotificationTemplateService.render_for_user(
                "esim_activated", user_id, iccid=iccid,
            )
            if not rendered:
                return
            title, body = rendered
            from app.tasks.push_tasks import send_push_notification
            send_push_notification.delay(
                user_id=user_id,
                title=title,
                body=body,
                data={
                    "type": "esim_activated",
                    "iccid": iccid,
                },
            )
        except Exception:
            logger.debug("Push notification skipped for ICCID %s", iccid)

    @staticmethod
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

    @staticmethod
    def _get_bundle_id(order_item_id: Optional[UUID]) -> Optional[str]:
        if not order_item_id:
            return None
        with get_session() as session:
            from sqlalchemy.orm import joinedload
            oi = session.query(OrderItem).options(
                joinedload(OrderItem.order).joinedload(Order.plan),
            ).filter(
                OrderItem.id == order_item_id,
            ).first()
            if oi and oi.order and oi.order.plan:
                return oi.order.plan.provider_bundle_id
        return None
