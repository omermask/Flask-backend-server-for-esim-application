"""add inventory tables: import_batches, esim_inventory

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-17

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "import_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("total_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("success_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(20), server_default="completed", nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["plans.id"], ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_import_batches_plan_id", "import_batches", ["plan_id"],
    )

    op.create_table(
        "esim_inventory",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("iccid", sa.String(22), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), server_default="available", nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=True),
        sa.Column("order_item_id", sa.Uuid(), nullable=True),
        sa.Column("sold_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activation_retries", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data_usage_mb", sa.BigInteger(), nullable=True, default=0),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["plans.id"], ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"], ["import_batches.id"], ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["order_item_id"], ["order_items.id"], ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("iccid"),
        sa.UniqueConstraint("order_item_id"),
    )
    op.create_index("ix_esim_inventory_iccid", "esim_inventory", ["iccid"])
    op.create_index("ix_esim_inventory_plan_id", "esim_inventory", ["plan_id"])
    op.create_index("ix_esim_inventory_status", "esim_inventory", ["status"])
    op.create_index("ix_esim_inventory_batch_id", "esim_inventory", ["batch_id"])


def downgrade() -> None:
    op.drop_table("esim_inventory")
    op.drop_table("import_batches")
