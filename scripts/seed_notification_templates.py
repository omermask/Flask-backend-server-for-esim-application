from __future__ import annotations

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("seed")


TEMPLATES = {
    "esim_activated": {
        "en": "eSIM Activated\nYour eSIM has been activated successfully",
        "ar": "تم تفعيل الشريحة الإلكترونية\nتم تفعيل شريحة eSIM الخاصة بك بنجاح",
        "data_schema": {"iccid": "string"},
        "description": "Sent when an eSIM is activated or installed",
    },
    "order_confirmed": {
        "en": "Order Confirmed\n{plan_name} x{quantity} activated successfully",
        "ar": "تم تأكيد الطلب\nتم تفعيل {plan_name} x{quantity} بنجاح",
        "data_schema": {"plan_name": "string", "quantity": "integer"},
        "description": "Sent when an order is confirmed and activated",
    },
    "deposit_received": {
        "en": "Deposit Received\n{amount} IQD has been added to your wallet",
        "ar": "تم استلام الإيداع\nتم إضافة {amount} دينار إلى محفظتك",
        "data_schema": {"amount": "number", "balance": "number"},
        "description": "Sent when a wallet deposit is confirmed",
    },
    "data_usage": {
        "en": "Data Usage Updated\nYou have used {usage_mb}MB of data",
        "ar": "تحديث استهلاك البيانات\nلقد استهلكت {usage_mb} ميغابايت من البيانات",
        "data_schema": {"usage_mb": "number", "iccid": "string"},
        "description": "Sent when data usage is reported via callback",
    },
    "bundle_topup": {
        "en": "Bundle Topup\nYour eSIM balance has been topped up",
        "ar": "تم تعبئة الرصيد\nتم تعبئة رصيد شريحة eSIM الخاصة بك",
        "data_schema": {"iccid": "string", "alert_type": "string"},
        "description": "Sent when a topup callback is received",
    },
    "welcome_country": {
        "en": "Welcome\nWelcome to {country_name}",
        "ar": "مرحباً بك\nمرحباً بك في {country_name}",
        "data_schema": {"country_name": "string", "iccid": "string"},
        "description": "Sent when the eSIM connects to a new country network",
    },
    "bundle_started": {
        "en": "Bundle Started\nYour data bundle has started",
        "ar": "بدأت الباقة\nبدأت باقة البيانات الخاصة بك",
        "data_schema": {"usage_mb": "number", "iccid": "string"},
        "description": "Sent when the eSIM first uses data after activation",
    },
}


def seed() -> None:
    from app import create_app
    from app.services.notification_template_service import NotificationTemplateService

    app = create_app()
    with app.app_context():
        for key, tpl in TEMPLATES.items():
            translations = {lang: tpl[lang] for lang in ("en", "ar") if lang in tpl}
            result = NotificationTemplateService.upsert(
                key=key,
                translations=translations,
                data_schema=tpl["data_schema"],
                description=tpl["description"],
            )
            logger.info("  %s — %s", key, result["id"])


if __name__ == "__main__":
    logger.info("Seeding notification templates...")
    seed()
    logger.info("Done.")
