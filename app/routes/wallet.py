from __future__ import annotations

import logging

from flask import Blueprint, g, request

from app.core.middleware import require_auth
from app.core.response import UnifiedResponse
from app.core.errors import ErrorCode
from app.core.validators import PaginationParams, DepositRequest
from app.services.wallet_service import WalletService
from app.services.payment_service import PaymentService

logger = logging.getLogger("esim-ego")
wallet_routes = Blueprint("wallet", __name__, url_prefix="/api/v1/wallet")


@wallet_routes.route("", methods=["GET"])
@require_auth()
def get_wallet():
    wallet = WalletService.get_wallet(user_id=g.user_id)
    return UnifiedResponse.success(data=wallet)


@wallet_routes.route("/transactions", methods=["GET"])
@require_auth()
def list_transactions():
    pagination = PaginationParams(
        page=request.args.get("page", 1, type=int),
        limit=request.args.get("limit", 20, type=int),
    )
    result = WalletService.get_transactions(
        user_id=g.user_id,
        page=pagination.page,
        limit=pagination.limit,
    )
    return UnifiedResponse.success(data=result)


@wallet_routes.route("/deposit", methods=["POST"])
@require_auth()
def deposit():
    data = request.get_json(silent=True) or {}
    validator = DepositRequest(**data)
    payment = PaymentService.initiate_deposit(
        user_id=g.user_id,
        amount=validator.amount,
        payment_method=validator.payment_method,
        idempotency_key=validator.idempotency_key,
    )
    return UnifiedResponse.success(data=payment)
