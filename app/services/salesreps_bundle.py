from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Sequence, Tuple

import pandas as pd

from app.services import fact_schema as fs
from app.services import fact_store
from app.services import filters_service


TOP_N_DEFAULT = 15
TABLE_PAGE_SIZE_DEFAULT = 25
TABLE_PAGE_SIZES = {25, 50, 100}
RISK_TOP_CUSTOMER_THRESHOLD = 0.30
RISK_MARGIN_THRESHOLD = 27.0
RISK_MOM_PROFIT_DOWN_THRESHOLD = -15.0

REP_ID_CANDIDATES: Tuple[str, ...] = (
    "SalesRepId",
    "SalesRepID",
    "PrimarySalesRepId",
    "PrimarySalesRepID",
    "RepId",
    "RepID",
    "UserId",
    "UserID",
    "RepUserId",
    "RepUserID",
    "SalesRepUserId",
    "SalesRepUserID",
)

REP_NAME_CANDIDATES: Tuple[str, ...] = (
    "SalesRepName",
    "PrimarySalesRepName",
    "SalesRep",
    "RepName",
    "SalespersonName",
    "SalesPersonName",
    "Owner",
    "AccountOwner",
    "UserName",
    "User",
    "FullName",
    "DisplayName",
)

ORDER_ID_CANDIDATES: Tuple[str, ...] = (
    "OrderId",
    "OrderID",
    "OrderNo",
    "Invoice",
    "InvoiceNo",
    "ShipmentID",
    "ShipmentId",
)

CUSTOMER_ID_CANDIDATES: Tuple[str, ...] = (
    "CustomerId",
    "CustomerID",
    "CustomerNo",
    "Customer",
    "CustID",
)

CUSTOMER_NAME_CANDIDATES: Tuple[str, ...] = (
    "CustomerName",
    "Customer",
)

PRODUCT_ID_CANDIDATES: Tuple[str, ...] = (
    "ProductId",
    "ProductID",
    "SKU",
    "Sku",
    "ItemId",
    "ItemID",
    "Item",
)

PRODUCT_NAME_CANDIDATES: Tuple[str, ...] = (
    "ProductName",
    "Product",
    "Description",
    "ItemName",
)


def _norm_col(name: str) -> str:
    return "".join(ch for ch in str(name).lower() if ch.isalnum())


def _safe_col(cols: set[str], *candidates: str) -> str | None:
    if not cols:
        return None
    lower_map = {str(c).lower(): c for c in cols}
    norm_map = {_norm_col(str(c)): c for c in cols}
    for cand in candidates:
        if not cand:
            continue
        if cand in cols:
            return cand
        key = str(cand).lower()
        if key in lower_map:
            return lower_map[key]
        norm_key = _norm_col(str(cand))
        if norm_key in norm_map:
            return norm_map[norm_key]
    return None


def _present_cols(cols: set[str], candidates: Sequence[str]) -> list[str]:
    if not cols:
        return []
    lower_map = {str(c).lower(): c for c in cols}
    norm_map = {_norm_col(str(c)): c for c in cols}
    present: list[str] = []
    for cand in candidates:
        if not cand:
            continue
        if cand in cols:
            present.append(cand)
            continue
        key = str(cand).lower()
        actual = lower_map.get(key)
        if actual:
            present.append(actual)
            continue
        norm_key = _norm_col(str(cand))
        actual = norm_map.get(norm_key)
        if actual:
            present.append(actual)
    return list(dict.fromkeys(present))


def _quote(col: str) -> str:
    return fact_store.quote_identifier(col)


def _coalesce_expr(cols: set[str], candidates: Sequence[str], default: str = "0") -> str:
    present = _present_cols(cols, candidates)
    if not present:
        return default
    inner = ", ".join([_quote(c) for c in present] + [default])
    return f"COALESCE({inner})"


def _string_expr(col: str) -> str:
    return f"NULLIF(TRIM(CAST({_quote(col)} AS VARCHAR)), '')"


def _coalesce_exprs(exprs: Sequence[str], default: str) -> str:
    if not exprs:
        return default
    inner = ", ".join([*exprs, default])
    return f"COALESCE({inner})"


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


def _all_time_requested(args: Any) -> bool:
    getter = args.get if hasattr(args, "get") else (lambda _k, _d=None: None)
    raw = getter("all_time") or getter("full_history") or getter("no_window") or getter("export_all")
    if raw is None:
        return False
    try:
        return str(raw).strip().lower() in {"1", "true", "yes", "on", "all"}
    except Exception:
        return False


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


def _clean_optional(val: Any) -> float | None:
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


def _pagination(args: Any, default_size: int = TABLE_PAGE_SIZE_DEFAULT, max_size: int = 100) -> Tuple[int, int]:
    getter = args.get if hasattr(args, "get") else (lambda _k, _d=None: None)
    try:
        page = max(1, int(getter("page", 1)))
    except Exception:
        page = 1
    try:
        size = int(getter("page_size") or getter("per_page") or default_size)
    except Exception:
        size = default_size
    if size not in TABLE_PAGE_SIZES:
        size = default_size
    size = max(1, min(size, max_size))
    return page, size


def _sort_params(args: Any) -> Tuple[str, str]:
    getter = args.get if hasattr(args, "get") else (lambda _k, _d=None: None)
    sort_raw = str(getter("sort") or getter("sort_by") or "revenue").strip().lower()
    dir_raw = str(getter("dir") or getter("sort_dir") or getter("direction") or "desc").strip().lower()
    mapping = {
        "rep": "rep_name",
        "name": "rep_name",
        "rep_name": "rep_name",
        "label": "rep_name",
        "revenue": "revenue",
        "profit": "profit",
        "margin_dollar": "profit",
        "margin$": "profit",
        "margin_amount": "profit",
        "margin": "margin_pct",
        "margin_pct": "margin_pct",
        "orders": "orders",
        "customers": "customers",
        "weight": "weight_lb",
        "weight_lb": "weight_lb",
        "units": "units",
        "qty": "units",
        "asp": "asp",
        "asp_lb": "asp_lb",
        "momentum": "momentum_pct",
        "top_customer_share": "top_customer_share",
        "top_5_customer_share": "top_5_customer_share",
        "concentration": "customer_hhi",
        "hhi": "customer_hhi",
        "mom_revenue_pct": "mom_revenue_pct",
        "mom_profit_pct": "mom_profit_pct",
        "top_customer_revenue": "top_customer_revenue",
    }
    sort_by = mapping.get(sort_raw, "revenue")
    sort_dir = "asc" if dir_raw in {"asc", "ascending", "up", "1"} else "desc"
    return sort_by, sort_dir


def _search_term(args: Any) -> str:
    getter = args.get if hasattr(args, "get") else (lambda _k, _d=None: None)
    raw = getter("search") or getter("q") or ""
    return str(raw).strip().lower()


def _apply_search_filter(df, search_term: str):
    if df is None or getattr(df, "empty", True) or not search_term:
        return df
    work = _normalize_frame(df)
    names = work.get("rep_name")
    if names is None:
        return work
    mask = names.fillna("").astype(str).str.lower().str.contains(search_term, na=False)
    return work.loc[mask]


def _normalize_frame(df):
    if df is None:
        return pd.DataFrame()
    try:
        records = df.to_dict(orient="records")
        if records:
            return pd.DataFrame.from_records(records)
        cols = list(getattr(df, "columns", []))
        return pd.DataFrame(columns=cols)
    except Exception:
        try:
            return df.reset_index(drop=True).copy()
        except Exception:
            return df


def _rollup_records(source: Any) -> List[Dict[str, Any]]:
    if source is None:
        return []
    if isinstance(source, list):
        return [dict(item) for item in source if isinstance(item, dict)]
    try:
        rows = source.to_dict(orient="records")
    except Exception:
        return []
    return [dict(item) for item in rows]


def _sanitize_rollup_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "rep_id": rec.get("rep_id") or rec.get("rep_key"),
        "rep_name": rec.get("rep_name"),
        "rep_key": rec.get("rep_key") or rec.get("rep_id"),
        "revenue": _clean_float(rec.get("revenue")),
        "cost": _clean_optional(rec.get("cost")),
        "profit": _clean_optional(rec.get("profit")),
        "margin_pct": _clean_optional(rec.get("margin_pct")),
        "orders": _clean_int(rec.get("orders")),
        "customers": _clean_int(rec.get("customers")),
        "units": _clean_float(rec.get("units")),
        "weight_lb": _clean_float(rec.get("weight_lb")),
        "asp": _clean_optional(rec.get("asp")),
        "asp_lb": _clean_optional(rec.get("asp_lb")),
        "top_customer_share": _clean_optional(rec.get("top_customer_share")),
        "top_5_customer_share": _clean_optional(rec.get("top_5_customer_share")),
        "top_customer_name": rec.get("top_customer_name"),
        "top_customer_revenue": _clean_optional(rec.get("top_customer_revenue")),
        "customer_hhi": _clean_optional(rec.get("customer_hhi")),
        "momentum_pct": _clean_optional(rec.get("momentum_pct")),
        "mom_revenue_pct": _clean_optional(rec.get("mom_revenue_pct")),
        "mom_profit_pct": _clean_optional(rec.get("mom_profit_pct")),
        "mom_margin_pct": _clean_optional(rec.get("mom_margin_pct")),
    }


def _sort_rollup_records(records: List[Dict[str, Any]], sort_by: str, sort_dir: str) -> List[Dict[str, Any]]:
    if not records:
        return []
    ascending = sort_dir == "asc"
    token = sort_by or "revenue"

    def _name(rec: Dict[str, Any]) -> str:
        return str(rec.get("rep_name") or "").strip().lower()

    if token == "rep_name":
        return sorted(records, key=lambda rec: (_name(rec), str(rec.get("rep_id") or "")), reverse=not ascending)

    def _metric(rec: Dict[str, Any]) -> float:
        val = rec.get(token)
        return _clean_float(val)

    return sorted(
        records,
        key=lambda rec: (_metric(rec), _name(rec)),
        reverse=not ascending,
    )


def _sort_rollup_df(df, sort_by: str, sort_dir: str):
    if df is None or getattr(df, "empty", True):
        return df
    work = _normalize_frame(df)
    if sort_by not in work.columns and sort_by != "rep_name":
        sort_by = "revenue"
    ascending = sort_dir == "asc"

    records = work.to_dict(orient="records")

    def _name(rec: Dict[str, Any]) -> str:
        return str(rec.get("rep_name") or "").strip().lower()

    if sort_by == "rep_name":
        records = sorted(records, key=lambda rec: (_name(rec), str(rec.get("rep_key") or "")), reverse=not ascending)
        return pd.DataFrame.from_records(records, columns=work.columns)

    def _metric_key(rec: Dict[str, Any]) -> tuple[int, float, str]:
        raw = rec.get(sort_by)
        missing = raw is None
        try:
            metric = float(raw)
            if math.isnan(metric):
                missing = True
                metric = 0.0
        except Exception:
            missing = True
            metric = 0.0
        if not ascending:
            metric *= -1
        return (1 if missing else 0, metric, _name(rec))

    records = sorted(records, key=_metric_key)
    return pd.DataFrame.from_records(records, columns=work.columns)


def _required_columns(cols: set[str]) -> Dict[str, str | None]:
    date_col = _safe_col(cols, fs.CANON.date, *fs.DATE_CANDIDATES)
    revenue_col = _safe_col(cols, fs.CANON.revenue, *fs.REVENUE_CANDIDATES)
    order_col = _safe_col(cols, fs.CANON.order_id, *ORDER_ID_CANDIDATES)
    customer_col = _safe_col(cols, fs.CANON.customer_id, *CUSTOMER_ID_CANDIDATES)
    customer_name_col = _safe_col(cols, fs.CANON.customer_name, *CUSTOMER_NAME_CANDIDATES)
    product_col = _safe_col(cols, fs.CANON.product_id, *PRODUCT_ID_CANDIDATES)
    product_name_col = _safe_col(cols, fs.CANON.product_name, *PRODUCT_NAME_CANDIDATES)
    missing_packs_col = _safe_col(cols, "missing_packs")
    cost_expr = _coalesce_expr(cols, (fs.CANON.cost, *fs.COST_TOTAL_CANDIDATES, "CostPrice"), "NULL")
    qty_expr = _coalesce_expr(cols, (fs.CANON.qty_units, *fs.QTY_CANDIDATES, "ShippedItems"), "0")
    weight_expr = _coalesce_expr(cols, (fs.CANON.weight_lb, *fs.WEIGHT_CANDIDATES), "0")
    return {
        "date": date_col,
        "revenue": revenue_col,
        "order": order_col,
        "customer": customer_col,
        "customer_name": customer_name_col,
        "product": product_col,
        "product_name": product_name_col,
        "missing_packs": missing_packs_col,
        "cost_expr": cost_expr,
        "qty_expr": qty_expr,
        "weight_expr": weight_expr,
    }


