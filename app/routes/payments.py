from __future__ import annotations

import logging

from flask import Blueprint, g, redirect, request

from app.core.errors import AppError, ErrorCode
from app.core.middleware import require_auth
from app.core.response import UnifiedResponse
from app.services.payment_service import PaymentService
from app.providers.payment.superqi import QiCardProvider
from config import settings

logger = logging.getLogger("esim-ego")
payment_routes = Blueprint("payments", __name__, url_prefix="/api/v1/payments")


@payment_routes.route("/<payment_id>", methods=["GET"])
@require_auth()
def get_payment(payment_id: str):
    result = PaymentService.get_payment(payment_id)
    return UnifiedResponse.success(data=result)


@payment_routes.route("/deposit/confirm", methods=["POST"])
@require_auth()
def confirm_deposit():
    data = request.get_json(silent=True) or {}
    payment_id = data.get("payment_id", "")
    provider_txn_id = data.get("provider_transaction_id", "")
    result = PaymentService.confirm_deposit(
        payment_id=payment_id,
        provider_txn_id=provider_txn_id,
    )
    return UnifiedResponse.success(data=result)


@payment_routes.route("/zaincash/init", methods=["POST"])
@require_auth()
def zaincash_init():
    data = request.get_json(silent=True) or {}
    amount = data.get("amount", 0)
    idempotency_key = data.get("idempotency_key", "")
    return_url = data.get("return_url", "")
    result = PaymentService.initiate_zaincash(
        user_id=g.user_id,
        amount=amount,
        idempotency_key=idempotency_key,
        return_url=return_url,
    )
    return UnifiedResponse.success(data=result)


@payment_routes.route("/zaincash/callback", methods=["GET"])
def zaincash_callback_get():
    token = request.args.get("token", "")
    return _process_zaincash_callback(token)


@payment_routes.route("/zaincash/callback", methods=["POST"])
def zaincash_callback_post():
    token = request.form.get("token", "")
    return _process_zaincash_callback(token)


def _process_zaincash_callback(token: str):
    result = PaymentService.handle_zaincash_callback(token)
    payment_id = result.get("payment_id", "")
    return_url = ""
    already = result.get("already_processed", False)
    if payment_id:
        payment = PaymentService.get_payment(payment_id)
        pd = payment.get("provider_data") or {}
        return_url = pd.get("return_url", "")
    if result.get("status") == "completed" and return_url:
        return redirect(return_url)
    if result.get("status") == "completed":
        frontend = settings.FRONTEND_URL or ""
        if frontend:
            return redirect(f"{frontend}/payment/success?payment_id={payment_id}")
        return UnifiedResponse.success(data=result)
    if result.get("status") == "failed":
        return UnifiedResponse.success(data=result)
    msg = result.get("msg", "")
    if msg:
        return UnifiedResponse.success(data=result)
    if already:
        return UnifiedResponse.success(data=result)
    raise AppError(ErrorCode.ZAINCASH_CALLBACK_INVALID)


@payment_routes.route("/qicard/init", methods=["POST"])
@require_auth()
def qicard_init():
    data = request.get_json(silent=True) or {}
    amount = data.get("amount", 0)
    idempotency_key = data.get("idempotency_key", "")
    result = PaymentService.initiate_qicard(
        user_id=g.user_id,
        amount=amount,
        idempotency_key=idempotency_key,
    )
    return UnifiedResponse.success(data=result)


@payment_routes.route("/qicard/webhook", methods=["POST"])
def qicard_webhook():
    data = request.get_json(silent=True) or {}
    signature = request.headers.get("X-Signature", "")
    result = PaymentService.handle_qicard_webhook(data, signature)
    return UnifiedResponse.success(data=result)


@payment_routes.route("/qicard/finish", methods=["GET"])
def qicard_finish():
    payment_id = request.args.get("payment_id", "")
    status = request.args.get("status", "")
    if status == "SUCCESS":
        frontend = settings.FRONTEND_URL or ""
        if frontend:
            return redirect(f"{frontend}/payment/success?payment_id={payment_id}")
        return UnifiedResponse.success(data={"status": "completed"})
    return UnifiedResponse.success(data={"status": status or "pending"})


@payment_routes.route("/qicard/status/<request_id>", methods=["GET"])
@require_auth()
def qicard_status(request_id: str):
    provider = QiCardProvider()
    result = provider.verify_payment(request_id)
    return UnifiedResponse.success(data=result)


@payment_routes.route("/qicard/status_by_payment_id/<payment_id>", methods=["GET"])
@require_auth()
def qicard_status_by_payment_id(payment_id: str):
    provider = QiCardProvider()
    result = provider.get_payment_status(payment_id)
    return UnifiedResponse.success(data=result)


@payment_routes.route("/qicard/cancel", methods=["POST"])
@require_auth()
def qicard_cancel():
    data = request.get_json(silent=True) or {}
    payment_id = data.get("payment_id", "")
    result = PaymentService.cancel_qicard_payment(
        payment_id=payment_id,
        user_id=g.user_id,
    )
    return UnifiedResponse.success(data=result)


@payment_routes.route("/qicard/refund", methods=["POST"])
@require_auth()
def qicard_refund():
    data = request.get_json(silent=True) or {}
    payment_id = data.get("payment_id", "")
    amount = data.get("amount", 0)
    message = data.get("message", "")
    result = PaymentService.refund_qicard_payment(
        payment_id=payment_id,
        amount=amount,
        message=message,
    )
    return UnifiedResponse.success(data=result)
