from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from flask import Blueprint, g, request

from app.core.constants import DEFAULT_PAGINATION_LIMIT, MAX_PAGINATION_LIMIT
from app.core.database import get_session
from app.core.errors import AppError, ErrorCode
from app.core.middleware import require_auth
from app.core.response import UnifiedResponse
from app.models.inventory import EsimInventory
from app.models.plan import Plan
from app.providers.registry import ProviderRegistry
from app.services.activation_service import ActivationService
from app.services.inventory_service import InventoryService
from config import settings

logger = logging.getLogger("esim-ego")
admin_inventory_routes = Blueprint(
    "admin_inventory", __name__, url_prefix="/api/v1/admin/inventory",
)


@admin_inventory_routes.route("/import", methods=["POST"])
@require_auth(roles=["admin", "superadmin"])
def import_csv():
    if "file" not in request.files:
        return UnifiedResponse.from_error_code(ErrorCode.INVENTORY_INVALID_FILE)
    file_storage = request.files["file"]
    plan_id = request.form.get("plan_id", "")
    if not plan_id:
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_REQUIRED_FIELD)
    try:
        result = InventoryService.import_csv(
            file_storage, plan_id, g.user_id,
        )
        return UnifiedResponse.success(data=result, status=201)
    except AppError as exc:
        return UnifiedResponse.from_error_code(exc.code)


@admin_inventory_routes.route("/batches", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def list_batches():
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    limit = min(request.args.get("limit", DEFAULT_PAGINATION_LIMIT, type=int) or DEFAULT_PAGINATION_LIMIT, MAX_PAGINATION_LIMIT)
    result = InventoryService.list_batches(page=page, limit=limit)
    return UnifiedResponse.success(data=result)


@admin_inventory_routes.route("/iccid", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def list_inventory():
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    limit = min(request.args.get("limit", DEFAULT_PAGINATION_LIMIT, type=int) or DEFAULT_PAGINATION_LIMIT, MAX_PAGINATION_LIMIT)
    plan_id = request.args.get("plan_id")
    status = request.args.get("status")
    result = InventoryService.list_inventory(
        plan_id=plan_id, status=status, page=page, limit=limit,
    )
    return UnifiedResponse.success(data=result)


@admin_inventory_routes.route("/stats", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def get_stats():
    plan_id = request.args.get("plan_id")
    result = InventoryService.get_stats(plan_id=plan_id)
    return UnifiedResponse.success(data=result)


@admin_inventory_routes.route("/retry/<inventory_id>", methods=["POST"])
@require_auth(roles=["admin", "superadmin"])
def retry_activation(inventory_id):
    try:
        result = ActivationService.retry_activation(inventory_id)
        return UnifiedResponse.success(data=result)
    except AppError as exc:
        return UnifiedResponse.from_error_code(exc.code)


@admin_inventory_routes.route("/expiring", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def get_expiring():
    days = request.args.get("days", 7, type=int) or 7
    cutoff = datetime.now(timezone.utc) + timedelta(days=days)

    with get_session() as session:
        items = (
            session.query(EsimInventory)
            .filter(
                EsimInventory.status.in_(["activated", "active"]),
                EsimInventory.expires_at <= cutoff,
            )
            .order_by(EsimInventory.expires_at.asc())
            .limit(100)
            .all()
        )
        return UnifiedResponse.success(data={
            "expiring_within_days": days,
            "count": len(items),
            "items": [
                {
                    "id": str(i.id),
                    "iccid": i.iccid,
                    "plan_name": i.plan.name if i.plan else "",
                    "expires_at": i.expires_at.isoformat() if i.expires_at else None,
                }
                for i in items
            ],
        })


@admin_inventory_routes.route("/purchase", methods=["POST"])
@require_auth(roles=["admin", "superadmin"])
def purchase_inventory():
    data = request.get_json(silent=True) or {}
    plan_id = data.get("plan_id", "")
    try:
        quantity = int(data.get("quantity", 1))
    except (ValueError, TypeError):
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_INVALID_PARAMETER)
    if not plan_id:
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_MISSING_FIELD)
    if quantity < 1 or quantity > 100:
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_INVALID_PARAMETER)
    provider = ProviderRegistry.get_esim(settings.ESIM_PROVIDER) if settings.ESIM_PROVIDER else ProviderRegistry.get_esim("esimgo")
    purchased = []
    with get_session() as s:
        pid = UUID(plan_id) if isinstance(plan_id, str) else plan_id
        plan = s.query(Plan).filter(Plan.id == pid).first()
        if not plan:
            raise AppError(ErrorCode.PLAN_NOT_FOUND)
        bundle_id = plan.provider_bundle_id
    for _ in range(quantity):
        try:
            result = provider.create_order(bundle_id)
            esims = result.get("esims", [])
            for esim in esims:
                iccid = esim.get("iccid", "")
                if iccid:
                    with get_session() as s:
                        existing = s.query(EsimInventory).filter(EsimInventory.iccid == iccid).first()
                        if not existing:
                            record = EsimInventory(
                                iccid=iccid, plan_id=plan_id,
                                status="available",
                            )
                            s.add(record)
                            s.flush()
                            purchased.append(iccid)
        except Exception as exc:
            logger.error("Bulk purchase failed: %s", exc)
    return UnifiedResponse.success(data={"purchased": len(purchased), "iccids": purchased})
