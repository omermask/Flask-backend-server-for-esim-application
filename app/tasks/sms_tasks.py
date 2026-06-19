from __future__ import annotations

import logging

from app.celery_app import celery_app
from app.providers.registry import ProviderRegistry
from config import settings

logger = logging.getLogger("esim-ego")


@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=10,
    acks_late=True,
)
def send_otp_sms(self, phone: str, otp: str, lang: str = "en") -> dict:
    provider_name = settings.SMS_PROVIDER.lower() if settings.SMS_PROVIDER else ""
    if not provider_name:
        logger.warning("No SMS provider configured — OTP for %s: %s", phone, otp)
        return {"success": True, "simulated": True}
    try:
        sms = ProviderRegistry.get_sms(provider_name)
        if not sms:
            logger.error("SMS provider '%s' not found", provider_name)
            return {"success": False}
        result = sms.send_otp(phone, otp, lang=lang)
        return result
    except Exception as exc:
        logger.error("send_otp_sms failed for %s: %s", phone, exc)
        try:
            raise self.retry(exc=exc)
        except Exception:
            return {"success": False, "error": str(exc)}


@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=10,
    acks_late=True,
)
def send_custom_sms(self, phone: str, message: str, lang: str = "en") -> dict:
    provider_name = settings.SMS_PROVIDER.lower() if settings.SMS_PROVIDER else ""
    if not provider_name:
        logger.info("No SMS provider — message for %s: %s", phone, message[:50])
        return {"success": True, "simulated": True}
    try:
        sms = ProviderRegistry.get_sms(provider_name)
        if not sms:
            logger.error("SMS provider '%s' not found", provider_name)
            return {"success": False}
        result = sms.send_sms(phone, message, lang=lang)
        return result
    except Exception as exc:
        logger.error("send_custom_sms failed for %s: %s", phone, exc)
        try:
            raise self.retry(exc=exc)
        except Exception:
            return {"success": False, "error": str(exc)}