def _rep_exprs(cols: set[str]) -> Tuple[str, str]:
    rep_id_cols = _present_cols(cols, REP_ID_CANDIDATES)
    rep_name_cols = _present_cols(cols, REP_NAME_CANDIDATES)
    rep_id_exprs = [_string_expr(c) for c in rep_id_cols]
    rep_name_exprs = [_string_expr(c) for c in rep_name_cols]
    default = "'Unassigned'"
    rep_key_expr = _coalesce_exprs(rep_id_exprs + rep_name_exprs, default)
    rep_name_expr = _coalesce_exprs(rep_name_exprs + rep_id_exprs, rep_key_expr)
    return rep_key_expr, rep_name_expr


def _scoped_sql(cols_map: Dict[str, str | None], where_sql: str, rep_key_expr: str, rep_name_expr: str) -> str:
    date_col = cols_map.get("date")
    revenue_col = cols_map.get("revenue")
    order_col = cols_map.get("order")
    customer_col = cols_map.get("customer")
    if not all([date_col, revenue_col, order_col, customer_col]):
        return ""
    customer_name = cols_map.get("customer_name")
    product_col = cols_map.get("product")
    product_name = cols_map.get("product_name")
    cost_expr = cols_map.get("cost_expr") or "NULL"
    qty_expr = cols_map.get("qty_expr") or "0"
    weight_expr = cols_map.get("weight_expr") or "0"
    missing_packs_col = cols_map.get("missing_packs")
    missing_packs_expr = f"CAST({_quote(missing_packs_col)} AS BOOLEAN)" if missing_packs_col else "NULL::BOOLEAN"

    order_expr = _string_expr(order_col)
    customer_expr = _string_expr(customer_col)
    customer_name_expr = _string_expr(customer_name) if customer_name else customer_expr
    product_expr = _string_expr(product_col) if product_col else "NULL::VARCHAR"
    product_name_expr = _string_expr(product_name) if product_name else product_expr

    return f"""
        SELECT
            {rep_key_expr} AS rep_key,
            {rep_name_expr} AS rep_name,
            CAST({_quote(date_col)} AS DATE) AS order_date,
            {order_expr} AS order_id,
            {customer_expr} AS customer_id,
            {customer_name_expr} AS customer_name,
            {product_expr} AS product_id,
            {product_name_expr} AS product_name,
            CAST({_quote(revenue_col)} AS DOUBLE) AS revenue,
            CAST({cost_expr} AS DOUBLE) AS cost,
            CAST({qty_expr} AS DOUBLE) AS units,
            CAST({weight_expr} AS DOUBLE) AS weight_lb,
            {missing_packs_expr} AS missing_packs
        FROM fact
        WHERE {where_sql}
    """


def _rollup_sql(base_sql: str) -> str:
    return f"""
        WITH base AS (
            {base_sql}
        ),
        rep_totals AS (
            SELECT
                rep_key,
                ANY_VALUE(rep_name) AS rep_name,
                SUM(revenue) AS revenue,
                SUM(cost) AS cost,
                CASE WHEN SUM(cost) IS NULL THEN NULL ELSE SUM(revenue) - SUM(cost) END AS profit,
                COUNT(DISTINCT order_id) AS orders,
                COUNT(DISTINCT customer_id) AS customers,
                SUM(units) AS units,
                SUM(weight_lb) AS weight_lb,
                SUM(CASE WHEN cost IS NULL THEN 1 ELSE 0 END) AS cost_null_rows,
                COUNT(*) AS row_count
            FROM base
            GROUP BY rep_key
        ),
        customer_rev AS (
            SELECT
                rep_key,
                customer_id,
                ANY_VALUE(customer_name) AS customer_name,
                SUM(revenue) AS revenue
            FROM base
            WHERE customer_id IS NOT NULL AND customer_id <> ''
            GROUP BY 1,2
        ),
        customer_ranked AS (
            SELECT
                cr.rep_key,
                cr.customer_id,
                cr.customer_name,
                cr.revenue,
                SUM(cr.revenue) OVER (PARTITION BY cr.rep_key) AS rep_total_revenue,
                ROW_NUMBER() OVER (PARTITION BY cr.rep_key ORDER BY cr.revenue DESC, cr.customer_id) AS rn
            FROM customer_rev cr
        ),
        concentration AS (
            SELECT
                rep_key,
                MAX(CASE WHEN rn = 1 AND rep_total_revenue > 0 THEN revenue / rep_total_revenue ELSE NULL END) AS top_customer_share,
                SUM(CASE WHEN rn <= 5 AND rep_total_revenue > 0 THEN revenue / rep_total_revenue ELSE 0 END) AS top_5_customer_share,
                SUM(CASE WHEN rep_total_revenue > 0 THEN POWER(revenue / rep_total_revenue, 2) ELSE 0 END) AS hhi,
                MAX(CASE WHEN rn = 1 THEN customer_name END) AS top_customer_name,
                MAX(CASE WHEN rn = 1 THEN revenue END) AS top_customer_revenue
            FROM customer_ranked
            GROUP BY rep_key
        ),
        ref AS (
            SELECT MAX(order_date) AS max_date FROM base
        ),
        momentum AS (
            SELECT
                rep_key,
                SUM(CASE WHEN order_date >= ref.max_date - INTERVAL 90 DAY THEN revenue ELSE 0 END) AS rev_recent,
                SUM(CASE WHEN order_date < ref.max_date - INTERVAL 90 DAY AND order_date >= ref.max_date - INTERVAL 180 DAY THEN revenue ELSE 0 END) AS rev_prior
            FROM base, ref
            GROUP BY rep_key
        ),
        monthly AS (
            SELECT
                rep_key,
                DATE_TRUNC('month', order_date) AS month_start,
                SUM(revenue) AS revenue,
                SUM(cost) AS cost,
                CASE WHEN SUM(cost) IS NULL THEN NULL ELSE SUM(revenue) - SUM(cost) END AS profit,
                CASE WHEN SUM(revenue) > 0 AND SUM(cost) IS NOT NULL THEN (SUM(revenue) - SUM(cost)) / SUM(revenue) * 100 ELSE NULL END AS margin_pct
            FROM base
            GROUP BY 1,2
        ),
        monthly_ranked AS (
            SELECT
                rep_key,
                month_start,
                revenue,
                profit,
                margin_pct,
                ROW_NUMBER() OVER (PARTITION BY rep_key ORDER BY month_start DESC) AS rn
            FROM monthly
        ),
        mom_monthly AS (
            SELECT
                rep_key,
                MAX(CASE WHEN rn = 1 THEN revenue END) AS revenue_curr_month,
                MAX(CASE WHEN rn = 2 THEN revenue END) AS revenue_prev_month,
                MAX(CASE WHEN rn = 1 THEN profit END) AS profit_curr_month,
                MAX(CASE WHEN rn = 2 THEN profit END) AS profit_prev_month,
                MAX(CASE WHEN rn = 1 THEN margin_pct END) AS margin_curr_month,
                MAX(CASE WHEN rn = 2 THEN margin_pct END) AS margin_prev_month
            FROM monthly_ranked
            GROUP BY rep_key
        )
        SELECT
            rt.rep_key,
            rt.rep_name,
            rt.revenue,
            rt.cost,
            rt.profit,
            CASE WHEN rt.revenue > 0 AND rt.cost IS NOT NULL THEN (rt.profit / rt.revenue) * 100 ELSE NULL END AS margin_pct,
            rt.orders,
            rt.customers,
            rt.units,
            rt.weight_lb,
            CASE WHEN rt.units > 0 THEN rt.revenue / NULLIF(rt.units, 0) ELSE NULL END AS asp,
            CASE WHEN rt.weight_lb > 0 THEN rt.revenue / NULLIF(rt.weight_lb, 0) ELSE NULL END AS asp_lb,
            conc.top_customer_share AS top_customer_share,
            conc.top_5_customer_share AS top_5_customer_share,
            conc.top_customer_name AS top_customer_name,
            conc.top_customer_revenue AS top_customer_revenue,
            conc.hhi AS customer_hhi,
            CASE WHEN mom90.rev_prior > 0 THEN (mom90.rev_recent - mom90.rev_prior) / mom90.rev_prior * 100 ELSE NULL END AS momentum_pct,
            CASE WHEN mm.revenue_prev_month > 0 THEN (mm.revenue_curr_month - mm.revenue_prev_month) / mm.revenue_prev_month * 100 ELSE NULL END AS mom_revenue_pct,
            CASE
                WHEN mm.profit_prev_month IS NULL OR mm.profit_prev_month = 0 THEN NULL
                ELSE (mm.profit_curr_month - mm.profit_prev_month) / ABS(mm.profit_prev_month) * 100
            END AS mom_profit_pct,
            CASE
                WHEN mm.margin_curr_month IS NULL OR mm.margin_prev_month IS NULL THEN NULL
                ELSE mm.margin_curr_month - mm.margin_prev_month
            END AS mom_margin_pct,
            rt.cost_null_rows,
            rt.row_count
        FROM rep_totals rt
        LEFT JOIN concentration conc ON conc.rep_key = rt.rep_key
        LEFT JOIN momentum mom90 ON mom90.rep_key = rt.rep_key
        LEFT JOIN mom_monthly mm ON mm.rep_key = rt.rep_key
    """


def _kpis_sql(base_sql: str) -> str:
    return f"""
        WITH base AS (
            {base_sql}
        ),
        monthly AS (
            SELECT
                DATE_TRUNC('month', order_date) AS month_start,
                SUM(revenue) AS revenue,
                SUM(cost) AS cost,
                CASE WHEN SUM(cost) IS NULL THEN NULL ELSE SUM(revenue) - SUM(cost) END AS profit,
                CASE WHEN SUM(revenue) > 0 AND SUM(cost) IS NOT NULL THEN (SUM(revenue) - SUM(cost)) / SUM(revenue) * 100 ELSE NULL END AS margin_pct
            FROM base
            GROUP BY 1
        ),
        monthly_ranked AS (
            SELECT
                month_start,
                revenue,
                profit,
                margin_pct,
                ROW_NUMBER() OVER (ORDER BY month_start DESC) AS rn
            FROM monthly
        )
        SELECT
            SUM(revenue) AS revenue,
            SUM(cost) AS cost,
            CASE WHEN SUM(cost) IS NULL THEN NULL ELSE SUM(revenue) - SUM(cost) END AS profit,
            CASE WHEN SUM(revenue) > 0 AND SUM(cost) IS NOT NULL THEN (SUM(revenue) - SUM(cost)) / SUM(revenue) * 100 ELSE NULL END AS margin_pct,
            COUNT(DISTINCT order_id) AS orders,
            COUNT(DISTINCT customer_id) AS customers,
            COUNT(DISTINCT rep_key) AS active_reps,
            SUM(units) AS units,
            SUM(weight_lb) AS weight_lb,
            CASE WHEN SUM(units) > 0 THEN SUM(revenue) / NULLIF(SUM(units), 0) ELSE NULL END AS asp,
            CASE WHEN SUM(weight_lb) > 0 THEN SUM(revenue) / NULLIF(SUM(weight_lb), 0) ELSE NULL END AS asp_lb,
            SUM(CASE WHEN cost IS NULL THEN 1 ELSE 0 END) AS cost_null_rows,
            COUNT(*) AS total_rows,
            MIN(order_date) AS date_min,
            MAX(order_date) AS date_max,
            (SELECT MAX(CASE WHEN rn = 1 THEN revenue END) FROM monthly_ranked) AS revenue_curr_month,
            (SELECT MAX(CASE WHEN rn = 2 THEN revenue END) FROM monthly_ranked) AS revenue_prev_month,
            (SELECT MAX(CASE WHEN rn = 1 THEN profit END) FROM monthly_ranked) AS profit_curr_month,
            (SELECT MAX(CASE WHEN rn = 2 THEN profit END) FROM monthly_ranked) AS profit_prev_month,
            (SELECT MAX(CASE WHEN rn = 1 THEN margin_pct END) FROM monthly_ranked) AS margin_curr_month,
            (SELECT MAX(CASE WHEN rn = 2 THEN margin_pct END) FROM monthly_ranked) AS margin_prev_month,
            CASE
                WHEN (SELECT MAX(CASE WHEN rn = 2 THEN revenue END) FROM monthly_ranked) > 0
                THEN (
                    (SELECT MAX(CASE WHEN rn = 1 THEN revenue END) FROM monthly_ranked)
                    - (SELECT MAX(CASE WHEN rn = 2 THEN revenue END) FROM monthly_ranked)
                )
                / (SELECT MAX(CASE WHEN rn = 2 THEN revenue END) FROM monthly_ranked) * 100
                ELSE NULL
            END AS revenue_mom_pct,
            CASE
                WHEN (SELECT MAX(CASE WHEN rn = 2 THEN profit END) FROM monthly_ranked) IS NULL
                     OR (SELECT MAX(CASE WHEN rn = 2 THEN profit END) FROM monthly_ranked) = 0
                THEN NULL
                ELSE (
                    (SELECT MAX(CASE WHEN rn = 1 THEN profit END) FROM monthly_ranked)
                    - (SELECT MAX(CASE WHEN rn = 2 THEN profit END) FROM monthly_ranked)
                )
                / ABS((SELECT MAX(CASE WHEN rn = 2 THEN profit END) FROM monthly_ranked)) * 100
            END AS profit_mom_pct,
            CASE
                WHEN (SELECT MAX(CASE WHEN rn = 1 THEN margin_pct END) FROM monthly_ranked) IS NULL
                     OR (SELECT MAX(CASE WHEN rn = 2 THEN margin_pct END) FROM monthly_ranked) IS NULL
                THEN NULL
                ELSE (
                    (SELECT MAX(CASE WHEN rn = 1 THEN margin_pct END) FROM monthly_ranked)
                    - (SELECT MAX(CASE WHEN rn = 2 THEN margin_pct END) FROM monthly_ranked)
                )
            END AS margin_mom_pct
        FROM base
    """


