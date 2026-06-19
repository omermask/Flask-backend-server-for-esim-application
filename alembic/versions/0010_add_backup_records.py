"""add missing backup_records table

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-17

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "backup_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("filepath", sa.String(512), nullable=False),
        sa.Column("file_size", sa.BigInteger, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("backup_type", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_backup_records_status", "backup_records", ["status"])


def downgrade() -> None:
    op.drop_table("backup_records")
