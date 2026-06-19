from __future__ import annotations

import json
import logging
import os
import time
from decimal import Decimal
from uuid import UUID

from app.core.database import get_session
from app.core.errors import AppError, ErrorCode
from app.models.plan import Plan
from app.models.inventory import EsimInventory, ImportBatch
from app.models.order import Order
from app.providers.registry import ProviderRegistry
from config import settings
from app.services.settings_service import SettingsService

logger = logging.getLogger("esim-ego")

CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "catalogue_cache.json")
NETWORK_INDEX_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "network_index.json")
NETWORK_INDEX_LOCK = os.path.join(os.path.dirname(__file__), "..", "..", "data", "network_index.lock")


def _read_catalogue_cache() -> dict | None:
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE) as f:
                return json.load(f)
    except Exception:
        logger.warning("Failed to read catalogue cache", exc_info=True)
    return None


def _write_catalogue_cache(data: dict) -> None:
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        logger.warning("Failed to write catalogue cache", exc_info=True)


def _read_network_index() -> dict | None:
    try:
        if os.path.exists(NETWORK_INDEX_FILE):
            with open(NETWORK_INDEX_FILE) as f:
                return json.load(f)
    except Exception:
        logger.warning("Failed to read network index", exc_info=True)
    return None


def _write_network_index(data: dict) -> None:
    try:
        os.makedirs(os.path.dirname(NETWORK_INDEX_FILE), exist_ok=True)
        with open(NETWORK_INDEX_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        logger.warning("Failed to write network index", exc_info=True)


def _get_provider():
    provider = ProviderRegistry.get_esim(settings.ESIM_PROVIDER) if settings.ESIM_PROVIDER else ProviderRegistry.get_esim("esimgo")
    if not provider:
        raise AppError(ErrorCode.PROVIDER_AUTH_FAILED, data={"message": "No eSIM provider configured"})
    return provider


class PlanService:

    @staticmethod
    def get_provider_catalogue(page: int = 1, perPage: int = 50, all_pages: bool = False, force: bool = False, network: str | None = None) -> dict:
        if all_pages:
            if not force:
                cached = _read_catalogue_cache()
                if cached is not None:
                    if network:
                        bundles = cached.get("bundles", [])
                        # Check network index first
                        index = _read_network_index()
                        if index:
                            network_lower = network.lower()
                            matched_names = set()
                            for net_name, bundle_names in index.get("networks", {}).items():
                                if network_lower in net_name.lower():
                                    matched_names.update(bundle_names)
                            filtered = [b for b in bundles if b.get("name") in matched_names]
                            return {"bundles": filtered, "total": len(filtered), "pageCount": 1, "network": network}
                        # Fall back to name/description search
                        n = network.lower()
                        filtered = [b for b in bundles if n in b.get("name", "").lower() or n in b.get("description", "").lower()]
                        return {"bundles": filtered, "total": len(filtered), "pageCount": 1, "network": network}
                    return cached
            return PlanService._fetch_full_catalogue(page, perPage)
        provider = _get_provider()
        try:
            catalogue = provider.get_catalogue(page=page, perPage=perPage)
            return catalogue
        except NotImplementedError:
            raise AppError(ErrorCode.ESIM_CATALOGUE_FAILED, data={"message": "Provider does not support catalogue browsing"})

    @staticmethod
    def _fetch_full_catalogue(page: int = 1, perPage: int = 50) -> dict:
        provider = _get_provider()
        all_bundles = []
        current_page = page
        rate_limited = False
        retries = 0
        max_retries = 2
        while True:
            try:
                cat = provider.get_catalogue(page=current_page, perPage=perPage)
                retries = 0
            except AppError:
                if retries < max_retries:
                    retries += 1
                    backoff = 2 ** retries
                    logger.warning("Rate limited on page %d, retrying in %ds (attempt %d)", current_page, backoff, retries)
                    time.sleep(backoff)
                    continue
                logger.warning("Rate limited on page %d after %d retries, returning partial results", current_page, retries)
                rate_limited = True
                break
            bundles = cat.get("bundles", [])
            if not bundles:
                break
            all_bundles.extend(bundles)
            total_pages = cat.get("pageCount", 0)
            if current_page >= total_pages:
                break
            current_page += 1
            time.sleep(0.7)
        result = {"bundles": all_bundles, "total": len(all_bundles), "pageCount": 1}
        if rate_limited:
            result["warning"] = f"Rate limited at page {current_page}. Showing partial results ({len(all_bundles)} bundles)."
        _write_catalogue_cache(result)
        return result

    @staticmethod
    def get_provider_catalogue_bundle(bundle_name: str) -> dict:
        provider = _get_provider()
        bundle_data = provider.get_catalogue_bundle(bundle_name)
        bundle = bundle_data.get("bundle", bundle_data)
        return bundle

    @staticmethod
    def get_network_index() -> dict:
        index = _read_network_index()
        if index:
            # Return summary for the UI
            networks = []
            for name, bundle_names in index.get("networks", {}).items():
                networks.append({"name": name, "bundle_count": len(bundle_names)})
            networks.sort(key=lambda n: n["bundle_count"], reverse=True)
            return {"networks": networks, "total_bundles_indexed": index.get("total_bundles", 0), "built_at": index.get("built_at", "")}
        return {"networks": [], "total_bundles_indexed": 0, "built_at": ""}

    @staticmethod
    def build_network_index() -> dict:
        lock_file = NETWORK_INDEX_LOCK
        if os.path.exists(lock_file):
            with open(lock_file) as f:
                pid = f.read().strip()
            if pid and os.path.exists(f"/proc/{pid}"):
                raise AppError(ErrorCode.ESIM_CATALOGUE_FAILED, data={"message": "Network index build already in progress"})
            os.remove(lock_file)
        with open(lock_file, "w") as f:
            f.write(str(os.getpid()))
        try:
            return PlanService._do_build_network_index()
        finally:
            if os.path.exists(lock_file):
                os.remove(lock_file)

    @staticmethod
    def _do_build_network_index() -> dict:
        cached = _read_catalogue_cache()
        if not cached:
            raise AppError(ErrorCode.ESIM_CATALOGUE_FAILED, data={"message": "Catalogue not loaded yet. Fetch catalogue first."})
        bundles = cached.get("bundles", [])
        provider = _get_provider()
        network_map: dict[str, set[str]] = {}
        total = len(bundles)
        errors = 0
        for i, bundle in enumerate(bundles):
            name = bundle.get("name", "")
            if not name:
                continue
            try:
                bundle_data = provider.get_catalogue_bundle(name)
                detail = bundle_data.get("bundle", bundle_data)
                countries_list = detail.get("countries", [])
                for country_entry in countries_list:
                    if not isinstance(country_entry, dict):
                        continue
                    networks = country_entry.get("networks", [])
                    if isinstance(networks, list):
                        for net in networks:
                            net_str = str(net).strip()
                            if net_str:
                                if net_str not in network_map:
                                    network_map[net_str] = set()
                                network_map[net_str].add(name)
            except Exception as e:
                logger.warning("Failed to fetch detail for bundle '%s': %s", name, e)
                errors += 1
            if (i + 1) % 10 == 0:
                logger.info("Network index: %d/%d bundles processed (%d errors)", i + 1, total, errors)
            time.sleep(0.7)
        index_data = {
            "networks": {k: list(v) for k, v in network_map.items()},
            "total_bundles_indexed": total,
            "built_at": __import__("datetime").datetime.utcnow().isoformat(),
        }
        _write_network_index(index_data)
        return {
            "total_networks": len(network_map),
            "total_bundles": total,
            "errors": errors,
            "index": index_data,
        }

    @staticmethod
    def import_catalogue_bundles(bundle_names: list[str]) -> dict:
        provider = _get_provider()
        created = 0
        already_existed = 0
        skipped = 0
        errors: list[dict] = []
        global_position = 0

        with get_session() as session:
            last_plan = session.query(Plan).order_by(Plan.sort_order.desc()).first()
            global_position = (last_plan.sort_order + 1) if last_plan else 1

        for bundle_name in bundle_names:
            try:
                bundle_data = provider.get_catalogue_bundle(bundle_name)
            except Exception as e:
                errors.append({"bundle": bundle_name, "success": False, "error": str(e)})
                continue

            bundle = bundle_data.get("bundle", bundle_data)
            bid = bundle.get("name", bundle_name)

            with get_session() as session:
                existing = session.query(Plan).filter(Plan.provider_bundle_id == bid).first()

                if existing:
                    skip_reason = "already_exists"
                    skipped += 1
                    continue

                price = bundle.get("price", 0)
                if not price:
                    skip_reason = "no_price"
                    skipped += 1
                    continue

                try:
                    price_usd = Decimal(str(price))
                except Exception:
                    skipped += 1
                    continue

                markup = Decimal("20.00")
                selling_usd = (price_usd * (Decimal("1") + markup / Decimal("100"))).quantize(Decimal("0.01"))
                official_currency = SettingsService.get_official_currency()
                try:
                    from app.services.currency_service import CurrencyService
                    rate_info = CurrencyService.get_rate("USD", official_currency)
                    rate = Decimal(str(rate_info.get("rate", settings.USD_TO_IQD_RATE)))
                except Exception:
                    rate = Decimal(str(settings.USD_TO_IQD_RATE)) if official_currency == "IQD" else Decimal("1")
                selling_iqd = round(selling_usd * rate)

                countries_list = PlanService._extract_countries(bundle)
                countries_str = ", ".join(countries_list) if countries_list else "all"

                data_amount = bundle.get("dataAmount", 0)
                duration = bundle.get("duration", 0)
                description = bundle.get("description", "")
                display_name = PlanService._generate_plan_name(bundle)

                if existing:
                    existing.name = display_name
                    existing.price_usd = selling_usd
                    existing.price_iqd = selling_iqd
                    existing.data_amount_mb = data_amount
                    existing.duration_days = duration
                    existing.countries = countries_str
                    existing.description = description
                    updated += 1
                else:
                    plan = Plan(
                        name=display_name,
                        description=description,
                        data_amount_mb=data_amount,
                        duration_days=duration,
                        price_usd=selling_usd,
                        price_iqd=selling_iqd,
                        countries=countries_str,
                        provider_bundle_id=bid,
                        sort_order=global_position,
                    )
                    session.add(plan)
                    global_position += 1
                    created += 1

                session.flush()

        return {
            "created": created,
            "already_existed": already_existed,
            "skipped": skipped,
            "errors": errors,
            "total_processed": len(bundle_names),
        }

    @staticmethod
    def create_plan(data: dict) -> Plan:
        with get_session() as session:
            plan = Plan(
                name=data["name"],
                description=data.get("description", ""),
                data_amount_mb=data["data_amount_mb"],
                duration_days=data["duration_days"],
                price_usd=data["price_usd"],
                price_iqd=data["price_iqd"],
                markup_percentage=data.get("markup_percentage", Decimal("20.00")),
                countries=data.get("countries", "all"),
                provider_bundle_id=data["provider_bundle_id"],
                is_active=data.get("is_active", True),
            )
            session.add(plan)
            session.flush()
            return PlanService._format_plan(plan)

    @staticmethod
    def get_plan(plan_id: str) -> dict:
        try:
            pid = UUID(plan_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        with get_session() as session:
            plan = session.query(Plan).filter(Plan.id == pid).first()
            if not plan:
                raise AppError(ErrorCode.PLAN_NOT_FOUND)
            return PlanService._format_plan(plan)

    @staticmethod
    def list_plans(
        page: int = 1,
        limit: int = 20,
        active_only: bool = True,
    ) -> dict:
        with get_session() as session:
            query = session.query(Plan)
            if active_only:
                query = query.filter(Plan.is_active == True)
            total = query.count()
            offset = (page - 1) * limit
            plans = (
                query.order_by(Plan.created_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return {
                "items": [PlanService._format_plan(p) for p in plans],
                "total": total,
                "page": page,
                "limit": limit,
            }

    @staticmethod
    def list_all_plans(page: int = 1, limit: int = 20) -> dict:
        with get_session() as session:
            query = session.query(Plan)
            total = query.count()
            offset = (page - 1) * limit
            plans = (
                query.order_by(Plan.sort_order.asc(), Plan.created_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return {
                "items": [PlanService._format_plan(p) for p in plans],
                "total": total,
                "page": page,
                "limit": limit,
            }

    @staticmethod
    def update_plan(plan_id: str, data: dict) -> dict:
        try:
            pid = UUID(plan_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        with get_session() as session:
            plan = session.query(Plan).filter(Plan.id == pid).first()
            if not plan:
                raise AppError(ErrorCode.PLAN_NOT_FOUND)
            allowed = {
                "name", "description", "data_amount_mb", "duration_days",
                "price_usd", "price_iqd", "markup_percentage",
                "countries", "provider_bundle_id", "is_active", "sort_order",
            }
            for key, value in data.items():
                if key in allowed:
                    setattr(plan, key, value)
            session.flush()
            return PlanService._format_plan(plan)

    @staticmethod
    def delete_plan(plan_id: str) -> None:
        try:
            pid = UUID(plan_id)
        except (ValueError, AttributeError):
            raise AppError(ErrorCode.VALIDATION_INVALID_UUID)
        with get_session() as session:
            plan = session.query(Plan).filter(Plan.id == pid).first()
            if not plan:
                logger.warning("delete_plan: plan %s not found", plan_id)
                raise AppError(ErrorCode.PLAN_NOT_FOUND)

            inv_count = session.query(EsimInventory.id).filter(EsimInventory.plan_id == pid).count()
            batch_count = session.query(ImportBatch.id).filter(ImportBatch.plan_id == pid).count()
            order_count = session.query(Order.id).filter(Order.plan_id == pid).count()
            logger.info("delete_plan %s: inv=%d batches=%d orders=%d", plan_id, inv_count, batch_count, order_count)

            session.query(EsimInventory).filter(EsimInventory.plan_id == pid).update(
                {"plan_id": None}, synchronize_session=False
            )
            session.query(ImportBatch).filter(ImportBatch.plan_id == pid).update(
                {"plan_id": None}, synchronize_session=False
            )
            session.query(Order).filter(Order.plan_id == pid).update(
                {"plan_id": None}, synchronize_session=False
            )

            session.delete(plan)
            session.flush()
            logger.info("delete_plan %s: deleted successfully", plan_id)

    @staticmethod
    def delete_all_plans() -> int:
        with get_session() as session:
            session.query(EsimInventory).update({"plan_id": None}, synchronize_session=False)
            session.query(ImportBatch).update({"plan_id": None}, synchronize_session=False)
            session.query(Order).update({"plan_id": None}, synchronize_session=False)
            count = session.query(Plan).count()
            session.query(Plan).delete()
            session.flush()
            logger.info("delete_all_plans: %d plans deleted", count)
            return count

    @staticmethod
    def _extract_countries(bundle: dict) -> list[str]:
        """Extract country names from provider bundle, handling both list and detail endpoint structures."""
        names: list[str] = []
        for c in bundle.get("countries", []):
            if isinstance(c, dict):
                if "country" in c and isinstance(c["country"], dict):
                    name = c["country"].get("name", "")
                else:
                    name = c.get("name", "")
                if name:
                    names.append(name)
        return names

    @staticmethod
    def _generate_plan_name(bundle: dict) -> str:
        countries_list = PlanService._extract_countries(bundle)
        country = countries_list[0] if countries_list else "Global"
        data = bundle.get("dataAmount", 0)
        duration = bundle.get("duration", 0)
        data_str = f"{data}MB" if data else "Unlimited"
        return f"{country} {data_str} / {duration}d"

    @staticmethod
    def sync_catalogue_from_provider() -> dict:
        provider = ProviderRegistry.get_esim(settings.ESIM_PROVIDER) if settings.ESIM_PROVIDER else ProviderRegistry.get_esim("esimgo")
        created = 0
        updated = 0
        skipped = 0
        errors: list[dict] = []
        page = 1
        global_position = 0

        while True:
            cat = provider.get_catalogue(page=page, perPage=50)
            bundles = cat.get("bundles", [])
            if not bundles:
                break

            with get_session() as session:
                for bundle in bundles:
                    global_position += 1
                    bundle_id = bundle.get("name", "")
                    if not bundle_id:
                        skipped += 1
                        continue

                    existing = session.query(Plan).filter(
                        Plan.provider_bundle_id == bundle_id
                    ).first()

                    price = bundle.get("price", 0)
                    if not price:
                        skipped += 1
                        continue

                    try:
                        price_usd = Decimal(str(price))
                    except Exception:
                        skipped += 1
                        continue
                    markup = Decimal("20.00")
                    selling_usd = (price_usd * (Decimal("1") + markup / Decimal("100"))).quantize(Decimal("0.01"))
                    official_currency = SettingsService.get_official_currency()
                    try:
                        from app.services.currency_service import CurrencyService
                        rate_info = CurrencyService.get_rate("USD", official_currency)
                        rate = Decimal(str(rate_info.get("rate", settings.USD_TO_IQD_RATE)))
                    except Exception:
                        rate = Decimal(str(settings.USD_TO_IQD_RATE)) if official_currency == "IQD" else Decimal("1")
                    selling_iqd = round(selling_usd * rate)

                    countries_list = PlanService._extract_countries(bundle)
                    countries_str = ", ".join(countries_list) if countries_list else "all"

                    data_amount = bundle.get("dataAmount", 0)
                    duration = bundle.get("duration", 0)
                    description = bundle.get("description", "")
                    display_name = PlanService._generate_plan_name(bundle)

                    if existing:
                        existing.name = display_name
                        existing.price_usd = selling_usd
                        existing.price_iqd = selling_iqd
                        existing.data_amount_mb = data_amount
                        existing.duration_days = duration
                        existing.countries = countries_str
                        existing.description = description
                        updated += 1
                    else:
                        plan = Plan(
                            name=display_name,
                            description=description,
                            data_amount_mb=data_amount,
                            duration_days=duration,
                            price_usd=selling_usd,
                            price_iqd=selling_iqd,
                            countries=countries_str,
                            provider_bundle_id=bundle_id,
                            sort_order=global_position,
                        )
                        session.add(plan)
                        created += 1

                session.flush()

            total_pages = cat.get("pageCount", 0)
            if page >= total_pages:
                break
            page += 1

        return {
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
        }

    @staticmethod
    def _format_plan(plan: Plan) -> dict:
        return {
            "id": str(plan.id),
            "name": plan.name,
            "description": plan.description,
            "data_amount_mb": plan.data_amount_mb,
            "duration_days": plan.duration_days,
            "price_usd": str(plan.price_usd),
            "price_iqd": plan.price_iqd,
            "markup_percentage": float(plan.markup_percentage),
            "countries": plan.countries,
            "provider_bundle_id": plan.provider_bundle_id,
            "is_active": plan.is_active,
            "sort_order": plan.sort_order,
            "created_at": plan.created_at.isoformat(),
            "updated_at": plan.updated_at.isoformat(),
        }
