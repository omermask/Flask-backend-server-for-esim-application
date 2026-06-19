from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any

from config import settings


class TranslationManager:
    _instance: TranslationManager | None = None
    _lock: Lock = Lock()
    _read_lock: Lock = Lock()
    _translations: dict[str, dict[str, str]] = {}
    _loaded: bool = False

    def __new__(cls) -> TranslationManager:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def _load_translations(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            translations_dir = Path(__file__).resolve().parent.parent / "translations"
            if not translations_dir.exists():
                self._loaded = True
                return
            for file_path in translations_dir.glob("*.json"):
                lang = file_path.stem
                if lang not in settings.SUPPORTED_LANGUAGES_LIST:
                    continue
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        self._translations[lang] = {
                            k: str(v) for k, v in data.items()
                        }
                except (json.JSONDecodeError, IOError):
                    continue
            self._loaded = True

    def get_message(
        self, code: str, lang: str | None = None
    ) -> str | dict[str, str]:
        self._load_translations()
        with self._read_lock:
            if lang and lang in self._translations:
                msg = self._translations[lang].get(code, "")
                if msg:
                    return msg
            default_msg = self._translations.get(
                settings.DEFAULT_LANGUAGE, {}
            ).get(code, "")
            if default_msg:
                return default_msg
            all_messages: dict[str, str] = {}
            for lng, msgs in self._translations.items():
                msg = msgs.get(code, "")
                if msg:
                    all_messages[lng] = msg
            if not all_messages:
                all_messages = {settings.DEFAULT_LANGUAGE: code}
            return all_messages

    def get_all_languages_message(self, code: str) -> dict[str, str]:
        self._load_translations()
        with self._read_lock:
            result: dict[str, str] = {}
            for lang in settings.SUPPORTED_LANGUAGES_LIST:
                if lang in self._translations:
                    msg = self._translations[lang].get(code, "")
                    if msg:
                        result[lang] = msg
            if not result:
                result[settings.DEFAULT_LANGUAGE] = code
            return result

    def reload(self) -> None:
        with self._lock:
            with self._read_lock:
                self._loaded = False
                self._translations.clear()
                self._load_translations()


translation_manager = TranslationManager()
