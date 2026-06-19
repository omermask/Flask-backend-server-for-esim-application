from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import joinedload

from app.core.database import get_session
from app.core.errors import AppError, ErrorCode
from app.models.order import Order

logger = logging.getLogger("esim-ego")


class InvoiceService:

    @staticmethod
    def generate_invoice(user_id: str, order_id: str) -> bytes:
        uid = UUID(user_id)
        try:
            oid = UUID(order_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        with get_session() as session:
            order = (
                session.query(Order)
                .filter(Order.id == oid, Order.user_id == uid)
                .options(
                    joinedload(Order.items),
                    joinedload(Order.plan),
                    joinedload(Order.payments),
                )
                .first()
            )
            if not order:
                raise AppError(ErrorCode.INVOICE_NOT_FOUND)
            return InvoiceService._build_pdf(order)

    @staticmethod
    def _build_pdf(order: Order) -> bytes:
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_page()

        pdf.set_font("Helvetica", "B", 20)
        pdf.cell(0, 15, "ESIM EGO", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, "eSIM Invoice", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(10)

        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, f"Invoice #{str(order.id)[:8].upper()}", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, f"Date: {order.created_at.strftime('%Y-%m-%d %H:%M')}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(5)

        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 8, "Order Details", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)

        plan_name = order.plan.name if order.plan else "N/A"
        pdf.cell(0, 6, f"Plan: {plan_name}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, f"Quantity: {order.quantity}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, f"Status: {order.status}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(5)

        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 8, "Items", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)

        col_widths = [60, 40, 40, 40]
        headers = ["ICCID", "Status", "Activated", "Expires"]
        for i, header in enumerate(headers):
            pdf.cell(col_widths[i], 7, header, border=1)
        pdf.ln()

        pdf.set_font("Helvetica", "", 8)
        for item in order.items:
            data = [
                item.esim_iccid or "Pending",
                item.status,
                item.activated_at.strftime("%Y-%m-%d") if item.activated_at else "-",
                item.expires_at.strftime("%Y-%m-%d") if item.expires_at else "-",
            ]
            for i, d in enumerate(data):
                pdf.cell(col_widths[i], 6, d, border=1)
            pdf.ln()

        pdf.ln(10)
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, f"Total: {order.total_price_iqd:,} IQD", align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(15)

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        pdf.set_font("Helvetica", "I", 8)
        pdf.cell(0, 5, f"Generated on {now}", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 5, "ESIM EGO - eSIM Services", align="C")

        return pdf.output()
