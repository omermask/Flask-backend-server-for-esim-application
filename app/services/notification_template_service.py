from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.core.database import get_session
from app.core.errors import AppError, ErrorCode
from app.models.notification_template import NotificationTemplate

logger = logging.getLogger("esim-ego")


class NotificationTemplateService:

    @staticmethod
    def render_for_user(key: str, user_id: str, **data: Any) -> tuple[str, str] | None:
        lang = "en"
        try:
            from app.models.user import User
            with get_session() as session:
                user = session.query(User).filter(User.id == UUID(user_id)).first()
                if user and user.language:
                    lang = user.language
        except Exception:
            pass
        return NotificationTemplateService.render(key, lang, **data)

    @staticmethod
    def render(key: str, lang: str, **data: Any) -> tuple[str, str] | None:
        with get_session() as session:
            template = session.query(NotificationTemplate).filter(
                NotificationTemplate.key == key,
            ).first()
            if not template:
                return None
            text = template.translations.get(lang) or template.translations.get("en", "")
            if not text:
                return None
            try:
                rendered = text.format(**data)
            except (KeyError, ValueError):
                logger.warning("Failed to render template %s with lang %s", key, lang)
                return None
            title, body = rendered.split("\n", 1) if "\n" in rendered else (rendered, rendered)
            return title.strip(), body.strip()

    @staticmethod
    def get(key: str) -> dict | None:
        with get_session() as session:
            template = session.query(NotificationTemplate).filter(
                NotificationTemplate.key == key,
            ).first()
            if not template:
                return None
            return {
                "id": str(template.id),
                "key": template.key,
                "translations": template.translations,
                "data_schema": template.data_schema,
                "description": template.description,
            }

    @staticmethod
    def list() -> list[dict]:
        with get_session() as session:
            templates = session.query(NotificationTemplate).order_by(
                NotificationTemplate.key,
            ).all()
            return [
                {
                    "id": str(t.id),
                    "key": t.key,
                    "translations": list(t.translations.keys()),
                    "data_schema": t.data_schema,
                    "description": t.description,
                }
                for t in templates
            ]

    @staticmethod
    def upsert(
        key: str,
        translations: dict[str, str],
        data_schema: dict[str, Any] | None = None,
        description: str | None = None,
    ) -> dict:
        with get_session() as session:
            template = session.query(NotificationTemplate).filter(
                NotificationTemplate.key == key,
            ).first()
            if template:
                template.translations = translations
                if data_schema is not None:
                    template.data_schema = data_schema
                if description is not None:
                    template.description = description
            else:
                template = NotificationTemplate(
                    key=key,
                    translations=translations,
                    data_schema=data_schema,
                    description=description,
                )
                session.add(template)
            session.flush()
            return {
                "id": str(template.id),
                "key": template.key,
                "translations": template.translations,
                "data_schema": template.data_schema,
                "description": template.description,
            }

    @staticmethod
    def delete(key: str) -> bool:
        with get_session() as session:
            template = session.query(NotificationTemplate).filter(
                NotificationTemplate.key == key,
            ).first()
            if not template:
                return False
            session.delete(template)
            session.flush()
            return True
