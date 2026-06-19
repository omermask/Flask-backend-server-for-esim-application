from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload

from app.core.database import get_session
from app.core.errors import AppError, ErrorCode
from app.models.audit import AuditLog
from app.models.inventory import EsimInventory
from app.models.order import Order
from app.models.payment import Payment
from app.models.plan import Plan
from app.models.setting import SystemSetting
from app.models.user import User
from app.models.wallet import Wallet, WalletTransaction
from app.services.refund_service import RefundService

logger = logging.getLogger("esim-ego")

_USER_SORT_WHITELIST = {"created_at", "name", "phone", "role", "is_active", "last_login_at"}
_ORDER_SORT_WHITELIST = {"created_at", "total_price_iqd", "status", "quantity"}


class AdminService:

    @staticmethod
    def search_users(
        q: str = "",
        role: str | None = None,
        is_active: bool | None = None,
        page: int = 1,
        limit: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> dict:
        with get_session() as session:
            query = session.query(User)
            if q:
                search = f"%{q}%"
                query = query.filter(
                    or_(User.phone.ilike(search), User.name.ilike(search)),
                )
            if role:
                query = query.filter(User.role == role)
            if is_active is not None:
                query = query.filter(User.is_active == is_active)
            safe_sort = sort_by if sort_by in _USER_SORT_WHITELIST else "created_at"
            sort_col = getattr(User, safe_sort, User.created_at)
            order_fn = sort_col.desc if sort_order == "desc" else sort_col.asc
            query = query.order_by(order_fn())
            total = query.count()
            offset = (page - 1) * limit
            users = query.offset(offset).limit(limit).all()
            return {
                "items": [
                    {
                        "id": str(u.id),
                        "phone": u.phone,
                        "name": u.name,
                        "role": u.role,
                        "is_active": u.is_active,
                        "is_verified": u.is_verified,
                        "language": u.language,
                        "timezone": u.timezone,
                        "failed_otp_attempts": u.failed_otp_attempts,
                        "created_at": u.created_at.isoformat(),
                        "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
                    }
                    for u in users
                ],
                "total": total,
                "page": page,
                "limit": limit,
            }

    @staticmethod
    def update_user(user_id: str, admin_id: str = "", **kwargs) -> dict:
        try:
            uid = UUID(user_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        allowed = {"name", "language", "timezone", "is_active", "role"}
        updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        if "role" in updates and updates["role"] not in {"user", "admin", "superadmin"}:
            raise AppError(ErrorCode.VALIDATION_INVALID_PARAMETER)
        with get_session() as session:
            user = session.query(User).filter(User.id == uid).first()
            if not user:
                raise AppError(ErrorCode.USER_NOT_FOUND)
            if admin_id and str(uid) == admin_id and "role" in updates:
                raise AppError(ErrorCode.ADMIN_CANNOT_MODIFY_SELF)
            for key, value in updates.items():
                setattr(user, key, value)
            session.flush()
            return {
                "id": str(user.id),
                "phone": user.phone,
                "name": user.name,
                "role": user.role,
                "is_active": user.is_active,
                "is_verified": user.is_verified,
                "language": user.language,
                "timezone": user.timezone,
                "created_at": user.created_at.isoformat(),
            }

    @staticmethod
    def get_user_wallet(user_id: str) -> dict:
        try:
            uid = UUID(user_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        with get_session() as session:
            wallet = (
                session.query(Wallet)
                .filter(Wallet.user_id == uid)
                .first()
            )
            if not wallet:
                raise AppError(ErrorCode.WALLET_NOT_FOUND)
            available = wallet.balance - wallet.frozen_balance
            return {
                "id": str(wallet.id),
                "user_id": str(wallet.user_id),
                "balance": wallet.balance,
                "frozen_balance": wallet.frozen_balance,
                "available_balance": available if available > 0 else 0,
                "created_at": wallet.created_at.isoformat(),
            }

    @staticmethod
    def get_user_wallet_transactions(
        user_id: str, page: int = 1, limit: int = 20,
    ) -> dict:
        try:
            uid = UUID(user_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        with get_session() as session:
            wallet = (
                session.query(Wallet)
                .filter(Wallet.user_id == uid)
                .first()
            )
            if not wallet:
                raise AppError(ErrorCode.WALLET_NOT_FOUND)
            offset = (page - 1) * limit
            total = (
                session.query(WalletTransaction)
                .filter(WalletTransaction.wallet_id == wallet.id)
                .count()
            )
            txns = (
                session.query(WalletTransaction)
                .filter(WalletTransaction.wallet_id == wallet.id)
                .order_by(WalletTransaction.created_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return {
                "items": [
                    {
                        "id": str(t.id),
                        "amount": t.amount,
                        "type": t.type,
                        "reference_type": t.reference_type,
                        "reference_id": str(t.reference_id) if t.reference_id else None,
                        "balance_before": t.balance_before,
                        "balance_after": t.balance_after,
                        "description": t.description,
                        "created_at": t.created_at.isoformat(),
                    }
                    for t in txns
                ],
                "total": total,
                "page": page,
                "limit": limit,
            }

    @staticmethod
    def manual_adjust_wallet(
        user_id: str, admin_id: str, amount: int, reason: str,
    ) -> dict:
        try:
            uid = UUID(user_id)
            aid = UUID(admin_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        if amount <= 0:
            raise AppError(ErrorCode.VALIDATION_INVALID_AMOUNT)
        with get_session() as session:
            wallet = (
                session.query(Wallet)
                .filter(Wallet.user_id == uid)
                .with_for_update()
                .first()
            )
            if not wallet:
                raise AppError(ErrorCode.WALLET_NOT_FOUND)
            balance_before = wallet.balance
            wallet.balance += amount
            if wallet.balance < 0:
                wallet.balance = balance_before
                raise AppError(ErrorCode.WALLET_INSUFFICIENT_BALANCE)
            balance_after = wallet.balance
            txn_type = "admin_adjustment"
            txn = WalletTransaction(
                wallet_id=wallet.id,
                amount=amount,
                type=txn_type,
                balance_before=balance_before,
                balance_after=balance_after,
                description=f"Admin adjustment: {reason} (admin: {aid})",
            )
            session.add(txn)
            session.flush()
            return {
                "transaction_id": str(txn.id),
                "amount": amount,
                "type": txn_type,
                "balance_before": balance_before,
                "balance_after": balance_after,
                "description": txn.description,
            }

    @staticmethod
    def list_orders(
        page: int = 1,
        limit: int = 20,
        status: str | None = None,
        user_id: str | None = None,
        plan_id: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> dict:
        with get_session() as session:
            query = session.query(Order).options(
                joinedload(Order.plan), joinedload(Order.user), joinedload(Order.items),
            )
            if status:
                query = query.filter(Order.status == status)
            if user_id:
                try:
                    uid = UUID(user_id)
                    query = query.filter(Order.user_id == uid)
                except (ValueError, AttributeError):
                    raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
            if plan_id:
                try:
                    pid = UUID(plan_id)
                    query = query.filter(Order.plan_id == pid)
                except (ValueError, AttributeError):
                    raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
            safe_sort = sort_by if sort_by in _ORDER_SORT_WHITELIST else "created_at"
            sort_col = getattr(Order, safe_sort, Order.created_at)
            order_fn = sort_col.desc if sort_order == "desc" else sort_col.asc
            query = query.order_by(order_fn())
            total = query.count()
            offset = (page - 1) * limit
            orders = query.offset(offset).limit(limit).all()
            return {
                "items": [
                    {
                        "id": str(o.id),
                        "user_id": str(o.user_id),
                        "user_name": o.user.name if o.user else "",
                        "user_phone": o.user.phone if o.user else "",
                        "plan_id": str(o.plan_id),
                        "plan_name": o.plan.name if o.plan else "",
                        "quantity": o.quantity,
                        "total_price_iqd": o.total_price_iqd,
                        "currency": o.currency,
                        "status": o.status,
                        "tax_amount": o.tax_amount,
                        "discount_amount": o.discount_amount,
                        "coupon_code": o.coupon_code,
                        "cost_price_iqd": o.cost_price_iqd,
                        "refunded_amount": o.refunded_amount,
                        "items": [
                            {
                                "id": str(item.id),
                                "esim_iccid": item.esim_iccid,
                                "status": item.status,
                                "activated_at": item.activated_at.isoformat() if item.activated_at else None,
                                "expires_at": item.expires_at.isoformat() if item.expires_at else None,
                            }
                            for item in o.items
                        ],
                        "created_at": o.created_at.isoformat(),
                    }
                    for o in orders
                ],
                "total": total,
                "page": page,
                "limit": limit,
            }

    @staticmethod
    def get_order_by_id(order_id: str) -> dict:
        try:
            oid = UUID(order_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        with get_session() as session:
            order = (
                session.query(Order)
                .filter(Order.id == oid)
                .options(joinedload(Order.plan), joinedload(Order.user), joinedload(Order.items))
                .first()
            )
            if not order:
                raise AppError(ErrorCode.ORDER_NOT_FOUND)
            return {
                "id": str(order.id),
                "user_id": str(order.user_id),
                "user_name": order.user.name if order.user else "",
                "user_phone": order.user.phone if order.user else "",
                "plan_id": str(order.plan_id),
                "plan_name": order.plan.name if order.plan else "",
                "quantity": order.quantity,
                "total_price_iqd": order.total_price_iqd,
                "currency": order.currency,
                "status": order.status,
                "cost_price_iqd": order.cost_price_iqd,
                "tax_amount": order.tax_amount,
                "tax_rate": order.tax_rate,
                "discount_amount": order.discount_amount,
                "coupon_code": order.coupon_code,
                "refunded_amount": order.refunded_amount,
                "items": [
                    {
                        "id": str(item.id),
                        "esim_iccid": item.esim_iccid,
                        "status": item.status,
                        "activation_code": item.activation_code,
                        "has_qr_code": bool(item.qr_code),
                        "activated_at": item.activated_at.isoformat() if item.activated_at else None,
                        "expires_at": item.expires_at.isoformat() if item.expires_at else None,
                    }
                    for item in order.items
                ],
                "created_at": order.created_at.isoformat(),
            }

    @staticmethod
    def cancel_order(order_id: str, admin_id: str, reason: str = "") -> dict:
        try:
            oid = UUID(order_id)
            aid = UUID(admin_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        with get_session() as session:
            order = (
                session.query(Order)
                .filter(Order.id == oid)
                .options(joinedload(Order.items))
                .with_for_update()
                .first()
            )
            if not order:
                raise AppError(ErrorCode.ORDER_NOT_FOUND)
            if order.status not in ("paid", "pending", "pending_approval"):
                raise AppError(ErrorCode.ORDER_INVALID_STATUS)
            was_paid = order.status == "paid"
            total_price = order.total_price_iqd
            order_id_str = str(order.id)
        refund = None
        if was_paid:
            try:
                refund = RefundService.create_refund(
                    order_id=order_id,
                    admin_id=admin_id,
                    amount=total_price,
                    reason=reason or "Order cancelled by admin",
                )
            except AppError:
                logger.warning("Refund failed for cancelled order %s", order_id)
                raise
        with get_session() as session:
            order = (
                session.query(Order)
                .filter(Order.id == oid)
                .options(joinedload(Order.items))
                .first()
            )
            if not order:
                raise AppError(ErrorCode.ORDER_NOT_FOUND)
            if order.items:
                for item in order.items:
                    item.status = "cancelled"
            order.status = "cancelled"
            session.flush()
        return {
            "order_id": order_id_str,
            "status": "cancelled",
            "refund": refund,
        }

    @staticmethod
    def reprocess_order(order_id: str) -> dict:
        try:
            oid = UUID(order_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        from app.services.activation_service import ActivationService
        with get_session() as session:
            order = (
                session.query(Order)
                .filter(Order.id == oid)
                .options(joinedload(Order.items), joinedload(Order.plan))
                .first()
            )
            if not order:
                raise AppError(ErrorCode.ORDER_NOT_FOUND)
            if order.status not in ("paid", "pending"):
                raise AppError(ErrorCode.ORDER_INVALID_STATUS)
            items = [
                {"id": item.id, "esim_iccid": item.esim_iccid, "status": item.status}
                for item in order.items
            ]
            plan_name = order.plan.name if order.plan else ""
            order_id_str = str(order.id)
        results = []
        for item in items:
            if item["status"] in ("pending", "failed"):
                try:
                    iccid = item["esim_iccid"]
                    if not iccid:
                        continue
                    inventory_id = None
                    inv_res = AdminService._get_inventory_by_iccid(iccid)
                    if inv_res:
                        inventory_id = UUID(inv_res["id"])
                    result = ActivationService.activate(iccid, plan_name, inventory_id)
                    results.append({
                        "item_id": str(item["id"]),
                        "iccid": iccid,
                        "status": result.get("status", "unknown"),
                    })
                except AppError as exc:
                    results.append({
                        "item_id": str(item["id"]),
                        "iccid": item["esim_iccid"],
                        "status": "failed",
                        "error": str(exc),
                    })
        return {
            "order_id": order_id_str,
            "reprocessed": len(results),
            "results": results,
        }

    @staticmethod
    def _get_inventory_by_iccid(iccid: str) -> dict | None:
        with get_session() as session:
            record = session.query(EsimInventory).filter(
                EsimInventory.iccid == iccid,
            ).first()
            if not record:
                return None
            return {
                "id": str(record.id),
                "iccid": record.iccid,
                "status": record.status,
            }

    @staticmethod
    def list_payments(
        page: int = 1,
        limit: int = 20,
        status: str | None = None,
        method: str | None = None,
        user_id: str | None = None,
    ) -> dict:
        with get_session() as session:
            query = session.query(Payment).options(joinedload(Payment.user))
            if status:
                query = query.filter(Payment.status == status)
            if method:
                query = query.filter(Payment.method == method)
            if user_id:
                try:
                    uid = UUID(user_id)
                    query = query.filter(Payment.user_id == uid)
                except (ValueError, AttributeError):
                    raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
            query = query.order_by(Payment.created_at.desc())
            total = query.count()
            offset = (page - 1) * limit
            payments = query.offset(offset).limit(limit).all()
            return {
                "items": [
                    {
                        "id": str(p.id),
                        "user_id": str(p.user_id),
                        "user_name": p.user.name if p.user else "",
                        "user_phone": p.user.phone if p.user else "",
                        "order_id": str(p.order_id) if p.order_id else None,
                        "amount": p.amount,
                        "method": p.method,
                        "status": p.status,
                        "provider_transaction_id": p.provider_transaction_id,
                        "created_at": p.created_at.isoformat(),
                    }
                    for p in payments
                ],
                "total": total,
                "page": page,
                "limit": limit,
            }

    @staticmethod
    def manual_confirm_payment(payment_id: str, admin_id: str) -> dict:
        try:
            pid = UUID(payment_id)
            aid = UUID(admin_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        return PaymentService.confirm_deposit(
            payment_id=payment_id,
            provider_txn_id="manual",
        )

    @staticmethod
    def manual_refund_payment(payment_id: str, admin_id: str, reason: str = "") -> dict:
        try:
            pid = UUID(payment_id)
            aid = UUID(admin_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        with get_session() as session:
            payment = (
                session.query(Payment)
                .filter(Payment.id == pid)
                .with_for_update()
                .first()
            )
            if not payment:
                raise AppError(ErrorCode.NOT_FOUND)
            if payment.status != "completed":
                raise AppError(ErrorCode.PAYMENT_REFUND_FAILED)
            payment.status = "refunded"
            if payment.order_id:
                refund = RefundService.create_refund(
                    order_id=str(payment.order_id),
                    admin_id=admin_id,
                    amount=payment.amount,
                    reason=reason or "Manual payment refund by admin",
                )
            else:
                wallet = (
                    session.query(Wallet)
                    .filter(Wallet.user_id == payment.user_id)
                    .with_for_update()
                    .first()
                )
                if not wallet:
                    raise AppError(ErrorCode.WALLET_NOT_FOUND)
                balance_before = wallet.balance
                wallet.balance -= payment.amount
                if wallet.balance < 0:
                    wallet.balance = balance_before
                    raise AppError(ErrorCode.WALLET_INSUFFICIENT_BALANCE)
                txn = WalletTransaction(
                    wallet_id=wallet.id,
                    amount=-payment.amount,
                    type="refund",
                    balance_before=balance_before,
                    balance_after=wallet.balance,
                    description=f"Deposit refund: {reason or 'Manual refund'} (admin: {aid})",
                )
                session.add(txn)
                refund = {
                    "amount": payment.amount,
                    "transaction_id": str(txn.id) if txn.id else None,
                }
            session.flush()
            return {
                "payment_id": str(payment.id),
                "status": "refunded",
                "refund": refund,
            }

    @staticmethod
    def get_settings() -> list[dict]:
        with get_session() as session:
            settings = session.query(SystemSetting).order_by(SystemSetting.key).all()
            return [
                {
                    "id": str(s.id),
                    "key": s.key,
                    "value": s.value,
                    "description": s.description,
                    "updated_by": str(s.updated_by) if s.updated_by else None,
                    "updated_at": s.updated_at.isoformat(),
                }
                for s in settings
            ]

    @staticmethod
    def get_setting(key: str) -> dict:
        with get_session() as session:
            setting = session.query(SystemSetting).filter(SystemSetting.key == key).first()
            if not setting:
                raise AppError(ErrorCode.SETTING_NOT_FOUND)
            return {
                "id": str(setting.id),
                "key": setting.key,
                "value": setting.value,
                "description": setting.description,
                "updated_by": str(setting.updated_by) if setting.updated_by else None,
                "updated_at": setting.updated_at.isoformat(),
            }

    @staticmethod
    def set_setting(key: str, value: str, description: str = "", admin_id: str = "") -> dict:
        try:
            aid = UUID(admin_id) if admin_id else None
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        if not key or not key.strip():
            raise AppError(ErrorCode.VALIDATION_MISSING_FIELD)
        with get_session() as session:
            existing = session.query(SystemSetting).filter(SystemSetting.key == key).first()
            if existing:
                existing.value = value
                existing.description = description or existing.description
                if aid:
                    existing.updated_by = aid
                session.flush()
                setting_id = existing.id
                setting_key = existing.key
                setting_value = existing.value
                setting_description = existing.description
                setting_updated_by = existing.updated_by
                setting_updated_at = existing.updated_at
            else:
                setting = SystemSetting(
                    key=key,
                    value=value,
                    description=description or None,
                    updated_by=aid,
                )
                session.add(setting)
                session.flush()
                setting_id = setting.id
                setting_key = setting.key
                setting_value = setting.value
                setting_description = setting.description
                setting_updated_by = setting.updated_by
                setting_updated_at = setting.updated_at
            return {
                "id": str(setting_id),
                "key": setting_key,
                "value": setting_value,
                "description": setting_description,
                "updated_by": str(setting_updated_by) if setting_updated_by else None,
                "updated_at": setting_updated_at.isoformat(),
            }

    @staticmethod
    def delete_setting(key: str) -> None:
        with get_session() as session:
            setting = session.query(SystemSetting).filter(SystemSetting.key == key).first()
            if not setting:
                raise AppError(ErrorCode.SETTING_NOT_FOUND)
            session.delete(setting)
            session.flush()

    @staticmethod
    def list_audit_logs(
        page: int = 1,
        limit: int = 20,
        user_id: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
    ) -> dict:
        with get_session() as session:
            query = session.query(AuditLog).options(joinedload(AuditLog.user))
            if user_id:
                try:
                    uid = UUID(user_id)
                    query = query.filter(AuditLog.user_id == uid)
                except (ValueError, AttributeError):
                    raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
            if action:
                query = query.filter(AuditLog.action == action)
            if resource_type:
                query = query.filter(AuditLog.resource_type == resource_type)
            query = query.order_by(AuditLog.created_at.desc())
            total = query.count()
            offset = (page - 1) * limit
            items = query.offset(offset).limit(limit).all()
            return {
                "items": [
                    {
                        "id": str(item.id),
                        "user_id": str(item.user_id) if item.user_id else None,
                        "user_name": item.user.name if item.user else "",
                        "action": item.action,
                        "resource_type": item.resource_type,
                        "resource_id": item.resource_id,
                        "details": item.details,
                        "ip_address": item.ip_address,
                        "created_at": item.created_at.isoformat(),
                    }
                    for item in items
                ],
                "total": total,
                "page": page,
                "limit": limit,
            }

    @staticmethod
    def get_plan_stock(plan_id: str | None = None) -> list[dict]:
        with get_session() as session:
            plan_query = session.query(Plan)
            if plan_id:
                try:
                    pid = UUID(plan_id)
                    plan_query = plan_query.filter(Plan.id == pid)
                except (ValueError, AttributeError):
                    raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
            plans = {p.id: p for p in plan_query.all()}
            if not plans:
                return []
            plan_ids = list(plans.keys())
            counts = (
                session.query(
                    EsimInventory.plan_id,
                    EsimInventory.status,
                    func.count(EsimInventory.id),
                )
                .filter(EsimInventory.plan_id.in_(plan_ids))
                .group_by(EsimInventory.plan_id, EsimInventory.status)
                .all()
            )
            stock_map: dict[uuid.UUID, dict[str, int]] = {}
            for pid, status, cnt in counts:
                if pid not in stock_map:
                    stock_map[pid] = {"total": 0, "available": 0, "sold": 0}
                stock_map[pid]["total"] += cnt
                if status == "available":
                    stock_map[pid]["available"] = cnt
                elif status == "sold":
                    stock_map[pid]["sold"] = cnt
            results = []
            for pid, plan in plans.items():
                s = stock_map.get(pid, {"total": 0, "available": 0, "sold": 0})
                results.append({
                    "plan_id": str(pid),
                    "plan_name": plan.name,
                    "total_stock": s["total"],
                    "available_stock": s["available"],
                    "sold_stock": s["sold"],
                })
            return results
