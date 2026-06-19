from __future__ import annotations

from flask import Blueprint, g, request

from app.core.middleware import require_auth
from app.core.response import UnifiedResponse
from app.core.errors import AppError
from app.core.validators import PaginationParams
from app.services.support_service import SupportTicketService
from app.services.audit_service import AuditService

admin_support_routes = Blueprint(
    "admin_support", __name__, url_prefix="/api/v1/admin/support",
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


@admin_support_routes.route("/tickets", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def list_tickets():
    pagination = PaginationParams(
        page=request.args.get("page", 1, type=int),
        limit=request.args.get("limit", 20, type=int),
    )
    status = request.args.get("status") or None
    priority = request.args.get("priority") or None
    result = SupportTicketService.admin_list_tickets(
        page=pagination.page, limit=pagination.limit,
        status=status, priority=priority,
    )
    AuditService.log(
        user_id=_get_admin_id(),
        action="admin.list_support_tickets",
        resource_type="support_ticket",
        details={"status": status, "priority": priority, "total": result.get("total", 0)},
        ip_address=_get_client_ip(),
        user_agent=_get_user_agent(),
    )
    return UnifiedResponse.success(data=result)


@admin_support_routes.route("/tickets/<ticket_id>", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def get_ticket(ticket_id: str):
    try:
        result = SupportTicketService.admin_get_ticket(ticket_id)
        return UnifiedResponse.success(data=result)
    except AppError as exc:
        return UnifiedResponse.from_error_code(exc.code)


@admin_support_routes.route("/tickets/<ticket_id>/reply", methods=["POST"])
@require_auth(roles=["admin", "superadmin"])
def reply_ticket(ticket_id: str):
    data = request.get_json(silent=True) or {}
    try:
        result = SupportTicketService.admin_reply(
            admin_id=_get_admin_id(), ticket_id=ticket_id,
            message=data.get("message", ""),
        )
    except AppError as exc:
        return UnifiedResponse.from_error_code(exc.code)
    AuditService.log(
        user_id=_get_admin_id(),
        action="admin.reply_support_ticket",
        resource_type="support_ticket",
        resource_id=ticket_id,
        ip_address=_get_client_ip(),
        user_agent=_get_user_agent(),
    )
    return UnifiedResponse.success(data=result)


@admin_support_routes.route("/tickets/<ticket_id>/status", methods=["PATCH"])
@require_auth(roles=["admin", "superadmin"])
def update_ticket_status(ticket_id: str):
    data = request.get_json(silent=True) or {}
    try:
        result = SupportTicketService.admin_update_status(
            ticket_id=ticket_id, status=data.get("status", ""),
        )
    except AppError as exc:
        return UnifiedResponse.from_error_code(exc.code)
    AuditService.log(
        user_id=_get_admin_id(),
        action="admin.update_ticket_status",
        resource_type="support_ticket",
        resource_id=ticket_id,
        details={"status": data.get("status")},
        ip_address=_get_client_ip(),
        user_agent=_get_user_agent(),
    )
    return UnifiedResponse.success(data=result)


@admin_support_routes.route("/tickets/<ticket_id>/assign", methods=["POST"])
@require_auth(roles=["admin", "superadmin"])
def assign_ticket(ticket_id: str):
    data = request.get_json(silent=True) or {}
    assigned_to_id = data.get("assigned_to_id", _get_admin_id())
    try:
        result = SupportTicketService.admin_assign(
            ticket_id=ticket_id, assigned_to_id=assigned_to_id,
        )
    except AppError as exc:
        return UnifiedResponse.from_error_code(exc.code)
    AuditService.log(
        user_id=_get_admin_id(),
        action="admin.assign_support_ticket",
        resource_type="support_ticket",
        resource_id=ticket_id,
        details={"assigned_to_id": assigned_to_id},
        ip_address=_get_client_ip(),
        user_agent=_get_user_agent(),
    )
    return UnifiedResponse.success(data=result)
