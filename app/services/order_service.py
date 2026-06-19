from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import joinedload

from app.core.database import get_session
from app.core.errors import AppError, ErrorCode
from app.models.finance import Coupon, CouponUsage
from app.models.inventory import EsimInventory
from app.models.order import Order, OrderItem
from app.models.plan import Plan
from app.models.setting import SystemSetting
from app.models.user import User
from app.models.wallet import Wallet, WalletTransaction
from app.providers.registry import ProviderRegistry
from app.services.activation_service import ActivationService
from app.services.coupon_service import CouponService
from app.services.referral_service import ReferralService
from app.services.settings_service import SettingsService
from app.services.tax_service import TaxService
from config import settings, ALLOWED_PURCHASE_MODES

__all__ = ["OrderService"]

logger = logging.getLogger("esim-ego")


class OrderService:

    @staticmethod
    def _get_order_approval_mode() -> str:
        try:
            with get_session() as s:
                setting = s.query(SystemSetting).filter(SystemSetting.key == "order_approval_mode").first()
                if setting and setting.value in ("auto", "manual"):
                    return setting.value
        except Exception:
            pass
        return "auto"

    @staticmethod
    def _get_effective_purchase_mode() -> str:
        mode = settings.PURCHASE_MODE
        try:
            with get_session() as s:
                setting = s.query(SystemSetting).filter(SystemSetting.key == "purchase_mode").first()
                if setting and setting.value in ALLOWED_PURCHASE_MODES:
                    mode = setting.value
        except Exception:
            pass
        return mode

    @staticmethod
    def create_order(
        user_id: str,
        plan_id: str,
        quantity: int = 1,
        idempotency_key: str = "",
        coupon_code: str = "",
    ) -> dict:
        uid = UUID(user_id)
        pid = UUID(plan_id)
        discount_amount = 0
        with get_session() as session:
            if idempotency_key:
                existing = (
                    session.query(Order)
                    .filter(Order.idempotency_key == idempotency_key)
                    .first()
                )
                if existing:
                    raise AppError(ErrorCode.VALIDATION_IDEMPOTENCY_REUSE)
            plan = session.query(Plan).filter(Plan.id == pid).first()
            if not plan:
                raise AppError(ErrorCode.PLAN_NOT_FOUND)
            if not plan.is_active:
                raise AppError(ErrorCode.PLAN_INACTIVE)
            user = session.query(User).filter(User.id == uid).first()
            if not user:
                raise AppError(ErrorCode.USER_NOT_FOUND)
            if not user.is_active:
                raise AppError(ErrorCode.USER_ACCOUNT_DELETED)
            base_price = plan.price_iqd * quantity
            if plan.markup_percentage > 0:
                cost_price = round(Decimal(str(base_price)) / (Decimal("1") + plan.markup_percentage / Decimal("100")))
            else:
                cost_price = base_price
            coupon_record = None
            if coupon_code:
                coupon_record = session.query(Coupon).filter(Coupon.code == coupon_code.upper()).with_for_update().first()
                if not coupon_record:
                    raise AppError(ErrorCode.COUPON_NOT_FOUND)
                CouponService._validate_coupon_record(coupon_record, uid, pid, base_price, session)
                discount_amount = CouponService._calculate_discount(
                    coupon_record.discount_type,
                    coupon_record.discount_value,
                    base_price,
                    coupon_record.max_discount_amount,
                )
            tax_data = TaxService.calculate_tax(base_price - discount_amount)
            tax_amount = tax_data["total_tax"]
            total_price = base_price - discount_amount + tax_amount
            total_price = max(total_price, 0)

            purchase_mode = OrderService._get_effective_purchase_mode()
            approval_mode = OrderService._get_order_approval_mode()

            inventory_records = []
            if purchase_mode != "on_demand_only":
                inventory_records = (
                    session.query(EsimInventory)
                    .filter(
                        EsimInventory.plan_id == pid,
                        EsimInventory.status == "available",
                    )
                    .with_for_update(skip_locked=True)
                    .limit(quantity)
                    .all()
                )

            order = Order(
                user_id=uid,
                plan_id=pid,
                quantity=quantity,
                total_price_iqd=total_price,
                status="pending_approval" if approval_mode == "manual" else "paid",
                idempotency_key=idempotency_key or None,
                currency=SettingsService.get_official_currency(),
                tax_amount=tax_amount,
                tax_rate=", ".join(t["name"] for t in tax_data["applied"]) if tax_data["applied"] else None,
                discount_amount=discount_amount,
                coupon_code=coupon_code.upper() if coupon_code else None,
                cost_price_iqd=cost_price,
            )
            session.add(order)
            session.flush()

            if coupon_record and discount_amount > 0:
                coupon_record.used_count += 1
                usage = CouponUsage(
                    coupon_id=coupon_record.id,
                    user_id=uid,
                    order_id=order.id,
                    discount_amount=discount_amount,
                )
                session.add(usage)

            # ── MANUAL APPROVAL MODE: stop here, no wallet deduction, no eSIM ──
            if approval_mode == "manual":
                for _ in range(quantity):
                    session.add(OrderItem(order_id=order.id))
                session.flush()
                return {
                    "order_id": str(order.id),
                    "plan_name": plan.name,
                    "quantity": quantity,
                    "base_price_iqd": base_price,
                    "discount_amount": discount_amount,
                    "tax_amount": tax_amount,
                    "total_price_iqd": total_price,
                    "cost_price_iqd": cost_price,
                    "status": "pending_approval",
                    "created_at": order.created_at.isoformat() if order.created_at else None,
                }

            wallet = (
                session.query(Wallet)
                .filter(Wallet.user_id == uid)
                .with_for_update()
                .first()
            )
            if not wallet:
                raise AppError(ErrorCode.WALLET_NOT_FOUND)
            available = wallet.balance - wallet.frozen_balance
            if available < total_price:
                raise AppError(ErrorCode.WALLET_INSUFFICIENT_AVAILABLE)
            balance_before = wallet.balance
            wallet.balance -= total_price
            balance_after = wallet.balance
            txn = WalletTransaction(
                wallet_id=wallet.id,
                amount=-total_price,
                type="payment",
                balance_before=balance_before,
                balance_after=balance_after,
                description=f"Order payment: {plan.name} x{quantity}",
            )
            session.add(txn)
            allocated_iccids = []
            on_demand_items: list[dict] = []
            for i in range(quantity):
                item = OrderItem(order_id=order.id)
                session.add(item)
                session.flush()
                if i < len(inventory_records):
                    record = inventory_records[i]
                    record.status = "sold"
                    record.order_item_id = item.id
                    record.sold_at = datetime.now(timezone.utc)
                    item.esim_iccid = record.iccid
                    allocated_iccids.append({
                        "iccid": record.iccid,
                        "inventory_id": record.id,
                        "item_id": item.id,
                    })
                else:
                    on_demand_items.append({
                        "item_id": item.id,
                        "order_item": item,
                    })
            if on_demand_items and purchase_mode == "inventory_only":
                raise AppError(ErrorCode.INVENTORY_INSUFFICIENT_STOCK)
            session.flush()
            order_id = order.id
            order_status = order.status
            created_at = order.created_at
            plan_name = plan.name
            bundle_id = plan.provider_bundle_id

        activation_results = []

        if on_demand_items:
            provider = ProviderRegistry.get_esim(settings.ESIM_PROVIDER) if settings.ESIM_PROVIDER else ProviderRegistry.get_esim("esimgo")
            for od in on_demand_items:
                try:
                    result = provider.create_order(bundle_id)
                    esims = result.get("esims", [])
                    if not esims:
                        activation_results.append({"iccid": "pending", "status": "failed", "error": "no esims returned"})
                        continue
                    iccid = esims[0].get("iccid", "")
                    if not iccid:
                        activation_results.append({"iccid": "pending", "status": "failed", "error": "no iccid"})
                        continue
                    with get_session() as s:
                        item = s.query(OrderItem).filter(OrderItem.id == od["item_id"]).first()
                        if item:
                            item.esim_iccid = iccid
                        record = EsimInventory(
                            iccid=iccid, plan_id=pid, status="activated",
                            order_item_id=od["item_id"],
                            sold_at=datetime.now(timezone.utc),
                            activated_at=datetime.now(timezone.utc),
                        )
                        s.add(record)
                        s.flush()
                        inventory_id = record.id
                        try:
                            ref = result.get("id") or result.get("transactionId") or ""
                            if ref:
                                details = provider.get_install_details(ref)
                                matching_id = details.get("matchingId")
                                smdp = details.get("smdpAddress")
                                if matching_id and smdp:
                                    item.activation_code = f"LPA:1${smdp}${matching_id}"
                                expiry = details.get("endTime") or details.get("expires_at")
                                if expiry:
                                    parsed = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
                                    item.expires_at = parsed
                                    record.expires_at = parsed
                        except Exception:
                            logger.debug("Install details fetch skipped for on-demand ICCID %s", iccid)
                    activation_results.append({"iccid": iccid, "status": "activated"})
                    allocated_iccids.append({"iccid": iccid, "inventory_id": inventory_id, "item_id": od["item_id"]})
                except AppError as exc:
                    activation_results.append({"iccid": "pending", "status": "failed", "error": str(exc)})

        for entry in allocated_iccids:
            if any(r["iccid"] == entry["iccid"] and r["status"] == "activated" for r in activation_results):
                continue
            try:
                result = ActivationService.activate(
                    entry["iccid"], bundle_id, entry["inventory_id"],
                )
                activation_results.append({
                    "iccid": entry["iccid"],
                    "status": result.get("status", "unknown"),
                })
            except AppError as exc:
                activation_results.append({
                    "iccid": entry["iccid"],
                    "status": "failed",
                    "error": str(exc),
                })

        try:
            ReferralService.check_and_qualify(
                referred_user_id=str(uid),
                order_id=str(order_id),
                order_total=total_price,
            )
        except Exception:
            logger.exception("Referral qualification check failed for user %s", uid)

        try:
            from app.services.notification_template_service import NotificationTemplateService
            rendered = NotificationTemplateService.render_for_user(
                "order_confirmed", str(uid),
                plan_name=plan_name, quantity=quantity,
            )
            if rendered:
                title, body = rendered
                from app.tasks.push_tasks import send_push_notification
                send_push_notification.delay(
                    user_id=str(uid),
                    title=title,
                    body=body,
                    data={
                        "type": "order_confirmed",
                        "order_id": str(order_id),
                        "plan_name": plan_name,
                    },
                )
        except Exception:
            logger.debug("Push notification skipped for order %s", order_id)

        try:
            from app.socketio import emit_order_update, emit_wallet_update
            emit_order_update(str(uid), str(order_id), order_status)
            emit_wallet_update(str(uid), balance_after)
        except Exception:
            logger.debug("SocketIO emit skipped for order %s", order_id)

        return {
            "order_id": str(order_id),
            "plan_name": plan_name,
            "quantity": quantity,
            "base_price_iqd": base_price,
            "discount_amount": discount_amount,
            "tax_amount": tax_amount,
            "total_price_iqd": total_price,
            "cost_price_iqd": cost_price,
            "status": order_status,
            "balance_before": balance_before,
            "balance_after": balance_after,
            "created_at": created_at.isoformat() if created_at else None,
            "activation": activation_results,
        }

    @staticmethod
    def approve_order(order_id: str) -> dict:
        try:
            oid = UUID(order_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        with get_session() as session:
            order = (
                session.query(Order)
                .filter(Order.id == oid)
                .options(joinedload(Order.plan), joinedload(Order.items))
                .with_for_update()
                .first()
            )
            if not order:
                raise AppError(ErrorCode.ORDER_NOT_FOUND)
            if order.status != "pending_approval":
                raise AppError(ErrorCode.ORDER_INVALID_STATUS)
            uid = order.user_id
            pid = order.plan_id
            quantity = order.quantity
            total_price = order.total_price_iqd
            plan_name = order.plan.name
            bundle_id = order.plan.provider_bundle_id
            base_price = order.total_price_iqd + order.discount_amount - order.tax_amount
            base_price = max(base_price, 0)
            cost_price = order.cost_price_iqd
            discount_amount = order.discount_amount
            tax_amount = order.tax_amount
            user = session.query(User).filter(User.id == uid).first()
            if not user:
                raise AppError(ErrorCode.USER_NOT_FOUND)
            if not user.is_active:
                raise AppError(ErrorCode.USER_ACCOUNT_DELETED)
            wallet = (
                session.query(Wallet)
                .filter(Wallet.user_id == uid)
                .with_for_update()
                .first()
            )
            if not wallet:
                raise AppError(ErrorCode.WALLET_NOT_FOUND)
            available = wallet.balance - wallet.frozen_balance
            if available < total_price:
                raise AppError(ErrorCode.WALLET_INSUFFICIENT_AVAILABLE)
            balance_before = wallet.balance
            wallet.balance -= total_price
            balance_after = wallet.balance
            txn = WalletTransaction(
                wallet_id=wallet.id,
                amount=-total_price,
                type="payment",
                balance_before=balance_before,
                balance_after=balance_after,
                description=f"Order approved: {plan_name} x{quantity}",
            )
            session.add(txn)
            order.status = "paid"
            purchase_mode = OrderService._get_effective_purchase_mode()
            inventory_records = []
            if purchase_mode != "on_demand_only":
                inventory_records = (
                    session.query(EsimInventory)
                    .filter(
                        EsimInventory.plan_id == pid,
                        EsimInventory.status == "available",
                    )
                    .with_for_update(skip_locked=True)
                    .limit(quantity)
                    .all()
                )
            existing_items = session.query(OrderItem).filter(OrderItem.order_id == oid).all()
            items = existing_items or []
            if not existing_items:
                for _ in range(quantity):
                    session.add(OrderItem(order_id=oid))
            session.flush()
            if not existing_items:
                items = session.query(OrderItem).filter(OrderItem.order_id == oid).all()
            allocated_iccids = []
            on_demand_items = []
            for i, item in enumerate(items):
                if i < len(inventory_records):
                    record = inventory_records[i]
                    record.status = "sold"
                    record.order_item_id = item.id
                    record.sold_at = datetime.now(timezone.utc)
                    item.esim_iccid = record.iccid
                    allocated_iccids.append({
                        "iccid": record.iccid,
                        "inventory_id": record.id,
                        "item_id": item.id,
                    })
                else:
                    on_demand_items.append({
                        "item_id": item.id,
                        "order_item": item,
                    })
            if on_demand_items and purchase_mode == "inventory_only":
                raise AppError(ErrorCode.INVENTORY_INSUFFICIENT_STOCK)
            session.flush()
            order_id_str = str(order.id)
            order_status = "paid"
            created_at = order.created_at

        activation_results = []

        if on_demand_items:
            provider = ProviderRegistry.get_esim(settings.ESIM_PROVIDER) if settings.ESIM_PROVIDER else ProviderRegistry.get_esim("esimgo")
            for od in on_demand_items:
                try:
                    result = provider.create_order(bundle_id)
                    esims = result.get("esims", [])
                    if not esims:
                        activation_results.append({"iccid": "pending", "status": "failed", "error": "no esims returned"})
                        continue
                    iccid = esims[0].get("iccid", "")
                    if not iccid:
                        activation_results.append({"iccid": "pending", "status": "failed", "error": "no iccid"})
                        continue
                    with get_session() as s:
                        item = s.query(OrderItem).filter(OrderItem.id == od["item_id"]).first()
                        if item:
                            item.esim_iccid = iccid
                        record = EsimInventory(
                            iccid=iccid, plan_id=pid, status="activated",
                            order_item_id=od["item_id"],
                            sold_at=datetime.now(timezone.utc),
                            activated_at=datetime.now(timezone.utc),
                        )
                        s.add(record)
                        s.flush()
                        inv_id = record.id
                        try:
                            ref = result.get("id") or result.get("transactionId") or ""
                            if ref:
                                details = provider.get_install_details(ref)
                                matching_id = details.get("matchingId")
                                smdp = details.get("smdpAddress")
                                if matching_id and smdp:
                                    item.activation_code = f"LPA:1${smdp}${matching_id}"
                                expiry = details.get("endTime") or details.get("expires_at")
                                if expiry:
                                    parsed = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
                                    item.expires_at = parsed
                                    record.expires_at = parsed
                        except Exception:
                            logger.debug("Install details fetch skipped for on-demand ICCID %s", iccid)
                    activation_results.append({"iccid": iccid, "status": "activated"})
                    allocated_iccids.append({"iccid": iccid, "inventory_id": inv_id, "item_id": od["item_id"]})
                except AppError as exc:
                    activation_results.append({"iccid": "pending", "status": "failed", "error": str(exc)})

        for entry in allocated_iccids:
            if any(r["iccid"] == entry["iccid"] and r["status"] == "activated" for r in activation_results):
                continue
            try:
                result = ActivationService.activate(
                    entry["iccid"], bundle_id, entry["inventory_id"],
                )
                activation_results.append({
                    "iccid": entry["iccid"],
                    "status": result.get("status", "unknown"),
                })
            except AppError as exc:
                activation_results.append({
                    "iccid": entry["iccid"],
                    "status": "failed",
                    "error": str(exc),
                })

        try:
            ReferralService.check_and_qualify(
                referred_user_id=str(uid),
                order_id=str(order_id_str),
                order_total=total_price,
            )
        except Exception:
            logger.exception("Referral qualification check failed for user %s", uid)

        try:
            from app.services.notification_template_service import NotificationTemplateService
            rendered = NotificationTemplateService.render_for_user(
                "order_confirmed", str(uid),
                plan_name=plan_name, quantity=quantity,
            )
            if rendered:
                title, body = rendered
                from app.tasks.push_tasks import send_push_notification
                send_push_notification.delay(
                    user_id=str(uid),
                    title=title,
                    body=body,
                    data={
                        "type": "order_confirmed",
                        "order_id": order_id_str,
                        "plan_name": plan_name,
                    },
                )
        except Exception:
            logger.debug("Push notification skipped for order %s", order_id_str)

        try:
            from app.socketio import emit_order_update, emit_wallet_update
            emit_order_update(str(uid), order_id_str, order_status)
            emit_wallet_update(str(uid), balance_after)
        except Exception:
            logger.debug("SocketIO emit skipped for order %s", order_id_str)

        return {
            "order_id": order_id_str,
            "plan_name": plan_name,
            "quantity": quantity,
            "base_price_iqd": base_price,
            "discount_amount": discount_amount,
            "tax_amount": tax_amount,
            "total_price_iqd": total_price,
            "cost_price_iqd": cost_price,
            "status": order_status,
            "balance_before": balance_before,
            "balance_after": balance_after,
            "created_at": created_at.isoformat() if created_at else None,
            "activation": activation_results,
        }

    @staticmethod
    def get_order(user_id: str, order_id: str) -> dict:
        uid = UUID(user_id)
        try:
            oid = UUID(order_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        with get_session() as session:
            order = (
                session.query(Order)
                .filter(Order.id == oid, Order.user_id == uid)
                .options(joinedload(Order.items), joinedload(Order.plan))
                .first()
            )
            if not order:
                raise AppError(ErrorCode.ORDER_NOT_FOUND)
            return OrderService._format_order(order)

    @staticmethod
    def list_user_orders(
        user_id: str, page: int = 1, limit: int = 20
    ) -> dict:
        uid = UUID(user_id)
        with get_session() as session:
            query = session.query(Order).filter(Order.user_id == uid)
            total = query.count()
            offset = (page - 1) * limit
            orders = (
                query.options(joinedload(Order.plan))
                .order_by(Order.created_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return {
                "items": [OrderService._format_order(o) for o in orders],
                "total": total,
                "page": page,
                "limit": limit,
            }

    @staticmethod
    def _format_order(order: Order) -> dict:
        return {
            "id": str(order.id),
            "plan_name": order.plan.name if order.plan else "",
            "quantity": order.quantity,
            "total_price_iqd": order.total_price_iqd,
            "currency": order.currency,
            "tax_amount": order.tax_amount,
            "tax_rate": order.tax_rate,
            "discount_amount": order.discount_amount,
            "coupon_code": order.coupon_code,
            "cost_price_iqd": order.cost_price_iqd,
            "refunded_amount": order.refunded_amount,
            "status": order.status,
            "items": [
                {
                    "id": str(item.id),
                    "status": item.status,
                    "esim_iccid": item.esim_iccid,
                    "activated_at": item.activated_at.isoformat() if item.activated_at else None,
                    "expires_at": item.expires_at.isoformat() if item.expires_at else None,
                }
                for item in order.items
            ],
            "created_at": order.created_at.isoformat(),
        }