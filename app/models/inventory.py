import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import UUIDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.plan import Plan
    from app.models.user import User
    from app.models.order import OrderItem


class ImportBatch(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "import_batches"

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    plan_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("plans.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    total_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="completed", nullable=False)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    plan: Mapped[Optional[Plan]] = relationship("Plan", lazy="selectin")


class EsimInventory(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "esim_inventory"

    iccid: Mapped[str] = mapped_column(
        String(22), unique=True, nullable=False, index=True,
    )
    plan_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("plans.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), default="available", nullable=False, index=True,
    )
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("import_batches.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    order_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("order_items.id", ondelete="SET NULL"), nullable=True, unique=True,
    )
    sold_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    activated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    activation_retries: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )
    last_error: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )
    suspended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    data_usage_mb: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, default=0,
    )

    plan: Mapped[Optional[Plan]] = relationship("Plan", lazy="selectin")
    batch: Mapped[Optional[ImportBatch]] = relationship("ImportBatch", lazy="selectin")
