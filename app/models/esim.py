from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import UUIDMixin, TimestampMixin


class EsimProviderTransaction(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "esim_provider_transactions"

    iccid: Mapped[str] = mapped_column(
        String(22), nullable=False, index=True,
    )
    provider: Mapped[str] = mapped_column(
        String(30), nullable=False,
    )
    action_type: Mapped[str] = mapped_column(
        String(30), nullable=False,
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
