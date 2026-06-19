"""add support, referral, sms tables + referral fields on users

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-17

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── users: referral fields ───────────────────────────────────
    # ── users: referral fields ───────────────────────────────────
    op.add_column("users", sa.Column("referral_code", sa.String(20), nullable=True))
    op.add_column("users", sa.Column("referred_by_id", UUID(as_uuid=True), nullable=True))
    op.create_unique_constraint("uq_users_referral_code", "users", ["referral_code"])
    op.create_index("ix_users_referral_code", "users", ["referral_code"])
    op.create_index("ix_users_referred_by_id", "users", ["referred_by_id"])
    op.create_foreign_key(
        "fk_users_referred_by", "users", "users",
        ["referred_by_id"], ["id"], ondelete="SET NULL",
    )

    # ── sms_provider_transactions ────────────────────────────────
    op.create_table(
        "sms_provider_transactions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("message_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("request_data", JSONB, nullable=True),
        sa.Column("response_data", JSONB, nullable=True),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("lang", sa.String(10), nullable=False, server_default="en"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_sms_provider_transactions_phone", "sms_provider_transactions", ["phone"])

    # ── referral_rewards ─────────────────────────────────────────
    op.create_table(
        "referral_rewards",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("referrer_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("referred_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("order_id", sa.String(36), nullable=True),
        sa.Column("amount", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("qualify_condition", sa.String(30), nullable=False, server_default="any_order"),
        sa.Column("qualify_threshold", sa.Integer, nullable=True),
        sa.Column("auto_credit", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("credited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_referral_rewards_referrer_id", "referral_rewards", ["referrer_id"])
    op.create_index("ix_referral_rewards_referred_id", "referral_rewards", ["referred_id"])

    # ── support_tickets ─────────────────────────────────────────
    op.create_table(
        "support_tickets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("priority", sa.String(10), nullable=False, server_default="medium"),
        sa.Column("assigned_to_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_support_tickets_user_id", "support_tickets", ["user_id"])
    op.create_index("ix_support_tickets_status", "support_tickets", ["status"])

    # ── support_messages ─────────────────────────────────────────
    op.create_table(
        "support_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("ticket_id", UUID(as_uuid=True), sa.ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("admin_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_support_messages_ticket_id", "support_messages", ["ticket_id"])


def downgrade() -> None:
    op.drop_table("support_messages")
    op.drop_table("support_tickets")
    op.drop_table("referral_rewards")
    op.drop_table("sms_provider_transactions")
    op.drop_constraint("fk_users_referred_by", "users", type_="foreignkey")
    op.drop_index("ix_users_referred_by_id", table_name="users")
    op.drop_index("ix_users_referral_code", table_name="users")
    op.drop_constraint("uq_users_referral_code", "users", type_="unique")
    op.drop_column("users", "referred_by_id")
    op.drop_column("users", "referral_code")
