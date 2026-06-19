from __future__ import annotations

import re
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import (
    BaseModel,
    Field,
    field_validator,
)

from app.core.constants import (
    MAX_EMAIL_LENGTH,
    MAX_NAME_LENGTH,
    MAX_PHONE_LENGTH,
    MIN_PHONE_LENGTH,
    OTP_CODE_LENGTH,
)


def _validate_phone_format(v: str) -> str:
    if not re.match(r"^9647[0-9]{8,9}$", v):
        raise ValueError("PHONE_MUST_BE_964_FORMAT")
    return v


def _validate_idempotency_key(v: str) -> str:
    if v and len(v) < 8:
        raise ValueError("IDEMPOTENCY_KEY_TOO_SHORT")
    return v


def _validate_uuid(v: str) -> str:
    try:
        UUID(v)
    except (ValueError, AttributeError):
        raise ValueError("INVALID_PLAN_ID_FORMAT")
    return v


class RegisterRequest(BaseModel):
    model_config = {"extra": "forbid"}

    phone: str = Field(..., min_length=MIN_PHONE_LENGTH, max_length=MAX_PHONE_LENGTH)
    name: str = Field(..., min_length=1, max_length=MAX_NAME_LENGTH)
    language: str = Field(default="en", max_length=10)
    timezone: str = Field(default="Asia/Baghdad", max_length=50)
    referral_code: Optional[str] = Field(None, max_length=20)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return _validate_phone_format(v)

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        from config import settings
        if v not in settings.SUPPORTED_LANGUAGES_LIST:
            raise ValueError("UNSUPPORTED_LANGUAGE")
        return v


class VerifyOTPRequest(BaseModel):
    model_config = {"extra": "forbid"}

    phone: str = Field(..., min_length=MIN_PHONE_LENGTH, max_length=MAX_PHONE_LENGTH)
    code: str = Field(..., min_length=OTP_CODE_LENGTH, max_length=OTP_CODE_LENGTH)
    device_id: str | None = Field(None, max_length=255)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return _validate_phone_format(v)

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("OTP_MUST_BE_DIGITS")
        return v


class RefreshTokenRequest(BaseModel):
    model_config = {"extra": "forbid"}

    refresh_token: str = Field(..., min_length=32)


class CreateOrderRequest(BaseModel):
    model_config = {"extra": "forbid"}

    plan_id: str = Field(..., min_length=1)
    quantity: int = Field(default=1, ge=1, le=10)
    idempotency_key: str = Field(default="", max_length=64)
    coupon_code: str = Field(default="", max_length=50)

    @field_validator("plan_id")
    @classmethod
    def validate_plan_id(cls, v: str) -> str:
        return _validate_uuid(v)

    @field_validator("idempotency_key")
    @classmethod
    def validate_idempotency(cls, v: str) -> str:
        return _validate_idempotency_key(v)


class DepositRequest(BaseModel):
    model_config = {"extra": "forbid"}

    amount: Decimal = Field(..., ge=Decimal("0"))
    payment_method: str = Field(..., min_length=1, max_length=30)
    idempotency_key: str = Field(default="", max_length=64)

    @field_validator("amount")
    @classmethod
    def validate_whole_amount(cls, v: Decimal) -> Decimal:
        if v % 1 != 0:
            raise ValueError("AMOUNT_MUST_BE_WHOLE_NUMBER")
        from app.core.constants import validate_amount_range
        validate_amount_range(int(v))
        return v

    @field_validator("payment_method")
    @classmethod
    def validate_payment_method(cls, v: str) -> str:
        from config import settings
        allowed = {m.lower() for m in settings.PAYMENT_PROVIDERS_LIST}
        if not allowed:
            allowed = {"zaincash", "qicard"}
        if v.lower() not in allowed:
            raise ValueError("UNSUPPORTED_PAYMENT_METHOD")
        return v.lower()

    @field_validator("idempotency_key")
    @classmethod
    def validate_idempotency(cls, v: str) -> str:
        return _validate_idempotency_key(v)


class AdminUpdateUserRequest(BaseModel):
    model_config = {"extra": "forbid"}

    name: Optional[str] = Field(None, min_length=1, max_length=MAX_NAME_LENGTH)
    language: Optional[str] = Field(None, max_length=10)
    timezone: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None
    role: Optional[str] = Field(None, max_length=20)

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: Optional[str]) -> Optional[str]:
        if v and v not in {"user", "admin", "superadmin"}:
            raise ValueError("INVALID_ROLE")
        return v


class CreatePlanRequest(BaseModel):
    model_config = {"extra": "forbid"}

    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)
    data_amount_mb: int = Field(..., ge=1, le=1_000_000)
    duration_days: int = Field(..., ge=1, le=365)
    price_usd: Decimal = Field(..., ge=Decimal("0.01"))
    price_iqd: int = Field(..., ge=0)
    markup_percentage: Decimal = Field(default=Decimal("20"), ge=0, le=1000)
    countries: str = Field(default="all", max_length=500)
    provider_bundle_id: str = Field(..., min_length=1, max_length=200)
    is_active: bool = True


class UpdatePlanRequest(BaseModel):
    model_config = {"extra": "forbid"}

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)
    data_amount_mb: Optional[int] = Field(None, ge=1, le=1_000_000)
    duration_days: Optional[int] = Field(None, ge=1, le=365)
    price_usd: Optional[Decimal] = Field(None, ge=Decimal("0.01"))
    price_iqd: Optional[int] = Field(None, ge=0)
    markup_percentage: Optional[Decimal] = Field(None, ge=0, le=1000)
    countries: Optional[str] = Field(None, max_length=500)
    provider_bundle_id: Optional[str] = Field(None, min_length=1, max_length=200)
    is_active: Optional[bool] = None
    sort_order: Optional[int] = Field(None, ge=0, le=32767)


class ProfileUpdateRequest(BaseModel):
    model_config = {"extra": "forbid"}

    name: Optional[str] = Field(None, min_length=1, max_length=MAX_NAME_LENGTH)
    language: Optional[str] = Field(None, max_length=10)
    timezone: Optional[str] = Field(None, max_length=50)

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        from config import settings
        if v not in settings.SUPPORTED_LANGUAGES_LIST:
            raise ValueError("UNSUPPORTED_LANGUAGE")
        return v


class PaginationParams(BaseModel):
    model_config = {"extra": "forbid"}

    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)


def validate_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


class AdminWalletAdjustRequest(BaseModel):
    model_config = {"extra": "forbid"}

    amount: int = Field(..., gt=0)
    reason: str = Field(default="", max_length=500)


class AdminRefundRequest(BaseModel):
    model_config = {"extra": "forbid"}

    order_id: str = Field(..., min_length=36, max_length=36)
    amount: Optional[int] = Field(None, gt=0)
    reason: str = Field(default="", max_length=500)
