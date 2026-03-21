from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any, Dict, Iterable, List, Mapping, Optional

from app.core import access_policy
from app.core.cache_manager import TTLValueCache
from app.core.exceptions import DatasetNotBuiltError
from app.services import fact_store
from app.services.filters import (
    FilterParams,
    canonical_filters_hash as _canonical_filters_hash,
    canonical_filters_json as _canonical_filters_json,
    filters_to_store,
    normalize_filters,
    parse_filters,
    resolve_effective_filters,
)

logger = logging.getLogger(__name__)

OPTIONS_TTL_MINUTES = int(os.getenv("FILTER_OPTIONS_TTL_MINUTES", os.getenv("FILTER_OPTIONS_TTL", "1060")))
OPTIONS_TTL_SECONDS = max(60, OPTIONS_TTL_MINUTES * 60)
_OPTIONS_CACHE = TTLValueCache(maxsize=64)
OPTION_KEYS = ("statuses", "regions", "methods", "ship_methods", "customers", "suppliers", "products", "sales_reps")
OPTION_KEY_SET = set(OPTION_KEYS)
_OPTION_ALIAS_MAP = {
    "shipping_methods": "methods",
    "ship_method": "methods",
    "shipping_method": "methods",
    "method": "methods",
    "customer": "customers",
    "supplier": "suppliers",
    "product": "products",
    "sales_rep": "sales_reps",
    "salesrep": "sales_reps",
    "salesreps": "sales_reps",
}
_PRIMARY_OPTION_KEYS = ("statuses", "regions", "methods", "customers", "suppliers", "products", "sales_reps")


def _clean_tokens(raw: Iterable[Any] | None) -> list[str]:
    vals: list[str] = []
    if raw is None:
        return vals
    try:
        for item in raw:
            if item is None:
                continue
            sval = str(item).strip()
            if sval:
                vals.append(sval)
    except Exception:
        pass
    return vals


def scope_from_user(user: Any) -> Dict[str, Any]:
    scope_obj = access_policy.scope_for_user(user, use_cache=True)
    scope = scope_obj.as_dict(include_allowed=True)
    try:
        scope["role"] = getattr(user, "role", None)
    except Exception:
        scope["role"] = None
    # Backward-compatible aliases for existing callers
    scope["sales_rep_ids"] = _clean_tokens(scope.get("allowed_erp_user_ids"))
    scope["is_super_user"] = bool(scope_obj.is_admin or scope_obj.scope_mode == "all")
    return scope


def canonical_json(filters: Any) -> str:
    """Stable JSON string for cache keys."""
    return _canonical_filters_json(filters)


def filters_hash(filters: Any) -> str:
    """Stable hash for filter payloads (used in cache keys/logging)."""
    return _canonical_filters_hash(filters)


def normalize_requested_option_keys(raw: Any = None) -> tuple[str, ...]:
    if raw is None:
        return tuple(OPTION_KEYS)

    values: list[str] = []
    if isinstance(raw, str):
        values.extend(part.strip() for part in raw.split(","))
    else:
        try:
            for item in raw:
                if item is None:
                    continue
                if isinstance(item, str):
                    values.extend(part.strip() for part in item.split(","))
                else:
                    values.append(str(item).strip())
        except Exception:
            values.append(str(raw).strip())

    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        token = str(item or "").strip().lower().replace("-", "_")
        if not token:
            continue
        token = _OPTION_ALIAS_MAP.get(token, token)
        if token not in OPTION_KEY_SET or token in seen:
            continue
        seen.add(token)
        normalized.append(token)

    if not normalized:
        return tuple(OPTION_KEYS)
    if "methods" in normalized and "ship_methods" not in seen:
        normalized.append("ship_methods")
    if "ship_methods" in normalized and "methods" not in seen:
        normalized.append("methods")
    return tuple(normalized)


def default_filters(user: Any = None) -> FilterParams:
    """Return default filters (last 3 months) honoring any RBAC presets."""
    params = parse_filters({})
    scope = scope_from_user(user)
    if scope.get("scope_mode") != "all":
        allowed = _clean_tokens(scope.get("allowed_erp_user_ids"))
        if allowed:
            params = params.__class__(**{**params.__dict__, "sales_reps": tuple(allowed)})
    return normalize_filters(params)


