from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import UUIDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class SystemSetting(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True,
    )
    value: Mapped[str] = mapped_column(
        Text, nullable=False,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )

    updater: Mapped[Optional[User]] = relationship(
        "User", lazy="selectin",
    )
