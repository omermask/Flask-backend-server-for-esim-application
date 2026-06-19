from __future__ import annotations

import mimetypes

from flask import Blueprint, Response as FlaskResponse, g, request, send_file

from app.core.middleware import require_auth
from app.core.response import UnifiedResponse
from app.core.errors import AppError, ErrorCode
from app.core.validators import PaginationParams
from app.services.backup_service import BackupService
from app.services.audit_service import AuditService

admin_backup_routes = Blueprint(
    "admin_backup", __name__, url_prefix="/api/v1/admin/backup",
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


@admin_backup_routes.route("/create", methods=["POST"])
@require_auth(roles=["admin", "superadmin"])
def create_backup():
    result = BackupService.create_backup(admin_id=_get_admin_id())
    AuditService.log(
        user_id=_get_admin_id(),
        action="admin.create_backup",
        resource_type="backup",
        details={"success": result.get("success")},
        ip_address=_get_client_ip(),
        user_agent=_get_user_agent(),
    )
    if not result.get("success"):
        return UnifiedResponse.from_error_code(ErrorCode.INTERNAL_ERROR, data=result)
    return UnifiedResponse.success(data=result)


@admin_backup_routes.route("/list", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def list_backups():
    pagination = PaginationParams(
        page=request.args.get("page", 1, type=int),
        limit=request.args.get("limit", 20, type=int),
    )
    result = BackupService.list_backups(page=pagination.page, limit=pagination.limit)
    return UnifiedResponse.success(data=result)


@admin_backup_routes.route("/<backup_id>", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def get_backup(backup_id: str):
    try:
        result = BackupService.get_backup(backup_id)
        return UnifiedResponse.success(data=result)
    except AppError as exc:
        return UnifiedResponse.from_error_code(exc.code)


@admin_backup_routes.route("/<backup_id>/download", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def download_backup(backup_id: str):
    try:
        filepath, filename, _ = BackupService.get_backup_path(backup_id)
    except AppError as exc:
        return UnifiedResponse.from_error_code(exc.code)
    mimetype, _ = mimetypes.guess_type(filename)
    response = send_file(
        filepath,
        mimetype=mimetype or "application/octet-stream",
        as_attachment=True,
        download_name=filename,
    )
    AuditService.log(
        user_id=_get_admin_id(),
        action="admin.download_backup",
        resource_type="backup",
        resource_id=backup_id,
        details={"filename": filename},
        ip_address=_get_client_ip(),
        user_agent=_get_user_agent(),
    )
    return response


@admin_backup_routes.route("/<backup_id>", methods=["DELETE"])
@require_auth(roles=["admin", "superadmin"])
def delete_backup(backup_id: str):
    try:
        result = BackupService.delete_backup(backup_id)
    except AppError as exc:
        return UnifiedResponse.from_error_code(exc.code)
    AuditService.log(
        user_id=_get_admin_id(),
        action="admin.delete_backup",
        resource_type="backup",
        resource_id=backup_id,
        ip_address=_get_client_ip(),
        user_agent=_get_user_agent(),
    )
    return UnifiedResponse.success(data=result)


@admin_backup_routes.route("/settings", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def get_settings():
    result = BackupService.get_settings()
    fs = BackupService.get_filesystem_info()
    result["filesystem"] = fs
    return UnifiedResponse.success(data=result)


@admin_backup_routes.route("/settings/<key>", methods=["PUT"])
@require_auth(roles=["admin", "superadmin"])
def update_setting(key: str):
    data = request.get_json(silent=True) or {}
    value = data.get("value", "")
    if not value:
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_MISSING_FIELD)
    try:
        result = BackupService.update_setting(key=key, value=value)
    except AppError as exc:
        return UnifiedResponse.from_error_code(exc.code)
    AuditService.log(
        user_id=_get_admin_id(),
        action="admin.update_backup_setting",
        resource_type="backup_setting",
        resource_id=key,
        details={"key": key},
        ip_address=_get_client_ip(),
        user_agent=_get_user_agent(),
    )
    return UnifiedResponse.success(data=result)


@admin_backup_routes.route("/cleanup", methods=["POST"])
@require_auth(roles=["admin", "superadmin"])
def run_cleanup():
    count = BackupService.cleanup_old()
    AuditService.log(
        user_id=_get_admin_id(),
        action="admin.run_backup_cleanup",
        resource_type="backup",
        details={"deleted_count": count},
        ip_address=_get_client_ip(),
        user_agent=_get_user_agent(),
    )
    return UnifiedResponse.success(data={"deleted": count})
