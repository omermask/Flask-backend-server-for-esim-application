from __future__ import annotations

import datetime
import logging
from datetime import timezone

from app.celery_app import celery_app
from app.core.database import get_session
from app.models.backup import BackupRecord
from app.services.backup_service import BackupService

logger = logging.getLogger("esim-ego")


@celery_app.task(
    bind=True,
    max_retries=1,
    default_retry_delay=60,
    acks_late=True,
)
def run_scheduled_backup(self) -> dict:
    try:
        cfg = BackupService.get_settings()
        if not cfg["enabled"]:
            return {"success": False, "reason": "backup_disabled"}
        interval_hours = cfg.get("interval_hours", 24)
        cutoff = datetime.datetime.now(timezone.utc) - datetime.timedelta(hours=interval_hours)
        with get_session() as session:
            last = session.query(BackupRecord).filter(
                BackupRecord.backup_type == "scheduled",
                BackupRecord.status == "completed",
            ).order_by(BackupRecord.created_at.desc()).first()
            if last and last.created_at > cutoff:
                return {"success": True, "reason": "skipped - too soon"}
        logger.info("Starting scheduled backup (interval: %dh)", interval_hours)
        result = BackupService.create_backup(admin_id="", backup_type="scheduled")
        try:
            BackupService.cleanup_old(cfg)
        except Exception:
            pass
        if result.get("success"):
            logger.info("Scheduled backup completed: %s", result.get("filename"))
        else:
            logger.warning("Scheduled backup failed: %s", result.get("error"))
        return result
    except Exception as exc:
        logger.error("Scheduled backup error: %s", exc)
        try:
            raise self.retry(exc=exc)
        except Exception:
            return {"success": False, "error": str(exc)}
