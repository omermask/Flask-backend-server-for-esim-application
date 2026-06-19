#!/usr/bin/env python3
"""Fill missing ErrorCode translations for ar, en, ku."""

import json
from pathlib import Path

TRANSLATIONS_DIR = Path(__file__).resolve().parent.parent / "app" / "translations"

# Arabic missing translations
AR_TRANSLATIONS = {
    "support_ticket_not_found": "تذكرة الدعم غير موجودة",
    "support_ticket_closed": "تذكرة الدعم مغلقة. لا يمكن إضافة ردود جديدة",
    "support_ticket_access_denied": "ليس لديك صلاحية الوصول إلى هذه التذكرة",
    "support_message_empty": "لا يمكن إرسال رسالة فارغة",
    "support_cannot_assign_to_self": "لا يمكن تعيين التذكرة إلى نفسك",
    "referral_code_not_found": "رمز الإحالة غير موجود",
    "referral_code_invalid": "رمز الإحالة غير صالح",
    "referral_self_referral": "لا يمكن استخدام رمز الإحالة الخاص بك",
    "referral_already_referred": "تمت إحالتك مسبقاً بواسطة مستخدم آخر",
    "referral_not_qualified": "أنت غير مؤهل للحصول على مكافأة الإحالة",
    "setting_not_found": "الإعداد غير موجود",
    "setting_key_exists": "مفتاح الإعداد موجود مسبقاً",
    "admin_cannot_modify_self": "لا يمكن تعديل حساب المسؤول الخاص بك",
    "feature_disabled": "هذه الميزة معطلة حالياً",
    "invalid_state": "الحالة غير صالحة لهذه العملية",
}

# English missing translations
EN_TRANSLATIONS = {
    "support_ticket_not_found": "Support ticket not found",
    "support_ticket_closed": "Support ticket is closed. Cannot add new replies",
    "support_ticket_access_denied": "You do not have access to this ticket",
    "support_message_empty": "Cannot send an empty message",
    "support_cannot_assign_to_self": "Cannot assign ticket to yourself",
    "referral_code_not_found": "Referral code not found",
    "referral_code_invalid": "Invalid referral code",
    "referral_self_referral": "Cannot use your own referral code",
    "referral_already_referred": "You have already been referred by another user",
    "referral_not_qualified": "You are not qualified for the referral reward",
    "setting_not_found": "Setting not found",
    "setting_key_exists": "Setting key already exists",
    "admin_cannot_modify_self": "Cannot modify your own admin account",
    "feature_disabled": "This feature is currently disabled",
    "invalid_state": "Invalid state for this operation",
}

