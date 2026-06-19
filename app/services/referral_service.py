from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.core.database import get_session
from app.core.errors import AppError, ErrorCode
from app.models.referral import ReferralReward
from app.models.setting import SystemSetting
from app.models.user import User
from app.models.wallet import Wallet, WalletTransaction

logger = logging.getLogger("esim-ego")

SETTING_PREFIX = "referral_"


class ReferralService:

    # ── Settings ──────────────────────────────────────────────────────

    @staticmethod
    def get_settings() -> dict[str, Any]:
        keys = [
            "referral_is_active",
            "referral_reward_amount",
            "referral_qualify_condition",
            "referral_qualify_min_amount",
            "referral_auto_credit",
        ]
        with get_session() as session:
            rows = session.query(SystemSetting).filter(
                SystemSetting.key.in_(keys),
            ).all()
            settings_map: dict[str, str] = {r.key: r.value for r in rows}
        return {
            "is_active": settings_map.get("referral_is_active", "false").lower() == "true",
            "reward_amount": int(settings_map.get("referral_reward_amount", "0")),
            "qualify_condition": settings_map.get("referral_qualify_condition", "any_order"),
            "qualify_min_amount": int(settings_map.get("referral_qualify_min_amount", "0")),
            "auto_credit": settings_map.get("referral_auto_credit", "false").lower() == "true",
        }

    @staticmethod
    def update_setting(key: str, value: str) -> dict[str, Any]:
        full_key = key if key.startswith(SETTING_PREFIX) else f"{SETTING_PREFIX}{key}"
        valid_keys = {
            "referral_is_active",
            "referral_reward_amount",
            "referral_qualify_condition",
            "referral_qualify_min_amount",
            "referral_auto_credit",
        }
        if full_key not in valid_keys:
            raise AppError(ErrorCode.VALIDATION_INVALID_PARAMETER)
        with get_session() as session:
            setting = session.query(SystemSetting).filter(
                SystemSetting.key == full_key,
            ).first()
            if setting:
                setting.value = value
            else:
                setting = SystemSetting(key=full_key, value=value)
                session.add(setting)
            session.flush()
        return {key: value}

    # ── Code ──────────────────────────────────────────────────────────

    @staticmethod
    def generate_code() -> str:
        return secrets.token_hex(4)

    @staticmethod
    def get_or_create_code(user_id: str) -> dict[str, Any]:
        with get_session() as session:
            user = session.query(User).filter(User.id == UUID(user_id)).first()
            if not user:
                raise AppError(ErrorCode.USER_NOT_FOUND)
            if not user.referral_code:
                code = ReferralService.generate_code()
                while session.query(User).filter(User.referral_code == code).first():
                    code = ReferralService.generate_code()
                user.referral_code = code
                session.flush()
            return {"referral_code": user.referral_code}

    @staticmethod
    def apply_referral(new_user_id: str, referral_code: str, session: Any = None) -> None:
        if session is None:
            with get_session() as s:
                return ReferralService.apply_referral(new_user_id, referral_code, session=s)
        if not referral_code or not referral_code.strip():
            raise AppError(ErrorCode.REFERRAL_CODE_INVALID)
        settings = ReferralService._get_settings_dict(session)
        if not settings["is_active"]:
            raise AppError(ErrorCode.FEATURE_DISABLED)
        referrer = session.query(User).filter(
            User.referral_code == referral_code.strip(),
        ).first()
        if not referrer:
            raise AppError(ErrorCode.REFERRAL_CODE_NOT_FOUND)
        if str(referrer.id) == new_user_id:
            raise AppError(ErrorCode.REFERRAL_SELF_REFERRAL)
        new_user = session.query(User).filter(User.id == UUID(new_user_id)).first()
        if not new_user:
            raise AppError(ErrorCode.USER_NOT_FOUND)
        if new_user.referred_by_id:
            raise AppError(ErrorCode.REFERRAL_ALREADY_REFERRED)
        new_user.referred_by_id = str(referrer.id)
        session.flush()
        existing = session.query(ReferralReward).filter(
            ReferralReward.referred_id == str(new_user.id),
        ).first()
        if not existing:
            reward = ReferralReward(
                referrer_id=str(referrer.id),
                referred_id=str(new_user.id),
                amount=settings["reward_amount"],
                status="pending",
                qualify_condition=settings["qualify_condition"],
                qualify_threshold=settings["qualify_min_amount"] if settings["qualify_condition"] == "min_amount" else None,
                auto_credit=settings["auto_credit"],
            )
            session.add(reward)
            session.flush()

    # ── Qualification ─────────────────────────────────────────────────

    @staticmethod
    def check_and_qualify(referred_user_id: str, order_id: str, order_total: int) -> None:
        with get_session() as session:
            reward = session.query(ReferralReward).filter(
                ReferralReward.referred_id == referred_user_id,
                ReferralReward.status == "pending",
            ).with_for_update().first()
            if not reward:
                return
            settings = ReferralService._get_settings_dict(session)
            qualifies = False
            if reward.qualify_condition == "any_order":
                qualifies = True
            elif reward.qualify_condition == "min_amount":
                threshold = reward.qualify_threshold or settings.get("qualify_min_amount", 0)
                qualifies = order_total >= threshold
            if not qualifies:
                return
            reward.order_id = order_id
            reward.status = "qualified"
            session.flush()
            if reward.auto_credit:
                ReferralService._do_credit(session, reward)

    @staticmethod
    def _do_credit(session: Any, reward: ReferralReward) -> None:
        wallet = session.query(Wallet).filter(
            Wallet.user_id == UUID(reward.referrer_id),
        ).with_for_update().first()
        if not wallet:
            logger.warning("No wallet for referrer %s, skipping auto-credit", reward.referrer_id)
            return
        balance_before = wallet.balance
        wallet.balance += reward.amount
        balance_after = wallet.balance
        txn = WalletTransaction(
            wallet_id=wallet.id,
            amount=reward.amount,
            type="credit",
            balance_before=balance_before,
            balance_after=balance_after,
            description=f"Referral reward — user {reward.referred_id[:8]}",
            reference_type="referral",
            reference_id=str(reward.id),
        )
        session.add(txn)
        reward.status = "credited"
        reward.credited_at = datetime.now(timezone.utc)
        session.flush()

    # ── User Stats ────────────────────────────────────────────────────

    @staticmethod
    def get_stats(user_id: str) -> dict[str, Any]:
        with get_session() as session:
            user = session.query(User).filter(User.id == UUID(user_id)).first()
            if not user:
                raise AppError(ErrorCode.USER_NOT_FOUND)
            referred_count = session.query(User).filter(
                User.referred_by_id == user_id,
            ).count()
            rewards = session.query(ReferralReward).filter(
                ReferralReward.referrer_id == user_id,
            ).order_by(ReferralReward.created_at.desc()).all()
            total_earned = sum(r.amount for r in rewards if r.status == "credited")
            pending = sum(r.amount for r in rewards if r.status == "pending")
            qualified = sum(r.amount for r in rewards if r.status == "qualified")
            return {
                "referral_code": user.referral_code or "",
                "total_referred": referred_count,
                "total_earned": total_earned,
                "pending_rewards": pending,
                "qualified_rewards": qualified,
                "rewards": [
                    {
                        "id": str(r.id),
                        "referred_name": r.referred.name if r.referred else "Unknown",
                        "amount": r.amount,
                        "status": r.status,
                        "created_at": r.created_at.isoformat(),
                    }
                    for r in rewards
                ],
            }

    @staticmethod
    def get_settings_for_user(user_id: str) -> dict[str, Any]:
        settings = ReferralService.get_settings()
        with get_session() as session:
            user = session.query(User).filter(User.id == UUID(user_id)).first()
            settings["my_code"] = user.referral_code or "" if user else ""
        return settings

    # ── Admin: credit/cancel ──────────────────────────────────────────

    @staticmethod
    def credit_reward(referral_reward_id: str) -> dict[str, Any]:
        try:
            rid = UUID(referral_reward_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        with get_session() as session:
            reward = session.query(ReferralReward).filter(
                ReferralReward.id == rid,
            ).with_for_update().first()
            if not reward:
                raise AppError(ErrorCode.NOT_FOUND)
            if reward.status == "credited":
                return {"id": str(reward.id), "status": "already_credited"}
            if reward.status == "pending":
                raise AppError(ErrorCode.REFERRAL_NOT_QUALIFIED)
            ReferralService._do_credit(session, reward)
            return {
                "id": str(reward.id),
                "referrer_id": reward.referrer_id,
                "amount": reward.amount,
                "status": "credited",
            }

    @staticmethod
    def cancel_reward(referral_reward_id: str, reason: str = "") -> dict[str, Any]:
        try:
            rid = UUID(referral_reward_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        with get_session() as session:
            reward = session.query(ReferralReward).filter(
                ReferralReward.id == rid,
            ).first()
            if not reward:
                raise AppError(ErrorCode.NOT_FOUND)
            if reward.status == "credited":
                return {"id": str(reward.id), "status": "already_credited"}
            reward.status = "cancelled"
            if reason:
                reward.notes = reason
            session.flush()
            return {"id": str(reward.id), "status": "cancelled"}

    # ── Admin: list + stats ───────────────────────────────────────────

    @staticmethod
    def admin_list_referrals(
        page: int = 1, limit: int = 20,
        status: str | None = None,
    ) -> dict[str, Any]:
        with get_session() as session:
            query = session.query(ReferralReward).order_by(
                ReferralReward.created_at.desc(),
            )
            if status:
                query = query.filter(ReferralReward.status == status)
            total = query.count()
            offset = (page - 1) * limit
            rewards = query.offset(offset).limit(limit).all()
            return {
                "items": [
                    {
                        "id": str(r.id),
                        "referrer": {
                            "id": str(r.referrer.id),
                            "name": r.referrer.name,
                            "phone": r.referrer.phone,
                        } if r.referrer else None,
                        "referred": {
                            "id": str(r.referred.id),
                            "name": r.referred.name,
                            "phone": r.referred.phone,
                        } if r.referred else None,
                        "amount": r.amount,
                        "status": r.status,
                        "qualify_condition": r.qualify_condition,
                        "qualify_threshold": r.qualify_threshold,
                        "auto_credit": r.auto_credit,
                        "notes": r.notes,
                        "credited_at": r.credited_at.isoformat() if r.credited_at else None,
                        "created_at": r.created_at.isoformat(),
                    }
                    for r in rewards
                ],
                "total": total,
                "page": page,
                "limit": limit,
            }

    @staticmethod
    def admin_get_stats() -> dict[str, Any]:
        with get_session() as session:
            total_referrals = session.query(ReferralReward).count()
            total_credited = session.query(ReferralReward).filter(
                ReferralReward.status == "credited",
            ).count()
            total_qualified = session.query(ReferralReward).filter(
                ReferralReward.status == "qualified",
            ).count()
            total_pending = session.query(ReferralReward).filter(
                ReferralReward.status == "pending",
            ).count()
            total_cancelled = session.query(ReferralReward).filter(
                ReferralReward.status == "cancelled",
            ).count()
            total_amount_credited = sum(
                r.amount for r in session.query(ReferralReward).filter(
                    ReferralReward.status == "credited",
                ).all()
            )
            total_amount_qualified = sum(
                r.amount for r in session.query(ReferralReward).filter(
                    ReferralReward.status == "qualified",
                ).all()
            )
            users_with_referrals = session.query(User).filter(
                User.referred_by_id.isnot(None),
            ).count()
            return {
                "total_referrals": total_referrals,
                "total_credited": total_credited,
                "total_qualified": total_qualified,
                "total_pending": total_pending,
                "total_cancelled": total_cancelled,
                "total_amount_credited": total_amount_credited,
                "total_amount_qualified": total_amount_qualified,
                "users_with_referrals": users_with_referrals,
            }

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _get_settings_dict(session: Any) -> dict[str, Any]:
        keys = [
            "referral_is_active",
            "referral_reward_amount",
            "referral_qualify_condition",
            "referral_qualify_min_amount",
            "referral_auto_credit",
        ]
        rows = session.query(SystemSetting).filter(
            SystemSetting.key.in_(keys),
        ).all()
        m: dict[str, str] = {r.key: r.value for r in rows}
        return {
            "is_active": m.get("referral_is_active", "false").lower() == "true",
            "reward_amount": int(m.get("referral_reward_amount", "0")),
            "qualify_condition": m.get("referral_qualify_condition", "any_order"),
            "qualify_min_amount": int(m.get("referral_qualify_min_amount", "0")),
            "auto_credit": m.get("referral_auto_credit", "false").lower() == "true",
        }
