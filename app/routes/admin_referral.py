from __future__ import annotations

from flask import Blueprint, g, request

from app.core.middleware import require_auth
from app.core.response import UnifiedResponse
from app.core.errors import AppError, ErrorCode
from app.core.validators import PaginationParams
from app.services.referral_service import ReferralService
from app.services.audit_service import AuditService

admin_referral_routes = Blueprint(
    "admin_referral", __name__, url_prefix="/api/v1/admin/referral",
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


# ── Settings ──────────────────────────────────────────────────────


@admin_referral_routes.route("/settings", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def get_settings():
    result = ReferralService.get_settings()
    return UnifiedResponse.success(data=result)


@admin_referral_routes.route("/settings/<key>", methods=["PUT"])
@require_auth(roles=["admin", "superadmin"])
def update_setting(key: str):
    data = request.get_json(silent=True) or {}
    value = data.get("value", "")
    if not value:
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_MISSING_FIELD)
    try:
        result = ReferralService.update_setting(key=key, value=value)
    except AppError as exc:
        return UnifiedResponse.from_error_code(exc.code)
    AuditService.log(
        user_id=_get_admin_id(),
        action="admin.update_referral_setting",
        resource_type="referral_setting",
        resource_id=key,
        details={"key": key, "value": value},
        ip_address=_get_client_ip(),
        user_agent=_get_user_agent(),
    )
    return UnifiedResponse.success(data=result)


# ── Rewards ───────────────────────────────────────────────────────


@admin_referral_routes.route("/rewards", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def list_referrals():
    pagination = PaginationParams(
        page=request.args.get("page", 1, type=int),
        limit=request.args.get("limit", 20, type=int),
    )
    status = request.args.get("status") or None
    result = ReferralService.admin_list_referrals(
        page=pagination.page, limit=pagination.limit, status=status,
    )
    AuditService.log(
        user_id=_get_admin_id(),
        action="admin.list_referral_rewards",
        resource_type="referral",
        details={"status": status, "total": result.get("total", 0)},
        ip_address=_get_client_ip(),
        user_agent=_get_user_agent(),
    )
    return UnifiedResponse.success(data=result)


@admin_referral_routes.route("/stats", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def referral_stats():
    result = ReferralService.admin_get_stats()
    AuditService.log(
        user_id=_get_admin_id(),
        action="admin.referral_stats",
        resource_type="referral",
        ip_address=_get_client_ip(),
        user_agent=_get_user_agent(),
    )
    return UnifiedResponse.success(data=result)


@admin_referral_routes.route("/rewards/<reward_id>/credit", methods=["POST"])
@require_auth(roles=["admin", "superadmin"])
def credit_reward(reward_id: str):
    try:
        result = ReferralService.credit_reward(reward_id)
    except AppError as exc:
        return UnifiedResponse.from_error_code(exc.code)
    AuditService.log(
        user_id=_get_admin_id(),
        action="admin.credit_referral_reward",
        resource_type="referral",
        resource_id=reward_id,
        ip_address=_get_client_ip(),
        user_agent=_get_user_agent(),
    )
    return UnifiedResponse.success(data=result)


@admin_referral_routes.route("/rewards/<reward_id>/cancel", methods=["POST"])
@require_auth(roles=["admin", "superadmin"])
def cancel_reward(reward_id: str):
    data = request.get_json(silent=True) or {}
    reason = data.get("reason", "")
    try:
        result = ReferralService.cancel_reward(reward_id, reason=reason)
    except AppError as exc:
        return UnifiedResponse.from_error_code(exc.code)
    AuditService.log(
        user_id=_get_admin_id(),
        action="admin.cancel_referral_reward",
        resource_type="referral",
        resource_id=reward_id,
        details={"reason": reason},
        ip_address=_get_client_ip(),
        user_agent=_get_user_agent(),
    )
    return UnifiedResponse.success(data=result)
