from __future__ import annotations

import logging
from uuid import UUID

from flask import Blueprint, request

from app.core.middleware import require_auth
from app.core.response import UnifiedResponse
from app.core.errors import AppError, ErrorCode
from app.core.security import (
    create_access_token, create_refresh_token,
    generate_totp_secret, get_totp_uri, verify_totp,
)
from app.core.validators import PaginationParams
from app.core.database import get_session
from app.models.user import User
from app.models.order import Order
from app.models.payment import Payment

logger = logging.getLogger("esim-ego")
admin_routes = Blueprint("admin", __name__, url_prefix="/api/v1/admin")


@admin_routes.route("/users", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def list_users():
    pagination = PaginationParams(
        page=request.args.get("page", 1, type=int),
        limit=request.args.get("limit", 20, type=int),
    )
    with get_session() as session:
        total = session.query(User).count()
        offset = (pagination.page - 1) * pagination.limit
        users = (
            session.query(User)
            .order_by(User.created_at.desc())
            .offset(offset)
            .limit(pagination.limit)
            .all()
        )
        return UnifiedResponse.success(data={
            "items": [
                {
                    "id": str(u.id),
                    "phone": u.phone,
                    "name": u.name,
                    "role": u.role,
                    "is_active": u.is_active,
                    "is_verified": u.is_verified,
                    "language": u.language,
                    "created_at": u.created_at.isoformat(),
                    "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
                }
                for u in users
            ],
            "total": total,
            "page": pagination.page,
            "limit": pagination.limit,
        })


@admin_routes.route("/users/<user_id>", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def get_user(user_id: str):
    try:
        uid = UUID(user_id)
    except (ValueError, AttributeError):
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_INVALID_UUID)
    with get_session() as session:
        user = session.query(User).filter(User.id == uid).first()
        if not user:
            return UnifiedResponse.from_error_code(ErrorCode.NOT_FOUND)
        return UnifiedResponse.success(data={
            "id": str(user.id),
            "phone": user.phone,
            "name": user.name,
            "role": user.role,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "language": user.language,
            "timezone": user.timezone,
            "failed_otp_attempts": user.failed_otp_attempts,
            "created_at": user.created_at.isoformat(),
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        })


@admin_routes.route("/users/<user_id>/toggle-active", methods=["POST"])
@require_auth(roles=["admin", "superadmin"])
def toggle_user_active(user_id: str):
    try:
        uid = UUID(user_id)
    except (ValueError, AttributeError):
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_INVALID_UUID)
    with get_session() as session:
        user = session.query(User).filter(User.id == uid).first()
        if not user:
            return UnifiedResponse.from_error_code(ErrorCode.NOT_FOUND)
        user.is_active = not user.is_active
        session.flush()
        return UnifiedResponse.success(data={
            "user_id": str(user.id),
            "is_active": user.is_active,
        })


@admin_routes.route("/dashboard", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def dashboard():
    with get_session() as session:
        total_users = session.query(User).count()
        total_orders = session.query(Order).count()
        total_payments = session.query(Payment).count()
        total_revenue = (
            session.query(Order)
            .filter(Order.status == "paid")
            .with_entities(Order.total_price_iqd)
            .all()
        )
        revenue_sum = sum(r[0] for r in total_revenue) if total_revenue else 0
        return UnifiedResponse.success(data={
            "total_users": total_users,
            "total_orders": total_orders,
            "total_payments": total_payments,
            "total_revenue_iqd": revenue_sum,
        })


@admin_routes.route("/2fa/setup", methods=["POST"])
@require_auth(roles=["admin", "superadmin"], require_totp=False)
def setup_2fa():
    from config import settings
    user_id = getattr(g, "user_id", "")
    try:
        uid = UUID(user_id)
    except (ValueError, AttributeError):
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_INVALID_UUID)
    with get_session() as session:
        user = session.query(User).filter(User.id == uid).first()
        if not user:
            return UnifiedResponse.from_error_code(ErrorCode.NOT_FOUND)
        secret = generate_totp_secret()
        user.totp_secret = secret
        session.flush()
    uri = get_totp_uri(secret, f"{user.phone}@esimego")
    return UnifiedResponse.success(data={
        "secret": secret,
        "provisioning_uri": uri,
        "issuer": settings.TOTP_ISSUER_NAME,
    })


