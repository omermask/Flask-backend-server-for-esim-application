from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID

from app.core.database import get_session
from app.core.errors import AppError, ErrorCode
from app.models.finance import TaxRate

logger = logging.getLogger("esim-ego")


class TaxService:

    @staticmethod
    def _validate_percentage(value: Decimal) -> None:
        if value < 0 or value > 100:
            raise AppError(ErrorCode.VALIDATION_INVALID_PARAMETER)

    @staticmethod
    def create_tax(name: str, percentage: Decimal, description: str = "") -> dict:
        TaxService._validate_percentage(percentage)
        with get_session() as session:
            record = TaxRate(
                name=name,
                percentage=percentage,
                description=description or None,
            )
            session.add(record)
            session.flush()
            return TaxService._format(record)

    @staticmethod
    def update_tax(tax_id: str, **kwargs) -> dict:
        try:
            tid = UUID(tax_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        if "percentage" in kwargs and kwargs["percentage"] is not None:
            TaxService._validate_percentage(kwargs["percentage"])
        with get_session() as session:
            record = session.query(TaxRate).filter(TaxRate.id == tid).first()
            if not record:
                raise AppError(ErrorCode.TAX_NOT_FOUND)
            for key, value in kwargs.items():
                if value is not None and hasattr(record, key):
                    setattr(record, key, value)
            session.flush()
            return TaxService._format(record)

    @staticmethod
    def list_taxes() -> list[dict]:
        with get_session() as session:
            records = session.query(TaxRate).all()
            return [TaxService._format(r) for r in records]

    @staticmethod
    def get_active_taxes() -> list[TaxRate]:
        with get_session() as session:
            return session.query(TaxRate).filter(TaxRate.is_active.is_(True)).all()

    @staticmethod
    def calculate_tax(amount_iqd: int) -> dict:
        total_tax = 0
        applied: list[dict] = []
        with get_session() as session:
            active = (
                session.query(TaxRate)
                .filter(TaxRate.is_active.is_(True))
                .all()
            )
            for tax in active:
                tax_amount = round(Decimal(str(amount_iqd)) * tax.percentage / Decimal("100"))
                total_tax += tax_amount
                applied.append({
                    "name": tax.name,
                    "percentage": str(tax.percentage),
                    "amount": tax_amount,
                })
            return {
                "total_tax": total_tax,
                "applied": applied,
            }

    @staticmethod
    def _format(record: TaxRate) -> dict:
        return {
            "id": str(record.id),
            "name": record.name,
            "percentage": str(record.percentage),
            "is_active": record.is_active,
            "description": record.description,
        }
