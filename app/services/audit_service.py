from __future__ import annotations

import logging
from uuid import UUID

from app.core.database import get_session
from app.models.audit import AuditLog

logger = logging.getLogger("esim-ego")


class AuditService:

    @staticmethod
    def log(
        user_id: str,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        details: dict | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        uid = UUID(user_id)
        with get_session() as session:
            record = AuditLog(
                user_id=uid,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            session.add(record)
            session.flush()

    @staticmethod
    def list_activity(
        user_id: str, page: int = 1, limit: int = 20
    ) -> dict:
        uid = UUID(user_id)
        with get_session() as session:
            query = session.query(AuditLog).filter(AuditLog.user_id == uid)
            total = query.count()
            offset = (page - 1) * limit
            items = (
                query
                .order_by(AuditLog.created_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return {
                "items": [
                    {
                        "id": str(item.id),
                        "action": item.action,
                        "resource_type": item.resource_type,
                        "resource_id": item.resource_id,
                        "details": item.details,
                        "ip_address": item.ip_address,
                        "created_at": item.created_at.isoformat(),
                    }
                    for item in items
                ],
                "total": total,
                "page": page,
                "limit": limit,
            }