def _trend_sql(base_sql: str, top_n: int) -> str:
    return f"""
        WITH base AS (
            {base_sql}
        ),
        rep_totals AS (
            SELECT rep_key, SUM(revenue) AS revenue
            FROM base
            GROUP BY rep_key
            ORDER BY revenue DESC
            LIMIT {top_n}
        )
        SELECT
            strftime('%Y-%m', order_date) AS month,
            base.rep_key AS rep_key,
            ANY_VALUE(base.rep_name) AS rep_name,
            SUM(base.revenue) AS revenue
        FROM base
        JOIN rep_totals ON base.rep_key = rep_totals.rep_key
        GROUP BY 1,2
        ORDER BY 1
    """


def _build_table_rows(df, page: int, page_size: int, sort_by: str, sort_dir: str) -> Tuple[List[Dict[str, Any]], int, int, int]:
    records = _rollup_records(df)
    if not records:
        return [], 0, 0, 0

    work = [_sanitize_rollup_record(rec) for rec in records]
    sorted_rows = _sort_rollup_records(work, sort_by, sort_dir)
    total_rows = len(sorted_rows)
    total_pages = max(1, math.ceil(total_rows / page_size)) if total_rows else 0
    offset = (page - 1) * page_size
    if offset >= total_rows:
        offset = 0
        page = 1
    page_rows = sorted_rows[offset : offset + page_size]

    rows: List[Dict[str, Any]] = []
    for rec in page_rows:
        rows.append(
            {
                "rep_id": rec.get("rep_id"),
                "rep_name": rec.get("rep_name"),
                "key": rec.get("rep_key") or rec.get("rep_id"),
                "label": rec.get("rep_name") or rec.get("rep_key") or rec.get("rep_id"),
                "revenue": _clean_float(rec.get("revenue", 0.0)),
                "cost": _clean_optional(rec.get("cost")),
                "profit": _clean_optional(rec.get("profit")),
                "margin_pct": _clean_optional(rec.get("margin_pct")),
                "orders": _clean_int(rec.get("orders", 0)),
                "customers": _clean_int(rec.get("customers", 0)),
                "units": _clean_float(rec.get("units", 0.0)),
                "weight_lb": _clean_float(rec.get("weight_lb", 0.0)),
                "asp": _clean_optional(rec.get("asp")),
                "asp_lb": _clean_optional(rec.get("asp_lb")),
                "top_customer_share": _clean_optional(rec.get("top_customer_share")),
                "top_5_customer_share": _clean_optional(rec.get("top_5_customer_share")),
                "top_customer_name": rec.get("top_customer_name"),
                "top_customer_revenue": _clean_optional(rec.get("top_customer_revenue")),
                "top_customer_share_pct": _clean_optional(rec.get("top_customer_share") * 100.0)
                if rec.get("top_customer_share") is not None
                else None,
                "top_5_customer_share_pct": _clean_optional(rec.get("top_5_customer_share") * 100.0)
                if rec.get("top_5_customer_share") is not None
                else None,
                "customer_hhi": _clean_optional(rec.get("customer_hhi")),
                "momentum_pct": _clean_optional(rec.get("momentum_pct")),
                "mom_revenue_pct": _clean_optional(rec.get("mom_revenue_pct")),
                "mom_profit_pct": _clean_optional(rec.get("mom_profit_pct")),
                "mom_margin_pct": _clean_optional(rec.get("mom_margin_pct")),
            }
        )
    return rows, total_rows, total_pages, page


def _what_changed_insight(kpis: Dict[str, Any], rollup_df) -> str:
    rows = [_sanitize_rollup_record(rec) for rec in _rollup_records(rollup_df)]
    if not rows:
        return "No sales rep activity for the selected filters."
    rev_mom = _clean_optional(kpis.get("revenue_mom_pct"))
    if rev_mom is None:
        return "MoM trend is unavailable for the selected date window."
    direction = "up" if rev_mom >= 0 else "down"
    magnitude = abs(rev_mom)
    risky = sum(1 for row in rows if (_clean_float(row.get("top_customer_share")) > RISK_TOP_CUSTOMER_THRESHOLD))
    decliners = sum(1 for row in rows if (_clean_optional(row.get("mom_revenue_pct")) or 0.0) < 0)
    if direction == "down":
        return f"Revenue down {magnitude:.1f}% MoM; {decliners} rep(s) declined and {risky} rep(s) have high concentration."
    return f"Revenue up {magnitude:.1f}% MoM; watch concentration risk on {risky} rep(s)."


def _risk_flags(rollup_df) -> List[Dict[str, Any]]:
    rows = [_sanitize_rollup_record(rec) for rec in _rollup_records(rollup_df)]
    if not rows:
        return []
    top_customer_count = sum(
        1 for row in rows if _clean_float(row.get("top_customer_share")) > RISK_TOP_CUSTOMER_THRESHOLD
    )
    low_margin_count = sum(
        1
        for row in rows
        if (_clean_optional(row.get("margin_pct")) is not None and _clean_float(row.get("margin_pct")) < RISK_MARGIN_THRESHOLD)
    )
    profit_down_count = sum(
        1
        for row in rows
        if (_clean_optional(row.get("mom_profit_pct")) is not None and _clean_float(row.get("mom_profit_pct")) < RISK_MOM_PROFIT_DOWN_THRESHOLD)
    )
    return [
        {
            "key": "top_customer_concentration",
            "severity": "high" if top_customer_count > 0 else "ok",
            "count": top_customer_count,
            "label": f"Top customer share > {int(RISK_TOP_CUSTOMER_THRESHOLD * 100)}%",
        },
        {
            "key": "low_margin",
            "severity": "medium" if low_margin_count > 0 else "ok",
            "count": low_margin_count,
            "label": f"Margin below {RISK_MARGIN_THRESHOLD:.0f}%",
        },
        {
            "key": "profit_decline",
            "severity": "high" if profit_down_count > 0 else "ok",
            "count": profit_down_count,
            "label": f"Profit down MoM worse than {abs(RISK_MOM_PROFIT_DOWN_THRESHOLD):.0f}%",
        },
    ]


