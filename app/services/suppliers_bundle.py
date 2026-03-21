from __future__ import annotations

import copy
from dataclasses import replace as dc_replace
import hashlib
import json
import math
import os
from datetime import date, timedelta
from typing import Any, Dict, List, Mapping, Sequence, Tuple

import pandas as pd

from app.core.cache_manager import TTLValueCache
from app.services import fact_schema as fs
from app.services import fact_store
from app.services import filters_service
from app.services import presentation

TOP_N_DEFAULT = 15
TOP_N_MAX = 5000
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 50000
SUPPLIER_PRODUCTS_EXPORT_MAX_ROWS = int(os.getenv("SUPPLIER_PRODUCTS_EXPORT_MAX_ROWS", "250000"))
SUPPLIER_PRODUCTS_EXPORT_CHUNK_SIZE = int(os.getenv("SUPPLIER_PRODUCTS_EXPORT_CHUNK_SIZE", "10000"))
SUPPLIERS_MARGIN_TARGET_PCT = float(os.getenv("SUPPLIERS_MARGIN_TARGET_PCT", "27"))

KPI_CHART_TTL_SECONDS = int(os.getenv("SUPPLIERS_KPI_CHART_TTL_SECONDS", "900"))
TABLE_TTL_SECONDS = int(os.getenv("SUPPLIERS_TABLE_TTL_SECONDS", "300"))
DRILLDOWN_TTL_SECONDS = int(os.getenv("SUPPLIERS_DRILLDOWN_TTL_SECONDS", "600"))

_KPI_CHART_CACHE = TTLValueCache(maxsize=256)
_TABLE_CACHE = TTLValueCache(maxsize=512)
_DRILLDOWN_CACHE = TTLValueCache(maxsize=256)
_ANALYTICS_CACHE = TTLValueCache(maxsize=256)


class SupplierProductsExportLimitError(ValueError):
    def __init__(self, *, row_count: int, max_rows: int) -> None:
        self.row_count = int(row_count)
        self.max_rows = int(max_rows)
        super().__init__(
            f"Export is too large ({self.row_count:,} rows). "
            f"Please narrow filters to {self.max_rows:,} rows or fewer."
        )

DATE_CANDIDATES: tuple[str, ...] = (
    "DateShipped_line",
    "DateShipped_order",
    "ShipDate",
    "DateExpected_line",
    "DateExpected_order",
    "DateOrdered_line",
    "DateOrdered_order",
    fs.CANON.date,
    "Date",
)

SUPPLIER_ID_CANDIDATES: tuple[str, ...] = (
    fs.CANON.supplier_id,
    "SupplierId",
    "SupplierID",
    "Supplier",
)
SUPPLIER_NAME_CANDIDATES: tuple[str, ...] = (
    fs.CANON.supplier_name,
    "SupplierName",
    "Name as SupplierName",
    "Supplier",
    "ShortName",
)

REVENUE_CANDIDATES: tuple[str, ...] = (
    fs.CANON.revenue,
    "Revenue",
    "revenue_shipped",
    "revenue_ordered",
    "LinesTotalPrice",
    "OrderTotalPrice",
    "TotalRevenue",
)

COST_TOTAL_CANDIDATES: tuple[str, ...] = (
    fs.CANON.cost,
    "Cost",
    "ExtCost",
    "ExtendedCost",
    "COGS",
    "TotalCost",
    "LineCost",
    "cost_shipped",
    "cost_ordered",
    "pack_cost_total",
)

COST_PER_UNIT_CANDIDATES: tuple[str, ...] = (
    "CostPerUnit",
    "CostPrice",
    "CostPrice_orderline",
    "CostPrice_po",
    "CostPrice_product",
    "CostPrice_x",
    "CostPrice_y",
    "unit_cost_effective",
    "pack_unit_cost_effective",
    "UnitCost",
)

COST_PER_LB_CANDIDATES: tuple[str, ...] = (
    "CostPerLb",
    "CostPerLB",
    "CostPerPound",
    "CostPerPounds",
    "AvgCostPerLb",
    "AvgCostPerLB",
    "avg_cost_per_lb",
    "AverageCostPerLb",
    "LandedCostPerLb",
    "LandedCostPerLB",
)

QTY_CANDIDATES: tuple[str, ...] = (
    "ShippedItems",
    fs.CANON.qty_units,
    "qty_units",
    "QuantityShipped",
    "QuantityOrdered",
    "Qty",
    "Quantity",
    "Units",
    "ItemCount",
    "pack_item_count_sum",
)

WEIGHT_CANDIDATES: tuple[str, ...] = (
    fs.CANON.weight_lb,
    "WeightLb",
    "Weight",
    "weight_lb",
    "pack_weight_lb_sum",
)

ORDER_ID_CANDIDATES: tuple[str, ...] = (
    fs.CANON.order_id,
    "OrderId",
    "OrderID",
)

PRODUCT_ID_CANDIDATES: tuple[str, ...] = (
    fs.CANON.product_id,
    "ProductId",
    "ProductID",
    "SKU",
)
PRODUCT_NAME_CANDIDATES: tuple[str, ...] = (
    fs.CANON.product_name,
    "ProductName",
    "Name as ProductName",
    "ProductDescription",
    "Description",
    "SkuName",
    "SKUName",
)

CUSTOMER_ID_CANDIDATES: tuple[str, ...] = (
    fs.CANON.customer_id,
    "CustomerId",
    "CustomerID",
)
CUSTOMER_NAME_CANDIDATES: tuple[str, ...] = (
    fs.CANON.customer_name,
    "CustomerName",
    "Name as CustomerName",
)

REGION_CANDIDATES: tuple[str, ...] = (
    fs.CANON.region,
    "RegionName",
    "Region",
    "RegionId",
)

SHIP_METHOD_CANDIDATES: tuple[str, ...] = (
    fs.CANON.ship_method,
    "ShippingMethodName",
    "ShippingMethod",
    "ShipMethodName",
    "ShipperName",
)

SALES_REP_CANDIDATES: tuple[str, ...] = (
    fs.CANON.sales_rep,
    "SalesRepName",
    "PrimarySalesRepName",
    "SalesRep",
    "SalesRepId",
    "SalesRepID",
)


def _hash_payload(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _scope_summary(scope: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "role": scope.get("role"),
        "user_id": scope.get("user_id"),
        "scope_mode": scope.get("scope_mode"),
        "scope_hash": scope.get("scope_hash"),
        "permissions_version": scope.get("permissions_version"),
    }


def _cache_key(
    kind: str,
    dataset_version: str,
    scope_summary: Mapping[str, Any],
    filter_hash: str,
    extras: Mapping[str, Any] | None = None,
) -> str:
    payload = {
        "kind": kind,
        "dataset_version": dataset_version,
        "scope": dict(scope_summary),
        "filter_hash": filter_hash,
        "extras": dict(extras or {}),
    }
    return _hash_payload(payload)


def _clone(value: Any) -> Any:
    try:
        return copy.deepcopy(value)
    except Exception:
        return value


def _safe_col(cols: set[str], *candidates: str) -> str | None:
    for cand in candidates:
        if cand and cand in cols:
            return cand
    return None


def _quote(col: str) -> str:
    return fact_store.quote_identifier(col)


def _to_list(val: Any) -> list:
    if val is None:
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, tuple):
        return list(val)
    try:
        import numpy as np  # type: ignore

        if isinstance(val, np.ndarray):
            return val.tolist()
    except Exception:
        pass
    return [val]


def _struct_list(val: Any) -> list[dict]:
    out: list[dict] = []
    for item in _to_list(val):
        if item is None:
            continue
        if isinstance(item, dict):
            out.append(item)
            continue
        try:
            out.append(dict(item))
            continue
        except Exception:
            pass
        try:
            out.append(item._asdict())  # type: ignore[attr-defined]
            continue
        except Exception:
            pass
        out.append({})
    return out


def _clean_float(val: Any, default: float = 0.0) -> float:
    try:
        fval = float(val)
        if math.isnan(fval):
            return default
        return fval
    except Exception:
        return default


def _clean_optional_float(val: Any) -> float | None:
    try:
        if val is None:
            return None
        fval = float(val)
        if math.isnan(fval):
            return None
        return fval
    except Exception:
        return None


def _clean_int(val: Any, default: int = 0) -> int:
    try:
        return int(val)
    except Exception:
        return default


def _date_to_iso(val: Any) -> str | None:
    if val in (None, ""):
        return None
    try:
        ts = pd.to_datetime(val, errors="coerce")
        if pd.isna(ts):
            return None
        return ts.date().isoformat()
    except Exception:
        try:
            return val.date().isoformat()  # type: ignore[attr-defined]
        except Exception:
            try:
                return val.isoformat()  # type: ignore[attr-defined]
            except Exception:
                return str(val)


def _execute_sql_df_with_fallback(sql: str, params: Sequence[Any], *, tag: str) -> pd.DataFrame:
    """
    DuckDB -> pandas conversion can intermittently raise `_NoValueType` errors
    under certain test/runtime stacks. Fallback to fetchall() in that case.
    """
    try:
        return fact_store.execute_sql_df(sql, params, tag=tag)
    except TypeError as exc:
        if "_NoValueType" not in str(exc):
            raise
        conn = fact_store.get_conn()
        cursor = conn.execute(sql, list(params))
        cols = [meta[0] for meta in (cursor.description or [])]
        rows = cursor.fetchall()
        return pd.DataFrame(rows, columns=cols)


def _parse_top_n(args: Any, default: int = TOP_N_DEFAULT) -> int:
    getter = args.get if hasattr(args, "get") else (lambda _k, _d=None: None)
    try:
        raw = getter("topN") or getter("top_n") or getter("top") or default
        n = int(raw)
        if n < 0:
            return default
        return min(n, TOP_N_MAX)
    except Exception:
        return default


def _parse_bool_arg(args: Any, keys: Sequence[str], default: bool = False) -> bool:
    getter = args.get if hasattr(args, "get") else (lambda _k, _d=None: None)
    for key in keys:
        raw = getter(key)
        if raw is None:
            continue
        if isinstance(raw, bool):
            return raw
        token = str(raw).strip().lower()
        if token in {"1", "true", "yes", "on", "y"}:
            return True
        if token in {"0", "false", "no", "off", "n"}:
            return False
    return default


def _suppliers_v2_requested(args: Any) -> bool:
    return _parse_bool_arg(args, ("suppliers_v2", "v2"), default=False)


def _args_getlist(args: Any, key: str) -> list[str]:
    if hasattr(args, "getlist"):
        try:
            vals = args.getlist(key)
            return [str(v).strip() for v in vals if str(v).strip()]
        except Exception:
            pass
    getter = args.get if hasattr(args, "get") else (lambda _k, _d=None: None)
    raw = getter(key)
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        out: list[str] = []
        for item in raw:
            token = str(item).strip()
            if token:
                out.append(token)
        return out
    token = str(raw).strip()
    if not token:
        return []
    if "," in token:
        return [part.strip() for part in token.split(",") if part.strip()]
    return [token]


def _normalize_segment_token(value: Any) -> str:
    token = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "marginrisk": "margin_risk",
        "datarisk": "data_risk",
        "longtail": "long_tail",
        "all_suppliers": "all",
        "all": "all",
    }
    return aliases.get(token, token)


def _parse_segment_filters(args: Any) -> list[str]:
    values = _args_getlist(args, "segment")
    values.extend(_args_getlist(args, "segments"))
    seen: set[str] = set()
    out: list[str] = []
    for val in values:
        token = _normalize_segment_token(val)
        if not token or token == "all" or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _parse_quick_filter(args: Any) -> str:
    getter = args.get if hasattr(args, "get") else (lambda _k, _d=None: None)
    raw = (
        getter("quick_filter")
        or getter("quick_filters")
        or getter("segment_quick")
        or getter("segment")
        or "all"
    )
    token = _normalize_segment_token(raw)
    return token or "all"


def _window_bounds(start_iso: str | None, end_iso: str | None) -> Dict[str, str | None]:
    try:
        start_ts = pd.to_datetime(start_iso, errors="coerce")
        end_ts = pd.to_datetime(end_iso, errors="coerce")
        if pd.isna(start_ts) or pd.isna(end_ts):
            raise ValueError("invalid current window")
        start_d = start_ts.date()
        end_d = end_ts.date()
        if end_d < start_d:
            start_d, end_d = end_d, start_d
        days = (end_d - start_d).days + 1
        prior_end = start_d - timedelta(days=1)
        prior_start = prior_end - timedelta(days=max(days - 1, 0))
        return {
            "start": start_d.isoformat(),
            "end": end_d.isoformat(),
            "prior_start": prior_start.isoformat(),
            "prior_end": prior_end.isoformat(),
            "days": str(days),
        }
    except Exception:
        return {
            "start": start_iso,
            "end": end_iso,
            "prior_start": None,
            "prior_end": None,
            "days": None,
        }


def _filters_with_window(filters: Any, start_iso: str | None, end_iso: str | None) -> Any:
    if not start_iso and not end_iso:
        return filters
    try:
        start_val = pd.to_datetime(start_iso, errors="coerce") if start_iso else None
        end_val = pd.to_datetime(end_iso, errors="coerce") if end_iso else None
        return dc_replace(filters, start=start_val, end=end_val)
    except Exception:
        return filters


def _pagination(args: Any, default_size: int = DEFAULT_PAGE_SIZE, max_size: int = MAX_PAGE_SIZE) -> Tuple[int, int]:
    getter = args.get if hasattr(args, "get") else (lambda _k, _d=None: None)
    try:
        page = max(1, int(getter("page", 1)))
    except Exception:
        page = 1
    try:
        size = int(getter("page_size") or getter("per_page") or default_size)
    except Exception:
        size = default_size
    size = max(1, min(size, max_size))
    return page, size


def _sort_params(args: Any) -> Tuple[str, str]:
    getter = args.get if hasattr(args, "get") else (lambda _k, _d=None: None)
    sort_by_raw = str(getter("sort") or getter("sort_by") or "revenue").strip().lower()
    sort_dir_raw = str(getter("sort_dir") or getter("direction") or "desc").strip().lower()
    sort_dir = "ASC" if sort_dir_raw in {"asc", "ascending", "up", "1"} else "DESC"
    mapping = {
        "supplier": "supplier_name",
        "supplier_name": "supplier_name",
        "suppliername": "supplier_name",
        "name": "supplier_name",
        "supplier_id": "supplier_id",
        "supplierid": "supplier_id",
        "revenue": "revenue",
        "revenue_current": "revenue_current",
        "revenue_prior": "revenue_prior",
        "revenue_prior_window": "revenue_prior",
        "delta_revenue": "delta_revenue",
        "delta_revenue_pct": "delta_revenue_pct",
        "cost": "cost",
        "cost_current": "cost",
        "profit": "profit",
        "profit_current": "profit",
        "profit_prior": "profit_prior",
        "delta_profit": "delta_profit",
        "margin": "margin_pct",
        "margin_pct": "margin_pct",
        "marginpct": "margin_pct",
        "margin_prior": "margin_prior_pct",
        "margin_prior_pct": "margin_prior_pct",
        "delta_margin_pp": "delta_margin_pp",
        "roi": "roi_pct",
        "roi_pct": "roi_pct",
        "roipct": "roi_pct",
        "units": "units",
        "qty": "units",
        "weight": "weight_lb",
        "weight_lb": "weight_lb",
        "weightlb": "weight_lb",
        "contribution_per_lb": "contribution_per_lb",
        "missing_cost_pct": "missing_cost_pct",
        "customers": "customers",
        "avg_sale_price_per_lb": "avg_sale_price_per_lb",
        "avgsalepriceperlb": "avg_sale_price_per_lb",
        "avg_cost_per_unit": "avg_cost_per_unit",
        "avgcostperunit": "avg_cost_per_unit",
        "avg_cost_per_lb": "avg_cost_per_lb",
        "avgcostperlb": "avg_cost_per_lb",
        "profit_per_unit": "profit_per_unit",
        "profitperunit": "profit_per_unit",
        "profit_per_lb": "profit_per_lb",
        "profitperlb": "profit_per_lb",
        "products": "products",
        "orders": "orders",
        "last_sold": "last_sold",
        "lastsold": "last_sold",
    }
    sort_by = mapping.get(sort_by_raw, "revenue")
    return sort_by, sort_dir


def _extract_search(args: Any) -> str:
    getter = args.get if hasattr(args, "get") else (lambda _k, _d=None: None)
    return str(getter("search") or getter("q") or "").strip()


def _coalesce_text_expr(cols: set[str], candidates: Sequence[str], default: str) -> str:
    parts: list[str] = []
    for cand in candidates:
        if cand in cols:
            qc = _quote(cand)
            parts.append(f"NULLIF(CAST({qc} AS VARCHAR), '')")
    if not parts:
        return default
    parts.append(default)
    if len(parts) == 1:
        return parts[0]
    return f"COALESCE({', '.join(parts)})"


def _coalesce_num_expr(cols: set[str], candidates: Sequence[str], default: str = "0") -> str:
    parts: list[str] = []
    for cand in candidates:
        if cand in cols:
            qc = _quote(cand)
            parts.append(f"CAST({qc} AS DOUBLE)")
    if not parts:
        return default
    parts.append(default)
    if len(parts) == 1:
        return parts[0]
    return f"COALESCE({', '.join(parts)})"


def _coalesce_nonzero_num_expr(cols: set[str], candidates: Sequence[str], default: str = "0") -> str:
    parts: list[str] = []
    for cand in candidates:
        if cand in cols:
            qc = _quote(cand)
            parts.append(f"NULLIF(CAST({qc} AS DOUBLE), 0)")
    if not parts:
        return default
    parts.append(default)
    if len(parts) == 1:
        return parts[0]
    return f"COALESCE({', '.join(parts)})"


def _coalesce_date_expr(cols: set[str], candidates: Sequence[str], default: str = "NULL::DATE") -> str:
    parts: list[str] = []
    for cand in candidates:
        if cand in cols:
            qc = _quote(cand)
            parts.append(f"CAST({qc} AS DATE)")
    if not parts:
        return default
    parts.append(default)
    if len(parts) == 1:
        return parts[0]
    return f"COALESCE({', '.join(parts)})"


def _required_columns(cols: set[str]) -> Dict[str, Any]:
    date_col = _safe_col(cols, fs.CANON.date, "Date")
    date_candidates = [c for c in DATE_CANDIDATES if c in cols]
    if date_col and date_col not in date_candidates:
        date_candidates.append(date_col)

    supplier_id_candidates = [c for c in SUPPLIER_ID_CANDIDATES if c in cols]
    supplier_name_candidates = [c for c in SUPPLIER_NAME_CANDIDATES if c in cols]
    revenue_candidates = [c for c in REVENUE_CANDIDATES if c in cols]

    order_candidates = [c for c in ORDER_ID_CANDIDATES if c in cols]
    product_id_candidates = [c for c in PRODUCT_ID_CANDIDATES if c in cols]
    product_name_candidates = [c for c in PRODUCT_NAME_CANDIDATES if c in cols]
    customer_id_candidates = [c for c in CUSTOMER_ID_CANDIDATES if c in cols]
    customer_name_candidates = [c for c in CUSTOMER_NAME_CANDIDATES if c in cols]
    region_candidates = [c for c in REGION_CANDIDATES if c in cols]
    ship_method_candidates = [c for c in SHIP_METHOD_CANDIDATES if c in cols]
    sales_rep_candidates = [c for c in SALES_REP_CANDIDATES if c in cols]

    qty_candidates = [c for c in QTY_CANDIDATES if c in cols]
    weight_candidates = [c for c in WEIGHT_CANDIDATES if c in cols]

    cost_total_candidates = [c for c in COST_TOTAL_CANDIDATES if c in cols]
    cost_per_unit_candidates = [c for c in COST_PER_UNIT_CANDIDATES if c in cols]
    cost_per_lb_candidates = [c for c in COST_PER_LB_CANDIDATES if c in cols]

    return {
        "date": date_col,
        "date_candidates": date_candidates,
        "supplier_id_candidates": supplier_id_candidates,
        "supplier_name_candidates": supplier_name_candidates,
        "revenue_candidates": revenue_candidates,
        "order_candidates": order_candidates,
        "product_id_candidates": product_id_candidates,
        "product_name_candidates": product_name_candidates,
        "customer_id_candidates": customer_id_candidates,
        "customer_name_candidates": customer_name_candidates,
        "region_candidates": region_candidates,
        "ship_method_candidates": ship_method_candidates,
        "sales_rep_candidates": sales_rep_candidates,
        "qty_candidates": qty_candidates,
        "weight_candidates": weight_candidates,
        "cost_total_candidates": cost_total_candidates,
        "cost_per_unit_candidates": cost_per_unit_candidates,
        "cost_per_lb_candidates": cost_per_lb_candidates,
    }


def _supplier_id_expr(cols: set[str], cols_map: Mapping[str, Any]) -> str:
    supplier_ids = list(cols_map.get("supplier_id_candidates") or [])
    supplier_names = list(cols_map.get("supplier_name_candidates") or [])
    candidates = supplier_ids + [c for c in supplier_names if c not in supplier_ids]
    return _coalesce_text_expr(cols, candidates, "'Unknown Supplier'")


def _supplier_name_expr(cols: set[str], cols_map: Mapping[str, Any], supplier_id_expr: str) -> str:
    supplier_ids = list(cols_map.get("supplier_id_candidates") or [])
    supplier_names = list(cols_map.get("supplier_name_candidates") or [])
    candidates = supplier_names + [c for c in supplier_ids if c not in supplier_names]
    return _coalesce_text_expr(cols, candidates, supplier_id_expr)


