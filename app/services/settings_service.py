from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

import requests

from app.core.database import get_session
from app.core.errors import AppError, ErrorCode
from app.models.setting import SystemSetting

logger = logging.getLogger("esim-ego")

SETTING_KEYS = {
    "official_currency": "IQD",
    "timezone": "Asia/Baghdad",
    "auto_fetch_interval": "manual",
}


class SettingsService:

    @staticmethod
    def get(key: str, default: str = "") -> str:
        with get_session() as session:
            setting = (
                session.query(SystemSetting)
                .filter(SystemSetting.key == key)
                .first()
            )
            if setting:
                return setting.value
            return default or SETTING_KEYS.get(key, "")

    @staticmethod
    def get_all() -> dict[str, str]:
        result = {}
        with get_session() as session:
            rows = (
                session.query(SystemSetting)
                .filter(SystemSetting.key.in_(list(SETTING_KEYS.keys())))
                .all()
            )
            for r in rows:
                result[r.key] = r.value
        for k, v in SETTING_KEYS.items():
            result.setdefault(k, v)
        return result

    @staticmethod
    def get_official_currency() -> str:
        return SettingsService.get("official_currency", "IQD")

    @staticmethod
    def get_timezone() -> str:
        return SettingsService.get("timezone", "Asia/Baghdad")

    @staticmethod
    def get_auto_fetch_interval() -> str:
        return SettingsService.get("auto_fetch_interval", "manual")
