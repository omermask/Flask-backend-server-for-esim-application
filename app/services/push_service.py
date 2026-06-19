from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any
from uuid import UUID

import requests

from app.core.database import get_session
from app.models.device_token import DeviceToken
from config import settings

logger = logging.getLogger("esim-ego")

_SCOPES = ["https://www.googleapis.com/auth/firebase.messaging"]
_MAX_TITLE_LENGTH = 256
_MAX_BODY_LENGTH = 1024
_MAX_TOKEN_LENGTH = 512

_credentials: Any = None
_fcm_project_id: str = ""
_fcm_lock: Lock = Lock()
_fcm_available: bool = False
_google_auth_available: bool = False

try:
    from google.auth.transport.requests import Request as GoogleRequest
    from google.oauth2 import service_account
    _google_auth_available = True
except ImportError:
    logger.warning("google-auth not installed — push notifications disabled")


def _ensure_fcm_init() -> bool:
    global _credentials, _fcm_project_id, _fcm_available
    if not _google_auth_available:
        return False
    if _fcm_available:
        return True
    with _fcm_lock:
        if _fcm_available:
            return True
        fcm_json = settings.FCM_SERVICE_ACCOUNT_JSON
        if not fcm_json:
            logger.info("FCM_SERVICE_ACCOUNT_JSON not set — push disabled")
            return False
        try:
            cred_info = json.loads(fcm_json)
            _fcm_project_id = cred_info.get("project_id", "")
            if not _fcm_project_id:
                logger.error("FCM service account missing project_id")
                return False
            _credentials = service_account.Credentials.from_service_account_info(
                cred_info, scopes=_SCOPES,
            )
            _fcm_available = True
            logger.info("FCM initialized for project %s", _fcm_project_id)
            return True
        except Exception as e:
            logger.error("FCM init failed: %s", e)
            return False


def _get_access_token() -> str:
    if _credentials is None or not _fcm_available:
        raise RuntimeError("FCM not initialized")
    if not _credentials.valid:
        _credentials.refresh(GoogleRequest(timeout=10))
    return _credentials.token


def _send_fcm_message(message: dict) -> dict:
    if not _ensure_fcm_init():
        return {"success": False, "error": "fcm_not_configured"}
    try:
        token = _get_access_token()
        url = f"https://fcm.googleapis.com/v1/projects/{_fcm_project_id}/messages:send"
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json={"message": message},
            timeout=10,
        )
        if resp.status_code == 200:
            return {"success": True, "name": resp.json().get("name", "")}
        error_body = resp.json()
        error_status = error_body.get("error", {}).get("status", "UNKNOWN")
        logger.warning("FCM error %d: %s", resp.status_code, error_status)
        return {
            "success": False,
            "error": error_status,
            "status_code": resp.status_code,
        }
    except requests.Timeout:
        logger.warning("FCM request timed out")
        return {"success": False, "error": "TIMEOUT"}
    except Exception as e:
        logger.error("FCM send failed: %s", e)
        return {"success": False, "error": "INTERNAL"}


def _mask_token(token: str) -> str:
    if len(token) > 8:
        return token[:4] + "****" + token[-4:]
    return "****"


def register_device(user_id: str, token: str, platform: str) -> dict:
    platform = platform.lower()
    if platform not in ("ios", "android"):
        return {"success": False, "error": "invalid_platform"}
    if not token or len(token) < 16 or len(token) > _MAX_TOKEN_LENGTH:
        return {"success": False, "error": "invalid_token"}
    uid = UUID(user_id)
    with get_session() as session:
        try:
            existing = session.query(DeviceToken).filter(
                DeviceToken.token == token,
            ).first()
            if existing:
                if str(existing.user_id) != user_id:
                    existing.user_id = uid
                existing.is_active = True
                existing.platform = platform
                session.flush()
                logger.debug("Device token re-registered for user %s", _mask_token(token))
                return {"success": True, "message": "token_updated"}
            device = DeviceToken(
                user_id=uid,
                token=token,
                platform=platform,
                is_active=True,
            )
            session.add(device)
            session.flush()
            logger.debug("Device token registered for user %s", _mask_token(token))
            return {"success": True, "message": "token_registered"}
        except Exception:
            logger.warning("Duplicate token registration failed for %s", _mask_token(token))
            return {"success": True, "message": "token_updated"}


