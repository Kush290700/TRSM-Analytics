from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlencode

import pandas as pd
from flask import current_app, request, url_for

from app.services import labor_store


WEEKDAY_ORDER = {
    "Monday": 1,
    "Tuesday": 2,
    "Wednesday": 3,
    "Thursday": 4,
    "Friday": 5,
    "Saturday": 6,
    "Sunday": 7,
}

TABLE_SORTS = {
    "labor_date": "labor_date",
    "department_name": "department_name",
    "employee_name": "employee_name",
    "time_category": "time_category",
    "labor_cost": "labor_cost",
    "paid_hours": "paid_hours_allocated",
    "effective_rate": "effective_rate",
    "status": "status",
    "work_rule": "work_rule",
}


@dataclass(frozen=True)
class LaborFilters:
    start: date
    end: date
    departments: tuple[str, ...] = ()
    employees: tuple[str, ...] = ()
    time_categories: tuple[str, ...] = ()
    statuses: tuple[str, ...] = ()
    work_rules: tuple[str, ...] = ()
    search: str | None = None
    page: int = 1
    page_size: int = 50
    sort_by: str = "labor_cost"
    sort_dir: str = "desc"


def _clean_tokens(values: Iterable[Any]) -> tuple[str, ...]:
    seen: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            parts = [part.strip() for part in value.split(",")]
        else:
            parts = [str(value).strip()]
        for part in parts:
            if not part:
                continue
            if part not in seen:
                seen.append(part)
    return tuple(seen)


def _arg_list(args: Mapping[str, Any], *keys: str) -> tuple[str, ...]:
    values: list[Any] = []
    getter = getattr(args, "getlist", None)
    for key in keys:
        if getter is not None:
            try:
                values.extend(getter(key))
                values.extend(getter(f"{key}[]"))
            except Exception:
                pass
        value = args.get(key) if hasattr(args, "get") else None
        if value not in (None, ""):
            values.append(value)
    return _clean_tokens(values)


def _parse_date(raw: Any, *, default: date) -> date:
    if raw in (None, ""):
        return default
    ts = pd.to_datetime(raw, errors="coerce")
    if pd.isna(ts):
        return default
    return ts.date()


