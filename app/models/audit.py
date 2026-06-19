from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import UUIDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class AuditLog(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "audit_logs"

    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    action: Mapped[str] = mapped_column(
        String(50), nullable=False,
    )
    resource_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
    )
    resource_id: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
    )
    details: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON, nullable=True,
    )
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45), nullable=True,
    )
    user_agent: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True,
    )

    user: Mapped[Optional[User]] = relationship(
        "User", back_populates="audit_logs", lazy="selectin",
    )
