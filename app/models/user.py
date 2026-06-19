from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import MAX_NAME_LENGTH, MAX_PHONE_LENGTH, OTP_CODE_LENGTH
from app.core.database import Base
from app.models.mixins import UUIDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.device_session import DeviceSession
    from app.models.wallet import Wallet
    from app.models.order import Order
    from app.models.payment import Payment
    from app.models.audit import AuditLog
    from app.models.support import SupportTicket
    from app.models.referral import ReferralReward


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    phone: Mapped[str] = mapped_column(
        String(MAX_PHONE_LENGTH), unique=True, nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(MAX_NAME_LENGTH), nullable=False,
    )
    language: Mapped[str] = mapped_column(
        String(10), default="en", nullable=False,
    )
    timezone: Mapped[str] = mapped_column(
        String(50), default="Asia/Baghdad", nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(20), default="user", nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    failed_otp_attempts: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )
    otp_blocked_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    totp_secret: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True,
    )
    totp_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    referral_code: Mapped[Optional[str]] = mapped_column(
        String(20), unique=True, nullable=True, index=True,
    )
    referred_by_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True,
    )

    device_sessions: Mapped[list[DeviceSession]] = relationship(
        "DeviceSession", back_populates="user", lazy="selectin",
    )
    wallet: Mapped[Wallet] = relationship(
        "Wallet", back_populates="user", uselist=False, lazy="selectin",
    )
    orders: Mapped[list[Order]] = relationship(
        "Order", back_populates="user", lazy="selectin",
    )
    payments: Mapped[list[Payment]] = relationship(
        "Payment", back_populates="user", lazy="selectin",
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(
        "AuditLog", back_populates="user", lazy="selectin",
    )
    support_tickets: Mapped[list[SupportTicket]] = relationship(
        "SupportTicket", back_populates="user",
        foreign_keys="SupportTicket.user_id",
        lazy="selectin",
    )
    referred_by: Mapped[Optional[User]] = relationship(
        "User", remote_side="User.id", foreign_keys=[referred_by_id],
        back_populates="referred_users",
    )
    referred_users: Mapped[list[User]] = relationship(
        "User", back_populates="referred_by",
        foreign_keys="User.referred_by_id",
        lazy="selectin",
    )
    referral_rewards_given: Mapped[list[ReferralReward]] = relationship(
        "ReferralReward", back_populates="referrer",
        foreign_keys="ReferralReward.referrer_id",
        lazy="selectin",
    )
    referral_reward_received: Mapped[Optional[ReferralReward]] = relationship(
        "ReferralReward", back_populates="referred",
        foreign_keys="ReferralReward.referred_id",
        uselist=False, lazy="selectin",
    )


class OTPCode(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "otp_codes"

    phone: Mapped[str] = mapped_column(
        String(MAX_PHONE_LENGTH), nullable=False, index=True,
    )
    code_hash: Mapped[str] = mapped_column(
        String(60), nullable=False,
    )
    purpose: Mapped[str] = mapped_column(
        String(20), nullable=False,
    )
    attempts: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer, default=3, nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    is_used: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
