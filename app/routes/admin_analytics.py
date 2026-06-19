from __future__ import annotations

import logging

from flask import Blueprint, g, request, Response

from app.core.middleware import require_auth
from app.core.response import UnifiedResponse
from app.core.errors import AppError
from app.core.validators import PaginationParams
from app.services.analytics_service import AnalyticsService
from app.services.audit_service import AuditService

logger = logging.getLogger("esim-ego")

admin_analytics_routes = Blueprint(
    "admin_analytics", __name__, url_prefix="/api/v1/admin/analytics",
)


def _get_admin_id() -> str:
    return getattr(g, "user_id", "")


def _get_client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or ""


def _get_user_agent() -> str:
    return request.headers.get("User-Agent", "")


# ── Dashboard ────────────────────────────────────────────────────────


@admin_analytics_routes.route("/dashboard", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def dashboard():
    stats = AnalyticsService.get_dashboard_stats()
    AuditService.log(
        user_id=_get_admin_id(),
        action="admin.dashboard",
        resource_type="analytics",
        ip_address=_get_client_ip(),
        user_agent=_get_user_agent(),
    )
    return UnifiedResponse.success(data=stats)


# ── Charts ───────────────────────────────────────────────────────────


@admin_analytics_routes.route("/charts/sales", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def sales_chart():
    days = request.args.get("days", 30, type=int)
    try:
        data = AnalyticsService.get_sales_chart(days=days)
        return UnifiedResponse.success(data={"items": data, "days": days})
    except AppError as exc:
        return UnifiedResponse.from_error_code(exc.code)


@admin_analytics_routes.route("/charts/plans", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def plans_chart():
    data = AnalyticsService.get_plan_distribution()
    return UnifiedResponse.success(data={"items": data})


@admin_analytics_routes.route("/charts/users", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def users_chart():
    period = request.args.get("period", "daily")
    try:
        data = AnalyticsService.get_user_growth(period=period)
        return UnifiedResponse.success(data={"items": data, "period": period})
    except AppError as exc:
        return UnifiedResponse.from_error_code(exc.code)


# ── Admin Activity ───────────────────────────────────────────────────


@admin_analytics_routes.route("/activity", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def admin_activity():
    pagination = PaginationParams(
        page=request.args.get("page", 1, type=int),
        limit=request.args.get("limit", 20, type=int),
    )
    action = request.args.get("action") or None
    result = AnalyticsService.get_admin_activity(
        page=pagination.page,
        limit=pagination.limit,
        action=action,
    )
    return UnifiedResponse.success(data=result)


# ── Report Export ────────────────────────────────────────────────────


@admin_analytics_routes.route("/reports/<report_type>/export", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def export_report(report_type: str):
    export_format = request.args.get("format", "csv").lower()
    filters: dict[str, str | None] = {}
    if report_type == "orders":
        filters["status"] = request.args.get("status") or None
    elif report_type == "payments":
        filters["status"] = request.args.get("status") or None
        filters["method"] = request.args.get("method") or None
    try:
        content, mime, filename = AnalyticsService.export_report(
            report_type=report_type,
            export_format=export_format,
            **filters,
        )
    except AppError as exc:
        return UnifiedResponse.from_error_code(exc.code)
    AuditService.log(
        user_id=_get_admin_id(),
        action="admin.export_report",
        resource_type="analytics",
        resource_id=report_type,
        details={"format": export_format},
        ip_address=_get_client_ip(),
        user_agent=_get_user_agent(),
    )
    return Response(
        content,
        mimetype=mime,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
