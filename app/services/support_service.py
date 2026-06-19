from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.core.database import get_session
from app.core.errors import AppError, ErrorCode
from app.models.support import SupportMessage, SupportTicket
from app.models.user import User

logger = logging.getLogger("esim-ego")


class SupportTicketService:

    @staticmethod
    def create_ticket(user_id: str, subject: str, message: str, priority: str = "medium") -> dict[str, Any]:
        if not subject or not subject.strip():
            raise AppError(ErrorCode.VALIDATION_MISSING_FIELD)
        if not message or not message.strip():
            raise AppError(ErrorCode.SUPPORT_MESSAGE_EMPTY)
        valid_priorities = {"low", "medium", "high", "urgent"}
        if priority not in valid_priorities:
            priority = "medium"
        with get_session() as session:
            user = session.query(User).filter(User.id == UUID(user_id)).first()
            if not user:
                raise AppError(ErrorCode.USER_NOT_FOUND)
            ticket = SupportTicket(
                user_id=user_id,
                subject=subject.strip()[:200],
                priority=priority,
            )
            session.add(ticket)
            session.flush()
            msg = SupportMessage(
                ticket_id=str(ticket.id),
                user_id=user_id,
                message=message.strip(),
            )
            session.add(msg)
            session.flush()
            return {
                "id": str(ticket.id),
                "subject": ticket.subject,
                "priority": ticket.priority,
                "status": ticket.status,
                "created_at": ticket.created_at.isoformat(),
            }

    @staticmethod
    def list_user_tickets(user_id: str, page: int = 1, limit: int = 20) -> dict[str, Any]:
        with get_session() as session:
            query = session.query(SupportTicket).filter(
                SupportTicket.user_id == user_id,
            ).order_by(SupportTicket.created_at.desc())
            total = query.count()
            offset = (page - 1) * limit
            tickets = query.offset(offset).limit(limit).all()
            return {
                "items": [
                    {
                        "id": str(t.id),
                        "subject": t.subject,
                        "status": t.status,
                        "priority": t.priority,
                        "message_count": len(t.messages),
                        "assigned_to": str(t.assigned_to.name) if t.assigned_to else None,
                        "created_at": t.created_at.isoformat(),
                        "updated_at": t.updated_at.isoformat(),
                        "closed_at": t.closed_at.isoformat() if t.closed_at else None,
                    }
                    for t in tickets
                ],
                "total": total,
                "page": page,
                "limit": limit,
            }

    @staticmethod
    def get_ticket(user_id: str, ticket_id: str) -> dict[str, Any]:
        try:
            tid = UUID(ticket_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        with get_session() as session:
            ticket = session.query(SupportTicket).filter(
                SupportTicket.id == tid,
            ).first()
            if not ticket:
                raise AppError(ErrorCode.SUPPORT_TICKET_NOT_FOUND)
            if str(ticket.user_id) != user_id:
                raise AppError(ErrorCode.SUPPORT_TICKET_ACCESS_DENIED)
            return {
                "id": str(ticket.id),
                "subject": ticket.subject,
                "status": ticket.status,
                "priority": ticket.priority,
                "assigned_to": {
                    "id": str(ticket.assigned_to.id),
                    "name": ticket.assigned_to.name,
                } if ticket.assigned_to else None,
                "messages": [
                    {
                        "id": str(m.id),
                        "message": m.message,
                        "sender": "user" if m.user_id else "admin",
                        "sender_name": m.ticket.user.name if m.user_id else (m.ticket.assigned_to.name if m.ticket.assigned_to else "Support"),
                        "created_at": m.created_at.isoformat(),
                    }
                    for m in ticket.messages
                ],
                "created_at": ticket.created_at.isoformat(),
                "updated_at": ticket.updated_at.isoformat(),
                "closed_at": ticket.closed_at.isoformat() if ticket.closed_at else None,
            }

    @staticmethod
    def add_message(user_id: str, ticket_id: str, message: str) -> dict[str, Any]:
        if not message or not message.strip():
            raise AppError(ErrorCode.SUPPORT_MESSAGE_EMPTY)
        try:
            tid = UUID(ticket_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        with get_session() as session:
            ticket = session.query(SupportTicket).filter(
                SupportTicket.id == tid,
            ).first()
            if not ticket:
                raise AppError(ErrorCode.SUPPORT_TICKET_NOT_FOUND)
            if str(ticket.user_id) != user_id:
                raise AppError(ErrorCode.SUPPORT_TICKET_ACCESS_DENIED)
            if ticket.status == "closed":
                raise AppError(ErrorCode.SUPPORT_TICKET_CLOSED)
            if ticket.status == "resolved":
                ticket.status = "open"
            msg = SupportMessage(
                ticket_id=ticket_id,
                user_id=user_id,
                message=message.strip(),
            )
            session.add(msg)
            session.flush()
            return {
                "id": str(msg.id),
                "message": msg.message,
                "created_at": msg.created_at.isoformat(),
            }

    @staticmethod
    def close_ticket(user_id: str, ticket_id: str) -> dict[str, Any]:
        try:
            tid = UUID(ticket_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        with get_session() as session:
            ticket = session.query(SupportTicket).filter(
                SupportTicket.id == tid,
            ).first()
            if not ticket:
                raise AppError(ErrorCode.SUPPORT_TICKET_NOT_FOUND)
            if str(ticket.user_id) != user_id:
                raise AppError(ErrorCode.SUPPORT_TICKET_ACCESS_DENIED)
            if ticket.status == "closed":
                raise AppError(ErrorCode.SUPPORT_TICKET_CLOSED)
            ticket.status = "closed"
            ticket.closed_at = datetime.now(timezone.utc)
            session.flush()
            return {"id": str(ticket.id), "status": "closed"}

    @staticmethod
    def admin_list_tickets(
        page: int = 1, limit: int = 20,
        status: str | None = None,
        priority: str | None = None,
    ) -> dict[str, Any]:
        with get_session() as session:
            query = session.query(SupportTicket)
            if status:
                query = query.filter(SupportTicket.status == status)
            if priority:
                query = query.filter(SupportTicket.priority == priority)
            query = query.order_by(SupportTicket.created_at.desc())
            total = query.count()
            offset = (page - 1) * limit
            tickets = query.offset(offset).limit(limit).all()
            return {
                "items": [
                    {
                        "id": str(t.id),
                        "user": {
                            "id": str(t.user.id),
                            "name": t.user.name,
                            "phone": t.user.phone,
                        } if t.user else None,
                        "subject": t.subject,
                        "status": t.status,
                        "priority": t.priority,
                        "message_count": len(t.messages),
                        "assigned_to": {
                            "id": str(t.assigned_to.id),
                            "name": t.assigned_to.name,
                        } if t.assigned_to else None,
                        "created_at": t.created_at.isoformat(),
                        "updated_at": t.updated_at.isoformat(),
                    }
                    for t in tickets
                ],
                "total": total,
                "page": page,
                "limit": limit,
            }

    @staticmethod
    def admin_get_ticket(ticket_id: str) -> dict[str, Any]:
        try:
            tid = UUID(ticket_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        with get_session() as session:
            ticket = session.query(SupportTicket).filter(
                SupportTicket.id == tid,
            ).first()
            if not ticket:
                raise AppError(ErrorCode.SUPPORT_TICKET_NOT_FOUND)
            return {
                "id": str(ticket.id),
                "user": {
                    "id": str(ticket.user.id),
                    "name": ticket.user.name,
                    "phone": ticket.user.phone,
                } if ticket.user else None,
                "subject": ticket.subject,
                "status": ticket.status,
                "priority": ticket.priority,
                "assigned_to": {
                    "id": str(ticket.assigned_to.id),
                    "name": ticket.assigned_to.name,
                } if ticket.assigned_to else None,
                "messages": [
                    {
                        "id": str(m.id),
                        "message": m.message,
                        "sender": "user" if m.user_id else "admin",
                        "sender_name": (
                            m.ticket.user.name if m.user_id
                            else (m.ticket.assigned_to.name if m.ticket.assigned_to else "Support")
                        ),
                        "created_at": m.created_at.isoformat(),
                    }
                    for m in ticket.messages
                ],
                "created_at": ticket.created_at.isoformat(),
                "updated_at": ticket.updated_at.isoformat(),
                "closed_at": ticket.closed_at.isoformat() if ticket.closed_at else None,
            }

    @staticmethod
    def admin_reply(admin_id: str, ticket_id: str, message: str) -> dict[str, Any]:
        if not message or not message.strip():
            raise AppError(ErrorCode.SUPPORT_MESSAGE_EMPTY)
        try:
            tid = UUID(ticket_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        with get_session() as session:
            ticket = session.query(SupportTicket).filter(
                SupportTicket.id == tid,
            ).first()
            if not ticket:
                raise AppError(ErrorCode.SUPPORT_TICKET_NOT_FOUND)
            if ticket.status == "closed":
                raise AppError(ErrorCode.SUPPORT_TICKET_CLOSED)
            msg = SupportMessage(
                ticket_id=ticket_id,
                admin_id=admin_id,
                message=message.strip(),
            )
            session.add(msg)
            session.flush()
            return {
                "id": str(msg.id),
                "message": msg.message,
                "created_at": msg.created_at.isoformat(),
            }

    @staticmethod
    def admin_update_status(ticket_id: str, status: str) -> dict[str, Any]:
        valid_statuses = {"open", "pending", "resolved", "closed"}
        if status not in valid_statuses:
            raise AppError(ErrorCode.VALIDATION_INVALID_PARAMETER)
        try:
            tid = UUID(ticket_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        with get_session() as session:
            ticket = session.query(SupportTicket).filter(
                SupportTicket.id == tid,
            ).first()
            if not ticket:
                raise AppError(ErrorCode.SUPPORT_TICKET_NOT_FOUND)
            ticket.status = status
            if status == "closed":
                ticket.closed_at = datetime.now(timezone.utc)
            elif status == "open" and ticket.closed_at:
                ticket.closed_at = None
            session.flush()
            return {"id": str(ticket.id), "status": ticket.status}

    @staticmethod
    def admin_assign(ticket_id: str, assigned_to_id: str) -> dict[str, Any]:
        try:
            tid = UUID(ticket_id)
            aid = UUID(assigned_to_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        with get_session() as session:
            ticket = session.query(SupportTicket).filter(
                SupportTicket.id == tid,
            ).first()
            if not ticket:
                raise AppError(ErrorCode.SUPPORT_TICKET_NOT_FOUND)
            admin = session.query(User).filter(
                User.id == aid, User.role.in_(["admin", "superadmin"]),
            ).first()
            if not admin:
                raise AppError(ErrorCode.USER_NOT_FOUND)
            ticket.assigned_to_id = assigned_to_id
            session.flush()
            return {
                "id": str(ticket.id),
                "assigned_to": {"id": str(admin.id), "name": admin.name},
            }
