"""add device_tokens table for push notifications

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-18

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "device_tokens",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("token", sa.String(512), nullable=False),
        sa.Column("platform", sa.String(10), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )
    op.create_index(op.f("ix_device_tokens_user_id"), "device_tokens", ["user_id"])
    op.create_index(op.f("ix_device_tokens_token"), "device_tokens", ["token"])


def downgrade() -> None:
    op.drop_index(op.f("ix_device_tokens_token"), table_name="device_tokens")
    op.drop_index(op.f("ix_device_tokens_user_id"), table_name="device_tokens")
    op.drop_table("device_tokens")
