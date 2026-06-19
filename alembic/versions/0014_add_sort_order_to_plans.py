"""add sort_order column to plans

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-18

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("plans", sa.Column("sort_order", sa.SmallInteger(), nullable=False, server_default=sa.text("0")))


def downgrade() -> None:
    op.drop_column("plans", "sort_order")
