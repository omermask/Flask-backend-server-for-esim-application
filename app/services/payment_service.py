from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID

from app.core.database import get_session
from app.core.errors import AppError, ErrorCode
from app.core.constants import validate_amount_range
from app.models.payment import Payment, PaymentProviderTransaction
from app.models.wallet import Wallet, WalletTransaction
from app.providers.payment.zaincash import ZainCashProvider
from app.providers.payment.superqi import QiCardProvider
from app.providers.registry import ProviderRegistry
from config import settings

logger = logging.getLogger("esim-ego")


class PaymentService:

    @staticmethod
    def initiate_deposit(
        user_id: str,
        amount: Decimal,
        payment_method: str,
        idempotency_key: str = "",
    ) -> dict:
        uid = UUID(user_id)
        try:
            int_amount = int(amount)
        except (ValueError, TypeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_AMOUNT)
        method = payment_method.lower()

        with get_session() as session:
            if idempotency_key:
                existing = (
                    session.query(Payment)
                    .filter(Payment.idempotency_key == idempotency_key)
                    .with_for_update()
                    .first()
                )
                if existing:
                    raise AppError(ErrorCode.VALIDATION_IDEMPOTENCY_REUSE)
            wallet = (
                session.query(Wallet)
                .filter(Wallet.user_id == uid)
                .first()
            )
            if not wallet:
                raise AppError(ErrorCode.WALLET_NOT_FOUND)
            payment = Payment(
                user_id=uid,
                amount=int_amount,
                method=method,
                status="pending",
                idempotency_key=idempotency_key or None,
            )
            session.add(payment)
            session.flush()
            payment_id = str(payment.id)

        provider = ProviderRegistry.get_payment(method)
        if not provider:
            raise AppError(ErrorCode.PAYMENT_METHOD_UNSUPPORTED)

        if method == "zaincash":
            order_id = f"{settings.ZAINCASH_ORDER_PREFIX}{payment_id}"
            callback_base = (
                settings.ZAINCASH_REDIRECT_URL
                or f"https://{settings.FLASK_HOST}/api/v1/payments/zaincash/callback"
            )
            callback_url = f"{callback_base}?payment_id={payment_id}"
        elif method == "qicard":
            order_id = payment_id
            notification_base = (
                settings.QICARD_NOTIFICATION_URL
                or f"https://{settings.FLASK_HOST}/api/v1/payments/qicard/webhook"
            )
            finish_base = (
                settings.QICARD_FINISH_URL
                or f"https://{settings.FLASK_HOST}/api/v1/payments/qicard/finish"
            )
            notification_url = f"{notification_base}?payment_id={payment_id}"
            finish_url = f"{finish_base}?payment_id={payment_id}"
        else:
            order_id = f"deposit_{payment_id}"
            callback_base = f"https://{settings.FLASK_HOST}/api/v1/payments/{method}/callback"
            callback_url = f"{callback_base}?payment_id={payment_id}"

        if method == "qicard":
            result = provider.initiate_payment(
                int_amount, order_id, finish_url,
                additional_info={"notification_url": notification_url},
            )
        else:
            result = provider.initiate_payment(int_amount, order_id, callback_url)

        req_data: dict = {
            "amount": int_amount,
            "order_id": order_id,
            "callback_url": finish_url if method == "qicard" else callback_url,
        }
        if method == "qicard":
            req_data["notification_url"] = notification_url
        with get_session() as session:
            txn = PaymentProviderTransaction(
                payment_id=UUID(payment_id),
                provider=method,
                request_data=req_data,
                response_data=result,
                status="pending",
            )
            session.add(txn)

        return {
            "payment_id": payment_id,
            "amount": int_amount,
            "method": method,
            "transaction_id": result.get("transaction_id", ""),
            "payment_url": result.get("payment_url", ""),
            "expiry_time": result.get("expiry_time", ""),
            "status": "pending",
        }

    @staticmethod
    def confirm_deposit(payment_id: str, provider_txn_id: str = "") -> dict:
        try:
            pid = UUID(payment_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        with get_session() as session:
            payment = (
                session.query(Payment)
                .filter(Payment.id == pid)
                .with_for_update()
                .first()
            )
            if not payment:
                raise AppError(ErrorCode.NOT_FOUND)
            if payment.status != "pending":
                raise AppError(ErrorCode.PAYMENT_DUPLICATE)
            payment.status = "completed"
            payment.provider_transaction_id = provider_txn_id or None
            wallet = (
                session.query(Wallet)
                .filter(Wallet.user_id == payment.user_id)
                .with_for_update()
                .first()
            )
            if not wallet:
                raise AppError(ErrorCode.WALLET_NOT_FOUND)
            balance_before = wallet.balance
            wallet.balance += payment.amount
            balance_after = wallet.balance
            txn = WalletTransaction(
                wallet_id=wallet.id,
                amount=payment.amount,
                type="deposit",
                balance_before=balance_before,
                balance_after=balance_after,
                description=f"Deposit via {payment.method}",
            )
            session.add(txn)
            session.flush()
            _payment_id = str(payment.id)
            _user_id = str(payment.user_id)
            _amount = payment.amount

        try:
            from app.services.notification_template_service import NotificationTemplateService
            rendered = NotificationTemplateService.render_for_user(
                "deposit_received", _user_id,
                amount=_amount, balance=balance_after,
            )
            if rendered:
                title, body = rendered
                from app.tasks.push_tasks import send_push_notification
                send_push_notification.delay(
                    user_id=_user_id,
                    title=title,
                    body=body,
                    data={
                        "type": "deposit_received",
                        "amount": _amount,
                        "balance": balance_after,
                    },
                )
        except Exception:
            logger.debug("Push notification skipped for payment %s", _payment_id)

        try:
            from app.socketio import emit_wallet_update
            emit_wallet_update(_user_id, balance_after)
        except Exception:
            logger.debug("SocketIO emit skipped for payment %s", _payment_id)

        return {
            "payment_id": _payment_id,
            "status": "completed",
            "amount": _amount,
            "balance_before": balance_before,
            "balance_after": balance_after,
        }

    @staticmethod
    def initiate_zaincash(
        user_id: str,
        amount: int,
        idempotency_key: str = "",
        return_url: str = "",
    ) -> dict:
        uid = UUID(user_id)
        validate_amount_range(amount)
        with get_session() as session:
            if idempotency_key:
                existing = (
                    session.query(Payment)
                    .filter(Payment.idempotency_key == idempotency_key)
                    .with_for_update()
                    .first()
                )
                if existing:
                    raise AppError(ErrorCode.VALIDATION_IDEMPOTENCY_REUSE)
            wallet = (
                session.query(Wallet)
                .filter(Wallet.user_id == uid)
                .first()
            )
            if not wallet:
                raise AppError(ErrorCode.WALLET_NOT_FOUND)
            provider_data: dict = {"return_url": return_url} if return_url else {}
            payment = Payment(
                user_id=uid,
                amount=amount,
                method="zaincash",
                status="pending",
                idempotency_key=idempotency_key or None,
                provider_data=provider_data or None,
            )
            session.add(payment)
            session.flush()
            payment_id = str(payment.id)
        order_id = f"{settings.ZAINCASH_ORDER_PREFIX}{payment_id}"
        callback_base = (
            settings.ZAINCASH_REDIRECT_URL
            or f"https://{settings.FLASK_HOST}/api/v1/payments/zaincash/callback"
        )
        callback_url = f"{callback_base}?payment_id={payment_id}"
        provider = ProviderRegistry.get_payment("zaincash")
        if not provider:
            raise AppError(ErrorCode.PAYMENT_METHOD_UNSUPPORTED)
        result = provider.initiate_payment(amount, order_id, callback_url)
        with get_session() as session:
            txn = PaymentProviderTransaction(
                payment_id=UUID(payment_id),
                provider="zaincash",
                request_data={
                    "amount": amount,
                    "order_id": order_id,
                    "callback_url": callback_url,
                },
                response_data=result,
                status="pending",
            )
            session.add(txn)
        return {
            "payment_id": payment_id,
            "amount": amount,
            "transaction_id": result["transaction_id"],
            "payment_url": result["payment_url"],
            "expiry_time": result.get("expiry_time", ""),
        }

    @staticmethod
    def handle_zaincash_callback(token: str) -> dict:
        if not token:
            raise AppError(ErrorCode.ZAINCASH_CALLBACK_INVALID)
        provider = ProviderRegistry.get_payment("zaincash")
        if not provider:
            raise AppError(ErrorCode.PAYMENT_METHOD_UNSUPPORTED)
        data = provider.verify_callback(token)
        if data["status"] != "success":
            logger.warning("ZainCash payment failed: %s", data.get("msg"))
            return {
                "status": "failed",
                "msg": data.get("msg", "payment_failed"),
            }
        callback_currency = data.get("currency", "IQD")
        if callback_currency != "IQD":
            raise AppError(ErrorCode.ZAINCASH_CALLBACK_INVALID)
        txn_id = data.get("transaction_id", "")
        order_id = data.get("order_id", "")
        prefix = settings.ZAINCASH_ORDER_PREFIX
        if not order_id.startswith(prefix):
            raise AppError(ErrorCode.ZAINCASH_CALLBACK_INVALID)
        payment_id = order_id[len(prefix):]
        try:
            pid = UUID(payment_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.ZAINCASH_CALLBACK_INVALID)
        callback_amount = data.get("amount")
        if callback_amount is not None:
            try:
                callback_amount = int(callback_amount)
            except (ValueError, TypeError):
                raise AppError(ErrorCode.ZAINCASH_CALLBACK_INVALID)
        with get_session() as session:
            payment = (
                session.query(Payment)
                .filter(Payment.id == pid)
                .with_for_update()
                .first()
            )
            if not payment:
                raise AppError(ErrorCode.NOT_FOUND)
            if payment.status != "pending":
                return {
                    "payment_id": str(payment.id),
                    "status": payment.status,
                    "already_processed": True,
                }
            if callback_amount is not None and callback_amount != payment.amount:
                logger.error(
                    "ZainCash amount mismatch: db=%d callback=%d payment=%s",
                    payment.amount, callback_amount, payment_id,
                )
                raise AppError(ErrorCode.ZAINCASH_CALLBACK_INVALID)
        result = PaymentService.confirm_deposit(
            payment_id=payment_id,
            provider_txn_id=txn_id,
        )
        return {
            "payment_id": str(result["payment_id"]),
            "status": "completed",
            "amount": result["amount"],
            "balance_before": result["balance_before"],
            "balance_after": result["balance_after"],
        }

    @staticmethod
    def initiate_qicard(
        user_id: str,
        amount: int,
        idempotency_key: str = "",
    ) -> dict:
        uid = UUID(user_id)
        validate_amount_range(amount)
        with get_session() as session:
            if idempotency_key:
                existing = (
                    session.query(Payment)
                    .filter(Payment.idempotency_key == idempotency_key)
                    .with_for_update()
                    .first()
                )
                if existing:
                    raise AppError(ErrorCode.VALIDATION_IDEMPOTENCY_REUSE)
            wallet = (
                session.query(Wallet)
                .filter(Wallet.user_id == uid)
                .first()
            )
            if not wallet:
                raise AppError(ErrorCode.WALLET_NOT_FOUND)
            payment = Payment(
                user_id=uid,
                amount=amount,
                method="qicard",
                status="pending",
                idempotency_key=idempotency_key or None,
            )
            session.add(payment)
            session.flush()
            payment_id = str(payment.id)
        notification_base = (
            settings.QICARD_NOTIFICATION_URL
            or f"https://{settings.FLASK_HOST}/api/v1/payments/qicard/webhook"
        )
        finish_base = (
            settings.QICARD_FINISH_URL
            or f"https://{settings.FLASK_HOST}/api/v1/payments/qicard/finish"
        )
        notification_url = f"{notification_base}?payment_id={payment_id}"
        finish_url = f"{finish_base}?payment_id={payment_id}"
        provider = ProviderRegistry.get_payment("qicard")
        if not provider:
            raise AppError(ErrorCode.PAYMENT_METHOD_UNSUPPORTED)
        result = provider.initiate_payment(
            amount, payment_id, finish_url,
            additional_info={"notification_url": notification_url},
        )
        with get_session() as session:
            txn = PaymentProviderTransaction(
                payment_id=UUID(payment_id),
                provider="qicard",
                request_data={
                    "amount": amount,
                    "request_id": payment_id,
                    "notification_url": notification_url,
                    "finish_url": finish_url,
                },
                response_data=result,
                status="pending",
            )
            session.add(txn)
        return {
            "payment_id": payment_id,
            "amount": amount,
            "request_id": result.get("request_id", payment_id),
            "payment_url": result["payment_url"],
        }

    @staticmethod
    def handle_qicard_webhook(data: dict, signature: str = "") -> dict:
        if not data:
            raise AppError(ErrorCode.QICARD_WEBHOOK_INVALID)
        provider = QiCardProvider()
        if not provider.verify_webhook(data, signature):
            raise AppError(ErrorCode.PAYMENT_INVALID_SIGNATURE)
        webhook_data = provider.handle_webhook(data)
        request_id = webhook_data["request_id"]
        try:
            pid = UUID(request_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.QICARD_WEBHOOK_INVALID)
        db_amount: int | None = None
        with get_session() as session:
            payment = (
                session.query(Payment)
                .filter(Payment.id == pid)
                .with_for_update()
                .first()
            )
            if not payment:
                raise AppError(ErrorCode.NOT_FOUND)
            db_amount = payment.amount
            if payment.status != "pending":
                return {
                    "payment_id": str(payment.id),
                    "status": payment.status,
                    "already_processed": True,
                }
        webhook_currency = webhook_data.get("currency", "IQD")
        if webhook_currency != "IQD":
            raise AppError(ErrorCode.QICARD_WEBHOOK_INVALID)
        if not webhook_data["is_success"]:
            logger.warning(
                "QiCard webhook status not success: %s", webhook_data.get("status")
            )
            return {"status": "failed", "msg": "payment_failed"}
        verification = provider.verify_payment(request_id)
        if not verification.get("is_success"):
            logger.error(
                "QiCard verification failed: request=%s api_status=%s",
                request_id, verification.get("status"),
            )
            raise AppError(ErrorCode.QICARD_VERIFICATION_FAILED)
        verified_amount = verification.get("confirmed_amount") or verification.get("amount")
        if verified_amount is not None and db_amount is not None:
            try:
                verified_int = int(verified_amount)
            except (ValueError, TypeError):
                raise AppError(ErrorCode.QICARD_VERIFICATION_FAILED)
            if verified_int != db_amount:
                logger.error(
                    "QiCard amount mismatch: db=%d api=%s request=%s",
                    db_amount, verified_amount, request_id,
                )
                raise AppError(ErrorCode.QICARD_VERIFICATION_FAILED)
        txn_id = webhook_data.get("payment_id", "")
        result = PaymentService.confirm_deposit(
            payment_id=request_id,
            provider_txn_id=txn_id,
        )
        return {
            "payment_id": str(result["payment_id"]),
            "status": "completed",
            "amount": result["amount"],
            "balance_before": result["balance_before"],
            "balance_after": result["balance_after"],
        }

    @staticmethod
    def cancel_qicard_payment(payment_id: str, user_id: str) -> dict:
        try:
            pid = UUID(payment_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        uid = UUID(user_id)
        with get_session() as session:
            payment = (
                session.query(Payment)
                .filter(Payment.id == pid, Payment.user_id == uid)
                .with_for_update()
                .first()
            )
            if not payment:
                raise AppError(ErrorCode.NOT_FOUND)
            if payment.method != "qicard":
                raise AppError(ErrorCode.PAYMENT_METHOD_UNSUPPORTED)
            if payment.status != "pending":
                raise AppError(ErrorCode.ORDER_INVALID_STATUS)
            import uuid
            cancel_request_id = str(uuid.uuid4())
            provider = QiCardProvider()
            result = provider.cancel_payment(payment_id, cancel_request_id)
            payment.status = "cancelled"
            if result.get("canceled", False):
                payment.provider_transaction_id = cancel_request_id
            return {
                "payment_id": payment_id,
                "status": "cancelled",
                "canceled": result.get("canceled", False),
                "provider_status": result.get("status", ""),
            }

    @staticmethod
    def refund_qicard_payment(payment_id: str, amount: int = 0, message: str = "") -> dict:
        try:
            pid = UUID(payment_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        with get_session() as session:
            payment = (
                session.query(Payment)
                .filter(Payment.id == pid)
                .with_for_update()
                .first()
            )
            if not payment:
                raise AppError(ErrorCode.NOT_FOUND)
            if payment.method != "qicard":
                raise AppError(ErrorCode.PAYMENT_METHOD_UNSUPPORTED)
            if payment.status != "completed":
                raise AppError(ErrorCode.REFUND_ORDER_NOT_PAID)
            import uuid
            refund_request_id = str(uuid.uuid4())
            refund_amount = amount if amount > 0 else payment.amount
            if refund_amount > payment.amount:
                raise AppError(ErrorCode.REFUND_INVALID_AMOUNT)
            provider = QiCardProvider()
            result = provider.refund_payment(payment_id, refund_request_id, refund_amount, message)
            payment.status = "refunded"
            return {
                "payment_id": payment_id,
                "refund_id": result.get("refund_id", ""),
                "amount": refund_amount,
                "status": "refunded",
                "provider_status": result.get("status", ""),
                "message": result.get("message", ""),
            }

    @staticmethod
    def get_payment(payment_id: str) -> dict:
        try:
            pid = UUID(payment_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        with get_session() as session:
            payment = session.query(Payment).filter(Payment.id == pid).first()
            if not payment:
                raise AppError(ErrorCode.NOT_FOUND)
            return {
                "id": str(payment.id),
                "user_id": str(payment.user_id),
                "amount": payment.amount,
                "method": payment.method,
                "status": payment.status,
                "provider_transaction_id": payment.provider_transaction_id,
                "provider_data": payment.provider_data,
                "created_at": payment.created_at.isoformat(),
            }
