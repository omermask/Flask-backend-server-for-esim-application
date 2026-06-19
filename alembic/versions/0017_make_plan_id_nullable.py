from __future__ import annotations

from typing import ClassVar

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.alter_column("esim_inventory", "plan_id", nullable=True)
    op.alter_column("import_batches", "plan_id", nullable=True)


def downgrade() -> None:
    op.alter_column("import_batches", "plan_id", nullable=False)
    op.alter_column("esim_inventory", "plan_id", nullable=False)