def _scoped_cte(cols: set[str], cols_map: Mapping[str, Any], where_sql: str) -> str:
    order_date_expr = _coalesce_date_expr(cols, cols_map.get("date_candidates") or (), "NULL::DATE")
    supplier_id_expr = _supplier_id_expr(cols, cols_map)
    supplier_name_expr = _supplier_name_expr(cols, cols_map, supplier_id_expr)

    order_id_expr = _coalesce_text_expr(cols, cols_map.get("order_candidates") or (), "NULL::VARCHAR")
    product_id_expr = _coalesce_text_expr(cols, cols_map.get("product_id_candidates") or (), "NULL::VARCHAR")
    product_name_expr = _coalesce_text_expr(
        cols,
        (cols_map.get("product_name_candidates") or ()) + (cols_map.get("product_id_candidates") or ()),
        product_id_expr,
    )
    customer_id_expr = _coalesce_text_expr(cols, cols_map.get("customer_id_candidates") or (), "NULL::VARCHAR")
    customer_name_expr = _coalesce_text_expr(
        cols,
        (cols_map.get("customer_name_candidates") or ()) + (cols_map.get("customer_id_candidates") or ()),
        customer_id_expr,
    )
    region_expr = _coalesce_text_expr(cols, cols_map.get("region_candidates") or (), "NULL::VARCHAR")
    ship_method_expr = _coalesce_text_expr(cols, cols_map.get("ship_method_candidates") or (), "NULL::VARCHAR")
    sales_rep_expr = _coalesce_text_expr(cols, cols_map.get("sales_rep_candidates") or (), "NULL::VARCHAR")

    # Prefer non-zero candidates so synthetic zero-filled columns do not shadow real revenue fields.
    revenue_expr = _coalesce_nonzero_num_expr(cols, cols_map.get("revenue_candidates") or (), "0")
    units_expr = _coalesce_nonzero_num_expr(cols, cols_map.get("qty_candidates") or (), "0")
    weight_expr = _coalesce_num_expr(cols, cols_map.get("weight_candidates") or (), "0")

    cost_total_expr = _coalesce_nonzero_num_expr(cols, cols_map.get("cost_total_candidates") or (), "NULL::DOUBLE")
    cost_per_unit_expr = _coalesce_nonzero_num_expr(cols, cols_map.get("cost_per_unit_candidates") or (), "NULL::DOUBLE")
    cost_per_lb_expr = _coalesce_nonzero_num_expr(cols, cols_map.get("cost_per_lb_candidates") or (), "NULL::DOUBLE")

    return f"""
        scoped_base AS (
            SELECT
                CAST({order_date_expr} AS DATE) AS order_date,
                CAST({supplier_id_expr} AS VARCHAR) AS supplier_id,
                CAST({supplier_name_expr} AS VARCHAR) AS supplier_name,
                CAST({order_id_expr} AS VARCHAR) AS order_id,
                CAST({product_id_expr} AS VARCHAR) AS product_id,
                CAST({product_name_expr} AS VARCHAR) AS product_name,
                CAST({customer_id_expr} AS VARCHAR) AS customer_id,
                CAST({customer_name_expr} AS VARCHAR) AS customer_name,
                CAST({region_expr} AS VARCHAR) AS region,
                CAST({ship_method_expr} AS VARCHAR) AS shipping_method,
                CAST({sales_rep_expr} AS VARCHAR) AS sales_rep,
                CAST({revenue_expr} AS DOUBLE) AS revenue,
                CAST({units_expr} AS DOUBLE) AS units,
                CAST({weight_expr} AS DOUBLE) AS weight_lb,
                {cost_total_expr} AS cost_total,
                {cost_per_lb_expr} AS cost_per_lb,
                {cost_per_unit_expr} AS cost_per_unit
            FROM fact
            WHERE {where_sql}
        ),
        scoped AS (
            SELECT
                order_date,
                supplier_id,
                supplier_name,
                order_id,
                product_id,
                product_name,
                customer_id,
                customer_name,
                region,
                shipping_method,
                sales_rep,
                revenue,
                units,
                weight_lb,
                COALESCE(
                    cost_total,
                    cost_per_lb * NULLIF(weight_lb, 0),
                    cost_per_unit * NULLIF(units, 0)
                ) AS cost
            FROM scoped_base
        )
    """


def _supplier_rollup_cte() -> str:
    return """
        supplier_rollup AS (
            SELECT
                supplier_id,
                supplier_name,
                SUM(revenue) AS revenue,
                SUM(units) AS units,
                SUM(weight_lb) AS weight_lb,
                SUM(cost) AS cost_sum,
                SUM(CASE WHEN cost IS NULL THEN 0 ELSE 1 END) AS cost_count,
                COUNT(DISTINCT CASE WHEN order_id IS NOT NULL AND order_id <> '' THEN order_id END) AS orders,
                COUNT(DISTINCT CASE WHEN product_id IS NOT NULL AND product_id <> '' THEN product_id END) AS products,
                COUNT(DISTINCT CASE WHEN customer_id IS NOT NULL AND customer_id <> '' THEN customer_id END) AS customers,
                MAX(order_date) AS last_sold
            FROM scoped
            GROUP BY 1,2
        ),
        supplier_enriched AS (
            SELECT
                supplier_id,
                supplier_name,
                revenue,
                CASE WHEN cost_count > 0 THEN cost_sum ELSE NULL END AS cost,
                CASE WHEN cost_count > 0 THEN revenue - cost_sum ELSE NULL END AS profit,
                CASE WHEN revenue > 0 AND cost_count > 0 THEN (revenue - cost_sum) / revenue * 100 ELSE NULL END AS margin_pct,
                CASE WHEN cost_count > 0 AND cost_sum > 0 THEN (revenue - cost_sum) / cost_sum * 100 ELSE NULL END AS roi_pct,
                units,
                weight_lb,
                CASE WHEN weight_lb > 0 THEN revenue / NULLIF(weight_lb, 0) ELSE NULL END AS avg_sale_price_per_lb,
                CASE WHEN cost_count > 0 AND units > 0 THEN cost_sum / NULLIF(units, 0) ELSE NULL END AS avg_cost_per_unit,
                CASE WHEN cost_count > 0 AND weight_lb > 0 THEN cost_sum / NULLIF(weight_lb, 0) ELSE NULL END AS avg_cost_per_lb,
                CASE WHEN cost_count > 0 AND units > 0 THEN (revenue - cost_sum) / NULLIF(units, 0) ELSE NULL END AS profit_per_unit,
                CASE WHEN cost_count > 0 AND weight_lb > 0 THEN (revenue - cost_sum) / NULLIF(weight_lb, 0) ELSE NULL END AS profit_per_lb,
                orders,
                products,
                customers,
                last_sold
            FROM supplier_rollup
        )
    """


def _table_order_expr(sort_by: str) -> str:
    mapping = {
        "supplier_id": "supplier_id",
        "supplier_name": "LOWER(supplier_name)",
        "revenue": "revenue",
        "cost": "cost",
        "profit": "profit",
        "margin_pct": "margin_pct",
        "roi_pct": "roi_pct",
        "units": "units",
        "weight_lb": "weight_lb",
        "avg_sale_price_per_lb": "avg_sale_price_per_lb",
        "avg_cost_per_unit": "avg_cost_per_unit",
        "avg_cost_per_lb": "avg_cost_per_lb",
        "profit_per_unit": "profit_per_unit",
        "profit_per_lb": "profit_per_lb",
        "products": "products",
        "orders": "orders",
        "last_sold": "last_sold",
    }
    return mapping.get(sort_by, "revenue")


def _supplier_product_sort_params(args: Any) -> Tuple[str, str]:
    getter = args.get if hasattr(args, "get") else (lambda _k, _d=None: None)
    sort_by_raw = str(getter("sort") or getter("sort_by") or "revenue").strip().lower()
    sort_dir_raw = str(getter("sort_dir") or getter("direction") or "desc").strip().lower()
    sort_dir = "ASC" if sort_dir_raw in {"asc", "ascending", "up", "1"} else "DESC"
    mapping = {
        "product": "product_name",
        "product_name": "product_name",
        "productname": "product_name",
        "name": "product_name",
        "product_id": "product_id",
        "productid": "product_id",
        "sku": "product_id",
        "revenue": "revenue",
        "cost": "cost",
        "profit": "profit",
        "margin": "margin_pct",
        "margin_pct": "margin_pct",
        "marginpct": "margin_pct",
        "units": "units",
        "qty": "units",
        "weight": "weight_lb",
        "weight_lb": "weight_lb",
        "weightlb": "weight_lb",
        "orders": "orders",
        "customers": "customers",
        "avg_sale_price": "avg_sale_price",
        "avgsaleprice": "avg_sale_price",
        "avg_cost_per_unit": "avg_cost_per_unit",
        "avgcostperunit": "avg_cost_per_unit",
    }
    sort_by = mapping.get(sort_by_raw, "revenue")
    return sort_by, sort_dir


def _supplier_product_order_expr(sort_by: str) -> str:
    mapping = {
        "product_id": "LOWER(COALESCE(product_id, ''))",
        "product_name": "LOWER(COALESCE(product_name, ''))",
        "revenue": "revenue",
        "cost": "cost",
        "profit": "profit",
        "margin_pct": "margin_pct",
        "units": "units",
        "weight_lb": "weight_lb",
        "orders": "orders",
        "customers": "customers",
        "avg_sale_price": "avg_sale_price",
        "avg_cost_per_unit": "avg_cost_per_unit",
    }
    return mapping.get(sort_by, "revenue")


def _supplier_products_sql(
    scoped_supplier_cte: str,
    sort_by: str,
    sort_dir: str,
    search: str,
    *,
    paginate: bool,
    page_size: int,
    offset: int,
) -> tuple[str, List[Any]]:
    order_expr = _supplier_product_order_expr(sort_by)
    search_sql = ""
    search_params: list[Any] = []
    if search:
        search_sql = """
            WHERE
                LOWER(COALESCE(product_name, '')) LIKE ?
                OR LOWER(COALESCE(product_id, '')) LIKE ?
        """
        token = f"%{search.lower()}%"
        search_params.extend([token, token])

    limit_sql = ""
    limit_params: list[Any] = []
    if paginate:
        limit_sql = "LIMIT ? OFFSET ?"
        limit_params.extend([page_size, offset])

    sql = f"""
        WITH
        {scoped_supplier_cte},
        prod_rollup AS (
            SELECT
                product_id,
                product_name,
                SUM(revenue) AS revenue,
                SUM(cost) AS cost_sum,
                SUM(CASE WHEN cost IS NULL THEN 0 ELSE 1 END) AS cost_count,
                SUM(units) AS units,
                SUM(weight_lb) AS weight_lb,
                COUNT(DISTINCT CASE WHEN order_id IS NOT NULL AND order_id <> '' THEN order_id END) AS orders,
                COUNT(DISTINCT CASE WHEN customer_id IS NOT NULL AND customer_id <> '' THEN customer_id END) AS customers
            FROM scoped_supplier
            WHERE product_id IS NOT NULL AND product_id <> ''
            GROUP BY 1,2
        ),
        enriched AS (
            SELECT
                product_id,
                product_name,
                revenue,
                CASE WHEN cost_count > 0 THEN cost_sum ELSE NULL END AS cost,
                CASE WHEN cost_count > 0 THEN revenue - cost_sum ELSE NULL END AS profit,
                CASE WHEN revenue > 0 AND cost_count > 0 THEN (revenue - cost_sum) / revenue * 100 ELSE NULL END AS margin_pct,
                units,
                weight_lb,
                orders,
                customers,
                CASE WHEN units > 0 THEN revenue / NULLIF(units, 0) ELSE NULL END AS avg_sale_price,
                CASE WHEN cost_count > 0 AND units > 0 THEN cost_sum / NULLIF(units, 0) ELSE NULL END AS avg_cost_per_unit
            FROM prod_rollup
        ),
        filtered AS (
            SELECT
                product_id,
                product_name,
                revenue,
                cost,
                profit,
                margin_pct,
                units,
                weight_lb,
                orders,
                customers,
                avg_sale_price,
                avg_cost_per_unit
            FROM enriched
            {search_sql}
        )
        SELECT
            product_id,
            product_name,
            revenue,
            cost,
            profit,
            margin_pct,
            units,
            weight_lb,
            orders,
            customers,
            avg_sale_price,
            avg_cost_per_unit
        FROM filtered
        ORDER BY {order_expr} {sort_dir} NULLS LAST, LOWER(COALESCE(product_name, product_id, ''))
        {limit_sql}
    """
    return sql, search_params + limit_params


def _supplier_products_count_sql(scoped_supplier_cte: str, search: str) -> tuple[str, List[Any]]:
    search_sql = ""
    search_params: list[Any] = []
    if search:
        search_sql = """
            WHERE
                LOWER(COALESCE(product_name, '')) LIKE ?
                OR LOWER(COALESCE(product_id, '')) LIKE ?
        """
        token = f"%{search.lower()}%"
        search_params.extend([token, token])

    sql = f"""
        WITH
        {scoped_supplier_cte},
        prod_rollup AS (
            SELECT
                product_id,
                product_name
            FROM scoped_supplier
            WHERE product_id IS NOT NULL AND product_id <> ''
            GROUP BY 1,2
        )
        SELECT COUNT(*) AS total_rows
        FROM prod_rollup
        {search_sql}
    """
    return sql, search_params


def _filter_hash(filters: Any, scope: Mapping[str, Any], dataset_version: str) -> tuple[str, Dict[str, Any]]:
    filters_json = filters_service.canonical_json(filters)
    scope_summary = _scope_summary(scope)
    payload = {
        "filters": json.loads(filters_json),
        "scope": scope_summary,
        "dataset_version": dataset_version,
    }
    return _hash_payload(payload), scope_summary


def _kpis_charts_sql(scoped_cte: str, top_n: int) -> str:
    return f"""
        WITH
        {scoped_cte},
        {_supplier_rollup_cte()},
        totals AS (
            SELECT
                SUM(revenue) AS total_revenue,
                SUM(cost) AS total_cost_sum,
                SUM(CASE WHEN cost IS NULL THEN 0 ELSE 1 END) AS total_cost_count,
                SUM(units) AS total_units,
                SUM(weight_lb) AS total_weight_lb,
                COUNT(DISTINCT CASE WHEN order_id IS NOT NULL AND order_id <> '' THEN order_id END) AS total_orders,
                COUNT(DISTINCT CASE WHEN product_id IS NOT NULL AND product_id <> '' THEN product_id END) AS total_products,
                COUNT(DISTINCT CASE WHEN customer_id IS NOT NULL AND customer_id <> '' THEN customer_id END) AS total_customers,
                COUNT(DISTINCT CASE WHEN supplier_id IS NOT NULL AND supplier_id <> '' THEN supplier_id END) AS supplier_count
            FROM scoped
        ),
        monthly_rollup AS (
            SELECT
                date_trunc('month', order_date) AS month_start,
                SUM(revenue) AS revenue,
                SUM(cost) AS cost_sum,
                SUM(CASE WHEN cost IS NULL THEN 0 ELSE 1 END) AS cost_count,
                SUM(units) AS units,
                SUM(weight_lb) AS weight_lb,
                COUNT(DISTINCT CASE WHEN order_id IS NOT NULL AND order_id <> '' THEN order_id END) AS orders
            FROM scoped
            GROUP BY 1
        ),
        monthly_last12 AS (
            SELECT * FROM monthly_rollup ORDER BY month_start DESC LIMIT 12
        ),
        monthly_sorted AS (
            SELECT
                strftime('%Y-%m', month_start) AS month,
                revenue,
                CASE WHEN cost_count > 0 THEN cost_sum ELSE NULL END AS cost,
                CASE WHEN cost_count > 0 THEN revenue - cost_sum ELSE NULL END AS profit,
                CASE WHEN revenue > 0 AND cost_count > 0 THEN (revenue - cost_sum) / revenue * 100 ELSE NULL END AS margin_pct,
                units,
                weight_lb,
                orders,
                month_start
            FROM monthly_last12
            ORDER BY month_start
        ),
        top_suppliers AS (
            SELECT *
            FROM supplier_enriched
            ORDER BY revenue DESC, supplier_name
            LIMIT {top_n if top_n > 0 else TOP_N_MAX}
        ),
        concentration AS (
            SELECT
                CASE
                    WHEN t.total_revenue > 0 THEN (
                        SELECT SUM(POWER(sr.revenue / t.total_revenue, 2)) * 10000
                        FROM supplier_rollup sr
                    )
                    ELSE NULL
                END AS hhi,
                CASE
                    WHEN t.total_revenue > 0 THEN (
                        SELECT SUM(revenue) / t.total_revenue * 100
                        FROM (SELECT revenue FROM supplier_rollup ORDER BY revenue DESC LIMIT 1)
                    )
                    ELSE NULL
                END AS top1_share,
                CASE
                    WHEN t.total_revenue > 0 THEN (
                        SELECT SUM(revenue) / t.total_revenue * 100
                        FROM (SELECT revenue FROM supplier_rollup ORDER BY revenue DESC LIMIT 5)
                    )
                    ELSE NULL
                END AS top5_share
            FROM totals t
        )
        SELECT
            t.total_revenue,
            CASE WHEN t.total_cost_count > 0 THEN t.total_cost_sum ELSE NULL END AS total_cost,
            CASE WHEN t.total_cost_count > 0 THEN t.total_revenue - t.total_cost_sum ELSE NULL END AS total_profit,
            t.supplier_count,
            t.total_orders,
            t.total_products,
            t.total_customers,
            t.total_units,
            t.total_weight_lb,
            CASE WHEN t.total_orders > 0 THEN t.total_revenue / NULLIF(t.total_orders, 0) ELSE 0 END AS avg_order_value,
            CASE
                WHEN t.total_revenue > 0 AND t.total_cost_count > 0 THEN (t.total_revenue - t.total_cost_sum) / t.total_revenue * 100
                ELSE NULL
            END AS avg_margin_pct,
            c.hhi,
            c.top1_share,
            c.top5_share,
            (SELECT list(struct_pack(
                month:=month,
                revenue:=revenue,
                cost:=cost,
                profit:=profit,
                margin_pct:=margin_pct,
                units:=units,
                weight_lb:=weight_lb,
                orders:=orders
            )) FROM monthly_sorted) AS monthly,
            (SELECT list(struct_pack(
                supplier_id:=supplier_id,
                supplier_name:=supplier_name,
                revenue:=revenue,
                cost:=cost,
                profit:=profit,
                margin_pct:=margin_pct,
                roi_pct:=roi_pct,
                units:=units,
                weight_lb:=weight_lb,
                avg_sale_price_per_lb:=avg_sale_price_per_lb,
                avg_cost_per_unit:=avg_cost_per_unit,
                avg_cost_per_lb:=avg_cost_per_lb,
                profit_per_unit:=profit_per_unit,
                profit_per_lb:=profit_per_lb,
                orders:=orders,
                products:=products,
                customers:=customers,
                last_sold:=last_sold
            )) FROM top_suppliers) AS top_suppliers
        FROM totals t
        CROSS JOIN concentration c
    """


def _parse_kpis_charts_row(row: Mapping[str, Any], start_iso: str | None, end_iso: str | None, top_n: int) -> Dict[str, Any]:
    monthly = _struct_list(row.get("monthly"))
    trend_labels = [str(item.get("month")) for item in monthly if item.get("month") is not None]
    trend_revenue = [_clean_float(item.get("revenue")) for item in monthly]
    trend_cost = [_clean_optional_float(item.get("cost")) for item in monthly]
    trend_profit = [_clean_optional_float(item.get("profit")) for item in monthly]
    trend_margin = [_clean_optional_float(item.get("margin_pct")) for item in monthly]

    top_list = _struct_list(row.get("top_suppliers"))
    top_rows: list[dict[str, Any]] = []
    for s in top_list:
        supplier_id = s.get("supplier_id")
        supplier_name = s.get("supplier_name") or supplier_id or "Unknown Supplier"
        top_rows.append(
            {
                "supplier_id": supplier_id,
                "supplier_name": supplier_name,
                "key": supplier_id,
                "label": supplier_name,
                "revenue": _clean_float(s.get("revenue")),
                "cost": _clean_optional_float(s.get("cost")),
                "profit": _clean_optional_float(s.get("profit")),
                "margin_pct": _clean_optional_float(s.get("margin_pct")),
                "roi_pct": _clean_optional_float(s.get("roi_pct")),
                "units": _clean_float(s.get("units")),
                "weight_lb": _clean_float(s.get("weight_lb")),
                "avg_sale_price_per_lb": _clean_optional_float(s.get("avg_sale_price_per_lb")),
                "avg_cost_per_unit": _clean_optional_float(s.get("avg_cost_per_unit")),
                "avg_cost_per_lb": _clean_optional_float(s.get("avg_cost_per_lb")),
                "profit_per_unit": _clean_optional_float(s.get("profit_per_unit")),
                "profit_per_lb": _clean_optional_float(s.get("profit_per_lb")),
                "orders": _clean_int(s.get("orders")),
                "products": _clean_int(s.get("products")),
                "customers": _clean_int(s.get("customers")),
                "last_sold": _date_to_iso(s.get("last_sold")),
            }
        )

    top_labels = [str(s.get("supplier_name") or s.get("supplier_id") or "Unknown Supplier") for s in top_rows]
    top_values = [_clean_float(s.get("revenue")) for s in top_rows]

    kpis = {
        "total_revenue": _clean_float(row.get("total_revenue")),
        "total_cost": _clean_optional_float(row.get("total_cost")),
        "total_profit": _clean_optional_float(row.get("total_profit")),
        "total_suppliers": _clean_int(row.get("supplier_count")),
        "total_orders": _clean_int(row.get("total_orders")),
        "total_products": _clean_int(row.get("total_products")),
        "total_customers": _clean_int(row.get("total_customers")),
        "total_units": _clean_float(row.get("total_units")),
        "total_weight_lb": _clean_float(row.get("total_weight_lb")),
        "avg_order_value": _clean_float(row.get("avg_order_value")),
        "avg_margin_pct": _clean_optional_float(row.get("avg_margin_pct")),
        "concentration_hhi": _clean_optional_float(row.get("hhi")),
        "concentration_top1_share": _clean_optional_float(row.get("top1_share")),
        "concentration_top5_share": _clean_optional_float(row.get("top5_share")),
        "start": start_iso,
        "end": end_iso,
    }

    trend_payload = {
        "labels": trend_labels,
        "revenue": trend_revenue,
        "cost": trend_cost,
        "profit": trend_profit,
        "margin_pct": trend_margin,
    }

    charts_payload = {
        "trend_12m": dict(trend_payload),
        "top_suppliers": {
            "labels": top_labels,
            "values": top_values,
            "rows": top_rows,
            "top_n": top_n,
        },
    }

    return {"kpis": kpis, "trend": trend_payload, "charts": charts_payload}


def _suppliers_table_sql(
    scoped_cte: str,
    sort_by: str,
    sort_dir: str,
    search: str,
    *,
    paginate: bool,
    page_size: int,
    offset: int,
) -> tuple[str, List[Any]]:
    order_expr = _table_order_expr(sort_by)
    search_sql = ""
    search_params: list[Any] = []
    if search:
        search_sql = """
            WHERE
                LOWER(COALESCE(supplier_name, '')) LIKE ?
                OR LOWER(COALESCE(supplier_id, '')) LIKE ?
        """
        token = f"%{search.lower()}%"
        search_params.extend([token, token])

    limit_sql = ""
    limit_params: list[Any] = []
    if paginate:
        limit_sql = "LIMIT ? OFFSET ?"
        limit_params.extend([page_size, offset])

    sql = f"""
        WITH
        {scoped_cte},
        {_supplier_rollup_cte()},
        filtered AS (
            SELECT
                supplier_id,
                supplier_name,
                revenue,
                cost,
                profit,
                margin_pct,
                roi_pct,
                units,
                weight_lb,
                avg_sale_price_per_lb,
                avg_cost_per_unit,
                avg_cost_per_lb,
                profit_per_unit,
                profit_per_lb,
                products,
                orders,
                customers,
                last_sold
            FROM supplier_enriched
            {search_sql}
        )
        SELECT
            supplier_id,
            supplier_name,
            revenue,
            cost,
            profit,
            margin_pct,
            roi_pct,
            units,
            weight_lb,
            avg_sale_price_per_lb,
            avg_cost_per_unit,
            avg_cost_per_lb,
            profit_per_unit,
            profit_per_lb,
            products,
            orders,
            customers,
            last_sold,
            COUNT(*) OVER() AS total_groups
        FROM filtered
        ORDER BY {order_expr} {sort_dir} NULLS LAST
        {limit_sql}
    """
    return sql, search_params + limit_params


