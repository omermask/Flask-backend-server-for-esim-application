from __future__ import annotations

import logging
import secrets
import threading
from datetime import datetime, timezone, timedelta
from typing import Any

import jwt
import pyotp
import redis as redis_lib
from bcrypt import checkpw, gensalt, hashpw

from config import settings

__all__ = [
    "hash_password", "verify_password", "generate_otp",
    "create_access_token", "create_refresh_token", "decode_token",
    "revoke_token", "is_token_revoked", "validate_token_type",
    "generate_idempotency_key",
    "generate_totp_secret", "get_totp_uri", "verify_totp",
    "close_redis", "mask_phone",
    "get_user_token_version", "increment_user_token_version",
]

logger = logging.getLogger("esim-ego")

ALGORITHM: str = "HS256"

_redis_lock: threading.Lock = threading.Lock()
_redis_available: bool = False
_redis_client: redis_lib.Redis | None = None
_in_memory_blacklist: set[str] = set()


def _get_redis() -> redis_lib.Redis | None:
    global _redis_client, _redis_available
    if _redis_client is None:
        with _redis_lock:
            if _redis_client is not None:
                return _redis_client
            try:
                _redis_client = redis_lib.Redis.from_url(
                    settings.REDIS_URL,
                    decode_responses=True,
                    socket_connect_timeout=2,
                    health_check_interval=30,
                )
                _redis_client.ping()
                _redis_available = True
                logger.info("Redis connected for token blacklist")
            except redis_lib.ConnectionError:
                _redis_available = False
                logger.warning("Redis unavailable — token blacklist limited to in-memory (per-worker only)")
    return _redis_client


def _blacklist_key(jti: str) -> str:
    return f"revoked_token:{jti}"


def revoke_token(jti: str, expiry_seconds: int = 900) -> None:
    r = _get_redis()
    if r is not None:
        try:
            r.setex(_blacklist_key(jti), expiry_seconds, "1")
        except redis_lib.RedisError:
            logger.error("Failed to revoke token in Redis | jti=%s", jti)
    _in_memory_blacklist.add(jti)


def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        try:
            _redis_client.close()
        except redis_lib.RedisError:
            pass
        _redis_client = None


def is_token_revoked(jti: str) -> bool:
    if not jti:
        return False
    if jti in _in_memory_blacklist:
        return True
    r = _get_redis()
    if r is not None:
        try:
            if r.exists(_blacklist_key(jti)):
                _in_memory_blacklist.add(jti)
                return True
        except redis_lib.RedisError:
            logger.error("Failed to check token revocation in Redis | jti=%s", jti)
    return False


def hash_password(password: str) -> str:
    return hashpw(password.encode("utf-8"), gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def generate_otp(length: int = 6) -> str:
    first = str(secrets.randbelow(9) + 1)
    rest = "".join(str(secrets.randbelow(10)) for _ in range(length - 1))
    return first + rest


def create_access_token(
    user_id: str,
    role: str,
    secret_key: str,
    expiry_minutes: int = 15,
    totp_enabled: bool = False,
    totp_verified: bool = False,
    token_version: int = 0,
) -> str:
    now = datetime.now(timezone.utc)
    jti = secrets.token_hex(16)
    payload: dict[str, Any] = {
        "sub": user_id,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expiry_minutes)).timestamp()),
        "type": "access",
        "jti": jti,
        "totp_enabled": totp_enabled,
        "totp_verified": totp_verified,
        "token_version": token_version,
    }
    return jwt.encode(payload, secret_key, algorithm=ALGORITHM)


def create_refresh_token(
    user_id: str,
    role: str,
    secret_key: str,
    expiry_days: int = 7,
    totp_enabled: bool = False,
    totp_verified: bool = False,
    token_version: int = 0,
) -> str:
    now = datetime.now(timezone.utc)
    jti = secrets.token_hex(16)
    payload: dict[str, Any] = {
        "sub": user_id,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=expiry_days)).timestamp()),
        "type": "refresh",
        "jti": jti,
        "totp_enabled": totp_enabled,
        "totp_verified": totp_verified,
        "token_version": token_version,
    }
    return jwt.encode(payload, secret_key, algorithm=ALGORITHM)


def decode_token(token: str, secret_key: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[ALGORITHM],
            options={"require": ["sub", "exp", "iat", "type", "jti"]},
            leeway=30,
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise
    except jwt.InvalidTokenError:
        raise
    except jwt.PyJWTError:
        raise jwt.InvalidTokenError("Unexpected JWT error")


def validate_token_type(payload: dict[str, Any], expected_type: str) -> None:
    token_type = payload.get("type", "")
    if token_type != expected_type:
        raise jwt.InvalidTokenError("Invalid token type")


def generate_idempotency_key() -> str:
    return secrets.token_hex(32)


def mask_phone(phone: str) -> str:
    if len(phone) > 7:
        return phone[:7] + "XXXX"
    return "XXXX"


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def get_totp_uri(secret: str, user_email: str, issuer_name: str | None = None) -> str:
    issuer = issuer_name or settings.TOTP_ISSUER_NAME
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=user_email, issuer_name=issuer)


def verify_totp(secret: str, code: str) -> bool:
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


def _user_token_version_key(user_id: str) -> str:
    return f"user_token_version:{user_id}"


def get_user_token_version(user_id: str) -> int:
    r = _get_redis()
    if r is not None:
        try:
            val = r.get(_user_token_version_key(user_id))
            if val is not None:
                return int(val)
        except redis_lib.RedisError:
            logger.error("Failed to get token version from Redis | user=%s", user_id)
    from app.models.device_session import DeviceSession
    try:
        from app.core.database import get_session
        with get_session() as session:
            ds = session.query(DeviceSession).filter(
                DeviceSession.user_id == user_id,
                DeviceSession.is_active == True,
            ).first()
            return ds.token_version if ds else 0
    except Exception:
        return 0


def increment_user_token_version(user_id: str) -> int:
    r = _get_redis()
    if r is not None:
        try:
            new_ver = r.incr(_user_token_version_key(user_id))
            return int(new_ver)
        except redis_lib.RedisError:
            logger.error("Failed to increment token version in Redis | user=%s", user_id)
    return 0
