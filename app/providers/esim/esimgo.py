from __future__ import annotations

import base64
import hmac
import logging
from typing import Any

import requests

from app.core.database import get_session
from app.core.errors import AppError, ErrorCode
from app.models.esim import EsimProviderTransaction
from app.providers.base import ESIMProviderBase
from app.providers.registry import esim_provider
from config import settings

logger = logging.getLogger("esim-ego")


def _log_transaction(
    log_ref: str,
    action_type: str,
    status: str,
    request_data: dict[str, Any] | None = None,
    response_data: dict[str, Any] | None = None,
    error_code: str | None = None,
) -> None:
    try:
        with get_session() as session:
            txn = EsimProviderTransaction(
                iccid=log_ref[:22],
                provider="esimgo",
                action_type=action_type,
                status=status,
                request_data=request_data,
                response_data=response_data,
                error_code=error_code,
            )
            session.add(txn)
            session.flush()
    except Exception as e:
        logger.error("Failed to log eSIM transaction: %s", e)


def _get_headers() -> dict[str, str]:
    if not settings.ESIMGO_API_KEY:
        raise AppError(ErrorCode.PROVIDER_AUTH_FAILED)
    return {
        "X-API-KEY": settings.ESIMGO_API_KEY,
        "Content-Type": "application/json",
    }


def _base_url() -> str:
    base = settings.ESIMGO_API_BASE_URL.rstrip("/")
    if settings.ESIMGO_SANDBOX:
        sandbox_url = settings.ESIMGO_SANDBOX_BASE_URL
        if sandbox_url:
            base = sandbox_url.rstrip("/")
    return base


def _request(
    method: str,
    path: str,
    log_id: str,
    action_type: str,
    json_data: dict[str, Any] | None = None,
    params: dict[str, str] | None = None,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    headers = _get_headers()
    if extra_headers:
        headers.update(extra_headers)
    url = f"{_base_url()}/{path.lstrip('/')}"
    try:
        resp = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=json_data,
            params=params,
            timeout=settings.ESIMGO_TIMEOUT,
        )
    except requests.Timeout:
        _log_transaction(log_id, action_type, "timeout", request_data=json_data)
        raise AppError(ErrorCode.PROVIDER_TIMEOUT)
    except requests.RequestException as e:
        _log_transaction(log_id, action_type, "error", request_data=json_data, error_code=str(e))
        raise AppError(ErrorCode.PROVIDER_UNAVAILABLE)

    try:
        body = resp.json()
    except Exception:
        body = {"raw": resp.text[:500]}

    if resp.status_code == 401:
        _log_transaction(log_id, action_type, "auth_failed", json_data, body, str(resp.status_code))
        raise AppError(ErrorCode.PROVIDER_AUTH_FAILED)

    if resp.status_code == 403:
        _log_transaction(log_id, action_type, "forbidden", json_data, body, str(resp.status_code))
        raise AppError(ErrorCode.PROVIDER_AUTH_FAILED)

    if resp.status_code == 404:
        _log_transaction(log_id, action_type, "not_found", json_data, body, str(resp.status_code))
        raise AppError(ErrorCode.PROVIDER_BUNDLE_NOT_FOUND)

    if resp.status_code == 410:
        _log_transaction(log_id, action_type, "gone", json_data, body, str(resp.status_code))
        raise AppError(ErrorCode.ESIM_EXPIRED)

    if resp.status_code == 429:
        _log_transaction(log_id, action_type, "rate_limited", json_data, body, str(resp.status_code))
        raise AppError(ErrorCode.PROVIDER_RATE_LIMITED)

    if resp.status_code == 503:
        retry_after = resp.headers.get("Retry-After")
        _log_transaction(log_id, action_type, "processing", json_data, body, str(resp.status_code))
        raise AppError(ErrorCode.PROVIDER_UNAVAILABLE, data={"retry_after": retry_after})

    if resp.status_code >= 500:
        _log_transaction(log_id, action_type, "provider_error", json_data, body, str(resp.status_code))
        raise AppError(ErrorCode.PROVIDER_UNAVAILABLE)

    if resp.status_code >= 400 or body.get("status") == "error":
        error_msg = body.get("message", body.get("error", "unknown"))
        _log_transaction(log_id, action_type, "failed", json_data, body, error_msg)
        raise AppError(ErrorCode.ESIM_ORDER_FAILED, data={"provider_message": error_msg})

    _log_transaction(log_id, action_type, "success", json_data, body)
    return body