def schema(filters: Any = None) -> Dict[str, Any]:
    params = normalize_filters(filters) if filters is not None else default_filters()
    defaults = filters_to_store(params)
    fields = [
        {"name": "start_date", "type": "date", "label": "Start Date", "default": defaults.get("start_date"), "aliases": ["start", "date_start"]},
        {"name": "end_date", "type": "date", "label": "End Date", "default": defaults.get("end_date"), "aliases": ["end", "date_end"]},
        {"name": "date_preset", "type": "select", "label": "Quick Range", "default": defaults.get("date_preset")},
        {"name": "statuses", "type": "multi", "label": "Statuses"},
        {"name": "regions", "type": "multi", "label": "Regions", "aliases": ["region_ids"]},
        {"name": "customers", "type": "multi", "label": "Customers", "aliases": ["customer_ids"]},
        {"name": "suppliers", "type": "multi", "label": "Suppliers", "aliases": ["supplier_ids"]},
        {"name": "products", "type": "multi", "label": "Products", "aliases": ["product_ids"]},
        {"name": "sales_reps", "type": "multi", "label": "Sales Reps", "aliases": ["sales_rep_ids"]},
        {"name": "shipping_methods", "type": "multi", "label": "Shipping Methods", "aliases": ["ship_method_ids", "methods"]},
    ]
    return {
        "fields": fields,
        "defaults": defaults,
        "dataset_version": fact_store.cache_buster(),
    }


def _list_expr(alias: str, col: Optional[str]) -> Optional[str]:
    if not col:
        return None
    safe = fact_store.quote_identifier(col)
    return f"list_sort(list(distinct CAST({safe} AS VARCHAR))) AS {alias}"


def _list_struct_expr(alias: str, id_col: Optional[str], label_col: Optional[str]) -> Optional[str]:
    if not id_col or not label_col:
        return None
    id_safe = fact_store.quote_identifier(id_col)
    label_safe = fact_store.quote_identifier(label_col)
    return (
        "list(distinct CASE WHEN {id_col} IS NULL THEN NULL "
        "ELSE struct_pack(id:=CAST({id_col} AS VARCHAR), "
        "label:=CAST(COALESCE({label_col}, {id_col}) AS VARCHAR)) END) AS {alias}"
    ).format(id_col=id_safe, label_col=label_safe, alias=alias)


def _option_selects(cols: set[str], requested_keys: tuple[str, ...]) -> List[str]:
    selects: List[str] = []
    requested = set(requested_keys or OPTION_KEYS)
    # Statuses use a single displayable string.
    if "statuses" in requested:
        status_col = fact_store.choose_column(("OrderStatus", "Status", "order_status"), cols)
        expr = _list_expr("statuses", status_col)
        if expr:
            selects.append(expr)

    def add_bucket(alias: str, id_candidates: Sequence[str], label_candidates: Sequence[str]) -> None:
        if alias not in requested:
            return
        id_col = fact_store.choose_column(id_candidates, cols)
        label_col = fact_store.choose_column(label_candidates, cols)
        if id_col and label_col and id_col != label_col:
            expr = _list_struct_expr(alias, id_col, label_col)
        else:
            expr = _list_expr(alias, id_col or label_col)
        if expr:
            selects.append(expr)

    # Align IDs with filter where-clause priority to avoid mismatches.
    add_bucket("regions", ("RegionId", "RegionName", "Region"), ("RegionName", "Region", "RegionId"))
    add_bucket(
        "methods",
        ("ShippingMethodName", "ShippingMethodLabel", "ShippingMethodRequested", "ShipMethod_Name"),
        ("ShippingMethodLabel", "ShippingMethodName", "ShippingMethodRequested", "ShipMethod_Name"),
    )
    add_bucket("customers", ("CustomerId", "CustomerName", "Customer"), ("CustomerName", "Customer", "CustomerId"))
    add_bucket("suppliers", ("SupplierId", "SupplierName", "Supplier"), ("SupplierName", "Supplier", "SupplierId"))
    add_bucket("products", ("ProductId", "SKU", "ProductName", "Product"), ("ProductName", "Product", "SKU", "ProductId"))
    add_bucket(
        "sales_reps",
        ("SalesRepId", "PrimarySalesRepId", "SalesRepName", "PrimarySalesRepName"),
        ("SalesRepName", "PrimarySalesRepName", "SalesRepId", "PrimarySalesRepId"),
    )
    return selects


def _coerce_option_value(val: Any) -> Optional[str]:
    if val is None:
        return None
    if isinstance(val, dict):
        raw = val.get("id") or val.get("value") or val.get("label") or val.get("name")
        if raw is None:
            return None
        sval = str(raw).strip()
        return sval or None
    sval = str(val).strip()
    return sval or None


def _coerce_option_label(val: Any, fallback: str) -> str:
    if isinstance(val, dict):
        raw = val.get("label") or val.get("name") or val.get("title") or val.get("value") or val.get("id")
        if raw is not None:
            text = str(raw).strip()
            if text:
                return text
    return fallback


