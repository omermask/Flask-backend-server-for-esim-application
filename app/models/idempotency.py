from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import DateTime, Integer, JSON, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.database import Base
from app.models.mixins import UUIDMixin


class IdempotencyRecord(UUIDMixin, Base):
    __tablename__ = "idempotency_records"

    key: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False,
    )
    resource_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
    )
    resource_id: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
    )
    response_code: Mapped[int] = mapped_column(
        Integer, nullable=False,
    )
    response_body: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON, nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True,
    )

    @classmethod
    def clean_expired(cls, session: Session) -> int:
        now = datetime.now(timezone.utc)
        deleted = (
            session.query(cls)
            .filter(cls.expires_at < now)
            .delete()
        )
        return deleted
