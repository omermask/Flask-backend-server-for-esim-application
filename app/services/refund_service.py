from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.orm import joinedload

from app.core.database import get_session
from app.core.errors import AppError, ErrorCode
from app.models.finance import Refund
from app.models.order import Order
from app.models.user import User
from app.models.wallet import Wallet, WalletTransaction
from app.services.audit_service import AuditService

logger = logging.getLogger("esim-ego")


class RefundService:

    @staticmethod
    def create_refund(
        order_id: str,
        admin_id: str,
        amount: int | None = None,
        reason: str = "",
    ) -> dict:
        try:
            oid = UUID(order_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        with get_session() as session:
            order = (
                session.query(Order)
                .filter(Order.id == oid)
                .options(joinedload(Order.plan))
                .with_for_update()
                .first()
            )
            if not order:
                raise AppError(ErrorCode.ORDER_NOT_FOUND)
            if order.status != "paid":
                raise AppError(ErrorCode.REFUND_ORDER_NOT_PAID)
            refund_amount = amount if amount is not None else order.total_price_iqd
            already_refunded = order.refunded_amount or 0
            max_refundable = order.total_price_iqd - already_refunded
            if refund_amount <= 0 or refund_amount > max_refundable:
                raise AppError(ErrorCode.REFUND_EXCEEDS_ORDER)
            refund = Refund(
                order_id=oid,
                user_id=order.user_id,
                amount=refund_amount,
                reason=reason or "Refund requested",
                status="approved",
                admin_id=UUID(admin_id),
            )
            session.add(refund)
            wallet = (
                session.query(Wallet)
                .filter(Wallet.user_id == order.user_id)
                .with_for_update()
                .first()
            )
            if not wallet:
                raise AppError(ErrorCode.WALLET_NOT_FOUND)
            balance_before = wallet.balance
            wallet.balance += refund_amount
            balance_after = wallet.balance
            order.refunded_amount = already_refunded + refund_amount
            if order.refunded_amount >= order.total_price_iqd:
                order.status = "refunded"
            txn = WalletTransaction(
                wallet_id=wallet.id,
                amount=refund_amount,
                type="refund",
                balance_before=balance_before,
                balance_after=balance_after,
                description=f"Refund for order {str(order.id)[:8]}",
            )
            session.add(txn)
            session.flush()
            result = {
                "refund_id": str(refund.id),
                "order_id": str(order.id),
                "amount": refund_amount,
                "status": refund.status,
                "balance_before": balance_before,
                "balance_after": balance_after,
            }
        AuditService.log(
            user_id=str(order.user_id),
            action="refund.created",
            resource_type="refund",
            resource_id=str(refund.id),
            details={"order_id": str(order.id), "amount": refund_amount},
        )
        return result

    @staticmethod
    def list_refunds(page: int = 1, limit: int = 20) -> dict:
        with get_session() as session:
            query = session.query(Refund)
            total = query.count()
            offset = (page - 1) * limit
            items = (
                query
                .order_by(Refund.created_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return {
                "items": [
                    {
                        "id": str(r.id),
                        "order_id": str(r.order_id),
                        "user_id": str(r.user_id),
                        "amount": r.amount,
                        "reason": r.reason,
                        "status": r.status,
                        "admin_note": r.admin_note,
                        "created_at": r.created_at.isoformat(),
                    }
                    for r in items
                ],
                "total": total,
                "page": page,
                "limit": limit,
            }
