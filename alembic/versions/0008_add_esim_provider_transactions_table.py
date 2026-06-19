"""add esim_provider_transactions table

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-17

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "esim_provider_transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("iccid", sa.String(22), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("action_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("request_data", sa.JSON(), nullable=True),
        sa.Column("response_data", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_esim_provider_transactions_iccid",
        "esim_provider_transactions", ["iccid"],
    )
    op.create_index(
        "ix_esim_provider_transactions_created_at",
        "esim_provider_transactions", ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_esim_provider_transactions_created_at", table_name="esim_provider_transactions")
    op.drop_index("ix_esim_provider_transactions_iccid", table_name="esim_provider_transactions")
    op.drop_table("esim_provider_transactions")
