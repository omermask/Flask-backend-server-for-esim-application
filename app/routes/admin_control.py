from __future__ import annotations

from uuid import UUID

from flask import Blueprint, g, request

from app.core.middleware import require_auth
from app.core.response import UnifiedResponse
from app.core.errors import AppError, ErrorCode
from app.core.validators import AdminRefundRequest, AdminWalletAdjustRequest, PaginationParams
from app.services.admin_service import AdminService
from app.services.audit_service import AuditService
from app.services.order_service import OrderService

admin_control_routes = Blueprint(
    "admin_control", __name__, url_prefix="/api/v1/admin",
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


# ── User Management ─────────────────────────────────────────────────


@admin_control_routes.route("/users/search", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def search_users():
    pagination = PaginationParams(
        page=request.args.get("page", 1, type=int),
        limit=request.args.get("limit", 20, type=int),
    )
    q = request.args.get("q", "")
    role = request.args.get("role") or None
    is_active = request.args.get("is_active")
    is_active = (
        is_active.lower() in ("true", "1", "yes") if is_active else None
    )
    sort_by = request.args.get("sort_by", "created_at")
    sort_order = request.args.get("sort_order", "desc")
    result = AdminService.search_users(
        q=q, role=role, is_active=is_active,
        page=pagination.page, limit=pagination.limit,
        sort_by=sort_by, sort_order=sort_order,
    )
    AuditService.log(
        user_id=_get_admin_id(),
        action="admin.search_users",
        resource_type="user",
        details={"query": q, "role": role, "total": result.get("total", 0)},
        ip_address=_get_client_ip(),
        user_agent=_get_user_agent(),
    )
    return UnifiedResponse.success(data=result)


@admin_control_routes.route("/users/<user_id>", methods=["PUT"])
@require_auth(roles=["admin", "superadmin"])
def update_user(user_id: str):
    data = request.get_json(silent=True) or {}
    try:
        result = AdminService.update_user(user_id, admin_id=_get_admin_id(), **data)
    except AppError as exc:
        return UnifiedResponse.from_error_code(exc.code)
    AuditService.log(
        user_id=_get_admin_id(),
        action="admin.update_user",
        resource_type="user",
        resource_id=user_id,
        details=data,
        ip_address=_get_client_ip(),
        user_agent=_get_user_agent(),
    )
    return UnifiedResponse.success(data=result)


@admin_control_routes.route("/users/<user_id>/ban", methods=["POST"])
@require_auth(roles=["admin", "superadmin"])
def ban_user(user_id: str):
    try:
        uid = UUID(user_id)
    except (ValueError, AttributeError):
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_INVALID_UUID)
    admin_id = _get_admin_id()
    if str(uid) == admin_id:
        return UnifiedResponse.from_error_code(ErrorCode.ADMIN_CANNOT_MODIFY_SELF)
    result = AdminService.update_user(user_id, admin_id=admin_id, is_active=False)
    AuditService.log(
        user_id=admin_id,
        action="admin.ban_user",
        resource_type="user",
        resource_id=user_id,
        ip_address=_get_client_ip(),
        user_agent=_get_user_agent(),
    )
    return UnifiedResponse.success(data=result)


@admin_control_routes.route("/users/<user_id>/unban", methods=["POST"])
@require_auth(roles=["admin", "superadmin"])
def unban_user(user_id: str):
    result = AdminService.update_user(user_id, admin_id=_get_admin_id(), is_active=True)
    AuditService.log(
        user_id=_get_admin_id(),
        action="admin.unban_user",
        resource_type="user",
        resource_id=user_id,
        ip_address=_get_client_ip(),
        user_agent=_get_user_agent(),
    )
    return UnifiedResponse.success(data=result)


@admin_control_routes.route("/users/<user_id>/wallet", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def get_user_wallet(user_id: str):
    try:
        result = AdminService.get_user_wallet(user_id)
        return UnifiedResponse.success(data=result)
    except AppError as exc:
        return UnifiedResponse.from_error_code(exc.code)


@admin_control_routes.route("/users/<user_id>/wallet/transactions", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def get_user_wallet_transactions(user_id: str):
    pagination = PaginationParams(
        page=request.args.get("page", 1, type=int),
        limit=request.args.get("limit", 20, type=int),
    )
    try:
        result = AdminService.get_user_wallet_transactions(
            user_id, page=pagination.page, limit=pagination.limit,
        )
        return UnifiedResponse.success(data=result)
    except AppError as exc:
        return UnifiedResponse.from_error_code(exc.code)


@admin_control_routes.route("/users/<user_id>/wallet/adjust", methods=["POST"])
@require_auth(roles=["admin", "superadmin"])
def adjust_wallet(user_id: str):
    data = request.get_json(silent=True) or {}
    try:
        params = AdminWalletAdjustRequest(**data)
    except Exception:
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_INVALID_AMOUNT)
    try:
        result = AdminService.manual_adjust_wallet(
            user_id=user_id, admin_id=_get_admin_id(),
            amount=params.amount, reason=params.reason,
        )
    except AppError as exc:
        return UnifiedResponse.from_error_code(exc.code)
    AuditService.log(
        user_id=_get_admin_id(),
        action="admin.adjust_wallet",
        resource_type="wallet",
        resource_id=user_id,
        details={"amount": amount, "reason": reason},
        ip_address=_get_client_ip(),
        user_agent=_get_user_agent(),
    )
    return UnifiedResponse.success(data=result)


# ── Order Management ────────────────────────────────────────────────


@admin_control_routes.route("/orders/<order_id>", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def get_order(order_id: str):
    try:
        result = AdminService.get_order_by_id(order_id)
        return UnifiedResponse.success(data=result)
    except AppError as exc:
        return UnifiedResponse.from_error_code(exc.code)


@admin_control_routes.route("/orders/<order_id>/refund", methods=["POST"])
@require_auth(roles=["admin", "superadmin"])
def refund_order(order_id: str):
    data = request.get_json(silent=True) or {}
    try:
        params = AdminRefundRequest(order_id=order_id, **data)
    except Exception:
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_MISSING_FIELD)
    try:
        from app.services.refund_service import RefundService
        result = RefundService.create_refund(
            order_id=params.order_id,
            admin_id=_get_admin_id(),
            amount=params.amount,
            reason=params.reason,
        )
    except AppError as exc:
        return UnifiedResponse.from_error_code(exc.code)
    AuditService.log(
        user_id=_get_admin_id(),
        action="admin.refund_order",
        resource_type="order",
        resource_id=order_id,
        details={"amount": amount, "reason": reason},
        ip_address=_get_client_ip(),
        user_agent=_get_user_agent(),
    )
    return UnifiedResponse.success(data=result)


@admin_control_routes.route("/orders", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def list_orders():
    pagination = PaginationParams(
        page=request.args.get("page", 1, type=int),
        limit=request.args.get("limit", 20, type=int),
    )
    status = request.args.get("status") or None
    user_id = request.args.get("user_id") or None
    plan_id = request.args.get("plan_id") or None
    sort_by = request.args.get("sort_by", "created_at")
    sort_order = request.args.get("sort_order", "desc")
    try:
        result = AdminService.list_orders(
            page=pagination.page, limit=pagination.limit,
            status=status, user_id=user_id, plan_id=plan_id,
            sort_by=sort_by, sort_order=sort_order,
        )
        return UnifiedResponse.success(data=result)
    except AppError as exc:
        return UnifiedResponse.from_error_code(exc.code)


@admin_control_routes.route("/orders/<order_id>/cancel", methods=["POST"])
@require_auth(roles=["admin", "superadmin"])
def cancel_order(order_id: str):
    data = request.get_json(silent=True) or {}
    reason = data.get("reason", "")
    try:
        result = AdminService.cancel_order(
            order_id=order_id, admin_id=_get_admin_id(), reason=reason,
        )
    except AppError as exc:
        return UnifiedResponse.from_error_code(exc.code)
    AuditService.log(
        user_id=_get_admin_id(),
        action="admin.cancel_order",
        resource_type="order",
        resource_id=order_id,
        details={"reason": reason},
        ip_address=_get_client_ip(),
        user_agent=_get_user_agent(),
    )
    return UnifiedResponse.success(data=result)


@admin_control_routes.route("/orders/<order_id>/reprocess", methods=["POST"])
@require_auth(roles=["admin", "superadmin"])
def reprocess_order(order_id: str):
    try:
        result = AdminService.reprocess_order(order_id)
    except AppError as exc:
        return UnifiedResponse.from_error_code(exc.code)
    AuditService.log(
        user_id=_get_admin_id(),
        action="admin.reprocess_order",
        resource_type="order",
        resource_id=order_id,
        ip_address=_get_client_ip(),
        user_agent=_get_user_agent(),
    )
    return UnifiedResponse.success(data=result)


@admin_control_routes.route("/orders/<order_id>/approve", methods=["POST"])
@require_auth(roles=["admin", "superadmin"])
def approve_order(order_id: str):
    try:
        result = OrderService.approve_order(order_id)
    except AppError as exc:
        return UnifiedResponse.from_error_code(exc.code)
    AuditService.log(
        user_id=_get_admin_id(),
        action="admin.approve_order",
        resource_type="order",
        resource_id=order_id,
        ip_address=_get_client_ip(),
        user_agent=_get_user_agent(),
    )
    return UnifiedResponse.success(data=result)


# ── Payment Management ──────────────────────────────────────────────


@admin_control_routes.route("/payments", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def list_payments():
    pagination = PaginationParams(
        page=request.args.get("page", 1, type=int),
        limit=request.args.get("limit", 20, type=int),
    )
    status = request.args.get("status") or None
    method = request.args.get("method") or None
    user_id = request.args.get("user_id") or None
    try:
        result = AdminService.list_payments(
            page=pagination.page, limit=pagination.limit,
            status=status, method=method, user_id=user_id,
        )
        return UnifiedResponse.success(data=result)
    except AppError as exc:
        return UnifiedResponse.from_error_code(exc.code)


@admin_control_routes.route("/payments/<payment_id>/confirm", methods=["POST"])
@require_auth(roles=["admin", "superadmin"])
def confirm_payment(payment_id: str):
    try:
        result = AdminService.manual_confirm_payment(
            payment_id=payment_id, admin_id=_get_admin_id(),
        )
    except AppError as exc:
        return UnifiedResponse.from_error_code(exc.code)
    AuditService.log(
        user_id=_get_admin_id(),
        action="admin.confirm_payment",
        resource_type="payment",
        resource_id=payment_id,
        ip_address=_get_client_ip(),
        user_agent=_get_user_agent(),
    )
    return UnifiedResponse.success(data=result)


@admin_control_routes.route("/payments/<payment_id>/refund", methods=["POST"])
@require_auth(roles=["admin", "superadmin"])
def refund_payment(payment_id: str):
    data = request.get_json(silent=True) or {}
    reason = data.get("reason", "")
    try:
        result = AdminService.manual_refund_payment(
            payment_id=payment_id, admin_id=_get_admin_id(), reason=reason,
        )
    except AppError as exc:
        return UnifiedResponse.from_error_code(exc.code)
    AuditService.log(
        user_id=_get_admin_id(),
        action="admin.refund_payment",
        resource_type="payment",
        resource_id=payment_id,
        details={"reason": reason},
        ip_address=_get_client_ip(),
        user_agent=_get_user_agent(),
    )
    return UnifiedResponse.success(data=result)


# ── System Settings ─────────────────────────────────────────────────


@admin_control_routes.route("/settings", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def list_settings():
    settings = AdminService.get_settings()
    return UnifiedResponse.success(data={"items": settings})


@admin_control_routes.route("/settings/<key>", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def get_setting(key: str):
    try:
        setting = AdminService.get_setting(key)
        return UnifiedResponse.success(data=setting)
    except AppError as exc:
        return UnifiedResponse.from_error_code(exc.code)


@admin_control_routes.route("/settings/<key>", methods=["PUT"])
@require_auth(roles=["admin", "superadmin"])
def set_setting(key: str):
    data = request.get_json(silent=True) or {}
    value = data.get("value", "")
    description = data.get("description", "")
    if not value:
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_MISSING_FIELD)
    result = AdminService.set_setting(
        key=key, value=value, description=description,
        admin_id=_get_admin_id(),
    )
    AuditService.log(
        user_id=_get_admin_id(),
        action="admin.set_setting",
        resource_type="system_setting",
        resource_id=key,
        details={"key": key},
        ip_address=_get_client_ip(),
        user_agent=_get_user_agent(),
    )
    return UnifiedResponse.success(data=result)


@admin_control_routes.route("/settings/<key>", methods=["DELETE"])
@require_auth(roles=["admin", "superadmin"])
def delete_setting(key: str):
    try:
        AdminService.delete_setting(key)
    except AppError as exc:
        return UnifiedResponse.from_error_code(exc.code)
    AuditService.log(
        user_id=_get_admin_id(),
        action="admin.delete_setting",
        resource_type="system_setting",
        resource_id=key,
        ip_address=_get_client_ip(),
        user_agent=_get_user_agent(),
    )
    return UnifiedResponse.success(data={"message": "Setting deleted"})


# ── Server Config (official_currency, timezone, auto_fetch_interval) ──


@admin_control_routes.route("/server-config", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def get_server_config():
    from app.services.settings_service import SettingsService
    config = SettingsService.get_all()
    return UnifiedResponse.success(data=config)


@admin_control_routes.route("/server-config", methods=["PUT"])
@require_auth(roles=["admin", "superadmin"])
def update_server_config():
    from app.services.settings_service import SettingsService, SETTING_KEYS
    from app.services.admin_service import AdminService
    data = request.get_json(silent=True) or {}
    updated = {}
    for key in SETTING_KEYS:
        if key in data:
            value = str(data[key])
            AdminService.set_setting(
                key=key, value=value,
                description=f"Server config: {key}",
                admin_id=_get_admin_id(),
            )
            updated[key] = value
    # Refresh cached timezone if changed
    if "timezone" in updated:
        from app.core.constants import clear_tz_cache
        clear_tz_cache()
    return UnifiedResponse.success(data=updated)


# ── Audit Logs ──────────────────────────────────────────────────────


@admin_control_routes.route("/audit-logs", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def list_audit_logs():
    pagination = PaginationParams(
        page=request.args.get("page", 1, type=int),
        limit=request.args.get("limit", 20, type=int),
    )
    user_id = request.args.get("user_id") or None
    action = request.args.get("action") or None
    resource_type = request.args.get("resource_type") or None
    try:
        result = AdminService.list_audit_logs(
            page=pagination.page, limit=pagination.limit,
            user_id=user_id, action=action, resource_type=resource_type,
        )
        return UnifiedResponse.success(data=result)
    except AppError as exc:
        return UnifiedResponse.from_error_code(exc.code)


# ── Plans Stock ─────────────────────────────────────────────────────


@admin_control_routes.route("/plans-stock", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def plans_stock():
    plan_id = request.args.get("plan_id") or None
    result = AdminService.get_plan_stock(plan_id=plan_id)
    return UnifiedResponse.success(data={"items": result})