def build_salesreps_bundle(filters: Any, scope: Dict[str, Any], args: Any) -> Dict[str, Any]:
    started = time.perf_counter()
    cols = fact_store.list_columns()
    cols_map = _required_columns(cols)
    missing = [k for k in ("date", "revenue", "order", "customer") if not cols_map.get(k)]
    if missing:
        return {"error": {"message": f"Required columns missing for salesreps bundle: {', '.join(missing)}"}, "meta": {"cached": False}}

    rep_key_expr, rep_name_expr = _rep_exprs(cols)
    where_sql, params, start_iso, end_iso = fact_store.build_where_clause(filters, cols, scope, apply_default_window=True)
    base_sql = _scoped_sql(cols_map, where_sql, rep_key_expr, rep_name_expr)
    if not base_sql:
        return {"error": {"message": "Salesreps base query could not be built"}, "meta": {"cached": False}}

    page_num, page_size = _pagination(args)
    sort_by, sort_dir = _sort_params(args)
    search_term = _search_term(args)
    getter = args.get if hasattr(args, "get") else (lambda _k, _d=None: None)
    metric_token = str(getter("metric") or "revenue").strip().lower()
    if hasattr(args, "get"):
        try:
            top_n = int(args.get("topN") or args.get("top_n") or TOP_N_DEFAULT)
        except Exception:
            top_n = TOP_N_DEFAULT
    else:
        top_n = TOP_N_DEFAULT
    top_n = max(5, min(top_n, 25))

    kpis_df = fact_store.execute_sql_df(_kpis_sql(base_sql), params, tag="salesreps.kpis")
    rollup_df = fact_store.execute_sql_df(_rollup_sql(base_sql), params, tag="salesreps.rollup")
    trend_df = fact_store.execute_sql_df(_trend_sql(base_sql, top_n), params, tag="salesreps.trend")
    kpis_df = _normalize_frame(kpis_df)
    rollup_df = _normalize_frame(rollup_df)
    trend_df = _normalize_frame(trend_df)

    if rollup_df.empty and kpis_df.empty:
        payload = {
            "kpis": {"what_changed": "No sales rep activity for the selected filters."},
            "trend": {"labels": [], "series": []},
            "charts": {},
            "table": {"rows": [], "page": page_num, "page_size": page_size, "total_rows": 0, "total_pages": 0},
            "risk_flags": [],
            "meta": {"page_id": "salesreps", "window_start": start_iso, "window_end": end_iso},
        }
        return payload

    krow = kpis_df.iloc[0] if not kpis_df.empty else {}
    revenue = _clean_float(krow.get("revenue"))
    cost = _clean_optional(krow.get("cost"))
    profit = _clean_optional(krow.get("profit"))
    margin_pct = _clean_optional(krow.get("margin_pct"))
    orders = _clean_int(krow.get("orders"))
    customers = _clean_int(krow.get("customers"))
    active_reps = _clean_int(krow.get("active_reps"))
    units = _clean_float(krow.get("units"))
    weight_lb = _clean_float(krow.get("weight_lb"))
    asp = _clean_optional(krow.get("asp"))
    asp_lb = _clean_optional(krow.get("asp_lb"))
    revenue_mom_pct = _clean_optional(krow.get("revenue_mom_pct"))
    profit_mom_pct = _clean_optional(krow.get("profit_mom_pct"))
    margin_mom_pct = _clean_optional(krow.get("margin_mom_pct"))
    cost_null_rows = _clean_int(krow.get("cost_null_rows"))
    total_rows = _clean_int(krow.get("total_rows"))
    cost_coverage_pct = None
    if total_rows:
        cost_coverage_pct = (1 - (cost_null_rows / total_rows)) * 100.0
    manifest_meta = fact_store.get_meta() or {}
    last_refresh = (
        manifest_meta.get("last_refresh_utc")
        or manifest_meta.get("watermark_dt")
        or manifest_meta.get("watermark")
        or None
    )

    kpis = {
        "revenue": revenue,
        "cost": cost,
        "profit": profit,
        "margin_pct": margin_pct,
        "orders": orders,
        "customers": customers,
        "active_reps": active_reps,
        "units": units,
        "weight_lb": weight_lb,
        "asp": asp,
        "asp_lb": asp_lb,
        "revenue_mom_pct": revenue_mom_pct,
        "profit_mom_pct": profit_mom_pct,
        "margin_mom_pct": margin_mom_pct,
        "cost_coverage_pct": cost_coverage_pct,
        "last_refresh": last_refresh,
        "start": start_iso,
        "end": end_iso,
    }

    # Trend payload (top reps)
    trend_labels = sorted({str(r.month) for r in trend_df.itertuples()} if not trend_df.empty else [])
    series_map: Dict[str, Dict[str, float]] = {}
    rep_names: Dict[str, str] = {}
    if not trend_df.empty:
        for r in trend_df.itertuples():
            rep_key = getattr(r, "rep_key", None)
            month = str(getattr(r, "month", ""))
            if rep_key is None or not month:
                continue
            series_map.setdefault(rep_key, {})[month] = _clean_float(getattr(r, "revenue", 0.0))
            rep_names[rep_key] = getattr(r, "rep_name", None) or rep_key

    trend_series: List[Dict[str, Any]] = []
    for rep_key, points in series_map.items():
        trend_series.append(
            {
                "rep_id": rep_key,
                "rep_name": rep_names.get(rep_key) or rep_key,
                "revenue": [points.get(label, 0.0) for label in trend_labels],
            }
        )

    # Charts built from rollup
    charts: Dict[str, Any] = {}
    rollup_rows = [_sanitize_rollup_record(rec) for rec in _rollup_records(rollup_df)]
    if rollup_rows:
        top_reps = _sort_rollup_records(rollup_rows, "revenue", "desc")[:10]
        charts["top_reps"] = [
            {
                "rep_id": row.get("rep_id"),
                "rep_name": row.get("rep_name"),
                "revenue": row.get("revenue"),
                "profit": row.get("profit"),
                "margin_pct": row.get("margin_pct"),
                "orders": row.get("orders"),
                "customers": row.get("customers"),
                "weight_lb": row.get("weight_lb"),
            }
            for row in top_reps
        ]

        charts["scatter"] = [
            {
                "rep_id": row.get("rep_id"),
                "rep_name": row.get("rep_name"),
                "customers": row.get("customers"),
                "orders": row.get("orders"),
                "revenue": row.get("revenue"),
                "profit": row.get("profit"),
                "margin_pct": row.get("margin_pct"),
            }
            for row in rollup_rows
        ]

        charts["concentration"] = [
            {
                "rep_id": row.get("rep_id"),
                "rep_name": row.get("rep_name"),
                "top_customer_share": row.get("top_customer_share"),
                "top_5_customer_share": row.get("top_5_customer_share"),
                "top_customer_name": row.get("top_customer_name"),
                "top_customer_revenue": row.get("top_customer_revenue"),
                "customer_hhi": row.get("customer_hhi"),
            }
            for row in rollup_rows
        ]

        charts["profit_vs_revenue"] = [
            {
                "rep_id": row.get("rep_id"),
                "rep_name": row.get("rep_name"),
                "revenue": row.get("revenue"),
                "profit": row.get("profit"),
                "margin_pct": row.get("margin_pct"),
            }
            for row in rollup_rows
        ]

        asp_leaders = [row for row in _sort_rollup_records(rollup_rows, "asp", "desc") if row.get("asp") is not None][:10]
        charts["asp_leaders"] = [
            {
                "rep_id": row.get("rep_id"),
                "rep_name": row.get("rep_name"),
                "asp": row.get("asp"),
                "revenue": row.get("revenue"),
            }
            for row in asp_leaders
        ]

        margin_rank = [
            row
            for row in _sort_rollup_records(rollup_rows, "margin_pct", "desc")
            if row.get("margin_pct") is not None
        ][:10]
        charts["margin_ranking"] = [
            {
                "rep_id": row.get("rep_id"),
                "rep_name": row.get("rep_name"),
                "margin_pct": row.get("margin_pct"),
                "revenue": row.get("revenue"),
            }
            for row in margin_rank
        ]

        pareto_rows: List[Dict[str, Any]] = []
        sorted_rev = _sort_rollup_records(rollup_rows, "revenue", "desc")
        total_rev = sum(_clean_float(row.get("revenue")) for row in sorted_rev)
        cumulative = 0.0
        for row in sorted_rev:
            rev = _clean_float(row.get("revenue"))
            cumulative += rev
            pareto_rows.append(
                {
                    "rep_id": row.get("rep_id"),
                    "rep_name": row.get("rep_name"),
                    "revenue": rev,
                    "cumulative_pct": (cumulative / total_rev * 100.0) if total_rev > 0 else None,
                }
            )
        charts["pareto"] = pareto_rows

    table_source = rollup_rows
    if search_term:
        table_source = [
            row
            for row in rollup_rows
            if search_term in str(row.get("rep_name") or "").strip().lower()
        ]
    rows, total_rows, total_pages, page_num = _build_table_rows(table_source, page_num, page_size, sort_by, sort_dir)
    total_reps = len(rollup_rows)
    kpis["active_reps"] = max(_clean_int(kpis.get("active_reps"), 0), total_reps)
    kpis["what_changed"] = _what_changed_insight(kpis, rollup_df)
    risk_flags = _risk_flags(rollup_df)

    duration_ms = int((time.perf_counter() - started) * 1000)
    meta = {
        "page_id": "salesreps",
        "window_start": start_iso,
        "window_end": end_iso,
        "date_min": krow.get("date_min"),
        "date_max": krow.get("date_max"),
        "elapsed_ms": duration_ms,
        "units_label": "Units",
        "asp_label": "ASP",
        "asp_lb_label": "ASP / lb",
        "has_margin": margin_pct is not None,
        "last_refresh": last_refresh,
        "search": search_term,
        "metric": metric_token,
        "risk_thresholds": {
            "top_customer_share": RISK_TOP_CUSTOMER_THRESHOLD,
            "margin_pct": RISK_MARGIN_THRESHOLD,
            "mom_profit_down_pct": RISK_MOM_PROFIT_DOWN_THRESHOLD,
        },
    }

    payload = {
        "kpis": kpis,
        "trend": {"labels": trend_labels, "series": trend_series},
        "charts": {
            "trend": {"labels": trend_labels, "series": trend_series},
            **charts,
        },
        "table": {
            "rows": rows,
            "page": page_num,
            "page_size": page_size,
            "total_rows": total_rows,
            "total_pages": total_pages,
            "sort_by": sort_by,
            "sort_dir": sort_dir,
            "search": search_term,
            "all_rows": len(table_source),
        },
        "risk_flags": risk_flags,
        "meta": meta,
    }
    return payload


