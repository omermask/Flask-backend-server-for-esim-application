"""add ondelete cascades to foreign keys and index on orders.status

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-17

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("fk_orders_user_id_users", "orders", type_="foreignkey")
    op.create_foreign_key(
        "fk_orders_user_id_users", "orders", "users",
        ["user_id"], ["id"], ondelete="CASCADE",
    )
    op.drop_constraint("fk_orders_plan_id_plans", "orders", type_="foreignkey")
    op.create_foreign_key(
        "fk_orders_plan_id_plans", "orders", "plans",
        ["plan_id"], ["id"], ondelete="RESTRICT",
    )
    op.drop_constraint("fk_order_items_order_id_orders", "order_items", type_="foreignkey")
    op.create_foreign_key(
        "fk_order_items_order_id_orders", "order_items", "orders",
        ["order_id"], ["id"], ondelete="CASCADE",
    )
    op.drop_constraint("fk_payments_user_id_users", "payments", type_="foreignkey")
    op.create_foreign_key(
        "fk_payments_user_id_users", "payments", "users",
        ["user_id"], ["id"], ondelete="CASCADE",
    )
    op.drop_constraint("fk_payments_order_id_orders", "payments", type_="foreignkey")
    op.create_foreign_key(
        "fk_payments_order_id_orders", "payments", "orders",
        ["order_id"], ["id"], ondelete="SET NULL",
    )
    op.drop_constraint("fk_wallets_user_id_users", "wallets", type_="foreignkey")
    op.create_foreign_key(
        "fk_wallets_user_id_users", "wallets", "users",
        ["user_id"], ["id"], ondelete="CASCADE",
    )
    op.drop_constraint("fk_wallet_transactions_wallet_id_wallets", "wallet_transactions", type_="foreignkey")
    op.create_foreign_key(
        "fk_wallet_transactions_wallet_id_wallets", "wallet_transactions", "wallets",
        ["wallet_id"], ["id"], ondelete="CASCADE",
    )
    op.drop_constraint("fk_audit_logs_user_id_users", "audit_logs", type_="foreignkey")
    op.create_foreign_key(
        "fk_audit_logs_user_id_users", "audit_logs", "users",
        ["user_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_index("ix_idempotency_records_expires_at", "idempotency_records", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_idempotency_records_expires_at", table_name="idempotency_records")
    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_constraint("fk_orders_user_id_users", "orders", type_="foreignkey")
    op.create_foreign_key(
        "fk_orders_user_id_users", "orders", "users",
        ["user_id"], ["id"],
    )
    op.drop_constraint("fk_orders_plan_id_plans", "orders", type_="foreignkey")
    op.create_foreign_key(
        "fk_orders_plan_id_plans", "orders", "plans",
        ["plan_id"], ["id"],
    )
    op.drop_constraint("fk_order_items_order_id_orders", "order_items", type_="foreignkey")
    op.create_foreign_key(
        "fk_order_items_order_id_orders", "order_items", "orders",
        ["order_id"], ["id"],
    )
    op.drop_constraint("fk_payments_user_id_users", "payments", type_="foreignkey")
    op.create_foreign_key(
        "fk_payments_user_id_users", "payments", "users",
        ["user_id"], ["id"],
    )
    op.drop_constraint("fk_payments_order_id_orders", "payments", type_="foreignkey")
    op.create_foreign_key(
        "fk_payments_order_id_orders", "payments", "orders",
        ["order_id"], ["id"],
    )
    op.drop_constraint("fk_wallets_user_id_users", "wallets", type_="foreignkey")
    op.create_foreign_key(
        "fk_wallets_user_id_users", "wallets", "users",
        ["user_id"], ["id"],
    )
    op.drop_constraint("fk_wallet_transactions_wallet_id_wallets", "wallet_transactions", type_="foreignkey")
    op.create_foreign_key(
        "fk_wallet_transactions_wallet_id_wallets", "wallet_transactions", "wallets",
        ["wallet_id"], ["id"],
    )
    op.drop_constraint("fk_audit_logs_user_id_users", "audit_logs", type_="foreignkey")
    op.create_foreign_key(
        "fk_audit_logs_user_id_users", "audit_logs", "users",
        ["user_id"], ["id"],
    )
