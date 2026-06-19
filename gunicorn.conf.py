from __future__ import annotations

from config import settings

bind = f"{settings.FLASK_HOST}:{settings.FLASK_PORT}"
workers = settings.FLASK_WORKERS
worker_class = "gevent"
timeout = 30
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = settings.LOG_LEVEL.lower()
server_header = False


def on_exit(server):
    from app.core.database import get_engine
    try:
        get_engine().dispose()
    except Exception:
        pass
    from app.core.security import close_redis
    try:
        close_redis()
    except Exception:
        pass