def build_salesreps_drilldown(rep_id: str, filters: Any, scope: Dict[str, Any], args: Any) -> Dict[str, Any]:
    cols = fact_store.list_columns()
    cols_map = _required_columns(cols)
    missing = [k for k in ("date", "revenue", "order", "customer") if not cols_map.get(k)]
    if missing:
        return {"error": {"message": f"Required columns missing for salesreps drilldown: {', '.join(missing)}"}, "meta": {"cached": False}}

    rep_key_expr, rep_name_expr = _rep_exprs(cols)
    base_where, params, start_iso, end_iso = fact_store.build_where_clause(
        filters, cols, scope, apply_default_window=True
    )
    rep_match_sql = f"({rep_key_expr} = ? OR {rep_name_expr} = ?)"
    where_sql = f"({base_where}) AND {rep_match_sql}"
    params_rep = list(params) + [rep_id, rep_id]
    scoped_sql = _scoped_sql(cols_map, where_sql, rep_key_expr, rep_name_expr)
    if not scoped_sql:
        return {"error": {"message": "Salesreps drilldown base query could not be built"}, "meta": {"cached": False}}

    at_risk_days = _clean_int(args.get("at_risk_days") if hasattr(args, "get") else None, 45)
    at_risk_days = max(7, min(at_risk_days, 365))

    summary_sql = f"""
        WITH scoped AS (
            {scoped_sql}
        ),
        ref AS (
            SELECT COALESCE(MAX(order_date), CURRENT_DATE) AS ref_date FROM scoped
        ),
        summary AS (
            SELECT
                MIN(rep_name) AS rep_name,
                SUM(revenue) AS revenue,
                SUM(cost) AS cost,
                CASE WHEN SUM(cost) IS NULL THEN NULL ELSE SUM(revenue) - SUM(cost) END AS profit,
                CASE WHEN SUM(revenue) > 0 AND SUM(cost) IS NOT NULL THEN (SUM(revenue) - SUM(cost)) / SUM(revenue) * 100 ELSE NULL END AS margin_pct,
                COUNT(DISTINCT order_id) AS orders,
                COUNT(DISTINCT customer_id) AS customers,
                SUM(units) AS units,
                SUM(weight_lb) AS weight_lb,
                CASE WHEN SUM(units) > 0 THEN SUM(revenue) / NULLIF(SUM(units), 0) ELSE NULL END AS asp,
                CASE WHEN SUM(weight_lb) > 0 THEN SUM(revenue) / NULLIF(SUM(weight_lb), 0) ELSE NULL END AS asp_lb,
                MIN(order_date) AS first_order,
                MAX(order_date) AS last_order,
                SUM(CASE WHEN order_date > ref.ref_date - INTERVAL 30 DAY THEN revenue ELSE 0 END) AS revenue_last_30,
                SUM(CASE WHEN order_date > ref.ref_date - INTERVAL 90 DAY THEN revenue ELSE 0 END) AS revenue_last_90,
                SUM(CASE WHEN order_date <= ref.ref_date - INTERVAL 90 DAY AND order_date > ref.ref_date - INTERVAL 180 DAY THEN revenue ELSE 0 END) AS revenue_prev_90,
                SUM(CASE WHEN order_date > ref.ref_date - INTERVAL 30 DAY THEN cost ELSE 0 END) AS cost_last_30,
                SUM(CASE WHEN order_date > ref.ref_date - INTERVAL 90 DAY THEN cost ELSE 0 END) AS cost_last_90,
                COUNT(DISTINCT CASE WHEN order_date > ref.ref_date - INTERVAL 30 DAY THEN order_id END) AS orders_last_30,
                COUNT(DISTINCT CASE WHEN order_date > ref.ref_date - INTERVAL 90 DAY THEN order_id END) AS orders_last_90,
                SUM(CASE WHEN cost IS NULL THEN 1 ELSE 0 END) AS cost_null_rows,
                COUNT(*) AS total_rows,
                DATE_DIFF('day', MAX(order_date), MAX(ref.ref_date)) AS days_since_last
            FROM scoped, ref
        ),
        monthly AS (
            SELECT
                DATE_TRUNC('month', order_date) AS month_start,
                SUM(revenue) AS revenue,
                SUM(cost) AS cost,
                CASE WHEN SUM(cost) IS NULL THEN NULL ELSE SUM(revenue) - SUM(cost) END AS profit,
                CASE WHEN SUM(revenue) > 0 AND SUM(cost) IS NOT NULL THEN (SUM(revenue) - SUM(cost)) / SUM(revenue) * 100 ELSE NULL END AS margin_pct,
                COUNT(DISTINCT order_id) AS orders,
                COUNT(DISTINCT customer_id) AS customers,
                SUM(units) AS units,
                SUM(weight_lb) AS weight_lb
            FROM scoped
            GROUP BY 1
            ORDER BY 1
        ),
        weekly AS (
            SELECT
                DATE_TRUNC('week', order_date) AS week_start,
                SUM(revenue) AS revenue,
                SUM(cost) AS cost,
                CASE WHEN SUM(cost) IS NULL THEN NULL ELSE SUM(revenue) - SUM(cost) END AS profit,
                CASE WHEN SUM(revenue) > 0 AND SUM(cost) IS NOT NULL THEN (SUM(revenue) - SUM(cost)) / SUM(revenue) * 100 ELSE NULL END AS margin_pct,
                COUNT(DISTINCT order_id) AS orders,
                COUNT(DISTINCT customer_id) AS customers,
                SUM(units) AS units,
                SUM(weight_lb) AS weight_lb
            FROM scoped
            GROUP BY 1
            ORDER BY 1
        )
        SELECT
            summary.*,
            (SELECT list(strftime('%Y-%m', month_start)) FROM monthly) AS trend_labels,
            (SELECT list(revenue) FROM monthly) AS trend_revenue,
            (SELECT list(orders) FROM monthly) AS trend_orders,
            (SELECT list(profit) FROM monthly) AS trend_profit,
            (SELECT list(margin_pct) FROM monthly) AS trend_margin,
            (SELECT list(customers) FROM monthly) AS trend_customers,
            (SELECT list(units) FROM monthly) AS trend_units,
            (SELECT list(strftime('%Y-%m-%d', week_start)) FROM weekly) AS trend_week_labels,
            (SELECT list(revenue) FROM weekly) AS trend_week_revenue,
            (SELECT list(orders) FROM weekly) AS trend_week_orders,
            (SELECT list(profit) FROM weekly) AS trend_week_profit,
            (SELECT list(margin_pct) FROM weekly) AS trend_week_margin,
            (SELECT ref_date FROM ref) AS ref_date
        FROM summary
        LIMIT 1
    """

    summary_df = fact_store.execute_sql_df(summary_sql, params_rep, tag="salesreps.drilldown.summary")
    customers_df = _normalize_frame(_salesrep_customers_frame(scoped_sql, params_rep))
    products_df = _normalize_frame(_salesrep_products_frame(scoped_sql, params_rep))

    if summary_df.empty:
        return {
            "kpis": {},
            "trend": {"monthly": {"labels": [], "revenue": [], "orders": [], "profit": [], "margin_pct": []}, "weekly": {"labels": [], "revenue": [], "orders": [], "profit": [], "margin_pct": []}},
            "charts": {},
            "table": {"rows": [], "page": 1, "page_size": 0, "total": 0},
            "meta": {"page_id": "salesrep_drilldown", "entity_id": rep_id},
        }

    srow = summary_df.iloc[0]
    revenue = _clean_float(srow.get("revenue"))
    cost = _clean_optional(srow.get("cost"))
    profit = _clean_optional(srow.get("profit"))
    margin_pct = _clean_optional(srow.get("margin_pct"))
    orders = _clean_int(srow.get("orders"))
    customers = _clean_int(srow.get("customers"))
    units = _clean_float(srow.get("units"))
    weight_lb = _clean_float(srow.get("weight_lb"))
    asp = _clean_optional(srow.get("asp"))
    asp_lb = _clean_optional(srow.get("asp_lb"))
    rep_name = srow.get("rep_name") or rep_id
    cost_null_rows = _clean_int(srow.get("cost_null_rows"))
    total_rows = _clean_int(srow.get("total_rows"))
    cost_coverage_pct = ((1 - (cost_null_rows / total_rows)) * 100.0) if total_rows else None
    ref_date = pd.to_datetime(srow.get("ref_date"), errors="coerce")

    trend_labels = [str(x) for x in _to_list(srow.get("trend_labels"))]
    trend_revenue = [_clean_float(x, 0.0) for x in _to_list(srow.get("trend_revenue"))]
    trend_orders = [_clean_int(x, 0) for x in _to_list(srow.get("trend_orders"))]
    trend_profit = [_clean_optional(x) for x in _to_list(srow.get("trend_profit"))]
    trend_margin = [_clean_optional(x) for x in _to_list(srow.get("trend_margin"))]
    trend_customers = [_clean_int(x, 0) for x in _to_list(srow.get("trend_customers"))]
    trend_units = [_clean_float(x, 0.0) for x in _to_list(srow.get("trend_units"))]

    def _rolling(values: List[Any], window: int) -> List[float | None]:
        out: List[float | None] = []
        for idx in range(len(values)):
            segment = [v for v in values[max(0, idx - window + 1) : idx + 1] if v is not None]
            out.append((sum(segment) / len(segment)) if segment else None)
        return out

    trend_monthly = {
        "labels": trend_labels,
        "revenue": trend_revenue,
        "orders": trend_orders,
        "profit": trend_profit,
        "margin_pct": trend_margin,
        "customers": trend_customers,
        "units": trend_units,
        "rolling_revenue_3m": _rolling(trend_revenue, 3),
        "rolling_profit_3m": _rolling([_clean_optional(v) for v in trend_profit], 3),
    }

    trend_weekly = {
        "labels": [str(v) for v in _to_list(srow.get("trend_week_labels"))],
        "revenue": [_clean_float(v, 0.0) for v in _to_list(srow.get("trend_week_revenue"))],
        "orders": [_clean_int(v, 0) for v in _to_list(srow.get("trend_week_orders"))],
        "profit": [_clean_optional(v) for v in _to_list(srow.get("trend_week_profit"))],
        "margin_pct": [_clean_optional(v) for v in _to_list(srow.get("trend_week_margin"))],
    }
    trend_weekly["rolling_revenue_4w"] = _rolling(trend_weekly["revenue"], 4)

    customers_df = customers_df.copy()
    products_df = products_df.copy()

    if "revenue" in customers_df:
        customers_df = customers_df.sort_values(["revenue", "customer_id"], ascending=[False, True]).reset_index(drop=True)
    if "revenue" in products_df:
        products_df = products_df.sort_values(["revenue", "product_id"], ascending=[False, True]).reset_index(drop=True)

    total_customer_revenue = float(customers_df["revenue"].sum()) if (not customers_df.empty and "revenue" in customers_df) else 0.0
    top_customer_share = None
    top5_customer_share = None
    customer_hhi = None
    if total_customer_revenue > 0 and not customers_df.empty:
        shares = (customers_df["revenue"] / total_customer_revenue).astype(float)
        top_customer_share = float(shares.iloc[0]) if len(shares.index) else None
        top5_customer_share = float(shares.head(5).sum())
        customer_hhi = float((shares.pow(2).sum()))

    top_product_share = None
    if not products_df.empty and "revenue" in products_df:
        total_product_revenue = float(products_df["revenue"].sum())
        if total_product_revenue > 0:
            top_product_share = float(products_df["revenue"].max() / total_product_revenue)

    def _mom_fields(values: List[Any]) -> tuple[float | None, float | None]:
        if len(values) < 2:
            return None, None
        curr = _clean_optional(values[-1])
        prev = _clean_optional(values[-2])
        if curr is None or prev is None:
            return curr, None
        if prev == 0:
            return curr, None
        return curr, ((curr - prev) / abs(prev)) * 100.0

    _, revenue_mom_pct = _mom_fields(trend_revenue)
    _, profit_mom_pct = _mom_fields([_clean_optional(v) for v in trend_profit])
    margin_mom_pct = None
    if len(trend_margin) >= 2 and trend_margin[-1] is not None and trend_margin[-2] is not None:
        margin_mom_pct = float(trend_margin[-1]) - float(trend_margin[-2])
    active_customers_prev = trend_customers[-2] if len(trend_customers) >= 2 else None
    active_customers_curr = trend_customers[-1] if trend_customers else None
    active_customers_delta = (active_customers_curr - active_customers_prev) if (active_customers_curr is not None and active_customers_prev is not None) else None

    def _yoy(series_values: List[Any]) -> float | None:
        if not trend_labels:
            return None
        latest_label = trend_labels[-1]
        try:
            latest_dt = pd.to_datetime(f"{latest_label}-01", errors="coerce")
            if pd.isna(latest_dt):
                return None
            yoy_label = (latest_dt - pd.DateOffset(years=1)).strftime("%Y-%m")
            idx_map = {lbl: idx for idx, lbl in enumerate(trend_labels)}
            if yoy_label not in idx_map:
                return None
            curr = _clean_optional(series_values[-1])
            prev = _clean_optional(series_values[idx_map[yoy_label]])
            if curr is None or prev is None or prev == 0:
                return None
            return ((curr - prev) / abs(prev)) * 100.0
        except Exception:
            return None

    revenue_yoy_pct = _yoy(trend_revenue)
    profit_yoy_pct = _yoy([_clean_optional(v) for v in trend_profit])
    margin_yoy_pct = _yoy([_clean_optional(v) for v in trend_margin])

    customers_records = customers_df.to_dict(orient="records") if not customers_df.empty else []
    products_records = products_df.to_dict(orient="records") if not products_df.empty else []

    for row in customers_records:
        row["margin_pct"] = _clean_optional(row.get("margin_pct"))
        row["mom_revenue_delta"] = _clean_optional(row.get("mom_revenue_delta"))
        row["mom_revenue_pct"] = _clean_optional(row.get("mom_revenue_pct"))
        row["revenue"] = _clean_float(row.get("revenue"))
        row["profit"] = _clean_optional(row.get("profit"))
        row["orders"] = _clean_int(row.get("orders"))
        row["weight_lb"] = _clean_float(row.get("weight_lb"))
        row["asp_lb"] = _clean_optional(row.get("asp_lb"))
        row["last_order_date"] = str(row.get("last_order_date"))[:10] if row.get("last_order_date") is not None else None
        row["customer_id"] = row.get("customer_id")
        row["customer_name"] = row.get("customer_name") or row.get("customer_id")

    for row in products_records:
        row["margin_pct"] = _clean_optional(row.get("margin_pct"))
        row["mom_revenue_delta"] = _clean_optional(row.get("mom_revenue_delta"))
        row["mom_revenue_pct"] = _clean_optional(row.get("mom_revenue_pct"))
        row["price_change_pct"] = _clean_optional(row.get("price_change_pct"))
        row["revenue"] = _clean_float(row.get("revenue"))
        row["profit"] = _clean_optional(row.get("profit"))
        row["orders"] = _clean_int(row.get("orders"))
        row["weight_lb"] = _clean_float(row.get("weight_lb"))
        row["asp_lb"] = _clean_optional(row.get("asp_lb"))
        row["last_order_date"] = str(row.get("last_order_date"))[:10] if row.get("last_order_date") is not None else None
        row["product_id"] = row.get("product_id")
        row["product_name"] = row.get("product_name") or row.get("product_id")
        row["volatility"] = None

    gainers_customers = sorted(customers_records, key=lambda r: _clean_float(r.get("mom_revenue_delta")), reverse=True)[:10]
    decliners_customers = sorted(customers_records, key=lambda r: _clean_float(r.get("mom_revenue_delta")))[:10]
    gainers_products = sorted(products_records, key=lambda r: _clean_float(r.get("mom_revenue_delta")), reverse=True)[:10]
    decliners_products = sorted(products_records, key=lambda r: _clean_float(r.get("mom_revenue_delta")))[:10]

    at_risk_rows: List[Dict[str, Any]] = []
    if ref_date is not None:
        for row in customers_records:
            lod = pd.to_datetime(row.get("last_order_date"), errors="coerce")
            if pd.isna(lod):
                continue
            days_since_last = int((ref_date - lod).days)
            if days_since_last <= at_risk_days:
                continue
            row_out = dict(row)
            row_out["days_since_last_order"] = days_since_last
            row_out["prior_period_revenue"] = _clean_optional(row.get("revenue_prev_30"))
            at_risk_rows.append(row_out)
    at_risk_rows = sorted(
        at_risk_rows,
        key=lambda r: (_clean_float(r.get("prior_period_revenue")), _clean_float(r.get("revenue"))),
        reverse=True,
    )[:200]

    margin_risk_rows: List[Dict[str, Any]] = []
    for row in products_records:
        m = _clean_optional(row.get("margin_pct"))
        p = _clean_optional(row.get("profit"))
        rev = _clean_float(row.get("revenue"))
        if m is None and p is None:
            continue
        if (m is not None and m < RISK_MARGIN_THRESHOLD) or (p is not None and p < 0):
            leakage = None
            if m is not None:
                leakage = max(((RISK_MARGIN_THRESHOLD - m) / 100.0) * rev, 0.0)
            row_out = dict(row)
            row_out["leakage_to_target"] = leakage
            row_out["negative_margin_flag"] = 1 if (p is not None and p < 0) else 0
            margin_risk_rows.append(row_out)
    margin_risk_rows = sorted(
        margin_risk_rows,
        key=lambda r: (_clean_float(r.get("leakage_to_target")), _clean_float(r.get("revenue"))),
        reverse=True,
    )[:200]

    below_target_count = sum(1 for r in margin_risk_rows if _clean_optional(r.get("margin_pct")) is not None and _clean_float(r.get("margin_pct")) < RISK_MARGIN_THRESHOLD)
    negative_margin_count = sum(1 for r in margin_risk_rows if _clean_int(r.get("negative_margin_flag")) == 1)
    below_target_revenue = sum(_clean_float(r.get("revenue")) for r in margin_risk_rows if _clean_optional(r.get("margin_pct")) is not None and _clean_float(r.get("margin_pct")) < RISK_MARGIN_THRESHOLD)
    negative_margin_revenue = sum(_clean_float(r.get("revenue")) for r in margin_risk_rows if _clean_int(r.get("negative_margin_flag")) == 1)

    rev_prev = trend_revenue[-2] if len(trend_revenue) >= 2 else None
    rev_curr = trend_revenue[-1] if len(trend_revenue) >= 1 else None
    units_prev = trend_units[-2] if len(trend_units) >= 2 else None
    units_curr = trend_units[-1] if len(trend_units) >= 1 else None
    price_impact = None
    volume_impact = None
    mix_impact = None
    total_change = None
    if (
        rev_prev is not None
        and rev_curr is not None
        and units_prev is not None
        and units_curr is not None
        and units_prev > 0
    ):
        asp_prev = rev_prev / units_prev if units_prev else None
        asp_curr = rev_curr / units_curr if units_curr else None
        if asp_prev is not None and asp_curr is not None:
            price_impact = (asp_curr - asp_prev) * units_prev
            volume_impact = (units_curr - units_prev) * asp_prev
            total_change = rev_curr - rev_prev
            mix_impact = total_change - price_impact - volume_impact

    top_customer_drivers = sorted(customers_records, key=lambda r: abs(_clean_float(r.get("mom_revenue_delta"))), reverse=True)[:3]
    top_product_drivers = sorted(products_records, key=lambda r: abs(_clean_float(r.get("mom_revenue_delta"))), reverse=True)[:3]
    driver_names = [d.get("customer_name") or d.get("customer_id") for d in top_customer_drivers] + [d.get("product_name") or d.get("product_id") for d in top_product_drivers]
    driver_names = [str(x) for x in driver_names if x][:3]
    if revenue_mom_pct is None:
        what_changed = "MoM change unavailable for this filter window."
    else:
        direction = "up" if revenue_mom_pct >= 0 else "down"
        what_changed = f"Revenue {direction} {abs(revenue_mom_pct):.1f}% MoM"
        if driver_names:
            what_changed += f" driven by {', '.join(driver_names)}."
        else:
            what_changed += "."

    risk_flags = [
        {
            "key": "top_customer_concentration",
            "severity": "high" if (_clean_float(top_customer_share) > 0.25) else "ok",
            "count": 1 if (_clean_float(top_customer_share) > 0.25) else 0,
            "label": "Top customer share > 25%",
        },
        {
            "key": "margin_below_target_skus",
            "severity": "medium" if below_target_count > 0 else "ok",
            "count": below_target_count,
            "label": f"SKUs below {RISK_MARGIN_THRESHOLD:.0f}% margin",
        },
        {
            "key": "negative_margin_skus",
            "severity": "high" if negative_margin_count > 0 else "ok",
            "count": negative_margin_count,
            "label": "Negative margin SKUs",
        },
    ]

    manifest_meta = fact_store.get_meta() or {}
    last_refresh = (
        manifest_meta.get("last_refresh_utc")
        or manifest_meta.get("watermark_dt")
        or manifest_meta.get("watermark")
        or None
    )

    kpis = {
        "rep_id": rep_id,
        "rep_name": rep_name,
        "revenue": revenue,
        "cost": cost,
        "profit": profit,
        "margin_pct": margin_pct,
        "orders": orders,
        "customers": customers,
        "units": units,
        "weight_lb": weight_lb,
        "asp": asp,
        "asp_lb": asp_lb,
        "orders_last_30": _clean_int(srow.get("orders_last_30")),
        "orders_last_90": _clean_int(srow.get("orders_last_90")),
        "revenue_last_30": _clean_float(srow.get("revenue_last_30")),
        "revenue_last_90": _clean_float(srow.get("revenue_last_90")),
        "momentum_pct": None,
        "profit_last_30": None
        if srow.get("cost_last_30") is None
        else _clean_float(srow.get("revenue_last_30")) - _clean_float(srow.get("cost_last_30")),
        "profit_last_90": None
        if srow.get("cost_last_90") is None
        else _clean_float(srow.get("revenue_last_90")) - _clean_float(srow.get("cost_last_90")),
        "days_since_last_order": srow.get("days_since_last"),
        "top_customer_share": _clean_optional(top_customer_share),
        "top5_customer_share": _clean_optional(top5_customer_share),
        "top_product_share": _clean_optional(top_product_share),
        "customer_hhi": _clean_optional(customer_hhi),
        "cost_coverage_pct": cost_coverage_pct,
        "revenue_mom_pct": revenue_mom_pct,
        "profit_mom_pct": profit_mom_pct,
        "margin_mom_pct": margin_mom_pct,
        "revenue_yoy_pct": revenue_yoy_pct,
        "profit_yoy_pct": profit_yoy_pct,
        "margin_yoy_pct": margin_yoy_pct,
        "active_customers_curr": active_customers_curr,
        "active_customers_prev": active_customers_prev,
        "active_customers_delta": active_customers_delta,
        "below_target_margin_skus": below_target_count,
        "below_target_margin_revenue": below_target_revenue,
        "negative_margin_skus": negative_margin_count,
        "negative_margin_revenue": negative_margin_revenue,
        "last_refresh": last_refresh,
        "what_changed": what_changed,
        "start": start_iso,
        "end": end_iso,
    }
    try:
        rev_prev_90 = _clean_float(srow.get("revenue_prev_90"))
        if rev_prev_90 > 0:
            kpis["momentum_pct"] = (kpis["revenue_last_90"] - rev_prev_90) / rev_prev_90 * 100.0
    except Exception:
        pass

    table_rows = [
        {
            "key": c.get("customer_id"),
            "label": c.get("customer_name") or c.get("customer_id"),
            "customer_id": c.get("customer_id"),
            "customer_name": c.get("customer_name") or c.get("customer_id"),
            "revenue": _clean_float(c.get("revenue")),
            "profit": _clean_optional(c.get("profit")),
            "margin_pct": _clean_optional(c.get("margin_pct")),
            "orders": _clean_int(c.get("orders")),
            "weight_lb": _clean_float(c.get("weight_lb")),
            "asp_lb": _clean_optional(c.get("asp_lb")),
            "mom_revenue_delta": _clean_optional(c.get("mom_revenue_delta")),
            "mom_revenue_pct": _clean_optional(c.get("mom_revenue_pct")),
            "last_order_date": c.get("last_order_date"),
        }
        for c in customers_records[:100]
    ]

    payload = {
        "kpis": kpis,
        "trend": {
            "monthly": trend_monthly,
            "weekly": trend_weekly,
            "default_grain": "monthly",
        },
        "table": {"rows": table_rows, "page": 1, "page_size": len(table_rows), "total": len(table_rows)},
        "tables": {
            "customers": customers_records[:250],
            "products": products_records[:250],
            "at_risk_customers": at_risk_rows,
            "margin_risk_products": margin_risk_rows,
            "movers_customers": {
                "gainers": gainers_customers,
                "decliners": decliners_customers,
            },
            "movers_products": {
                "gainers": gainers_products,
                "decliners": decliners_products,
            },
        },
        "decomposition": {
            "price_impact": price_impact,
            "volume_impact": volume_impact,
            "mix_impact": mix_impact,
            "total_change": total_change,
            "methodology": "Approximation using latest vs prior month ASP and units.",
        },
        "charts": {
            "trend": trend_monthly,
            "trend_weekly": trend_weekly,
            "top_customers": customers_records[:20],
            "top_customers_profit": sorted(customers_records, key=lambda r: (_clean_float(r.get("profit")), _clean_float(r.get("revenue"))), reverse=True)[:20],
            "top_products": products_records[:20],
            "worst_products": sorted(products_records, key=lambda r: (_clean_float(r.get("profit")), _clean_float(r.get("revenue"))))[:20],
            "mix": products_records[:20],
            "concentration": {
                "top_customer_share": _clean_optional(top_customer_share),
                "top5_customer_share": _clean_optional(top5_customer_share),
                "customer_hhi": _clean_optional(customer_hhi),
            },
        },
        "risk_flags": risk_flags,
        "insights": {
            "what_changed": what_changed,
            "drivers": {
                "customers": top_customer_drivers,
                "products": top_product_drivers,
            },
        },
        "meta": {
            "page_id": "salesrep_drilldown",
            "entity_id": rep_id,
            "entity_label": rep_name,
            "window_start": start_iso,
            "window_end": end_iso,
            "last_refresh": last_refresh,
            "risk_thresholds": {
                "top_customer_share": 0.25,
                "margin_pct": RISK_MARGIN_THRESHOLD,
                "at_risk_days": at_risk_days,
            },
            "dataset_version": fact_store.cache_buster(),
        },
    }
    return payload


