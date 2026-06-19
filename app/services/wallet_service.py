from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from app.core.database import get_session
from app.core.constants import validate_amount_range
from app.core.errors import AppError, ErrorCode
from app.models.finance import WalletFreeze
from app.models.wallet import Wallet, WalletTransaction

logger = logging.getLogger("esim-ego")


class WalletService:

    @staticmethod
    def get_wallet(user_id: str) -> dict:
        uid = UUID(user_id)
        with get_session() as session:
            wallet = (
                session.query(Wallet)
                .filter(Wallet.user_id == uid)
                .first()
            )
            if not wallet:
                raise AppError(ErrorCode.WALLET_NOT_FOUND)
            available = wallet.balance - wallet.frozen_balance
            return {
                "id": str(wallet.id),
                "user_id": str(wallet.user_id),
                "balance": wallet.balance,
                "frozen_balance": wallet.frozen_balance,
                "available_balance": available if available > 0 else 0,
                "created_at": wallet.created_at.isoformat(),
            }

    @staticmethod
    def get_transactions(
        user_id: str, page: int = 1, limit: int = 20
    ) -> dict:
        uid = UUID(user_id)
        with get_session() as session:
            wallet = (
                session.query(Wallet)
                .filter(Wallet.user_id == uid)
                .first()
            )
            if not wallet:
                raise AppError(ErrorCode.WALLET_NOT_FOUND)
            offset = (page - 1) * limit
            total = (
                session.query(WalletTransaction)
                .filter(WalletTransaction.wallet_id == wallet.id)
                .count()
            )
            txns = (
                session.query(WalletTransaction)
                .filter(WalletTransaction.wallet_id == wallet.id)
                .order_by(WalletTransaction.created_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return {
                "items": [
                    {
                        "id": str(t.id),
                        "amount": t.amount,
                        "type": t.type,
                        "balance_before": t.balance_before,
                        "balance_after": t.balance_after,
                        "description": t.description,
                        "created_at": t.created_at.isoformat(),
                    }
                    for t in txns
                ],
                "total": total,
                "page": page,
                "limit": limit,
            }

    @staticmethod
    def freeze_balance(user_id: str, amount: int, reason: str = "", admin_id: str = "") -> dict:
        uid = UUID(user_id)
        with get_session() as session:
            wallet = (
                session.query(Wallet)
                .filter(Wallet.user_id == uid)
                .with_for_update()
                .first()
            )
            if not wallet:
                raise AppError(ErrorCode.WALLET_NOT_FOUND)
            available = wallet.balance - wallet.frozen_balance
            if amount <= 0 or amount > available:
                raise AppError(ErrorCode.WALLET_FREEZE_EXCEEDS_BALANCE)
            wallet.frozen_balance += amount
            freeze = WalletFreeze(
                wallet_id=wallet.id,
                amount=amount,
                reason=reason or "Admin freeze",
                created_by=UUID(admin_id) if admin_id else uid,
            )
            session.add(freeze)
            session.flush()
            return {
                "freeze_id": str(freeze.id),
                "amount": amount,
                "reason": freeze.reason,
                "status": freeze.status,
            }

    @staticmethod
    def release_freeze(freeze_id: str) -> dict:
        try:
            fid = UUID(freeze_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        with get_session() as session:
            freeze = (
                session.query(WalletFreeze)
                .filter(WalletFreeze.id == fid, WalletFreeze.status == "active")
                .with_for_update()
                .first()
            )
            if not freeze:
                raise AppError(ErrorCode.WALLET_FREEZE_NOT_FOUND)
            wallet = (
                session.query(Wallet)
                .filter(Wallet.id == freeze.wallet_id)
                .with_for_update()
                .first()
            )
            freeze.status = "released"
            freeze.released_at = datetime.now(timezone.utc)
            wallet.frozen_balance -= freeze.amount
            session.flush()
            return {
                "freeze_id": str(freeze.id),
                "amount": freeze.amount,
                "status": freeze.status,
                "released_at": freeze.released_at.isoformat(),
            }

    @staticmethod
    def list_freezes(page: int = 1, limit: int = 20) -> dict:
        with get_session() as session:
            query = session.query(WalletFreeze).order_by(WalletFreeze.created_at.desc())
            total = query.count()
            offset = (page - 1) * limit
            items = query.offset(offset).limit(limit).all()
            return {
                "items": [
                    {
                        "id": str(f.id),
                        "wallet_id": str(f.wallet_id),
                        "amount": f.amount,
                        "reason": f.reason,
                        "status": f.status,
                        "released_at": f.released_at.isoformat() if f.released_at else None,
                        "created_at": f.created_at.isoformat(),
                    }
                    for f in items
                ],
                "total": total,
                "page": page,
                "limit": limit,
            }

    @staticmethod
    def deposit(
        user_id: str, amount: Decimal, idempotency_key: str = ""
    ) -> dict:
        uid = UUID(user_id)
        with get_session() as session:
            wallet = (
                session.query(Wallet)
                .filter(Wallet.user_id == uid)
                .with_for_update()
                .first()
            )
            if not wallet:
                raise AppError(ErrorCode.WALLET_NOT_FOUND)
            try:
                int_amount = int(amount)
            except (ValueError, TypeError):
                raise AppError(ErrorCode.VALIDATION_INVALID_AMOUNT)
            validate_amount_range(int_amount)
            balance_before = wallet.balance
            wallet.balance += int_amount
            balance_after = wallet.balance
            txn = WalletTransaction(
                wallet_id=wallet.id,
                amount=int_amount,
                type="deposit",
                balance_before=balance_before,
                balance_after=balance_after,
                description=f"Deposit of {int_amount} IQD",
            )
            session.add(txn)
            session.flush()
            return {
                "transaction_id": str(txn.id),
                "amount": int_amount,
                "balance_before": balance_before,
                "balance_after": balance_after,
                "type": "deposit",
            }