@admin_routes.route("/2fa/enable", methods=["POST"])
@require_auth(roles=["admin", "superadmin"], require_totp=False)
def enable_2fa():
    user_id = getattr(g, "user_id", "")
    data = request.get_json(silent=True) or {}
    code = data.get("code", "")
    if not code:
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_MISSING_FIELD)
    try:
        uid = UUID(user_id)
    except (ValueError, AttributeError):
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_INVALID_UUID)
    with get_session() as session:
        user = session.query(User).filter(User.id == uid).first()
        if not user:
            return UnifiedResponse.from_error_code(ErrorCode.NOT_FOUND)
        if not user.totp_secret:
            return UnifiedResponse.from_error_code(ErrorCode.AUTH_2FA_INVALID)
        if not verify_totp(user.totp_secret, code):
            return UnifiedResponse.from_error_code(ErrorCode.AUTH_2FA_INVALID)
        user.totp_enabled = True
        session.flush()
    return UnifiedResponse.success(data={"message": "Two-factor authentication enabled"})


@admin_routes.route("/2fa/disable", methods=["POST"])
@require_auth(roles=["admin", "superadmin"], require_totp=False)
def disable_2fa():
    user_id = getattr(g, "user_id", "")
    data = request.get_json(silent=True) or {}
    code = data.get("code", "")
    if not code:
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_MISSING_FIELD)
    try:
        uid = UUID(user_id)
    except (ValueError, AttributeError):
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_INVALID_UUID)
    with get_session() as session:
        user = session.query(User).filter(User.id == uid).first()
        if not user:
            return UnifiedResponse.from_error_code(ErrorCode.NOT_FOUND)
        if not user.totp_secret or not user.totp_enabled:
            return UnifiedResponse.from_error_code(ErrorCode.AUTH_2FA_INVALID)
        if not verify_totp(user.totp_secret, code):
            return UnifiedResponse.from_error_code(ErrorCode.AUTH_2FA_INVALID)
        user.totp_secret = None
        user.totp_enabled = False
        session.flush()
    return UnifiedResponse.success(data={"message": "Two-factor authentication disabled"})


@admin_routes.route("/2fa/verify", methods=["POST"])
@require_auth(roles=["admin", "superadmin"], require_totp=False)
def verify_2fa():
    from config import settings
    user_id = getattr(g, "user_id", "")
    user_role = getattr(g, "user_role", "admin")
    data = request.get_json(silent=True) or {}
    code = data.get("code", "")
    if not code:
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_MISSING_FIELD)
    with get_session() as session:
        user = session.query(User).filter(User.id == UUID(user_id)).first()
        if not user:
            return UnifiedResponse.from_error_code(ErrorCode.NOT_FOUND)
        if not user.totp_secret or not user.totp_enabled:
            return UnifiedResponse.from_error_code(ErrorCode.AUTH_2FA_INVALID)
        if not verify_totp(user.totp_secret, code):
            return UnifiedResponse.from_error_code(ErrorCode.AUTH_2FA_INVALID)
    new_access = create_access_token(
        user_id=user_id,
        role=user_role,
        secret_key=settings.SECRET_KEY,
        totp_enabled=True,
        totp_verified=True,
    )
    new_refresh = create_refresh_token(
        user_id=user_id,
        role=user_role,
        secret_key=settings.SECRET_KEY,
        totp_enabled=True,
        totp_verified=True,
    )
    return UnifiedResponse.success(data={
        "access_token": new_access,
        "refresh_token": new_refresh,
        "token_type": "bearer",
        "expires_in": 900,
    })
