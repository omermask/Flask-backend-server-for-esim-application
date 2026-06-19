from __future__ import annotations

import datetime
import logging
import os
import secrets
import shlex
import subprocess
import time
from datetime import timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from app.core.database import get_session
from app.core.errors import AppError, ErrorCode
from app.models.backup import BackupRecord
from app.models.setting import SystemSetting
from config import settings

logger = logging.getLogger("esim-ego")

BACKUP_SETTING_KEYS = frozenset({
    "backup_enabled",
    "backup_interval_hours",
    "backup_retention_days",
    "backup_path",
    "backup_encrypt",
})

DEFAULT_BACKUP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backups")
BACKUP_TIMEOUT = 600


class BackupService:

    @staticmethod
    def get_settings() -> dict[str, Any]:
        keys = list(BACKUP_SETTING_KEYS)
        with get_session() as session:
            rows = session.query(SystemSetting).filter(
                SystemSetting.key.in_(keys),
            ).all()
            m: dict[str, str] = {r.key: r.value for r in rows}
        return {
            "enabled": m.get("backup_enabled", "false").lower() == "true",
            "interval_hours": int(m.get("backup_interval_hours", "24")),
            "retention_days": int(m.get("backup_retention_days", "30")),
            "path": m.get("backup_path", DEFAULT_BACKUP_DIR),
            "encrypt": m.get("backup_encrypt", "false").lower() == "true",
        }

    @staticmethod
    def update_setting(key: str, value: str) -> dict[str, Any]:
        full_key = key if key.startswith("backup_") else f"backup_{key}"
        if full_key not in BACKUP_SETTING_KEYS:
            raise AppError(ErrorCode.VALIDATION_INVALID_PARAMETER)
        if full_key == "backup_interval_hours":
            try:
                v = int(value)
                if v < 1 or v > 720:
                    raise ValueError
            except (ValueError, TypeError):
                raise AppError(ErrorCode.VALIDATION_INVALID_PARAMETER)
        if full_key == "backup_retention_days":
            try:
                v = int(value)
                if v < 1 or v > 365:
                    raise ValueError
            except (ValueError, TypeError):
                raise AppError(ErrorCode.VALIDATION_INVALID_PARAMETER)
        if full_key == "backup_path":
            sanitized = BackupService._sanitize_path(value)
            if not sanitized:
                raise AppError(ErrorCode.VALIDATION_INVALID_PARAMETER)
            value = sanitized
        with get_session() as session:
            setting = session.query(SystemSetting).filter(
                SystemSetting.key == full_key,
            ).first()
            if setting:
                setting.value = value
            else:
                setting = SystemSetting(key=full_key, value=value)
                session.add(setting)
            session.flush()
        return {key: value}

    @staticmethod
    def create_backup(admin_id: str, backup_type: str = "manual") -> dict[str, Any]:
        cfg = BackupService.get_settings()
        if backup_type == "scheduled" and not cfg["enabled"]:
            return {"success": False, "reason": "backup_disabled"}
        backup_dir = cfg["path"]
        try:
            Path(backup_dir).mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error("Cannot create backup dir %s: %s", backup_dir, e)
            raise AppError(ErrorCode.INTERNAL_ERROR)
        ts = datetime.datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
        safe_type = "manual" if backup_type != "scheduled" else "scheduled"
        token = secrets.token_hex(4)
        filename = f"esim_ego_{ts}_{safe_type}_{token}.dump"
        filepath = os.path.join(backup_dir, filename)
        filepath = os.path.normpath(filepath)

        record = BackupRecord(
            filename=filename,
            filepath=filepath,
            status="running",
            backup_type=safe_type,
            created_by=admin_id if admin_id else None,
        )
        with get_session() as session:
            session.add(record)
            session.flush()
            record_id = str(record.id)

        start = time.monotonic()
        try:
            env = os.environ.copy()
            env["PGPASSWORD"] = settings.DB_PASSWORD
            args = [
                "pg_dump",
                "--host", settings.DB_HOST,
                "--port", str(settings.DB_PORT),
                "--username", settings.DB_USER,
                "--dbname", settings.DB_NAME,
                "--format", "custom",
                "--file", filepath,
            ]
            result = subprocess.run(
                args, env=env, capture_output=True, text=True,
                timeout=BACKUP_TIMEOUT,
            )
            if result.returncode != 0:
                err_msg = result.stderr[:500] if result.stderr else "pg_dump failed"
                BackupService._update_record(record_id, "failed", notes=err_msg, file_size=0)
                logger.error("Backup %s failed: %s", record_id, err_msg)
                BackupService._cleanup_file(filepath)
                return {"success": False, "error": err_msg}
            try:
                file_size = os.path.getsize(filepath)
            except OSError:
                file_size = 0
            elapsed = time.monotonic() - start
            BackupService._update_record(
                record_id, "completed", file_size=file_size,
                notes=f"Completed in {elapsed:.1f}s",
            )
            BackupService._cleanup_old(cfg)
            logger.info("Backup %s completed: %s (%d bytes in %.1fs)", record_id, filename, file_size, elapsed)
            return {
                "success": True,
                "id": record_id,
                "filename": filename,
                "file_size": file_size,
                "elapsed_seconds": round(elapsed, 1),
            }
        except subprocess.TimeoutExpired:
            BackupService._update_record(record_id, "failed", notes="Timeout expired")
            BackupService._cleanup_file(filepath)
            logger.error("Backup %s timed out", record_id)
            return {"success": False, "error": "timeout"}
        except FileNotFoundError:
            BackupService._update_record(record_id, "failed", notes="pg_dump not found")
            logger.error("pg_dump binary not found on system")
            return {"success": False, "error": "pg_dump not found"}
        except Exception as exc:
            BackupService._update_record(record_id, "failed", notes=str(exc)[:500])
            BackupService._cleanup_file(filepath)
            logger.error("Backup %s error: %s", record_id, exc)
            return {"success": False, "error": str(exc)[:200]}

    @staticmethod
    def list_backups(page: int = 1, limit: int = 20) -> dict[str, Any]:
        with get_session() as session:
            query = session.query(BackupRecord).order_by(
                BackupRecord.created_at.desc(),
            )
            total = query.count()
            offset = (page - 1) * limit
            records = query.offset(offset).limit(limit).all()
            return {
                "items": [
                    BackupService._format_record(r) for r in records
                ],
                "total": total,
                "page": page,
                "limit": limit,
            }

    @staticmethod
    def get_backup(backup_id: str) -> dict[str, Any]:
        try:
            bid = UUID(backup_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        with get_session() as session:
            record = session.query(BackupRecord).filter(
                BackupRecord.id == bid,
            ).first()
            if not record:
                raise AppError(ErrorCode.NOT_FOUND)
            return BackupService._format_record(record)

    @staticmethod
    def get_backup_path(backup_id: str) -> tuple[str, str, str]:
        try:
            bid = UUID(backup_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        with get_session() as session:
            record = session.query(BackupRecord).filter(
                BackupRecord.id == bid,
            ).first()
            if not record:
                raise AppError(ErrorCode.NOT_FOUND)
            if record.status != "completed":
                raise AppError(ErrorCode.INVALID_STATE)
            filepath = os.path.normpath(record.filepath)
            cfg = BackupService.get_settings()
            backup_dir = os.path.normpath(cfg["path"])
            if not filepath.startswith(backup_dir):
                logger.warning("Path traversal attempt: %s", filepath)
                raise AppError(ErrorCode.AUTH_FORBIDDEN)
            if not os.path.isfile(filepath):
                raise AppError(ErrorCode.NOT_FOUND)
            return filepath, record.filename, str(record.id)

    @staticmethod
    def delete_backup(backup_id: str) -> dict[str, Any]:
        try:
            bid = UUID(backup_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        with get_session() as session:
            record = session.query(BackupRecord).filter(
                BackupRecord.id == bid,
            ).first()
            if not record:
                raise AppError(ErrorCode.NOT_FOUND)
            filepath = os.path.normpath(record.filepath)
            cfg = BackupService.get_settings()
            backup_dir = os.path.normpath(cfg["path"])
            if filepath.startswith(backup_dir):
                BackupService._cleanup_file(filepath)
            session.delete(record)
            session.flush()
            return {"success": True}

    @staticmethod
    def cleanup_old(cfg: dict[str, Any] | None = None) -> int:
        if cfg is None:
            cfg = BackupService.get_settings()
        retention_days = cfg.get("retention_days", 30)
        cutoff = datetime.datetime.now(timezone.utc) - datetime.timedelta(days=retention_days)
        with get_session() as session:
            old = session.query(BackupRecord).filter(
                BackupRecord.created_at < cutoff,
                BackupRecord.status == "completed",
            ).all()
            count = 0
            for r in old:
                fpath = os.path.normpath(r.filepath)
                backup_dir = os.path.normpath(cfg["path"])
                if fpath.startswith(backup_dir):
                    BackupService._cleanup_file(fpath)
                session.delete(r)
                count += 1
            if count:
                session.flush()
                logger.info("Cleaned %d old backups (retention: %d days)", count, retention_days)
            return count

    @staticmethod
    def get_filesystem_info() -> dict[str, Any]:
        cfg = BackupService.get_settings()
        backup_dir = cfg["path"]
        try:
            Path(backup_dir).mkdir(parents=True, exist_ok=True)
            stat = os.statvfs(backup_dir)
            free_bytes = stat.f_frsize * stat.f_bavail
            total_bytes = stat.f_frsize * stat.f_blocks
            used_bytes = total_bytes - free_bytes
            return {
                "path": backup_dir,
                "total_bytes": total_bytes,
                "used_bytes": used_bytes,
                "free_bytes": free_bytes,
                "free_human": BackupService._human_size(free_bytes),
                "usage_percent": round(used_bytes / total_bytes * 100, 1) if total_bytes else 0,
            }
        except OSError:
            return {"path": backup_dir, "error": "unreachable"}

    # ── Internal ──────────────────────────────────────────────────────

    @staticmethod
    def _update_record(
        record_id: str, status: str,
        file_size: int | None = None,
        notes: str | None = None,
    ) -> None:
        try:
            rid = UUID(record_id)
        except (ValueError, AttributeError):
            return
        with get_session() as session:
            record = session.query(BackupRecord).filter(
                BackupRecord.id == rid,
            ).first()
            if not record:
                return
            record.status = status
            if file_size is not None:
                record.file_size = file_size
            if notes:
                record.notes = notes
            if status in ("completed", "failed"):
                record.completed_at = datetime.datetime.now(timezone.utc)
            session.flush()

    @staticmethod
    def _cleanup_file(filepath: str) -> None:
        try:
            norm = os.path.normpath(filepath)
            if os.path.isfile(norm):
                os.remove(norm)
        except OSError:
            pass

    @staticmethod
    def _cleanup_old(cfg: dict[str, Any]) -> None:
        try:
            BackupService.cleanup_old(cfg)
        except Exception as e:
            logger.warning("Backup cleanup failed: %s", e)

    @staticmethod
    def _format_record(r: BackupRecord) -> dict[str, Any]:
        return {
            "id": str(r.id),
            "filename": r.filename,
            "file_size": r.file_size,
            "file_size_human": BackupService._human_size(r.file_size) if r.file_size else None,
            "status": r.status,
            "backup_type": r.backup_type,
            "created_by": {
                "id": str(r.creator.id),
                "name": r.creator.name,
            } if r.creator else None,
            "notes": r.notes,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "created_at": r.created_at.isoformat(),
        }

    @staticmethod
    def _sanitize_path(user_path: str) -> str | None:
        if not user_path or not user_path.strip():
            return None
        clean = os.path.normpath(user_path.strip())
        if clean.startswith("/proc") or clean.startswith("/sys") or clean.startswith("/dev"):
            return None
        return clean

    @staticmethod
    def _human_size(bytes_val: int) -> str:
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if bytes_val < 1024:
                return f"{bytes_val:.1f} {unit}"
            bytes_val /= 1024
        return f"{bytes_val:.1f} PB"