@esim_provider("esimgo")
class EsimGoProvider(ESIMProviderBase):

    def __init__(self) -> None:
        self._simulated = False
        if not settings.ESIMGO_API_KEY:
            if settings.ESIMGO_SANDBOX:
                logger.info("ESIMGO_API_KEY not configured — operating in simulated mode")
                self._simulated = True
                return
            logger.error("ESIMGO_API_KEY not configured and ESIMGO_SANDBOX is False")
            raise AppError(ErrorCode.PROVIDER_AUTH_FAILED)

    @property
    def _is_simulated(self) -> bool:
        return self._simulated

    def _sim_result(self, action: str, iccid: str = "", extra: dict | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {
            "status": "success",
            "simulated": True,
        }
        if iccid:
            result["iccid"] = iccid
        if extra:
            result.update(extra)
        _log_transaction(iccid or "sim", action, "success")
        return result

    def create_order(
        self,
        bundle_id: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if self._is_simulated:
            return self._sim_result("create_order", extra={"orderReference": f"sim_order_{bundle_id[:10]}"})
        iccid = kwargs.get("iccid", "")
        iccids = [iccid] if iccid else None
        order_item: dict[str, Any] = {
            "type": "bundle",
            "quantity": 1,
            "item": bundle_id,
            "allowReassign": False,
        }
        if iccids:
            order_item["iccids"] = iccids

        body: dict[str, Any] = {
            "type": "transaction",
            "assign": True,
            "order": [order_item],
        }

        profile_id = kwargs.get("profile_id")
        if profile_id:
            body["profileID"] = profile_id

        extra_headers: dict[str, str] = {}
        idempotency_key = kwargs.get("idempotency_key")
        if idempotency_key:
            extra_headers["Idempotency-Key"] = idempotency_key

        result = _request(
            "POST", "orders",
            log_id=iccid or "pending",
            action_type="create_order",
            json_data=body,
            extra_headers=extra_headers,
        )
        return result

    def apply_bundle(
        self,
        iccid: str,
        bundle_id: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if self._is_simulated:
            return self._sim_result("apply_bundle", iccid=iccid, extra={"bundle": bundle_id, "applyReference": f"sim_apply_{iccid[-6:]}"})
        body: dict[str, Any] = {
            "iccid": iccid,
            "name": bundle_id,
            "allowReassign": False,
        }
        repeat = kwargs.get("repeat")
        if repeat:
            body["repeat"] = repeat

        result = _request(
            "POST", "esims/apply",
            log_id=iccid,
            action_type="apply_bundle",
            json_data=body,
        )
        return result

    def get_install_details(self, reference: str, **kwargs: Any) -> dict[str, Any]:
        if self._is_simulated:
            return self._sim_result("get_install_details", extra={
                "iccid": f"sim_{reference[-8:]}",
                "matchingId": f"sim_match_{reference[-8:]}",
                "smdpAddress": "sim.smdp.example.com",
                "profileStatus": "installed",
            })
        params: dict[str, str] = {"reference": reference}
        additional_fields = kwargs.get("additional_fields")
        if additional_fields:
            params["additionalFields"] = additional_fields
        result = _request(
            "GET", "esims/assignments",
            log_id=reference,
            action_type="get_install_details",
            params=params,
        )
        return result

    def get_catalogue(self, **kwargs: Any) -> dict[str, Any]:
        if self._is_simulated:
            return self._sim_result("get_catalogue", extra={"bundles": []})
        params: dict[str, str] = {}
        for param in ("page", "perPage", "direction", "orderBy", "description", "group", "countries", "region"):
            val = kwargs.get(param)
            if val is not None:
                params[param] = str(val)
        try:
            headers = _get_headers()
            url = f"{_base_url()}/catalogue"
            resp = requests.get(url, headers=headers, params=params, timeout=settings.ESIMGO_TIMEOUT)
            if resp.status_code == 200:
                return resp.json()
            logger.error("Catalogue fetch failed: %s %s", resp.status_code, resp.text[:300])
            raise AppError(ErrorCode.ESIM_CATALOGUE_FAILED)
        except requests.RequestException as e:
            logger.error("Catalogue request failed: %s", e)
            raise AppError(ErrorCode.PROVIDER_UNAVAILABLE)

    def get_catalogue_bundle(self, name: str) -> dict[str, Any]:
        if self._is_simulated:
            return self._sim_result("get_catalogue_bundle", extra={"name": name})
        try:
            headers = _get_headers()
            url = f"{_base_url()}/catalogue/bundle/{name}"
            resp = requests.get(url, headers=headers, timeout=settings.ESIMGO_TIMEOUT)
            if resp.status_code == 200:
                return resp.json()
            logger.error("Catalogue bundle fetch failed: %s %s", resp.status_code, resp.text[:300])
            raise AppError(ErrorCode.ESIM_CATALOGUE_FAILED)
        except requests.RequestException as e:
            logger.error("Catalogue bundle request failed: %s", e)
            raise AppError(ErrorCode.PROVIDER_UNAVAILABLE)

    def get_pricing(self, bundle_ids: list[str] | None = None) -> dict[str, Any]:
        if self._is_simulated:
            return self._sim_result("get_pricing", extra={"prices": []})
        try:
            headers = _get_headers()
            url = f"{_base_url()}/catalogue/prices"
            resp = requests.get(url, headers=headers, timeout=settings.ESIMGO_TIMEOUT)
            if resp.status_code == 200:
                return resp.json()
            logger.error("Pricing fetch failed: %s %s", resp.status_code, resp.text[:300])
            raise AppError(ErrorCode.ESIM_CATALOGUE_FAILED)
        except requests.RequestException as e:
            logger.error("Pricing request failed: %s", e)
            raise AppError(ErrorCode.PROVIDER_UNAVAILABLE)

    def validate_callback_signature(self, body: bytes, signature: str) -> bool:
        expected = base64.b64encode(
            hmac.new(
                settings.ESIMGO_API_KEY.encode("utf-8"),
                body,
                "sha256",
            ).digest()
        ).decode("utf-8")
        return hmac.compare_digest(expected, signature)

    def handle_usage_callback(self, data: dict[str, Any]) -> dict[str, Any]:
        iccid = data.get("iccid", "")
        if not iccid:
            raise AppError(ErrorCode.ESIM_CALLBACK_INVALID, data={"reason": "missing iccid"})
        alert_type = data.get("alertType", "usage")
        bundle = data.get("bundle")
        if not isinstance(bundle, dict):
            bundle = {}
        initial_bytes = bundle.get("initialQuantity", 0)
        remaining_bytes = bundle.get("remainingQuantity", 0)
        if isinstance(initial_bytes, (int, float)) and initial_bytes > 0:
            usage_mb = max(0, int((initial_bytes - remaining_bytes) // (1024 * 1024)))
        else:
            usage_mb = 0
        logger.info("Usage callback for ICCID=%s: %d MB used (alertType=%s)", iccid, usage_mb, alert_type)
        return {
            "iccid": iccid,
            "data_usage_mb": usage_mb,
            "alert_type": alert_type,
            "bundle_name": bundle.get("name", ""),
        }

    def get_esim_details(self, iccid: str, **kwargs: Any) -> dict[str, Any]:
        if self._is_simulated:
            return self._sim_result("get_esim_details", iccid=iccid, extra={
                "profileStatus": "installed",
                "state": "active",
                "matchingId": f"sim_match_{iccid[-8:]}",
                "smdpAddress": "sim.smdp.example.com",
            })
        params: dict[str, str] = {}
        additional_fields = kwargs.get("additional_fields")
        if additional_fields:
            params["additionalFields"] = additional_fields
        result = _request(
            "GET", f"esims/{iccid}",
            log_id=iccid,
            action_type="get_esim_details",
            params=params,
        )
        return result

    def list_esims(self, **kwargs: Any) -> dict[str, Any]:
        if self._is_simulated:
            return self._sim_result("list_esims", extra={"esims": []})
        params: dict[str, str] = {}
        for param in ("page", "perPage", "direction", "orderBy", "filterBy", "filter"):
            val = kwargs.get(param)
            if val is not None:
                params[param] = str(val)
        result = _request(
            "GET", "esims",
            log_id="",
            action_type="list_esims",
            params=params,
        )
        return result

    def list_bundles(self, iccid: str, **kwargs: Any) -> dict[str, Any]:
        if self._is_simulated:
            return self._sim_result("list_bundles", iccid=iccid, extra={"bundles": []})
        params: dict[str, str] = {}
        include_used = kwargs.get("include_used")
        if include_used is not None:
            params["includeUsed"] = "true" if include_used else "false"
        limit = kwargs.get("limit")
        if limit is not None:
            params["limit"] = str(limit)
        result = _request(
            "GET", f"esims/{iccid}/bundles",
            log_id=iccid,
            action_type="list_bundles",
            params=params,
        )
        return result

    def revoke_bundle(self, iccid: str, bundle_name: str, **kwargs: Any) -> dict[str, Any]:
        if self._is_simulated:
            return self._sim_result("revoke_bundle", iccid=iccid, extra={"bundle": bundle_name})
        params: dict[str, str] = {}
        refund_to_balance = kwargs.get("refund_to_balance")
        if refund_to_balance is not None:
            params["refundToBalance"] = "true" if refund_to_balance else "false"
        revoke_type = kwargs.get("revoke_type", "transaction")
        params["type"] = revoke_type
        result = _request(
            "DELETE", f"esims/{iccid}/bundles/{bundle_name}",
            log_id=iccid,
            action_type="revoke_bundle",
            params=params,
        )
        return result

    def suspend_esim(self, iccid: str, suspend: bool = True) -> dict[str, Any]:
        if self._is_simulated:
            return self._sim_result("suspend_esim", iccid=iccid, extra={"suspended": suspend})
        result = _request(
            "POST", f"esims/{iccid}/suspend",
            log_id=iccid,
            action_type="suspend_esim",
            json_data={"suspend": suspend},
        )
        return result

    def get_organisation(self) -> dict[str, Any]:
        if self._is_simulated:
            return self._sim_result("get_organisation", extra={
                "name": "Simulated Org",
                "balance": 999999,
                "testCredit": 100000,
            })
        try:
            headers = _get_headers()
            url = f"{_base_url()}/organisation"
            resp = requests.get(url, headers=headers, timeout=settings.ESIMGO_TIMEOUT)
            if resp.status_code == 200:
                return resp.json()
            logger.error("Organisation fetch failed: %s %s", resp.status_code, resp.text[:300])
            raise AppError(ErrorCode.PROVIDER_UNAVAILABLE)
        except requests.RequestException as e:
            logger.error("Organisation request failed: %s", e)
            raise AppError(ErrorCode.PROVIDER_UNAVAILABLE)

    def get_inventory(self) -> dict[str, Any]:
        if self._is_simulated:
            return self._sim_result("get_inventory", extra={"bundles": []})
        try:
            headers = _get_headers()
            url = f"{_base_url()}/inventory"
            resp = requests.get(url, headers=headers, timeout=settings.ESIMGO_TIMEOUT)
            if resp.status_code == 200:
                return resp.json()
            logger.error("Inventory fetch failed: %s %s", resp.status_code, resp.text[:300])
            raise AppError(ErrorCode.ESIM_CATALOGUE_FAILED)
        except requests.RequestException as e:
            logger.error("Inventory request failed: %s", e)
            raise AppError(ErrorCode.PROVIDER_UNAVAILABLE)

    def get_networks(self, **kwargs: Any) -> dict[str, Any]:
        if self._is_simulated:
            return self._sim_result("get_networks", extra={"countryNetworks": []})
        params: dict[str, str] = {}
        for param in ("countries", "isos", "returnAll"):
            val = kwargs.get(param)
            if val is not None:
                params[param] = str(val)
        try:
            headers = _get_headers()
            url = f"{_base_url()}/networks"
            resp = requests.get(url, headers=headers, params=params, timeout=settings.ESIMGO_TIMEOUT)
            if resp.status_code == 200:
                return resp.json()
            logger.error("Networks fetch failed: %s %s", resp.status_code, resp.text[:300])
            raise AppError(ErrorCode.ESIM_CATALOGUE_FAILED)
        except requests.RequestException as e:
            logger.error("Networks request failed: %s", e)
            raise AppError(ErrorCode.PROVIDER_UNAVAILABLE)

    def handle_topup_callback(self, data: dict[str, Any]) -> dict[str, Any]:
        bundle = data.get("bundle", {})
        return {
            "alert_type": data.get("alertType", ""),
            "old_amount": bundle.get("oldAmount"),
            "new_amount": bundle.get("newAmount"),
        }

    def handle_first_attachment_callback(self, data: dict[str, Any]) -> dict[str, Any]:
        iccid = data.get("iccid", "")
        if not iccid:
            raise AppError(ErrorCode.ESIM_CALLBACK_INVALID, data={"reason": "missing iccid"})
        return {
            "iccid": iccid,
            "alert_type": data.get("alertType", ""),
        }

    def handle_location_update_callback(self, data: dict[str, Any]) -> dict[str, Any]:
        iccid = data.get("iccid", "")
        country = data.get("country", {})
        if not iccid:
            raise AppError(ErrorCode.ESIM_CALLBACK_INVALID, data={"reason": "missing iccid"})
        return {
            "iccid": iccid,
            "alert_type": data.get("alertType", ""),
            "country_code": country.get("code", ""),
            "country_name": country.get("name", ""),
        }

    def handle_first_use_callback(self, data: dict[str, Any]) -> dict[str, Any]:
        iccid = data.get("iccid", "")
        if not iccid:
            raise AppError(ErrorCode.ESIM_CALLBACK_INVALID, data={"reason": "missing iccid"})
        bundle = data.get("bundle", {})
        initial_bytes = bundle.get("initialQuantity", 0)
        remaining_bytes = bundle.get("remainingQuantity", 0)
        if isinstance(initial_bytes, (int, float)) and initial_bytes > 0:
            usage_mb = max(0, int((initial_bytes - remaining_bytes) // (1024 * 1024)))
        else:
            usage_mb = 0
        return {
            "iccid": iccid,
            "alert_type": data.get("alertType", ""),
            "data_usage_mb": usage_mb,
            "bundle_name": bundle.get("name", ""),
            "start_time": bundle.get("startTime", ""),
            "end_time": bundle.get("endTime", ""),
        }

    def handle_balance_notification_callback(self, data: dict[str, Any]) -> dict[str, Any]:
        balance_info = data.get("balanceInfo", {})
        return {
            "alert_type": data.get("alertType", ""),
            "balance": balance_info.get("balance"),
            "threshold": balance_info.get("threshold"),
            "threshold_percent_remaining": balance_info.get("thresholdPercentRemaining"),
        }

    def handle_msisdn_enabled_callback(self, data: dict[str, Any]) -> dict[str, Any]:
        iccid = data.get("iccid", "")
        msisdn = data.get("msisdn", "")
        if not iccid or not msisdn:
            raise AppError(ErrorCode.ESIM_CALLBACK_INVALID, data={"reason": "missing iccid or msisdn"})
        return {
            "iccid": iccid,
            "alert_type": data.get("alertType", ""),
            "msisdn": msisdn,
            "reason": data.get("reason", ""),
        }

    def handle_msisdn_disabled_callback(self, data: dict[str, Any]) -> dict[str, Any]:
        iccid = data.get("iccid", "")
        msisdn = data.get("msisdn", "")
        if not iccid or not msisdn:
            raise AppError(ErrorCode.ESIM_CALLBACK_INVALID, data={"reason": "missing iccid or msisdn"})
        return {
            "iccid": iccid,
            "alert_type": data.get("alertType", ""),
            "msisdn": msisdn,
            "reason": data.get("reason", ""),
        }

    def activate_bundle(self, iccid: str, bundle_name: str) -> dict[str, Any]:
        try:
            result = self.apply_bundle(iccid, bundle_name)
            return {"success": True, "data": result}
        except AppError as e:
            return {"success": False, "error": str(e.code)}

    def get_bundle_status(self, iccid: str, bundle_name: str) -> dict[str, Any]:
        path = f"esims/{iccid}/bundles/{bundle_name}"
        result = _request(
            "GET", path,
            log_id=iccid,
            action_type="get_bundle_status",
        )
        return result
