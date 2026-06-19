__all__ = [
    "SERVER_TZ", "get_server_tz", "clear_tz_cache", "PHONE_REGEX", "MIN_AMOUNT_IQD", "MAX_AMOUNT_IQD",
    "validate_amount_range", "get_currency_min_max",
    "OTP_CODE_LENGTH", "MAX_PHONE_LENGTH", "MIN_PHONE_LENGTH",
    "MAX_NAME_LENGTH", "MAX_EMAIL_LENGTH", "REQUEST_ID_LENGTH",
    "ERROR_ID_LENGTH", "IDEMPOTENCY_KEY_LENGTH", "MAX_PAGINATION_LIMIT",
    "DEFAULT_PAGINATION_LIMIT", "BODY_SIZE_LIMIT",
    "MAX_RETRIES", "ACTIVATION_RETRY_DELAYS",
]

from decimal import Decimal

from pytz import timezone
from pytz.tzinfo import DstTzInfo

_CACHED_TZ: DstTzInfo | None = None


def get_server_tz() -> DstTzInfo:
    global _CACHED_TZ
    from config import settings
    tz_name = settings.DEFAULT_TIMEZONE
    try:
        from app.services.settings_service import SettingsService
        stored = SettingsService.get_timezone()
        if stored:
            tz_name = stored
    except Exception:
        pass
    if _CACHED_TZ is None or str(_CACHED_TZ) != tz_name:
        _CACHED_TZ = timezone(tz_name)
    return _CACHED_TZ


def clear_tz_cache() -> None:
    global _CACHED_TZ
    _CACHED_TZ = None


SERVER_TZ: DstTzInfo = get_server_tz()

PHONE_REGEX: str = r"^9647[0-9]{8,9}$"
MIN_AMOUNT_IQD: int = 250
MAX_AMOUNT_IQD: int = 100_000_000
OTP_CODE_LENGTH: int = 6
MAX_PHONE_LENGTH: int = 15
MIN_PHONE_LENGTH: int = 11
MAX_NAME_LENGTH: int = 100
MAX_EMAIL_LENGTH: int = 254
REQUEST_ID_LENGTH: int = 16
ERROR_ID_LENGTH: int = 16
IDEMPOTENCY_KEY_LENGTH: int = 64
MAX_PAGINATION_LIMIT: int = 100
DEFAULT_PAGINATION_LIMIT: int = 20
BODY_SIZE_LIMIT: int = 1_048_576

MAX_RETRIES: int = 5
ACTIVATION_RETRY_DELAYS: list[int] = [30, 120, 600, 3600]


def get_currency_min_max(currency: str | None = None) -> tuple[int, int]:
    """Return (min_amount, max_amount) for the given or official currency."""
    if currency is None:
        from app.services.settings_service import SettingsService
        currency = SettingsService.get_official_currency()
    if currency == "IQD":
        return MIN_AMOUNT_IQD, MAX_AMOUNT_IQD
    try:
        from app.services.currency_service import CurrencyService
        rate = CurrencyService.get_rate_value(currency, "IQD")
        min_iqd = int(Decimal(str(MIN_AMOUNT_IQD)) / rate)
        max_iqd = int(Decimal(str(MAX_AMOUNT_IQD)) / rate)
        return max(min_iqd, 1), min(max_iqd, 1_000_000_000)
    except Exception:
        return MIN_AMOUNT_IQD, MAX_AMOUNT_IQD


def validate_amount_range(amount: int, currency: str | None = None) -> None:
    """Raise AppError if amount is outside allowed range for the given/official currency."""
    from app.core.errors import AppError, ErrorCode
    min_amt, max_amt = get_currency_min_max(currency)
    if amount < min_amt or amount > max_amt:
        raise AppError(ErrorCode.VALIDATION_INVALID_AMOUNT)