def _table_payload_from_df(
    table_df: pd.DataFrame,
    *,
    page_num: int,
    page_size: int,
    sort_by: str,
    sort_dir: str,
    search: str,
) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    total_groups = 0
    if not table_df.empty:
        total_groups = int(table_df.iloc[0].get("total_groups", len(table_df)))
        for _, r in table_df.iterrows():
            supplier_id = r.get("supplier_id")
            supplier_name = r.get("supplier_name") or supplier_id or "Unknown Supplier"
            last_sold = _date_to_iso(r.get("last_sold"))
            row = {
                "supplier_id": supplier_id,
                "supplier_name": supplier_name,
                "key": supplier_id,
                "label": supplier_name,
                "revenue": _clean_float(r.get("revenue")),
                "cost": _clean_optional_float(r.get("cost")),
                "profit": _clean_optional_float(r.get("profit")),
                "margin_pct": _clean_optional_float(r.get("margin_pct")),
                "roi_pct": _clean_optional_float(r.get("roi_pct")),
                "units": _clean_float(r.get("units")),
                "weight_lb": _clean_float(r.get("weight_lb")),
                "avg_sale_price_per_lb": _clean_optional_float(r.get("avg_sale_price_per_lb")),
                "avg_cost_per_unit": _clean_optional_float(r.get("avg_cost_per_unit")),
                "avg_cost_per_lb": _clean_optional_float(r.get("avg_cost_per_lb")),
                "profit_per_unit": _clean_optional_float(r.get("profit_per_unit")),
                "profit_per_lb": _clean_optional_float(r.get("profit_per_lb")),
                "products": _clean_int(r.get("products")),
                "orders": _clean_int(r.get("orders")),
                "customers": _clean_int(r.get("customers")),
                "last_sold": last_sold,
                # Legacy aliases for templates that still reference old keys
                "SupplierId": supplier_id,
                "SupplierName": supplier_name,
                "Revenue": _clean_float(r.get("revenue")),
                "Cost": _clean_optional_float(r.get("cost")),
                "Profit": _clean_optional_float(r.get("profit")),
                "MarginPct": _clean_optional_float(r.get("margin_pct")),
                "ROIPct": _clean_optional_float(r.get("roi_pct")),
                "Units": _clean_float(r.get("units")),
                "WeightLb": _clean_float(r.get("weight_lb")),
                "AvgSalePricePerLb": _clean_optional_float(r.get("avg_sale_price_per_lb")),
                "AvgCostPerUnit": _clean_optional_float(r.get("avg_cost_per_unit")),
                "AvgCostPerLb": _clean_optional_float(r.get("avg_cost_per_lb")),
                "ProfitPerUnit": _clean_optional_float(r.get("profit_per_unit")),
                "ProfitPerLb": _clean_optional_float(r.get("profit_per_lb")),
                "Products": _clean_int(r.get("products")),
                "Orders": _clean_int(r.get("orders")),
                "LastSold": last_sold,
            }
            rows.append(row)

    return {
        "rows": rows,
        "page": page_num,
        "page_size": page_size,
        "total": total_groups,
        "total_rows": total_groups,
        "sort_by": sort_by,
        "sort_dir": sort_dir.lower(),
        "search": search,
    }


def _supplier_v2_stats_sql(scoped_cte: str) -> str:
    return f"""
        WITH
        {scoped_cte},
        window_params AS (
            SELECT
                CAST(? AS DATE) AS curr_start,
                CAST(? AS DATE) AS curr_end,
                CAST(? AS DATE) AS prior_start,
                CAST(? AS DATE) AS prior_end
        ),
        supplier_window AS (
            SELECT
                s.supplier_id,
                s.supplier_name,
                MIN(s.order_date) AS first_order_date,
                MAX(s.order_date) AS last_order_date,
                SUM(CASE WHEN s.order_date BETWEEN p.curr_start AND p.curr_end THEN s.revenue ELSE 0 END) AS revenue_current,
                SUM(CASE WHEN s.order_date BETWEEN p.prior_start AND p.prior_end THEN s.revenue ELSE 0 END) AS revenue_prior,
                SUM(CASE WHEN s.order_date BETWEEN p.curr_start AND p.curr_end THEN s.units ELSE 0 END) AS units_current,
                SUM(CASE WHEN s.order_date BETWEEN p.prior_start AND p.prior_end THEN s.units ELSE 0 END) AS units_prior,
                SUM(CASE WHEN s.order_date BETWEEN p.curr_start AND p.curr_end THEN s.weight_lb ELSE 0 END) AS weight_current,
                SUM(CASE WHEN s.order_date BETWEEN p.prior_start AND p.prior_end THEN s.weight_lb ELSE 0 END) AS weight_prior,
                SUM(CASE WHEN s.order_date BETWEEN p.curr_start AND p.curr_end AND s.cost IS NOT NULL THEN s.cost ELSE 0 END) AS cost_current_sum,
                SUM(CASE WHEN s.order_date BETWEEN p.prior_start AND p.prior_end AND s.cost IS NOT NULL THEN s.cost ELSE 0 END) AS cost_prior_sum,
                SUM(CASE WHEN s.order_date BETWEEN p.curr_start AND p.curr_end AND s.cost IS NOT NULL THEN 1 ELSE 0 END) AS cost_known_rows_current,
                SUM(CASE WHEN s.order_date BETWEEN p.prior_start AND p.prior_end AND s.cost IS NOT NULL THEN 1 ELSE 0 END) AS cost_known_rows_prior,
                SUM(CASE WHEN s.order_date BETWEEN p.curr_start AND p.curr_end THEN CASE WHEN s.cost IS NULL THEN 1 ELSE 0 END ELSE 0 END) AS cost_missing_rows_current,
                SUM(CASE WHEN s.order_date BETWEEN p.curr_start AND p.curr_end THEN 1 ELSE 0 END) AS rows_current,
                COUNT(DISTINCT CASE WHEN s.order_date BETWEEN p.curr_start AND p.curr_end AND s.order_id IS NOT NULL AND s.order_id <> '' THEN s.order_id END) AS orders_current,
                COUNT(DISTINCT CASE WHEN s.order_date BETWEEN p.prior_start AND p.prior_end AND s.order_id IS NOT NULL AND s.order_id <> '' THEN s.order_id END) AS orders_prior,
                COUNT(DISTINCT CASE WHEN s.order_date BETWEEN p.curr_start AND p.curr_end AND s.product_id IS NOT NULL AND s.product_id <> '' THEN s.product_id END) AS products_current,
                COUNT(DISTINCT CASE WHEN s.order_date BETWEEN p.curr_start AND p.curr_end AND s.customer_id IS NOT NULL AND s.customer_id <> '' THEN s.customer_id END) AS customers_current
            FROM scoped s
            CROSS JOIN window_params p
            GROUP BY 1,2
        )
        SELECT
            supplier_id,
            supplier_name,
            first_order_date,
            last_order_date,
            revenue_current,
            revenue_prior,
            units_current,
            units_prior,
            weight_current,
            weight_prior,
            CASE WHEN cost_known_rows_current > 0 THEN cost_current_sum ELSE NULL END AS cost_current,
            CASE WHEN cost_known_rows_prior > 0 THEN cost_prior_sum ELSE NULL END AS cost_prior,
            cost_missing_rows_current,
            rows_current,
            orders_current,
            orders_prior,
            products_current,
            customers_current
        FROM supplier_window
        WHERE revenue_current > 0
           OR revenue_prior > 0
           OR orders_current > 0
           OR orders_prior > 0
    """


def _normalize_v2_supplier_frame(frame: pd.DataFrame, *, window_end_iso: str | None) -> pd.DataFrame:
    base_cols = [
        "supplier_id",
        "supplier_name",
        "first_order_date",
        "last_order_date",
        "revenue_current",
        "revenue_prior",
        "units_current",
        "units_prior",
        "weight_current",
        "weight_prior",
        "cost_current",
        "cost_prior",
        "cost_missing_rows_current",
        "rows_current",
        "orders_current",
        "orders_prior",
        "products_current",
        "customers_current",
    ]
    if frame is None or frame.empty:
        empty = pd.DataFrame(columns=base_cols)
        empty["segment_label"] = pd.Series(dtype="object")
        empty["segment_key"] = pd.Series(dtype="object")
        return empty

    df = frame.copy()
    for col in base_cols:
        if col not in df.columns:
            df[col] = pd.NA

    numeric_zero_cols = [
        "revenue_current",
        "revenue_prior",
        "units_current",
        "units_prior",
        "weight_current",
        "weight_prior",
        "cost_missing_rows_current",
        "rows_current",
        "orders_current",
        "orders_prior",
        "products_current",
        "customers_current",
    ]
    for col in numeric_zero_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    df["cost_current"] = pd.to_numeric(df["cost_current"], errors="coerce")
    df["cost_prior"] = pd.to_numeric(df["cost_prior"], errors="coerce")

    df["supplier_id"] = df["supplier_id"].astype("string")
    fallback_name = df["supplier_id"].fillna("Unknown Supplier")
    df["supplier_name"] = df["supplier_name"].astype("string").fillna(fallback_name)

    first_dates = pd.to_datetime(df["first_order_date"], errors="coerce")
    last_dates = pd.to_datetime(df["last_order_date"], errors="coerce")
    df["first_order_date"] = first_dates.dt.date.astype("string")
    df["last_order_date"] = last_dates.dt.date.astype("string")

    df["profit_current"] = (df["revenue_current"] - df["cost_current"]).where(df["cost_current"].notna())
    df["profit_prior"] = (df["revenue_prior"] - df["cost_prior"]).where(df["cost_prior"].notna())
    df["delta_revenue"] = df["revenue_current"] - df["revenue_prior"]
    df["delta_profit"] = (df["profit_current"] - df["profit_prior"]).where(
        df["profit_current"].notna() & df["profit_prior"].notna()
    )

    df["margin_pct"] = ((df["profit_current"] / df["revenue_current"]) * 100.0).where(df["revenue_current"] > 0)
    df["margin_prior_pct"] = ((df["profit_prior"] / df["revenue_prior"]) * 100.0).where(df["revenue_prior"] > 0)
    df["delta_margin_pp"] = (df["margin_pct"] - df["margin_prior_pct"]).where(
        df["margin_pct"].notna() & df["margin_prior_pct"].notna()
    )
    df["roi_pct"] = ((df["profit_current"] / df["cost_current"]) * 100.0).where(df["cost_current"] > 0)

    delta_pct_raw = ((df["delta_revenue"] / df["revenue_prior"]) * 100.0).where(df["revenue_prior"] > 0)
    df["delta_revenue_pct_raw"] = delta_pct_raw
    df["low_base_warning"] = (df["revenue_prior"] > 0) & (df["revenue_prior"] < 500.0)
    df["delta_revenue_pct"] = delta_pct_raw.where(~df["low_base_warning"])

    status = pd.Series(["flat"] * len(df), index=df.index, dtype="object")
    new_mask = (df["revenue_prior"] <= 0) & (df["revenue_current"] > 0)
    lost_mask = (df["revenue_current"] <= 0) & (df["revenue_prior"] > 0)
    up_mask = (df["delta_revenue"] > 0) & (df["revenue_prior"] > 0)
    down_mask = (df["delta_revenue"] < 0) & (df["revenue_prior"] > 0)
    status.loc[new_mask] = "new"
    status.loc[lost_mask] = "lost"
    status.loc[up_mask & ~new_mask & ~lost_mask] = "up"
    status.loc[down_mask & ~new_mask & ~lost_mask] = "down"
    status.loc[df["low_base_warning"] & status.isin(["up", "down", "flat"])] = "low_base"
    df["delta_revenue_status"] = status
    label_map = {
        "new": "New",
        "lost": "Lost",
        "up": "Up",
        "down": "Down",
        "flat": "Flat",
        "low_base": "Low base",
    }
    df["delta_revenue_label"] = df["delta_revenue_status"].map(label_map).fillna("Flat")

    df["aov"] = (df["revenue_current"] / df["orders_current"]).where(df["orders_current"] > 0)
    df["avg_sale_price_per_lb"] = (df["revenue_current"] / df["weight_current"]).where(df["weight_current"] > 0)
    df["avg_cost_per_unit"] = (df["cost_current"] / df["units_current"]).where(
        df["cost_current"].notna() & (df["units_current"] > 0)
    )
    df["avg_cost_per_lb"] = (df["cost_current"] / df["weight_current"]).where(
        df["cost_current"].notna() & (df["weight_current"] > 0)
    )
    df["contribution_per_lb"] = (df["avg_sale_price_per_lb"] - df["avg_cost_per_lb"]).where(
        df["avg_sale_price_per_lb"].notna() & df["avg_cost_per_lb"].notna()
    )
    df["missing_cost_pct"] = ((df["cost_missing_rows_current"] / df["rows_current"]) * 100.0).where(df["rows_current"] > 0)
    df["cost_coverage_pct"] = (100.0 - df["missing_cost_pct"]).where(df["missing_cost_pct"].notna())

    window_end = pd.to_datetime(window_end_iso, errors="coerce") if window_end_iso else pd.NaT
    if pd.notna(window_end):
        last_dt = pd.to_datetime(df["last_order_date"], errors="coerce")
        days_since = (window_end.normalize() - last_dt).dt.days
        df["days_since_last_order"] = days_since
    else:
        df["days_since_last_order"] = pd.NA

    risk_band = pd.Series(["Unknown"] * len(df), index=df.index, dtype="object")
    days = pd.to_numeric(df["days_since_last_order"], errors="coerce")
    risk_band = risk_band.where(~(days < 60), "Low")
    risk_band = risk_band.where(~((days >= 60) & (days < 90)), "Medium")
    risk_band = risk_band.where(~(days >= 90), "High")
    df["risk_band"] = risk_band
    df["at_risk_flag"] = (df["risk_band"] == "High").astype(int)

    df["revenue"] = df["revenue_current"]
    df["revenue_prior_window"] = df["revenue_prior"]
    df["cost"] = df["cost_current"]
    df["profit"] = df["profit_current"]
    df["units"] = df["units_current"]
    df["weight_lb"] = df["weight_current"]
    df["orders"] = df["orders_current"]
    df["orders_prior_window"] = df["orders_prior"]
    df["products"] = df["products_current"]
    df["customers"] = df["customers_current"]
    df["last_sold"] = df["last_order_date"]
    return df


def _assign_supplier_segments(frame: pd.DataFrame, margin_target_pct: float = SUPPLIERS_MARGIN_TARGET_PCT) -> pd.DataFrame:
    if frame is None or frame.empty:
        out = frame.copy() if frame is not None else pd.DataFrame()
        out["segment_label"] = pd.Series(dtype="object")
        out["segment_key"] = pd.Series(dtype="object")
        return out

    out = frame.copy()
    revenue_positive = pd.to_numeric(out["revenue_current"], errors="coerce")
    revenue_positive = revenue_positive[revenue_positive > 0]
    strategic_cutoff = float(revenue_positive.quantile(0.80)) if not revenue_positive.empty else 0.0
    median_cutoff = float(revenue_positive.quantile(0.50)) if not revenue_positive.empty else 0.0
    growth_cutoff_pct = 20.0

    labels: list[str] = []
    for _, row in out.iterrows():
        rev = _clean_float(row.get("revenue_current"))
        margin = _clean_optional_float(row.get("margin_pct"))
        delta_pct = _clean_optional_float(row.get("delta_revenue_pct_raw"))
        missing_cost_pct = _clean_optional_float(row.get("missing_cost_pct")) or 0.0

        if missing_cost_pct >= 25.0:
            labels.append("Data risk")
            continue
        if rev >= strategic_cutoff and (margin is None or margin >= margin_target_pct):
            labels.append("Strategic")
            continue
        if rev > 0 and delta_pct is not None and delta_pct >= growth_cutoff_pct:
            labels.append("Growth")
            continue
        if rev >= max(median_cutoff, 1.0) and margin is not None and margin < margin_target_pct:
            labels.append("Margin risk")
            continue
        labels.append("Long tail")

    out["segment_label"] = labels
    out["segment_key"] = out["segment_label"].map(
        {
            "Strategic": "strategic",
            "Growth": "growth",
            "Margin risk": "margin_risk",
            "Data risk": "data_risk",
            "Long tail": "long_tail",
        }
    ).fillna("long_tail")
    return out


def _apply_v2_table_filters(
    frame: pd.DataFrame,
    *,
    search: str,
    quick_filter: str,
    segments: Sequence[str],
) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=list(frame.columns) if frame is not None else [])

    out = frame.copy()
    if search:
        token = search.lower()
        names = out["supplier_name"].astype("string").fillna("").str.lower()
        ids = out["supplier_id"].astype("string").fillna("").str.lower()
        out = out[names.str.contains(token, na=False) | ids.str.contains(token, na=False)]

    seg_tokens = {_normalize_segment_token(v) for v in segments if _normalize_segment_token(v)}
    if seg_tokens:
        out = out[out["segment_key"].isin(seg_tokens)]

    quick = _normalize_segment_token(quick_filter)
    if quick and quick != "all":
        if quick in {"strategic", "growth", "margin_risk", "data_risk", "long_tail"}:
            out = out[out["segment_key"] == quick]
        elif quick == "at_risk":
            out = out[out["at_risk_flag"] == 1]
        elif quick == "new":
            out = out[out["delta_revenue_status"] == "new"]
        elif quick == "lost":
            out = out[out["delta_revenue_status"] == "lost"]

    return out


def _sort_v2_frame(frame: pd.DataFrame, sort_by: str, sort_dir: str) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=list(frame.columns) if frame is not None else [])

    out = frame.copy()
    col = sort_by if sort_by in out.columns else "revenue_current"
    asc = str(sort_dir or "DESC").upper() == "ASC"

    if col in {"supplier_name", "supplier_id", "segment_label", "segment_key", "risk_band", "delta_revenue_status"}:
        out["__sort__"] = out[col].astype("string").fillna("").str.lower()
    else:
        out["__sort__"] = pd.to_numeric(out[col], errors="coerce")

    out = out.sort_values(
        by=["__sort__", "supplier_name"],
        ascending=[asc, True],
        na_position="last",
        kind="mergesort",
    ).drop(columns=["__sort__"])
    return out


def _v2_row_payload(row: Mapping[str, Any]) -> Dict[str, Any]:
    supplier_id = row.get("supplier_id")
    supplier_name = row.get("supplier_name") or supplier_id or "Unknown Supplier"
    revenue = _clean_float(row.get("revenue_current"))
    revenue_prior = _clean_float(row.get("revenue_prior"))
    profit = _clean_optional_float(row.get("profit_current"))
    profit_prior = _clean_optional_float(row.get("profit_prior"))
    margin_pct = _clean_optional_float(row.get("margin_pct"))
    margin_prior = _clean_optional_float(row.get("margin_prior_pct"))
    row_out: Dict[str, Any] = {
        "supplier_id": supplier_id,
        "supplier_name": supplier_name,
        "key": supplier_id,
        "label": supplier_name,
        "revenue_current": revenue,
        "revenue_prior": revenue_prior,
        "delta_revenue": _clean_float(row.get("delta_revenue")),
        "delta_revenue_pct": _clean_optional_float(row.get("delta_revenue_pct")),
        "delta_revenue_pct_raw": _clean_optional_float(row.get("delta_revenue_pct_raw")),
        "delta_revenue_status": row.get("delta_revenue_status"),
        "delta_revenue_label": row.get("delta_revenue_label"),
        "low_base_warning": bool(row.get("low_base_warning")),
        "cost": _clean_optional_float(row.get("cost_current")),
        "profit": profit,
        "profit_prior": profit_prior,
        "delta_profit": _clean_optional_float(row.get("delta_profit")),
        "margin_pct": margin_pct,
        "margin_prior_pct": margin_prior,
        "delta_margin_pp": _clean_optional_float(row.get("delta_margin_pp")),
        "roi_pct": _clean_optional_float(row.get("roi_pct")),
        "units": _clean_float(row.get("units_current")),
        "weight_lb": _clean_float(row.get("weight_current")),
        "avg_sale_price_per_lb": _clean_optional_float(row.get("avg_sale_price_per_lb")),
        "avg_cost_per_unit": _clean_optional_float(row.get("avg_cost_per_unit")),
        "avg_cost_per_lb": _clean_optional_float(row.get("avg_cost_per_lb")),
        "contribution_per_lb": _clean_optional_float(row.get("contribution_per_lb")),
        "products": _clean_int(row.get("products_current")),
        "orders": _clean_int(row.get("orders_current")),
        "orders_prior": _clean_int(row.get("orders_prior")),
        "customers": _clean_int(row.get("customers_current")),
        "aov": _clean_optional_float(row.get("aov")),
        "first_order_date": _date_to_iso(row.get("first_order_date")),
        "last_order_date": _date_to_iso(row.get("last_order_date")),
        "last_sold": _date_to_iso(row.get("last_order_date")),
        "days_since_last_order": _clean_int(row.get("days_since_last_order"), default=-1),
        "risk_band": row.get("risk_band") or "Unknown",
        "at_risk_flag": _clean_int(row.get("at_risk_flag"), default=0),
        "segment_label": row.get("segment_label") or "Long tail",
        "segment_key": row.get("segment_key") or "long_tail",
        "missing_cost_pct": _clean_optional_float(row.get("missing_cost_pct")),
        "cost_coverage_pct": _clean_optional_float(row.get("cost_coverage_pct")),
        "rows_current": _clean_int(row.get("rows_current")),
        "cost_missing_rows_current": _clean_int(row.get("cost_missing_rows_current")),
        # Legacy aliases expected by v1 template/JS.
        "SupplierId": supplier_id,
        "SupplierName": supplier_name,
        "Revenue": revenue,
        "RevenuePriorWindow": revenue_prior,
        "DeltaRevenue": _clean_float(row.get("delta_revenue")),
        "DeltaRevenuePct": _clean_optional_float(row.get("delta_revenue_pct")),
        "DeltaRevenueStatus": row.get("delta_revenue_status"),
        "DeltaRevenueLabel": row.get("delta_revenue_label"),
        "Cost": _clean_optional_float(row.get("cost_current")),
        "Profit": profit,
        "ProfitPrior": profit_prior,
        "DeltaProfit": _clean_optional_float(row.get("delta_profit")),
        "MarginPct": margin_pct,
        "MarginPriorPct": margin_prior,
        "DeltaMarginPct": _clean_optional_float(row.get("delta_margin_pp")),
        "ROIPct": _clean_optional_float(row.get("roi_pct")),
        "Units": _clean_float(row.get("units_current")),
        "WeightLb": _clean_float(row.get("weight_current")),
        "AvgSalePricePerLb": _clean_optional_float(row.get("avg_sale_price_per_lb")),
        "AvgCostPerUnit": _clean_optional_float(row.get("avg_cost_per_unit")),
        "AvgCostPerLb": _clean_optional_float(row.get("avg_cost_per_lb")),
        "ContributionPerLb": _clean_optional_float(row.get("contribution_per_lb")),
        "Products": _clean_int(row.get("products_current")),
        "Orders": _clean_int(row.get("orders_current")),
        "OrdersPrior": _clean_int(row.get("orders_prior")),
        "Customers": _clean_int(row.get("customers_current")),
        "AOV": _clean_optional_float(row.get("aov")),
        "FirstOrderDate": _date_to_iso(row.get("first_order_date")),
        "LastOrderDate": _date_to_iso(row.get("last_order_date")),
        "LastSold": _date_to_iso(row.get("last_order_date")),
        "DaysSinceLastOrder": _clean_int(row.get("days_since_last_order"), default=-1),
        "RiskBand": row.get("risk_band") or "Unknown",
        "SegmentLabel": row.get("segment_label") or "Long tail",
        "MissingCostPct": _clean_optional_float(row.get("missing_cost_pct")),
        "CostCoveragePct": _clean_optional_float(row.get("cost_coverage_pct")),
    }
    return row_out


