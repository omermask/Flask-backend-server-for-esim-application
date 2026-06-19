from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from config import settings

from app.core.database import get_session
import jwt as pyjwt

from app.core.errors import AppError, ErrorCode
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_otp,
    get_user_token_version,
    hash_password,
    increment_user_token_version,
    is_token_revoked,
    mask_phone,
    revoke_token,
    verify_password,
    validate_token_type,
)
from app.models.user import OTPCode, User
from app.models.device_session import DeviceSession
from app.models.wallet import Wallet
from app.providers.registry import ProviderRegistry
from app.services.referral_service import ReferralService

logger = logging.getLogger("esim-ego")


class AuthService:

    @staticmethod
    def register(phone: str, name: str, language: str, timezone: str, referral_code: str | None = None) -> dict:
        with get_session() as session:
            existing = session.query(User).filter(User.phone == phone).first()
            if existing:
                raise AppError(ErrorCode.AUTH_PHONE_EXISTS)
            code = ReferralService.generate_code()
            while session.query(User).filter(User.referral_code == code).first():
                code = ReferralService.generate_code()
            user = User(
                phone=phone,
                name=name,
                language=language,
                timezone=timezone,
                referral_code=code,
            )
            session.add(user)
            session.flush()
            wallet = Wallet(user_id=user.id, balance=0)
            session.add(wallet)
            session.flush()
            if referral_code and referral_code.strip():
                try:
                    ReferralService.apply_referral(
                        new_user_id=str(user.id),
                        referral_code=referral_code,
                        session=session,
                    )
                except AppError:
                    raise
                except Exception:
                    pass
            session.flush()
            otp_record = AuthService._create_otp(session, phone)
            AuthService._send_sms(phone, otp_record["plain_otp"], lang=language)
            user_data = {
                "id": str(user.id),
                "phone": user.phone,
                "name": user.name,
            }
        return user_data

    @staticmethod
    def send_otp(phone: str) -> None:
        with get_session() as session:
            user = session.query(User).filter(User.phone == phone).first()
            if not user:
                raise AppError(ErrorCode.AUTH_PHONE_NOT_FOUND)
            if user.otp_blocked_until and user.otp_blocked_until > datetime.now(timezone.utc):
                raise AppError(ErrorCode.AUTH_BLOCKED)
            otp_record = AuthService._create_otp(session, phone)
            lang = user.language
        AuthService._send_sms(phone, otp_record["plain_otp"], lang=lang)

    @staticmethod
    def _send_sms(phone: str, otp: str, lang: str = "en") -> None:
        provider_name = settings.SMS_PROVIDER.lower() if settings.SMS_PROVIDER else ""
        if not provider_name:
            logger.warning("No SMS provider configured — OTP would be sent to %s", mask_phone(phone))
            if not settings.IS_PRODUCTION:
                logger.info("Dev OTP for %s: %s", mask_phone(phone), otp)
            return
        sms = ProviderRegistry.get_sms(provider_name)
        if not sms:
            logger.error("SMS provider '%s' not found in registry", provider_name)
            raise AppError(ErrorCode.SMS_INIT_FAILED)
        result = sms.send_otp(phone, otp, lang=lang)
        if not result.get("success"):
            raise AppError(ErrorCode.SMS_SEND_FAILED)

    @staticmethod
    def _create_otp(session, phone: str) -> dict:
        plain_otp = generate_otp()
        code_hash = hash_password(plain_otp)
        otp_record = OTPCode(
            phone=phone,
            code_hash=code_hash,
            purpose="login",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.OTP_EXPIRY_MINUTES),
            max_attempts=settings.OTP_MAX_ATTEMPTS,
        )
        session.add(otp_record)
        session.flush()
        return {"plain_otp": plain_otp, "record": otp_record}

    @staticmethod
    def verify_otp(phone: str, code: str, device_id: str | None = None) -> tuple[str, str, dict]:
        with get_session() as session:
            user = session.query(User).filter(User.phone == phone).first()
            if not user:
                raise AppError(ErrorCode.AUTH_PHONE_NOT_FOUND)
            if user.otp_blocked_until and user.otp_blocked_until > datetime.now(timezone.utc):
                raise AppError(ErrorCode.AUTH_BLOCKED)
            otp_record = (
                session.query(OTPCode)
                .filter(OTPCode.phone == phone, OTPCode.is_used == False)
                .order_by(OTPCode.created_at.desc())
                .with_for_update()
                .first()
            )
            if not otp_record:
                raise AppError(ErrorCode.AUTH_EXPIRED_OTP)
            if otp_record.expires_at < datetime.now(timezone.utc):
                otp_record.is_used = True
                session.commit()
                raise AppError(ErrorCode.AUTH_EXPIRED_OTP)
            if otp_record.attempts >= otp_record.max_attempts:
                otp_record.is_used = True
                user.otp_blocked_until = datetime.now(timezone.utc) + timedelta(
                    minutes=settings.OTP_BLOCK_MINUTES
                )
                session.commit()
                raise AppError(ErrorCode.AUTH_MAX_ATTEMPTS)
            if not verify_password(code, otp_record.code_hash):
                otp_record.attempts += 1
                session.flush()
                if otp_record.attempts >= otp_record.max_attempts:
                    otp_record.is_used = True
                    user.otp_blocked_until = datetime.now(timezone.utc) + timedelta(
                        minutes=settings.OTP_BLOCK_MINUTES
                    )
                    session.commit()
                    raise AppError(ErrorCode.AUTH_BLOCKED)
                session.commit()
                raise AppError(ErrorCode.AUTH_INVALID_OTP)
            otp_record.is_used = True
            user.is_verified = True
            user.failed_otp_attempts = 0
            user.otp_blocked_until = None
            user.last_login_at = datetime.now(timezone.utc)
            token_version = 0
            if device_id:
                existing = (
                    session.query(DeviceSession)
                    .filter(
                        DeviceSession.user_id == user.id,
                        DeviceSession.is_active == True,
                    )
                    .with_for_update()
                    .first()
                )
                if existing and existing.device_id != device_id:
                    existing.is_active = False
                    session.flush()
                device_session = existing if existing and existing.device_id == device_id else (
                    session.query(DeviceSession)
                    .filter(
                        DeviceSession.user_id == user.id,
                        DeviceSession.device_id == device_id,
                    )
                    .with_for_update()
                    .first()
                )
                new_version = increment_user_token_version(str(user.id))
                if device_session:
                    device_session.is_active = True
                    device_session.last_active_at = datetime.now(timezone.utc)
                    if new_version > 0:
                        device_session.token_version = new_version
                    else:
                        device_session.token_version += 1
                    token_version = device_session.token_version
                else:
                    if new_version <= 0:
                        new_version = 1
                    device_session = DeviceSession(
                        user_id=user.id,
                        device_id=device_id,
                        token_version=new_version,
                    )
                    session.add(device_session)
                    token_version = new_version
                session.flush()
            session.flush()
            admin_2fa = user.role in ("admin", "superadmin") and user.totp_enabled
            totp_enabled = user.role in ("admin", "superadmin") and user.totp_enabled
            totp_verified = False
            access_token = create_access_token(
                user_id=str(user.id),
                role=user.role,
                secret_key=settings.SECRET_KEY,
                totp_enabled=totp_enabled,
                totp_verified=totp_verified,
                token_version=token_version,
            )
            refresh_token = create_refresh_token(
                user_id=str(user.id),
                role=user.role,
                secret_key=settings.SECRET_KEY,
                totp_enabled=totp_enabled,
                totp_verified=totp_verified,
                token_version=token_version,
            )
            user_data = {
                "id": str(user.id),
                "phone": user.phone,
                "name": user.name,
                "role": user.role,
                "language": user.language,
                "is_verified": user.is_verified,
                "2fa_required": admin_2fa,
            }
        return access_token, refresh_token, user_data

    @staticmethod
    def refresh_token(refresh_token_str: str) -> tuple[str, str]:
        secret = settings.SECRET_KEY
        try:
            payload = decode_token(refresh_token_str, secret)
        except pyjwt.ExpiredSignatureError:
            raise AppError(ErrorCode.AUTH_TOKEN_EXPIRED)
        except pyjwt.InvalidTokenError:
            raise AppError(ErrorCode.AUTH_INVALID_REFRESH)
        try:
            validate_token_type(payload, "refresh")
        except pyjwt.InvalidTokenError:
            raise AppError(ErrorCode.AUTH_INVALID_REFRESH)
        jti = payload.get("jti", "")
        if is_token_revoked(jti):
            raise AppError(ErrorCode.AUTH_TOKEN_REVOKED)
        user_id = payload["sub"]
        role = payload.get("role", "user")
        totp_enabled = payload.get("totp_enabled", False)
        totp_verified = payload.get("totp_verified", False)
        token_version = payload.get("token_version", 0)
        if token_version > 0:
            current_version = get_user_token_version(user_id)
            if current_version > token_version:
                raise AppError(ErrorCode.AUTH_DEVICE_SESSION_EXPIRED)
        revoke_token(jti, expiry_seconds=settings.JWT_REFRESH_TOKEN_EXPIRY_DAYS * 86400)
        new_access = create_access_token(
            user_id=user_id,
            role=role,
            secret_key=secret,
            totp_enabled=totp_enabled,
            totp_verified=totp_verified,
            token_version=token_version,
        )
        new_refresh = create_refresh_token(
            user_id=user_id,
            role=role,
            secret_key=secret,
            totp_enabled=totp_enabled,
            totp_verified=totp_verified,
            token_version=token_version,
        )
        return new_access, new_refresh

    @staticmethod
    def logout(
        user_id: str,
        access_jti: str,
        refresh_jti: str | None = None,
        device_id: str | None = None,
    ) -> None:
        revoke_token(access_jti, expiry_seconds=900)
        if refresh_jti:
            revoke_token(refresh_jti, expiry_seconds=settings.JWT_REFRESH_TOKEN_EXPIRY_DAYS * 86400)
        if device_id:
            with get_session() as session:
                session.query(DeviceSession).filter(
                    DeviceSession.user_id == user_id,
                    DeviceSession.device_id == device_id,
                    DeviceSession.is_active == True,
                ).update({"is_active": False})
                increment_user_token_version(user_id)
