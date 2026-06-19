from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any

from flask import g, jsonify

__all__ = ["UnifiedResponse"]

from app.core.constants import get_server_tz, ERROR_ID_LENGTH
from app.core.errors import AppError, ErrorCode
from app.core.i18n import translation_manager


class UnifiedResponse:
    _request_id: str = ""
    _error_id: str = ""

    @classmethod
    def _generate_error_id(cls) -> str:
        return "err_" + secrets.token_hex(ERROR_ID_LENGTH // 2)

    @classmethod
    def _get_meta(cls, error_id: str = "") -> dict[str, Any]:
        request_id = getattr(g, "request_id", "")
        now = datetime.now(get_server_tz())
        meta: dict[str, Any] = {
            "request_id": request_id,
            "timestamp": now.isoformat(),
            "timezone": str(get_server_tz()),
            "api_version": "v1",
        }
        if error_id:
            meta["error_id"] = error_id
        return meta

    @classmethod
    def success(
        cls,
        data: Any = None,
        code: str = "",
        status: int = 200,
    ) -> tuple:
        code = code or ErrorCode.SUCCESS.value
        lang = getattr(g, "lang", "")
        raw = translation_manager.get_message(code, lang)
        if isinstance(raw, dict):
            raw = raw.get(lang, code)
        meta = cls._get_meta()
        body: dict[str, Any] = {
            "success": True,
            "status": status,
            "code": code,
            "message": raw,
            "data": data if data is not None else {},
            "meta": meta,
        }
        return jsonify(body), status

    @classmethod
    def error(
        cls,
        app_error: AppError,
        lang: str | None = None,
    ) -> tuple:
        error_id = cls._generate_error_id()
        meta = cls._get_meta(error_id=error_id)
        message = translation_manager.get_all_languages_message(app_error.code.value)
        if isinstance(message, str):
            message = {lang or "en": message}
        body: dict[str, Any] = {
            "success": False,
            "status": app_error.status,
            "code": app_error.code.value,
            "message": message,
            "data": app_error.data if app_error.data is not None else {},
            "meta": meta,
        }
        return jsonify(body), app_error.status

    @classmethod
    def from_error_code(
        cls,
        code: ErrorCode,
        data: Any = None,
        status: int | None = None,
        lang: str | None = None,
    ) -> tuple:
        app_error = AppError(code=code, data=data, status=status)
        return cls.error(app_error, lang)