def _v2_table_payload_from_frame(
    frame: pd.DataFrame,
    args: Any,
    *,
    paginate: bool,
) -> tuple[Dict[str, Any], pd.DataFrame]:
    page_num, page_size = _pagination(args)
    sort_by, sort_dir = _sort_params(args)
    search = _extract_search(args)
    quick_filter = _parse_quick_filter(args)
    segments = _parse_segment_filters(args)
    export_all = _parse_bool_arg(args, ("export_all", "all_rows"), default=False)

    filtered = _apply_v2_table_filters(
        frame,
        search=search,
        quick_filter=quick_filter,
        segments=segments,
    )
    sorted_df = _sort_v2_frame(filtered, sort_by, sort_dir)

    total_rows = int(len(sorted_df.index))
    if paginate and not export_all:
        offset = (page_num - 1) * page_size
        page_df = sorted_df.iloc[offset : offset + page_size]
    else:
        page_num = 1
        page_df = sorted_df

    rows = [_v2_row_payload(rec) for rec in page_df.to_dict(orient="records")]
    payload = {
        "rows": rows,
        "page": page_num,
        "page_size": page_size,
        "total": total_rows,
        "total_rows": total_rows,
        "sort_by": sort_by,
        "sort_dir": sort_dir.lower(),
        "search": search,
        "quick_filter": quick_filter,
        "segments": list(segments),
    }
    return payload, sorted_df


