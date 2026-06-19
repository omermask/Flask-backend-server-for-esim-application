from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import UUIDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class SupportTicket(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "support_tickets"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="open", nullable=False, index=True,
    )
    priority: Mapped[str] = mapped_column(
        String(10), default="medium", nullable=False,
    )
    assigned_to_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    user: Mapped[User] = relationship(
        "User", foreign_keys=[user_id], back_populates="support_tickets",
    )
    assigned_to: Mapped[Optional[User]] = relationship(
        "User", foreign_keys=[assigned_to_id],
    )
    messages: Mapped[list[SupportMessage]] = relationship(
        "SupportMessage", back_populates="ticket",
        order_by="SupportMessage.created_at.asc()",
        cascade="all, delete-orphan",
    )


class SupportMessage(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "support_messages"

    ticket_id: Mapped[str] = mapped_column(
        ForeignKey("support_tickets.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    admin_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)

    ticket: Mapped[SupportTicket] = relationship(
        "SupportTicket", back_populates="messages",
    )
