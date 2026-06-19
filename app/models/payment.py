from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import BigInteger, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import UUIDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.order import Order


class Payment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "payments"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    amount: Mapped[int] = mapped_column(
        BigInteger, nullable=False,
    )
    method: Mapped[str] = mapped_column(
        String(20), nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False,
    )
    provider_transaction_id: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, nullable=True,
    )
    provider_data: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON, nullable=True,
    )
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(64), unique=True, nullable=True,
    )

    user: Mapped[User] = relationship(
        "User", back_populates="payments", lazy="selectin",
    )
    order: Mapped[Optional[Order]] = relationship(
        "Order", back_populates="payments", lazy="selectin",
    )
    provider_transactions: Mapped[list[PaymentProviderTransaction]] = relationship(
        "PaymentProviderTransaction", back_populates="payment", lazy="selectin",
    )


class PaymentProviderTransaction(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "payment_provider_transactions"

    payment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payments.id"), nullable=False,
    )
    provider: Mapped[str] = mapped_column(
        String(20), nullable=False,
    )
    request_data: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON, nullable=True,
    )
    response_data: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON, nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False,
    )

    payment: Mapped[Payment] = relationship(
        "Payment", back_populates="provider_transactions", lazy="selectin",
    )
