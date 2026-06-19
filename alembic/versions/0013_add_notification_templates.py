"""add notification_templates table

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-18

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notification_templates",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("translations", sa.JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("data_schema", sa.JSON, nullable=True),
        sa.Column("description", sa.String(255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index(op.f("ix_notification_templates_key"), "notification_templates", ["key"])


def downgrade() -> None:
    op.drop_index(op.f("ix_notification_templates_key"), table_name="notification_templates")
    op.drop_table("notification_templates")