def _to_options(raw: Iterable[Any] | None, bucket: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if raw is None:
        return out
    seen: set[str] = set()
    for val in raw:
        sval = _coerce_option_value(val)
        if not sval:
            continue
        if sval in seen:
            continue
        seen.add(sval)
        label = _coerce_option_label(val, sval)
        out.append({"id": sval, "label": label, "bucket": bucket, "value": sval})
    if out:
        out.sort(key=lambda item: (item.get("label") or item.get("id") or "").lower())
    return out


def _normalize_options_map(raw_options: Any) -> Dict[str, list[dict[str, str]]]:
    raw = raw_options if isinstance(raw_options, dict) else {}
    options: Dict[str, list[dict[str, str]]] = {}
    for key in OPTION_KEYS:
        raw_list = raw.get(key)
        if raw_list is None and key == "ship_methods":
            raw_list = raw.get("methods")
        options[key] = _to_options(raw_list or [], key)
    return options


def _option_counts(options: Dict[str, list[dict[str, str]]]) -> Dict[str, int]:
    return {key: len(options.get(key) or []) for key in OPTION_KEYS}


def sanitize_filters_against_options(filters: Any, payload: Mapping[str, Any] | None) -> tuple[FilterParams, Dict[str, Any]]:
    params = normalize_filters(filters)
    raw_options = payload.get("options") if isinstance(payload, Mapping) else {}
    options = _normalize_options_map(raw_options)
    allowlists: Dict[str, Dict[str, str]] = {}
    for key in OPTION_KEYS:
        items = options.get(key) or []
        allowlists[key] = {}
        for item in items:
            raw = item.get("id") or item.get("value") or item.get("label")
            if raw in (None, ""):
                continue
            token = str(raw).strip()
            if not token:
                continue
            allowlists[key][token.lower()] = token

    dropped: Dict[str, list[str]] = {}

    def _sanitize(bucket: str, values: Iterable[str] | None, *, lower: bool = False) -> tuple[str, ...]:
        current = tuple(values or ())
        if not current:
            return tuple()
        allowlist = allowlists.get(bucket)
        if not allowlist:
            return current
        kept: list[str] = []
        seen: set[str] = set()
        for raw in current:
            token = str(raw).strip()
            if not token:
                continue
            canonical = allowlist.get(token.lower())
            if canonical is None:
                dropped.setdefault(bucket, [])
                if token not in dropped[bucket]:
                    dropped[bucket].append(token)
                continue
            normalized = canonical.lower() if lower else canonical
            compare = normalized.lower() if lower else normalized
            if compare in seen:
                continue
            seen.add(compare)
            kept.append(normalized)
        return tuple(kept)

    sanitized = FilterParams(
        start=params.start,
        end=params.end,
        statuses=_sanitize("statuses", getattr(params, "statuses", ()), lower=True),
        regions=_sanitize("regions", getattr(params, "regions", ())),
        methods=_sanitize("methods", getattr(params, "methods", ())),
        customers=_sanitize("customers", getattr(params, "customers", ())),
        suppliers=_sanitize("suppliers", getattr(params, "suppliers", ())),
        products=_sanitize("products", getattr(params, "products", ())),
        sales_reps=_sanitize("sales_reps", getattr(params, "sales_reps", ())),
        preset=params.preset,
        protein_min=params.protein_min,
        protein_max=params.protein_max,
        protein_name_like=params.protein_name_like,
        complete_months_only=params.complete_months_only,
    )
    meta = {
        "sanitized": bool(dropped),
        "dropped_filters": {key: list(values) for key, values in dropped.items()},
        "filters_notice": (
            "Some filters were removed because they are no longer available in the current filter options."
            if dropped else None
        ),
    }
    return sanitized, meta


def empty_options_payload(
    filters: Any,
    scope: Optional[Dict[str, Any]] = None,
    *,
    requested_keys: Any = None,
    error: Any = None,
) -> Dict[str, Any]:
    params = normalize_filters(filters)
    requested = normalize_requested_option_keys(requested_keys)
    meta = fact_store.get_meta()
    payload = {
        "options": {key: [] for key in OPTION_KEYS},
        "dataset_version": fact_store.cache_buster(),
        "filters": filters_to_store(params),
        "scope": scope or {},
        "date_min": meta.get("date_min") or meta.get("min_date"),
        "date_max": meta.get("date_max") or meta.get("max_date"),
        "cached": False,
        "duration_ms": 0,
        "meta": {
            "degraded": True,
            "requested_dimensions": list(requested),
            "option_counts": {key: 0 for key in OPTION_KEYS},
        },
    }
    if error is not None:
        payload["meta"]["error"] = str(error)
    return payload


def _options_payload(filters: FilterParams, scope: Dict[str, Any], *, requested_keys: tuple[str, ...]) -> Dict[str, Any]:
    cols = fact_store.list_columns()
    if not cols:
        raise DatasetNotBuiltError("Fact view not initialized.")
    requested = normalize_requested_option_keys(requested_keys)
    selects = _option_selects(cols, requested)
    if not selects:
        return {
            "options": {key: [] for key in OPTION_KEYS},
            "dataset_version": fact_store.cache_buster(),
            "filters": filters_to_store(filters),
            "meta": {"requested_dimensions": list(requested), "option_counts": {key: 0 for key in OPTION_KEYS}},
        }

    where_sql, params, start_iso, end_iso = fact_store.build_where_clause(
        filters, cols, scope, apply_default_window=True
    )
    sql = f"SELECT {', '.join(selects)} FROM fact WHERE {where_sql}"
    conn = fact_store.get_conn()
    started = time.perf_counter()
    cursor = conn.execute(sql, params)
    row = cursor.fetchone()
    names = [meta[0] for meta in (cursor.description or [])]
    duration_ms = int((time.perf_counter() - started) * 1000)

    options: Dict[str, list[dict[str, str]]] = {}
    if row is not None:
        for idx, name in enumerate(names):
            raw = row[idx] if idx < len(row) else None
            options[name] = _to_options(raw, name)

    for key in ("statuses", "regions", "methods", "customers", "suppliers", "products", "sales_reps"):
        options.setdefault(key, [])
    if "ship_methods" not in options:
        options["ship_methods"] = _to_options(options.get("methods", []), "ship_methods")

    meta = fact_store.get_meta()
    date_min = meta.get("date_min") or meta.get("min_date")
    date_max = meta.get("date_max") or meta.get("max_date")
    normalized_options = _normalize_options_map(options)

    return {
        "options": normalized_options,
        "dataset_version": fact_store.cache_buster(),
        "duration_ms": duration_ms,
        "filters": filters_to_store(filters),
        "scope": scope,
        "start": start_iso,
        "end": end_iso,
        "date_min": date_min,
        "date_max": date_max,
        "meta": {
            "requested_dimensions": list(requested),
            "option_counts": _option_counts(normalized_options),
        },
    }


def get_filter_options(
    filters: Any,
    scope: Optional[Dict[str, Any]] = None,
    *,
    use_cache: bool = True,
    requested_keys: Any = None,
) -> Dict[str, Any]:
    params = normalize_filters(filters)
    scope_payload = scope or {}
    version = fact_store.cache_buster()
    requested = normalize_requested_option_keys(requested_keys)
    cache_key_parts = {
        "endpoint": "filters.options",
        "filters": filters_to_store(params),
        "filters_hash": filters_hash(params),
        "scope": {
            "scope_mode": scope_payload.get("scope_mode"),
            "allowed_count": scope_payload.get("allowed_count"),
            "scope_hash": scope_payload.get("scope_hash"),
            "permissions_version": scope_payload.get("permissions_version"),
        },
        "requested_dimensions": list(requested),
        "version": version,
    }
    key = hashlib.sha256(json.dumps(cache_key_parts, sort_keys=True, default=str).encode("utf-8")).hexdigest()

    def _build() -> Dict[str, Any]:
        payload = _options_payload(params, scope_payload, requested_keys=requested)
        payload["cached"] = False
        return payload

    if not use_cache:
        payload = _build()
        payload.setdefault("meta", {})
        payload["meta"]["cache_key"] = key
        payload["meta"]["cache_ttl"] = OPTIONS_TTL_SECONDS
        payload["meta"]["cached"] = False
        payload["meta"]["requested_dimensions"] = list(requested)
        return payload

    result, hit = _OPTIONS_CACHE.get_or_compute(key, OPTIONS_TTL_SECONDS, _build)
    if isinstance(result, dict):
        result["dataset_version"] = result.get("dataset_version", version)
        result["cached"] = bool(hit)
        result.setdefault("meta", {})
        result["meta"]["cache_key"] = key
        result["meta"]["cache_ttl"] = OPTIONS_TTL_SECONDS
        result["meta"]["cached"] = bool(hit)
        result["meta"]["requested_dimensions"] = list(requested)
        result.setdefault("date_min", None)
        result.setdefault("date_max", None)
        if isinstance(result.get("options"), dict):
            result["options"] = _normalize_options_map(result.get("options"))
            result["meta"].setdefault("option_counts", _option_counts(result["options"]))
    return result


def options_etag(payload: Dict[str, Any]) -> str:
    basis = {
        "dataset_version": payload.get("dataset_version"),
        "filters": payload.get("filters"),
        "scope": payload.get("scope"),
        "date_min": payload.get("date_min"),
        "date_max": payload.get("date_max"),
        "options": payload.get("options"),
    }
    try:
        encoded = json.dumps(basis, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
    except Exception:
        return ""
