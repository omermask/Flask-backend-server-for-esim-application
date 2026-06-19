"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-06-17

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.create_table(
        "plans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("data_amount_mb", sa.Integer, nullable=False),
        sa.Column("duration_days", sa.Integer, nullable=False),
        sa.Column("price_usd", sa.Numeric(10, 2), nullable=False),
        sa.Column("price_iqd", sa.BigInteger, nullable=False),
        sa.Column("markup_percentage", sa.Numeric(5, 2), nullable=False, server_default="20.00"),
        sa.Column("countries", sa.String(500), nullable=False, server_default="all"),
        sa.Column("provider_bundle_id", sa.String(200), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("phone", sa.String(15), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("language", sa.String(10), nullable=False, server_default="en"),
        sa.Column("timezone", sa.String(50), nullable=False, server_default="Asia/Baghdad"),
        sa.Column("role", sa.String(20), nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("failed_otp_attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("otp_blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "otp_codes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("phone", sa.String(15), nullable=False),
        sa.Column("code_hash", sa.String(60), nullable=False),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="3"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_used", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_otp_codes_phone", "otp_codes", ["phone"])
    op.create_table(
        "wallets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("balance", sa.BigInteger, nullable=False, server_default="0"),
        sa.CheckConstraint("balance >= 0", name="ck_wallets_balance_positive"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "wallet_transactions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("wallet_id", UUID(as_uuid=True), sa.ForeignKey("wallets.id"), nullable=False),
        sa.Column("amount", sa.BigInteger, nullable=False),
        sa.CheckConstraint("amount != 0", name="ck_wallet_transactions_amount_nonzero"),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("reference_type", sa.String(20), nullable=True),
        sa.Column("reference_id", UUID(as_uuid=True), nullable=True),
        sa.Column("balance_before", sa.BigInteger, nullable=False),
        sa.Column("balance_after", sa.BigInteger, nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_wallet_transactions_wallet_id", "wallet_transactions", ["wallet_id"])
    op.create_table(
        "orders",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("plan_id", UUID(as_uuid=True), sa.ForeignKey("plans.id"), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False, server_default="1"),
        sa.Column("total_price_iqd", sa.BigInteger, nullable=False),
        sa.CheckConstraint("total_price_iqd > 0", name="ck_orders_price_positive"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("idempotency_key", sa.String(64), nullable=True, unique=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_orders_user_id", "orders", ["user_id"])
    op.create_table(
        "order_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("order_id", UUID(as_uuid=True), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("esim_iccid", sa.String(50), nullable=True, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("activation_code", sa.String(255), nullable=True),
        sa.Column("qr_code", sa.Text, nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])
    op.create_table(
        "payments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("order_id", UUID(as_uuid=True), sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("amount", sa.BigInteger, nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        sa.Column("method", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("provider_transaction_id", sa.String(255), nullable=True),
        sa.Column("provider_data", JSON, nullable=True),
        sa.Column("idempotency_key", sa.String(64), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_payments_user_id", "payments", ["user_id"])
    op.create_index("ix_payments_order_id", "payments", ["order_id"])
    op.create_table(
        "payment_provider_transactions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("payment_id", UUID(as_uuid=True), sa.ForeignKey("payments.id"), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("request_data", JSON, nullable=True),
        sa.Column("response_data", JSON, nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.String(50), nullable=True),
        sa.Column("details", JSON, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_table(
        "idempotency_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("key", sa.String(64), nullable=False, unique=True),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.String(50), nullable=True),
        sa.Column("response_code", sa.Integer, nullable=False),
        sa.Column("response_body", JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("payment_provider_transactions")
    op.drop_table("payments")
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_table("wallet_transactions")
    op.drop_table("wallets")
    op.drop_table("otp_codes")
    op.drop_table("audit_logs")
    op.drop_table("idempotency_records")
    op.drop_table("users")
    op.drop_table("plans")
