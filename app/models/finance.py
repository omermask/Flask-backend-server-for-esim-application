import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import UUIDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.user import User
    from app.models.wallet import Wallet


class ExchangeRate(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "exchange_rates"

    base_currency: Mapped[str] = mapped_column(
        String(3), default="IQD", nullable=False,
    )
    target_currency: Mapped[str] = mapped_column(
        String(3), nullable=False,
    )
    rate: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False,
    )
    source: Mapped[str] = mapped_column(
        String(50), default="manual", nullable=False,
    )


class TaxRate(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tax_rates"

    name: Mapped[str] = mapped_column(
        String(100), nullable=False,
    )
    percentage: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )


class Coupon(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "coupons"

    code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True,
    )
    discount_type: Mapped[str] = mapped_column(
        String(10), nullable=False,
    )
    discount_value: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False,
    )
    max_uses: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )
    used_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )
    min_order_amount: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False,
    )
    max_discount_amount: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True,
    )
    applicable_plan_ids: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )
    expires_at: Mapped[Optional[DateTime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
    )

    usages: Mapped[list[CouponUsage]] = relationship(
        "CouponUsage", back_populates="coupon", lazy="selectin",
    )


class CouponUsage(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "coupon_usages"

    coupon_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("coupons.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    discount_amount: Mapped[int] = mapped_column(
        BigInteger, nullable=False,
    )

    coupon: Mapped[Coupon] = relationship(
        "Coupon", back_populates="usages", lazy="selectin",
    )


class Refund(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "refunds"

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    amount: Mapped[int] = mapped_column(
        BigInteger, nullable=False,
    )
    reason: Mapped[str] = mapped_column(
        Text, nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False,
    )
    admin_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    admin_note: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )


class WalletFreeze(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "wallet_freezes"

    wallet_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    amount: Mapped[int] = mapped_column(
        BigInteger, nullable=False,
    )
    reason: Mapped[str] = mapped_column(
        Text, nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20), default="active", nullable=False,
    )
    released_at: Mapped[Optional[DateTime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=False,
    )

    wallet: Mapped[Wallet] = relationship(
        "Wallet", back_populates="freezes", lazy="selectin",
    )
