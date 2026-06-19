from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


ALLOWED_SMS_PROVIDERS: frozenset[str] = frozenset({"bulksmsiraq", "otpiq"})
ALLOWED_ESIM_PROVIDERS: frozenset[str] = frozenset({"esimgo"})
ALLOWED_PAYMENT_METHODS: frozenset[str] = frozenset({"zaincash", "qicard"})
ALLOWED_PURCHASE_MODES: frozenset[str] = frozenset({"hybrid", "inventory_only", "on_demand_only"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="forbid",
    )

    ENVIRONMENT: str = "production"
    SECRET_KEY: str
    API_KEYS_ENCRYPTION_KEY: str

    FLASK_HOST: str = "0.0.0.0"
    FLASK_PORT: int = 5000
    FLASK_WORKERS: int = 4

    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "esim_ego"
    DB_USER: str = "postgres"
    DB_PASSWORD: str

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""

    JWT_ACCESS_TOKEN_EXPIRY_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRY_DAYS: int = 7

    RATE_LIMIT_AUTH_PER_MINUTE: int = 5
    RATE_LIMIT_API_PER_MINUTE: int = 30
    RATE_LIMIT_ADMIN_PER_MINUTE: int = 60

    SMS_PROVIDER: str = ""
    BULKSMSIRAQ_API_KEY: str = ""
    BULKSMSIRAQ_SENDER_ID: str = "ESIMEGO"
    BULKSMSIRAQ_BASE_URL: str = "https://gateway.standingtech.com/api/v5"
    BULKSMSIRAQ_SANDBOX: bool = False
    BULKSMSIRAQ_SANDBOX_BASE_URL: str = ""
    BULKSMSIRAQ_TIMEOUT: int = 10
    OTPIQ_API_KEY: str = ""
    OTPIQ_SENDER_ID: str = "ESIMEGO"
    OTPIQ_API_BASE_URL: str = "https://api.otpiq.com/api"
    OTPIQ_SANDBOX: bool = False
    OTPIQ_SANDBOX_BASE_URL: str = ""
    OTPIQ_TIMEOUT: int = 10
    OTPIQ_WEBHOOK_SECRET: str = ""
    OTPIQ_WEBHOOK_URL: str = ""

    PAYMENT_PROVIDERS: str = ""
    ZAINCASH_CLIENT_ID: str = ""
    ZAINCASH_CLIENT_SECRET: str = ""
    ZAINCASH_MERCHANT_ID: str = ""
    ZAINCASH_SECRET: str = ""
    ZAINCASH_MSISDN: str = ""
    ZAINCASH_REDIRECT_URL: str = ""
    ZAINCASH_ORDER_PREFIX: str = "esim_"
    ZAINCASH_TEST: bool = True
    ZAINCASH_TIMEOUT: int = 15
    FRONTEND_URL: str = ""
    FIB_CLIENT_ID: str = ""
    FIB_CLIENT_SECRET: str = ""
    FIB_BASE_URL: str = "https://api.fib.iq"
    FIB_SANDBOX: bool = False
    FIB_SANDBOX_BASE_URL: str = ""
    QICARD_USERNAME: str = ""
    QICARD_PASSWORD: str = ""
    QICARD_TERMINAL_ID: str = ""
    QICARD_SANDBOX: bool = True
    QICARD_TEST: bool = True
    QICARD_BASE_URL: str = "https://api.qi.iq/api/v1"
    QICARD_CURRENCY: str = "IQD"
    QICARD_LOCALE: str = "en_US"
    QICARD_PRODUCT_CODE: str = ""
    QICARD_TIMEOUT: int = 15
    QICARD_FINISH_URL: str = ""
    QICARD_NOTIFICATION_URL: str = ""
    QICARD_WEBHOOK_PUBLIC_KEY: str = ""

    ESIM_PROVIDER: str = ""
    FCM_SERVICE_ACCOUNT_JSON: str = ""

    ESIMGO_API_KEY: str = ""
    ESIMGO_API_BASE_URL: str = "https://api.esim-go.com/v2.5"
    ESIMGO_SANDBOX: bool = False
    ESIMGO_SANDBOX_BASE_URL: str = ""
    ESIMGO_TIMEOUT: int = 30

    USD_TO_IQD_RATE: int = 1500  # Deprecated: fallback only, use ExchangeRate table + CurrencyService
    PURCHASE_MODE: str = "hybrid"

    DEFAULT_LANGUAGE: str = "en"
    SUPPORTED_LANGUAGES: str = "en,ar,fr,tr,ku,fa,ur,de,es,ru,zh,pt"
    DEFAULT_TIMEZONE: str = "Asia/Baghdad"

    LOG_LEVEL: str = "WARNING"
    LOG_FILE: str = "logs/esim-ego.log"
    LOG_MAX_BYTES: int = 104_857_600
    LOG_BACKUP_COUNT: int = 10

    CORS_ORIGINS: str = ""

    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    ADMIN_IP_WHITELIST: str = ""
    TOTP_ISSUER_NAME: str = "ESIM EGO"

    OTP_MAX_ATTEMPTS: int = 3
    OTP_EXPIRY_MINUTES: int = 5
    OTP_BLOCK_MINUTES: int = 10

    @field_validator("SECRET_KEY", mode="before")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if not v or v == "change_this_to_a_random_64_char_string":
            raise ValueError("SECRET_KEY must be changed to a secure random value")
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v

    @field_validator("API_KEYS_ENCRYPTION_KEY", mode="before")
    @classmethod
    def validate_encryption_key(cls, v: str) -> str:
        if not v or v == "change_this_to_a_random_32_char_string":
            raise ValueError("API_KEYS_ENCRYPTION_KEY must be changed")
        if len(v) < 16:
            raise ValueError("API_KEYS_ENCRYPTION_KEY must be at least 16 characters")
        return v

    @field_validator("SMS_PROVIDER", mode="before")
    @classmethod
    def validate_sms_provider(cls, v: str) -> str:
        if v and v.lower() not in ALLOWED_SMS_PROVIDERS:
            raise ValueError(f"SMS_PROVIDER must be one of: {', '.join(sorted(ALLOWED_SMS_PROVIDERS))}")
        return v.lower() if v else v

    @field_validator("ESIM_PROVIDER", mode="before")
    @classmethod
    def validate_esim_provider(cls, v: str) -> str:
        if v and v.lower() not in ALLOWED_ESIM_PROVIDERS:
            raise ValueError(f"ESIM_PROVIDER must be one of: {', '.join(sorted(ALLOWED_ESIM_PROVIDERS))}")
        return v.lower() if v else v

    @field_validator("PURCHASE_MODE", mode="before")
    @classmethod
    def validate_purchase_mode(cls, v: str) -> str:
        if v.lower() not in ALLOWED_PURCHASE_MODES:
            raise ValueError(f"PURCHASE_MODE must be one of: {', '.join(sorted(ALLOWED_PURCHASE_MODES))}")
        return v.lower()

    @field_validator("ADMIN_IP_WHITELIST", mode="before")
    @classmethod
    def validate_ip_whitelist(cls, v: str) -> str:
        import ipaddress
        if not v:
            return v
        for entry in v.split(","):
            entry = entry.strip()
            if not entry:
                continue
            try:
                ipaddress.ip_network(entry, strict=False)
            except ValueError:
                raise ValueError(f"Invalid IP/CIDR in ADMIN_IP_WHITELIST: {entry}")
        return v

    @field_validator("ENVIRONMENT", mode="before")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        if v.lower() not in {"development", "staging", "production"}:
            raise ValueError("ENVIRONMENT must be development, staging, or production")
        return v.lower()

    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    @property
    def SUPPORTED_LANGUAGES_LIST(self) -> list[str]:
        return [lang.strip() for lang in self.SUPPORTED_LANGUAGES.split(",")]

    @property
    def PAYMENT_PROVIDERS_LIST(self) -> list[str]:
        return [p.strip().lower() for p in self.PAYMENT_PROVIDERS.split(",") if p.strip()]

    @property
    def ADMIN_IP_WHITELIST_LIST(self) -> list[str]:
        return [ip.strip() for ip in self.ADMIN_IP_WHITELIST.split(",") if ip.strip()]

    @property
    def CORS_ORIGINS_LIST(self) -> list[str]:
        origins = [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]
        if self.ENVIRONMENT == "development":
            origins.append("*")
        return origins

    @property
    def IS_DEVELOPMENT(self) -> bool:
        return self.ENVIRONMENT == "development"

    @property
    def IS_PRODUCTION(self) -> bool:
        return self.ENVIRONMENT == "production"

    BASE_DIR: ClassVar[Path] = Path(__file__).resolve().parent


try:
    settings = Settings()
except Exception as e:
    import sys
    print(f"CRITICAL: Configuration error: {e}", file=sys.stderr)
    print("Server cannot start. Fix configuration and try again.", file=sys.stderr)
    sys.exit(1)
