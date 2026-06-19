from __future__ import annotations

import logging
from uuid import UUID

from flask import Blueprint, Response as FlaskResponse, g, request
from sqlalchemy.orm import joinedload

from app.core.database import get_session
from app.core.middleware import require_auth
from app.core.response import UnifiedResponse
from app.core.errors import ErrorCode
from app.core.validators import PaginationParams, ProfileUpdateRequest
from app.models.order import Order
from app.services.user_service import UserService
from app.services.esim_service import EsimService
from app.services.invoice_service import InvoiceService
from app.services.audit_service import AuditService
from app.core.security import revoke_token
from app.services.order_service import OrderService
from app.services.support_service import SupportTicketService
from app.services.referral_service import ReferralService

logger = logging.getLogger("esim-ego")
user_routes = Blueprint("user", __name__, url_prefix="/api/v1/user")


@user_routes.route("/profile", methods=["GET"])
@require_auth()
def get_profile():
    profile = UserService.get_profile(user_id=g.user_id)
    return UnifiedResponse.success(data=profile)


@user_routes.route("/profile", methods=["PUT"])
@require_auth()
def update_profile():
    data = request.get_json(silent=True) or {}
    validator = ProfileUpdateRequest(**data)
    result = UserService.update_profile(
        user_id=g.user_id,
        name=validator.name,
        language=validator.language,
        timezone=validator.timezone,
    )
    return UnifiedResponse.success(data=result)


@user_routes.route("/profile", methods=["DELETE"])
@require_auth()
def delete_account():
    UserService.delete_account(user_id=g.user_id)
    revoke_token(getattr(g, "token_jti", ""))
    return UnifiedResponse.success(data={"message": "Account deleted successfully"})


@user_routes.route("/esims", methods=["GET"])
@require_auth()
def list_esims():
    pagination = PaginationParams(
        page=request.args.get("page", 1, type=int),
        limit=request.args.get("limit", 20, type=int),
    )
    result = EsimService.list_user_esims(
        user_id=g.user_id,
        page=pagination.page,
        limit=pagination.limit,
    )
    return UnifiedResponse.success(data=result)


@user_routes.route("/esims/<item_id>", methods=["GET"])
@require_auth()
def get_esim(item_id: str):
    result = EsimService.get_esim(user_id=g.user_id, item_id=item_id)
    return UnifiedResponse.success(data=result)


@user_routes.route("/esims/<item_id>/qr", methods=["GET"])
@require_auth()
def download_qr(item_id: str):
    return EsimService.download_qr(user_id=g.user_id, item_id=item_id)


@user_routes.route("/esims/<item_id>/renew", methods=["POST"])
@require_auth()
def renew_esim(item_id: str):
    result = EsimService.renew_esim(user_id=g.user_id, item_id=item_id)
    return UnifiedResponse.success(data=result)


@user_routes.route("/orders/<order_id>/invoice", methods=["GET"])
@require_auth()
def download_invoice(order_id: str):
    pdf_bytes = InvoiceService.generate_invoice(
        user_id=g.user_id, order_id=order_id,
    )
    return FlaskResponse(
        pdf_bytes,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="invoice_{order_id}.pdf"',
        },
    )


@user_routes.route("/activity", methods=["GET"])
@require_auth()
def list_activity():
    pagination = PaginationParams(
        page=request.args.get("page", 1, type=int),
        limit=request.args.get("limit", 20, type=int),
    )
    result = AuditService.list_activity(
        user_id=g.user_id,
        page=pagination.page,
        limit=pagination.limit,
    )
    return UnifiedResponse.success(data=result)


@user_routes.route("/orders/<order_id>/reorder", methods=["POST"])
@require_auth()
def reorder(order_id: str):
    try:
        oid = UUID(order_id)
    except (ValueError, AttributeError):
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_INVALID_UUID)
    with get_session() as session:
        order = (
            session.query(Order)
            .filter(Order.id == oid, Order.user_id == UUID(g.user_id))
            .options(joinedload(Order.plan))
            .first()
        )
        if not order:
            return UnifiedResponse.from_error_code(ErrorCode.ORDER_NOT_FOUND)
        plan_id = str(order.plan.id) if order.plan else ""
        if not plan_id:
            return UnifiedResponse.from_error_code(ErrorCode.PLAN_NOT_FOUND)
        quantity = order.quantity
    result = OrderService.create_order(
        user_id=g.user_id,
        plan_id=plan_id,
        quantity=quantity,
    )
    return UnifiedResponse.success(data=result)


@user_routes.route("/support/tickets", methods=["POST"])
@require_auth()
def create_ticket():
    data = request.get_json(silent=True) or {}
    result = SupportTicketService.create_ticket(
        user_id=g.user_id,
        subject=data.get("subject", ""),
        message=data.get("message", ""),
        priority=data.get("priority", "medium"),
    )
    return UnifiedResponse.success(data=result, status=201)


@user_routes.route("/support/tickets", methods=["GET"])
@require_auth()
def list_tickets():
    p = PaginationParams(
        page=request.args.get("page", 1, type=int),
        limit=request.args.get("limit", 20, type=int),
    )
    result = SupportTicketService.list_user_tickets(
        user_id=g.user_id, page=p.page, limit=p.limit,
    )
    return UnifiedResponse.success(data=result)


@user_routes.route("/support/tickets/<ticket_id>", methods=["GET"])
@require_auth()
def get_ticket(ticket_id: str):
    result = SupportTicketService.get_ticket(
        user_id=g.user_id, ticket_id=ticket_id,
    )
    return UnifiedResponse.success(data=result)


@user_routes.route("/support/tickets/<ticket_id>/messages", methods=["POST"])
@require_auth()
def add_ticket_message(ticket_id: str):
    data = request.get_json(silent=True) or {}
    result = SupportTicketService.add_message(
        user_id=g.user_id, ticket_id=ticket_id, message=data.get("message", ""),
    )
    return UnifiedResponse.success(data=result)


@user_routes.route("/support/tickets/<ticket_id>/close", methods=["POST"])
@require_auth()
def close_ticket(ticket_id: str):
    result = SupportTicketService.close_ticket(
        user_id=g.user_id, ticket_id=ticket_id,
    )
    return UnifiedResponse.success(data=result)


@user_routes.route("/referral/code", methods=["GET"])
@require_auth()
def get_referral_code():
    result = ReferralService.get_or_create_code(user_id=g.user_id)
    return UnifiedResponse.success(data=result)


@user_routes.route("/referral/code", methods=["POST"])
@require_auth()
def apply_referral_code():
    data = request.get_json(silent=True) or {}
    ReferralService.apply_referral(
        new_user_id=g.user_id, referral_code=data.get("code", ""),
    )
    return UnifiedResponse.success(data={"message": "Referral code applied"})


@user_routes.route("/referral/stats", methods=["GET"])
@require_auth()
def referral_stats():
    result = ReferralService.get_stats(user_id=g.user_id)
    return UnifiedResponse.success(data=result)


@user_routes.route("/referral/settings", methods=["GET"])
@require_auth()
def referral_settings():
    result = ReferralService.get_settings_for_user(user_id=g.user_id)
    return UnifiedResponse.success(data=result)
