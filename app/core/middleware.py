from __future__ import annotations

import ipaddress
import logging
import secrets
from datetime import datetime
from typing import Any, Callable

import jwt as pyjwt
from flask import Flask, Response, g, jsonify, request
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import HTTPException

from app.core.constants import get_server_tz, BODY_SIZE_LIMIT, REQUEST_ID_LENGTH
from app.core.errors import AppError, ErrorCode
from app.core.i18n import translation_manager
from app.core.response import UnifiedResponse
from app.core.security import decode_token, is_token_revoked, validate_token_type

logger = logging.getLogger("esim-ego")


def get_language_from_request() -> str:
    from config import settings
    lang = request.headers.get("Accept-Language", settings.DEFAULT_LANGUAGE)
    if lang and "," in lang:
        lang = lang.split(",")[0]
    if lang and "-" in lang:
        lang = lang.split("-")[0]
    if lang not in settings.SUPPORTED_LANGUAGES_LIST:
        lang = settings.DEFAULT_LANGUAGE
    return lang


def parse_pydantic_errors(err: PydanticValidationError) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for e in err.errors():
        field = ".".join(str(loc) for loc in e.get("loc", []))
        msg = e.get("msg", "")
        errors.append({"field": field, "message": msg})
    return errors


def _is_ip_whitelisted(ip: str) -> bool:
    allowed = _get_admin_ip_whitelist()
    if not allowed:
        return True
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for cidr in allowed:
        try:
            net = ipaddress.ip_network(cidr, strict=False)
            if addr in net:
                return True
        except ValueError:
            continue
    return False


def _get_admin_ip_whitelist() -> list[str]:
    from config import settings
    return settings.ADMIN_IP_WHITELIST_LIST


def _get_client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or ""