def build_salesreps_export_frame(filters: Any, scope: Dict[str, Any], args: Any):
    cols = fact_store.list_columns()
    cols_map = _required_columns(cols)
    missing = [k for k in ("date", "revenue", "order", "customer") if not cols_map.get(k)]
    if missing:
        raise RuntimeError(f"Required columns missing for salesreps export: {', '.join(missing)}")

    rep_key_expr, rep_name_expr = _rep_exprs(cols)
    where_sql, params, _, _ = fact_store.build_where_clause(
        filters, cols, scope, apply_default_window=True
    )
    base_sql = _scoped_sql(cols_map, where_sql, rep_key_expr, rep_name_expr)
    if not base_sql:
        raise RuntimeError("Salesreps export base query could not be built")

    rollup_df = fact_store.execute_sql_df(_rollup_sql(base_sql), params, tag="salesreps.export.rollup")
    rollup_df = _normalize_frame(rollup_df)
    if rollup_df.empty:
        return rollup_df

    search_term = _search_term(args)
    sort_by, sort_dir = _sort_params(args)

    work = _apply_search_filter(rollup_df, search_term)
    work = _sort_rollup_df(work, sort_by, sort_dir)
    if work is None or work.empty:
        return work

    work = work.copy()
    for src, dst in (
        ("margin_pct", "margin_pct_export"),
        ("top_customer_share", "top_customer_share_pct_export"),
        ("top_5_customer_share", "top_5_customer_share_pct_export"),
        ("mom_revenue_pct", "mom_revenue_pct_export"),
        ("mom_profit_pct", "mom_profit_pct_export"),
    ):
        if src in work.columns:
            if src in {"top_customer_share", "top_5_customer_share"}:
                work[dst] = work[src] * 100.0
            else:
                work[dst] = work[src]
        else:
            work[dst] = None

    ordered = [
        ("rep_key", "Rep ID"),
        ("rep_name", "Rep Name"),
        ("revenue", "Revenue"),
        ("profit", "Profit"),
        ("margin_pct_export", "Margin %"),
        ("orders", "Orders"),
        ("customers", "Customers"),
        ("weight_lb", "Weight (lb)"),
        ("units", "Units"),
        ("asp_lb", "ASP/LB"),
        ("asp", "ASP"),
        ("top_customer_share_pct_export", "Top Customer %"),
        ("top_customer_name", "Top Customer Name"),
        ("top_customer_revenue", "Top Customer Revenue"),
        ("mom_revenue_pct_export", "MoM Revenue %"),
        ("mom_profit_pct_export", "MoM Profit %"),
        ("top_5_customer_share_pct_export", "Top 5 Customer %"),
        ("customer_hhi", "Concentration HHI"),
    ]
    export_df = work.reindex(columns=[src for src, _ in ordered]).rename(columns={src: dst for src, dst in ordered})
    return export_df


def build_salesrep_history_frame(rep_id: str, filters: Any, scope: Dict[str, Any], args: Any):
    cols = fact_store.list_columns()
    cols_map = _required_columns(cols)
    missing = [k for k in ("date", "revenue", "order", "customer") if not cols_map.get(k)]
    if missing:
        raise RuntimeError(f"Required columns missing for salesrep history: {', '.join(missing)}")

    rep_key_expr, rep_name_expr = _rep_exprs(cols)
    base_where, params, _, _ = fact_store.build_where_clause(
        filters, cols, scope, apply_default_window=True
    )
    rep_match_sql = f"({rep_key_expr} = ? OR {rep_name_expr} = ?)"
    where_sql = f"({base_where}) AND {rep_match_sql}"
    params_rep = list(params) + [rep_id, rep_id]
    scoped_sql = _scoped_sql(cols_map, where_sql, rep_key_expr, rep_name_expr)
    if not scoped_sql:
        raise RuntimeError("Salesrep history base query could not be built")

    history_sql = f"""
        WITH scoped AS (
            {scoped_sql}
        )
        SELECT
            rep_key,
            rep_name,
            order_date,
            order_id,
            customer_id,
            customer_name,
            product_id,
            product_name,
            revenue,
            cost,
            missing_packs,
            CASE WHEN cost IS NULL THEN NULL ELSE revenue - cost END AS profit,
            units,
            weight_lb
        FROM scoped
        ORDER BY order_date DESC, order_id
    """
    return fact_store.execute_sql_df(history_sql, params_rep, tag="salesreps.drilldown.history")


def _salesrep_export_context(rep_id: str, filters: Any, scope: Dict[str, Any]) -> tuple[str, list[Any], str | None, str | None]:
    cols = fact_store.list_columns()
    cols_map = _required_columns(cols)
    missing = [k for k in ("date", "revenue", "order", "customer") if not cols_map.get(k)]
    if missing:
        raise RuntimeError(f"Required columns missing for salesrep export: {', '.join(missing)}")

    rep_key_expr, rep_name_expr = _rep_exprs(cols)
    base_where, params, start_iso, end_iso = fact_store.build_where_clause(
        filters, cols, scope, apply_default_window=True
    )
    rep_match_sql = f"({rep_key_expr} = ? OR {rep_name_expr} = ?)"
    where_sql = f"({base_where}) AND {rep_match_sql}"
    params_rep = list(params) + [rep_id, rep_id]
    scoped_sql = _scoped_sql(cols_map, where_sql, rep_key_expr, rep_name_expr)
    if not scoped_sql:
        raise RuntimeError("Salesrep export base query could not be built")
    return scoped_sql, params_rep, start_iso, end_iso


