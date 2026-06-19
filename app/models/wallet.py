from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import UUIDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class Wallet(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "wallets"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False,
    )
    balance: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False,
    )
    frozen_balance: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False,
    )

    user: Mapped[User] = relationship(
        "User", back_populates="wallet", lazy="selectin",
    )
    transactions: Mapped[list[WalletTransaction]] = relationship(
        "WalletTransaction", back_populates="wallet", lazy="selectin",
    )
    freezes: Mapped[list["WalletFreeze"]] = relationship(
        "WalletFreeze", back_populates="wallet", lazy="selectin",
    )


class WalletTransaction(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "wallet_transactions"

    wallet_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    amount: Mapped[int] = mapped_column(
        BigInteger, nullable=False,
    )
    type: Mapped[str] = mapped_column(
        String(20), nullable=False,
    )
    reference_type: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True,
    )
    reference_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        nullable=True,
    )
    balance_before: Mapped[int] = mapped_column(
        BigInteger, nullable=False,
    )
    balance_after: Mapped[int] = mapped_column(
        BigInteger, nullable=False,
    )
    description: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
    )

    wallet: Mapped[Wallet] = relationship(
        "Wallet", back_populates="transactions", lazy="selectin",
    )
