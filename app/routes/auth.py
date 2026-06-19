from __future__ import annotations

import logging

from flask import Blueprint, g, request

from app.core.middleware import require_auth
from app.core.response import UnifiedResponse
from app.core.errors import ErrorCode
from app.core.security import decode_token, is_token_revoked
from app.services.auth_service import AuthService
from app.core.validators import RegisterRequest, VerifyOTPRequest, RefreshTokenRequest

logger = logging.getLogger("esim-ego")
auth_routes = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


@auth_routes.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    validator = RegisterRequest(**data)
    user_data = AuthService.register(
        phone=validator.phone,
        name=validator.name,
        language=validator.language,
        timezone=validator.timezone,
        referral_code=validator.referral_code,
    )
    return UnifiedResponse.success(
        data=user_data,
        code=ErrorCode.SUCCESS.value,
    )


@auth_routes.route("/send-otp", methods=["POST"])
def send_otp():
    data = request.get_json(silent=True) or {}
    phone = data.get("phone", "")
    if not phone:
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_MISSING_FIELD)
    AuthService.send_otp(phone)
    return UnifiedResponse.success(
        data={"message": "OTP sent"},
        code=ErrorCode.SUCCESS.value,
    )


@auth_routes.route("/verify-otp", methods=["POST"])
def verify_otp():
    data = request.get_json(silent=True) or {}
    validator = VerifyOTPRequest(**data)
    access_token, refresh_token, user_data = AuthService.verify_otp(
        phone=validator.phone,
        code=validator.code,
        device_id=validator.device_id,
    )
    twofa_required = user_data.pop("2fa_required", False)
    return UnifiedResponse.success(
        data={
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": 900,
            "user": user_data,
            "2fa_required": twofa_required,
        },
        code=ErrorCode.SUCCESS.value,
    )


@auth_routes.route("/refresh", methods=["POST"])
def refresh():
    data = request.get_json(silent=True) or {}
    validator = RefreshTokenRequest(**data)
    access, refresh = AuthService.refresh_token(validator.refresh_token)
    return UnifiedResponse.success(
        data={
            "access_token": access,
            "refresh_token": refresh,
            "token_type": "bearer",
            "expires_in": 900,
        },
        code=ErrorCode.SUCCESS.value,
    )


@auth_routes.route("/logout", methods=["POST"])
@require_auth()
def logout():
    data = request.get_json(silent=True) or {}
    access_jti = getattr(g, "token_jti", "")
    refresh_jti = data.get("refresh_jti", "")
    user_id = getattr(g, "user_id", "")
    device_id = data.get("device_id", "")
    AuthService.logout(
        user_id=user_id,
        access_jti=access_jti,
        refresh_jti=refresh_jti or None,
        device_id=device_id or None,
    )
    return UnifiedResponse.success(
        data={"message": "Logged out successfully"},
        code=ErrorCode.SUCCESS.value,
    )
