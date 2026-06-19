from __future__ import annotations

import logging
from uuid import UUID

from app.core.database import get_session
from app.core.errors import AppError, ErrorCode
from app.models.user import User
from app.services.audit_service import AuditService

logger = logging.getLogger("esim-ego")


class UserService:

    @staticmethod
    def get_profile(user_id: str) -> dict:
        uid = UUID(user_id)
        with get_session() as session:
            user = session.query(User).filter(User.id == uid).first()
            if not user:
                raise AppError(ErrorCode.USER_NOT_FOUND)
            if not user.is_active:
                raise AppError(ErrorCode.USER_ACCOUNT_DELETED)
            return {
                "id": str(user.id),
                "phone": user.phone,
                "name": user.name,
                "language": user.language,
                "timezone": user.timezone,
                "role": user.role,
                "is_active": user.is_active,
                "is_verified": user.is_verified,
                "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
                "created_at": user.created_at.isoformat(),
            }

    @staticmethod
    def update_profile(
        user_id: str,
        name: str | None = None,
        language: str | None = None,
        timezone: str | None = None,
    ) -> dict:
        uid = UUID(user_id)
        changed_fields: list[str] = []
        with get_session() as session:
            user = session.query(User).filter(User.id == uid).first()
            if not user:
                raise AppError(ErrorCode.USER_NOT_FOUND)
            if not user.is_active:
                raise AppError(ErrorCode.USER_ACCOUNT_DELETED)
            if name is not None and name != user.name:
                changed_fields.append("name")
                user.name = name
            if language is not None and language != user.language:
                changed_fields.append("language")
                user.language = language
            if timezone is not None and timezone != user.timezone:
                changed_fields.append("timezone")
                user.timezone = timezone
            session.flush()
            result = {
                "id": str(user.id),
                "name": user.name,
                "language": user.language,
                "timezone": user.timezone,
            }
        if changed_fields:
            AuditService.log(
                user_id=user_id,
                action="profile.updated",
                resource_type="user",
                resource_id=result["id"],
                details={"changed_fields": changed_fields},
            )
        return result

    @staticmethod
    def delete_account(user_id: str) -> None:
        uid = UUID(user_id)
        with get_session() as session:
            user = session.query(User).filter(User.id == uid).first()
            if not user:
                raise AppError(ErrorCode.USER_NOT_FOUND)
            if not user.is_active:
                raise AppError(ErrorCode.USER_ACCOUNT_DELETED)
            user.is_active = False
            user.phone = f"del_{user.id.hex[:10]}"
            user.name = "Deleted User"
            audit_uid = str(user.id)
            session.flush()
        AuditService.log(
            user_id=user_id,
            action="account.deleted",
            resource_type="user",
            resource_id=audit_uid,
            ip_address="",
            user_agent="",
        )
