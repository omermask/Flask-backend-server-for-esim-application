from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import UUIDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class ReferralReward(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "referral_rewards"

    referrer_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    referred_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True,
    )
    order_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True,
    )

    amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False,
    )

    qualify_condition: Mapped[str] = mapped_column(
        String(30), default="any_order", nullable=False,
    )
    qualify_threshold: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
    )
    auto_credit: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    notes: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )
    credited_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )

    referrer: Mapped[User] = relationship(
        "User", foreign_keys=[referrer_id], back_populates="referral_rewards_given",
    )
    referred: Mapped[User] = relationship(
        "User", foreign_keys=[referred_id], back_populates="referral_reward_received",
    )
