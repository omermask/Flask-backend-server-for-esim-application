from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import UUIDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class BackupRecord(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "backup_records"

    filename: Mapped[str] = mapped_column(
        String(255), nullable=False,
    )
    filepath: Mapped[str] = mapped_column(
        String(512), nullable=False,
    )
    file_size: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), default="running", nullable=False,
    )
    backup_type: Mapped[str] = mapped_column(
        String(20), default="manual", nullable=False,
    )
    created_by: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    notes: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    creator: Mapped[Optional[User]] = relationship(
        "User", lazy="selectin",
    )