def _int_arg(raw: Any, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(raw)
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


def resolve_filters(args: Mapping[str, Any] | None = None) -> LaborFilters:
    source = args or request.args
    status = labor_store.get_status()
    max_date = _parse_date(status.max_date, default=date.today()) if status.max_date else date.today()
    default_days = max(7, int(current_app.config.get("LABOR_PAGE_DEFAULT_DAYS", 90) or 90))
    default_end = max_date
    default_start = default_end - timedelta(days=default_days - 1)
    start = _parse_date(source.get("start"), default=default_start)
    end = _parse_date(source.get("end"), default=default_end)
    if start > end:
        start, end = end, start
    sort_by = str(source.get("sort") or source.get("sort_by") or "labor_cost").strip().lower()
    if sort_by not in TABLE_SORTS:
        sort_by = "labor_cost"
    sort_dir = str(source.get("sort_dir") or source.get("direction") or "desc").strip().lower()
    sort_dir = "asc" if sort_dir == "asc" else "desc"
    return LaborFilters(
        start=start,
        end=end,
        departments=_arg_list(source, "department", "departments"),
        employees=_arg_list(source, "employee", "employees", "employee_code"),
        time_categories=_arg_list(source, "time_category", "time_categories"),
        statuses=_arg_list(source, "status", "statuses"),
        work_rules=_arg_list(source, "work_rule", "work_rules"),
        search=(str(source.get("search") or "").strip() or None),
        page=_int_arg(source.get("page"), 1, minimum=1, maximum=100000),
        page_size=_int_arg(source.get("page_size") or source.get("per_page"), 50, minimum=10, maximum=250),
        sort_by=sort_by,
        sort_dir=sort_dir,
    )


def _append_in_clause(clauses: list[str], params: list[Any], column_sql: str, values: Sequence[str]) -> None:
    values = [value for value in values if value]
    if not values:
        return
    placeholders = ", ".join(["?"] * len(values))
    clauses.append(f"{column_sql} IN ({placeholders})")
    params.extend(values)


def build_where_clause(
    filters: LaborFilters,
    *,
    alias: str = "lf",
    start: date | None = None,
    end: date | None = None,
) -> tuple[str, list[Any]]:
    clauses = [f"{alias}.labor_date >= ?", f"{alias}.labor_date <= ?"]
    params: list[Any] = [str(start or filters.start), str(end or filters.end)]
    _append_in_clause(clauses, params, f"COALESCE({alias}.department_name, 'Unassigned')", filters.departments)
    _append_in_clause(clauses, params, f"COALESCE({alias}.employee_code, '')", filters.employees)
    _append_in_clause(clauses, params, f"COALESCE({alias}.time_category, 'Unclassified')", filters.time_categories)
    _append_in_clause(clauses, params, f"COALESCE({alias}.status, '')", filters.statuses)
    _append_in_clause(clauses, params, f"COALESCE({alias}.work_rule, '')", filters.work_rules)
    if filters.search:
        needle = f"%{filters.search.lower()}%"
        clauses.append(
            "("
            f"LOWER(COALESCE({alias}.department_name, '')) LIKE ? OR "
            f"LOWER(COALESCE({alias}.employee_name, '')) LIKE ? OR "
            f"LOWER(COALESCE({alias}.employee_code, '')) LIKE ? OR "
            f"LOWER(COALESCE({alias}.time_category, '')) LIKE ? OR "
            f"LOWER(COALESCE({alias}.status, '')) LIKE ? OR "
            f"LOWER(COALESCE({alias}.work_rule, '')) LIKE ?"
            ")"
        )
        params.extend([needle] * 6)
    return " AND ".join(clauses), params


def _query_df(sql: str, params: Sequence[Any] | None = None) -> pd.DataFrame:
    return labor_store.query_df(sql, params)


def _query_summary(filters: LaborFilters, *, start: date | None = None, end: date | None = None) -> dict[str, Any]:
    where_sql, params = build_where_clause(filters, start=start, end=end)
    sql = f"""
        SELECT
            COALESCE(SUM(labor_cost), 0) AS total_labor_cost,
            COALESCE(SUM(paid_hours_allocated), 0) AS total_paid_hours,
            COALESCE(SUM(CASE WHEN is_premium THEN labor_cost ELSE 0 END), 0) AS premium_cost,
            COALESCE(SUM(CASE WHEN is_absence THEN labor_cost ELSE 0 END), 0) AS absence_cost,
            COALESCE(SUM(CASE WHEN is_memo THEN COALESCE(memo_amount, labor_cost, 0) ELSE 0 END), 0) AS memo_cost,
            COUNT(DISTINCT employee_key) AS active_employees,
            COUNT(DISTINCT department_key) AS active_departments,
            COUNT(*) AS transaction_count
        FROM labor_fact lf
        WHERE {where_sql}
    """
    frame = _query_df(sql, params)
    if frame.empty:
        return {
            "total_labor_cost": 0.0,
            "total_paid_hours": 0.0,
            "premium_cost": 0.0,
            "absence_cost": 0.0,
            "memo_cost": 0.0,
            "active_employees": 0,
            "active_departments": 0,
            "transaction_count": 0,
            "blended_rate": None,
            "premium_share_pct": None,
            "absence_share_pct": None,
        }
    row = frame.iloc[0].to_dict()
    total_labor_cost = float(row.get("total_labor_cost") or 0.0)
    total_paid_hours = float(row.get("total_paid_hours") or 0.0)
    premium_cost = float(row.get("premium_cost") or 0.0)
    absence_cost = float(row.get("absence_cost") or 0.0)
    row["blended_rate"] = (total_labor_cost / total_paid_hours) if total_paid_hours else None
    row["premium_share_pct"] = (premium_cost / total_labor_cost) if total_labor_cost else None
    row["absence_share_pct"] = (absence_cost / total_labor_cost) if total_labor_cost else None
    row["total_labor_cost"] = total_labor_cost
    row["total_paid_hours"] = total_paid_hours
    row["premium_cost"] = premium_cost
    row["absence_cost"] = absence_cost
    row["memo_cost"] = float(row.get("memo_cost") or 0.0)
    row["active_employees"] = int(row.get("active_employees") or 0)
    row["active_departments"] = int(row.get("active_departments") or 0)
    row["transaction_count"] = int(row.get("transaction_count") or 0)
    return row


def _query_department_summary(filters: LaborFilters, *, start: date | None = None, end: date | None = None) -> pd.DataFrame:
    where_sql, params = build_where_clause(filters, start=start, end=end)
    sql = f"""
        WITH grouped AS (
            SELECT
                COALESCE(department_name, 'Unassigned') AS department_name,
                COALESCE(department_number, '') AS department_number,
                COUNT(*) AS transaction_count,
                COUNT(DISTINCT employee_key) AS active_employee_count,
                COALESCE(SUM(labor_cost), 0) AS labor_cost,
                COALESCE(SUM(paid_hours_allocated), 0) AS paid_hours,
                COALESCE(SUM(CASE WHEN is_premium THEN labor_cost ELSE 0 END), 0) AS premium_cost,
                COALESCE(SUM(CASE WHEN is_absence THEN labor_cost ELSE 0 END), 0) AS absence_cost
            FROM labor_fact lf
            WHERE {where_sql}
            GROUP BY 1, 2
        )
        SELECT
            *,
            CASE WHEN paid_hours = 0 THEN NULL ELSE labor_cost / paid_hours END AS blended_rate,
            CASE WHEN labor_cost = 0 THEN NULL ELSE premium_cost / labor_cost END AS premium_share_pct,
            CASE WHEN labor_cost = 0 THEN NULL ELSE absence_cost / labor_cost END AS absence_share_pct,
            CASE WHEN active_employee_count = 0 THEN NULL ELSE labor_cost / active_employee_count END AS avg_cost_per_employee,
            CASE WHEN active_employee_count = 0 THEN NULL ELSE paid_hours / active_employee_count END AS avg_paid_hours_per_employee,
            CASE WHEN SUM(labor_cost) OVER () = 0 THEN NULL ELSE labor_cost / SUM(labor_cost) OVER () END AS labor_cost_share_pct,
            CASE WHEN SUM(paid_hours) OVER () = 0 THEN NULL ELSE paid_hours / SUM(paid_hours) OVER () END AS paid_hours_share_pct
        FROM grouped
        ORDER BY labor_cost DESC, department_name ASC
    """
    return _query_df(sql, params)


def _query_daily_trend(filters: LaborFilters) -> pd.DataFrame:
    where_sql, params = build_where_clause(filters)
    sql = f"""
        SELECT
            labor_date,
            COALESCE(SUM(labor_cost), 0) AS labor_cost,
            COALESCE(SUM(paid_hours_allocated), 0) AS paid_hours,
            COALESCE(SUM(CASE WHEN is_premium THEN labor_cost ELSE 0 END), 0) AS premium_cost,
            COALESCE(SUM(CASE WHEN is_absence THEN labor_cost ELSE 0 END), 0) AS absence_cost
        FROM labor_fact lf
        WHERE {where_sql}
        GROUP BY 1
        ORDER BY 1
    """
    frame = _query_df(sql, params)
    if not frame.empty:
        frame["labor_date"] = pd.to_datetime(frame["labor_date"], errors="coerce").dt.date
    return frame


def _query_monthly_department_trend(filters: LaborFilters, departments: Sequence[str]) -> pd.DataFrame:
    if not departments:
        return pd.DataFrame(columns=["labor_month", "department_name", "labor_cost", "paid_hours"])
    scoped = replace(filters, departments=tuple(departments))
    where_sql, params = build_where_clause(scoped)
    sql = f"""
        SELECT
            labor_month,
            department_name,
            COALESCE(SUM(labor_cost), 0) AS labor_cost,
            COALESCE(SUM(paid_hours_allocated), 0) AS paid_hours
        FROM labor_fact lf
        WHERE {where_sql}
        GROUP BY 1, 2
        ORDER BY 1, 2
    """
    return _query_df(sql, params)


def _query_category_mix(filters: LaborFilters, *, start: date | None = None, end: date | None = None) -> pd.DataFrame:
    where_sql, params = build_where_clause(filters, start=start, end=end)
    sql = f"""
        WITH grouped AS (
            SELECT
                COALESCE(time_category, 'Unclassified') AS time_category,
                COALESCE(SUM(labor_cost), 0) AS labor_cost,
                COALESCE(SUM(paid_hours_allocated), 0) AS paid_hours,
                COALESCE(SUM(CASE WHEN is_premium THEN labor_cost ELSE 0 END), 0) AS premium_cost,
                COALESCE(SUM(CASE WHEN is_absence THEN labor_cost ELSE 0 END), 0) AS absence_cost
            FROM labor_fact lf
            WHERE {where_sql}
            GROUP BY 1
        )
        SELECT
            *,
            CASE WHEN SUM(labor_cost) OVER () = 0 THEN NULL ELSE labor_cost / SUM(labor_cost) OVER () END AS labor_cost_share_pct,
            CASE WHEN SUM(paid_hours) OVER () = 0 THEN NULL ELSE paid_hours / SUM(paid_hours) OVER () END AS paid_hours_share_pct
        FROM grouped
        ORDER BY labor_cost DESC, time_category ASC
    """
    return _query_df(sql, params)


def _query_department_category_mix(filters: LaborFilters) -> pd.DataFrame:
    where_sql, params = build_where_clause(filters)
    sql = f"""
        SELECT
            COALESCE(department_name, 'Unassigned') AS department_name,
            COALESCE(time_category, 'Unclassified') AS time_category,
            COALESCE(SUM(labor_cost), 0) AS labor_cost,
            COALESCE(SUM(paid_hours_allocated), 0) AS paid_hours
        FROM labor_fact lf
        WHERE {where_sql}
        GROUP BY 1, 2
        ORDER BY labor_cost DESC
        LIMIT 24
    """
    return _query_df(sql, params)


def _query_weekday_pattern(filters: LaborFilters) -> pd.DataFrame:
    trend = _query_daily_trend(filters)
    if trend.empty:
        return pd.DataFrame(columns=["weekday_name", "avg_daily_labor_cost", "avg_daily_paid_hours"])
    trend["weekday_name"] = pd.to_datetime(trend["labor_date"], errors="coerce").dt.day_name()
    grouped = (
        trend.groupby("weekday_name", dropna=False)
        .agg(avg_daily_labor_cost=("labor_cost", "mean"), avg_daily_paid_hours=("paid_hours", "mean"))
        .reset_index()
    )
    grouped["weekday_order"] = grouped["weekday_name"].map(WEEKDAY_ORDER).fillna(99)
    grouped = grouped.sort_values(["weekday_order", "weekday_name"]).drop(columns=["weekday_order"])
    return grouped


def _query_monthly_pattern(filters: LaborFilters) -> pd.DataFrame:
    where_sql, params = build_where_clause(filters)
    sql = f"""
        SELECT
            labor_month,
            COALESCE(SUM(labor_cost), 0) AS labor_cost,
            COALESCE(SUM(paid_hours_allocated), 0) AS paid_hours
        FROM labor_fact lf
        WHERE {where_sql}
        GROUP BY 1
        ORDER BY 1
    """
    return _query_df(sql, params)


def _query_department_daily(filters: LaborFilters) -> pd.DataFrame:
    where_sql, params = build_where_clause(filters)
    sql = f"""
        SELECT
            labor_date,
            COALESCE(department_name, 'Unassigned') AS department_name,
            COALESCE(SUM(labor_cost), 0) AS labor_cost,
            COALESCE(SUM(paid_hours_allocated), 0) AS paid_hours,
            COALESCE(SUM(CASE WHEN is_premium THEN labor_cost ELSE 0 END), 0) AS premium_cost,
            COALESCE(SUM(CASE WHEN is_absence THEN labor_cost ELSE 0 END), 0) AS absence_cost
        FROM labor_fact lf
        WHERE {where_sql}
        GROUP BY 1, 2
        ORDER BY 1, 2
    """
    frame = _query_df(sql, params)
    if not frame.empty:
        frame["labor_date"] = pd.to_datetime(frame["labor_date"], errors="coerce").dt.date
    return frame


def _query_category_daily_trend(filters: LaborFilters, categories: Sequence[str]) -> pd.DataFrame:
    if not categories:
        return pd.DataFrame(columns=["labor_date", "time_category", "labor_cost", "paid_hours"])
    scoped = replace(filters, time_categories=tuple(categories))
    where_sql, params = build_where_clause(scoped)
    sql = f"""
        SELECT
            labor_date,
            COALESCE(time_category, 'Unclassified') AS time_category,
            COALESCE(SUM(labor_cost), 0) AS labor_cost,
            COALESCE(SUM(paid_hours_allocated), 0) AS paid_hours
        FROM labor_fact lf
        WHERE {where_sql}
        GROUP BY 1, 2
        ORDER BY 1, 2
    """
    frame = _query_df(sql, params)
    if not frame.empty:
        frame["labor_date"] = pd.to_datetime(frame["labor_date"], errors="coerce").dt.date
    return frame


def _query_worker_summary(
    filters: LaborFilters,
    *,
    start: date | None = None,
    end: date | None = None,
    limit: int | None = None,
) -> pd.DataFrame:
    where_sql, params = build_where_clause(filters, start=start, end=end)
    sql = f"""
        WITH grouped AS (
            SELECT
                COALESCE(employee_code, '') AS employee_code,
                COALESCE(employee_name, employee_code, 'Unknown Employee') AS employee_name,
                COUNT(*) AS transaction_count,
                COUNT(DISTINCT labor_date) AS active_days,
                COUNT(DISTINCT COALESCE(department_name, 'Unassigned')) AS department_count,
                COUNT(DISTINCT COALESCE(time_category, 'Unclassified')) AS category_count,
                COALESCE(SUM(labor_cost), 0) AS labor_cost,
                COALESCE(SUM(paid_hours_allocated), 0) AS paid_hours,
                COALESCE(SUM(CASE WHEN is_premium THEN labor_cost ELSE 0 END), 0) AS premium_cost,
                COALESCE(SUM(CASE WHEN is_absence THEN labor_cost ELSE 0 END), 0) AS absence_cost
            FROM labor_fact lf
            WHERE {where_sql}
            GROUP BY 1, 2
        )
        SELECT
            *,
            CASE WHEN paid_hours = 0 THEN NULL ELSE labor_cost / paid_hours END AS blended_rate,
            CASE WHEN labor_cost = 0 THEN NULL ELSE premium_cost / labor_cost END AS premium_share_pct,
            CASE WHEN labor_cost = 0 THEN NULL ELSE absence_cost / labor_cost END AS absence_share_pct,
            CASE WHEN active_days = 0 THEN NULL ELSE labor_cost / active_days END AS avg_cost_per_day,
            CASE WHEN active_days = 0 THEN NULL ELSE paid_hours / active_days END AS avg_hours_per_day,
            CASE WHEN SUM(labor_cost) OVER () = 0 THEN NULL ELSE labor_cost / SUM(labor_cost) OVER () END AS labor_cost_share_pct,
            CASE WHEN SUM(paid_hours) OVER () = 0 THEN NULL ELSE paid_hours / SUM(paid_hours) OVER () END AS paid_hours_share_pct
        FROM grouped
        ORDER BY labor_cost DESC, employee_name ASC
    """
    if limit is not None:
        sql += " LIMIT ?"
        params = [*params, int(limit)]
    return _query_df(sql, params)


def _query_worker_daily_trend(filters: LaborFilters, employee_codes: Sequence[str]) -> pd.DataFrame:
    if not employee_codes:
        return pd.DataFrame(columns=["labor_date", "employee_code", "employee_name", "labor_cost", "paid_hours", "premium_cost", "absence_cost"])
    scoped = replace(filters, employees=tuple(employee_codes))
    where_sql, params = build_where_clause(scoped)
    sql = f"""
        SELECT
            labor_date,
            COALESCE(employee_code, '') AS employee_code,
            COALESCE(employee_name, employee_code, 'Unknown Employee') AS employee_name,
            COALESCE(SUM(labor_cost), 0) AS labor_cost,
            COALESCE(SUM(paid_hours_allocated), 0) AS paid_hours,
            COALESCE(SUM(CASE WHEN is_premium THEN labor_cost ELSE 0 END), 0) AS premium_cost,
            COALESCE(SUM(CASE WHEN is_absence THEN labor_cost ELSE 0 END), 0) AS absence_cost
        FROM labor_fact lf
        WHERE {where_sql}
        GROUP BY 1, 2, 3
        ORDER BY 1, 3
    """
    frame = _query_df(sql, params)
    if not frame.empty:
        frame["labor_date"] = pd.to_datetime(frame["labor_date"], errors="coerce").dt.date
    return frame


def _query_worker_department_mix(filters: LaborFilters) -> pd.DataFrame:
    where_sql, params = build_where_clause(filters)
    sql = f"""
        SELECT
            COALESCE(employee_code, '') AS employee_code,
            COALESCE(employee_name, employee_code, 'Unknown Employee') AS employee_name,
            COALESCE(department_name, 'Unassigned') AS department_name,
            COALESCE(SUM(labor_cost), 0) AS labor_cost,
            COALESCE(SUM(paid_hours_allocated), 0) AS paid_hours
        FROM labor_fact lf
        WHERE {where_sql}
        GROUP BY 1, 2, 3
        ORDER BY labor_cost DESC, employee_name ASC, department_name ASC
        LIMIT 60
    """
    return _query_df(sql, params)


def _query_worker_category_mix(filters: LaborFilters) -> pd.DataFrame:
    where_sql, params = build_where_clause(filters)
    sql = f"""
        SELECT
            COALESCE(employee_code, '') AS employee_code,
            COALESCE(employee_name, employee_code, 'Unknown Employee') AS employee_name,
            COALESCE(time_category, 'Unclassified') AS time_category,
            COALESCE(SUM(labor_cost), 0) AS labor_cost,
            COALESCE(SUM(paid_hours_allocated), 0) AS paid_hours
        FROM labor_fact lf
        WHERE {where_sql}
        GROUP BY 1, 2, 3
        ORDER BY labor_cost DESC, employee_name ASC, time_category ASC
        LIMIT 60
    """
    return _query_df(sql, params)


def _query_workspace(filters: LaborFilters, *, export_all: bool = False) -> dict[str, Any]:
    where_sql, params = build_where_clause(filters)
    count_sql = f"SELECT COUNT(*) AS total_rows FROM labor_fact lf WHERE {where_sql}"
    total_rows_frame = _query_df(count_sql, params)
    total_rows = int((total_rows_frame.iloc[0]["total_rows"] if not total_rows_frame.empty else 0) or 0)
    sort_col = TABLE_SORTS.get(filters.sort_by, "labor_cost")
    sort_dir = "ASC" if filters.sort_dir == "asc" else "DESC"
    sql = f"""
        SELECT
            labor_date,
            COALESCE(department_name, 'Unassigned') AS department_name,
            COALESCE(employee_name, employee_code, 'Unknown Employee') AS employee_name,
            employee_code,
            COALESCE(time_category, 'Unclassified') AS time_category,
            labor_cost,
            paid_hours_allocated AS paid_hours,
            effective_rate,
            status,
            work_rule,
            is_premium,
            is_absence,
            is_memo
        FROM labor_fact lf
        WHERE {where_sql}
        ORDER BY {sort_col} {sort_dir}, labor_date DESC, department_name ASC, employee_name ASC
    """
    query_params = list(params)
    if not export_all:
        offset = max(0, (filters.page - 1) * filters.page_size)
        sql += " LIMIT ? OFFSET ?"
        query_params.extend([filters.page_size, offset])
    frame = _query_df(sql, query_params)
    if not frame.empty:
        frame["labor_date"] = pd.to_datetime(frame["labor_date"], errors="coerce").dt.date
    total_pages = max(1, math.ceil(total_rows / max(1, filters.page_size))) if not export_all else 1
    return {
        "rows": frame.to_dict(orient="records"),
        "frame": frame,
        "total_rows": total_rows,
        "total_pages": total_pages,
        "page": filters.page,
        "page_size": filters.page_size,
    }


def _query_filter_options(filters: LaborFilters) -> dict[str, list[dict[str, str]]]:
    base_where, base_params = build_where_clause(replace(filters, departments=(), employees=(), time_categories=(), statuses=(), work_rules=(), search=None))
    departments = _query_df(
        f"""
        SELECT
            COALESCE(department_name, 'Unassigned') AS department_name,
            COALESCE(department_number, '') AS department_number,
            SUM(labor_cost) AS labor_cost
        FROM labor_fact lf
        WHERE {base_where}
        GROUP BY 1, 2
        ORDER BY labor_cost DESC, department_name ASC
        """,
        base_params,
    )
    employees = _query_df(
        f"""
        SELECT
            COALESCE(employee_code, '') AS employee_code,
            COALESCE(employee_name, employee_code, 'Unknown Employee') AS employee_name,
            SUM(labor_cost) AS labor_cost
        FROM labor_fact lf
        WHERE {base_where}
        GROUP BY 1, 2
        ORDER BY labor_cost DESC, employee_name ASC
        LIMIT 400
        """,
        base_params,
    )
    categories = _query_df(
        f"""
        SELECT COALESCE(time_category, 'Unclassified') AS time_category, SUM(labor_cost) AS labor_cost
        FROM labor_fact lf
        WHERE {base_where}
        GROUP BY 1
        ORDER BY labor_cost DESC, time_category ASC
        """,
        base_params,
    )
    statuses = _query_df(
        f"""
        SELECT COALESCE(status, '') AS status, COUNT(*) AS rows
        FROM labor_fact lf
        WHERE {base_where}
        GROUP BY 1
        ORDER BY rows DESC, status ASC
        """,
        base_params,
    )
    work_rules = _query_df(
        f"""
        SELECT COALESCE(work_rule, '') AS work_rule, COUNT(*) AS rows
        FROM labor_fact lf
        WHERE {base_where}
        GROUP BY 1
        ORDER BY rows DESC, work_rule ASC
        """,
        base_params,
    )
    return {
        "departments": [
            {
                "value": str(row.get("department_name") or "Unassigned"),
                "label": (
                    f"{str(row.get('department_number') or '').strip()} - {str(row.get('department_name') or 'Unassigned')}"
                ).strip(" -"),
            }
            for row in departments.to_dict(orient="records")
        ],
        "employees": [
            {
                "value": str(row.get("employee_code") or ""),
                "label": (
                    f"{str(row.get('employee_code') or '').strip()} - {str(row.get('employee_name') or 'Unknown Employee')}"
                ).strip(" -"),
            }
            for row in employees.to_dict(orient="records")
            if row.get("employee_code")
        ],
        "time_categories": [
            {"value": str(row.get("time_category") or "Unclassified"), "label": str(row.get("time_category") or "Unclassified")}
            for row in categories.to_dict(orient="records")
        ],
        "statuses": [
            {"value": str(row.get("status") or ""), "label": str(row.get("status") or "Unknown")}
            for row in statuses.to_dict(orient="records")
            if row.get("status")
        ],
        "work_rules": [
            {"value": str(row.get("work_rule") or ""), "label": str(row.get("work_rule") or "Unknown")}
            for row in work_rules.to_dict(orient="records")
            if row.get("work_rule")
        ],
    }


def _prior_window(filters: LaborFilters) -> tuple[date, date]:
    window_days = max(1, (filters.end - filters.start).days + 1)
    prior_end = filters.start - timedelta(days=1)
    prior_start = prior_end - timedelta(days=window_days - 1)
    return prior_start, prior_end


def _delta_pct(current: float | None, prior: float | None) -> float | None:
    if current is None or prior in (None, 0):
        return None
    return (float(current) - float(prior)) / float(prior)


def _safe_float(value: Any) -> float:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def _driver_label(cost_delta: float | None, hours_delta: float | None, rate_delta: float | None) -> str:
    cost = _safe_float(cost_delta)
    hours = _safe_float(hours_delta)
    rate = _safe_float(rate_delta)
    if abs(cost) < 0.02:
        return "stable"
    if abs(rate) > abs(hours) + 0.03:
        return "rate-driven"
    if abs(hours) > abs(rate) + 0.03:
        return "hours-driven"
    return "mixed"


def _recent_change(series: pd.Series) -> float | None:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return None
    window = min(14, max(2, int(len(clean) // 2) or 2))
    if len(clean) < window * 2:
        return None
    recent = float(clean.iloc[-window:].sum())
    prior = float(clean.iloc[-(window * 2) : -window].sum())
    if prior == 0:
        return None
    return (recent - prior) / prior


def _sort_for_json(frame: pd.DataFrame, columns: Sequence[str], ascending: Sequence[bool], limit: int | None = None) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    work = frame.sort_values(list(columns), ascending=list(ascending))
    if limit is not None:
        work = work.head(limit)
    return work.to_dict(orient="records")


def _top_label(frame: pd.DataFrame, column: str, default: str) -> str:
    if frame.empty or column not in frame.columns:
        return default
    value = str(frame.iloc[0].get(column) or "").strip()
    return value or default


def _enrich_department_summary(
    current_departments: pd.DataFrame,
    prior_departments: pd.DataFrame,
    department_daily: pd.DataFrame,
) -> pd.DataFrame:
    if current_departments.empty:
        return current_departments
    frame = current_departments.copy()
    prior = prior_departments.rename(
        columns={
            "labor_cost": "prior_labor_cost",
            "paid_hours": "prior_paid_hours",
            "blended_rate": "prior_blended_rate",
            "premium_share_pct": "prior_premium_share_pct",
            "absence_share_pct": "prior_absence_share_pct",
        }
    )
    keep = [column for column in ["department_name", "department_number", "prior_labor_cost", "prior_paid_hours", "prior_blended_rate", "prior_premium_share_pct", "prior_absence_share_pct"] if column in prior.columns]
    if keep:
        frame = frame.merge(prior.loc[:, keep], on=["department_name", "department_number"], how="left")
    else:
        frame["prior_labor_cost"] = pd.NA
        frame["prior_paid_hours"] = pd.NA
        frame["prior_blended_rate"] = pd.NA
        frame["prior_premium_share_pct"] = pd.NA
        frame["prior_absence_share_pct"] = pd.NA
    frame["cost_delta_pct"] = (frame["labor_cost"] - frame["prior_labor_cost"]) / frame["prior_labor_cost"]
    frame["hours_delta_pct"] = (frame["paid_hours"] - frame["prior_paid_hours"]) / frame["prior_paid_hours"]
    frame["rate_delta_pct"] = (frame["blended_rate"] - frame["prior_blended_rate"]) / frame["prior_blended_rate"]
    frame["premium_share_delta_pct"] = frame["premium_share_pct"] - frame["prior_premium_share_pct"]
    frame["absence_share_delta_pct"] = frame["absence_share_pct"] - frame["prior_absence_share_pct"]
    if department_daily.empty:
        frame["cost_volatility"] = pd.NA
        frame["recent_cost_acceleration_pct"] = pd.NA
        frame["recent_hours_acceleration_pct"] = pd.NA
    else:
        daily = department_daily.copy()
        summary = (
            daily.groupby("department_name", dropna=False)
            .agg(
                daily_cost_mean=("labor_cost", "mean"),
                daily_cost_std=("labor_cost", "std"),
                daily_hours_mean=("paid_hours", "mean"),
                daily_hours_std=("paid_hours", "std"),
            )
            .reset_index()
        )
        summary["cost_volatility"] = summary["daily_cost_std"] / summary["daily_cost_mean"]
        summary["hours_volatility"] = summary["daily_hours_std"] / summary["daily_hours_mean"]
        accel_rows: list[dict[str, Any]] = []
        for department_name, part in daily.groupby("department_name", dropna=False):
            ordered = part.sort_values("labor_date")
            accel_rows.append(
                {
                    "department_name": department_name,
                    "recent_cost_acceleration_pct": _recent_change(ordered["labor_cost"]),
                    "recent_hours_acceleration_pct": _recent_change(ordered["paid_hours"]),
                }
            )
        accel = pd.DataFrame(accel_rows)
        frame = frame.merge(summary[["department_name", "cost_volatility", "hours_volatility"]], on="department_name", how="left")
        frame = frame.merge(accel, on="department_name", how="left")
    frame["driver_label"] = [
        _driver_label(cost_delta, hours_delta, rate_delta)
        for cost_delta, hours_delta, rate_delta in zip(
            frame.get("cost_delta_pct", pd.Series(dtype="float")),
            frame.get("hours_delta_pct", pd.Series(dtype="float")),
            frame.get("rate_delta_pct", pd.Series(dtype="float")),
        )
    ]
    frame["management_focus"] = "review mix"
    frame.loc[frame["premium_share_pct"].fillna(0).ge(0.08), "management_focus"] = "review premium"
    frame.loc[frame["absence_share_pct"].fillna(0).ge(0.04), "management_focus"] = "review absence"
    frame.loc[frame["driver_label"] == "hours-driven", "management_focus"] = "review staffing volume"
    frame.loc[frame["driver_label"] == "rate-driven", "management_focus"] = "review rate pressure"
    frame.loc[frame["cost_volatility"].fillna(0).ge(0.20), "management_focus"] = "review stability"
    return frame


def _enrich_category_summary(
    current_categories: pd.DataFrame,
    prior_categories: pd.DataFrame,
    department_category_mix: pd.DataFrame,
) -> pd.DataFrame:
    if current_categories.empty:
        return current_categories
    frame = current_categories.copy()
    prior = prior_categories.rename(
        columns={
            "labor_cost": "prior_labor_cost",
            "paid_hours": "prior_paid_hours",
            "premium_cost": "prior_premium_cost",
            "absence_cost": "prior_absence_cost",
        }
    )
    keep = [column for column in ["time_category", "prior_labor_cost", "prior_paid_hours", "prior_premium_cost", "prior_absence_cost"] if column in prior.columns]
    if "time_category" in keep and len(keep) > 1:
        frame = frame.merge(prior.loc[:, keep], on="time_category", how="left")
    else:
        frame["prior_labor_cost"] = pd.NA
        frame["prior_paid_hours"] = pd.NA
        frame["prior_premium_cost"] = pd.NA
        frame["prior_absence_cost"] = pd.NA
    frame["cost_delta_pct"] = (frame["labor_cost"] - frame["prior_labor_cost"]) / frame["prior_labor_cost"]
    frame["hours_delta_pct"] = (frame["paid_hours"] - frame["prior_paid_hours"]) / frame["prior_paid_hours"]
    if department_category_mix.empty:
        frame["leading_department"] = pd.NA
        frame["leading_department_share_pct"] = pd.NA
        return frame
    mix = department_category_mix.sort_values(["labor_cost", "department_name"], ascending=[False, True]).copy()
    leading = mix.groupby("time_category", dropna=False).head(1).rename(columns={"department_name": "leading_department", "labor_cost": "leading_department_cost"})
    frame = frame.merge(leading[["time_category", "leading_department", "leading_department_cost"]], on="time_category", how="left")
    frame["leading_department_share_pct"] = frame["leading_department_cost"] / frame["labor_cost"]
    return frame


def _enrich_worker_summary(current_workers: pd.DataFrame, prior_workers: pd.DataFrame) -> pd.DataFrame:
    if current_workers.empty:
        return current_workers
    frame = current_workers.copy()
    prior = prior_workers.rename(
        columns={
            "labor_cost": "prior_labor_cost",
            "paid_hours": "prior_paid_hours",
            "blended_rate": "prior_blended_rate",
            "premium_share_pct": "prior_premium_share_pct",
            "absence_share_pct": "prior_absence_share_pct",
        }
    )
    keep = [column for column in ["employee_code", "prior_labor_cost", "prior_paid_hours", "prior_blended_rate", "prior_premium_share_pct", "prior_absence_share_pct"] if column in prior.columns]
    if "employee_code" in keep and len(keep) > 1:
        frame = frame.merge(prior.loc[:, keep], on="employee_code", how="left")
    else:
        frame["prior_labor_cost"] = pd.NA
        frame["prior_paid_hours"] = pd.NA
        frame["prior_blended_rate"] = pd.NA
        frame["prior_premium_share_pct"] = pd.NA
        frame["prior_absence_share_pct"] = pd.NA
    frame["cost_delta_pct"] = (frame["labor_cost"] - frame["prior_labor_cost"]) / frame["prior_labor_cost"]
    frame["hours_delta_pct"] = (frame["paid_hours"] - frame["prior_paid_hours"]) / frame["prior_paid_hours"]
    frame["rate_delta_pct"] = (frame["blended_rate"] - frame["prior_blended_rate"]) / frame["prior_blended_rate"]
    frame["multi_department_flag"] = frame["department_count"].fillna(0).ge(2)
    frame["management_focus"] = "review workload"
    frame.loc[frame["premium_share_pct"].fillna(0).ge(0.08), "management_focus"] = "review premium"
    frame.loc[frame["absence_share_pct"].fillna(0).ge(0.04), "management_focus"] = "review absence"
    frame.loc[frame["multi_department_flag"], "management_focus"] = "review coverage"
    return frame


def _build_signals(
    filters: LaborFilters,
    current_summary: Mapping[str, Any],
    prior_summary: Mapping[str, Any],
    current_departments: pd.DataFrame,
    watchlist: pd.DataFrame,
    current_categories: pd.DataFrame,
    current_workers: pd.DataFrame,
) -> list[dict[str, Any]]:
    total_cost_delta = _delta_pct(current_summary.get("total_labor_cost"), prior_summary.get("total_labor_cost"))
    total_hours_delta = _delta_pct(current_summary.get("total_paid_hours"), prior_summary.get("total_paid_hours"))
    blended_rate_delta = _delta_pct(current_summary.get("blended_rate"), prior_summary.get("blended_rate"))
    top_department = current_departments.iloc[0].to_dict() if not current_departments.empty else {}
    top_watch = watchlist.iloc[0].to_dict() if not watchlist.empty else {}
    top_category = current_categories.iloc[0].to_dict() if not current_categories.empty else {}
    top_worker = current_workers.iloc[0].to_dict() if not current_workers.empty else {}
    premium_share = float(current_summary.get("premium_share_pct") or 0.0)
    absence_share = float(current_summary.get("absence_share_pct") or 0.0)
    rate_driver = "hours-driven"
    if (blended_rate_delta or 0.0) > (total_hours_delta or 0.0):
        rate_driver = "rate-driven"
    signals = [
        {
            "title": "Department Labor Pressure",
            "tone": "danger" if top_watch else "secondary",
            "detail": (
                f"{top_watch.get('department_name')} needs attention first because cost, premium, absence, or volatility is elevated."
                if top_watch
                else f"{top_department.get('department_name', 'No department')} carries the largest share of labor cost."
            ),
            "next_step": "Open the department investigation layer and compare workers, categories, and the recent trend.",
        },
        {
            "title": "Premium Risk",
            "tone": "warning" if premium_share >= 0.08 else "success",
            "detail": f"Premium share is {premium_share:.1%}; investigate when it stays above 8% or rises faster than hours.",
            "next_step": "Review premium-heavy departments and workers before adding coverage.",
        },
        {
            "title": "Absence Watch",
            "tone": "warning" if absence_share >= 0.04 else "success",
            "detail": f"Absence share is {absence_share:.1%}; concentrated absence costs usually require schedule or policy review.",
            "next_step": "Check absence-heavy departments, then inspect the worker watchlist for repeat exposure.",
        },
        {
            "title": "Cost Acceleration",
            "tone": "danger" if (total_cost_delta or 0.0) >= 0.10 else "secondary",
            "detail": (
                f"Current labor cost is {rate_driver} versus the prior comparable period."
                if prior_summary.get("transaction_count")
                else "No prior comparable period is available yet."
            ),
            "next_step": "Use the department cost vs hours comparison to separate staffing volume from rate or premium pressure.",
        },
        {
            "title": "Staffing Stability",
            "tone": "warning" if top_watch.get("cost_volatility") and float(top_watch["cost_volatility"]) >= 0.2 else "success",
            "detail": (
                f"Highest observed department volatility is {float(top_watch.get('cost_volatility') or 0.0):.1%}."
                if top_watch
                else "No abnormal volatility detected in the current selection."
            ),
            "next_step": "Use worker concentration and cross-department coverage to assess whether staffing is fragile.",
        },
        {
            "title": "Management Focus",
            "tone": "primary",
            "detail": (
                f"Start with {top_watch.get('department_name')}, {top_category.get('time_category', 'the largest category')}, and {top_worker.get('employee_name', 'the top worker')}."
                if top_watch
                else "Use the department, category, and worker layers together to rank where cost, hours, and rate diverge."
            ),
            "next_step": "Follow chart and table clicks into scoped department, category, worker, or day views.",
        },
    ]
    return signals


def _build_watchlist(current_departments: pd.DataFrame) -> pd.DataFrame:
    if current_departments.empty:
        return pd.DataFrame()
    merged = current_departments.copy()
    flags = (
        merged["premium_share_pct"].fillna(0).ge(0.08)
        | merged["absence_share_pct"].fillna(0).ge(0.04)
        | merged["cost_delta_pct"].fillna(0).ge(0.12)
        | merged["cost_volatility"].fillna(0).ge(0.20)
    )
    watch = merged.loc[flags].copy()
    if watch.empty:
        return watch
    watch["risk_score"] = (
        watch["premium_share_pct"].fillna(0).abs()
        + watch["absence_share_pct"].fillna(0).abs()
        + watch["cost_delta_pct"].fillna(0).abs()
        + watch["cost_volatility"].fillna(0).abs()
        + pd.to_numeric(watch["recent_cost_acceleration_pct"], errors="coerce").fillna(0).abs()
    )
    watch = watch.sort_values(["risk_score", "labor_cost"], ascending=[False, False]).reset_index(drop=True)
    return watch


def _build_worker_watchlist(workers: pd.DataFrame) -> pd.DataFrame:
    if workers.empty:
        return workers
    frame = workers.copy()
    premium_share = pd.to_numeric(frame["premium_share_pct"], errors="coerce").fillna(0)
    absence_share = pd.to_numeric(frame["absence_share_pct"], errors="coerce").fillna(0)
    cost_delta = pd.to_numeric(frame["cost_delta_pct"], errors="coerce").fillna(0)
    labor_share = pd.to_numeric(frame["labor_cost_share_pct"], errors="coerce").fillna(0)
    flags = (
        premium_share.ge(0.08)
        | absence_share.ge(0.04)
        | frame["multi_department_flag"].fillna(False)
        | cost_delta.ge(0.20)
    )
    frame = frame.loc[flags].copy()
    if frame.empty:
        return frame
    frame["risk_score"] = premium_share.loc[frame.index].abs() + absence_share.loc[frame.index].abs() + cost_delta.loc[frame.index].abs() + labor_share.loc[frame.index].abs()
    return frame.sort_values(["risk_score", "labor_cost"], ascending=[False, False]).reset_index(drop=True)


def _build_category_watchlist(categories: pd.DataFrame) -> pd.DataFrame:
    if categories.empty:
        return categories
    frame = categories.copy()
    flags = (
        frame["cost_delta_pct"].fillna(0).ge(0.15)
        | frame["labor_cost_share_pct"].fillna(0).ge(0.12)
        | frame["leading_department_share_pct"].fillna(0).ge(0.60)
    )
    frame = frame.loc[flags].copy()
    if frame.empty:
        return frame
    frame["risk_score"] = (
        frame["cost_delta_pct"].fillna(0).abs()
        + frame["labor_cost_share_pct"].fillna(0).abs()
        + frame["leading_department_share_pct"].fillna(0).abs()
    )
    return frame.sort_values(["risk_score", "labor_cost"], ascending=[False, False]).reset_index(drop=True)


def _top_departments_for_trend(current_departments: pd.DataFrame, limit: int = 5) -> list[str]:
    if current_departments.empty:
        return []
    return current_departments.head(limit)["department_name"].astype(str).tolist()


def _top_categories_for_trend(current_categories: pd.DataFrame, limit: int = 5) -> list[str]:
    if current_categories.empty:
        return []
    return current_categories.head(limit)["time_category"].astype(str).tolist()


def _pick_focus_value(selected_values: Sequence[str], frame: pd.DataFrame, column: str, fallback_default: str) -> str | None:
    if selected_values:
        return str(selected_values[0])
    if frame.empty or column not in frame.columns:
        return None
    value = str(frame.iloc[0].get(column) or "").strip()
    return value or fallback_default


def _build_department_focus(
    filters: LaborFilters,
    department_name: str | None,
    departments: pd.DataFrame,
) -> dict[str, Any] | None:
    if not department_name:
        return None
    frame = departments.loc[departments["department_name"] == department_name].copy()
    if frame.empty:
        return None
    scoped = replace(filters, departments=(department_name,), page=1, sort_by="labor_cost", sort_dir="desc")
    daily_trend = _query_daily_trend(scoped)
    workers = _enrich_worker_summary(_query_worker_summary(scoped, limit=12), pd.DataFrame())
    categories = _query_category_mix(scoped).head(10)
    worker_watchlist = _build_worker_watchlist(workers)
    department_row = frame.iloc[0].to_dict()
    driver = _driver_label(department_row.get("cost_delta_pct"), department_row.get("hours_delta_pct"), department_row.get("rate_delta_pct"))
    interpretation = (
        f"{department_name} is currently {driver}. "
        f"Premium share is {department_row.get('premium_share_pct'):.1%} and absence share is {department_row.get('absence_share_pct'):.1%}."
        if department_row.get("premium_share_pct") is not None and department_row.get("absence_share_pct") is not None
        else f"{department_name} is currently {driver} under the active filters."
    )
    return {
        "department_name": department_name,
        "summary": department_row,
        "trend_rows": daily_trend.to_dict(orient="records"),
        "worker_rows": workers.head(12).to_dict(orient="records"),
        "category_rows": categories.to_dict(orient="records"),
        "watch_rows": worker_watchlist.head(8).to_dict(orient="records"),
        "interpretation": interpretation,
        "clear_url": build_url(filters, updates={"department": None}, include_pagination=False),
        "is_selected": department_name in filters.departments,
    }


def _build_category_focus(
    filters: LaborFilters,
    category_name: str | None,
    categories: pd.DataFrame,
) -> dict[str, Any] | None:
    if not category_name:
        return None
    frame = categories.loc[categories["time_category"] == category_name].copy()
    if frame.empty:
        return None
    scoped = replace(filters, time_categories=(category_name,), page=1, sort_by="labor_cost", sort_dir="desc")
    trend_rows = _query_daily_trend(scoped)
    department_rows = _query_department_summary(scoped).head(12)
    worker_rows = _enrich_worker_summary(_query_worker_summary(scoped, limit=12), pd.DataFrame())
    row = frame.iloc[0].to_dict()
    leading_department = _top_label(department_rows, "department_name", "the current selection")
    interpretation = (
        f"{category_name} is led by {leading_department}. "
        "Use this layer to see whether the category is concentrated in one department, widening across the business, or being driven by a small worker group."
    )
    return {
        "time_category": category_name,
        "summary": row,
        "trend_rows": trend_rows.to_dict(orient="records"),
        "department_rows": department_rows.to_dict(orient="records"),
        "worker_rows": worker_rows.to_dict(orient="records"),
        "interpretation": interpretation,
        "clear_url": build_url(filters, updates={"time_category": None}, include_pagination=False),
        "is_selected": category_name in filters.time_categories,
    }


def _build_worker_focus(
    filters: LaborFilters,
    employee_code: str | None,
    workers: pd.DataFrame,
) -> dict[str, Any] | None:
    if not employee_code:
        return None
    frame = workers.loc[workers["employee_code"] == employee_code].copy()
    if frame.empty:
        return None
    scoped = replace(filters, employees=(employee_code,), page=1, sort_by="labor_cost", sort_dir="desc")
    trend_rows = _query_daily_trend(scoped)
    department_rows = _query_department_summary(scoped).head(10)
    category_rows = _query_category_mix(scoped).head(10)
    row = frame.iloc[0].to_dict()
    interpretation = (
        f"{row.get('employee_name', 'This worker')} contributes {float(row.get('labor_cost_share_pct') or 0.0):.1%} of labor cost in the active selection. "
        "Review whether that exposure is spread across departments, concentrated in premium categories, or driven by recent absence."
    )
    return {
        "employee_code": employee_code,
        "employee_name": row.get("employee_name"),
        "summary": row,
        "trend_rows": trend_rows.to_dict(orient="records"),
        "department_rows": department_rows.to_dict(orient="records"),
        "category_rows": category_rows.to_dict(orient="records"),
        "interpretation": interpretation,
        "clear_url": build_url(filters, updates={"employee": None}, include_pagination=False),
        "is_selected": employee_code in filters.employees,
    }


def _build_actions(
    current_summary: Mapping[str, Any],
    department_watchlist: pd.DataFrame,
    worker_watchlist: pd.DataFrame,
    category_watchlist: pd.DataFrame,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if not department_watchlist.empty:
        top = department_watchlist.iloc[0]
        actions.append(
            {
                "title": f"Investigate {top.get('department_name')}",
                "detail": f"Department cost, volatility, premium share, or absence share is above peer levels under the current filters.",
                "scope": "department",
                "value": top.get("department_name"),
            }
        )
    if float(current_summary.get("premium_share_pct") or 0.0) >= 0.08:
        actions.append(
            {
                "title": "Review premium and overtime coverage",
                "detail": "Current premium share is elevated relative to total labor cost; confirm whether staffing gaps or work-rule usage are causing the pressure.",
                "scope": "category",
                "value": "Overtime",
            }
        )
    if not worker_watchlist.empty:
        top_worker = worker_watchlist.iloc[0]
        actions.append(
            {
                "title": f"Review {top_worker.get('employee_name')}",
                "detail": "Worker-level concentration, premium exposure, absence exposure, or cross-department coverage suggests management review.",
                "scope": "employee",
                "value": top_worker.get("employee_code"),
            }
        )
    if not category_watchlist.empty:
        top_category = category_watchlist.iloc[0]
        actions.append(
            {
                "title": f"Review {top_category.get('time_category')}",
                "detail": "Category growth, concentration, or category share suggests a policy or scheduling review before expanding headcount.",
                "scope": "category",
                "value": top_category.get("time_category"),
            }
        )
    if not actions:
        actions.append(
            {
                "title": "Maintain current staffing rhythm",
                "detail": "No major department, worker, or category watch signal is elevated in the active selection.",
                "scope": None,
                "value": None,
            }
        )
    return actions[:5]


def _build_narratives(
    current_summary: Mapping[str, Any],
    prior_summary: Mapping[str, Any],
    current_departments: pd.DataFrame,
    category_mix: pd.DataFrame,
    current_workers: pd.DataFrame,
    department_watchlist: pd.DataFrame,
) -> dict[str, str]:
    total_cost = float(current_summary.get("total_labor_cost") or 0.0)
    prior_cost = float(prior_summary.get("total_labor_cost") or 0.0)
    cost_delta = total_cost - prior_cost
    top_department = current_departments.iloc[0].to_dict() if not current_departments.empty else {}
    top_category = category_mix.iloc[0].to_dict() if not category_mix.empty else {}
    top_worker = current_workers.iloc[0].to_dict() if not current_workers.empty else {}
    top_watch = department_watchlist.iloc[0].to_dict() if not department_watchlist.empty else {}
    executive = "No labor rows matched the active filters."
    if total_cost > 0:
        direction = "rose" if cost_delta >= 0 else "fell"
        executive = (
            f"Labor cost {direction} to ${total_cost:,.0f}. "
            f"{top_department.get('department_name', 'The top department')} is carrying the largest share of cost, "
            f"{top_category.get('time_category', 'the top category')} is the dominant transaction mix, "
            f"and {top_worker.get('employee_name', 'the top worker')} is the biggest worker-level contributor."
        )
        if top_watch:
            executive += f" {top_watch.get('department_name')} shows the strongest current watch signal."
    department = (
        "Department rankings compare cost, hours, blended rate, premium share, absence share, volatility, and recent acceleration under the same filters. "
        "Use them to decide where staffing review should start, not just where cost is highest."
    )
    trend = (
        "Trend charts separate labor cost, hours, blended rate, and operating rhythm over time. "
        "When cost moves faster than hours, management should check rate, premium, or category mix before changing staffing levels."
    )
    composition = (
        "Composition shows which time categories are absorbing spend, which departments own those categories, and whether the mix is shifting. "
        "A shift toward premium, absence, sick, or vacation categories is usually more actionable than total cost alone."
    )
    watchlist = (
        "Watchlists surface departments, workers, and categories where premium share, absence share, concentration, volatility, or recent acceleration exceed the rest of the selection."
    )
    workspace = (
        "Use the workspace to trace the exact department, employee, and time category rows behind any signal or chart, then export the scoped detail if action is required."
    )
    workers = (
        "Worker views highlight who is driving cost, hours, premium exposure, absence exposure, and cross-department coverage. "
        "Use them to review assignment concentration and staffing resilience."
    )
    return {
        "executive": executive,
        "department": department,
        "trend": trend,
        "composition": composition,
        "watchlist": watchlist,
        "workspace": workspace,
        "workers": workers,
    }


def _serialize_filters(filters: LaborFilters) -> dict[str, Any]:
    return {
        "start": filters.start.isoformat(),
        "end": filters.end.isoformat(),
        "departments": list(filters.departments),
        "employees": list(filters.employees),
        "time_categories": list(filters.time_categories),
        "statuses": list(filters.statuses),
        "work_rules": list(filters.work_rules),
        "search": filters.search,
        "page": filters.page,
        "page_size": filters.page_size,
        "sort_by": filters.sort_by,
        "sort_dir": filters.sort_dir,
    }


def _query_args_from_filters(filters: LaborFilters, *, include_pagination: bool = True) -> list[tuple[str, str]]:
    args = [("start", filters.start.isoformat()), ("end", filters.end.isoformat())]
    for department in filters.departments:
        args.append(("department", department))
    for employee in filters.employees:
        args.append(("employee", employee))
    for category in filters.time_categories:
        args.append(("time_category", category))
    for status in filters.statuses:
        args.append(("status", status))
    for work_rule in filters.work_rules:
        args.append(("work_rule", work_rule))
    if filters.search:
        args.append(("search", filters.search))
    if include_pagination:
        args.append(("page", str(filters.page)))
        args.append(("page_size", str(filters.page_size)))
        args.append(("sort", filters.sort_by))
        args.append(("sort_dir", filters.sort_dir))
    return args


def build_url(filters: LaborFilters, *, updates: Mapping[str, Any] | None = None, include_pagination: bool = True) -> str:
    pairs = _query_args_from_filters(filters, include_pagination=include_pagination)
    params: dict[str, list[str]] = {}
    for key, value in pairs:
        params.setdefault(key, []).append(value)
    for key, value in (updates or {}).items():
        if value is None or value == "":
            params.pop(key, None)
            continue
        if isinstance(value, (list, tuple)):
            params[key] = [str(item) for item in value if item not in (None, "")]
        else:
            params[key] = [str(value)]
    encoded = urlencode([(key, item) for key, values in params.items() for item in values], doseq=True)
    return f"{url_for('labor.index')}?{encoded}" if encoded else url_for("labor.index")


def build_export_url(filters: LaborFilters, dataset: str, fmt: str) -> str:
    base = url_for("labor.export_dataset", dataset=dataset)
    encoded = urlencode(_query_args_from_filters(filters, include_pagination=False) + [("format", fmt)], doseq=True)
    return f"{base}?{encoded}"


def build_page_payload(args: Mapping[str, Any] | None = None) -> dict[str, Any]:
    status = labor_store.get_status()
    filters = resolve_filters(args)
    payload: dict[str, Any] = {
        "status": status.__dict__,
        "filters": _serialize_filters(filters),
        "filter_options": {"departments": [], "employees": [], "time_categories": [], "statuses": [], "work_rules": []},
        "kpis": {},
        "signals": [],
        "actions": [],
        "charts": {},
        "watchlist": {"rows": []},
        "watchlists": {"departments": [], "workers": [], "categories": []},
        "workspace": {"rows": [], "total_rows": 0, "page": filters.page, "page_size": filters.page_size, "total_pages": 1},
        "focus": {"department": None, "category": None, "worker": None},
        "messages": [],
        "has_results": False,
        "narratives": {},
        "export_urls": {
            "snapshot_xlsx": build_export_url(filters, "snapshot", "xlsx"),
            "detail_csv": build_export_url(filters, "detail", "csv"),
            "department_summary_xlsx": build_export_url(filters, "department-summary", "xlsx"),
            "category_summary_xlsx": build_export_url(filters, "category-summary", "xlsx"),
            "employee_summary_xlsx": build_export_url(filters, "employee-summary", "xlsx"),
            "watchlist_csv": build_export_url(filters, "watchlist", "csv"),
        },
    }
    if not status.available:
        payload["messages"].append(status.warning)
        return payload

    filter_options = _query_filter_options(filters)
    current_summary = _query_summary(filters)
    prior_start, prior_end = _prior_window(filters)
    prior_summary = _query_summary(filters, start=prior_start, end=prior_end)
    current_departments = _query_department_summary(filters)
    prior_departments = _query_department_summary(filters, start=prior_start, end=prior_end)
    department_daily = _query_department_daily(filters)
    current_departments = _enrich_department_summary(current_departments, prior_departments, department_daily)
    daily_trend = _query_daily_trend(filters)
    category_mix = _query_category_mix(filters)
    prior_category_mix = _query_category_mix(filters, start=prior_start, end=prior_end)
    department_category_mix = _query_department_category_mix(filters)
    category_mix = _enrich_category_summary(category_mix, prior_category_mix, department_category_mix)
    weekday_pattern = _query_weekday_pattern(filters)
    monthly_pattern = _query_monthly_pattern(filters)
    worker_summary = _query_worker_summary(filters, limit=400)
    prior_worker_summary = _query_worker_summary(filters, start=prior_start, end=prior_end, limit=2000)
    worker_summary = _enrich_worker_summary(worker_summary, prior_worker_summary)
    worker_department_mix = _query_worker_department_mix(filters)
    worker_category_mix = _query_worker_category_mix(filters)
    top_department_names = _top_departments_for_trend(current_departments)
    top_category_names = _top_categories_for_trend(category_mix)
    top_worker_codes = worker_summary.head(5)["employee_code"].astype(str).tolist() if not worker_summary.empty else []
    monthly_department_trend = _query_monthly_department_trend(filters, top_department_names)
    category_daily_trend = _query_category_daily_trend(filters, top_category_names)
    worker_daily_trend = _query_worker_daily_trend(filters, top_worker_codes)
    watchlist = _build_watchlist(current_departments)
    worker_watchlist = _build_worker_watchlist(worker_summary)
    category_watchlist = _build_category_watchlist(category_mix)
    workspace = _query_workspace(filters)
    workspace_payload = {key: value for key, value in workspace.items() if key != "frame"}
    narratives = _build_narratives(current_summary, prior_summary, current_departments, category_mix, worker_summary, watchlist)
    signals = _build_signals(filters, current_summary, prior_summary, current_departments, watchlist, category_mix, worker_summary)
    actions = _build_actions(current_summary, watchlist, worker_watchlist, category_watchlist)

    total_cost_delta_pct = _delta_pct(current_summary.get("total_labor_cost"), prior_summary.get("total_labor_cost"))
    total_hours_delta_pct = _delta_pct(current_summary.get("total_paid_hours"), prior_summary.get("total_paid_hours"))
    active_departments = int(current_summary.get("active_departments") or 0)
    active_employees = int(current_summary.get("active_employees") or 0)
    focus_department_name = _pick_focus_value(filters.departments, current_departments, "department_name", "Top department")
    focus_category_name = _pick_focus_value(filters.time_categories, category_mix, "time_category", "Top category")
    focus_worker_code = _pick_focus_value(filters.employees, worker_summary, "employee_code", "Top worker")
    department_focus = _build_department_focus(filters, focus_department_name, current_departments)
    category_focus = _build_category_focus(filters, focus_category_name, category_mix)
    worker_focus = _build_worker_focus(filters, focus_worker_code, worker_summary)
    top_department = current_departments.iloc[0].to_dict() if not current_departments.empty else {}
    top_category = category_mix.iloc[0].to_dict() if not category_mix.empty else {}
    top_worker = worker_summary.iloc[0].to_dict() if not worker_summary.empty else {}
    driver_label = _driver_label(total_cost_delta_pct, total_hours_delta_pct, _delta_pct(current_summary.get("blended_rate"), prior_summary.get("blended_rate")))

    kpis = {
        **current_summary,
        "labor_trend_vs_prior_pct": total_cost_delta_pct,
        "hours_trend_vs_prior_pct": total_hours_delta_pct,
        "blended_rate_vs_prior_pct": _delta_pct(current_summary.get("blended_rate"), prior_summary.get("blended_rate")),
        "prior_window_start": prior_start.isoformat(),
        "prior_window_end": prior_end.isoformat(),
    }

    payload.update(
        {
            "filter_options": filter_options,
            "kpis": kpis,
            "signals": signals,
            "actions": actions,
            "has_results": bool(current_summary.get("transaction_count")),
            "narratives": narratives,
            "hero": {
                "title": "Labor Intelligence",
                "subtitle": "Workforce, labor cost, premium, absence, and staffing pressure analysis from Synerion time transactions.",
                "purpose": "Use this page to understand what is happening, where labor pressure is building, who is driving it, and what management should review next.",
                "window_label": f"{filters.start.isoformat()} to {filters.end.isoformat()}",
                "active_departments": active_departments,
                "active_employees": active_employees,
                "total_labor_cost": current_summary.get("total_labor_cost"),
                "total_paid_hours": current_summary.get("total_paid_hours"),
                "driver_label": driver_label,
                "top_department": top_department.get("department_name"),
                "top_category": top_category.get("time_category"),
                "top_worker": top_worker.get("employee_name"),
                "executive_narrative": narratives.get("executive"),
                "last_refresh_utc": status.last_refresh_utc,
            },
            "charts": {
                "department_cost": _sort_for_json(current_departments, ["labor_cost", "department_name"], [False, True], limit=12),
                "department_hours": _sort_for_json(current_departments, ["paid_hours", "department_name"], [False, True], limit=12),
                "department_rate": _sort_for_json(current_departments, ["blended_rate", "department_name"], [False, True], limit=12),
                "department_premium": _sort_for_json(current_departments, ["premium_share_pct", "department_name"], [False, True], limit=12),
                "department_absence": _sort_for_json(current_departments, ["absence_share_pct", "department_name"], [False, True], limit=12),
                "department_volatility": _sort_for_json(current_departments, ["cost_volatility", "department_name"], [False, True], limit=12),
                "department_scatter": _sort_for_json(current_departments, ["labor_cost", "department_name"], [False, True], limit=15),
                "daily_trend": daily_trend.to_dict(orient="records"),
                "department_daily": department_daily.to_dict(orient="records"),
                "monthly_department_trend": monthly_department_trend.to_dict(orient="records"),
                "monthly_pattern": monthly_pattern.to_dict(orient="records"),
                "category_mix": category_mix.head(12).to_dict(orient="records"),
                "category_trend": category_daily_trend.to_dict(orient="records"),
                "department_category_mix": department_category_mix.to_dict(orient="records"),
                "weekday_pattern": weekday_pattern.to_dict(orient="records"),
                "worker_cost": _sort_for_json(worker_summary, ["labor_cost", "employee_name"], [False, True], limit=12),
                "worker_hours": _sort_for_json(worker_summary, ["paid_hours", "employee_name"], [False, True], limit=12),
                "worker_premium": _sort_for_json(worker_summary, ["premium_share_pct", "employee_name"], [False, True], limit=12),
                "worker_absence": _sort_for_json(worker_summary, ["absence_share_pct", "employee_name"], [False, True], limit=12),
                "worker_daily_trend": worker_daily_trend.to_dict(orient="records"),
                "worker_department_mix": worker_department_mix.to_dict(orient="records"),
                "worker_category_mix": worker_category_mix.to_dict(orient="records"),
            },
            "department_table": current_departments.head(15).to_dict(orient="records"),
            "category_table": category_mix.head(15).to_dict(orient="records"),
            "worker_table": worker_summary.head(20).to_dict(orient="records"),
            "watchlist": {"rows": watchlist.head(15).to_dict(orient="records")},
            "watchlists": {
                "departments": watchlist.head(12).to_dict(orient="records"),
                "workers": worker_watchlist.head(12).to_dict(orient="records"),
                "categories": category_watchlist.head(12).to_dict(orient="records"),
            },
            "focus": {
                "department": department_focus,
                "category": category_focus,
                "worker": worker_focus,
            },
            "workspace": workspace_payload,
        }
    )
    if current_departments.empty:
        payload["messages"].append("No labor rows matched the active filters.")
    return payload


def _rename_columns(frame: pd.DataFrame, mapping: Mapping[str, str]) -> pd.DataFrame:
    out = frame.copy()
    cols = [column for column in mapping if column in out.columns]
    if cols:
        out = out.loc[:, cols].rename(columns={column: mapping[column] for column in cols})
    return out


def _combined_watchlist_frame(
    department_watchlist: pd.DataFrame,
    worker_watchlist: pd.DataFrame,
    category_watchlist: pd.DataFrame,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    if not department_watchlist.empty:
        dept = department_watchlist.copy()
        dept["Scope"] = "Department"
        dept["Entity"] = dept["department_name"]
        dept["Focus"] = dept["management_focus"]
        frames.append(
            _rename_columns(
                dept,
                {
                    "Scope": "Scope",
                    "Entity": "Entity",
                    "Focus": "Focus",
                    "labor_cost": "Labor Cost",
                    "paid_hours": "Paid Hours",
                    "premium_share_pct": "Premium Share %",
                    "absence_share_pct": "Absence Share %",
                    "cost_delta_pct": "Cost Delta %",
                    "hours_delta_pct": "Hours Delta %",
                    "cost_volatility": "Volatility",
                    "recent_cost_acceleration_pct": "Recent Cost Acceleration %",
                },
            )
        )
    if not worker_watchlist.empty:
        workers = worker_watchlist.copy()
        workers["Scope"] = "Worker"
        workers["Entity"] = workers["employee_name"]
        workers["Focus"] = workers["management_focus"]
        frames.append(
            _rename_columns(
                workers,
                {
                    "Scope": "Scope",
                    "Entity": "Entity",
                    "Focus": "Focus",
                    "employee_code": "Employee Code",
                    "labor_cost": "Labor Cost",
                    "paid_hours": "Paid Hours",
                    "premium_share_pct": "Premium Share %",
                    "absence_share_pct": "Absence Share %",
                    "cost_delta_pct": "Cost Delta %",
                    "hours_delta_pct": "Hours Delta %",
                    "department_count": "Departments Worked",
                },
            )
        )
    if not category_watchlist.empty:
        categories = category_watchlist.copy()
        categories["Scope"] = "Category"
        categories["Entity"] = categories["time_category"]
        categories["Focus"] = categories["leading_department"]
        frames.append(
            _rename_columns(
                categories,
                {
                    "Scope": "Scope",
                    "Entity": "Entity",
                    "Focus": "Leading Department",
                    "labor_cost": "Labor Cost",
                    "paid_hours": "Paid Hours",
                    "labor_cost_share_pct": "Labor Cost Share %",
                    "paid_hours_share_pct": "Paid Hours Share %",
                    "cost_delta_pct": "Cost Delta %",
                    "leading_department_share_pct": "Leading Department Share %",
                },
            )
        )
    if not frames:
        return pd.DataFrame(columns=["Scope", "Entity", "Focus"])
    return pd.concat(frames, ignore_index=True, sort=False)


def build_export_frames(filters: LaborFilters, dataset: str) -> tuple[dict[str, pd.DataFrame], str]:
    current_summary = _query_summary(filters)
    prior_start, prior_end = _prior_window(filters)
    current_departments = _query_department_summary(filters)
    prior_departments = _query_department_summary(filters, start=prior_start, end=prior_end)
    department_daily = _query_department_daily(filters)
    current_departments = _enrich_department_summary(current_departments, prior_departments, department_daily)
    top_department_names = _top_departments_for_trend(current_departments)
    monthly_department_trend = _query_monthly_department_trend(filters, top_department_names)
    category_df = _enrich_category_summary(
        _query_category_mix(filters),
        _query_category_mix(filters, start=prior_start, end=prior_end),
        _query_department_category_mix(filters),
    )
    worker_df = _enrich_worker_summary(
        _query_worker_summary(filters, limit=2000),
        _query_worker_summary(filters, start=prior_start, end=prior_end, limit=2000),
    )
    department_watchlist_df = _build_watchlist(current_departments)
    worker_watchlist_df = _build_worker_watchlist(worker_df)
    category_watchlist_df = _build_category_watchlist(category_df)
    watchlist_df = _combined_watchlist_frame(department_watchlist_df, worker_watchlist_df, category_watchlist_df)
    detail_df = _query_workspace(filters, export_all=True)["frame"]
    trend_df = _query_daily_trend(filters)
    monthly_pattern_df = _query_monthly_pattern(filters)
    department_df = current_departments
    summary_df = pd.DataFrame(
        [
            {"Metric": "Window Start", "Value": filters.start.isoformat()},
            {"Metric": "Window End", "Value": filters.end.isoformat()},
            {
                "Metric": "Total Labor Cost",
                "Value": current_summary.get("total_labor_cost"),
            },
            {
                "Metric": "Total Paid Hours",
                "Value": current_summary.get("total_paid_hours"),
            },
            {
                "Metric": "Blended Rate",
                "Value": current_summary.get("blended_rate"),
            },
            {
                "Metric": "Premium Cost",
                "Value": current_summary.get("premium_cost"),
            },
            {
                "Metric": "Absence Cost",
                "Value": current_summary.get("absence_cost"),
            },
            {
                "Metric": "Premium Share %",
                "Value": current_summary.get("premium_share_pct"),
            },
            {
                "Metric": "Absence Share %",
                "Value": current_summary.get("absence_share_pct"),
            },
            {
                "Metric": "Active Employees",
                "Value": current_summary.get("active_employees"),
            },
            {
                "Metric": "Active Departments",
                "Value": current_summary.get("active_departments"),
            },
        ]
    )
    if dataset == "detail":
        return (
            {
                "LaborDetail": _rename_columns(
                    detail_df,
                    {
                        "labor_date": "Labor Date",
                        "department_name": "Department",
                        "employee_name": "Employee",
                        "employee_code": "Employee Code",
                        "time_category": "Time Category",
                        "labor_cost": "Labor Cost",
                        "paid_hours": "Paid Hours",
                        "effective_rate": "Effective Rate",
                        "status": "Status",
                        "work_rule": "Work Rule",
                        "is_premium": "Is Premium",
                        "is_absence": "Is Absence",
                        "is_memo": "Is Memo",
                    },
                )
            },
            "labor_detail",
        )
    if dataset == "department-summary":
        return (
            {
                "DepartmentSummary": _rename_columns(
                    department_df,
                    {
                        "department_name": "Department",
                        "department_number": "Department Number",
                        "labor_cost": "Labor Cost",
                        "paid_hours": "Paid Hours",
                        "blended_rate": "Blended Rate",
                        "premium_share_pct": "Premium Share %",
                        "absence_share_pct": "Absence Share %",
                        "labor_cost_share_pct": "Labor Cost Share %",
                        "paid_hours_share_pct": "Paid Hours Share %",
                        "cost_delta_pct": "Cost Delta %",
                        "hours_delta_pct": "Hours Delta %",
                        "rate_delta_pct": "Rate Delta %",
                        "cost_volatility": "Volatility",
                        "recent_cost_acceleration_pct": "Recent Cost Acceleration %",
                        "management_focus": "Management Focus",
                    },
                )
            },
            "labor_department_summary",
        )
    if dataset == "category-summary":
        return (
            {
                "CategorySummary": _rename_columns(
                    category_df,
                    {
                        "time_category": "Time Category",
                        "labor_cost": "Labor Cost",
                        "paid_hours": "Paid Hours",
                        "labor_cost_share_pct": "Labor Cost Share %",
                        "paid_hours_share_pct": "Paid Hours Share %",
                        "cost_delta_pct": "Cost Delta %",
                        "hours_delta_pct": "Hours Delta %",
                        "leading_department": "Leading Department",
                        "leading_department_share_pct": "Leading Department Share %",
                    },
                )
            },
            "labor_category_summary",
        )
    if dataset == "employee-summary":
        return (
            {
                "EmployeeSummary": _rename_columns(
                    worker_df,
                    {
                        "employee_name": "Employee",
                        "employee_code": "Employee Code",
                        "labor_cost": "Labor Cost",
                        "paid_hours": "Paid Hours",
                        "blended_rate": "Blended Rate",
                        "premium_share_pct": "Premium Share %",
                        "absence_share_pct": "Absence Share %",
                        "department_count": "Departments Worked",
                        "category_count": "Categories Used",
                        "cost_delta_pct": "Cost Delta %",
                        "hours_delta_pct": "Hours Delta %",
                        "management_focus": "Management Focus",
                    },
                )
            },
            "labor_employee_summary",
        )
    if dataset == "watchlist":
        return (
            {
                "Watchlist": watchlist_df,
                "DepartmentWatchlist": department_watchlist_df,
                "WorkerWatchlist": worker_watchlist_df,
                "CategoryWatchlist": category_watchlist_df,
            },
            "labor_watchlist",
        )
    return (
        {
            "Summary": summary_df,
            "Departments": department_df,
            "Workers": worker_df,
            "Categories": category_df,
            "Trend": trend_df,
            "MonthlyPattern": monthly_pattern_df,
            "DepartmentTrend": monthly_department_trend,
            "Watchlist": watchlist_df,
            "Detail": _rename_columns(
                detail_df,
                {
                    "labor_date": "Labor Date",
                    "department_name": "Department",
                    "employee_name": "Employee",
                    "employee_code": "Employee Code",
                    "time_category": "Time Category",
                    "labor_cost": "Labor Cost",
                    "paid_hours": "Paid Hours",
                    "effective_rate": "Effective Rate",
                    "status": "Status",
                    "work_rule": "Work Rule",
                },
            ),
        },
        "labor_snapshot",
    )
