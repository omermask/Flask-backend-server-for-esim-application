from __future__ import annotations

import base64
import logging
from uuid import UUID

from flask import Response, redirect
from sqlalchemy.orm import joinedload

from app.core.database import get_session
from app.core.errors import AppError, ErrorCode
from app.models.inventory import EsimInventory
from app.models.order import Order, OrderItem
from app.services.audit_service import AuditService
from app.services.order_service import OrderService

logger = logging.getLogger("esim-ego")


class EsimService:

    @staticmethod
    def _load_inventory(items: list[OrderItem]) -> dict[UUID, EsimInventory]:
        item_ids = [item.id for item in items if item.id]
        if not item_ids:
            return {}
        with get_session() as s:
            records = s.query(EsimInventory).filter(
                EsimInventory.order_item_id.in_(item_ids),
            ).all()
            return {r.order_item_id: r for r in records if r.order_item_id}

    @staticmethod
    def list_user_esims(
        user_id: str, page: int = 1, limit: int = 20
    ) -> dict:
        uid = UUID(user_id)
        with get_session() as session:
            query = (
                session.query(OrderItem)
                .join(Order)
                .filter(Order.user_id == uid)
            )
            total = query.count()
            offset = (page - 1) * limit
            items = (
                query
                .options(joinedload(OrderItem.order).joinedload(Order.plan))
                .order_by(OrderItem.created_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            inv_map = EsimService._load_inventory(items)
            return {
                "items": [
                    EsimService._format_esim(item, inv_map.get(item.id)) for item in items
                ],
                "total": total,
                "page": page,
                "limit": limit,
            }

    @staticmethod
    def get_esim(user_id: str, item_id: str) -> dict:
        uid = UUID(user_id)
        try:
            iid = UUID(item_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        with get_session() as session:
            item = (
                session.query(OrderItem)
                .join(Order)
                .filter(OrderItem.id == iid, Order.user_id == uid)
                .options(joinedload(OrderItem.order).joinedload(Order.plan))
                .first()
            )
            if not item:
                raise AppError(ErrorCode.ESIM_NOT_FOUND)
            inv_map = EsimService._load_inventory([item])
            return EsimService._format_esim(item, inv_map.get(item.id))

    @staticmethod
    def download_qr(user_id: str, item_id: str) -> Response:
        uid = UUID(user_id)
        try:
            iid = UUID(item_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        with get_session() as session:
            item = (
                session.query(OrderItem)
                .join(Order)
                .filter(OrderItem.id == iid, Order.user_id == uid)
                .first()
            )
            if not item:
                raise AppError(ErrorCode.ESIM_NOT_FOUND)
            if not item.qr_code:
                raise AppError(ErrorCode.ESIM_INVALID_STATUS)
            qr = item.qr_code
            if qr.startswith("https://") or qr.startswith("http://"):
                return redirect(qr)
            try:
                decoded = base64.b64decode(qr)
                return Response(
                    decoded,
                    mimetype="image/png",
                    headers={
                        "Content-Disposition": f'attachment; filename="esim_{item_id}.png"'
                    },
                )
            except Exception:
                return Response(
                    qr,
                    mimetype="text/plain",
                    headers={
                        "Content-Disposition": f'attachment; filename="esim_{item_id}.txt"'
                    },
                )

    @staticmethod
    def renew_esim(user_id: str, item_id: str) -> dict:
        uid = UUID(user_id)
        try:
            iid = UUID(item_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        with get_session() as session:
            item = (
                session.query(OrderItem)
                .join(Order)
                .filter(OrderItem.id == iid, Order.user_id == uid)
                .options(joinedload(OrderItem.order).joinedload(Order.plan))
                .first()
            )
            if not item:
                raise AppError(ErrorCode.ESIM_NOT_FOUND)
            if not item.order or not item.order.plan:
                raise AppError(ErrorCode.ESIM_INVALID_STATUS)
            plan_id = str(item.order.plan.id)
        result = OrderService.create_order(
            user_id=user_id,
            plan_id=plan_id,
            quantity=1,
        )
        AuditService.log(
            user_id=user_id,
            action="esim.renewed",
            resource_type="order_item",
            resource_id=item_id,
            details={"new_order_id": result.get("order_id")},
        )
        return result

    @staticmethod
    def _format_esim(item: OrderItem, inv: EsimInventory | None = None) -> dict:
        plan_name = ""
        data_amount_mb = 0
        duration_days = 0
        if item.order and item.order.plan:
            plan = item.order.plan
            plan_name = plan.name
            data_amount_mb = plan.data_amount_mb
            duration_days = plan.duration_days
        return {
            "id": str(item.id),
            "order_id": str(item.order_id) if item.order_id else None,
            "plan_name": plan_name,
            "plan_data_amount_mb": data_amount_mb,
            "plan_duration_days": duration_days,
            "esim_iccid": item.esim_iccid,
            "status": item.status,
            "inventory_status": inv.status if inv else None,
            "data_usage_mb": inv.data_usage_mb if inv else None,
            "activation_code": item.activation_code,
            "has_qr_code": bool(item.qr_code),
            "activated_at": item.activated_at.isoformat() if item.activated_at else None,
            "expires_at": item.expires_at.isoformat() if item.expires_at else None,
            "created_at": item.created_at.isoformat(),
        }
