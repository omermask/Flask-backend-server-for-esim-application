from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import UUIDMixin, TimestampMixin


class SMSProviderTransaction(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "sms_provider_transactions"

    phone: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True,
    )
    provider: Mapped[str] = mapped_column(
        String(30), nullable=False,
    )
    message_type: Mapped[str] = mapped_column(
        String(20), nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False,
    )
    request_data: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON, nullable=True,
    )
    response_data: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON, nullable=True,
    )
    error_code: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
    )
    lang: Mapped[str] = mapped_column(
        String(10), default="en", nullable=False,
    )
