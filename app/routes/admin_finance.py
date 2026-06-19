from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from flask import Blueprint, g, request

from app.core.middleware import require_auth
from app.core.response import UnifiedResponse
from app.core.errors import ErrorCode
from app.core.validators import AdminRefundRequest, PaginationParams
from app.services.currency_service import CurrencyService
from app.services.tax_service import TaxService
from app.services.coupon_service import CouponService, MAX_COUPON_CODE_LENGTH
from app.services.refund_service import RefundService
from app.services.wallet_service import WalletService
from app.services.report_service import ReportService

logger = logging.getLogger("esim-ego")
admin_finance_routes = Blueprint("admin_finance", __name__, url_prefix="/api/v1/admin")


@admin_finance_routes.route("/exchange-rates", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def list_rates():
    rates = CurrencyService.list_rates()
    return UnifiedResponse.success(data={"items": rates})


@admin_finance_routes.route("/exchange-rates", methods=["POST"])
@require_auth(roles=["admin", "superadmin"])
def set_rate():
    data = request.get_json(silent=True) or {}
    base = data.get("base_currency", "IQD")
    target = data.get("target_currency", "")
    rate_str = data.get("rate", "0")
    if not target:
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_MISSING_FIELD)
    try:
        rate = Decimal(str(rate_str))
    except Exception:
        return UnifiedResponse.from_error_code(ErrorCode.EXCHANGE_RATE_INVALID)
    result = CurrencyService.set_rate(base, target, rate)
    return UnifiedResponse.success(data=result)


@admin_finance_routes.route("/exchange-rates/fetch", methods=["POST"])
@require_auth(roles=["admin", "superadmin"])
def fetch_rates():
    result = CurrencyService.auto_fetch_rates()
    if result.get("success"):
        return UnifiedResponse.success(data=result)
    return UnifiedResponse.from_error_code(ErrorCode.ESIM_CATALOGUE_FAILED)


@admin_finance_routes.route("/tax-rates", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def list_taxes():
    taxes = TaxService.list_taxes()
    return UnifiedResponse.success(data={"items": taxes})


@admin_finance_routes.route("/tax-rates", methods=["POST"])
@require_auth(roles=["admin", "superadmin"])
def create_tax():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "")
    percentage_str = data.get("percentage", "0")
    description = data.get("description", "")
    if not name:
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_MISSING_FIELD)
    try:
        percentage = Decimal(str(percentage_str))
    except Exception:
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_INVALID_PARAMETER)
    result = TaxService.create_tax(name, percentage, description)
    return UnifiedResponse.success(data=result, status=201)


@admin_finance_routes.route("/tax-rates/<tax_id>", methods=["PUT"])
@require_auth(roles=["admin", "superadmin"])
def update_tax(tax_id: str):
    data = request.get_json(silent=True) or {}
    kwargs = {}
    if "name" in data:
        kwargs["name"] = data["name"]
    if "percentage" in data:
        try:
            kwargs["percentage"] = Decimal(str(data["percentage"]))
        except Exception:
            return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_INVALID_PARAMETER)
    if "is_active" in data:
        kwargs["is_active"] = data["is_active"]
    if "description" in data:
        kwargs["description"] = data["description"]
    result = TaxService.update_tax(tax_id, **kwargs)
    return UnifiedResponse.success(data=result)


@admin_finance_routes.route("/coupons", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def list_coupons():
    coupons = CouponService.list_coupons()
    return UnifiedResponse.success(data={"items": coupons})


@admin_finance_routes.route("/coupons", methods=["POST"])
@require_auth(roles=["admin", "superadmin"])
def create_coupon():
    data = request.get_json(silent=True) or {}
    code = data.get("code", "")
    if not code:
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_MISSING_FIELD)
    if len(code) > MAX_COUPON_CODE_LENGTH:
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_EXCEEDS_MAX_LENGTH)
    expires_str = data.get("expires_at", None)
    expires_at = None
    if expires_str:
        try:
            expires_at = datetime.fromisoformat(expires_str)
        except (ValueError, TypeError):
            return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_INVALID_PARAMETER)
    try:
        discount_value = Decimal(str(data.get("discount_value", "0")))
    except Exception:
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_INVALID_PARAMETER)
    result = CouponService.create_coupon(
        code=code,
        discount_type=data.get("discount_type", "percentage"),
        discount_value=discount_value,
        max_uses=data.get("max_uses", 0),
        min_order_amount=data.get("min_order_amount", 0),
        max_discount_amount=data.get("max_discount_amount"),
        applicable_plan_ids=data.get("applicable_plan_ids"),
        expires_at=expires_at,
    )
    return UnifiedResponse.success(data=result, status=201)


@admin_finance_routes.route("/coupons/<coupon_id>", methods=["PUT"])
@require_auth(roles=["admin", "superadmin"])
def update_coupon(coupon_id: str):
    data = request.get_json(silent=True) or {}
    kwargs = {}
    for key in ("code", "discount_type", "max_uses", "min_order_amount",
                "max_discount_amount", "applicable_plan_ids", "is_active"):
        if key in data:
            kwargs[key] = data[key]
    if "discount_value" in data:
        try:
            kwargs["discount_value"] = Decimal(str(data["discount_value"]))
        except Exception:
            return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_INVALID_PARAMETER)
    result = CouponService.update_coupon(coupon_id, **kwargs)
    return UnifiedResponse.success(data=result)


@admin_finance_routes.route("/refunds", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def list_refunds():
    pagination = PaginationParams(
        page=request.args.get("page", 1, type=int),
        limit=request.args.get("limit", 20, type=int),
    )
    result = RefundService.list_refunds(page=pagination.page, limit=pagination.limit)
    return UnifiedResponse.success(data=result)


@admin_finance_routes.route("/refunds", methods=["POST"])
@require_auth(roles=["admin", "superadmin"])
def create_refund():
    data = request.get_json(silent=True) or {}
    try:
        params = AdminRefundRequest(**data)
    except Exception:
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_MISSING_FIELD)
    result = RefundService.create_refund(
        order_id=params.order_id,
        admin_id=g.user_id,
        amount=params.amount,
        reason=params.reason,
    )
    return UnifiedResponse.success(data=result)


@admin_finance_routes.route("/freezes", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def list_freezes():
    pagination = PaginationParams(
        page=request.args.get("page", 1, type=int),
        limit=request.args.get("limit", 20, type=int),
    )
    result = WalletService.list_freezes(page=pagination.page, limit=pagination.limit)
    return UnifiedResponse.success(data=result)


@admin_finance_routes.route("/freezes", methods=["POST"])
@require_auth(roles=["admin", "superadmin"])
def create_freeze():
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id", "")
    amount = data.get("amount", 0)
    reason = data.get("reason", "")
    if not user_id or not amount:
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_MISSING_FIELD)
    result = WalletService.freeze_balance(
        user_id=user_id,
        amount=amount,
        reason=reason,
        admin_id=g.user_id,
    )
    return UnifiedResponse.success(data=result)


@admin_finance_routes.route("/freezes/<freeze_id>/release", methods=["POST"])
@require_auth(roles=["admin", "superadmin"])
def release_freeze(freeze_id: str):
    result = WalletService.release_freeze(freeze_id)
    return UnifiedResponse.success(data=result)


@admin_finance_routes.route("/reports/financial", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def financial_report():
    period = request.args.get("period", "daily")
    result = ReportService.financial_report(period=period)
    return UnifiedResponse.success(data=result)


@admin_finance_routes.route("/reports/wallet", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def wallet_dashboard():
    result = ReportService.wallet_dashboard()
    return UnifiedResponse.success(data=result)