def unregister_device(user_id: str, token: str) -> dict:
    if not token or len(token) > _MAX_TOKEN_LENGTH:
        return {"success": False, "error": "invalid_token"}
    uid = UUID(user_id)
    with get_session() as session:
        record = session.query(DeviceToken).filter(
            DeviceToken.token == token,
            DeviceToken.user_id == uid,
        ).first()
        if record:
            record.is_active = False
            logger.debug("Device token deactivated for user %s", _mask_token(token))
        return {"success": True, "message": "token_unregistered"}


def get_active_tokens(user_id: str) -> list[dict]:
    uid = UUID(user_id)
    with get_session() as session:
        records = session.query(DeviceToken).filter(
            DeviceToken.user_id == uid,
            DeviceToken.is_active == True,
        ).all()
        return [
            {
                "id": r.id,
                "user_id": r.user_id,
                "token": r.token,
                "platform": r.platform,
                "is_active": r.is_active,
                "last_notified_at": r.last_notified_at,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }
            for r in records
        ]


def get_all_active_tokens() -> list[dict]:
    with get_session() as session:
        records = session.query(DeviceToken).filter(
            DeviceToken.is_active == True,
        ).all()
        return [
            {
                "id": r.id,
                "user_id": r.user_id,
                "token": r.token,
                "platform": r.platform,
                "is_active": r.is_active,
                "last_notified_at": r.last_notified_at,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }
            for r in records
        ]


def send_to_user(user_id: str, title: str, body: str, data: dict | None = None) -> list[dict]:
    tokens = get_active_tokens(user_id)
    if not tokens:
        return []
    title = title[:_MAX_TITLE_LENGTH]
    body = body[:_MAX_BODY_LENGTH]
    results = []
    for device in tokens:
        message = _build_message(device["token"], title, body, data)
        result = _send_fcm_message(message)
        if not result["success"]:
            error = result.get("error", "")
            if error in ("UNREGISTERED", "NOT_FOUND"):
                _mark_token_inactive(device["id"])
        else:
            _update_last_notified(device["id"])
        results.append({
            "token_id": str(device["id"]),
            "platform": device["platform"],
            "success": result["success"],
            "error": result.get("error"),
        })
    return results


def send_to_all(title: str, body: str, data: dict | None = None) -> list[dict]:
    tokens = get_all_active_tokens()
    if not tokens:
        return []
    title = title[:_MAX_TITLE_LENGTH]
    body = body[:_MAX_BODY_LENGTH]
    results = []
    for device in tokens:
        message = _build_message(device["token"], title, body, data)
        result = _send_fcm_message(message)
        if not result["success"]:
            error = result.get("error", "")
            if error in ("UNREGISTERED", "NOT_FOUND"):
                _mark_token_inactive(device["id"])
        else:
            _update_last_notified(device["id"])
        results.append({
            "token_id": str(device["id"]),
            "user_id": str(device["user_id"]),
            "platform": device["platform"],
            "success": result["success"],
            "error": result.get("error"),
        })
    return results


def _build_message(token: str, title: str, body: str, data: dict | None = None) -> dict:
    message: dict[str, Any] = {
        "token": token,
        "notification": {
            "title": title,
            "body": body,
        },
        "android": {
            "priority": "high",
            "notification": {
                "channel_id": "default",
                "priority": "high",
                "sound": "default",
                "click_action": "FLUTTER_NOTIFICATION_CLICK",
            },
        },
        "apns": {
            "payload": {
                "aps": {
                    "alert": {
                        "title": title,
                        "body": body,
                    },
                    "sound": "default",
                    "badge": 1,
                    "contentAvailable": True,
                },
            },
            "headers": {
                "apns-priority": "10",
            },
        },
    }
    if data:
        message["data"] = {k: str(v) for k, v in data.items()}
    return message


def _mark_token_inactive(token_id: UUID) -> None:
    try:
        with get_session() as session:
            record = session.query(DeviceToken).filter(
                DeviceToken.id == token_id,
            ).first()
            if record:
                record.is_active = False
    except Exception as e:
        logger.error("Failed to mark token inactive: %s", e)


def _update_last_notified(token_id: UUID) -> None:
    try:
        with get_session() as session:
            record = session.query(DeviceToken).filter(
                DeviceToken.id == token_id,
            ).first()
            if record:
                record.last_notified_at = datetime.now(timezone.utc)
    except Exception as e:
        logger.error("Failed to update last_notified: %s", e)


def cleanup_inactive_tokens(days: int = 30) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    with get_session() as session:
        deleted = session.query(DeviceToken).filter(
            DeviceToken.is_active == False,
            DeviceToken.updated_at < cutoff,
        ).delete()
        session.flush()
        if deleted:
            logger.info("Cleaned %d inactive device tokens", deleted)
        return deleted