# Kurdish Sorani missing translations
KU_TRANSLATIONS = {
    "support_ticket_not_found": "تکەتی پشتگیری نەدۆزرایەوە",
    "support_ticket_closed": "تکەتی پشتگیری داخراوە. ناتوانیت وەڵامی نوێ زیاد بکەیت",
    "support_ticket_access_denied": "تۆ مۆڵەتی دەستگەیشتن بەم تکەتەت نییە",
    "support_message_empty": "ناتوانیت نامەی بەتاڵ بنێریت",
    "support_cannot_assign_to_self": "ناتوانیت تکەتەکە بۆ خۆت دابین بکەیت",
    "referral_code_not_found": "کۆدی ڕێکەوتن نەدۆزرایەوە",
    "referral_code_invalid": "کۆدی ڕێکەوتن نادروستە",
    "referral_self_referral": "ناتوانیت کۆدی ڕێکەوتنی خۆت بەکاربهێنیت",
    "referral_already_referred": "پێشتر لەلایەن بەکارهێنەرێکی ترەوە ڕێکەوتراویت",
    "referral_not_qualified": "تۆ شایستەی خەڵاتی ڕێکەوتن نیت",
    "setting_not_found": "ڕێکخستن نەدۆزرایەوە",
    "setting_key_exists": "کلیلی ڕێکخستن پێشتر هەیە",
    "admin_cannot_modify_self": "ناتوانیت هەژماری بەڕێوەبەری خۆت دەستکاری بکەیت",
    "feature_disabled": "ئەم تایبەتمەندییە لە ئێستادا ناچالاککراوە",
    "invalid_state": "باری نادروست بۆ ئەم کارە",
    "user_not_found": "بەکارهێنەر نەدۆزرایەوە",
    "user_account_deleted": "هەژماری بەکارهێنەر سڕدراوەتەوە",
    "esim_not_found": "eSIM نەدۆزرایەوە",
    "esim_expired": "eSIM بەسەرچووە",
    "esim_invalid_status": "باری eSIM نادروستە بۆ ئەم کارە",
    "inventory_not_found": "مەخزنی eSIM نەدۆزرایەوە",
    "inventory_insufficient_stock": "پێداویستی eSIM لە مەخزندا تەواو نییە",
    "inventory_iccid_duplicate": "ICCID تەواو دووبارەیە لە مەخزندا",
    "inventory_invalid_file": "پەڕگەی هێنراو نادروستە. تکایە CSV پشتڕاست بکەوە",
    "inventory_iccid_invalid": "ICCID نادروستە",
    "invoice_not_found": "پەیامەت نەدۆزرایەوە",
    "coupon_not_found": "کۆدی کەمکردنەوە نەدۆزرایەوە",
    "coupon_expired": "کۆدی کەمکردنەوە بەسەرچووە",
    "coupon_exhausted": "کۆدی کەمکردنەوە تەواو بووە",
    "coupon_invalid_for_plan": "کۆدی کەمکردنەوە بۆ ئەم پلانە ناڕێکە",
    "coupon_min_order_not_met": "نرخی داواکاری کەمترە لە کەمترین پێویست بۆ کۆدی کەمکردنەوە",
    "coupon_already_used": "ئەم کۆدی کەمکردنەوە پێشتر بەکارهاتووە",
    "tax_not_found": "باج نەدۆزرایەوە",
    "tax_inactive": "باج ناچالاکە",
    "exchange_rate_not_found": "نرخی ئاڵوگۆڕ نەدۆزرایەوە",
    "exchange_rate_invalid": "نرخی ئاڵوگۆڕ نادروستە",
    "refund_not_found": "گەڕاندنەوە نەدۆزرایەوە",
    "refund_invalid_amount": "بڕی گەڕاندنەوە نادروستە",
    "refund_exceeds_order": "بڕی گەڕاندنەوە لە نرخی داواکاری زیاترە",
    "refund_order_not_paid": "داواکاری نەدراوە. ناتوانیت گەڕاندنەوە بکەیت",
    "report_invalid_period": "ماوەی ڕاپۆرت نادروستە",
    "activation_failed": "چالاککردنی eSIM سەرکەوتوو نەبوو",
    "activation_timeout": "چالاککردنی eSIM کاتی بەسەرچوو",
    "activation_max_retries": "زۆرترین هەوڵی چالاککردن تەواو بوو",
    "wallet_not_found": "گەنجینە نەدۆزرایەوە",
    "wallet_transaction_failed": "مامەڵەی گەنجینە سەرکەوتوو نەبوو",
    "wallet_insufficient_available": "ڕێژەی بەردەست لە گەنجینەدا تەواو نییە",
    "wallet_freeze_not_found": "بەستنی گەنجینە نەدۆزرایەوە",
    "wallet_freeze_exceeds_balance": "بڕی بەستن لە ڕێژەی گەنجینە زیاترە",
    "wallet_freeze_already_released": "بەستنی گەنجینە پێشتر بڵاوکراوەتەوە",
    "order_already_processed": "ئەم داواکارییە پێشتر جێبەجێکراوە",
    "order_expired": "ئەم داواکارییە کاتی بەسەرچووە",
    "order_cancelled": "ئەم داواکارییە هەڵوەشاوەتەوە",
    "order_invalid_status": "باری داواکاری نادروستە بۆ ئەم کارە",
    "plan_unavailable": "ئەم پلانە لە ئێستادا بەردەست نییە",
    "plan_inactive": "ئەم پلانە چیتر چالاک نییە",
    "provider_bundle_not_found": "بەستەری داواکراو لە دابینکەر نەدۆزرایەوە",
    "provider_insufficient_balance": "ڕێژەی تەواو نییە لە دابینکەر. پەیوەندی بکە بە پشتگیری",
    "provider_invalid_response": "وەڵامێکی نادروست لە دابینکەری خزمەتگوزاری وەرگیرا",
    "provider_rate_limited": "سنووری داواکاری دابینکەر تێپەڕێندرا. تکایە دواتر هەوڵبدەوە",
    "rate_limit_auth_exceeded": "هەوڵی چوونەژوورەوەی زۆر. تکایە دواتر هەوڵبدەوە",
    "payment_timeout": "داواکاری پارەدان کاتی بەسەرچوو. تکایە هەوڵبدەوە",
    "payment_cancelled": "پارەدان هەڵوەشایەوە",
    "payment_invalid_signature": "واژۆی پارەدان نادروستە. پشکنینی ئاسایش سەرکەوتوو نەبوو",
    "payment_duplicate": "پارەدانی دووبارە دۆزرایەوە. تکایە باری داواکاری بپشکنە",
    "payment_refund_failed": "گەڕاندنەوەی پارە سەرکەوتوو نەبوو",
    "payment_method_unsupported": "ئەم ڕێگای پارەدان پشتگیری ناکرێت",
    "validation_idempotency_reuse": "داواکاری بەم کلیلی idempotency پێشتر جێبەجێکراوە",
    "validation_invalid_parameter": "بڕی پارامیتەر نادروستە",
}

def fill_translations(lang: str, new_entries: dict):
    path = TRANSLATIONS_DIR / f"{lang}.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    existing = set(data.keys())
    added = 0
    for key, msg in new_entries.items():
        if key not in existing:
            data[key] = msg
            added += 1

    # Sort keys alphabetically for consistency
    sorted_data = dict(sorted(data.items()))

    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted_data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"{lang}.json: {added} translations added ({len(data)} total)")


if __name__ == "__main__":
    fill_translations("ar", AR_TRANSLATIONS)
    fill_translations("en", EN_TRANSLATIONS)
    fill_translations("ku", KU_TRANSLATIONS)
    print("\nDone! All missing translations filled.")
