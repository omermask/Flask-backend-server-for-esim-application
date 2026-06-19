from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from app.core.database import get_session
from app.core.errors import AppError, ErrorCode
from app.models.order import Order
from app.models.user import User
from app.models.wallet import Wallet, WalletTransaction

logger = logging.getLogger("esim-ego")


class ReportService:

    SUPPORTED_PERIODS = ("daily", "monthly", "yearly")

    @staticmethod
    def financial_report(period: str = "daily", date: str | None = None) -> dict:
        if period not in ReportService.SUPPORTED_PERIODS:
            raise AppError(ErrorCode.REPORT_INVALID_PERIOD)
        now = datetime.now(timezone.utc)
        if period == "daily":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
        elif period == "monthly":
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if start.month == 12:
                end = start.replace(year=start.year + 1, month=1)
            else:
                end = start.replace(month=start.month + 1)
        else:
            start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            end = start.replace(year=start.year + 1)
        with get_session() as session:
            orders_query = session.query(
                func.count(Order.id).label("total_orders"),
                func.coalesce(func.sum(Order.total_price_iqd), 0).label("gross_revenue"),
                func.coalesce(func.sum(Order.cost_price_iqd), 0).label("total_cost"),
                func.coalesce(func.sum(Order.discount_amount), 0).label("total_discount"),
                func.coalesce(func.sum(Order.tax_amount), 0).label("total_tax"),
                func.coalesce(func.sum(Order.refunded_amount), 0).label("total_refunded"),
            ).filter(
                Order.created_at >= start,
                Order.created_at < end,
                Order.status.in_(["paid", "refunded"]),
            ).first()
            if orders_query is None:
                return ReportService._empty_report(period, start)
            gross = int(orders_query.gross_revenue)
            cost = int(orders_query.total_cost)
            discount = int(orders_query.total_discount)
            tax = int(orders_query.total_tax)
            refunded = int(orders_query.total_refunded)
            net = gross - cost - refunded
            new_users = session.query(func.count(User.id)).filter(
                User.created_at >= start,
                User.created_at < end,
            ).scalar() or 0
            deposits = session.query(
                func.coalesce(func.sum(WalletTransaction.amount), 0)
            ).filter(
                WalletTransaction.type == "deposit",
                WalletTransaction.created_at >= start,
                WalletTransaction.created_at < end,
            ).scalar() or 0
            return {
                "period": period,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "summary": {
                    "total_orders": int(orders_query.total_orders),
                    "gross_revenue_iqd": gross,
                    "total_cost_iqd": cost,
                    "total_discount_iqd": discount,
                    "total_tax_iqd": tax,
                    "total_refunded_iqd": refunded,
                    "net_revenue_iqd": net,
                    "total_deposits_iqd": int(deposits),
                    "new_users": int(new_users),
                },
            }

    @staticmethod
    def _empty_report(period: str, start: datetime) -> dict:
        return {
            "period": period,
            "start": start.isoformat(),
            "summary": {
                "total_orders": 0,
                "gross_revenue_iqd": 0,
                "total_cost_iqd": 0,
                "total_discount_iqd": 0,
                "total_tax_iqd": 0,
                "total_refunded_iqd": 0,
                "net_revenue_iqd": 0,
                "total_deposits_iqd": 0,
                "new_users": 0,
            },
        }

    @staticmethod
    def wallet_dashboard() -> dict:
        with get_session() as session:
            total_balance = session.query(
                func.coalesce(func.sum(Wallet.balance), 0)
            ).scalar() or 0
            total_frozen = session.query(
                func.coalesce(func.sum(Wallet.frozen_balance), 0)
            ).scalar() or 0
            total_orders = session.query(func.count(Order.id)).filter(
                Order.status == "paid",
            ).scalar() or 0
            gross_revenue = session.query(
                func.coalesce(func.sum(Order.total_price_iqd), 0)
            ).filter(
                Order.status.in_(["paid", "refunded"]),
            ).scalar() or 0
            total_cost = session.query(
                func.coalesce(func.sum(Order.cost_price_iqd), 0)
            ).filter(
                Order.status.in_(["paid", "refunded"]),
            ).scalar() or 0
            total_refunded = session.query(
                func.coalesce(func.sum(Order.refunded_amount), 0)
            ).filter(
                Order.status.in_(["paid", "refunded"]),
            ).scalar() or 0
            net_profit = int(gross_revenue) - int(total_cost) - int(total_refunded)
            return {
                "total_balance_iqd": int(total_balance),
                "total_frozen_iqd": int(total_frozen),
                "available_balance_iqd": int(total_balance) - int(total_frozen),
                "total_orders": int(total_orders),
                "gross_sales_iqd": int(gross_revenue),
                "total_cost_iqd": int(total_cost),
                "total_refunded_iqd": int(total_refunded),
                "net_profit_iqd": int(net_profit),
            }
