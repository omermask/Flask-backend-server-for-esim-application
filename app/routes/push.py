from __future__ import annotations

import logging

from flask import Blueprint, g, request

from app.core.errors import AppError, ErrorCode
from app.core.middleware import require_auth
from app.core.response import UnifiedResponse
from app.services.push_service import get_active_tokens, register_device, unregister_device

logger = logging.getLogger("esim-ego")
push_routes = Blueprint("push", __name__, url_prefix="/api/v1/push")


@push_routes.route("/register", methods=["POST"])
@require_auth(roles=["user", "admin", "superadmin"])
def register():
    data = request.get_json(silent=True) or {}
    token = (data.get("token") or "").strip()
    platform = (data.get("platform") or "").strip().lower()
    if not token or len(token) < 16:
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_MISSING_FIELD)
    if platform not in ("ios", "android"):
        return UnifiedResponse.from_error_code(
            ErrorCode.VALIDATION_INVALID_ENUM,
            data={"field": "platform", "allowed": ["ios", "android"]},
        )
    try:
        result = register_device(g.user_id, token, platform)
        if result["success"]:
            return UnifiedResponse.success(data=result)
        return UnifiedResponse.from_error_code(
            ErrorCode.VALIDATION_INVALID_PARAMETER,
            data=result,
        )
    except AppError as e:
        return UnifiedResponse.from_error_code(e.code)


@push_routes.route("/unregister", methods=["DELETE"])
@require_auth(roles=["user", "admin", "superadmin"])
def unregister():
    data = request.get_json(silent=True) or {}
    token = (data.get("token") or "").strip()
    if not token:
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_MISSING_FIELD)
    try:
        result = unregister_device(g.user_id, token)
        return UnifiedResponse.success(data=result)
    except AppError as e:
        return UnifiedResponse.from_error_code(e.code)


@push_routes.route("/tokens", methods=["GET"])
@require_auth(roles=["user", "admin", "superadmin"])
def list_tokens():
    try:
        tokens = get_active_tokens(g.user_id)
        return UnifiedResponse.success(data={
            "tokens": [
                {
                    "id": str(t["id"]),
                    "platform": t["platform"],
                    "created_at": t["created_at"].isoformat() if t["created_at"] else None,
                    "last_notified_at": t["last_notified_at"].isoformat() if t["last_notified_at"] else None,
                }
                for t in tokens
            ],
            "total": len(tokens),
        })
    except AppError as e:
        return UnifiedResponse.from_error_code(e.code)
