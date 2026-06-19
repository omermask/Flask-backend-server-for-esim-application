from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import UUIDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.plan import Plan
    from app.models.payment import Payment


class Order(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "orders"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    plan_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("plans.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    quantity: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False,
    )
    total_price_iqd: Mapped[int] = mapped_column(
        BigInteger, nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True,
    )
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(64), unique=True, nullable=True,
    )
    notes: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )
    currency: Mapped[str] = mapped_column(
        String(3), default="IQD", nullable=False,
    )
    tax_amount: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False,
    )
    tax_rate: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
    )
    discount_amount: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False,
    )
    coupon_code: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
    )
    cost_price_iqd: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False,
    )
    refunded_amount: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False,
    )

    user: Mapped[User] = relationship(
        "User", back_populates="orders", lazy="selectin",
    )
    plan: Mapped[Plan] = relationship(
        "Plan", lazy="selectin",
    )
    items: Mapped[list[OrderItem]] = relationship(
        "OrderItem", back_populates="order", lazy="selectin",
    )
    payments: Mapped[list[Payment]] = relationship(
        "Payment", back_populates="order", lazy="selectin",
    )


class OrderItem(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "order_items"

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    esim_iccid: Mapped[Optional[str]] = mapped_column(
        String(50), unique=True, nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False,
    )
    activation_code: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
    )
    qr_code: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )
    activated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    order: Mapped[Order] = relationship(
        "Order", back_populates="items", lazy="selectin",
    )