def _salesrep_summary_frame(scoped_sql: str, params_rep: list[Any]) -> Any:
    sql = f"""
        WITH scoped AS (
            {scoped_sql}
        )
        SELECT
            MIN(rep_name) AS rep_name,
            SUM(revenue) AS revenue,
            SUM(cost) AS cost,
            CASE WHEN SUM(cost) IS NULL THEN NULL ELSE SUM(revenue) - SUM(cost) END AS profit,
            CASE WHEN SUM(revenue) > 0 AND SUM(cost) IS NOT NULL THEN (SUM(revenue) - SUM(cost)) / SUM(revenue) * 100 ELSE NULL END AS margin_pct,
            COUNT(DISTINCT order_id) AS orders,
            COUNT(DISTINCT customer_id) AS customers,
            COUNT(DISTINCT product_id) AS products,
            SUM(units) AS units,
            SUM(weight_lb) AS weight_lb,
            CASE WHEN SUM(units) > 0 THEN SUM(revenue) / NULLIF(SUM(units), 0) ELSE NULL END AS asp,
            CASE WHEN SUM(weight_lb) > 0 THEN SUM(revenue) / NULLIF(SUM(weight_lb), 0) ELSE NULL END AS asp_lb,
            MIN(order_date) AS first_order_date,
            MAX(order_date) AS last_order_date,
            SUM(CASE WHEN cost IS NULL THEN 1 ELSE 0 END) AS cost_null_rows,
            COUNT(*) AS total_rows
        FROM scoped
    """
    return fact_store.execute_sql_df(sql, params_rep, tag="salesreps.export.summary")


def _salesrep_trend_frame(scoped_sql: str, params_rep: list[Any]) -> Any:
    sql = f"""
        WITH scoped AS (
            {scoped_sql}
        )
        SELECT
            strftime('%Y-%m', order_date) AS month,
            SUM(revenue) AS revenue,
            CASE WHEN SUM(cost) IS NULL THEN NULL ELSE SUM(revenue) - SUM(cost) END AS profit,
            CASE WHEN SUM(revenue) > 0 AND SUM(cost) IS NOT NULL THEN (SUM(revenue) - SUM(cost)) / SUM(revenue) * 100 ELSE NULL END AS margin_pct,
            COUNT(DISTINCT order_id) AS orders,
            COUNT(DISTINCT customer_id) AS customers,
            COUNT(DISTINCT product_id) AS products,
            SUM(units) AS units,
            SUM(weight_lb) AS weight_lb
        FROM scoped
        GROUP BY 1
        ORDER BY 1
    """
    return fact_store.execute_sql_df(sql, params_rep, tag="salesreps.export.trend")


def _salesrep_customers_frame(scoped_sql: str, params_rep: list[Any]) -> Any:
    sql = f"""
        WITH scoped AS (
            {scoped_sql}
        ),
        ref AS (
            SELECT COALESCE(MAX(order_date), CURRENT_DATE) AS ref_date FROM scoped
        )
        SELECT
            customer_id,
            ANY_VALUE(customer_name) AS customer_name,
            SUM(revenue) AS revenue,
            CASE WHEN SUM(cost) IS NULL THEN NULL ELSE SUM(revenue) - SUM(cost) END AS profit,
            CASE WHEN SUM(revenue) > 0 AND SUM(cost) IS NOT NULL THEN (SUM(revenue) - SUM(cost)) / SUM(revenue) * 100 ELSE NULL END AS margin_pct,
            COUNT(DISTINCT order_id) AS orders,
            COUNT(DISTINCT product_id) AS products,
            SUM(units) AS units,
            SUM(weight_lb) AS weight_lb,
            CASE WHEN SUM(weight_lb) > 0 THEN SUM(revenue) / NULLIF(SUM(weight_lb), 0) ELSE NULL END AS asp_lb,
            MAX(order_date) AS last_order_date,
            SUM(CASE WHEN order_date > ref.ref_date - INTERVAL 30 DAY THEN revenue ELSE 0 END) AS revenue_last_30,
            SUM(CASE WHEN order_date <= ref.ref_date - INTERVAL 30 DAY AND order_date > ref.ref_date - INTERVAL 60 DAY THEN revenue ELSE 0 END) AS revenue_prev_30,
            (
                SUM(CASE WHEN order_date > ref.ref_date - INTERVAL 30 DAY THEN revenue ELSE 0 END)
                - SUM(CASE WHEN order_date <= ref.ref_date - INTERVAL 30 DAY AND order_date > ref.ref_date - INTERVAL 60 DAY THEN revenue ELSE 0 END)
            ) AS mom_revenue_delta,
            CASE
                WHEN SUM(CASE WHEN order_date <= ref.ref_date - INTERVAL 30 DAY AND order_date > ref.ref_date - INTERVAL 60 DAY THEN revenue ELSE 0 END) > 0
                THEN (
                    SUM(CASE WHEN order_date > ref.ref_date - INTERVAL 30 DAY THEN revenue ELSE 0 END)
                    - SUM(CASE WHEN order_date <= ref.ref_date - INTERVAL 30 DAY AND order_date > ref.ref_date - INTERVAL 60 DAY THEN revenue ELSE 0 END)
                )
                / NULLIF(SUM(CASE WHEN order_date <= ref.ref_date - INTERVAL 30 DAY AND order_date > ref.ref_date - INTERVAL 60 DAY THEN revenue ELSE 0 END), 0) * 100
                ELSE NULL
            END AS mom_revenue_pct
        FROM scoped, ref
        WHERE customer_id IS NOT NULL AND customer_id <> ''
        GROUP BY 1
        ORDER BY revenue DESC NULLS LAST, customer_id
    """
    return fact_store.execute_sql_df(sql, params_rep, tag="salesreps.export.customers")


def _salesrep_products_frame(scoped_sql: str, params_rep: list[Any]) -> Any:
    sql = f"""
        WITH scoped AS (
            {scoped_sql}
        ),
        ref AS (
            SELECT COALESCE(MAX(order_date), CURRENT_DATE) AS ref_date FROM scoped
        )
        SELECT
            product_id,
            ANY_VALUE(product_name) AS product_name,
            SUM(revenue) AS revenue,
            CASE WHEN SUM(cost) IS NULL THEN NULL ELSE SUM(revenue) - SUM(cost) END AS profit,
            CASE WHEN SUM(revenue) > 0 AND SUM(cost) IS NOT NULL THEN (SUM(revenue) - SUM(cost)) / SUM(revenue) * 100 ELSE NULL END AS margin_pct,
            COUNT(DISTINCT order_id) AS orders,
            COUNT(DISTINCT customer_id) AS customers,
            SUM(units) AS units,
            SUM(weight_lb) AS weight_lb,
            CASE WHEN SUM(weight_lb) > 0 THEN SUM(revenue) / NULLIF(SUM(weight_lb), 0) ELSE NULL END AS asp_lb,
            MAX(order_date) AS last_order_date,
            SUM(CASE WHEN order_date > ref.ref_date - INTERVAL 30 DAY THEN revenue ELSE 0 END) AS revenue_last_30,
            SUM(CASE WHEN order_date <= ref.ref_date - INTERVAL 30 DAY AND order_date > ref.ref_date - INTERVAL 60 DAY THEN revenue ELSE 0 END) AS revenue_prev_30,
            (
                SUM(CASE WHEN order_date > ref.ref_date - INTERVAL 30 DAY THEN revenue ELSE 0 END)
                - SUM(CASE WHEN order_date <= ref.ref_date - INTERVAL 30 DAY AND order_date > ref.ref_date - INTERVAL 60 DAY THEN revenue ELSE 0 END)
            ) AS mom_revenue_delta,
            CASE
                WHEN SUM(CASE WHEN order_date <= ref.ref_date - INTERVAL 30 DAY AND order_date > ref.ref_date - INTERVAL 60 DAY THEN revenue ELSE 0 END) > 0
                THEN (
                    SUM(CASE WHEN order_date > ref.ref_date - INTERVAL 30 DAY THEN revenue ELSE 0 END)
                    - SUM(CASE WHEN order_date <= ref.ref_date - INTERVAL 30 DAY AND order_date > ref.ref_date - INTERVAL 60 DAY THEN revenue ELSE 0 END)
                )
                / NULLIF(SUM(CASE WHEN order_date <= ref.ref_date - INTERVAL 30 DAY AND order_date > ref.ref_date - INTERVAL 60 DAY THEN revenue ELSE 0 END), 0) * 100
                ELSE NULL
            END AS mom_revenue_pct,
            CASE WHEN SUM(weight_lb) FILTER (WHERE order_date > ref.ref_date - INTERVAL 30 DAY) > 0
                 THEN SUM(revenue) FILTER (WHERE order_date > ref.ref_date - INTERVAL 30 DAY)
                      / NULLIF(SUM(weight_lb) FILTER (WHERE order_date > ref.ref_date - INTERVAL 30 DAY), 0)
                 ELSE NULL
            END AS asp_lb_last_30,
            CASE WHEN SUM(weight_lb) FILTER (WHERE order_date <= ref.ref_date - INTERVAL 30 DAY AND order_date > ref.ref_date - INTERVAL 60 DAY) > 0
                 THEN SUM(revenue) FILTER (WHERE order_date <= ref.ref_date - INTERVAL 30 DAY AND order_date > ref.ref_date - INTERVAL 60 DAY)
                      / NULLIF(SUM(weight_lb) FILTER (WHERE order_date <= ref.ref_date - INTERVAL 30 DAY AND order_date > ref.ref_date - INTERVAL 60 DAY), 0)
                 ELSE NULL
            END AS asp_lb_prev_30,
            CASE
                WHEN SUM(weight_lb) FILTER (WHERE order_date <= ref.ref_date - INTERVAL 30 DAY AND order_date > ref.ref_date - INTERVAL 60 DAY) > 0
                     AND SUM(revenue) FILTER (WHERE order_date <= ref.ref_date - INTERVAL 30 DAY AND order_date > ref.ref_date - INTERVAL 60 DAY) > 0
                THEN (
                    (
                        SUM(revenue) FILTER (WHERE order_date > ref.ref_date - INTERVAL 30 DAY)
                        / NULLIF(SUM(weight_lb) FILTER (WHERE order_date > ref.ref_date - INTERVAL 30 DAY), 0)
                    ) - (
                        SUM(revenue) FILTER (WHERE order_date <= ref.ref_date - INTERVAL 30 DAY AND order_date > ref.ref_date - INTERVAL 60 DAY)
                        / NULLIF(SUM(weight_lb) FILTER (WHERE order_date <= ref.ref_date - INTERVAL 30 DAY AND order_date > ref.ref_date - INTERVAL 60 DAY), 0)
                    )
                ) / NULLIF(
                    SUM(revenue) FILTER (WHERE order_date <= ref.ref_date - INTERVAL 30 DAY AND order_date > ref.ref_date - INTERVAL 60 DAY)
                    / NULLIF(SUM(weight_lb) FILTER (WHERE order_date <= ref.ref_date - INTERVAL 30 DAY AND order_date > ref.ref_date - INTERVAL 60 DAY), 0),
                    0
                ) * 100
                ELSE NULL
            END AS price_change_pct
        FROM scoped, ref
        WHERE product_id IS NOT NULL AND product_id <> ''
        GROUP BY 1
        ORDER BY revenue DESC NULLS LAST, product_id
    """
    return fact_store.execute_sql_df(sql, params_rep, tag="salesreps.export.products")


