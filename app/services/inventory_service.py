from __future__ import annotations

import csv
import io
import logging
import re
from datetime import datetime, timezone
from uuid import UUID

from app.core.database import get_session
from app.core.errors import AppError, ErrorCode
from app.models.inventory import EsimInventory, ImportBatch

logger = logging.getLogger("esim-ego")

ICCID_PATTERN = re.compile(r"^\d{18,22}$")
MAX_FILE_SIZE = 5 * 1024 * 1024


class InventoryService:

    @staticmethod
    def import_csv(file_storage, plan_id: str, admin_id: str) -> dict:
        try:
            pid = UUID(plan_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        try:
            aid = UUID(admin_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)

        raw = file_storage.read()
        if len(raw) > MAX_FILE_SIZE:
            raise AppError(ErrorCode.VALIDATION_BODY_TOO_LARGE)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise AppError(ErrorCode.INVENTORY_INVALID_FILE)

        reader = csv.DictReader(io.StringIO(text))
        if "iccid" not in (reader.fieldnames or []):
            raise AppError(ErrorCode.INVENTORY_INVALID_FILE)

        rows = list(reader)
        if not rows:
            raise AppError(ErrorCode.INVENTORY_INVALID_FILE)

        iccids = []
        seen = set()
        for row in rows:
            raw_iccid = row.get("iccid", "").strip()
            if not raw_iccid:
                continue
            iccid = raw_iccid.replace(" ", "").replace("-", "")
            if not ICCID_PATTERN.match(iccid):
                continue
            if iccid in seen:
                continue
            seen.add(iccid)
            iccids.append(iccid)

        if not iccids:
            raise AppError(ErrorCode.INVENTORY_ICCID_INVALID)

        filename = getattr(file_storage, "filename", "unknown.csv")

        with get_session() as session:
            existing = set(
                row[0] for row in
                session.query(EsimInventory.iccid).filter(
                    EsimInventory.iccid.in_(iccids),
                ).all()
            )
            new_iccids = [i for i in iccids if i not in existing]

            batch = ImportBatch(
                filename=filename,
                plan_id=pid,
                total_count=len(iccids),
                success_count=len(new_iccids),
                error_count=len(iccids) - len(new_iccids),
                status="completed",
                created_by=aid,
                completed_at=datetime.now(timezone.utc),
            )
            session.add(batch)
            session.flush()

            for iccid in new_iccids:
                session.add(EsimInventory(
                    iccid=iccid,
                    plan_id=pid,
                    status="available",
                    batch_id=batch.id,
                ))
            session.flush()

            return {
                "batch_id": str(batch.id),
                "filename": filename,
                "total": len(iccids),
                "imported": len(new_iccids),
                "skipped": len(iccids) - len(new_iccids),
                "duplicates_in_file": len(rows) - len(iccids),
            }

    @staticmethod
    def list_batches(page: int = 1, limit: int = 20) -> dict:
        with get_session() as session:
            query = session.query(ImportBatch).order_by(ImportBatch.created_at.desc())
            total = query.count()
            offset = (page - 1) * limit
            items = query.offset(offset).limit(limit).all()
            return {
                "items": [InventoryService._format_batch(b) for b in items],
                "total": total,
                "page": page,
                "limit": limit,
            }

    @staticmethod
    def list_inventory(
        plan_id: str | None = None,
        status: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> dict:
        with get_session() as session:
            query = session.query(EsimInventory).order_by(EsimInventory.created_at.desc())
            if plan_id:
                try:
                    pid = UUID(plan_id)
                    query = query.filter(EsimInventory.plan_id == pid)
                except (ValueError, AttributeError):
                    raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
            if status:
                query = query.filter(EsimInventory.status == status)
            total = query.count()
            offset = (page - 1) * limit
            items = query.offset(offset).limit(limit).all()
            return {
                "items": [InventoryService._format_inventory(i) for i in items],
                "total": total,
                "page": page,
                "limit": limit,
            }

    @staticmethod
    def get_stats(plan_id: str | None = None) -> dict:
        with get_session() as session:
            query = session.query(EsimInventory)
            if plan_id:
                try:
                    pid = UUID(plan_id)
                    query = query.filter(EsimInventory.plan_id == pid)
                except (ValueError, AttributeError):
                    raise AppError(ErrorCode.VALIDATION_INVALID_UUID)

            total = query.count()
            available = query.filter(EsimInventory.status == "available").count()
            sold = query.filter(EsimInventory.status == "sold").count()
            processing = query.filter(EsimInventory.status == "processing").count()
            activated = query.filter(
                EsimInventory.status.in_(["activated", "active"]),
            ).count()
            expired = query.filter(EsimInventory.status == "expired").count()
            suspended = query.filter(EsimInventory.status == "suspended").count()
            revoked = query.filter(EsimInventory.status == "revoked").count()

            return {
                "total": total,
                "available": available,
                "sold": sold,
                "processing": processing,
                "activated": activated,
                "expired": expired,
                "suspended": suspended,
                "revoked": revoked,
            }

    @staticmethod
    def allocate_iccid(plan_id: UUID, order_item_id: UUID) -> dict:
        with get_session() as session:
            record = (
                session.query(EsimInventory)
                .filter(
                    EsimInventory.plan_id == plan_id,
                    EsimInventory.status == "available",
                )
                .with_for_update(skip_locked=True)
                .first()
            )
            if not record:
                raise AppError(ErrorCode.INVENTORY_INSUFFICIENT_STOCK)
            record.status = "sold"
            record.order_item_id = order_item_id
            record.sold_at = datetime.now(timezone.utc)
            session.flush()
            return {
                "id": str(record.id),
                "iccid": record.iccid,
                "status": record.status,
                "plan_id": str(record.plan_id),
                "sold_at": record.sold_at.isoformat(),
            }

    @staticmethod
    def get_by_order_item(order_item_id: UUID) -> dict | None:
        with get_session() as session:
            record = session.query(EsimInventory).filter(
                EsimInventory.order_item_id == order_item_id,
            ).first()
            if not record:
                return None
            return InventoryService._format_inventory(record)

    @staticmethod
    def _format_batch(batch: ImportBatch) -> dict:
        return {
            "id": str(batch.id),
            "filename": batch.filename,
            "plan_id": str(batch.plan_id),
            "plan_name": batch.plan.name if batch.plan else "",
            "total_count": batch.total_count,
            "success_count": batch.success_count,
            "error_count": batch.error_count,
            "status": batch.status,
            "created_by": str(batch.created_by),
            "created_at": batch.created_at.isoformat(),
            "completed_at": batch.completed_at.isoformat() if batch.completed_at else None,
        }

    @staticmethod
    def _format_inventory(item: EsimInventory) -> dict:
        return {
            "id": str(item.id),
            "iccid": item.iccid,
            "plan_id": str(item.plan_id),
            "plan_name": item.plan.name if item.plan else "",
            "status": item.status,
            "batch_id": str(item.batch_id) if item.batch_id else None,
            "order_item_id": str(item.order_item_id) if item.order_item_id else None,
            "sold_at": item.sold_at.isoformat() if item.sold_at else None,
            "activated_at": item.activated_at.isoformat() if item.activated_at else None,
            "expires_at": item.expires_at.isoformat() if item.expires_at else None,
            "activation_retries": item.activation_retries,
            "last_error": item.last_error,
            "data_usage_mb": item.data_usage_mb,
            "created_at": item.created_at.isoformat(),
        }
