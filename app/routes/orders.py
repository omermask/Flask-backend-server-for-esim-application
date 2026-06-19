from __future__ import annotations

import logging

from flask import Blueprint, g, request

from app.core.middleware import require_auth
from app.core.response import UnifiedResponse
from app.core.errors import ErrorCode
from app.core.validators import PaginationParams, CreateOrderRequest
from app.services.order_service import OrderService

logger = logging.getLogger("esim-ego")
order_routes = Blueprint("orders", __name__, url_prefix="/api/v1/orders")


@order_routes.route("", methods=["POST"])
@require_auth()
def create_order():
    data = request.get_json(silent=True) or {}
    validator = CreateOrderRequest(**data)
    result = OrderService.create_order(
        user_id=g.user_id,
        plan_id=validator.plan_id,
        quantity=validator.quantity,
        idempotency_key=validator.idempotency_key,
        coupon_code=validator.coupon_code,
    )
    return UnifiedResponse.success(data=result, status=201)


@order_routes.route("", methods=["GET"])
@require_auth()
def list_orders():
    pagination = PaginationParams(
        page=request.args.get("page", 1, type=int),
        limit=request.args.get("limit", 20, type=int),
    )
    result = OrderService.list_user_orders(
        user_id=g.user_id,
        page=pagination.page,
        limit=pagination.limit,
    )
    return UnifiedResponse.success(data=result)


@order_routes.route("/<order_id>", methods=["GET"])
@require_auth()
def get_order(order_id: str):
    result = OrderService.get_order(
        user_id=g.user_id,
        order_id=order_id,
    )
    return UnifiedResponse.success(data=result)
