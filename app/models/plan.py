from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Integer, Numeric, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import MAX_NAME_LENGTH
from app.core.database import Base
from app.models.mixins import UUIDMixin, TimestampMixin


class Plan(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "plans"

    name: Mapped[str] = mapped_column(
        String(MAX_NAME_LENGTH), nullable=False,
    )
    description: Mapped[str] = mapped_column(
        Text, default="", nullable=False,
    )
    data_amount_mb: Mapped[int] = mapped_column(
        Integer, nullable=False,
    )
    duration_days: Mapped[int] = mapped_column(
        Integer, nullable=False,
    )
    price_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False,
    )
    price_iqd: Mapped[int] = mapped_column(
        BigInteger, nullable=False,
    )
    markup_percentage: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("20.00"), nullable=False,
    )
    countries: Mapped[str] = mapped_column(
        String(500), default="all", nullable=False,
    )
    provider_bundle_id: Mapped[str] = mapped_column(
        String(200), nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
    )
    sort_order: Mapped[int] = mapped_column(
        SmallInteger, default=0, nullable=False,
    )