def register_middleware(app: Flask) -> None:
    @app.before_request
    def before_request_middleware() -> Response | None:
        g.start_time = datetime.now(get_server_tz())
        g.request_id = "req_" + secrets.token_hex(REQUEST_ID_LENGTH // 2)
        g.lang = get_language_from_request()

        body_size = request.content_length or 0
        if body_size > BODY_SIZE_LIMIT:
            return UnifiedResponse.from_error_code(
                ErrorCode.VALIDATION_BODY_TOO_LARGE,
                status=413,
                lang=g.lang,
            )

        if request.method in {"POST", "PUT", "PATCH"}:
            content_type = request.content_type or ""
            if body_size > 0 and "application/json" not in content_type:
                return UnifiedResponse.from_error_code(
                    ErrorCode.VALIDATION_INVALID_CONTENT_TYPE,
                    status=415,
                    lang=g.lang,
                )

        if request.path.startswith("/api/v1/admin/"):
            whitelist = _get_admin_ip_whitelist()
            if whitelist:
                ip = _get_client_ip()
                if not ip or not _is_ip_whitelisted(ip):
                    return UnifiedResponse.from_error_code(
                        ErrorCode.AUTH_FORBIDDEN, lang=g.lang,
                    )

        return None

    @app.after_request
    def after_request_middleware(response: Response) -> Response:
        start_time = getattr(g, "start_time", None)
        if start_time:
            elapsed = (datetime.now(get_server_tz()) - start_time).total_seconds()
            response.headers["X-Request-Id"] = getattr(g, "request_id", "")
            response.headers["X-Response-Time-Ms"] = str(round(elapsed * 1000, 2))
            response.headers["X-API-Version"] = "v1"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        if request.headers.get("Origin"):
            response.headers.add("Vary", "Origin")
        if "Server" in response.headers:
            del response.headers["Server"]
        return response

    def register_error_handlers(app: Flask) -> None:
        @app.errorhandler(AppError)
        def handle_app_error(error: AppError) -> tuple:
            lang = getattr(g, "lang", "en")
            if error.code in {
                ErrorCode.INTERNAL_ERROR,
                ErrorCode.DATABASE_ERROR,
                ErrorCode.PROVIDER_UNAVAILABLE,
                ErrorCode.PROVIDER_TIMEOUT,
                ErrorCode.PROVIDER_INVALID_RESPONSE,
            }:
                error_id = "err_" + secrets.token_hex(8)
                logger.error(
                    "Internal error | error_id=%s | code=%s | path=%s | method=%s",
                    error_id, error.code.value, request.path, request.method,
                    exc_info=True,
                )
                error.data = {"error_id": error_id}
            return UnifiedResponse.error(error, lang)

        @app.errorhandler(PydanticValidationError)
        def handle_pydantic_error(err: PydanticValidationError) -> tuple:
            lang = getattr(g, "lang", "en")
            error_id = "err_" + secrets.token_hex(8)
            logger.info(
                "Validation error | error_id=%s | path=%s | method=%s",
                error_id, request.path, request.method,
            )
            parsed = parse_pydantic_errors(err)
            app_error = AppError(
                code=ErrorCode.VALIDATION_INVALID_PARAMETER,
                data={"error_id": error_id, "details": parsed},
                status=422,
            )
            return UnifiedResponse.error(app_error, lang)

        @app.errorhandler(HTTPException)
        def handle_http_error(http_error: HTTPException) -> tuple:
            lang = getattr(g, "lang", "en")
            if http_error.code == 404:
                code = ErrorCode.NOT_FOUND
            elif http_error.code == 405:
                code = ErrorCode.METHOD_NOT_ALLOWED
            elif http_error.code == 429:
                code = ErrorCode.RATE_LIMIT_EXCEEDED
            elif http_error.code == 413:
                code = ErrorCode.VALIDATION_BODY_TOO_LARGE
            else:
                code = ErrorCode.INTERNAL_ERROR
            return UnifiedResponse.from_error_code(
                code, status=http_error.code, lang=lang
            )

        @app.errorhandler(IntegrityError)
        def handle_integrity_error(error: IntegrityError) -> tuple:
            lang = getattr(g, "lang", "en")
            logger.warning(
                "Integrity constraint violation | path=%s | method=%s",
                request.path, request.method,
            )
            return UnifiedResponse.from_error_code(
                ErrorCode.DATABASE_INTEGRITY_ERROR, lang=lang
            )

        @app.errorhandler(Exception)
        def handle_unexpected_error(error: Exception) -> tuple:
            error_id = "err_" + secrets.token_hex(8)
            logger.critical(
                "Unhandled exception | error_id=%s | path=%s | method=%s",
                error_id, request.path, request.method,
                exc_info=True,
            )
            msg = translation_manager.get_all_languages_message(
                ErrorCode.INTERNAL_ERROR.value
            )
            body = {
                "success": False,
                "status": 500,
                "code": ErrorCode.INTERNAL_ERROR.value,
                "message": msg,
                "data": {"error_id": error_id},
                "meta": {
                    "request_id": getattr(g, "request_id", ""),
                    "error_id": error_id,
                    "timestamp": datetime.now(get_server_tz()).isoformat(),
                    "timezone": str(get_server_tz()),
                    "api_version": "v1",
                },
            }
            return jsonify(body), 500

    register_error_handlers(app)


def require_auth(roles: list[str] | None = None, require_totp: bool = True) -> Callable:
    def decorator(f: Callable) -> Callable:
        from functools import wraps

        @wraps(f)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            from flask import current_app

            lang = getattr(g, "lang", "en")
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return UnifiedResponse.from_error_code(
                    ErrorCode.AUTH_UNAUTHORIZED, lang=lang
                )
            token = auth_header[7:]
            try:
                payload = decode_token(token, current_app.config["SECRET_KEY"])
            except pyjwt.ExpiredSignatureError:
                return UnifiedResponse.from_error_code(
                    ErrorCode.AUTH_TOKEN_EXPIRED, lang=lang
                )
            except pyjwt.InvalidTokenError:
                return UnifiedResponse.from_error_code(
                    ErrorCode.AUTH_INVALID_TOKEN, lang=lang
                )
            token_jti = payload.get("jti", "")
            if is_token_revoked(token_jti):
                return UnifiedResponse.from_error_code(
                    ErrorCode.AUTH_TOKEN_REVOKED, lang=lang
                )
            try:
                validate_token_type(payload, "access")
            except pyjwt.InvalidTokenError:
                return UnifiedResponse.from_error_code(
                    ErrorCode.AUTH_INVALID_TOKEN, lang=lang
                )
            g.user_id = payload["sub"]
            g.user_role = payload.get("role", "")
            g.token_jti = payload.get("jti", "")
            g.totp_verified = payload.get("totp_verified", False)
            if roles and payload.get("role") not in roles:
                return UnifiedResponse.from_error_code(
                    ErrorCode.AUTH_FORBIDDEN, lang=lang
                )
            if require_totp and payload.get("totp_enabled") and not payload.get("totp_verified"):
                return UnifiedResponse.from_error_code(
                    ErrorCode.AUTH_2FA_REQUIRED, lang=lang
                )
            token_version = payload.get("token_version", 0)
            if token_version > 0:
                from app.core.security import get_user_token_version
                current_version = get_user_token_version(payload["sub"])
                if current_version > token_version:
                    return UnifiedResponse.from_error_code(
                        ErrorCode.AUTH_DEVICE_SESSION_EXPIRED, lang=lang
                    )
            return f(*args, **kwargs)

        return wrapper

    return decorator