def _salesrep_movers_customers_frame(scoped_sql: str, params_rep: list[Any]) -> Any:
    sql = f"""
        WITH scoped AS (
            {scoped_sql}
        ),
        ref AS (
            SELECT COALESCE(MAX(order_date), CURRENT_DATE) AS ref_date FROM scoped
        ),
        customer_rollup AS (
            SELECT
                customer_id,
                ANY_VALUE(customer_name) AS customer_name,
                SUM(CASE WHEN order_date > ref.ref_date - INTERVAL 30 DAY THEN revenue ELSE 0 END) AS revenue_last_30,
                SUM(CASE WHEN order_date <= ref.ref_date - INTERVAL 30 DAY AND order_date > ref.ref_date - INTERVAL 60 DAY THEN revenue ELSE 0 END) AS revenue_prev_30
            FROM scoped, ref
            WHERE customer_id IS NOT NULL AND customer_id <> ''
            GROUP BY 1
        )
        SELECT
            customer_id,
            customer_name,
            revenue_last_30,
            revenue_prev_30,
            revenue_last_30 - revenue_prev_30 AS delta_revenue,
            CASE WHEN revenue_prev_30 > 0 THEN (revenue_last_30 - revenue_prev_30) / NULLIF(revenue_prev_30, 0) * 100 ELSE NULL END AS delta_revenue_pct
        FROM customer_rollup
        WHERE revenue_last_30 <> 0 OR revenue_prev_30 <> 0
        ORDER BY delta_revenue DESC NULLS LAST, customer_id
    """
    return fact_store.execute_sql_df(sql, params_rep, tag="salesreps.export.movers_customers")


def _salesrep_movers_products_frame(scoped_sql: str, params_rep: list[Any]) -> Any:
    sql = f"""
        WITH scoped AS (
            {scoped_sql}
        ),
        ref AS (
            SELECT COALESCE(MAX(order_date), CURRENT_DATE) AS ref_date FROM scoped
        ),
        product_rollup AS (
            SELECT
                product_id,
                ANY_VALUE(product_name) AS product_name,
                SUM(CASE WHEN order_date > ref.ref_date - INTERVAL 30 DAY THEN revenue ELSE 0 END) AS revenue_last_30,
                SUM(CASE WHEN order_date <= ref.ref_date - INTERVAL 30 DAY AND order_date > ref.ref_date - INTERVAL 60 DAY THEN revenue ELSE 0 END) AS revenue_prev_30
            FROM scoped, ref
            WHERE product_id IS NOT NULL AND product_id <> ''
            GROUP BY 1
        )
        SELECT
            product_id,
            product_name,
            revenue_last_30,
            revenue_prev_30,
            revenue_last_30 - revenue_prev_30 AS delta_revenue,
            CASE WHEN revenue_prev_30 > 0 THEN (revenue_last_30 - revenue_prev_30) / NULLIF(revenue_prev_30, 0) * 100 ELSE NULL END AS delta_revenue_pct
        FROM product_rollup
        WHERE revenue_last_30 <> 0 OR revenue_prev_30 <> 0
        ORDER BY delta_revenue DESC NULLS LAST, product_id
    """
    return fact_store.execute_sql_df(sql, params_rep, tag="salesreps.export.movers_products")


def _salesrep_margin_risk_frame(scoped_sql: str, params_rep: list[Any], target_margin_pct: float = RISK_MARGIN_THRESHOLD) -> Any:
    sql = f"""
        WITH scoped AS (
            {scoped_sql}
        ),
        product_rollup AS (
            SELECT
                product_id,
                ANY_VALUE(product_name) AS product_name,
                SUM(revenue) AS revenue,
                CASE WHEN SUM(cost) IS NULL THEN NULL ELSE SUM(revenue) - SUM(cost) END AS profit,
                CASE WHEN SUM(revenue) > 0 AND SUM(cost) IS NOT NULL THEN (SUM(revenue) - SUM(cost)) / SUM(revenue) * 100 ELSE NULL END AS margin_pct,
                COUNT(DISTINCT order_id) AS orders,
                SUM(weight_lb) AS weight_lb,
                CASE WHEN SUM(weight_lb) > 0 THEN SUM(revenue) / NULLIF(SUM(weight_lb), 0) ELSE NULL END AS asp_lb
            FROM scoped
            WHERE product_id IS NOT NULL AND product_id <> ''
            GROUP BY 1
        )
        SELECT
            product_id,
            product_name,
            revenue,
            profit,
            margin_pct,
            orders,
            weight_lb,
            asp_lb,
            CASE
                WHEN margin_pct IS NULL THEN NULL
                WHEN margin_pct < {float(target_margin_pct)} THEN ({float(target_margin_pct)} - margin_pct) / 100.0 * revenue
                ELSE 0
            END AS leakage_to_target,
            CASE WHEN profit IS NOT NULL AND profit < 0 THEN 1 ELSE 0 END AS negative_margin_flag
        FROM product_rollup
        WHERE (margin_pct IS NOT NULL AND margin_pct < {float(target_margin_pct)}) OR (profit IS NOT NULL AND profit < 0)
        ORDER BY leakage_to_target DESC NULLS LAST, product_id
    """
    return fact_store.execute_sql_df(sql, params_rep, tag="salesreps.export.margin_risk")


def _salesrep_at_risk_customers_frame(
    scoped_sql: str, params_rep: list[Any], inactivity_days: int = 45
) -> Any:
    inactivity_days = max(7, min(int(inactivity_days), 365))
    sql = f"""
        WITH scoped AS (
            {scoped_sql}
        ),
        ref AS (
            SELECT COALESCE(MAX(order_date), CURRENT_DATE) AS ref_date FROM scoped
        ),
        customer_rollup AS (
            SELECT
                customer_id,
                ANY_VALUE(customer_name) AS customer_name,
                MAX(order_date) AS last_order_date,
                SUM(revenue) AS revenue,
                SUM(CASE WHEN order_date <= ref.ref_date - INTERVAL 90 DAY AND order_date > ref.ref_date - INTERVAL 180 DAY THEN revenue ELSE 0 END) AS prior_period_revenue,
                COUNT(DISTINCT order_id) AS orders
            FROM scoped, ref
            WHERE customer_id IS NOT NULL AND customer_id <> ''
            GROUP BY 1
        )
        SELECT
            customer_id,
            customer_name,
            last_order_date,
            DATE_DIFF('day', last_order_date, (SELECT ref_date FROM ref)) AS days_since_last_order,
            revenue,
            prior_period_revenue,
            orders
        FROM customer_rollup
        WHERE last_order_date < (SELECT ref_date FROM ref) - INTERVAL {inactivity_days} DAY
        ORDER BY prior_period_revenue DESC NULLS LAST, revenue DESC NULLS LAST, customer_id
    """
    return fact_store.execute_sql_df(sql, params_rep, tag="salesreps.export.at_risk")


def _salesrep_history_frame(scoped_sql: str, params_rep: list[Any]) -> Any:
    sql = f"""
        WITH scoped AS (
            {scoped_sql}
        )
        SELECT
            rep_key,
            rep_name,
            order_date,
            order_id,
            customer_id,
            customer_name,
            product_id,
            product_name,
            revenue,
            cost,
            CASE WHEN cost IS NULL THEN NULL ELSE revenue - cost END AS profit,
            units,
            weight_lb,
            missing_packs
        FROM scoped
        ORDER BY order_date DESC, order_id
    """
    return fact_store.execute_sql_df(sql, params_rep, tag="salesreps.export.history")


def _salesrep_mix_frame(products_df: Any) -> Any:
    if products_df is None or products_df.empty:
        return products_df
    mix = products_df.copy()
    revenue_series = mix.get("revenue")
    total_revenue = float(revenue_series.sum()) if revenue_series is not None else 0.0
    if total_revenue > 0:
        mix["share_pct"] = (mix["revenue"] / total_revenue) * 100.0
    else:
        mix["share_pct"] = None
    return mix


def _salesrep_metadata_frame(
    rep_id: str,
    summary_df: Any,
    filters: Any,
    dataset_version: str,
    export_type: str,
) -> pd.DataFrame:
    rep_name = rep_id
    try:
        if summary_df is not None and not summary_df.empty:
            rep_name = str(summary_df.iloc[0].get("rep_name") or rep_id)
    except Exception:
        rep_name = rep_id
    start = getattr(filters, "start", None)
    end = getattr(filters, "end", None)
    generated_at = pd.Timestamp.utcnow().isoformat()
    return pd.DataFrame(
        [
            {"key": "rep_id", "value": rep_id},
            {"key": "rep_name", "value": rep_name},
            {"key": "export_type", "value": export_type},
            {"key": "window_start", "value": str(start) if start is not None else ""},
            {"key": "window_end", "value": str(end) if end is not None else ""},
            {"key": "generated_at_utc", "value": generated_at},
            {"key": "dataset_version", "value": str(dataset_version or "")},
            {"key": "filters_json", "value": filters_service.canonical_json(filters)},
        ]
    )


def build_salesrep_export_metadata_frame(
    rep_id: str,
    filters: Any,
    scope: Dict[str, Any],
    export_type: str,
):
    scoped_sql, params_rep, _, _ = _salesrep_export_context(rep_id, filters, scope)
    summary_df = _salesrep_summary_frame(scoped_sql, params_rep)
    return _salesrep_metadata_frame(
        rep_id=rep_id,
        summary_df=summary_df if summary_df is not None else pd.DataFrame(),
        filters=filters,
        dataset_version=fact_store.cache_buster(),
        export_type=export_type,
    )


def build_salesrep_export_dataset(rep_id: str, filters: Any, scope: Dict[str, Any], args: Any, dataset: str):
    token = str(dataset or "all").strip().lower()
    aliases = {
        "customer": "customers",
        "cust": "customers",
        "product": "products",
        "prod": "products",
        "product_mix": "mix",
        "orders": "history",
        "summary_all": "summary",
        "movers_customer": "movers_customers",
        "movers_product": "movers_products",
        "margin_leakage": "margin_risk",
        "risk_margin": "margin_risk",
        "risk_at_risk": "at_risk",
        "atrisk": "at_risk",
    }
    token = aliases.get(token, token)
    scoped_sql, params_rep, _, _ = _salesrep_export_context(rep_id, filters, scope)
    inactivity_days = _clean_int(args.get("at_risk_days") if hasattr(args, "get") else None, 45)

    if token == "summary":
        return _salesrep_summary_frame(scoped_sql, params_rep)
    if token == "trend":
        return _salesrep_trend_frame(scoped_sql, params_rep)
    if token == "customers":
        return _salesrep_customers_frame(scoped_sql, params_rep)
    if token == "products":
        return _salesrep_products_frame(scoped_sql, params_rep)
    if token == "mix":
        products_df = _salesrep_products_frame(scoped_sql, params_rep)
        return _salesrep_mix_frame(products_df)
    if token in {"history", "all_history"}:
        return _salesrep_history_frame(scoped_sql, params_rep)
    if token == "movers_customers":
        return _salesrep_movers_customers_frame(scoped_sql, params_rep)
    if token == "movers_products":
        return _salesrep_movers_products_frame(scoped_sql, params_rep)
    if token == "margin_risk":
        return _salesrep_margin_risk_frame(scoped_sql, params_rep)
    if token == "at_risk":
        return _salesrep_at_risk_customers_frame(scoped_sql, params_rep, inactivity_days=inactivity_days)

    raise ValueError(f"Unsupported export dataset: {dataset}")


def build_salesrep_export_sheets(rep_id: str, filters: Any, scope: Dict[str, Any], args: Any, include_history: bool = False):
    scoped_sql, params_rep, _, _ = _salesrep_export_context(rep_id, filters, scope)
    summary_df = _salesrep_summary_frame(scoped_sql, params_rep)
    trend_df = _salesrep_trend_frame(scoped_sql, params_rep)
    customers_df = _salesrep_customers_frame(scoped_sql, params_rep)
    products_df = _salesrep_products_frame(scoped_sql, params_rep)
    mix_df = _salesrep_mix_frame(products_df)
    movers_customers_df = _salesrep_movers_customers_frame(scoped_sql, params_rep)
    movers_products_df = _salesrep_movers_products_frame(scoped_sql, params_rep)
    margin_risk_df = _salesrep_margin_risk_frame(scoped_sql, params_rep)
    inactivity_days = _clean_int(args.get("at_risk_days") if hasattr(args, "get") else None, 45)
    at_risk_df = _salesrep_at_risk_customers_frame(scoped_sql, params_rep, inactivity_days=inactivity_days)
    metadata_df = _salesrep_metadata_frame(
        rep_id,
        summary_df,
        filters,
        dataset_version=fact_store.cache_buster(),
        export_type="all",
    )

    sheets = {
        "Metadata": metadata_df,
        "Summary": summary_df,
        "Trend": trend_df,
        "Customers": customers_df,
        "Products": products_df,
        "Mix": mix_df,
        "Movers_Customers": movers_customers_df,
        "Movers_Products": movers_products_df,
        "Margin_Risk": margin_risk_df,
        "At_Risk_Customers": at_risk_df,
    }
    if include_history:
        sheets["History"] = _salesrep_history_frame(scoped_sql, params_rep)
    return sheets
