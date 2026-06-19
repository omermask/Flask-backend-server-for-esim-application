from __future__ import annotations

import atexit
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_limiter import Limiter
from sqlalchemy import text

from config import settings


def get_client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _health_check_db() -> dict:
    from app.core.database import get_engine
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as e:
        if settings.IS_PRODUCTION:
            return {"status": "error", "detail": "database unreachable"}
        return {"status": "error", "detail": str(e)}


def _health_check_redis() -> dict:
    try:
        import redis as redis_lib
        r = redis_lib.Redis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=3,
            decode_responses=True,
        )
        r.ping()
        r.close()
        return {"status": "ok"}
    except Exception as e:
        if settings.IS_PRODUCTION:
            return {"status": "error", "detail": "redis unreachable"}
        return {"status": "error", "detail": str(e)}


def _health_check_providers() -> dict:
    from app.providers.registry import ProviderRegistry
    configured_sms = settings.SMS_PROVIDER
    configured_esim = settings.ESIM_PROVIDER
    configured_payments = settings.PAYMENT_PROVIDERS_LIST
    return {
        "sms": {
            "configured": bool(configured_sms),
            "provider": configured_sms or None,
            "available": configured_sms in ProviderRegistry.available_sms() if configured_sms else False,
        },
        "esim": {
            "configured": bool(configured_esim),
            "provider": configured_esim or None,
            "available": configured_esim in ProviderRegistry.available_esim() if configured_esim else False,
        },
        "payment": {
            "configured": configured_payments,
            "available": ProviderRegistry.available_payments(),
        },
    }


def _cleanup_idempotency() -> None:
    try:
        from app.core.database import get_session
        from app.models.idempotency import IdempotencyRecord
        with get_session() as session:
            deleted = IdempotencyRecord.clean_expired(session)
            if deleted:
                logger = logging.getLogger("esim-ego")
                logger.info("Cleaned %d expired idempotency records", deleted)
    except Exception:
        pass


def _init_auto_fetch() -> None:
    import threading
    try:
        from app.services.settings_service import SettingsService
        interval = SettingsService.get_auto_fetch_interval()
    except Exception:
        interval = "manual"
    if interval == "manual":
        return
    if interval == "hourly":
        delay = 3600
    elif interval == "every_6_hours":
        delay = 21600
    elif interval == "daily":
        delay = 86400
    else:
        return

    from app.services.currency_service import CurrencyService

    def _auto_fetch_loop():
        import time
        while True:
            try:
                CurrencyService.auto_fetch_rates()
            except Exception:
                pass
            time.sleep(delay)

    t = threading.Thread(target=_auto_fetch_loop, daemon=True)
    t.start()


def _close_resources() -> None:
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


def create_app() -> Flask:
    app = Flask(__name__)

    app.config["SECRET_KEY"] = settings.SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = 1_048_576
    app.config["JSON_AS_ASCII"] = False
    app.config["JSONIFY_PRETTYPRINT_REGULAR"] = settings.IS_DEVELOPMENT

    _configure_logging()
    _register_extensions(app)
    _register_middleware(app)
    _register_limiter(app)
    _register_blueprints(app)

    _init_socketio(app)

    _cleanup_idempotency()

    _init_auto_fetch()

    @app.route("/socket.io/health")
    def socket_health():
        return jsonify({"status": "ok"})

    @app.route("/health")
    def health():
        db = _health_check_db()
        redis = _health_check_redis()
        providers = _health_check_providers()
        critical_ok = db["status"] == "ok"
        overall = "ok" if critical_ok else "degraded"
        return jsonify({
            "status": overall,
            "components": {
                "database": db,
                "redis": redis,
                "providers": providers,
            },
        }), (200 if critical_ok else 503)

    atexit.register(_close_resources)

    return app


