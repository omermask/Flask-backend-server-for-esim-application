from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import UUIDMixin, TimestampMixin


class NotificationTemplate(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "notification_templates"

    key: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True,
    )
    translations: Mapped[dict[str, str]] = mapped_column(
        JSON, nullable=False, default=dict,
    )
    data_schema: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON, nullable=True,
    )
    description: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
    )
