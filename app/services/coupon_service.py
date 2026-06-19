from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from app.core.database import get_session
from app.core.errors import AppError, ErrorCode
from app.models.finance import Coupon, CouponUsage

logger = logging.getLogger("esim-ego")

MAX_COUPON_CODE_LENGTH = 50
MAX_COUPON_REASON_LENGTH = 500


class CouponService:

    @staticmethod
    def create_coupon(
        code: str,
        discount_type: str,
        discount_value: Decimal,
        max_uses: int = 0,
        min_order_amount: int = 0,
        max_discount_amount: int | None = None,
        applicable_plan_ids: str | None = None,
        expires_at: datetime | None = None,
    ) -> dict:
        code_upper = code.upper()
        if not code_upper or len(code_upper) > MAX_COUPON_CODE_LENGTH:
            raise AppError(ErrorCode.VALIDATION_EXCEEDS_MAX_LENGTH)
        if discount_type not in ("percentage", "fixed"):
            raise AppError(ErrorCode.VALIDATION_INVALID_ENUM)
        if discount_value <= 0:
            raise AppError(ErrorCode.VALIDATION_INVALID_PARAMETER)
        with get_session() as session:
            existing = session.query(Coupon).filter(Coupon.code == code_upper).first()
            if existing:
                raise AppError(ErrorCode.VALIDATION_IDEMPOTENCY_REUSE)
            record = Coupon(
                code=code_upper,
                discount_type=discount_type,
                discount_value=discount_value,
                max_uses=max_uses,
                min_order_amount=min_order_amount,
                max_discount_amount=max_discount_amount,
                applicable_plan_ids=applicable_plan_ids,
                expires_at=expires_at,
            )
            session.add(record)
            session.flush()
            return CouponService._format(record)

    @staticmethod
    def update_coupon(coupon_id: str, **kwargs) -> dict:
        try:
            cid = UUID(coupon_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        if "discount_value" in kwargs and kwargs["discount_value"] is not None:
            if kwargs["discount_value"] <= 0:
                raise AppError(ErrorCode.VALIDATION_INVALID_PARAMETER)
        with get_session() as session:
            record = session.query(Coupon).filter(Coupon.id == cid).first()
            if not record:
                raise AppError(ErrorCode.COUPON_NOT_FOUND)
            for key, value in kwargs.items():
                if value is not None and hasattr(record, key):
                    setattr(record, key, value)
            session.flush()
            return CouponService._format(record)

    @staticmethod
    def list_coupons() -> list[dict]:
        with get_session() as session:
            records = session.query(Coupon).all()
            return [CouponService._format(r) for r in records]

    @staticmethod
    def validate_coupon(
        code: str,
        user_id: str,
        plan_id: str,
        order_amount: int,
        session=None,
    ) -> dict:
        uid = UUID(user_id)
        try:
            pid = UUID(plan_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        if session is not None:
            record = session.query(Coupon).filter(Coupon.code == code.upper()).with_for_update().first()
            if not record:
                raise AppError(ErrorCode.COUPON_NOT_FOUND)
            CouponService._validate_coupon_record(record, uid, pid, order_amount, session)
            discount = CouponService._calculate_discount(
                record.discount_type,
                record.discount_value,
                order_amount,
                record.max_discount_amount,
            )
            return {
                "coupon_id": str(record.id),
                "code": record.code,
                "discount_type": record.discount_type,
                "discount_value": str(record.discount_value),
                "discount_amount": discount,
            }
        with get_session() as session:
            record = session.query(Coupon).filter(Coupon.code == code.upper()).first()
            if not record:
                raise AppError(ErrorCode.COUPON_NOT_FOUND)
            CouponService._validate_coupon_record(record, uid, pid, order_amount, session)
            discount = CouponService._calculate_discount(
                record.discount_type,
                record.discount_value,
                order_amount,
                record.max_discount_amount,
            )
            return {
                "coupon_id": str(record.id),
                "code": record.code,
                "discount_type": record.discount_type,
                "discount_value": str(record.discount_value),
                "discount_amount": discount,
            }

    @staticmethod
    def _validate_coupon_record(
        record: Coupon,
        uid: UUID,
        plan_id: UUID,
        order_amount: int,
        session,
    ) -> None:
        if not record.is_active:
            raise AppError(ErrorCode.COUPON_EXPIRED)
        if record.expires_at and record.expires_at < datetime.now(timezone.utc):
            raise AppError(ErrorCode.COUPON_EXPIRED)
        if record.max_uses > 0 and record.used_count >= record.max_uses:
            raise AppError(ErrorCode.COUPON_EXHAUSTED)
        if order_amount < record.min_order_amount:
            raise AppError(ErrorCode.COUPON_MIN_ORDER_NOT_MET)
        if record.applicable_plan_ids:
            allowed = [p.strip() for p in record.applicable_plan_ids.split(",")]
            if str(plan_id) not in allowed:
                raise AppError(ErrorCode.COUPON_INVALID_FOR_PLAN)
        existing_usage = (
            session.query(CouponUsage)
            .filter(
                CouponUsage.coupon_id == record.id,
                CouponUsage.user_id == uid,
            )
            .first()
        )
        if existing_usage:
            raise AppError(ErrorCode.COUPON_ALREADY_USED)

    @staticmethod
    def apply_coupon(
        code: str,
        user_id: str,
        order_id: str,
        order_amount: int,
        plan_id: str,
        session=None,
    ) -> dict:
        uid = UUID(user_id)
        try:
            oid = UUID(order_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        if session is not None:
            record = session.query(Coupon).filter(Coupon.code == code.upper()).with_for_update().first()
            if not record:
                raise AppError(ErrorCode.COUPON_NOT_FOUND)
            CouponService._validate_coupon_record(
                record, uid, UUID(plan_id), order_amount, session,
            )
            discount = CouponService._calculate_discount(
                record.discount_type,
                record.discount_value,
                order_amount,
                record.max_discount_amount,
            )
            record.used_count += 1
            usage = CouponUsage(
                coupon_id=record.id,
                user_id=uid,
                order_id=oid,
                discount_amount=discount,
            )
            session.add(usage)
            session.flush()
            return {
                "coupon_id": str(record.id),
                "code": record.code,
                "discount_type": record.discount_type,
                "discount_value": str(record.discount_value),
                "discount_amount": discount,
            }
        with get_session() as session:
            record = session.query(Coupon).filter(Coupon.code == code.upper()).with_for_update().first()
            if not record:
                raise AppError(ErrorCode.COUPON_NOT_FOUND)
            CouponService._validate_coupon_record(
                record, uid, UUID(plan_id), order_amount, session,
            )
            discount = CouponService._calculate_discount(
                record.discount_type,
                record.discount_value,
                order_amount,
                record.max_discount_amount,
            )
            record.used_count += 1
            usage = CouponUsage(
                coupon_id=record.id,
                user_id=uid,
                order_id=oid,
                discount_amount=discount,
            )
            session.add(usage)
            session.flush()
            return {
                "coupon_id": str(record.id),
                "code": record.code,
                "discount_type": record.discount_type,
                "discount_value": str(record.discount_value),
                "discount_amount": discount,
            }

    @staticmethod
    def _calculate_discount(
        discount_type: str,
        discount_value: Decimal,
        order_amount: int,
        max_discount_amount: int | None,
    ) -> int:
        if discount_type == "percentage":
            discount = round(Decimal(str(order_amount)) * discount_value / Decimal("100"))
        else:
            discount = int(discount_value)
        if max_discount_amount is not None and discount > max_discount_amount:
            discount = max_discount_amount
        if discount > order_amount:
            discount = order_amount
        return discount

    @staticmethod
    def _format(record: Coupon) -> dict:
        return {
            "id": str(record.id),
            "code": record.code,
            "discount_type": record.discount_type,
            "discount_value": str(record.discount_value),
            "max_uses": record.max_uses,
            "used_count": record.used_count,
            "min_order_amount": record.min_order_amount,
            "max_discount_amount": record.max_discount_amount,
            "applicable_plan_ids": record.applicable_plan_ids,
            "expires_at": record.expires_at.isoformat() if record.expires_at else None,
            "is_active": record.is_active,
        }
