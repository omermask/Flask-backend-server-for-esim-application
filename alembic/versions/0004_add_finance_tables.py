"""add financial tables: exchange_rates, tax_rates, coupons, coupon_usages, refunds, wallet_freezes + new order/wallet columns

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-17

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # exchange_rates
    op.create_table(
        "exchange_rates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("base_currency", sa.String(3), nullable=False, server_default="IQD"),
        sa.Column("target_currency", sa.String(3), nullable=False),
        sa.Column("rate", sa.Numeric(12, 6), nullable=False),
        sa.Column("source", sa.String(50), nullable=False, server_default="manual"),
        sa.PrimaryKeyConstraint("id"),
    )

    # tax_rates
    op.create_table(
        "tax_rates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("percentage", sa.Numeric(5, 2), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # coupons
    op.create_table(
        "coupons",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("discount_type", sa.String(10), nullable=False),
        sa.Column("discount_value", sa.Numeric(10, 2), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("min_order_amount", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_discount_amount", sa.BigInteger(), nullable=True),
        sa.Column("applicable_plan_ids", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_coupons_code", "coupons", ["code"])

    # coupon_usages
    op.create_table(
        "coupon_usages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("coupon_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("discount_amount", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["coupon_id"], ["coupons.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_coupon_usages_coupon_id", "coupon_usages", ["coupon_id"])
    op.create_index("ix_coupon_usages_order_id", "coupon_usages", ["order_id"])

    # refunds
    op.create_table(
        "refunds",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("admin_id", sa.Uuid(), nullable=True),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["admin_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_refunds_order_id", "refunds", ["order_id"])

    # wallet_freezes
    op.create_table(
        "wallet_freezes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("wallet_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'active'")),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wallet_freezes_wallet_id", "wallet_freezes", ["wallet_id"])

    # new order columns
    op.add_column("orders", sa.Column("currency", sa.String(3), nullable=False, server_default="IQD"))
    op.add_column("orders", sa.Column("tax_amount", sa.BigInteger(), nullable=False, server_default=sa.text("0")))
    op.add_column("orders", sa.Column("tax_rate", sa.String(100), nullable=True))
    op.add_column("orders", sa.Column("discount_amount", sa.BigInteger(), nullable=False, server_default=sa.text("0")))
    op.add_column("orders", sa.Column("coupon_code", sa.String(50), nullable=True))
    op.add_column("orders", sa.Column("cost_price_iqd", sa.BigInteger(), nullable=False, server_default=sa.text("0")))
    op.add_column("orders", sa.Column("refunded_amount", sa.BigInteger(), nullable=False, server_default=sa.text("0")))

    # new wallet column
    op.add_column("wallets", sa.Column("frozen_balance", sa.BigInteger(), nullable=False, server_default=sa.text("0")))


def downgrade() -> None:
    op.drop_column("wallets", "frozen_balance")

    op.drop_column("orders", "refunded_amount")
    op.drop_column("orders", "cost_price_iqd")
    op.drop_column("orders", "coupon_code")
    op.drop_column("orders", "discount_amount")
    op.drop_column("orders", "tax_rate")
    op.drop_column("orders", "tax_amount")
    op.drop_column("orders", "currency")

    op.drop_index("ix_wallet_freezes_wallet_id", table_name="wallet_freezes")
    op.drop_table("wallet_freezes")

    op.drop_index("ix_refunds_order_id", table_name="refunds")
    op.drop_table("refunds")

    op.drop_index("ix_coupon_usages_order_id", table_name="coupon_usages")
    op.drop_index("ix_coupon_usages_coupon_id", table_name="coupon_usages")
    op.drop_table("coupon_usages")

    op.drop_index("ix_coupons_code", table_name="coupons")
    op.drop_table("coupons")

    op.drop_table("tax_rates")
    op.drop_table("exchange_rates")
