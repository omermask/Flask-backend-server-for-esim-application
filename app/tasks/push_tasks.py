from __future__ import annotations

import logging

from celery.exceptions import MaxRetriesExceededError

from app.celery_app import celery_app
from app.services.push_service import cleanup_inactive_tokens, send_to_user

try:
    from app.socketio import emit_push_received
except Exception:
    def emit_push_received(*args, **kwargs):  # type: ignore
        pass

logger = logging.getLogger("esim-ego")


@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=5,
    acks_late=True,
)
def send_push_notification(
    self,
    user_id: str,
    title: str,
    body: str,
    data: dict | None = None,
) -> list[dict]:
    try:
        results = send_to_user(user_id, title, body, data)
        failed = [r for r in results if not r["success"]]
        if failed:
            logger.warning(
                "Push to user %s: %d/%d failed",
                user_id, len(failed), len(results),
            )
        try:
            emit_push_received(user_id, title, body, data)
        except Exception:
            pass
        return results
    except Exception as exc:
        logger.error("send_push_notification failed for user %s: %s", user_id, exc)
        try:
            raise self.retry(exc=exc)
        except MaxRetriesExceededError:
            logger.error("send_push_notification max retries exceeded for user %s", user_id)
            return []


@celery_app.task
def cleanup_device_tokens() -> int:
    try:
        deleted = cleanup_inactive_tokens()
        if deleted:
            logger.info("Cleaned %d inactive device tokens", deleted)
        return deleted
    except Exception as e:
        logger.error("cleanup_device_tokens failed: %s", e)
        return 0
