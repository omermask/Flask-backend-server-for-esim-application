from __future__ import annotations

import logging

from flask import Blueprint, make_response, request

from app.core.middleware import require_auth
from app.core.response import UnifiedResponse
from app.core.errors import ErrorCode
from app.core.validators import CreatePlanRequest, UpdatePlanRequest, PaginationParams
from app.services.plan_service import PlanService

logger = logging.getLogger("esim-ego")
plan_routes = Blueprint("plans", __name__, url_prefix="/api/v1/plans")
admin_plan_routes = Blueprint("admin_plans", __name__, url_prefix="/api/v1/admin/plans")


@plan_routes.route("", methods=["GET"])
def list_plans():
    pagination = PaginationParams(
        page=request.args.get("page", 1, type=int),
        limit=request.args.get("limit", 20, type=int),
    )
    result = PlanService.list_plans(
        page=pagination.page,
        limit=pagination.limit,
        active_only=True,
    )
    resp = make_response(UnifiedResponse.success(data=result))
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp


@plan_routes.route("/<plan_id>", methods=["GET"])
def get_plan(plan_id: str):
    plan = PlanService.get_plan(plan_id)
    resp = make_response(UnifiedResponse.success(data=plan))
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp


@admin_plan_routes.route("", methods=["POST"])
@require_auth(roles=["admin", "superadmin"])
def create_plan():
    data = request.get_json(silent=True) or {}
    validator = CreatePlanRequest(**data)
    plan = PlanService.create_plan(validator.model_dump())
    return UnifiedResponse.success(data=plan, status=201)


@admin_plan_routes.route("/<plan_id>", methods=["PUT"])
@require_auth(roles=["admin", "superadmin"])
def update_plan(plan_id: str):
    data = request.get_json(silent=True) or {}
    validator = UpdatePlanRequest(**data)
    filtered = {k: v for k, v in validator.model_dump().items() if v is not None}
    plan = PlanService.update_plan(plan_id, filtered)
    return UnifiedResponse.success(data=plan)


@admin_plan_routes.route("/delete-all", methods=["DELETE"])
@require_auth(roles=["admin", "superadmin"])
def delete_all_plans():
    count = PlanService.delete_all_plans()
    return UnifiedResponse.success(data={"deleted": count})


@admin_plan_routes.route("/<plan_id>", methods=["DELETE"])
@require_auth(roles=["admin", "superadmin"])
def delete_plan(plan_id: str):
    PlanService.delete_plan(plan_id)
    return UnifiedResponse.success(data={"message": "Plan deleted"})


@admin_plan_routes.route("", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def list_all_plans():
    pagination = PaginationParams(
        page=request.args.get("page", 1, type=int),
        limit=request.args.get("limit", 20, type=int),
    )
    result = PlanService.list_all_plans(
        page=pagination.page,
        limit=pagination.limit,
    )
    return UnifiedResponse.success(data=result)


@admin_plan_routes.route("/sync-catalogue", methods=["POST"])
@require_auth(roles=["admin", "superadmin"])
def sync_catalogue():
    logger.warning("sync-catalogue called but is disabled")
    return UnifiedResponse.success(data={"message": "Sync disabled. Use import from catalogue screen.", "created": 0, "updated": 0, "skipped": 0, "errors": []})


@admin_plan_routes.route("/catalogue", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def get_catalogue():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("perPage", 50, type=int)
    all_pages = request.args.get("allPages", "false").lower() == "true"
    force = request.args.get("force", "false").lower() == "true"
    network = request.args.get("network", None)
    result = PlanService.get_provider_catalogue(page=page, perPage=per_page, all_pages=all_pages, force=force, network=network)
    return UnifiedResponse.success(data=result)


@admin_plan_routes.route("/catalogue/networks", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def get_networks():
    result = PlanService.get_network_index()
    return UnifiedResponse.success(data=result)


@admin_plan_routes.route("/catalogue/build-network-index", methods=["POST"])
@require_auth(roles=["admin", "superadmin"])
def build_network_index():
    result = PlanService.build_network_index()
    return UnifiedResponse.success(data=result)


@admin_plan_routes.route("/catalogue/bundle/<bundle_name>", methods=["GET"])
@require_auth(roles=["admin", "superadmin"])
def get_catalogue_bundle(bundle_name: str):
    result = PlanService.get_provider_catalogue_bundle(bundle_name)
    return UnifiedResponse.success(data=result)


@admin_plan_routes.route("/catalogue/import", methods=["POST"])
@require_auth(roles=["admin", "superadmin"])
def import_from_catalogue():
    data = request.get_json(silent=True) or {}
    bundle_names = data.get("bundles", [])
    if not isinstance(bundle_names, list) or not bundle_names:
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_INVALID_PARAMETER, data={"message": "bundles must be a non-empty array"})
    result = PlanService.import_catalogue_bundles(bundle_names)
    return UnifiedResponse.success(data=result)


@admin_plan_routes.route("/batch", methods=["DELETE"])
@require_auth(roles=["admin", "superadmin"])
def batch_delete_plans():
    data = request.get_json(silent=True) or {}
    ids = data.get("ids", [])
    if not isinstance(ids, list) or not ids:
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_INVALID_PARAMETER, data={"message": "ids must be a non-empty array"})
    logger.info("batch_delete_plans: received %d ids", len(ids))
    results: list[dict] = []
    for pid in ids:
        try:
            PlanService.delete_plan(pid)
            results.append({"id": pid, "success": True})
        except Exception as e:
            logger.warning("batch_delete_plans: plan %s failed: %s", pid, e)
            results.append({"id": pid, "success": False, "error": str(e)})
    succeeded = sum(1 for r in results if r["success"])
    logger.info("batch_delete_plans: %d succeeded, %d failed", succeeded, len(results) - succeeded)
    return UnifiedResponse.success(data={"results": results, "total": len(results), "deleted": succeeded})


@admin_plan_routes.route("/batch", methods=["PUT"])
@require_auth(roles=["admin", "superadmin"])
def batch_update_plans():
    data = request.get_json(silent=True) or {}
    updates = data.get("updates", [])
    if not isinstance(updates, list) or not updates:
        return UnifiedResponse.from_error_code(ErrorCode.VALIDATION_INVALID_PARAMETER, data={"message": "updates must be a non-empty array"})
    results: list[dict] = []
    for item in updates:
        plan_id = item.get("id", "")
        if not plan_id:
            results.append({"id": plan_id, "success": False, "error": "missing id"})
            continue
        try:
            fields = {k: v for k, v in item.items() if k != "id" and v is not None}
            filtered = {k: v for k, v in fields.items() if k in {
                "name", "description", "data_amount_mb", "duration_days",
                "price_usd", "price_iqd", "markup_percentage",
                "countries", "is_active", "sort_order",
            }}
            if not filtered:
                results.append({"id": plan_id, "success": False, "error": "no valid fields"})
                continue
            plan = PlanService.update_plan(plan_id, filtered)
            results.append({"id": plan_id, "success": True, "plan": plan})
        except Exception as e:
            results.append({"id": plan_id, "success": False, "error": str(e)})
    return UnifiedResponse.success(data={"results": results, "total": len(results), "succeeded": sum(1 for r in results if r["success"])})
