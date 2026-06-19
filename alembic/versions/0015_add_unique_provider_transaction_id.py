"""add unique constraint on provider_transaction_id in payments

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-18

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_payments_provider_transaction_id",
        "payments",
        ["provider_transaction_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_payments_provider_transaction_id",
        "payments",
        type_="unique",
    )
