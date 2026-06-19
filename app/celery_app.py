from __future__ import annotations

import logging

from celery import Celery
from celery.signals import worker_process_init

from config import settings

logger = logging.getLogger("esim-ego")

celery_app = Celery(
    "esim_ego",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=30,
    task_time_limit=60,
    beat_schedule={
        "backup-every-hour": {
            "task": "app.tasks.backup_tasks.run_scheduled_backup",
            "schedule": 3600.0,
            "options": {"expires": 3000},
        },
        "cleanup-device-tokens-daily": {
            "task": "app.tasks.push_tasks.cleanup_device_tokens",
            "schedule": 86400.0,
            "options": {"expires": 43200},
        },
    },
)


import app.tasks.backup_tasks  # noqa: F401 — register celery tasks
import app.tasks.push_tasks  # noqa: F401
import app.tasks.sms_tasks  # noqa: F401


@worker_process_init.connect
def init_worker(**kwargs) -> None:
    import app.models  # noqa: F401
    from app.core.database import get_engine
    try:
        with get_engine().connect() as conn:
            conn.execute(conn.default_schema_name)  # no-op to verify connection
    except Exception:
        pass