def _configure_logging() -> None:
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.WARNING)
    log_dir = Path(settings.LOG_FILE).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )

    file_handler = RotatingFileHandler(
        settings.LOG_FILE,
        maxBytes=settings.LOG_MAX_BYTES,
        backupCount=settings.LOG_BACKUP_COUNT,
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)

    root_logger = logging.getLogger("esim-ego")
    root_logger.setLevel(log_level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def _register_extensions(app: Flask) -> None:
    origins = settings.CORS_ORIGINS_LIST
    has_wildcard = "*" in origins
    CORS(
        app,
        origins=origins,
        supports_credentials=not has_wildcard,
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type", "Authorization", "Accept-Language", "Idempotency-Key", "X-API-KEY",
        ],
        expose_headers=[
            "X-Request-Id", "X-Response-Time-Ms", "X-API-Version",
        ],
    )


def _register_middleware(app: Flask) -> None:
    from app.core.middleware import register_middleware
    register_middleware(app)


_limiter: Limiter | None = None


def _register_limiter(app: Flask) -> None:
    global _limiter
    logger = logging.getLogger("esim-ego")
    try:
        _limiter = Limiter(
            app=app,
            key_func=get_client_ip,
            storage_uri=settings.REDIS_URL,
            storage_options={"socket_connect_timeout": 3},
            strategy="fixed-window",
            default_limits=[f"{settings.RATE_LIMIT_API_PER_MINUTE}/minute"],
        )
        app.config["RATELIMIT_ENABLED"] = True
    except Exception:
        logger.warning("Redis unavailable — rate limiting falls back to in-memory")
        try:
            _limiter = Limiter(
                app=app,
                key_func=get_client_ip,
                storage_uri="memory://",
                strategy="fixed-window",
                default_limits=[f"{settings.RATE_LIMIT_API_PER_MINUTE}/minute"],
            )
            app.config["RATELIMIT_ENABLED"] = True
        except Exception:
            logger.critical("Rate limiter failed completely")
            if settings.IS_PRODUCTION:
                import sys
                sys.exit(1)
            app.config["RATELIMIT_ENABLED"] = False


def get_limiter() -> Limiter | None:
    return _limiter


def _init_socketio(app: Flask) -> None:
    from app.socketio import init_socketio as _init_ws
    try:
        _init_ws(app)
    except Exception:
        logger = logging.getLogger("esim-ego")
        logger.warning("SocketIO initialization failed — WebSocket will be unavailable")


def _register_blueprints(app: Flask) -> None:
    from app.routes.auth import auth_routes
    from app.routes.plans import plan_routes, admin_plan_routes
    from app.routes.orders import order_routes
    from app.routes.wallet import wallet_routes
    from app.routes.payments import payment_routes
    from app.routes.admin import admin_routes
    from app.routes.admin_finance import admin_finance_routes
    from app.routes.admin_inventory import admin_inventory_routes
    from app.routes.admin_analytics import admin_analytics_routes
    from app.routes.admin_backup import admin_backup_routes
    from app.routes.admin_control import admin_control_routes
    from app.routes.admin_support import admin_support_routes
    from app.routes.admin_referral import admin_referral_routes
    from app.routes.esim_callback import esim_callback_routes
    from app.routes.otpiq_callback import otpiq_callback_routes
    from app.routes.user import user_routes
    from app.routes.push import push_routes
    app.register_blueprint(push_routes)
    app.register_blueprint(auth_routes)
    app.register_blueprint(plan_routes)
    app.register_blueprint(admin_plan_routes)
    app.register_blueprint(order_routes)
    app.register_blueprint(wallet_routes)
    app.register_blueprint(payment_routes)
    app.register_blueprint(admin_control_routes)
    app.register_blueprint(admin_support_routes)
    app.register_blueprint(admin_referral_routes)
    app.register_blueprint(admin_routes)
    app.register_blueprint(admin_finance_routes)
    app.register_blueprint(admin_inventory_routes)
    app.register_blueprint(admin_analytics_routes)
    app.register_blueprint(admin_backup_routes)
    app.register_blueprint(user_routes)
    app.register_blueprint(esim_callback_routes)
    app.register_blueprint(otpiq_callback_routes)
