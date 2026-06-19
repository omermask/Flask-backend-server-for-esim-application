from __future__ import annotations

import logging
from decimal import Decimal

import requests

from app.core.database import get_session
from app.core.errors import AppError, ErrorCode
from app.models.finance import ExchangeRate
from app.services.settings_service import SettingsService

logger = logging.getLogger("esim-ego")

FREE_API_URLS = [
    "https://open.er-api.com/v6/latest/USD",
    "https://api.exchangerate.host/latest?base=USD",
]


class CurrencyService:

    @staticmethod
    def set_rate(base: str, target: str, rate: Decimal, source: str = "manual") -> dict:
        if rate <= 0 or rate >= Decimal("1000000"):
            raise AppError(ErrorCode.EXCHANGE_RATE_INVALID)
        rate = rate.quantize(Decimal("0.000001"))
        with get_session() as session:
            existing = (
                session.query(ExchangeRate)
                .filter(
                    ExchangeRate.base_currency == base.upper(),
                    ExchangeRate.target_currency == target.upper(),
                )
                .first()
            )
            if existing:
                existing.rate = rate
                existing.source = source
                session.flush()
                record = existing
            else:
                record = ExchangeRate(
                    base_currency=base.upper(),
                    target_currency=target.upper(),
                    rate=rate,
                    source=source,
                )
                session.add(record)
                session.flush()
            return {
                "id": str(record.id),
                "base": record.base_currency,
                "target": record.target_currency,
                "rate": str(record.rate),
                "source": record.source,
            }

    @staticmethod
    def get_rate(base: str, target: str) -> dict:
        with get_session() as session:
            record = (
                session.query(ExchangeRate)
                .filter(
                    ExchangeRate.base_currency == base.upper(),
                    ExchangeRate.target_currency == target.upper(),
                )
                .first()
            )
            if not record:
                raise AppError(ErrorCode.EXCHANGE_RATE_NOT_FOUND)
            return {
                "id": str(record.id),
                "base": record.base_currency,
                "target": record.target_currency,
                "rate": str(record.rate),
                "source": record.source,
            }

    @staticmethod
    def list_rates() -> list[dict]:
        with get_session() as session:
            records = session.query(ExchangeRate).all()
            return [
                {
                    "id": str(r.id),
                    "base": r.base_currency,
                    "target": r.target_currency,
                    "rate": str(r.rate),
                    "source": r.source,
                }
                for r in records
            ]

    @staticmethod
    def get_rate_value(base: str, target: str) -> Decimal:
        """Return the numeric rate, or raise if not found."""
        try:
            return Decimal(CurrencyService.get_rate(base, target)["rate"])
        except AppError:
            raise AppError(ErrorCode.EXCHANGE_RATE_NOT_FOUND)

    @staticmethod
    def convert(amount: Decimal, from_currency: str, to_currency: str) -> dict:
        if from_currency.upper() == to_currency.upper():
            return {"amount": str(amount), "from": from_currency.upper(), "to": to_currency.upper(), "rate": "1.0"}
        rate = CurrencyService.get_rate_value(from_currency, to_currency)
        converted = amount * rate
        return {
            "amount": str(converted),
            "from": from_currency.upper(),
            "to": to_currency.upper(),
            "rate": str(rate),
        }

    @staticmethod
    def convert_to_official(amount: Decimal, from_currency: str) -> dict:
        """Convert amount from given currency to the official app currency."""
        official = SettingsService.get_official_currency()
        return CurrencyService.convert(amount, from_currency, official)

    @staticmethod
    def auto_fetch_rates() -> dict:
        """Fetch exchange rates from free public APIs and store them."""
        official = SettingsService.get_official_currency()
        data = None
        last_error = ""

        for url in FREE_API_URLS:
            try:
                resp = requests.get(url, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("result") == "success" or "rates" in data:
                        break
                    data = None
            except Exception as e:
                last_error = str(e)
                continue

        if not data or "rates" not in data:
            logger.warning("auto_fetch_rates: all APIs failed: %s", last_error)
            return {"success": False, "error": last_error or "All APIs failed"}

        rates_map = data["rates"]
        stored = 0
        base = data.get("base", "USD")
        with get_session() as session:
            for target, rate_val in rates_map.items():
                if target == base:
                    continue
                try:
                    d = Decimal(str(rate_val))
                    if d <= Decimal("0") or d >= Decimal("1000000"):
                        continue
                    rate = d.quantize(Decimal("0.000001"))
                except Exception:
                    continue
                existing = (
                    session.query(ExchangeRate)
                    .filter(
                        ExchangeRate.base_currency == base,
                        ExchangeRate.target_currency == target,
                    )
                    .first()
                )
                if existing:
                    existing.rate = rate
                    existing.source = "auto"
                else:
                    session.add(ExchangeRate(
                        base_currency=base,
                        target_currency=target,
                        rate=rate,
                        source="auto",
                    ))
                stored += 1
            session.flush()

        logger.info("auto_fetch_rates: stored %d rates base=%s official=%s", stored, base, official)
        return {"success": True, "stored": stored, "base": base}