def _segment_summary_from_frame(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    grouped = (
        frame.groupby("segment_label", dropna=False)
        .agg(
            suppliers=("supplier_id", "nunique"),
            revenue=("revenue_current", "sum"),
            profit=("profit_current", "sum"),
            avg_margin_pct=("margin_pct", "mean"),
            avg_orders=("orders_current", "mean"),
            median_days_since_last=("days_since_last_order", "median"),
        )
        .reset_index()
    )
    total_revenue = float(grouped["revenue"].sum()) if not grouped.empty else 0.0
    grouped["share_pct"] = (grouped["revenue"] / total_revenue * 100.0) if total_revenue > 0 else 0.0
    order_map = {
        "Strategic": 1,
        "Growth": 2,
        "Margin risk": 3,
        "Data risk": 4,
        "Long tail": 5,
    }
    grouped["segment_order"] = grouped["segment_label"].map(order_map).fillna(99)
    grouped = grouped.sort_values(["segment_order", "revenue"], ascending=[True, False])
    rows: list[dict[str, Any]] = []
    for _, rec in grouped.iterrows():
        rows.append(
            {
                "segment": rec.get("segment_label"),
                "suppliers": _clean_int(rec.get("suppliers")),
                "revenue": _clean_float(rec.get("revenue")),
                "profit": _clean_optional_float(rec.get("profit")),
                "avg_margin_pct": _clean_optional_float(rec.get("avg_margin_pct")),
                "avg_orders": _clean_optional_float(rec.get("avg_orders")),
                "median_days_since_last": _clean_optional_float(rec.get("median_days_since_last")),
                "share_pct": _clean_optional_float(rec.get("share_pct")),
            }
        )
    return rows


def _movers_payload_from_frame(frame: pd.DataFrame) -> Dict[str, Any]:
    if frame is None or frame.empty:
        return {"rows": [], "top_gainers": [], "top_decliners": []}
    cols = [
        "supplier_id",
        "supplier_name",
        "revenue_current",
        "revenue_prior",
        "delta_revenue",
        "delta_revenue_pct",
        "delta_revenue_status",
        "delta_revenue_label",
        "segment_label",
        "margin_pct",
    ]
    movers = frame.loc[:, [c for c in cols if c in frame.columns]].copy()
    movers = movers.sort_values("delta_revenue", ascending=False, na_position="last")

    def _rows(df: pd.DataFrame) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            out.append(
                {
                    "supplier_id": row.get("supplier_id"),
                    "supplier_name": row.get("supplier_name"),
                    "revenue_current": _clean_float(row.get("revenue_current")),
                    "revenue_prior": _clean_float(row.get("revenue_prior")),
                    "delta_revenue": _clean_float(row.get("delta_revenue")),
                    "delta_revenue_pct": _clean_optional_float(row.get("delta_revenue_pct")),
                    "delta_revenue_status": row.get("delta_revenue_status"),
                    "delta_revenue_label": row.get("delta_revenue_label"),
                    "segment_label": row.get("segment_label"),
                    "margin_pct": _clean_optional_float(row.get("margin_pct")),
                }
            )
        return out

    top_gainers_df = movers.sort_values("delta_revenue", ascending=False, na_position="last").head(10)
    top_decliners_df = movers.sort_values("delta_revenue", ascending=True, na_position="last").head(10)
    return {
        "rows": _rows(movers),
        "top_gainers": _rows(top_gainers_df),
        "top_decliners": _rows(top_decliners_df),
    }


def _risk_payload_from_frame(frame: pd.DataFrame, *, margin_target_pct: float = SUPPLIERS_MARGIN_TARGET_PCT) -> Dict[str, Any]:
    if frame is None or frame.empty:
        return {"margin_leakage": [], "data_risk": [], "summary": {}}

    margin_df = frame.copy()
    margin_df = margin_df[
        (pd.to_numeric(margin_df["revenue_current"], errors="coerce") > 0)
        & (pd.to_numeric(margin_df["margin_pct"], errors="coerce") < margin_target_pct)
    ].copy()
    margin_df["profit_uplift_target"] = (
        (pd.to_numeric(margin_df["revenue_current"], errors="coerce") * (margin_target_pct / 100.0))
        - pd.to_numeric(margin_df["profit_current"], errors="coerce")
    ).clip(lower=0.0)
    margin_df = margin_df.sort_values(["profit_uplift_target", "revenue_current"], ascending=[False, False])

    data_risk_df = frame.copy()
    data_risk_df = data_risk_df[pd.to_numeric(data_risk_df["missing_cost_pct"], errors="coerce") >= 10.0].copy()
    data_risk_df = data_risk_df.sort_values(["missing_cost_pct", "revenue_current"], ascending=[False, False])

    def _margin_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            out.append(
                {
                    "supplier_id": row.get("supplier_id"),
                    "supplier_name": row.get("supplier_name"),
                    "revenue": _clean_float(row.get("revenue_current")),
                    "profit": _clean_optional_float(row.get("profit_current")),
                    "margin_pct": _clean_optional_float(row.get("margin_pct")),
                    "target_margin_pct": margin_target_pct,
                    "profit_uplift_target": _clean_optional_float(row.get("profit_uplift_target")),
                }
            )
        return out

    def _risk_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            out.append(
                {
                    "supplier_id": row.get("supplier_id"),
                    "supplier_name": row.get("supplier_name"),
                    "revenue": _clean_float(row.get("revenue_current")),
                    "missing_cost_pct": _clean_optional_float(row.get("missing_cost_pct")),
                    "cost_coverage_pct": _clean_optional_float(row.get("cost_coverage_pct")),
                    "missing_rows": _clean_int(row.get("cost_missing_rows_current")),
                    "rows_current": _clean_int(row.get("rows_current")),
                }
            )
        return out

    margin_rows = _margin_rows(margin_df)
    data_risk_rows = _risk_rows(data_risk_df)
    total_uplift = sum(_clean_float(r.get("profit_uplift_target")) for r in margin_rows)
    return {
        "margin_leakage": margin_rows,
        "data_risk": data_risk_rows,
        "summary": {
            "margin_risk_suppliers": len(margin_rows),
            "data_risk_suppliers": len(data_risk_rows),
            "target_margin_pct": margin_target_pct,
            "profit_uplift_target": total_uplift,
        },
    }


def _concentration_payload_from_frame(frame: pd.DataFrame) -> Dict[str, Any]:
    if frame is None or frame.empty:
        return {
            "hhi": None,
            "top1_share": None,
            "top5_share": None,
            "level": "unknown",
            "pareto_rows": [],
        }
    conc = frame.copy()
    conc = conc[pd.to_numeric(conc["revenue_current"], errors="coerce") > 0].copy()
    if conc.empty:
        return {
            "hhi": None,
            "top1_share": None,
            "top5_share": None,
            "level": "unknown",
            "pareto_rows": [],
        }
    conc = conc.sort_values("revenue_current", ascending=False).reset_index(drop=True)
    total_revenue = float(conc["revenue_current"].sum())
    if total_revenue <= 0:
        return {
            "hhi": None,
            "top1_share": None,
            "top5_share": None,
            "level": "unknown",
            "pareto_rows": [],
        }

    conc["share_pct"] = (conc["revenue_current"] / total_revenue) * 100.0
    conc["cumulative_share_pct"] = conc["share_pct"].cumsum()
    hhi = float(((conc["revenue_current"] / total_revenue) ** 2).sum() * 10000.0)
    top1_share = float(conc["share_pct"].iloc[0]) if not conc.empty else 0.0
    top5_share = float(conc["share_pct"].head(5).sum()) if not conc.empty else 0.0

    if hhi >= 2500:
        level = "high"
    elif hhi >= 1500:
        level = "medium"
    else:
        level = "low"

    pareto_rows: list[dict[str, Any]] = []
    for idx, row in conc.head(30).iterrows():
        pareto_rows.append(
            {
                "rank": _clean_int(idx + 1),
                "supplier_id": row.get("supplier_id"),
                "supplier_name": row.get("supplier_name"),
                "revenue": _clean_float(row.get("revenue_current")),
                "share_pct": _clean_optional_float(row.get("share_pct")),
                "cumulative_share_pct": _clean_optional_float(row.get("cumulative_share_pct")),
            }
        )

    return {
        "hhi": hhi,
        "top1_share": top1_share,
        "top5_share": top5_share,
        "level": level,
        "pareto_rows": pareto_rows,
    }


def _suppliers_narrative(
    *,
    total_revenue: float,
    revenue_prior: float,
    top_gainers: Sequence[Mapping[str, Any]],
    top_decliners: Sequence[Mapping[str, Any]],
    margin_shift_supplier: str | None,
) -> str:
    delta = total_revenue - revenue_prior
    direction = "up" if delta >= 0 else "down"
    pct = (abs(delta) / revenue_prior * 100.0) if revenue_prior > 0 else None
    gainers_txt = ", ".join([str(r.get("supplier_name")) for r in top_gainers[:2] if r.get("supplier_name")]) or "n/a"
    decliners_txt = ", ".join([str(r.get("supplier_name")) for r in top_decliners[:2] if r.get("supplier_name")]) or "n/a"
    if pct is not None:
        base = f"Revenue {direction} by ${abs(delta):,.0f} ({pct:.1f}%) vs prior window."
    else:
        base = f"Revenue {direction} by ${abs(delta):,.0f} vs prior window."
    margin_txt = f" Margin shift is most visible for {margin_shift_supplier}." if margin_shift_supplier else ""
    return f"{base} Top gainers: {gainers_txt}. Top decliners: {decliners_txt}.{margin_txt}".strip()


def _suppliers_v2_base_frame(
    filters: Any,
    scope: Dict[str, Any],
    cols: set[str],
    cols_map: Mapping[str, Any],
    dataset_version: str,
    filter_hash: str,
    scope_summary: Mapping[str, Any],
    start_iso: str | None,
    end_iso: str | None,
) -> tuple[pd.DataFrame, Dict[str, Any], bool]:
    window = _window_bounds(start_iso, end_iso)
    curr_start = window.get("start") or start_iso
    curr_end = window.get("end") or end_iso
    prior_start = window.get("prior_start") or curr_start
    prior_end = window.get("prior_end") or curr_start

    cache_key = _cache_key(
        "suppliers.v2.base",
        dataset_version,
        scope_summary,
        filter_hash,
        {
            "curr_start": curr_start,
            "curr_end": curr_end,
            "prior_start": prior_start,
            "prior_end": prior_end,
        },
    )

    def _build() -> Dict[str, Any]:
        expanded_filters = _filters_with_window(filters, prior_start, curr_end)
        where_sql, params, _, _ = fact_store.build_where_clause(
            expanded_filters,
            cols,
            scope,
            apply_default_window=True,
        )
        scoped_cte = _scoped_cte(cols, cols_map, where_sql)
        sql = _supplier_v2_stats_sql(scoped_cte)
        sql_params = list(params) + [curr_start, curr_end, prior_start, prior_end]
        frame = _execute_sql_df_with_fallback(sql, sql_params, tag="suppliers.v2.base")
        normalized = _normalize_v2_supplier_frame(frame, window_end_iso=curr_end)
        segmented = _assign_supplier_segments(normalized)
        return {
            "rows": segmented.to_dict(orient="records"),
            "window": {
                "start": curr_start,
                "end": curr_end,
                "prior_start": prior_start,
                "prior_end": prior_end,
            },
        }

    payload, hit = _ANALYTICS_CACHE.get_or_compute(cache_key, TABLE_TTL_SECONDS, _build)
    payload = _clone(payload) if isinstance(payload, dict) else {"rows": [], "window": {}}
    frame = pd.DataFrame.from_records(payload.get("rows") or [])
    return frame, payload.get("window") or {}, bool(hit)


def _build_suppliers_bundle_v2(
    filters: Any,
    scope: Dict[str, Any],
    args: Any,
    *,
    cols: set[str],
    cols_map: Mapping[str, Any],
    dataset_version: str,
    filter_hash: str,
    scope_summary: Mapping[str, Any],
    where_sql: str,
    params: Sequence[Any],
    start_iso: str | None,
    end_iso: str | None,
    scoped_cte: str,
) -> Dict[str, Any]:
    top_n = _parse_top_n(args)
    kpi_cache_key = _cache_key(
        "suppliers.kpis_charts.v2",
        dataset_version,
        scope_summary,
        filter_hash,
        {"top_n": top_n},
    )

    def _build_kpis_charts() -> Dict[str, Any]:
        sql = _kpis_charts_sql(scoped_cte, top_n)
        df = _execute_sql_df_with_fallback(sql, params, tag="suppliers.kpis_charts.v2")
        row = df.iloc[0].to_dict() if not df.empty else {}
        return _parse_kpis_charts_row(row, start_iso, end_iso, top_n)

    kpi_payload, kpi_hit = _KPI_CHART_CACHE.get_or_compute(kpi_cache_key, KPI_CHART_TTL_SECONDS, _build_kpis_charts)
    kpi_payload = _clone(kpi_payload)

    base_frame, window_meta, base_hit = _suppliers_v2_base_frame(
        filters,
        scope,
        cols,
        cols_map,
        dataset_version,
        filter_hash,
        scope_summary,
        start_iso,
        end_iso,
    )

    table_payload, filtered_table_df = _v2_table_payload_from_frame(base_frame, args, paginate=True)
    concentration = _concentration_payload_from_frame(base_frame)
    segments_summary = _segment_summary_from_frame(base_frame)
    movers_payload = _movers_payload_from_frame(base_frame)
    risk_payload = _risk_payload_from_frame(base_frame, margin_target_pct=SUPPLIERS_MARGIN_TARGET_PCT)

    total_revenue = _clean_float(base_frame.get("revenue_current", pd.Series(dtype="float64")).sum()) if not base_frame.empty else 0.0
    total_revenue_prior = _clean_float(base_frame.get("revenue_prior", pd.Series(dtype="float64")).sum()) if not base_frame.empty else 0.0
    total_profit = _clean_optional_float(base_frame.get("profit_current", pd.Series(dtype="float64")).sum()) if not base_frame.empty else None
    total_profit_prior = _clean_optional_float(base_frame.get("profit_prior", pd.Series(dtype="float64")).sum()) if not base_frame.empty else None

    margin_pct = ((total_profit / total_revenue) * 100.0) if (total_profit is not None and total_revenue > 0) else None
    margin_prior_pct = (
        ((total_profit_prior / total_revenue_prior) * 100.0)
        if (total_profit_prior is not None and total_revenue_prior > 0)
        else None
    )
    margin_delta_pp = (margin_pct - margin_prior_pct) if (margin_pct is not None and margin_prior_pct is not None) else None

    rows_current = _clean_float(base_frame.get("rows_current", pd.Series(dtype="float64")).sum()) if not base_frame.empty else 0.0
    cost_missing_rows = _clean_float(base_frame.get("cost_missing_rows_current", pd.Series(dtype="float64")).sum()) if not base_frame.empty else 0.0
    cost_coverage_pct = ((rows_current - cost_missing_rows) / rows_current * 100.0) if rows_current > 0 else None

    active_suppliers = int((pd.to_numeric(base_frame.get("revenue_current"), errors="coerce") > 0).sum()) if not base_frame.empty else 0
    suppliers_total = int(base_frame["supplier_id"].nunique()) if not base_frame.empty and "supplier_id" in base_frame.columns else 0
    active_30d = int((pd.to_numeric(base_frame.get("days_since_last_order"), errors="coerce") <= 30).sum()) if not base_frame.empty else 0
    at_risk_mask = pd.to_numeric(base_frame.get("at_risk_flag"), errors="coerce") == 1 if not base_frame.empty else pd.Series(dtype="bool")
    at_risk_count = int(at_risk_mask.sum()) if not base_frame.empty else 0
    revenue_at_risk = _clean_float(base_frame.loc[at_risk_mask, "revenue_current"].sum()) if not base_frame.empty else 0.0

    margin_shift_supplier = None
    if not base_frame.empty and "delta_margin_pp" in base_frame.columns:
        margin_sorted = base_frame.copy()
        margin_sorted["abs_margin_delta"] = pd.to_numeric(margin_sorted["delta_margin_pp"], errors="coerce").abs()
        margin_sorted = margin_sorted.sort_values("abs_margin_delta", ascending=False, na_position="last")
        if not margin_sorted.empty:
            margin_shift_supplier = margin_sorted.iloc[0].get("supplier_name")

    narrative = _suppliers_narrative(
        total_revenue=total_revenue,
        revenue_prior=total_revenue_prior,
        top_gainers=movers_payload.get("top_gainers") or [],
        top_decliners=movers_payload.get("top_decliners") or [],
        margin_shift_supplier=str(margin_shift_supplier) if margin_shift_supplier else None,
    )

    kpis = dict(kpi_payload.get("kpis", {}) or {})
    kpis.update(
        {
            "total_revenue": total_revenue,
            "total_revenue_prior": total_revenue_prior,
            "revenue_delta": total_revenue - total_revenue_prior,
            "revenue_delta_pct": ((total_revenue - total_revenue_prior) / total_revenue_prior * 100.0)
            if total_revenue_prior > 0
            else None,
            "total_profit": total_profit,
            "total_profit_prior": total_profit_prior,
            "profit_delta": (total_profit - total_profit_prior)
            if (total_profit is not None and total_profit_prior is not None)
            else None,
            "margin_pct": margin_pct,
            "margin_prior_pct": margin_prior_pct,
            "margin_delta_pp": margin_delta_pp,
            "cost_coverage_pct": cost_coverage_pct,
            "cost_missing_rows": _clean_int(cost_missing_rows),
            "active_suppliers": active_suppliers,
            "active_suppliers_30d": active_30d,
            "suppliers_total": suppliers_total,
            "at_risk_suppliers": at_risk_count,
            "revenue_at_risk": revenue_at_risk,
            "concentration_hhi": concentration.get("hhi"),
            "concentration_top1_share": concentration.get("top1_share"),
            "concentration_top5_share": concentration.get("top5_share"),
            "window": {
                "start": window_meta.get("start") or start_iso,
                "end": window_meta.get("end") or end_iso,
                "prior_start": window_meta.get("prior_start"),
                "prior_end": window_meta.get("prior_end"),
            },
            "narrative": narrative,
        }
    )

    charts = dict(kpi_payload.get("charts", {}) or {})
    charts["concentration_pareto"] = concentration.get("pareto_rows") or []
    charts["revenue_profit_trend"] = charts.get("trend_12m", {})

    payload = {
        "kpis": kpis,
        "trend": kpi_payload.get("trend", {}),
        "charts": charts,
        "table": table_payload,
        "segments": {
            "summary": segments_summary,
        },
        "movers": movers_payload,
        "risk_opportunities": risk_payload,
        "executive_summary": {
            "narrative": narrative,
            "active_suppliers_30d": active_30d,
            "active_suppliers": active_suppliers,
            "suppliers_total": suppliers_total,
            "at_risk_suppliers": at_risk_count,
            "revenue_at_risk": revenue_at_risk,
            "cost_coverage_pct": cost_coverage_pct,
        },
        "meta": {
            "page_id": "suppliers",
            "suppliers_v2": True,
            "top_n": top_n,
            "window_start": window_meta.get("start") or start_iso,
            "window_end": window_meta.get("end") or end_iso,
            "prior_window_start": window_meta.get("prior_start"),
            "prior_window_end": window_meta.get("prior_end"),
            "cache_parts": {
                "kpis_charts": bool(kpi_hit),
                "analytics": bool(base_hit),
                "table": False,
            },
            "table_rows_after_filters": int(len(filtered_table_df.index)),
        },
    }
    return payload


def build_suppliers_bundle(filters: Any, scope: Dict[str, Any], args: Any) -> Dict[str, Any]:
    cols = fact_store.list_columns()
    cols_map = _required_columns(cols)
    missing = []
    if not cols_map.get("date"):
        missing.append("date")
    if not cols_map.get("revenue_candidates"):
        missing.append("revenue")
    if not (cols_map.get("supplier_id_candidates") or cols_map.get("supplier_name_candidates")):
        missing.append("supplier_id/supplier_name")
    if missing:
        return {
            "error": {"message": "Required columns missing for suppliers bundle: " + ", ".join(missing)},
            "meta": {"cached": False},
        }

    dataset_version = fact_store.cache_buster()
    filter_hash, scope_summary = _filter_hash(filters, scope, dataset_version)

    where_sql, params, start_iso, end_iso = fact_store.build_where_clause(
        filters, cols, scope, apply_default_window=True
    )
    scoped_cte = _scoped_cte(cols, cols_map, where_sql)

    if _suppliers_v2_requested(args):
        return _build_suppliers_bundle_v2(
            filters,
            scope,
            args,
            cols=cols,
            cols_map=cols_map,
            dataset_version=dataset_version,
            filter_hash=filter_hash,
            scope_summary=scope_summary,
            where_sql=where_sql,
            params=params,
            start_iso=start_iso,
            end_iso=end_iso,
            scoped_cte=scoped_cte,
        )

    top_n = _parse_top_n(args)
    kpi_cache_key = _cache_key(
        "suppliers.kpis_charts",
        dataset_version,
        scope_summary,
        filter_hash,
        {"top_n": top_n},
    )

    def _build_kpis_charts() -> Dict[str, Any]:
        sql = _kpis_charts_sql(scoped_cte, top_n)
        df = fact_store.execute_sql_df(sql, params, tag="suppliers.kpis_charts")
        row = df.iloc[0].to_dict() if not df.empty else {}
        return _parse_kpis_charts_row(row, start_iso, end_iso, top_n)

    kpi_payload, kpi_hit = _KPI_CHART_CACHE.get_or_compute(kpi_cache_key, KPI_CHART_TTL_SECONDS, _build_kpis_charts)
    kpi_payload = _clone(kpi_payload)

    page_num, page_size = _pagination(args)
    sort_by, sort_dir = _sort_params(args)
    search = _extract_search(args)
    offset = (page_num - 1) * page_size

    table_cache_key = _cache_key(
        "suppliers.table",
        dataset_version,
        scope_summary,
        filter_hash,
        {
            "page": page_num,
            "page_size": page_size,
            "sort_by": sort_by,
            "sort_dir": sort_dir,
            "search": search,
        },
    )

    def _build_table() -> Dict[str, Any]:
        sql, table_params = _suppliers_table_sql(
            scoped_cte,
            sort_by,
            sort_dir,
            search,
            paginate=True,
            page_size=page_size,
            offset=offset,
        )
        df = fact_store.execute_sql_df(sql, params + table_params, tag="suppliers.table")
        return _table_payload_from_df(
            df,
            page_num=page_num,
            page_size=page_size,
            sort_by=sort_by,
            sort_dir=sort_dir,
            search=search,
        )

    table_payload, table_hit = _TABLE_CACHE.get_or_compute(table_cache_key, TABLE_TTL_SECONDS, _build_table)
    table_payload = _clone(table_payload)

    payload = {
        "kpis": kpi_payload.get("kpis", {}),
        "trend": kpi_payload.get("trend", {}),
        "charts": kpi_payload.get("charts", {}),
        "table": table_payload,
        "meta": {
            "page_id": "suppliers",
            "top_n": top_n,
            "cache_parts": {"kpis_charts": bool(kpi_hit), "table": bool(table_hit)},
        },
    }
    return payload


def build_suppliers_table_frame(filters: Any, scope: Dict[str, Any], args: Any) -> tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Export helper: returns the full filtered + sorted supplier table without pagination.
    This reuses the same DuckDB SQL generator used by the on-page table.
    """
    cols = fact_store.list_columns()
    cols_map = _required_columns(cols)
    if not cols_map.get("date") or not cols_map.get("revenue_candidates"):
        return pd.DataFrame(), {"total_rows": 0}

    if _suppliers_v2_requested(args):
        dataset_version = fact_store.cache_buster()
        filter_hash, scope_summary = _filter_hash(filters, scope, dataset_version)
        where_sql, params, start_iso, end_iso = fact_store.build_where_clause(
            filters, cols, scope, apply_default_window=True
        )
        scoped_cte = _scoped_cte(cols, cols_map, where_sql)
        _ = params  # explicit for parity with v1 window resolver
        base_frame, window_meta, _cache_hit = _suppliers_v2_base_frame(
            filters,
            scope,
            cols,
            cols_map,
            dataset_version,
            filter_hash,
            scope_summary,
            start_iso,
            end_iso,
        )
        table_payload, _filtered = _v2_table_payload_from_frame(base_frame, args, paginate=False)
        frame = pd.DataFrame.from_records(table_payload.get("rows") or [])
        rename_map = {
            "supplier_name": "Supplier",
            "supplier_id": "Supplier ID",
            "segment_label": "Segment",
            "risk_band": "Risk Band",
            "revenue_current": "Revenue",
            "revenue_prior": "Revenue (Prior Window)",
            "delta_revenue": "Delta Revenue",
            "delta_revenue_pct": "Delta Revenue %",
            "delta_revenue_label": "Delta Status",
            "cost": "Cost",
            "profit": "Profit",
            "profit_prior": "Profit (Prior Window)",
            "delta_profit": "Delta Profit",
            "margin_pct": "Margin %",
            "margin_prior_pct": "Margin % (Prior Window)",
            "delta_margin_pp": "Delta Margin (pp)",
            "orders": "Orders",
            "orders_prior": "Orders (Prior Window)",
            "customers": "Customers",
            "products": "Products",
            "units": "Units",
            "weight_lb": "Weight (lb)",
            "aov": "AOV",
            "avg_sale_price_per_lb": "ASP / lb",
            "avg_cost_per_lb": "Avg Cost / lb",
            "contribution_per_lb": "Contribution / lb",
            "missing_cost_pct": "Missing Cost %",
            "cost_coverage_pct": "Cost Coverage %",
            "first_order_date": "First Order Date",
            "last_order_date": "Last Order Date",
            "days_since_last_order": "Days Since Last Order",
        }
        if not frame.empty:
            frame = frame.rename(columns={k: v for k, v in rename_map.items() if k in frame.columns})
        meta = {
            "total_rows": int(table_payload.get("total_rows") or 0),
            "sort_by": table_payload.get("sort_by"),
            "sort_dir": table_payload.get("sort_dir"),
            "search": table_payload.get("search"),
            "quick_filter": table_payload.get("quick_filter"),
            "segments": table_payload.get("segments") or [],
            "start": window_meta.get("start") or start_iso,
            "end": window_meta.get("end") or end_iso,
            "prior_start": window_meta.get("prior_start"),
            "prior_end": window_meta.get("prior_end"),
        }
        return frame, meta

    where_sql, params, start_iso, end_iso = fact_store.build_where_clause(
        filters, cols, scope, apply_default_window=True
    )
    scoped_cte = _scoped_cte(cols, cols_map, where_sql)

    sort_by, sort_dir = _sort_params(args)
    search = _extract_search(args)
    sql, table_params = _suppliers_table_sql(
        scoped_cte,
        sort_by,
        sort_dir,
        search,
        paginate=False,
        page_size=0,
        offset=0,
    )
    df = fact_store.execute_sql_df(sql, params + table_params, tag="suppliers.export.table")
    if "total_groups" in df.columns:
        df = df.drop(columns=["total_groups"])
    if "last_sold" in df.columns:
        last = pd.to_datetime(df["last_sold"], errors="coerce")
        df["last_sold"] = last.dt.date.astype("string")

    rename_map = {
        "supplier_name": "Supplier",
        "supplier_id": "Supplier ID",
        "revenue": "Revenue",
        "cost": "Cost",
        "profit": "Profit",
        "margin_pct": "Margin %",
        "roi_pct": "ROI %",
        "units": "Units",
        "weight_lb": "Weight (lb)",
        "avg_sale_price_per_lb": "Avg Sale Price / lb",
        "avg_cost_per_unit": "Avg Cost / Unit",
        "avg_cost_per_lb": "Avg Cost / lb",
        "profit_per_unit": "Profit / Unit",
        "profit_per_lb": "Profit / lb",
        "products": "Products",
        "orders": "Orders",
        "customers": "Customers",
        "last_sold": "Last Sold",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    meta = {
        "total_rows": int(len(df)),
        "sort_by": sort_by,
        "sort_dir": sort_dir.lower(),
        "search": search,
        "start": start_iso,
        "end": end_iso,
    }
    return df, meta


def build_suppliers_export_dataset(
    filters: Any,
    scope: Dict[str, Any],
    args: Any,
    dataset: str,
) -> tuple[pd.DataFrame, Dict[str, Any]]:
    token = str(dataset or "table").strip().lower()
    aliases = {
        "suppliers": "table",
        "overview": "table",
        "mover": "movers",
        "segment": "segments",
        "segment_summary": "segments",
        "data_quality_risk": "risk",
        "margin_leakage": "risk",
        "pareto": "concentration",
    }
    token = aliases.get(token, token)

    if token == "table" and not _suppliers_v2_requested(args):
        return build_suppliers_table_frame(filters, scope, args)

    cols = fact_store.list_columns()
    cols_map = _required_columns(cols)
    if not cols_map.get("date") or not cols_map.get("revenue_candidates"):
        return pd.DataFrame(), {"total_rows": 0, "dataset": token}

    dataset_version = fact_store.cache_buster()
    filter_hash, scope_summary = _filter_hash(filters, scope, dataset_version)
    where_sql, params, start_iso, end_iso = fact_store.build_where_clause(
        filters, cols, scope, apply_default_window=True
    )
    scoped_cte = _scoped_cte(cols, cols_map, where_sql)
    _ = params
    _ = scoped_cte
    base_frame, window_meta, _cache_hit = _suppliers_v2_base_frame(
        filters,
        scope,
        cols,
        cols_map,
        dataset_version,
        filter_hash,
        scope_summary,
        start_iso,
        end_iso,
    )

    if token == "table":
        table_payload, _filtered = _v2_table_payload_from_frame(base_frame, args, paginate=False)
        frame = pd.DataFrame.from_records(table_payload.get("rows") or [])
        total_rows = int(table_payload.get("total_rows") or len(frame.index))
        meta = {
            "dataset": token,
            "total_rows": total_rows,
            "sort_by": table_payload.get("sort_by"),
            "sort_dir": table_payload.get("sort_dir"),
            "search": table_payload.get("search"),
            "quick_filter": table_payload.get("quick_filter"),
            "segments": table_payload.get("segments") or [],
            "start": window_meta.get("start") or start_iso,
            "end": window_meta.get("end") or end_iso,
            "prior_start": window_meta.get("prior_start"),
            "prior_end": window_meta.get("prior_end"),
        }
        return frame, meta

    if token == "movers":
        movers_payload = _movers_payload_from_frame(base_frame)
        frame = pd.DataFrame.from_records(movers_payload.get("rows") or [])
        meta = {
            "dataset": token,
            "total_rows": int(len(frame.index)),
            "start": window_meta.get("start") or start_iso,
            "end": window_meta.get("end") or end_iso,
            "prior_start": window_meta.get("prior_start"),
            "prior_end": window_meta.get("prior_end"),
        }
        return frame, meta

    if token == "segments":
        rows = _segment_summary_from_frame(base_frame)
        frame = pd.DataFrame.from_records(rows)
        meta = {
            "dataset": token,
            "total_rows": int(len(frame.index)),
            "start": window_meta.get("start") or start_iso,
            "end": window_meta.get("end") or end_iso,
            "prior_start": window_meta.get("prior_start"),
            "prior_end": window_meta.get("prior_end"),
        }
        return frame, meta

    if token == "concentration":
        conc = _concentration_payload_from_frame(base_frame)
        frame = pd.DataFrame.from_records(conc.get("pareto_rows") or [])
        meta = {
            "dataset": token,
            "total_rows": int(len(frame.index)),
            "start": window_meta.get("start") or start_iso,
            "end": window_meta.get("end") or end_iso,
            "prior_start": window_meta.get("prior_start"),
            "prior_end": window_meta.get("prior_end"),
        }
        return frame, meta

    if token == "risk":
        risk_payload = _risk_payload_from_frame(base_frame, margin_target_pct=SUPPLIERS_MARGIN_TARGET_PCT)
        margin_df = pd.DataFrame.from_records(risk_payload.get("margin_leakage") or [])
        if not margin_df.empty:
            margin_df.insert(0, "risk_type", "margin_leakage")
        data_df = pd.DataFrame.from_records(risk_payload.get("data_risk") or [])
        if not data_df.empty:
            data_df.insert(0, "risk_type", "data_quality")
        frame = pd.concat([margin_df, data_df], ignore_index=True, sort=False) if (not margin_df.empty or not data_df.empty) else pd.DataFrame()
        meta = {
            "dataset": token,
            "total_rows": int(len(frame.index)),
            "start": window_meta.get("start") or start_iso,
            "end": window_meta.get("end") or end_iso,
            "prior_start": window_meta.get("prior_start"),
            "prior_end": window_meta.get("prior_end"),
        }
        return frame, meta

    raise ValueError(f"Unsupported suppliers export dataset: {dataset}")


def build_suppliers_export_metadata_frame(
    filters: Any,
    *,
    dataset: str,
    dataset_version: str,
    meta: Mapping[str, Any],
    args: Any,
) -> pd.DataFrame:
    getter = args.get if hasattr(args, "get") else (lambda _k, _d=None: None)
    rows = [
        {"field": "generated_at_utc", "value": pd.Timestamp.utcnow().isoformat()},
        {"field": "dataset", "value": str(dataset)},
        {"field": "dataset_version", "value": str(dataset_version or "")},
        {"field": "window_start", "value": str(meta.get("start") or "")},
        {"field": "window_end", "value": str(meta.get("end") or "")},
        {"field": "prior_window_start", "value": str(meta.get("prior_start") or "")},
        {"field": "prior_window_end", "value": str(meta.get("prior_end") or "")},
        {"field": "filters_json", "value": filters_service.canonical_json(filters)},
        {"field": "search", "value": str(meta.get("search") or getter("search") or "")},
        {"field": "quick_filter", "value": str(meta.get("quick_filter") or getter("quick_filter") or "all")},
        {"field": "segments", "value": ",".join(meta.get("segments") or _parse_segment_filters(args))},
        {"field": "sort_by", "value": str(meta.get("sort_by") or getter("sort") or "")},
        {"field": "sort_dir", "value": str(meta.get("sort_dir") or getter("sort_dir") or "")},
        {"field": "total_rows", "value": str(meta.get("total_rows") or 0)},
    ]
    return pd.DataFrame(rows)


def _scoped_supplier_cte(scoped_cte: str) -> str:
    return f"""
        {scoped_cte},
        scoped_supplier AS (
            SELECT * FROM scoped WHERE supplier_id = ?
        )
    """


def _drilldown_summary_sql(scoped_supplier_cte: str) -> str:
    return f"""
        WITH
        {scoped_supplier_cte},
        monthly_rollup AS (
            SELECT
                date_trunc('month', order_date) AS month_start,
                SUM(revenue) AS revenue,
                SUM(cost) AS cost_sum,
                SUM(CASE WHEN cost IS NULL THEN 0 ELSE 1 END) AS cost_count,
                SUM(units) AS units,
                SUM(weight_lb) AS weight_lb,
                COUNT(DISTINCT CASE WHEN order_id IS NOT NULL AND order_id <> '' THEN order_id END) AS orders
            FROM scoped_supplier
            GROUP BY 1
        ),
        monthly_last24 AS (
            SELECT * FROM monthly_rollup ORDER BY month_start DESC LIMIT 24
        ),
        monthly_sorted AS (
            SELECT
                strftime('%Y-%m', month_start) AS month,
                revenue,
                CASE WHEN cost_count > 0 THEN cost_sum ELSE NULL END AS cost,
                CASE WHEN cost_count > 0 THEN revenue - cost_sum ELSE NULL END AS profit,
                CASE WHEN revenue > 0 AND cost_count > 0 THEN (revenue - cost_sum) / revenue * 100 ELSE NULL END AS margin_pct,
                units,
                weight_lb,
                orders,
                month_start
            FROM monthly_last24
            ORDER BY month_start
        )
        SELECT
            MIN(supplier_name) AS supplier_name,
            SUM(revenue) AS revenue,
            CASE WHEN SUM(CASE WHEN cost IS NULL THEN 0 ELSE 1 END) > 0 THEN SUM(cost) ELSE NULL END AS cost,
            CASE
                WHEN SUM(CASE WHEN cost IS NULL THEN 0 ELSE 1 END) > 0 THEN SUM(revenue) - SUM(cost)
                ELSE NULL
            END AS profit,
            CASE
                WHEN SUM(revenue) > 0 AND SUM(CASE WHEN cost IS NULL THEN 0 ELSE 1 END) > 0 THEN (SUM(revenue) - SUM(cost)) / SUM(revenue) * 100
                ELSE NULL
            END AS margin_pct,
            CASE
                WHEN SUM(CASE WHEN cost IS NULL THEN 0 ELSE 1 END) > 0 AND SUM(cost) > 0 THEN (SUM(revenue) - SUM(cost)) / SUM(cost) * 100
                ELSE NULL
            END AS roi_pct,
            SUM(units) AS units,
            SUM(weight_lb) AS weight_lb,
            COUNT(DISTINCT CASE WHEN order_id IS NOT NULL AND order_id <> '' THEN order_id END) AS orders,
            COUNT(DISTINCT CASE WHEN product_id IS NOT NULL AND product_id <> '' THEN product_id END) AS products,
            COUNT(DISTINCT CASE WHEN customer_id IS NOT NULL AND customer_id <> '' THEN customer_id END) AS customers,
            MAX(order_date) AS last_sold,
            (SELECT list(struct_pack(
                month:=month,
                revenue:=revenue,
                cost:=cost,
                profit:=profit,
                margin_pct:=margin_pct,
                units:=units,
                weight_lb:=weight_lb,
                orders:=orders
            )) FROM monthly_sorted) AS monthly
        FROM scoped_supplier
    """


def _drilldown_products_sql(scoped_supplier_cte: str, top_n: int) -> str:
    return f"""
        WITH
        {scoped_supplier_cte},
        prod_rollup AS (
            SELECT
                product_id,
                product_name,
                SUM(revenue) AS revenue,
                SUM(cost) AS cost_sum,
                SUM(CASE WHEN cost IS NULL THEN 0 ELSE 1 END) AS cost_count,
                SUM(units) AS units,
                SUM(weight_lb) AS weight_lb,
                COUNT(DISTINCT CASE WHEN order_id IS NOT NULL AND order_id <> '' THEN order_id END) AS orders,
                COUNT(DISTINCT CASE WHEN customer_id IS NOT NULL AND customer_id <> '' THEN customer_id END) AS customers
            FROM scoped_supplier
            WHERE product_id IS NOT NULL AND product_id <> ''
            GROUP BY 1,2
        ),
        totals AS (
            SELECT SUM(revenue) AS total_revenue FROM prod_rollup
        ),
        enriched AS (
            SELECT
                product_id,
                product_name,
                revenue,
                CASE WHEN cost_count > 0 THEN cost_sum ELSE NULL END AS cost,
                CASE WHEN cost_count > 0 THEN revenue - cost_sum ELSE NULL END AS profit,
                CASE WHEN revenue > 0 AND cost_count > 0 THEN (revenue - cost_sum) / revenue * 100 ELSE NULL END AS margin_pct,
                units,
                weight_lb,
                orders,
                customers,
                CASE WHEN units > 0 THEN revenue / NULLIF(units, 0) ELSE NULL END AS avg_sale_price,
                CASE WHEN cost_count > 0 AND units > 0 THEN cost_sum / NULLIF(units, 0) ELSE NULL END AS avg_cost_per_unit
            FROM prod_rollup
        ),
        ranked AS (
            SELECT * FROM enriched ORDER BY revenue DESC, product_name LIMIT {top_n if top_n > 0 else TOP_N_MAX}
        ),
        conc AS (
            SELECT
                CASE
                    WHEN t.total_revenue > 0 THEN (
                        SELECT SUM(POWER(pr.revenue / t.total_revenue, 2)) * 10000
                        FROM prod_rollup pr
                    )
                    ELSE NULL
                END AS hhi,
                CASE
                    WHEN t.total_revenue > 0 THEN (
                        SELECT SUM(revenue) / t.total_revenue * 100
                        FROM (SELECT revenue FROM prod_rollup ORDER BY revenue DESC LIMIT 1)
                    )
                    ELSE NULL
                END AS top1_share,
                CASE
                    WHEN t.total_revenue > 0 THEN (
                        SELECT SUM(revenue) / t.total_revenue * 100
                        FROM (SELECT revenue FROM prod_rollup ORDER BY revenue DESC LIMIT 5)
                    )
                    ELSE NULL
                END AS top5_share
            FROM totals t
        )
        SELECT
            (SELECT list(struct_pack(
                product_id:=product_id,
                product_name:=product_name,
                revenue:=revenue,
                cost:=cost,
                profit:=profit,
                margin_pct:=margin_pct,
                units:=units,
                weight_lb:=weight_lb,
                orders:=orders,
                customers:=customers,
                avg_sale_price:=avg_sale_price,
                avg_cost_per_unit:=avg_cost_per_unit
            )) FROM ranked) AS top_products,
            (SELECT list(
                CASE WHEN units > 0 THEN revenue / NULLIF(units, 0) ELSE NULL END
            ) FROM scoped_supplier WHERE units > 0) AS unit_prices,
            (SELECT
                struct_pack(
                    p10:=quantile_cont(CASE WHEN units > 0 THEN revenue / NULLIF(units, 0) ELSE NULL END, 0.10),
                    p50:=quantile_cont(CASE WHEN units > 0 THEN revenue / NULLIF(units, 0) ELSE NULL END, 0.50),
                    p90:=quantile_cont(CASE WHEN units > 0 THEN revenue / NULLIF(units, 0) ELSE NULL END, 0.90)
                )
             FROM scoped_supplier) AS unit_price_stats,
            (SELECT
                struct_pack(
                    p10:=quantile_cont(CASE WHEN revenue > 0 AND cost IS NOT NULL THEN (revenue - cost) / revenue * 100 ELSE NULL END, 0.10),
                    p50:=quantile_cont(CASE WHEN revenue > 0 AND cost IS NOT NULL THEN (revenue - cost) / revenue * 100 ELSE NULL END, 0.50),
                    p90:=quantile_cont(CASE WHEN revenue > 0 AND cost IS NOT NULL THEN (revenue - cost) / revenue * 100 ELSE NULL END, 0.90)
                )
             FROM scoped_supplier) AS margin_stats,
            (SELECT struct_pack(hhi:=hhi, top1_share:=top1_share, top5_share:=top5_share) FROM conc) AS concentration
    """


def _drilldown_customers_sql(scoped_supplier_cte: str, top_n: int) -> str:
    return f"""
        WITH
        {scoped_supplier_cte},
        cust_rollup AS (
            SELECT
                customer_id,
                customer_name,
                SUM(revenue) AS revenue,
                SUM(cost) AS cost_sum,
                SUM(CASE WHEN cost IS NULL THEN 0 ELSE 1 END) AS cost_count,
                COUNT(DISTINCT CASE WHEN order_id IS NOT NULL AND order_id <> '' THEN order_id END) AS orders,
                COUNT(DISTINCT CASE WHEN product_id IS NOT NULL AND product_id <> '' THEN product_id END) AS products
            FROM scoped_supplier
            WHERE customer_id IS NOT NULL AND customer_id <> ''
            GROUP BY 1,2
        ),
        ranked AS (
            SELECT * FROM cust_rollup ORDER BY revenue DESC, customer_name LIMIT {top_n if top_n > 0 else TOP_N_MAX}
        ),
        totals AS (
            SELECT SUM(revenue) AS total_revenue FROM cust_rollup
        ),
        conc AS (
            SELECT
                CASE
                    WHEN t.total_revenue > 0 THEN (
                        SELECT SUM(POWER(cr.revenue / t.total_revenue, 2)) * 10000
                        FROM cust_rollup cr
                    )
                    ELSE NULL
                END AS hhi,
                CASE
                    WHEN t.total_revenue > 0 THEN (
                        SELECT SUM(revenue) / t.total_revenue * 100
                        FROM (SELECT revenue FROM cust_rollup ORDER BY revenue DESC LIMIT 1)
                    )
                    ELSE NULL
                END AS top1_share,
                CASE
                    WHEN t.total_revenue > 0 THEN (
                        SELECT SUM(revenue) / t.total_revenue * 100
                        FROM (SELECT revenue FROM cust_rollup ORDER BY revenue DESC LIMIT 5)
                    )
                    ELSE NULL
                END AS top5_share
            FROM totals t
        )
        SELECT
            (SELECT list(struct_pack(
                customer_id:=customer_id,
                customer_name:=customer_name,
                revenue:=revenue,
                cost:=CASE WHEN cost_count > 0 THEN cost_sum ELSE NULL END,
                profit:=CASE WHEN cost_count > 0 THEN revenue - cost_sum ELSE NULL END,
                margin_pct:=CASE WHEN revenue > 0 AND cost_count > 0 THEN (revenue - cost_sum) / revenue * 100 ELSE NULL END,
                orders:=orders,
                products:=products
            )) FROM ranked) AS top_customers,
            (SELECT struct_pack(hhi:=hhi, top1_share:=top1_share, top5_share:=top5_share) FROM conc) AS concentration
    """


def _drilldown_detail_rows_sql(scoped_supplier_cte: str) -> str:
    return f"""
        WITH
        {scoped_supplier_cte}
        SELECT
            CAST(order_date AS DATE) AS order_date,
            strftime('%Y-%m', date_trunc('month', order_date)) AS month,
            supplier_id,
            supplier_name,
            order_id,
            product_id,
            product_name,
            customer_id,
            customer_name,
            region,
            shipping_method,
            sales_rep,
            revenue,
            cost,
            units,
            weight_lb,
            CASE WHEN units > 0 THEN revenue / NULLIF(units, 0) ELSE NULL END AS unit_price,
            CASE WHEN weight_lb > 0 THEN revenue / NULLIF(weight_lb, 0) ELSE NULL END AS asp_lb,
            CASE WHEN revenue > 0 AND cost IS NOT NULL THEN (revenue - cost) / revenue * 100 ELSE NULL END AS margin_pct
        FROM scoped_supplier
        WHERE order_date IS NOT NULL
        ORDER BY order_date ASC
    """


def _series_quantile(values: pd.Series, q: float) -> float | None:
    if values is None or values.empty:
        return None
    s = pd.to_numeric(values, errors="coerce").dropna()
    if s.empty:
        return None
    try:
        return float(s.quantile(q))
    except Exception:
        return None


def _clamp(value: float | None, lo: float = 0.0, hi: float = 100.0) -> float | None:
    if value is None:
        return None
    try:
        num = float(value)
    except Exception:
        return None
    if num < lo:
        return lo
    if num > hi:
        return hi
    return num


def _hhi_and_shares(frame: pd.DataFrame, value_col: str) -> Dict[str, Any]:
    if frame is None or frame.empty or value_col not in frame.columns:
        return {"hhi": None, "top1_share": None, "top5_share": None, "top10_share": None}
    vals = pd.to_numeric(frame[value_col], errors="coerce").fillna(0.0)
    vals = vals[vals > 0]
    if vals.empty:
        return {"hhi": None, "top1_share": None, "top5_share": None, "top10_share": None}
    vals = vals.sort_values(ascending=False).reset_index(drop=True)
    total = float(vals.sum())
    if total <= 0:
        return {"hhi": None, "top1_share": None, "top5_share": None, "top10_share": None}
    shares = vals / total
    return {
        "hhi": float((shares.pow(2).sum()) * 10000.0),
        "top1_share": float(shares.head(1).sum() * 100.0),
        "top5_share": float(shares.head(5).sum() * 100.0),
        "top10_share": float(shares.head(10).sum() * 100.0),
    }


def _health_label(score: float | None) -> str:
    if score is None:
        return "Watch"
    if score >= 70:
        return "Strong"
    if score >= 45:
        return "Watch"
    return "Risk"


def _month_labels(series: pd.Series) -> pd.Series:
    dt = pd.to_datetime(series, errors="coerce")
    return dt.dt.to_period("M").astype("string")


def _product_display_fields(product_id: Any, product_name: Any) -> Dict[str, str]:
    full_label = presentation.format_product_label(product_id, product_name)
    return {
        "display_name": full_label,
        "display_name_short": presentation.compact_product_label(product_id, product_name, max_length=56),
        "display_name_axis": presentation.compact_product_label(product_id, product_name, max_length=34),
    }


def _rolling(values: Sequence[float], window_size: int = 3) -> list[float | None]:
    out: list[float | None] = []
    if not values:
        return out
    s = pd.Series(list(values), dtype="float64")
    roll = s.rolling(window=window_size, min_periods=1).mean()
    for val in roll.tolist():
        if pd.isna(val):
            out.append(None)
        else:
            out.append(float(val))
    return out


def _supplier_drilldown_v2_payload(
    *,
    supplier_id: str,
    supplier_name: str,
    detail_df: pd.DataFrame,
    kpis: Mapping[str, Any],
    top_n: int,
    start_iso: str | None,
    end_iso: str | None,
    prior_start_iso: str | None,
    prior_end_iso: str | None,
) -> Dict[str, Any]:
    empty_payload = {
        "window": {
            "start": start_iso,
            "end": end_iso,
            "prior_start": prior_start_iso,
            "prior_end": prior_end_iso,
        },
        "scorecard": {
            "supplier_id": supplier_id,
            "supplier_name": supplier_name,
            "total_revenue": _clean_float(kpis.get("revenue")),
            "total_profit": _clean_optional_float(kpis.get("profit")),
            "gross_margin_pct": _clean_optional_float(kpis.get("margin_pct")),
            "orders": _clean_int(kpis.get("orders")),
            "units": _clean_float(kpis.get("units")),
            "weight_lb": _clean_float(kpis.get("weight_lb")),
            "active_skus": _clean_int(kpis.get("products")),
            "active_customers": _clean_int(kpis.get("customers")),
            "asp_lb": None,
            "asp_lb_delta_pct": None,
            "last_sold": None,
            "cost_coverage_pct": None,
            "revenue_delta_mom": None,
            "revenue_delta_mom_pct": None,
            "margin_volatility": None,
            "customer_hhi": None,
            "sku_hhi": None,
            "customer_top1_share": None,
            "customer_top5_share": None,
            "sku_top1_share": None,
            "sku_top5_share": None,
            "health_score": None,
            "health_label": "Watch",
            "health_formula": "Weighted score: margin 25%, stability 20%, growth 20%, concentration 20%, coverage 15%.",
            "cost_missing_rows": 0,
            "rows_total": 0,
            "no_data": True,
        },
        "trend": {"labels": [], "revenue": [], "profit": [], "margin_pct": [], "orders": [], "rolling_revenue_3m": [], "rolling_profit_3m": [], "rolling_margin_3m": []},
        "mix": {
            "top_products_revenue": [],
            "top_products_profit": [],
            "top_customers": [],
            "customer_concentration": {"hhi": None, "top1_share": None, "top5_share": None, "top10_share": None},
            "product_concentration": {"hhi": None, "top1_share": None, "top5_share": None, "top10_share": None, "skus_for_80_pct": None},
        },
        "pricing": {
            "asp_lb_stats": {"p10": None, "p50": None, "p90": None},
            "margin_stats": {"p10": None, "p50": None, "p90": None},
            "asp_lb_samples": [],
            "margin_samples": [],
            "guardrails": {"high_outliers": 0, "low_outliers": 0},
            "price_velocity": [],
            "elasticity": {"correlation": None, "slope": None, "method": "indicative", "insufficient_variation": True},
            "outliers": [],
        },
        "customers": {
            "top_rows": [],
            "decliners": [],
            "summary": {
                "customer_count": 0,
                "decliner_count": 0,
                "repeat_customer_revenue_share_pct": None,
                "new_customer_revenue_share_pct": None,
                "returning_customer_revenue_share_pct": None,
            },
        },
        "products_table": {"rows": [], "total_rows": 0},
        "opportunities": {"margin_at_risk": [], "pricing_fixes": [], "promote_candidates": [], "data_quality_fixes": []},
        "playbook": {"goal": "Stabilize and grow supplier contribution", "actions": []},
    }

    if detail_df is None or detail_df.empty:
        return empty_payload

    df = detail_df.copy()
    df["order_date"] = pd.to_datetime(df.get("order_date"), errors="coerce")
    df = df[df["order_date"].notna()].copy()
    if df.empty:
        return empty_payload
    df["month"] = _month_labels(df["order_date"])
    df["revenue"] = pd.to_numeric(df.get("revenue"), errors="coerce").fillna(0.0)
    df["cost"] = pd.to_numeric(df.get("cost"), errors="coerce")
    df["units"] = pd.to_numeric(df.get("units"), errors="coerce").fillna(0.0)
    df["weight_lb"] = pd.to_numeric(df.get("weight_lb"), errors="coerce").fillna(0.0)
    df["unit_price"] = pd.to_numeric(df.get("unit_price"), errors="coerce")
    df["asp_lb"] = pd.to_numeric(df.get("asp_lb"), errors="coerce")
    df["margin_pct"] = pd.to_numeric(df.get("margin_pct"), errors="coerce")
    df["profit"] = (df["revenue"] - df["cost"]).where(df["cost"].notna())

    curr_start = pd.to_datetime(start_iso, errors="coerce")
    curr_end = pd.to_datetime(end_iso, errors="coerce")
    prior_start = pd.to_datetime(prior_start_iso, errors="coerce")
    prior_end = pd.to_datetime(prior_end_iso, errors="coerce")
    if pd.isna(curr_start):
        curr_start = df["order_date"].min()
    if pd.isna(curr_end):
        curr_end = df["order_date"].max()
    curr_mask = (df["order_date"] >= curr_start) & (df["order_date"] <= curr_end)
    prior_mask = (df["order_date"] >= prior_start) & (df["order_date"] <= prior_end) if pd.notna(prior_start) and pd.notna(prior_end) else pd.Series(False, index=df.index)

    curr = df[curr_mask].copy()
    prior = df[prior_mask].copy()
    if curr.empty:
        return empty_payload

    month_rollup = (
        curr.groupby("month", dropna=False)
        .agg(
            revenue=("revenue", "sum"),
            profit=("profit", "sum"),
            orders=("order_id", lambda s: s.astype("string").replace("", pd.NA).dropna().nunique()),
            cost_known=("cost", lambda s: s.notna().sum()),
            cost_sum=("cost", "sum"),
        )
        .reset_index()
        .sort_values("month")
    )
    month_rollup["margin_pct"] = ((month_rollup["profit"] / month_rollup["revenue"]) * 100.0).where(month_rollup["revenue"] > 0)
    trend_labels = [str(v) for v in month_rollup["month"].tolist() if str(v)]
    trend_revenue = [_clean_float(v) for v in month_rollup["revenue"].tolist()]
    trend_profit = [_clean_optional_float(v) for v in month_rollup["profit"].tolist()]
    trend_margin = [_clean_optional_float(v) for v in month_rollup["margin_pct"].tolist()]
    trend_orders = [_clean_int(v) for v in month_rollup["orders"].tolist()]

    mom_delta = None
    mom_delta_pct = None
    if len(trend_revenue) >= 2:
        mom_delta = trend_revenue[-1] - trend_revenue[-2]
        mom_delta_pct = (mom_delta / trend_revenue[-2] * 100.0) if trend_revenue[-2] > 0 else None

    product_cols = ["product_id", "product_name"]
    product_rollup = (
        curr.groupby(product_cols, dropna=False)
        .agg(
            revenue=("revenue", "sum"),
            cost_sum=("cost", "sum"),
            cost_known_rows=("cost", lambda s: s.notna().sum()),
            orders=("order_id", lambda s: s.astype("string").replace("", pd.NA).dropna().nunique()),
            units=("units", "sum"),
            weight_lb=("weight_lb", "sum"),
            customers=("customer_id", lambda s: s.astype("string").replace("", pd.NA).dropna().nunique()),
            last_order=("order_date", "max"),
        )
        .reset_index()
    )
    prior_product = (
        prior.groupby("product_id", dropna=False)
        .agg(revenue_prior=("revenue", "sum"), units_prior=("units", "sum"), weight_prior=("weight_lb", "sum"))
        .reset_index()
    )
    if not product_rollup.empty:
        product_rollup = product_rollup.merge(prior_product, on="product_id", how="left")
    else:
        product_rollup["revenue_prior"] = pd.Series(dtype="float64")
        product_rollup["units_prior"] = pd.Series(dtype="float64")
        product_rollup["weight_prior"] = pd.Series(dtype="float64")
    product_rollup["revenue_prior"] = pd.to_numeric(product_rollup.get("revenue_prior"), errors="coerce").fillna(0.0)
    product_rollup["units_prior"] = pd.to_numeric(product_rollup.get("units_prior"), errors="coerce").fillna(0.0)
    product_rollup["weight_prior"] = pd.to_numeric(product_rollup.get("weight_prior"), errors="coerce").fillna(0.0)
    product_rollup["cost"] = product_rollup["cost_sum"].where(product_rollup["cost_known_rows"] > 0)
    product_rollup["profit"] = (product_rollup["revenue"] - product_rollup["cost"]).where(product_rollup["cost"].notna())
    product_rollup["margin_pct"] = ((product_rollup["profit"] / product_rollup["revenue"]) * 100.0).where(product_rollup["revenue"] > 0)
    product_rollup["asp_lb"] = (product_rollup["revenue"] / product_rollup["weight_lb"]).where(product_rollup["weight_lb"] > 0)
    product_rollup["asp_lb_prior"] = (product_rollup["revenue_prior"] / product_rollup["weight_prior"]).where(product_rollup["weight_prior"] > 0)
    product_rollup["asp_lb_delta_pct"] = (
        (product_rollup["asp_lb"] - product_rollup["asp_lb_prior"]) / product_rollup["asp_lb_prior"] * 100.0
    ).where(product_rollup["asp_lb_prior"] > 0)
    product_rollup["delta_revenue"] = product_rollup["revenue"] - product_rollup["revenue_prior"]
    total_product_revenue = float(product_rollup["revenue"].sum()) if not product_rollup.empty else 0.0
    if total_product_revenue > 0:
        product_rollup["revenue_share_pct"] = product_rollup["revenue"] / total_product_revenue * 100.0
    else:
        product_rollup["revenue_share_pct"] = pd.Series([None] * len(product_rollup), index=product_rollup.index, dtype="float64")
    product_rollup["last_sold"] = pd.to_datetime(product_rollup["last_order"], errors="coerce").dt.date.astype("string")

    customer_rollup = (
        curr.groupby(["customer_id", "customer_name"], dropna=False)
        .agg(
            revenue=("revenue", "sum"),
            cost_sum=("cost", "sum"),
            cost_known_rows=("cost", lambda s: s.notna().sum()),
            orders=("order_id", lambda s: s.astype("string").replace("", pd.NA).dropna().nunique()),
            units=("units", "sum"),
            last_order=("order_date", "max"),
        )
        .reset_index()
    )
    prior_customer = (
        prior.groupby("customer_id", dropna=False)
        .agg(revenue_prior=("revenue", "sum"))
        .reset_index()
    )
    if not customer_rollup.empty:
        customer_rollup = customer_rollup.merge(prior_customer, on="customer_id", how="left")
    else:
        customer_rollup["revenue_prior"] = pd.Series(dtype="float64")
    customer_rollup["revenue_prior"] = pd.to_numeric(customer_rollup.get("revenue_prior"), errors="coerce").fillna(0.0)
    customer_rollup["cost"] = customer_rollup["cost_sum"].where(customer_rollup["cost_known_rows"] > 0)
    customer_rollup["profit"] = (customer_rollup["revenue"] - customer_rollup["cost"]).where(customer_rollup["cost"].notna())
    customer_rollup["margin_pct"] = ((customer_rollup["profit"] / customer_rollup["revenue"]) * 100.0).where(customer_rollup["revenue"] > 0)
    customer_rollup["delta_revenue"] = customer_rollup["revenue"] - customer_rollup["revenue_prior"]
    customer_rollup["last_order"] = pd.to_datetime(customer_rollup["last_order"], errors="coerce")
    customer_rollup["last_order_date"] = customer_rollup["last_order"].dt.date.astype("string")

    customer_conc = _hhi_and_shares(customer_rollup, "revenue")
    product_conc = _hhi_and_shares(product_rollup, "revenue")
    skus_for_80 = None
    if total_product_revenue > 0 and not product_rollup.empty:
        shares = product_rollup.sort_values("revenue", ascending=False)["revenue"] / total_product_revenue * 100.0
        skus_for_80 = int((shares.cumsum() <= 80.0).sum() + 1)
    product_conc["skus_for_80_pct"] = skus_for_80

    asp_lb_samples = curr["asp_lb"].dropna()
    margins = curr["margin_pct"].dropna()
    asp_lb_stats = {
        "p10": _series_quantile(asp_lb_samples, 0.10),
        "p50": _series_quantile(asp_lb_samples, 0.50),
        "p90": _series_quantile(asp_lb_samples, 0.90),
    }
    margin_stats = {
        "p10": _series_quantile(margins, 0.10),
        "p50": _series_quantile(margins, 0.50),
        "p90": _series_quantile(margins, 0.90),
    }
    high_cut = (asp_lb_stats["p90"] * 1.15) if asp_lb_stats["p90"] is not None else None
    low_cut = (asp_lb_stats["p10"] / 1.15) if asp_lb_stats["p10"] not in {None, 0} else None

    peer_median = asp_lb_stats["p50"]
    outliers_rows: list[dict[str, Any]] = []
    high_outliers = 0
    low_outliers = 0
    for _, row in product_rollup.sort_values("revenue", ascending=False).iterrows():
        asp_lb = _clean_optional_float(row.get("asp_lb"))
        if asp_lb is None:
            continue
        is_high = bool(high_cut is not None and asp_lb > high_cut)
        is_low = bool(low_cut is not None and asp_lb < low_cut)
        if not (is_high or is_low):
            continue
        if is_high:
            high_outliers += 1
        if is_low:
            low_outliers += 1
        delta_peer = ((asp_lb - peer_median) / peer_median * 100.0) if peer_median and peer_median > 0 else None
        display = _product_display_fields(row.get("product_id"), row.get("product_name"))
        outliers_rows.append(
            {
                "product_id": row.get("product_id"),
                "product_name": row.get("product_name") or row.get("product_id"),
                "asp_lb": asp_lb,
                "peer_median": _clean_optional_float(peer_median),
                "delta_pct_vs_peer": _clean_optional_float(delta_peer),
                "revenue": _clean_float(row.get("revenue")),
                "margin_pct": _clean_optional_float(row.get("margin_pct")),
                "last_sold": _date_to_iso(row.get("last_sold")),
                "outlier_type": "high" if is_high else "low",
                **display,
            }
        )

    window_days = max(int((curr_end - curr_start).days) + 1 if pd.notna(curr_end) and pd.notna(curr_start) else 30, 1)
    window_months = max(window_days / 30.0, 1.0)
    product_rollup["velocity_units_per_month"] = product_rollup["units"] / window_months
    price_velocity_rows: list[dict[str, Any]] = []
    for _, row in product_rollup.iterrows():
        display = _product_display_fields(row.get("product_id"), row.get("product_name"))
        price_velocity_rows.append(
            {
                "product_id": row.get("product_id"),
                "product_name": row.get("product_name") or row.get("product_id"),
                "asp_lb": _clean_optional_float(row.get("asp_lb")),
                "velocity": _clean_optional_float(row.get("velocity_units_per_month")),
                "revenue_share_pct": _clean_optional_float(row.get("revenue_share_pct")),
                "margin_pct": _clean_optional_float(row.get("margin_pct")),
                **display,
            }
        )

    pv = pd.DataFrame.from_records(price_velocity_rows)
    elasticity = {
        "correlation": None,
        "slope": None,
        "method": "indicative",
        "insufficient_variation": True,
    }
    if not pv.empty:
        pv["asp_lb"] = pd.to_numeric(pv["asp_lb"], errors="coerce")
        pv["velocity"] = pd.to_numeric(pv["velocity"], errors="coerce")
        pv = pv.dropna(subset=["asp_lb", "velocity"])
        if len(pv.index) >= 3 and pv["asp_lb"].nunique() > 1 and pv["velocity"].nunique() > 1:
            corr = pv["asp_lb"].corr(pv["velocity"])
            var_x = float(pv["asp_lb"].var(ddof=0))
            cov_xy = float(((pv["asp_lb"] - pv["asp_lb"].mean()) * (pv["velocity"] - pv["velocity"].mean())).mean())
            slope = (cov_xy / var_x) if var_x > 0 else None
            elasticity = {
                "correlation": _clean_optional_float(corr),
                "slope": _clean_optional_float(slope),
                "method": "linear_proxy",
                "insufficient_variation": False,
            }

    target_margin = SUPPLIERS_MARGIN_TARGET_PCT
    margin_at_risk = product_rollup[
        (pd.to_numeric(product_rollup["revenue"], errors="coerce") > 0)
        & (pd.to_numeric(product_rollup["margin_pct"], errors="coerce") < target_margin)
        & (product_rollup["cost"].notna())
    ].copy()
    margin_at_risk["target_profit"] = margin_at_risk["revenue"] * (target_margin / 100.0)
    margin_at_risk["uplift_to_target"] = (margin_at_risk["target_profit"] - margin_at_risk["profit"]).clip(lower=0.0)
    margin_at_risk = margin_at_risk.sort_values(["uplift_to_target", "revenue"], ascending=[False, False])

    declining_customers = customer_rollup[customer_rollup["delta_revenue"] < 0].copy()
    declining_customers = declining_customers.sort_values("delta_revenue", ascending=True)

    customer_behavior = (
        curr.groupby("customer_id", dropna=False)
        .agg(
            revenue=("revenue", "sum"),
            order_count=("order_id", lambda s: s.astype("string").replace("", pd.NA).dropna().nunique()),
        )
        .reset_index()
    )
    if not customer_behavior.empty:
        customer_behavior = customer_behavior.merge(
            prior_customer.rename(columns={"revenue_prior": "revenue_prior_customer"}),
            on="customer_id",
            how="left",
        )
    customer_behavior["revenue_prior_customer"] = pd.to_numeric(
        customer_behavior.get("revenue_prior_customer"), errors="coerce"
    ).fillna(0.0)
    total_customer_revenue = float(pd.to_numeric(customer_behavior.get("revenue"), errors="coerce").fillna(0.0).sum())
    repeat_revenue = float(
        pd.to_numeric(
            customer_behavior.loc[pd.to_numeric(customer_behavior.get("order_count"), errors="coerce").fillna(0) >= 2, "revenue"],
            errors="coerce",
        ).fillna(0.0).sum()
    ) if not customer_behavior.empty else 0.0
    new_revenue = float(
        pd.to_numeric(
            customer_behavior.loc[pd.to_numeric(customer_behavior.get("revenue_prior_customer"), errors="coerce").fillna(0) <= 0, "revenue"],
            errors="coerce",
        ).fillna(0.0).sum()
    ) if not customer_behavior.empty else 0.0
    repeat_share_pct = (repeat_revenue / total_customer_revenue * 100.0) if total_customer_revenue > 0 else None
    new_share_pct = (new_revenue / total_customer_revenue * 100.0) if total_customer_revenue > 0 else None
    returning_share_pct = (100.0 - new_share_pct) if new_share_pct is not None else None

    product_monthly = (
        curr.groupby(["product_id", "month"], dropna=False)
        .agg(revenue=("revenue", "sum"))
        .reset_index()
    )
    prod_vol_map: dict[str, float] = {}
    if not product_monthly.empty:
        for pid, grp in product_monthly.groupby("product_id"):
            vals = pd.to_numeric(grp["revenue"], errors="coerce").dropna()
            mean = float(vals.mean()) if not vals.empty else 0.0
            std = float(vals.std(ddof=0)) if not vals.empty else 0.0
            cv = (std / mean) if mean > 0 else 0.0
            prod_vol_map[str(pid)] = cv

    products_rows: list[dict[str, Any]] = []
    for _, row in product_rollup.sort_values("revenue", ascending=False).iterrows():
        margin = _clean_optional_float(row.get("margin_pct"))
        tags: list[str] = []
        if _clean_float(row.get("revenue_share_pct")) >= 10.0:
            tags.append("Top SKU")
        if margin is not None and margin < target_margin:
            tags.append("Below target margin")
        pid = str(row.get("product_id") or "")
        if prod_vol_map.get(pid, 0.0) >= 1.0:
            tags.append("High volatility")
        asp_lb = _clean_optional_float(row.get("asp_lb"))
        if high_cut is not None and asp_lb is not None and asp_lb > high_cut:
            tags.append("Price outlier")
        if low_cut is not None and asp_lb is not None and asp_lb < low_cut:
            tags.append("Price outlier")
        display = _product_display_fields(row.get("product_id"), row.get("product_name"))
        products_rows.append(
            {
                "product_id": row.get("product_id"),
                "product_name": row.get("product_name") or row.get("product_id"),
                "customers": _clean_int(row.get("customers")),
                "revenue": _clean_float(row.get("revenue")),
                "profit": _clean_optional_float(row.get("profit")),
                "margin_pct": margin,
                "orders": _clean_int(row.get("orders")),
                "units": _clean_float(row.get("units")),
                "weight_lb": _clean_float(row.get("weight_lb")),
                "asp_lb": asp_lb,
                "asp_lb_delta_pct": _clean_optional_float(row.get("asp_lb_delta_pct")),
                "revenue_share_pct": _clean_optional_float(row.get("revenue_share_pct")),
                "last_sold": _date_to_iso(row.get("last_sold")),
                "delta_revenue": _clean_float(row.get("delta_revenue")),
                "tags": tags,
                **display,
            }
        )

    top_products_revenue = products_rows[: max(15, top_n if top_n > 0 else 15)]
    top_products_profit = sorted(
        [r for r in products_rows if r.get("profit") is not None],
        key=lambda rec: float(rec.get("profit") or 0.0),
        reverse=True,
    )[:15]

    customers_top_rows: list[dict[str, Any]] = []
    for _, row in customer_rollup.sort_values("revenue", ascending=False).iterrows():
        customers_top_rows.append(
            {
                "customer_id": row.get("customer_id"),
                "customer_name": row.get("customer_name") or row.get("customer_id"),
                "revenue": _clean_float(row.get("revenue")),
                "profit": _clean_optional_float(row.get("profit")),
                "margin_pct": _clean_optional_float(row.get("margin_pct")),
                "orders": _clean_int(row.get("orders")),
                "last_order_date": _date_to_iso(row.get("last_order_date")),
                "delta_revenue": _clean_optional_float(row.get("delta_revenue")),
            }
        )

    decline_rows = []
    for _, row in declining_customers.head(15).iterrows():
        decline_rows.append(
            {
                "customer_id": row.get("customer_id"),
                "customer_name": row.get("customer_name") or row.get("customer_id"),
                "revenue_current": _clean_float(row.get("revenue")),
                "revenue_prior": _clean_float(row.get("revenue_prior")),
                "delta_revenue": _clean_float(row.get("delta_revenue")),
                "last_order_date": _date_to_iso(row.get("last_order_date")),
            }
        )

    pricing_fixes = []
    data_quality_fixes = []
    promote_candidates = []
    velocity_median = _series_quantile(product_rollup["velocity_units_per_month"], 0.50)
    for row in products_rows:
        margin = row.get("margin_pct")
        velocity = _clean_optional_float(
            product_rollup.loc[
                pd.Series(product_rollup["product_id"]).astype("string") == str(row.get("product_id")),
                "velocity_units_per_month",
            ].iloc[0]
        ) if not product_rollup.empty else None
        if margin is not None and margin < target_margin and velocity is not None and velocity_median is not None and velocity >= velocity_median:
            pricing_fixes.append(
                {
                    "product_id": row.get("product_id"),
                    "product_name": row.get("product_name"),
                    "revenue": row.get("revenue"),
                    "margin_pct": margin,
                    "velocity": velocity,
                    "suggested_action": "Fix margin",
                    "reason": "High velocity SKU below target margin.",
                    "display_name": row.get("display_name"),
                }
            )
        if "Price outlier" in (row.get("tags") or []):
            pricing_fixes.append(
                {
                    "product_id": row.get("product_id"),
                    "product_name": row.get("product_name"),
                    "revenue": row.get("revenue"),
                    "margin_pct": margin,
                    "velocity": velocity,
                    "suggested_action": "Review price",
                    "reason": "ASP/lb outside guardrail band.",
                    "display_name": row.get("display_name"),
                }
            )
        if margin is not None and margin >= target_margin and velocity is not None and velocity_median is not None and velocity < velocity_median:
            promote_candidates.append(
                {
                    "product_id": row.get("product_id"),
                    "product_name": row.get("product_name"),
                    "revenue": row.get("revenue"),
                    "margin_pct": margin,
                    "velocity": velocity,
                    "suggested_action": "Promote",
                    "reason": "High-margin SKU with lower velocity.",
                    "display_name": row.get("display_name"),
                }
            )
        if row.get("margin_pct") is None:
            data_quality_fixes.append(
                {
                    "product_id": row.get("product_id"),
                    "product_name": row.get("product_name"),
                    "revenue": row.get("revenue"),
                    "suggested_action": "Fix cost mapping",
                    "reason": "Cost missing; margin cannot be computed.",
                    "display_name": row.get("display_name"),
                }
            )

    margin_pct = _clean_optional_float(kpis.get("margin_pct"))
    cost_known_rows = int(curr["cost"].notna().sum())
    rows_total = int(len(curr.index))
    cost_coverage_pct = (cost_known_rows / rows_total * 100.0) if rows_total > 0 else None
    margin_volatility = _series_quantile(month_rollup["margin_pct"].dropna().diff().abs(), 0.50)
    if margin_volatility is None:
        margin_volatility = float(pd.to_numeric(month_rollup["margin_pct"], errors="coerce").std(ddof=0)) if len(month_rollup.index) > 1 else None

    asp_lb = (float(curr["revenue"].sum()) / float(curr["weight_lb"].sum())) if float(curr["weight_lb"].sum()) > 0 else None
    asp_lb_prior = (
        float(prior["revenue"].sum()) / float(prior["weight_lb"].sum())
        if not prior.empty and float(prior["weight_lb"].sum()) > 0
        else None
    )
    asp_lb_delta_pct = (
        ((asp_lb - asp_lb_prior) / asp_lb_prior * 100.0)
        if asp_lb is not None and asp_lb_prior and asp_lb_prior > 0
        else None
    )

    growth_component = _clamp(50.0 + (mom_delta_pct or 0.0) * 2.0)
    margin_component = _clamp((margin_pct or 0.0) / 35.0 * 100.0)
    stability_component = _clamp(100.0 - ((margin_volatility or 0.0) * 3.0))
    hhi_vals = [v for v in [customer_conc.get("hhi"), product_conc.get("hhi")] if v is not None]
    hhi_avg = float(sum(hhi_vals) / len(hhi_vals)) if hhi_vals else 1800.0
    concentration_component = _clamp(100.0 - max(hhi_avg - 1200.0, 0.0) / 30.0)
    coverage_component = _clamp(cost_coverage_pct if cost_coverage_pct is not None else 0.0)
    health_score = _clamp(
        (0.25 * (margin_component or 0.0))
        + (0.20 * (stability_component or 0.0))
        + (0.20 * (growth_component or 0.0))
        + (0.20 * (concentration_component or 0.0))
        + (0.15 * (coverage_component or 0.0))
    )
    health_label = _health_label(health_score)

    delta_revenue_total = _clean_float(curr["revenue"].sum()) - _clean_float(prior["revenue"].sum())
    delta_revenue_total_pct = (delta_revenue_total / _clean_float(prior["revenue"].sum()) * 100.0) if _clean_float(prior["revenue"].sum()) > 0 else None

    lifecycle = "Stable"
    if _clean_float(prior["revenue"].sum()) <= 0 and _clean_float(curr["revenue"].sum()) > 0:
        lifecycle = "New"
    elif delta_revenue_total_pct is not None and delta_revenue_total_pct >= 20.0:
        lifecycle = "Growth"
    elif delta_revenue_total_pct is not None and delta_revenue_total_pct <= -20.0:
        lifecycle = "Decline"

    actions = [
        "Focus pricing review on high-velocity low-margin SKUs.",
        "Prioritize top customer decliners for recovery outreach.",
        "Close cost gaps to improve margin reliability.",
    ]

    return {
        "window": {
            "start": start_iso,
            "end": end_iso,
            "prior_start": prior_start_iso,
            "prior_end": prior_end_iso,
        },
        "scorecard": {
            "supplier_id": supplier_id,
            "supplier_name": supplier_name,
            "total_revenue": _clean_float(curr["revenue"].sum()),
            "total_profit": _clean_optional_float(curr["profit"].sum()) if curr["profit"].notna().any() else None,
            "gross_margin_pct": margin_pct,
            "orders": _clean_int(curr["order_id"].astype("string").replace("", pd.NA).dropna().nunique()),
            "units": _clean_float(curr["units"].sum()),
            "weight_lb": _clean_float(curr["weight_lb"].sum()),
            "active_skus": _clean_int(curr["product_id"].astype("string").replace("", pd.NA).dropna().nunique()),
            "active_customers": _clean_int(curr["customer_id"].astype("string").replace("", pd.NA).dropna().nunique()),
            "asp_lb": _clean_optional_float(asp_lb),
            "asp_lb_delta_pct": _clean_optional_float(asp_lb_delta_pct),
            "last_sold": _date_to_iso(curr["order_date"].max()),
            "cost_coverage_pct": _clean_optional_float(cost_coverage_pct),
            "revenue_delta_mom": _clean_optional_float(mom_delta),
            "revenue_delta_mom_pct": _clean_optional_float(mom_delta_pct),
            "margin_volatility": _clean_optional_float(margin_volatility),
            "customer_hhi": _clean_optional_float(customer_conc.get("hhi")),
            "sku_hhi": _clean_optional_float(product_conc.get("hhi")),
            "customer_top1_share": _clean_optional_float(customer_conc.get("top1_share")),
            "customer_top5_share": _clean_optional_float(customer_conc.get("top5_share")),
            "sku_top1_share": _clean_optional_float(product_conc.get("top1_share")),
            "sku_top5_share": _clean_optional_float(product_conc.get("top5_share")),
            "health_score": _clean_optional_float(health_score),
            "health_label": health_label,
            "health_formula": "Weighted score: margin 25%, stability 20%, growth 20%, concentration 20%, coverage 15%.",
            "cost_missing_rows": rows_total - cost_known_rows,
            "rows_total": rows_total,
            "lifecycle": lifecycle,
            "classification": "Concentrated" if (product_conc.get("top5_share") or 0.0) >= 70.0 else "Diversified",
            "revenue_delta_window": _clean_optional_float(delta_revenue_total),
            "revenue_delta_window_pct": _clean_optional_float(delta_revenue_total_pct),
            "supplier_share_pct": None,
            "no_data": False,
        },
        "trend": {
            "labels": trend_labels,
            "revenue": trend_revenue,
            "profit": trend_profit,
            "margin_pct": trend_margin,
            "orders": trend_orders,
            "rolling_revenue_3m": _rolling(trend_revenue, 3),
            "rolling_profit_3m": _rolling([v or 0.0 for v in trend_profit], 3),
            "rolling_margin_3m": _rolling([v or 0.0 for v in trend_margin], 3),
        },
        "mix": {
            "top_products_revenue": top_products_revenue[:15],
            "top_products_profit": top_products_profit,
            "top_customers": customers_top_rows[:15],
            "customer_concentration": customer_conc,
            "product_concentration": product_conc,
        },
        "pricing": {
            "asp_lb_stats": asp_lb_stats,
            "margin_stats": margin_stats,
            "asp_lb_samples": [float(v) for v in asp_lb_samples.dropna().head(5000).tolist()],
            "margin_samples": [float(v) for v in margins.dropna().head(5000).tolist()],
            "guardrails": {"high_outliers": high_outliers, "low_outliers": low_outliers},
            "price_velocity": price_velocity_rows,
            "elasticity": elasticity,
            "outliers": outliers_rows,
        },
        "customers": {
            "top_rows": customers_top_rows,
            "decliners": decline_rows,
            "summary": {
                "customer_count": int(customer_rollup["customer_id"].astype("string").replace("", pd.NA).dropna().nunique()),
                "decliner_count": int(len(decline_rows)),
                "repeat_customer_revenue_share_pct": _clean_optional_float(repeat_share_pct),
                "new_customer_revenue_share_pct": _clean_optional_float(new_share_pct),
                "returning_customer_revenue_share_pct": _clean_optional_float(returning_share_pct),
            },
        },
        "products_table": {
            "rows": products_rows,
            "total_rows": len(products_rows),
        },
        "opportunities": {
            "margin_at_risk": [
                {
                    "product_id": r.get("product_id"),
                    "product_name": r.get("product_name") or r.get("product_id"),
                    "revenue": _clean_float(r.get("revenue")),
                    "profit": _clean_optional_float(r.get("profit")),
                    "margin_pct": _clean_optional_float(r.get("margin_pct")),
                    "target_margin_pct": target_margin,
                    "uplift_to_target": _clean_optional_float(r.get("uplift_to_target")),
                    "last_sold": _date_to_iso(r.get("last_sold")),
                    "asp_lb": _clean_optional_float(r.get("asp_lb")),
                    **_product_display_fields(r.get("product_id"), r.get("product_name")),
                }
                for _, r in margin_at_risk.head(200).iterrows()
            ],
            "pricing_fixes": pricing_fixes[:200],
            "promote_candidates": promote_candidates[:200],
            "data_quality_fixes": data_quality_fixes[:200],
        },
        "playbook": {
            "goal": "Protect margin, reduce concentration risk, and grow stable volume",
            "actions": actions,
        },
    }


def build_suppliers_drilldown(supplier_id: str, filters: Any, scope: Dict[str, Any], args: Any) -> Dict[str, Any]:
    # DEV NOTE (audit summary):
    # - Drilldown data source: canonical fact_store DuckDB `fact` view via `_scoped_cte` + `_scoped_supplier_cte`.
    # - Scope enforcement helper: access_policy.enforce_entity_access(...) in bundle_service before this builder runs;
    #   scoped SQL is applied by fact_store.build_where_clause(..., scope=...).
    # - Caching: `_DRILLDOWN_CACHE` keyed by dataset_version + scope_hash + filters hash + supplier_id + v2 args.
    cols = fact_store.list_columns()
    cols_map = _required_columns(cols)
    missing = []
    if not cols_map.get("date"):
        missing.append("date")
    if not cols_map.get("revenue_candidates"):
        missing.append("revenue")
    if not (cols_map.get("supplier_id_candidates") or cols_map.get("supplier_name_candidates")):
        missing.append("supplier_id/supplier_name")
    if missing:
        return {
            "error": {"message": "Required columns missing for suppliers drilldown: " + ", ".join(missing)},
            "meta": {"cached": False},
        }

    dataset_version = fact_store.cache_buster()
    filter_hash, scope_summary = _filter_hash(filters, scope, dataset_version)
    top_n = _parse_top_n(args, default=25)
    drilldown_v2 = _parse_bool_arg(args, ("supplier_drilldown_v2", "drilldown_v2", "v2"), default=False)

    cache_key = _cache_key(
        "suppliers.drilldown",
        dataset_version,
        scope_summary,
        filter_hash,
        {"supplier_id": str(supplier_id), "top_n": top_n, "drilldown_v2": drilldown_v2},
    )

    def _build_drilldown() -> Dict[str, Any]:
        where_sql, params, start_iso, end_iso = fact_store.build_where_clause(
            filters, cols, scope, apply_default_window=True
        )
        window = _window_bounds(start_iso, end_iso)
        prior_start_iso = window.get("prior_start")
        prior_end_iso = window.get("prior_end")
        scoped_cte = _scoped_cte(cols, cols_map, where_sql)
        scoped_supplier_cte = _scoped_supplier_cte(scoped_cte)
        params_with_supplier = list(params) + [supplier_id]

        summary_sql = _drilldown_summary_sql(scoped_supplier_cte)
        products_sql = _drilldown_products_sql(scoped_supplier_cte, top_n)
        customers_sql = _drilldown_customers_sql(scoped_supplier_cte, top_n)
        detail_sql = None
        detail_params_with_supplier: list[Any] = []
        if drilldown_v2:
            detail_filters = _filters_with_window(filters, prior_start_iso or start_iso, end_iso)
            detail_where_sql, detail_params, _, _ = fact_store.build_where_clause(
                detail_filters, cols, scope, apply_default_window=True
            )
            detail_scoped_cte = _scoped_cte(cols, cols_map, detail_where_sql)
            detail_scoped_supplier_cte = _scoped_supplier_cte(detail_scoped_cte)
            detail_sql = _drilldown_detail_rows_sql(detail_scoped_supplier_cte)
            detail_params_with_supplier = list(detail_params) + [supplier_id]

        summary_df = fact_store.execute_sql_df(summary_sql, params_with_supplier, tag="suppliers.drilldown.summary")
        products_df = fact_store.execute_sql_df(products_sql, params_with_supplier, tag="suppliers.drilldown.products")
        customers_df = fact_store.execute_sql_df(customers_sql, params_with_supplier, tag="suppliers.drilldown.customers")
        detail_df = (
            _execute_sql_df_with_fallback(detail_sql, detail_params_with_supplier, tag="suppliers.drilldown.detail")
            if detail_sql
            else pd.DataFrame()
        )

        summary_row = summary_df.iloc[0].to_dict() if not summary_df.empty else {}
        monthly = _struct_list(summary_row.get("monthly"))
        trend_labels = [str(item.get("month")) for item in monthly if item.get("month") is not None]
        trend_revenue = [_clean_float(item.get("revenue")) for item in monthly]
        trend_cost = [_clean_optional_float(item.get("cost")) for item in monthly]
        trend_profit = [_clean_optional_float(item.get("profit")) for item in monthly]
        trend_margin = [_clean_optional_float(item.get("margin_pct")) for item in monthly]

        products_row = products_df.iloc[0].to_dict() if not products_df.empty else {}
        top_products = _struct_list(products_row.get("top_products"))
        unit_prices = _to_list(products_row.get("unit_prices"))
        unit_price_stats = products_row.get("unit_price_stats") or {}
        margin_stats = products_row.get("margin_stats") or {}
        prod_conc = products_row.get("concentration") or {}

        customers_row = customers_df.iloc[0].to_dict() if not customers_df.empty else {}
        top_customers = _struct_list(customers_row.get("top_customers"))
        cust_conc = customers_row.get("concentration") or {}

        supplier_name = summary_row.get("supplier_name") or str(supplier_id)
        last_sold_iso = _date_to_iso(summary_row.get("last_sold"))
        days_since_last_order = None
        if last_sold_iso:
            try:
                last_dt = date.fromisoformat(last_sold_iso)
                days_since_last_order = (date.today() - last_dt).days
            except Exception:
                days_since_last_order = None

        kpis = {
            "supplier_id": str(supplier_id),
            "supplier_name": supplier_name,
            "revenue": _clean_float(summary_row.get("revenue")),
            "cost": _clean_optional_float(summary_row.get("cost")),
            "profit": _clean_optional_float(summary_row.get("profit")),
            "margin_pct": _clean_optional_float(summary_row.get("margin_pct")),
            "roi_pct": _clean_optional_float(summary_row.get("roi_pct")),
            "orders": _clean_int(summary_row.get("orders")),
            "products": _clean_int(summary_row.get("products")),
            "customers": _clean_int(summary_row.get("customers")),
            "units": _clean_float(summary_row.get("units")),
            "weight_lb": _clean_float(summary_row.get("weight_lb")),
            "last_sold": last_sold_iso,
            "days_since_last_order": days_since_last_order,
            "start": start_iso,
            "end": end_iso,
        }

        product_metrics = [
            {
                "product_id": p.get("product_id"),
                "product_name": p.get("product_name") or p.get("product_id"),
                "revenue": _clean_float(p.get("revenue")),
                "cost": _clean_optional_float(p.get("cost")),
                "profit": _clean_optional_float(p.get("profit")),
                "margin_pct": _clean_optional_float(p.get("margin_pct")),
                "units": _clean_float(p.get("units")),
                "weight_lb": _clean_float(p.get("weight_lb")),
                "orders": _clean_int(p.get("orders")),
                "customers": _clean_int(p.get("customers")),
                "avg_sale_price": _clean_optional_float(p.get("avg_sale_price")),
                "avg_cost_per_unit": _clean_optional_float(p.get("avg_cost_per_unit")),
            }
            for p in top_products
        ]

        top_prod_labels = [str(p.get("product_name") or p.get("product_id")) for p in top_products]
        top_prod_values = [_clean_float(p.get("revenue")) for p in top_products]
        top_cust_labels = [str(c.get("customer_name") or c.get("customer_id")) for c in top_customers]
        top_cust_values = [_clean_float(c.get("revenue")) for c in top_customers]

        payload = {
            "kpis": kpis,
            "trend": {
                "labels": trend_labels,
                "revenue": trend_revenue,
                "cost": trend_cost,
                "profit": trend_profit,
                "margin_pct": trend_margin,
            },
            "charts": {
                "trend": {
                    "labels": trend_labels,
                    "revenue": trend_revenue,
                    "cost": trend_cost,
                    "profit": trend_profit,
                    "margin_pct": trend_margin,
                },
                "top_products": {
                    "labels": top_prod_labels,
                    "values": top_prod_values,
                    "rows": top_products,
                    "concentration": prod_conc or {},
                },
                "top_customers": {
                    "labels": top_cust_labels,
                    "values": top_cust_values,
                    "rows": top_customers,
                    "concentration": cust_conc or {},
                },
                "unit_price": {
                    "values": unit_prices,
                    "stats": unit_price_stats or {},
                },
                "margin_stats": margin_stats or {},
            },
            "table": {
                "rows": product_metrics,
                "page": 1,
                "page_size": len(product_metrics),
                "total": len(product_metrics),
                "total_rows": len(product_metrics),
                "sort_by": "revenue",
                "sort_dir": "desc",
            },
            "meta": {
                "page_id": "supplier_drilldown",
                "entity_id": str(supplier_id),
                "entity_label": supplier_name,
                "top_n": top_n,
                "window_start": start_iso,
                "window_end": end_iso,
                "prior_window_start": prior_start_iso,
                "prior_window_end": prior_end_iso,
            },
        }
        if drilldown_v2:
            supplier_v2 = _supplier_drilldown_v2_payload(
                supplier_id=str(supplier_id),
                supplier_name=str(supplier_name),
                detail_df=detail_df,
                kpis=kpis,
                top_n=top_n,
                start_iso=start_iso,
                end_iso=end_iso,
                prior_start_iso=prior_start_iso,
                prior_end_iso=prior_end_iso,
            )
            payload["supplier_v2"] = supplier_v2
            payload["v2"] = supplier_v2
        return payload

    drilldown_payload, cache_hit = _DRILLDOWN_CACHE.get_or_compute(cache_key, DRILLDOWN_TTL_SECONDS, _build_drilldown)
    drilldown_payload = _clone(drilldown_payload)
    drilldown_payload.setdefault("meta", {})
    drilldown_payload["meta"].setdefault("cache_parts", {})
    drilldown_payload["meta"]["cache_parts"]["drilldown"] = bool(cache_hit)
    return drilldown_payload


def build_supplier_products_frame(
    supplier_id: str,
    filters: Any,
    scope: Dict[str, Any],
    args: Any,
) -> tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Export helper for supplier products.
    Uses the same scoped filters/window as drilldown, but does not apply top-N
    or pagination so exports always include all matching products.
    """
    cols = fact_store.list_columns()
    cols_map = _required_columns(cols)
    missing: list[str] = []
    if not cols_map.get("date"):
        missing.append("date")
    if not cols_map.get("revenue_candidates"):
        missing.append("revenue")
    if not (cols_map.get("supplier_id_candidates") or cols_map.get("supplier_name_candidates")):
        missing.append("supplier_id/supplier_name")
    if not cols_map.get("product_id_candidates"):
        missing.append("product_id")
    if missing:
        return pd.DataFrame(), {
            "supplier_id": str(supplier_id),
            "total_rows": 0,
            "missing_columns": missing,
        }

    where_sql, params, start_iso, end_iso = fact_store.build_where_clause(
        filters, cols, scope, apply_default_window=True
    )
    scoped_cte = _scoped_cte(cols, cols_map, where_sql)
    scoped_supplier_cte = _scoped_supplier_cte(scoped_cte)
    base_params = list(params) + [supplier_id]

    sort_by, sort_dir = _supplier_product_sort_params(args)
    search = _extract_search(args)

    count_sql, count_params = _supplier_products_count_sql(scoped_supplier_cte, search)
    count_df = _execute_sql_df_with_fallback(
        count_sql,
        base_params + count_params,
        tag="suppliers.products_export.count",
    )
    total_rows_raw = count_df.iloc[0].get("total_rows") if not count_df.empty else 0
    total_rows = _clean_int(total_rows_raw, default=0)
    if total_rows > SUPPLIER_PRODUCTS_EXPORT_MAX_ROWS:
        raise SupplierProductsExportLimitError(
            row_count=total_rows,
            max_rows=SUPPLIER_PRODUCTS_EXPORT_MAX_ROWS,
        )

    if total_rows <= 0:
        df = pd.DataFrame(
            columns=[
                "product_id",
                "product_name",
                "revenue",
                "cost",
                "profit",
                "margin_pct",
                "units",
                "weight_lb",
                "orders",
                "customers",
                "avg_sale_price",
                "avg_cost_per_unit",
            ]
        )
    else:
        chunk_size = max(1000, min(SUPPLIER_PRODUCTS_EXPORT_CHUNK_SIZE, MAX_PAGE_SIZE))
        chunks: list[pd.DataFrame] = []
        offset = 0
        while offset < total_rows:
            sql, query_params = _supplier_products_sql(
                scoped_supplier_cte,
                sort_by,
                sort_dir,
                search,
                paginate=True,
                page_size=min(chunk_size, total_rows - offset),
                offset=offset,
            )
            chunk = _execute_sql_df_with_fallback(
                sql,
                base_params + query_params,
                tag="suppliers.products_export.rows",
            )
            if chunk.empty:
                break
            chunks.append(chunk)
            fetched = len(chunk.index)
            if fetched <= 0:
                break
            offset += fetched
        df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()

    if "total_groups" in df.columns:
        df = df.drop(columns=["total_groups"])

    rename_map = {
        "product_id": "Product ID",
        "product_name": "Product",
        "revenue": "Revenue",
        "cost": "Cost",
        "profit": "Profit",
        "margin_pct": "Margin %",
        "units": "Units",
        "weight_lb": "Weight (lb)",
        "orders": "Orders",
        "customers": "Customers",
        "avg_sale_price": "Avg Sale Price",
        "avg_cost_per_unit": "Avg Cost / Unit",
    }
    export_order = [
        "product_id",
        "product_name",
        "revenue",
        "cost",
        "profit",
        "margin_pct",
        "units",
        "weight_lb",
        "orders",
        "customers",
        "avg_sale_price",
        "avg_cost_per_unit",
    ]
    existing_order = [c for c in export_order if c in df.columns]
    if existing_order:
        ordered_data = {col: df[col].tolist() for col in existing_order}
        df = pd.DataFrame(ordered_data)
    else:
        df = pd.DataFrame(columns=export_order)
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    meta = {
        "supplier_id": str(supplier_id),
        "total_rows": int(len(df.index)),
        "sort_by": sort_by,
        "sort_dir": sort_dir.lower(),
        "search": search,
        "start": start_iso,
        "end": end_iso,
    }
    return df, meta


def _mode_text(series: pd.Series) -> str | None:
    if series is None:
        return None
    values = series.astype("string").str.strip().replace({"": pd.NA}).dropna()
    if values.empty:
        return None
    mode_vals = values.mode(dropna=True)
    if not mode_vals.empty:
        return str(mode_vals.iloc[0])
    return str(values.iloc[0])


def build_supplier_products_vs_customers_export_frame(
    supplier_id: str,
    filters: Any,
    scope: Dict[str, Any],
) -> tuple[pd.DataFrame, Dict[str, Any]]:
    output_cols = [
        "SupplierId",
        "SupplierName",
        "SKU",
        "Product",
        "ProductName",
        "CustomerId",
        "CustomerName",
        "Region",
        "Orders",
        "Units",
        "WeightLb",
        "Revenue",
        "Cost",
        "Profit",
        "MarginPct",
        "ASP/lb",
        "FirstOrderDate",
        "LastOrderDate",
        "RevenueShareWithinSupplier",
        "RevenueShareWithinProduct",
        "CustomerRankForProduct",
        "ProductRankWithinSupplier",
        "ShippingMethod",
        "SalesRep",
        "ActiveFilterStart",
        "ActiveFilterEnd",
    ]

    cols = fact_store.list_columns()
    cols_map = _required_columns(cols)
    missing: list[str] = []
    if not cols_map.get("date"):
        missing.append("date")
    if not cols_map.get("revenue_candidates"):
        missing.append("revenue")
    if not (cols_map.get("supplier_id_candidates") or cols_map.get("supplier_name_candidates")):
        missing.append("supplier_id/supplier_name")
    if not cols_map.get("product_id_candidates"):
        missing.append("product_id")
    if not cols_map.get("customer_id_candidates"):
        missing.append("customer_id")
    if missing:
        return pd.DataFrame(columns=output_cols), {
            "dataset": "products_vs_customers",
            "supplier_id": str(supplier_id),
            "total_rows": 0,
            "missing_columns": missing,
            "start": None,
            "end": None,
            "prior_start": None,
            "prior_end": None,
        }

    where_sql, params, start_iso, end_iso = fact_store.build_where_clause(
        filters, cols, scope, apply_default_window=True
    )
    scoped_cte = _scoped_cte(cols, cols_map, where_sql)
    scoped_supplier_cte = _scoped_supplier_cte(scoped_cte)
    detail_sql = _drilldown_detail_rows_sql(scoped_supplier_cte)
    detail_df = _execute_sql_df_with_fallback(
        detail_sql,
        list(params) + [supplier_id],
        tag="suppliers.drilldown.export.products_vs_customers",
    )

    if detail_df is None or detail_df.empty:
        return pd.DataFrame(columns=output_cols), {
            "dataset": "products_vs_customers",
            "supplier_id": str(supplier_id),
            "total_rows": 0,
            "start": start_iso,
            "end": end_iso,
            "prior_start": None,
            "prior_end": None,
        }

    detail = detail_df.copy()
    detail["order_date"] = pd.to_datetime(detail.get("order_date"), errors="coerce")
    detail = detail[detail["order_date"].notna()].copy()
    if detail.empty:
        return pd.DataFrame(columns=output_cols), {
            "dataset": "products_vs_customers",
            "supplier_id": str(supplier_id),
            "total_rows": 0,
            "start": start_iso,
            "end": end_iso,
            "prior_start": None,
            "prior_end": None,
        }

    for col in ("revenue", "cost", "units", "weight_lb"):
        detail[col] = pd.to_numeric(detail.get(col), errors="coerce")
    detail["revenue"] = detail["revenue"].fillna(0.0)
    detail["units"] = detail["units"].fillna(0.0)
    detail["weight_lb"] = detail["weight_lb"].fillna(0.0)

    def _text_col(name: str, default: str = "") -> pd.Series:
        raw = detail.get(name)
        if raw is None:
            return pd.Series([default] * len(detail.index), index=detail.index, dtype="string")
        return raw.astype("string").str.strip().replace({"nan": pd.NA, "None": pd.NA})

    detail["supplier_id"] = _text_col("supplier_id", str(supplier_id)).fillna(str(supplier_id))
    detail["supplier_name"] = _text_col("supplier_name", str(supplier_id)).fillna(str(supplier_id))
    detail["product_id"] = _text_col("product_id").fillna("")
    detail["product_name"] = _text_col("product_name").fillna(detail["product_id"])
    detail["customer_id"] = _text_col("customer_id").fillna("")
    detail["customer_name"] = _text_col("customer_name").fillna(detail["customer_id"])
    detail["region"] = _text_col("region", "Unspecified").fillna("Unspecified")
    detail["shipping_method"] = _text_col("shipping_method").fillna("")
    detail["sales_rep"] = _text_col("sales_rep").fillna("")

    group_cols = [
        "supplier_id",
        "supplier_name",
        "product_id",
        "product_name",
        "customer_id",
        "customer_name",
        "region",
    ]
    grouped = (
        detail.groupby(group_cols, dropna=False)
        .agg(
            Orders=("order_id", lambda s: s.astype("string").replace({"": pd.NA}).dropna().nunique()),
            Units=("units", "sum"),
            WeightLb=("weight_lb", "sum"),
            Revenue=("revenue", "sum"),
            _CostSum=("cost", "sum"),
            _CostRows=("cost", lambda s: s.notna().sum()),
            FirstOrderDate=("order_date", "min"),
            LastOrderDate=("order_date", "max"),
            ShippingMethod=("shipping_method", _mode_text),
            SalesRep=("sales_rep", _mode_text),
        )
        .reset_index()
    )

    grouped["Cost"] = grouped["_CostSum"].where(grouped["_CostRows"] > 0)
    grouped["Profit"] = (grouped["Revenue"] - grouped["Cost"]).where(grouped["Cost"].notna())
    grouped["MarginPct"] = ((grouped["Profit"] / grouped["Revenue"]) * 100.0).where(grouped["Revenue"] > 0)
    grouped["ASP/lb"] = (grouped["Revenue"] / grouped["WeightLb"]).where(grouped["WeightLb"] > 0)
    grouped["Product"] = grouped.apply(
        lambda row: presentation.format_product_label(row.get("product_id"), row.get("product_name")),
        axis=1,
    )

    supplier_revenue = float(pd.to_numeric(grouped["Revenue"], errors="coerce").fillna(0.0).sum())
    if supplier_revenue > 0:
        grouped["RevenueShareWithinSupplier"] = grouped["Revenue"] / supplier_revenue * 100.0
    else:
        grouped["RevenueShareWithinSupplier"] = None

    product_keys = ["product_id", "product_name"]
    product_revenue = grouped.groupby(product_keys, dropna=False)["Revenue"].transform("sum")
    grouped["RevenueShareWithinProduct"] = ((grouped["Revenue"] / product_revenue) * 100.0).where(product_revenue > 0)
    grouped["CustomerRankForProduct"] = (
        grouped.groupby(product_keys, dropna=False)["Revenue"].rank(method="dense", ascending=False).astype("Int64")
    )
    product_rank = (
        grouped.groupby(product_keys, dropna=False)["Revenue"]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
    )
    product_rank["ProductRankWithinSupplier"] = (
        product_rank["Revenue"].rank(method="dense", ascending=False).astype("Int64")
    )
    grouped = grouped.merge(product_rank[product_keys + ["ProductRankWithinSupplier"]], on=product_keys, how="left")

    grouped["FirstOrderDate"] = pd.to_datetime(grouped["FirstOrderDate"], errors="coerce").dt.date.astype("string")
    grouped["LastOrderDate"] = pd.to_datetime(grouped["LastOrderDate"], errors="coerce").dt.date.astype("string")
    grouped["ActiveFilterStart"] = str(start_iso or "")
    grouped["ActiveFilterEnd"] = str(end_iso or "")

    grouped = grouped.rename(
        columns={
            "supplier_id": "SupplierId",
            "supplier_name": "SupplierName",
            "product_id": "SKU",
            "product_name": "ProductName",
            "customer_id": "CustomerId",
            "customer_name": "CustomerName",
            "region": "Region",
        }
    )
    grouped["Orders"] = pd.to_numeric(grouped["Orders"], errors="coerce").fillna(0).astype(int)
    grouped["CustomerRankForProduct"] = pd.to_numeric(grouped["CustomerRankForProduct"], errors="coerce").astype("Int64")
    grouped["ProductRankWithinSupplier"] = pd.to_numeric(grouped["ProductRankWithinSupplier"], errors="coerce").astype("Int64")
    grouped["ShippingMethod"] = grouped["ShippingMethod"].astype("string").fillna("")
    grouped["SalesRep"] = grouped["SalesRep"].astype("string").fillna("")

    for col in output_cols:
        if col not in grouped.columns:
            grouped[col] = None

    frame = grouped[output_cols].sort_values(
        by=["ProductRankWithinSupplier", "CustomerRankForProduct", "Revenue", "CustomerName"],
        ascending=[True, True, False, True],
        na_position="last",
        kind="stable",
    )
    frame = frame.reset_index(drop=True)
    meta = {
        "dataset": "products_vs_customers",
        "supplier_id": str(supplier_id),
        "supplier_name": (
            str(frame["SupplierName"].iloc[0])
            if not frame.empty and "SupplierName" in frame.columns and pd.notna(frame["SupplierName"].iloc[0])
            else None
        ),
        "total_rows": int(len(frame.index)),
        "start": start_iso,
        "end": end_iso,
        "prior_start": None,
        "prior_end": None,
    }
    return frame, meta


def build_supplier_drilldown_export_dataset(
    supplier_id: str,
    filters: Any,
    scope: Dict[str, Any],
    args: Any,
    dataset: str,
) -> tuple[pd.DataFrame, Dict[str, Any]]:
    token = str(dataset or "products").strip().lower()
    aliases = {
        "table": "products",
        "product_table": "products",
        "product": "products",
        "customer": "customers",
        "products_customers": "products_vs_customers",
        "products-vs-customers": "products_vs_customers",
        "product_customer": "products_vs_customers",
        "product_vs_customer": "products_vs_customers",
        "outlier": "pricing_outliers",
        "pricing": "pricing_outliers",
        "margin": "margin_risk",
        "margin_at_risk": "margin_risk",
        "trend": "monthly_series",
        "monthly": "monthly_series",
        "kpis": "summary",
    }
    token = aliases.get(token, token)

    args_payload: Dict[str, Any] = {}
    if hasattr(args, "to_dict"):
        try:
            args_payload = args.to_dict(flat=True)  # type: ignore[assignment]
        except Exception:
            args_payload = {}
    elif isinstance(args, Mapping):
        args_payload = {str(k): v for k, v in args.items()}
    args_payload["supplier_drilldown_v2"] = "1"
    args_payload["drilldown_v2"] = "1"
    args_payload["top_n"] = str(TOP_N_MAX)
    payload = build_suppliers_drilldown(str(supplier_id), filters, scope, args_payload)
    supplier_v2 = payload.get("supplier_v2") or payload.get("v2") or {}
    if not isinstance(supplier_v2, dict):
        supplier_v2 = {}
    window = supplier_v2.get("window") if isinstance(supplier_v2.get("window"), dict) else {}
    score = supplier_v2.get("scorecard") if isinstance(supplier_v2.get("scorecard"), dict) else {}

    if token == "products":
        frame = pd.DataFrame.from_records(((supplier_v2.get("products_table") or {}).get("rows") or []))
    elif token == "products_vs_customers":
        frame, meta = build_supplier_products_vs_customers_export_frame(str(supplier_id), filters, scope)
        return frame, meta
    elif token == "customers":
        frame = pd.DataFrame.from_records(((supplier_v2.get("customers") or {}).get("top_rows") or []))
    elif token == "pricing_outliers":
        frame = pd.DataFrame.from_records(((supplier_v2.get("pricing") or {}).get("outliers") or []))
    elif token == "margin_risk":
        frame = pd.DataFrame.from_records(((supplier_v2.get("opportunities") or {}).get("margin_at_risk") or []))
    elif token == "monthly_series":
        trend = supplier_v2.get("trend") or {}
        frame = pd.DataFrame(
            {
                "month": trend.get("labels") or [],
                "revenue": trend.get("revenue") or [],
                "profit": trend.get("profit") or [],
                "margin_pct": trend.get("margin_pct") or [],
                "orders": trend.get("orders") or [],
            }
        )
    elif token == "summary":
        frame = pd.DataFrame([score]) if score else pd.DataFrame()
    else:
        raise ValueError(f"Unsupported suppliers drilldown export dataset: {dataset}")

    if token == "products":
        rename_map = {
            "product_id": "SKU",
            "display_name": "Product",
            "revenue": "Revenue",
            "profit": "Profit",
            "margin_pct": "MarginPct",
            "orders": "Orders",
            "customers": "Customers",
            "units": "Units",
            "weight_lb": "WeightLb",
            "asp_lb": "ASP/lb",
            "asp_lb_delta_pct": "ASP/lb DeltaPct",
            "revenue_share_pct": "RevenueSharePct",
            "last_sold": "LastSold",
            "tags": "Tags",
        }
        order = [
            "SKU",
            "Product",
            "Revenue",
            "Profit",
            "MarginPct",
            "Orders",
            "Customers",
            "Units",
            "WeightLb",
            "ASP/lb",
            "ASP/lb DeltaPct",
            "RevenueSharePct",
            "LastSold",
            "Tags",
        ]
        if "tags" in frame.columns:
            frame["tags"] = frame["tags"].apply(
                lambda values: " | ".join(str(v) for v in values if str(v).strip()) if isinstance(values, list) else values
            )
        frame = frame.rename(columns={k: v for k, v in rename_map.items() if k in frame.columns})
        existing = [col for col in order if col in frame.columns]
        frame = frame[existing] if existing else frame
    elif token == "customers":
        rename_map = {
            "customer_id": "CustomerId",
            "customer_name": "CustomerName",
            "revenue": "Revenue",
            "profit": "Profit",
            "margin_pct": "MarginPct",
            "orders": "Orders",
            "last_order_date": "LastOrderDate",
            "delta_revenue": "DeltaRevenue",
        }
        frame = frame.rename(columns={k: v for k, v in rename_map.items() if k in frame.columns})
    elif token == "pricing_outliers":
        rename_map = {
            "product_id": "SKU",
            "display_name": "Product",
            "asp_lb": "ASP/lb",
            "peer_median": "PeerMedianASP/lb",
            "delta_pct_vs_peer": "DeltaPctVsPeer",
            "revenue": "Revenue",
            "margin_pct": "MarginPct",
            "last_sold": "LastSold",
            "outlier_type": "OutlierType",
        }
        order = ["SKU", "Product", "ASP/lb", "PeerMedianASP/lb", "DeltaPctVsPeer", "Revenue", "MarginPct", "LastSold", "OutlierType"]
        frame = frame.rename(columns={k: v for k, v in rename_map.items() if k in frame.columns})
        existing = [col for col in order if col in frame.columns]
        frame = frame[existing] if existing else frame
    elif token == "margin_risk":
        rename_map = {
            "product_id": "SKU",
            "display_name": "Product",
            "revenue": "Revenue",
            "profit": "Profit",
            "margin_pct": "MarginPct",
            "target_margin_pct": "TargetMarginPct",
            "uplift_to_target": "UpliftToTarget",
            "asp_lb": "ASP/lb",
            "last_sold": "LastSold",
        }
        order = ["SKU", "Product", "Revenue", "Profit", "MarginPct", "TargetMarginPct", "UpliftToTarget", "ASP/lb", "LastSold"]
        frame = frame.rename(columns={k: v for k, v in rename_map.items() if k in frame.columns})
        existing = [col for col in order if col in frame.columns]
        frame = frame[existing] if existing else frame
    elif token == "monthly_series":
        rename_map = {
            "month": "Month",
            "revenue": "Revenue",
            "profit": "Profit",
            "margin_pct": "MarginPct",
            "orders": "Orders",
        }
        frame = frame.rename(columns={k: v for k, v in rename_map.items() if k in frame.columns})
    elif token == "summary":
        rename_map = {
            "supplier_id": "SupplierId",
            "supplier_name": "SupplierName",
            "total_revenue": "Revenue",
            "total_profit": "Profit",
            "gross_margin_pct": "MarginPct",
            "orders": "Orders",
            "units": "Units",
            "weight_lb": "WeightLb",
            "active_skus": "ActiveSkus",
            "active_customers": "ActiveCustomers",
            "asp_lb": "ASP/lb",
            "asp_lb_delta_pct": "ASP/lb DeltaPct",
            "last_sold": "LastSold",
            "cost_coverage_pct": "CostCoveragePct",
            "revenue_delta_mom": "RevenueDeltaMoM",
            "revenue_delta_mom_pct": "RevenueDeltaMoMPct",
            "margin_volatility": "MarginVolatility",
            "customer_hhi": "CustomerHHI",
            "sku_hhi": "SkuHHI",
            "health_score": "HealthScore",
            "health_label": "HealthLabel",
            "lifecycle": "Lifecycle",
            "classification": "Classification",
            "revenue_delta_window": "RevenueDeltaWindow",
            "revenue_delta_window_pct": "RevenueDeltaWindowPct",
        }
        frame = frame.rename(columns={k: v for k, v in rename_map.items() if k in frame.columns})

    meta = {
        "dataset": token,
        "supplier_id": str(supplier_id),
        "supplier_name": score.get("supplier_name"),
        "total_rows": int(len(frame.index)),
        "start": window.get("start"),
        "end": window.get("end"),
        "prior_start": window.get("prior_start"),
        "prior_end": window.get("prior_end"),
    }
    return frame, meta
