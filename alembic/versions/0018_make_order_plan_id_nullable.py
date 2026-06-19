from __future__ import annotations

from typing import ClassVar

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.alter_column("orders", "plan_id", nullable=True)


def downgrade() -> None:
    op.alter_column("orders", "plan_id", nullable=False)
