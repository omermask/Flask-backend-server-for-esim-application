from __future__ import annotations

from typing import ClassVar

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "device_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("device_id", sa.String(255), nullable=False),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_device_sessions_active_user",
        "device_sessions",
        ["user_id"],
        postgresql_where=sa.text("is_active = true"),
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("idx_device_sessions_active_user", table_name="device_sessions")
    op.drop_table("device_sessions")
