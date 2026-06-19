"""fix import_batches.created_by nullable to match SET NULL FK

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-17

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("import_batches", "created_by", nullable=True)


def downgrade() -> None:
    op.alter_column("import_batches", "created_by", nullable=False)
