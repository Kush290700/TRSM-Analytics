from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from dataclasses import asdict, is_dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
import math
import time
from threading import Lock

import numpy as np
import pandas as pd
from flask import current_app
from flask_login import current_user

from app.cache import cache
from app.services import analytics_utils as au
from app.services import overview_v2 as ov2
from app.services.filters import FilterParams, filters_cache_key, normalize_filters
from data.store import manifest_max_date, manifest_version

FORECAST_TTL_SECONDS = 600  # 10 minutes
FORECAST_TIMEOUT_SECONDS = 6
ALLOWED_METRICS = {"revenue", "profit", "margin"}
MARGIN_BOUNDS = (-100.0, 100.0)
MAX_HISTORY_MONTHS = 144
MODEL_VERSION = "2026-03-19-forecast-1"
MODEL_VERSION_V2 = "2026-03-19-forecast-1"
OUTLIER_METHOD = "hampel"
OUTLIER_WINDOW = 3
OUTLIER_N_SIGMA = 3.0
MIN_MONTHLY_FORECAST_POINTS = 6
MIN_WEEKLY_FORECAST_POINTS = 16
RECENT_SHORT_WINDOW = 24
RECENT_MEDIUM_WINDOW = 36
RECENT_TREND_WINDOW = 18
MAX_CANDIDATE_WINDOWS = 6

_forecast_lock: Lock = Lock()
_forecast_locks: Dict[str, Lock] = {}


def _filters_payload(filters: FilterParams) -> Dict[str, Any]:
    """Return a JSON-safe view of the filters for hashing/logging."""
    params = normalize_filters(filters)
    if is_dataclass(params):
        data = asdict(params)
    else:  # pragma: no cover - defensive
        data = getattr(params, "__dict__", {}) or {}
    for key in ("regions", "methods", "customers", "suppliers", "products", "sales_reps"):
        if key in data and isinstance(data[key], (list, tuple, set)):
            data[key] = sorted(data[key])
    for key in ("start", "end"):
        val = data.get(key)
        if isinstance(val, pd.Timestamp):
            data[key] = val.isoformat()
    return data


def _dataset_marker() -> str:
    return manifest_max_date() or manifest_version() or ""


def _normalize_metric(metric: str | None) -> str:
    value = (metric or "revenue").strip().lower()
    if value == "margin_pct":
        return "margin"
    return value


def _lock_for(key: str) -> Lock:
    with _forecast_lock:
        lock = _forecast_locks.get(key)
        if lock is None:
            lock = Lock()
            _forecast_locks[key] = lock
    return lock


def _hampel_filter(series: pd.Series, window: int = OUTLIER_WINDOW, n_sigma: float = OUTLIER_N_SIGMA) -> Tuple[pd.Series, int]:
    if series.empty:
        return series, 0
    s = series.copy()
    values = s.values.astype(float)
    n = len(values)
    k = 1.4826
    outliers = 0
    for i in range(n):
        start = max(0, i - window)
        end = min(n, i + window + 1)
        window_vals = values[start:end]
        med = np.nanmedian(window_vals)
        mad = np.nanmedian(np.abs(window_vals - med))
        if mad == 0 or np.isnan(mad):
            continue
        threshold = n_sigma * k * mad
        if abs(values[i] - med) > threshold:
            values[i] = med
            outliers += 1
    s[:] = values
    return s, outliers


def _clean_series(series: pd.Series) -> Tuple[pd.Series, int]:
    if series.empty:
        return series, 0
    method = OUTLIER_METHOD
    if method == "hampel":
        return _hampel_filter(series)
    return series, 0


def _backtest_metrics(series: pd.Series) -> Dict[str, Any]:
    values = series.dropna()
    n_total = len(values)
    if n_total < 3:
        return {"mape": None, "smape": None, "n": 0}
    n = min(36, n_total - 1)
    actual = values.iloc[-n:]
    preds: List[float] = []
    for i in range(n):
        idx = n_total - n + i
        if n_total >= 12 and idx - 12 >= 0:
            pred = float(values.iloc[idx - 12])
        else:
            history_slice = values.iloc[:idx]
            window = min(3, len(history_slice)) if len(history_slice) else 1
            pred = float(history_slice.tail(window).mean() if len(history_slice) else values.iloc[0])
        preds.append(pred)
    actual_vals = actual.values.astype(float)
    preds_arr = np.array(preds, dtype=float)
    mask = actual_vals != 0
    mape = None
    if mask.any():
        mape = float(np.mean(np.abs((actual_vals[mask] - preds_arr[mask]) / actual_vals[mask])) * 100)
    denom = np.abs(actual_vals) + np.abs(preds_arr)
    smape = None
    if np.any(denom):
        smape = float(np.mean(2 * np.abs(actual_vals - preds_arr) / np.where(denom == 0, 1, denom)) * 100)
    return {"mape": mape, "smape": smape, "n": int(n)}


def _error_metrics(actual: np.ndarray, predicted: np.ndarray) -> Dict[str, Optional[float]]:
    if actual.size == 0 or predicted.size == 0:
        return {"mape": None, "smape": None, "mae": None}
    err = np.abs(actual - predicted)
    mae = float(np.mean(err)) if err.size else None
    nonzero = actual != 0
    mape = float(np.mean(np.abs((actual[nonzero] - predicted[nonzero]) / actual[nonzero])) * 100) if np.any(nonzero) else None
    denom = np.abs(actual) + np.abs(predicted)
    smape = float(np.mean(2 * np.abs(actual - predicted) / np.where(denom == 0, 1, denom)) * 100) if np.any(denom) else None
    return {"mape": mape, "smape": smape, "mae": mae}


def _split_train_test(series: pd.Series, *, min_train: int = 6, max_test: int = 12) -> Tuple[pd.Series, pd.Series]:
    values = series.dropna().astype(float)
    n = len(values)
    if n <= min_train + 1:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    test_size = min(max_test, max(2, n // 4))
    if (n - test_size) < min_train:
        test_size = n - min_train
    if test_size <= 0:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    train = values.iloc[:-test_size]
    test = values.iloc[-test_size:]
    return train, test


def _forecast_seasonal_naive(history: pd.Series, horizon: int) -> pd.Series:
    if history.empty:
        return pd.Series(dtype=float)
    idx = pd.period_range(start=history.index.max() + 1, periods=horizon, freq="M")
    values: List[float] = []
    for step in range(horizon):
        if len(history) >= 12:
            ref_pos = -12 + step
            if abs(ref_pos) > len(history):
                ref_pos = -12
            values.append(float(history.iloc[ref_pos]))
        else:
            values.append(float(history.iloc[-1]))
    return pd.Series(values, index=idx)


def _forecast_mean(history: pd.Series, horizon: int, window: int = 6) -> pd.Series:
    if history.empty:
        return pd.Series(dtype=float)
    idx = pd.period_range(start=history.index.max() + 1, periods=horizon, freq="M")
    lookback = max(1, min(window, len(history)))
    mean_val = float(history.tail(lookback).mean() or 0.0)
    return pd.Series([mean_val] * horizon, index=idx)


def _forecast_naive_last(history: pd.Series, horizon: int) -> pd.Series:
    if history.empty:
        return pd.Series(dtype=float)
    idx = pd.period_range(start=history.index.max() + 1, periods=horizon, freq="M")
    last = float(history.iloc[-1] or 0.0)
    return pd.Series([last] * horizon, index=idx)


def _forecast_ets(history: pd.Series, horizon: int) -> Tuple[pd.Series, float]:
    if history.empty:
        return pd.Series(dtype=float), 0.0
    from statsmodels.tsa.holtwinters import ExponentialSmoothing  # type: ignore

    def _fit_and_forecast():
        use_damped = len(history) >= 24
        model = ExponentialSmoothing(
            history,
            trend="add",
            seasonal="add",
            seasonal_periods=12,
            initialization_method="estimated",
            damped_trend=use_damped,
        )
        fitted = model.fit(optimized=True)
        fc = pd.Series(fitted.forecast(horizon))
        resid = _residual_band(fitted.fittedvalues, history)
        return fc, resid

    fc_series, resid_std = _forecast_with_timeout(_fit_and_forecast, FORECAST_TIMEOUT_SECONDS)
    return pd.Series(fc_series), float(resid_std or 0.0)


def _evaluate_candidate(
    history: pd.Series,
    *,
    name: str,
    forecast_fn: Callable[[pd.Series, int], pd.Series],
) -> Dict[str, Any]:
    train, test = _split_train_test(history)
    if train.empty or test.empty:
        return {"name": name, "mape": None, "smape": None, "mae": None, "n": 0}
    preds = forecast_fn(train, len(test))
    if preds.empty:
        return {"name": name, "mape": None, "smape": None, "mae": None, "n": 0}
    actual_vals = test.values.astype(float)
    pred_vals = np.array([float(v) if pd.notna(v) else np.nan for v in preds.values], dtype=float)
    mask = np.isfinite(actual_vals) & np.isfinite(pred_vals)
    if not np.any(mask):
        return {"name": name, "mape": None, "smape": None, "mae": None, "n": 0}
    metrics = _error_metrics(actual_vals[mask], pred_vals[mask])
    metrics["name"] = name
    metrics["n"] = int(np.sum(mask))
    return metrics


def _confidence_from_smape(smape: Optional[float]) -> Optional[str]:
    if smape is None:
        return None
    if smape <= 10:
        return "high"
    if smape <= 20:
        return "medium"
    return "low"


def _monthly_from_frame_context(frame_ctx: Any) -> pd.DataFrame:
    """Build a monthly series from a legacy FrameContext (used in tests)."""
    try:
        df = getattr(frame_ctx, "df", None)
        colmap = getattr(frame_ctx, "colmap", {}) or {}
    except Exception:
        return pd.DataFrame()
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()

    date_col = colmap.get("date")
    rev_col = colmap.get("revenue")
    cost_col = colmap.get("cost")
    qty_col = colmap.get("qty")
    if not date_col or date_col not in df.columns or not rev_col or rev_col not in df.columns:
        return pd.DataFrame()

    work = pd.DataFrame()
    work["Date"] = pd.to_datetime(df[date_col], errors="coerce")
    work = work.dropna(subset=["Date"])
    if work.empty:
        return pd.DataFrame()
    work["month"] = work["Date"].dt.to_period("M")
    work["revenue"] = pd.to_numeric(df[rev_col], errors="coerce").fillna(0.0)
    if cost_col and cost_col in df.columns:
        work["cost"] = pd.to_numeric(df[cost_col], errors="coerce").fillna(0.0)
    else:
        work["cost"] = 0.0
    if qty_col and qty_col in df.columns:
        work["qty"] = pd.to_numeric(df[qty_col], errors="coerce").fillna(0.0)
    else:
        work["qty"] = 0.0

    monthly = work.groupby("month")[["revenue", "cost", "qty"]].sum().sort_index()
    if monthly.empty:
        return monthly

    monthly["profit"] = monthly["revenue"] - monthly["cost"]
    monthly["margin_pct"] = au.safe_div(monthly["profit"], monthly["revenue"]) * 100
    monthly["margin_pct"] = (
        monthly["margin_pct"].replace([np.inf, -np.inf], np.nan).clip(lower=MARGIN_BOUNDS[0], upper=MARGIN_BOUNDS[1])
    )
    monthly["asp"] = au.safe_div(monthly["revenue"], monthly["qty"].replace(0, pd.NA))
    monthly["month_start"] = monthly.index.to_timestamp().normalize()
    return monthly


def monthly_series(filters: FilterParams, *, include_partial_current: bool = True) -> Tuple[pd.DataFrame, dict]:
    """
    Aggregated monthly series for the current filters.

    Returns:
        monthly dataframe indexed by Period["M"] with columns revenue, cost, profit, margin_pct, qty, asp
        frame context (for logging/cache metadata)
    """
    ctx: dict = {}
    monthly = pd.DataFrame()

    # TESTING fallback: allow monkeypatched get_filtered_frame to drive forecasts.
    if current_app and current_app.config.get("TESTING"):
        try:
            frame_ctx = ov2.get_filtered_frame(current_user, filters)
            monthly = _monthly_from_frame_context(frame_ctx)
            if not monthly.empty:
                rows_val = len(getattr(frame_ctx, "df", monthly))
                ctx = {
                    "payload": {
                        "health": {"rows": rows_val},
                        "meta": {
                            "version": getattr(frame_ctx, "version", None),
                            "cache_hit": bool(getattr(frame_ctx, "cache_hit", False)),
                        },
                    },
                    "monthly": monthly,
                    "cache_hit": bool(getattr(frame_ctx, "cache_hit", False)),
                    "version": getattr(frame_ctx, "version", None),
                }
        except Exception:
            ctx = {}
            monthly = pd.DataFrame()

    if monthly.empty:
        ctx = ov2.get_bundle_context(filters)
        monthly = ctx.get("monthly")
        if not isinstance(monthly, pd.DataFrame) or monthly.empty:
            return pd.DataFrame(), ctx

    monthly = monthly.sort_index()
    if not include_partial_current and not monthly.empty:
        now_period = pd.Timestamp.utcnow().tz_localize(None).to_period("M")
        if monthly.index.max() == now_period and len(monthly) > 1:
            monthly = monthly.iloc[:-1]

    if "profit" not in monthly.columns:
        monthly["profit"] = monthly.get("revenue", pd.Series(dtype=float)) - monthly.get("cost", pd.Series(dtype=float))
    if "margin_pct" in monthly.columns:
        monthly["margin_pct"] = monthly["margin_pct"].replace([np.inf, -np.inf], np.nan)
        monthly["margin_pct"] = monthly["margin_pct"].clip(lower=MARGIN_BOUNDS[0], upper=MARGIN_BOUNDS[1])
    else:
        monthly["margin_pct"] = au.safe_div(monthly.get("profit"), monthly.get("revenue")) * 100
        monthly["margin_pct"] = monthly["margin_pct"].replace([np.inf, -np.inf], np.nan)
        monthly["margin_pct"] = monthly["margin_pct"].clip(lower=MARGIN_BOUNDS[0], upper=MARGIN_BOUNDS[1])

    if "asp" in monthly.columns:
        monthly["asp"] = monthly["asp"].where(~monthly["asp"].isna(), np.nan)
    monthly["month_start"] = monthly.index.to_timestamp().normalize()
    return monthly, ctx


def _series_for_metric(monthly: pd.DataFrame, metric: str) -> pd.Series:
    metric = _normalize_metric(metric)
    column = {
        "revenue": "revenue",
        "profit": "profit",
        "margin": "margin_pct",
    }.get(metric)
    if not column or column not in monthly.columns:
        return pd.Series(dtype=float)
    series = monthly[column]
    series = pd.to_numeric(series, errors="coerce")
    if isinstance(series.index, pd.PeriodIndex):
        try:
            series = series.asfreq("M")
        except Exception:
            pass
    return series


def _forecast_with_timeout(fn, timeout: float):
    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(fn)
        return fut.result(timeout=timeout)


def _residual_band(fitted: pd.Series, actual: pd.Series) -> float:
    if fitted is None or actual is None or fitted.empty or actual.empty:
        return 0.0
    residuals = actual.align(fitted, join="left")[0] - fitted
    try:
        return float(residuals.std(skipna=True) or 0.0)
    except Exception:
        return 0.0


def _clip_non_negative(series: pd.Series) -> pd.Series:
    return series.apply(lambda v: max(0.0, float(v) if pd.notna(v) else 0.0))


def _bound_value(metric: str, value: float | None) -> float | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if metric in {"revenue", "profit"}:
        return max(0.0, float(value))
    if metric == "margin":
        return float(min(MARGIN_BOUNDS[1], max(MARGIN_BOUNDS[0], float(value))))
    return float(value)


def _apply_metric_bounds(series: pd.Series, metric: str) -> pd.Series:
    if series.empty:
        return series
    metric = _normalize_metric(metric)
    if metric in {"revenue", "profit"}:
        return _clip_non_negative(series)
    if metric == "margin":
        return series.clip(lower=MARGIN_BOUNDS[0], upper=MARGIN_BOUNDS[1])
    return series


def _model_info_payload(payload: Dict[str, Any], history_points: int) -> Dict[str, Any]:
    backtest = payload.get("backtest") or {}
    return {
        "name": payload.get("model_used"),
        "mape": backtest.get("mape"),
        "smape": backtest.get("smape"),
        "n_points": history_points,
    }


def _normalize_granularity(granularity: str | None) -> str:
    token = str(granularity or "monthly").strip().lower()
    if token in {"weekly", "week", "w"}:
        return "weekly"
    return "monthly"


def _future_index(last_ts: pd.Timestamp, horizon: int, granularity: str) -> pd.DatetimeIndex:
    if _normalize_granularity(granularity) == "weekly":
        start = pd.Timestamp(last_ts) + pd.Timedelta(days=7)
        return pd.date_range(start=start.normalize(), periods=horizon, freq="W-MON")
    start = (pd.Timestamp(last_ts) + pd.offsets.MonthBegin(1)).normalize()
    return pd.date_range(start=start, periods=horizon, freq="MS")


def _forecast_naive_generic(history: pd.Series, horizon: int, granularity: str) -> pd.Series:
    if history.empty:
        return pd.Series(dtype=float)
    last = float(history.iloc[-1] or 0.0)
    idx = _future_index(pd.Timestamp(history.index[-1]), horizon, granularity)
    return pd.Series([last] * horizon, index=idx, dtype="float64")


def _forecast_seasonal_naive_generic(history: pd.Series, horizon: int, period: int, granularity: str) -> pd.Series:
    if history.empty:
        return pd.Series(dtype=float)
    idx = _future_index(pd.Timestamp(history.index[-1]), horizon, granularity)
    vals: List[float] = []
    n = len(history)
    for step in range(horizon):
        if n >= period:
            ref = max(0, n - period + (step % period))
        else:
            ref = n - 1
        vals.append(float(history.iloc[ref] or 0.0))
    return pd.Series(vals, index=idx, dtype="float64")


def _forecast_ets_generic(
    history: pd.Series,
    horizon: int,
    *,
    granularity: str,
    seasonal_periods: int | None = None,
    damped: bool = True,
    trend_mode: str | None = "add",
    seasonal_mode: str | None = "add",
) -> Tuple[pd.Series, float]:
    if history.empty:
        return pd.Series(dtype=float), 0.0
    from statsmodels.tsa.holtwinters import ExponentialSmoothing  # type: ignore

    gran = _normalize_granularity(granularity)
    inferred_freq = "W-MON" if gran == "weekly" else "MS"

    def _fit_and_forecast():
        use_seasonal = seasonal_periods is not None and len(history) >= int(seasonal_periods) * 2
        seasonal_token = seasonal_mode if use_seasonal else None
        if seasonal_token == "mul":
            try:
                if bool((history <= 0).any()):
                    seasonal_token = "add"
            except Exception:
                seasonal_token = "add"
        model = ExponentialSmoothing(
            history,
            trend=trend_mode,
            damped_trend=bool(damped),
            seasonal=seasonal_token,
            seasonal_periods=int(seasonal_periods) if use_seasonal else None,
            initialization_method="estimated",
        )
        fitted = model.fit(optimized=True)
        fc = pd.Series(fitted.forecast(horizon))
        if not isinstance(fc.index, pd.DatetimeIndex):
            fc.index = _future_index(pd.Timestamp(history.index[-1]), horizon, granularity)
        else:
            try:
                fc = fc.asfreq(inferred_freq)
            except Exception:
                pass
        resid = _residual_band(pd.Series(fitted.fittedvalues, index=history.index), history)
        return fc, resid

    fc_series, resid_std = _forecast_with_timeout(_fit_and_forecast, FORECAST_TIMEOUT_SECONDS)
    return pd.Series(fc_series), float(resid_std or 0.0)


def _forecast_arima_generic(
    history: pd.Series,
    horizon: int,
    *,
    granularity: str,
    seasonal_periods: int | None = None,
) -> Tuple[pd.Series, float]:
    if history.empty:
        return pd.Series(dtype=float), 0.0
    from statsmodels.tsa.statespace.sarimax import SARIMAX  # type: ignore

    def _fit_and_forecast():
        use_seasonal = seasonal_periods is not None and len(history) >= int(seasonal_periods) * 2
        model = SARIMAX(
            history,
            order=(1, 1, 1),
            seasonal_order=(1, 0, 0, int(seasonal_periods)) if use_seasonal else (0, 0, 0, 0),
            enforce_stationarity=False,
            enforce_invertibility=False,
        )
        fitted = model.fit(disp=False, maxiter=200)
        fc = pd.Series(fitted.forecast(steps=horizon))
        if not isinstance(fc.index, pd.DatetimeIndex):
            fc.index = _future_index(pd.Timestamp(history.index[-1]), horizon, granularity)
        fitted_vals = pd.Series(getattr(fitted, "fittedvalues", pd.Series(dtype=float)))
        if not fitted_vals.empty:
            try:
                fitted_vals.index = history.index[-len(fitted_vals.index):]
            except Exception:
                pass
        resid = _residual_band(fitted_vals, history)
        return fc, resid

    fc_series, resid_std = _forecast_with_timeout(_fit_and_forecast, FORECAST_TIMEOUT_SECONDS)
    return pd.Series(fc_series), float(resid_std or 0.0)


def _rolling_origin_eval(
    history: pd.Series,
    *,
    forecast_fn: Callable[[pd.Series, int], pd.Series],
    holdout_points: int,
) -> Dict[str, Any]:
    clean = history.dropna().astype(float)
    n = len(clean)
    if n < 8:
        return {"mape": None, "smape": None, "mae": None, "n": 0, "resid_std": 0.0}
    holdout = min(max(3, int(holdout_points)), max(3, n // 3))
    if (n - holdout) < 6:
        holdout = max(2, n - 6)
    if holdout <= 1:
        return {"mape": None, "smape": None, "mae": None, "n": 0, "resid_std": 0.0}

    actuals: List[float] = []
    preds: List[float] = []
    for pos in range(n - holdout, n):
        train = clean.iloc[:pos]
        if len(train) < 6:
            continue
        try:
            pred_series = forecast_fn(train, 1)
        except Exception:
            continue
        if pred_series is None or pred_series.empty:
            continue
        try:
            pred = float(pred_series.iloc[0])
            actual = float(clean.iloc[pos])
        except Exception:
            continue
        if not (np.isfinite(pred) and np.isfinite(actual)):
            continue
        actuals.append(actual)
        preds.append(pred)

    if len(actuals) < 2:
        return {"mape": None, "smape": None, "mae": None, "n": int(len(actuals)), "resid_std": 0.0}

    actual_arr = np.asarray(actuals, dtype=float)
    pred_arr = np.asarray(preds, dtype=float)
    metrics = _error_metrics(actual_arr, pred_arr)
    resid = actual_arr - pred_arr
    metrics["n"] = int(len(actual_arr))
    metrics["resid_std"] = float(np.std(resid, ddof=1)) if len(resid) > 1 else 0.0
    return metrics


def _build_weekly_history(filters: FilterParams, metric: str, *, include_current: bool) -> Tuple[pd.Series, Dict[str, Any]]:
    bundle = ov2.build_overview_bundle(filters, include_current_month=bool(include_current), defaulted_window=False)
    trend = bundle.get("trend") or {}
    weekly = trend.get("weekly") or {}
    labels = list(weekly.get("months") or [])
    metric_key = {"revenue": "revenue", "profit": "profit", "margin": "margin_pct"}.get(_normalize_metric(metric), "revenue")
    values = list(weekly.get(metric_key) or [])
    if not labels or not values:
        return pd.Series(dtype="float64"), {"bundle_meta": bundle.get("meta") or {}}
    limit = min(len(labels), len(values))
    idx = pd.to_datetime(labels[:limit], errors="coerce")
    arr = pd.to_numeric(pd.Series(values[:limit]), errors="coerce")
    series = pd.Series(arr.values, index=idx).dropna()
    series = series.sort_index()
    if not include_current and not series.empty:
        now_floor = pd.Timestamp.utcnow().tz_localize(None).normalize()
        series = series[series.index <= now_floor]
    series = series.tail(MAX_HISTORY_MONTHS * 5)
    return series.astype("float64"), {"bundle_meta": bundle.get("meta") or {}}


def _build_monthly_history(filters: FilterParams, metric: str, *, include_current: bool) -> Tuple[pd.Series, Dict[str, Any]]:
    monthly, ctx = monthly_series(filters, include_partial_current=True)
    if not isinstance(monthly, pd.DataFrame) or monthly.empty:
        return pd.Series(dtype="float64"), {"bundle_ctx": ctx, "partial_period": {"detected": False}}

    work = _regularize_monthly_frame(monthly)
    partial_meta = _terminal_month_meta(filters, work)
    if partial_meta.get("detected") and not include_current and len(work.index) > 1:
        work = work.iloc[:-1]
        partial_meta["included"] = False
        partial_meta["excluded"] = True
        partial_meta["note"] = (
            f"Excluded incomplete month {partial_meta.get('period')} from training through "
            f"{partial_meta.get('effective_end')}."
        )
    elif partial_meta.get("detected"):
        partial_meta["included"] = True
        partial_meta["excluded"] = False
        partial_meta["note"] = (
            f"Included incomplete month {partial_meta.get('period')} through {partial_meta.get('effective_end')} in training."
        )
    else:
        partial_meta["included"] = False
        partial_meta["excluded"] = False
        partial_meta["note"] = "Training uses completed months only."

    metric_series = _series_for_metric(work, metric)
    imputed_points = 0
    if metric == "margin":
        metric_series, imputed_points = _fill_margin_gaps(metric_series)
    else:
        metric_series = pd.to_numeric(metric_series, errors="coerce").fillna(0.0)

    metric_series = metric_series.dropna()
    if isinstance(metric_series.index, pd.PeriodIndex):
        metric_series.index = metric_series.index.to_timestamp().normalize()
    metric_series = metric_series.sort_index().astype("float64").tail(MAX_HISTORY_MONTHS)
    meta = {
        "bundle_ctx": ctx,
        "partial_period": partial_meta,
        "history_start": metric_series.index.min().date().isoformat() if len(metric_series.index) else None,
        "history_end": metric_series.index.max().date().isoformat() if len(metric_series.index) else None,
        "imputed_points": int(imputed_points),
    }
    return metric_series, meta


def _coerce_timestamp(value: Any) -> pd.Timestamp | None:
    if value is None:
        return None
    try:
        ts = pd.Timestamp(value)
        if getattr(ts, "tzinfo", None) is not None:
            try:
                ts = ts.tz_convert(None)
            except Exception:
                ts = ts.tz_localize(None)
        return ts.normalize()
    except Exception:
        return None


def _month_end_timestamp(value: pd.Timestamp | None) -> pd.Timestamp | None:
    if value is None:
        return None
    try:
        return (pd.Timestamp(value).normalize() + pd.offsets.MonthEnd(0)).normalize()
    except Exception:
        return None


def _effective_window_end(filters: FilterParams) -> pd.Timestamp | None:
    filter_end = _coerce_timestamp(getattr(filters, "end", None))
    if filter_end is not None:
        return filter_end
    data_end = _coerce_timestamp(manifest_max_date())
    if data_end is not None:
        return data_end
    return _coerce_timestamp(pd.Timestamp.utcnow())


def _regularize_monthly_frame(monthly: pd.DataFrame) -> pd.DataFrame:
    work = monthly.copy()
    if work.empty:
        return work
    if not isinstance(work.index, pd.PeriodIndex):
        idx = pd.to_datetime(work.index, errors="coerce")
        mask = idx.notna()
        work = work.loc[mask].copy()
        if work.empty:
            return work
        work.index = idx[mask].to_period("M")
    work = work.sort_index()
    full_index = pd.period_range(work.index.min(), work.index.max(), freq="M")
    work = work.reindex(full_index)
    for col in ("revenue", "cost", "qty", "orders", "customers", "weight"):
        if col in work.columns:
            work[col] = pd.to_numeric(work[col], errors="coerce").fillna(0.0)
    if "revenue" not in work.columns:
        work["revenue"] = 0.0
    if "cost" not in work.columns:
        work["cost"] = 0.0
    work["profit"] = pd.to_numeric(work.get("revenue"), errors="coerce").fillna(0.0) - pd.to_numeric(work.get("cost"), errors="coerce").fillna(0.0)
    if "qty" not in work.columns:
        work["qty"] = 0.0
    if "orders" in work.columns:
        work["aov"] = au.safe_div(work["revenue"], work["orders"].replace(0, pd.NA))
    if "qty" in work.columns:
        work["asp"] = au.safe_div(work["revenue"], work["qty"].replace(0, pd.NA))
    work["margin_pct"] = au.safe_div(work["profit"], work["revenue"].replace(0, pd.NA)) * 100
    work["margin_pct"] = work["margin_pct"].replace([np.inf, -np.inf], np.nan).clip(lower=MARGIN_BOUNDS[0], upper=MARGIN_BOUNDS[1])
    return work


def _terminal_month_meta(filters: FilterParams, monthly: pd.DataFrame) -> Dict[str, Any]:
    if not isinstance(monthly, pd.DataFrame) or monthly.empty:
        return {"detected": False, "period": None, "effective_end": None}
    last_period = monthly.index.max()
    if not isinstance(last_period, pd.Period):
        return {"detected": False, "period": None, "effective_end": None}
    effective_end = _effective_window_end(filters)
    if effective_end is None:
        return {"detected": False, "period": str(last_period), "effective_end": None}
    last_start = last_period.to_timestamp().normalize()
    last_end = _month_end_timestamp(last_start)
    detected = bool(last_start <= effective_end <= last_end and effective_end < last_end)
    return {
        "detected": detected,
        "period": str(last_period),
        "effective_end": effective_end.date().isoformat(),
        "month_end": last_end.date().isoformat() if last_end is not None else None,
        "days_elapsed": int(effective_end.day) if detected else None,
        "days_in_month": int(last_end.day) if detected and last_end is not None else None,
    }


def _fill_margin_gaps(series: pd.Series) -> Tuple[pd.Series, int]:
    clean = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)
    missing = int(clean.isna().sum())
    if not missing:
        return clean.clip(lower=MARGIN_BOUNDS[0], upper=MARGIN_BOUNDS[1]), 0
    if isinstance(clean.index, (pd.PeriodIndex, pd.DatetimeIndex)) and len(clean) >= 6:
        if isinstance(clean.index, pd.PeriodIndex):
            slots = pd.Series(clean.index.month, index=clean.index)
        else:
            slots = pd.Series(clean.index.month, index=clean.index)
        month_medians = clean.groupby(slots).median()
        for idx in clean[clean.isna()].index:
            try:
                slot = int(idx.month)
            except Exception:
                slot = None
            fill_val = month_medians.get(slot) if slot is not None else None
            if fill_val is not None and pd.notna(fill_val):
                clean.loc[idx] = float(fill_val)
    clean = clean.interpolate(method="linear", limit_direction="both")
    if clean.isna().any():
        fallback = float(clean.dropna().median()) if not clean.dropna().empty else 0.0
        clean = clean.fillna(fallback)
    return clean.clip(lower=MARGIN_BOUNDS[0], upper=MARGIN_BOUNDS[1]), missing


def _seasonal_slot_index(index: Sequence[Any], granularity: str) -> List[int]:
    slots: List[int] = []
    gran = _normalize_granularity(granularity)
    for raw in index:
        ts = pd.Timestamp(raw)
        if gran == "weekly":
            try:
                slots.append(int(ts.isocalendar().week))
            except Exception:
                slots.append(int(ts.weekofyear))
        else:
            slots.append(int(ts.month))
    return slots


def _seasonal_profile(history: pd.Series, seasonal_period: int, granularity: str) -> pd.Series:
    if history.empty or len(history) < max(6, seasonal_period):
        return pd.Series(np.zeros(len(history)), index=history.index, dtype="float64")
    slots = _seasonal_slot_index(history.index, granularity)
    grouped = pd.DataFrame({"y": history.values.astype(float), "slot": slots})
    slot_means = grouped.groupby("slot")["y"].median()
    centered = slot_means - float(slot_means.mean() or 0.0)
    values = [float(centered.get(slot, 0.0)) for slot in slots]
    return pd.Series(values, index=history.index, dtype="float64")


def _future_seasonal_component(history: pd.Series, horizon: int, seasonal_period: int, granularity: str) -> pd.Series:
    if history.empty:
        return pd.Series(dtype="float64")
    idx = _future_index(pd.Timestamp(history.index[-1]), horizon, granularity)
    if len(history) < max(6, seasonal_period):
        return pd.Series(np.zeros(horizon), index=idx, dtype="float64")
    slots = _seasonal_slot_index(history.index, granularity)
    grouped = pd.DataFrame({"y": history.values.astype(float), "slot": slots})
    slot_means = grouped.groupby("slot")["y"].median()
    centered = slot_means - float(slot_means.mean() or 0.0)
    future_slots = _seasonal_slot_index(idx, granularity)
    values = [float(centered.get(slot, 0.0)) for slot in future_slots]
    return pd.Series(values, index=idx, dtype="float64")


def _robust_outlier_adjust(
    history: pd.Series,
    *,
    metric: str,
    granularity: str,
    seasonal_period: int,
) -> Tuple[pd.Series, Dict[str, Any]]:
    clean = history.dropna().astype("float64").copy()
    if clean.empty or len(clean) < 8:
        return clean, {"count": 0, "share_pct": 0.0, "positions": [], "applied": False}

    if len(clean) >= seasonal_period * 2:
        baseline = _seasonal_profile(clean, seasonal_period, granularity)
        baseline = baseline + float((clean - baseline).rolling(window=min(5, len(clean)), min_periods=1).median().iloc[-1] or 0.0)
    else:
        baseline = clean.rolling(window=min(5, len(clean)), center=True, min_periods=1).median()

    residual = clean - baseline
    local_med = residual.rolling(window=min(5, len(residual)), center=True, min_periods=1).median()
    local_mad = (residual - local_med).abs().rolling(window=min(5, len(residual)), center=True, min_periods=1).median()
    scale = (1.4826 * local_mad).replace(0, np.nan)
    z = ((residual - local_med).abs() / scale).replace([np.inf, -np.inf], np.nan)
    flags = z > 4.5
    isolated = flags & ~flags.shift(1, fill_value=False) & ~flags.shift(-1, fill_value=False)
    if int(isolated.sum()) > max(3, int(len(clean) * 0.12)):
        isolated[:] = False
    adjusted = clean.copy()
    if isolated.any():
        threshold = 4.5 * scale
        clipped = local_med + np.sign(residual - local_med) * np.minimum((residual - local_med).abs(), threshold.fillna(np.inf))
        adjusted.loc[isolated] = (baseline + clipped).loc[isolated]
        adjusted = _apply_metric_bounds(adjusted, metric)
    positions = [pd.Timestamp(idx).date().isoformat() for idx in adjusted.index[isolated]]
    return adjusted, {
        "count": int(isolated.sum()),
        "share_pct": round(float(isolated.sum()) / float(len(clean)) * 100.0, 1) if len(clean) else 0.0,
        "positions": positions[:6],
        "applied": bool(isolated.any()),
    }


def _weighted_mean(values: np.ndarray, weights: np.ndarray) -> float | None:
    if values.size == 0 or weights.size == 0:
        return None
    total_weight = float(np.sum(weights))
    if total_weight <= 0:
        return None
    return float(np.sum(values * weights) / total_weight)


def _safe_mean_abs(values: np.ndarray) -> float:
    if values.size == 0:
        return 0.0
    return float(np.mean(np.abs(values)))


def _selection_score(metrics: Dict[str, Any], *, prefer_recent: bool = False) -> float:
    smape = float(metrics.get("smape") or 100.0)
    wape = float(metrics.get("wape") or smape)
    rmse_pct = float(metrics.get("rmse_pct") or max(smape, wape))
    bias_pct = abs(float(metrics.get("bias_pct") or 0.0))
    direction_acc = float(metrics.get("directional_accuracy") or 0.0)
    score = (smape * 0.36) + (wape * 0.24) + (rmse_pct * 0.18) + (bias_pct * 0.12) + ((100.0 - direction_acc) * 0.10)
    if prefer_recent:
        score -= 2.5
    return float(score)


def _quality_score_from_metrics(metrics: Dict[str, Any]) -> float:
    smape = float(metrics.get("smape") or 100.0)
    wape = float(metrics.get("wape") or smape)
    bias_pct = abs(float(metrics.get("bias_pct") or 0.0))
    direction_acc = float(metrics.get("directional_accuracy") or 0.0)
    penalty = (smape * 0.45) + (wape * 0.25) + (bias_pct * 0.10) + ((100.0 - direction_acc) * 0.20)
    return float(max(0.0, min(100.0, 100.0 - penalty)))


def _recent_slope(series: pd.Series, window: int = RECENT_TREND_WINDOW) -> float:
    clean = series.dropna().astype("float64")
    if clean.empty:
        return 0.0
    sample = clean.tail(max(3, min(window, len(clean))))
    if len(sample) < 2:
        return 0.0
    x = np.arange(len(sample), dtype=float)
    try:
        return float(np.polyfit(x, sample.values.astype(float), 1)[0])
    except Exception:
        return float((sample.iloc[-1] - sample.iloc[0]) / max(1, len(sample) - 1))


def _seasonality_strength(history: pd.Series, seasonal_period: int, granularity: str) -> float:
    clean = history.dropna().astype("float64")
    if clean.empty or len(clean) < seasonal_period:
        return 0.0
    try:
        ac = float(clean.autocorr(lag=seasonal_period) or 0.0)
    except Exception:
        ac = 0.0
    profile = _seasonal_profile(clean, seasonal_period, granularity)
    signal = float(np.nanstd(profile.values.astype(float))) if not profile.empty else 0.0
    noise = float(np.nanstd(clean.values.astype(float))) if len(clean) else 0.0
    profile_ratio = (signal / noise) if noise > 0 else 0.0
    score = max(0.0, min(100.0, (max(ac, 0.0) * 65.0) + min(35.0, profile_ratio * 55.0)))
    return float(score)


def _level_shift_score(history: pd.Series) -> float:
    clean = history.dropna().astype("float64")
    if len(clean) < 12:
        return 0.0
    recent_window = min(12, max(6, len(clean) // 4))
    recent = clean.tail(recent_window)
    prior = clean.iloc[:-recent_window].tail(min(24, max(12, len(clean) - recent_window)))
    if prior.empty:
        return 0.0
    recent_mean = float(recent.mean() or 0.0)
    prior_mean = float(prior.mean() or 0.0)
    scale = float(clean.std(ddof=0) or abs(prior_mean) or 1.0)
    level_delta = abs(recent_mean - prior_mean) / max(scale, 1e-6)
    pct_delta = abs(recent_mean - prior_mean) / max(abs(prior_mean), 1e-6)
    return float(max(0.0, min(100.0, (level_delta * 30.0) + (pct_delta * 55.0))))


def _volatility_pct(history: pd.Series) -> float:
    clean = history.dropna().astype("float64")
    if clean.empty:
        return 0.0
    mean_abs = _safe_mean_abs(clean.values.astype(float))
    if mean_abs <= 0:
        return 0.0
    return float((clean.std(ddof=0) / mean_abs) * 100.0)


def _zero_share_pct(history: pd.Series) -> float:
    clean = history.dropna().astype("float64")
    if clean.empty:
        return 0.0
    return float((clean.eq(0).sum() / len(clean)) * 100.0)


def _trend_strength_score(history: pd.Series) -> float:
    clean = history.dropna().astype("float64")
    if len(clean) < 6:
        return 0.0
    slope = abs(_recent_slope(clean))
    level = max(_safe_mean_abs(clean.tail(min(12, len(clean))).values.astype(float)), 1e-6)
    return float(max(0.0, min(100.0, (slope / level) * 1200.0)))


def _score_label(score: float) -> str:
    if score >= 80:
        return "High"
    if score >= 60:
        return "Medium"
    if score >= 40:
        return "Watch"
    return "Limited"


def _confidence_tier(score: float) -> str:
    if score >= 72:
        return "high"
    if score >= 52:
        return "medium"
    return "low"


def _rolling_eval(
    history: pd.Series,
    *,
    forecast_fn: Callable[[pd.Series, int], pd.Series],
    holdout_points: int,
    eval_horizon: int = 1,
    max_windows: int = MAX_CANDIDATE_WINDOWS,
) -> Dict[str, Any]:
    clean = history.dropna().astype("float64")
    n = len(clean)
    if n < 6:
        return {
            "mape": None,
            "smape": None,
            "wape": None,
            "mae": None,
            "rmse": None,
            "mae_pct": None,
            "rmse_pct": None,
            "bias": None,
            "bias_pct": None,
            "directional_accuracy": None,
            "validation_windows": 0,
            "resid_std": 0.0,
        }

    holdout = min(max(3, int(holdout_points)), max(3, n - 4))
    origins = list(range(max(3, n - holdout), n))
    if max_windows and len(origins) > max_windows:
        origins = origins[-max_windows:]

    actuals: List[float] = []
    preds: List[float] = []
    weights: List[float] = []
    direction_hits: List[float] = []
    residuals: List[float] = []

    for offset, pos in enumerate(origins, start=1):
        train = clean.iloc[:pos]
        actual_window = clean.iloc[pos : pos + max(1, eval_horizon)]
        if train.empty or actual_window.empty:
            continue
        try:
            pred_series = forecast_fn(train, len(actual_window))
        except Exception:
            continue
        if pred_series is None or pred_series.empty:
            continue
        pred_vals = np.asarray([float(v) if pd.notna(v) else np.nan for v in pred_series.iloc[: len(actual_window)].values], dtype=float)
        actual_vals = np.asarray(actual_window.values, dtype=float)
        mask = np.isfinite(actual_vals) & np.isfinite(pred_vals)
        if not np.any(mask):
            continue
        weight = float(offset)
        baseline = float(train.iloc[-1]) if len(train) else 0.0
        actual_first = float(actual_vals[mask][0])
        pred_first = float(pred_vals[mask][0])
        actual_dir = np.sign(actual_first - baseline)
        pred_dir = np.sign(pred_first - baseline)
        direction_hits.append(100.0 if actual_dir == pred_dir else 0.0)
        for actual_val, pred_val in zip(actual_vals[mask], pred_vals[mask]):
            actuals.append(float(actual_val))
            preds.append(float(pred_val))
            weights.append(weight)
            residuals.append(float(actual_val - pred_val))

    if not actuals:
        return {
            "mape": None,
            "smape": None,
            "wape": None,
            "mae": None,
            "rmse": None,
            "mae_pct": None,
            "rmse_pct": None,
            "bias": None,
            "bias_pct": None,
            "directional_accuracy": None,
            "validation_windows": 0,
            "resid_std": 0.0,
        }

    actual_arr = np.asarray(actuals, dtype=float)
    pred_arr = np.asarray(preds, dtype=float)
    weight_arr = np.asarray(weights, dtype=float)
    err = pred_arr - actual_arr
    abs_err = np.abs(err)
    denom = np.abs(actual_arr) + np.abs(pred_arr)
    nonzero = np.abs(actual_arr) > 1e-9
    mean_abs_actual = max(_safe_mean_abs(actual_arr), 1e-6)
    mae = _weighted_mean(abs_err, weight_arr)
    rmse = float(np.sqrt(_weighted_mean(np.square(err), weight_arr) or 0.0))
    smape = _weighted_mean((2.0 * np.abs(actual_arr - pred_arr) / np.where(denom == 0, 1.0, denom)) * 100.0, weight_arr) if np.any(denom) else 0.0
    mape = _weighted_mean((np.abs((actual_arr[nonzero] - pred_arr[nonzero]) / actual_arr[nonzero])) * 100.0, weight_arr[nonzero]) if np.any(nonzero) else None
    total_actual = float(np.sum(np.abs(actual_arr) * weight_arr))
    wape = float(np.sum(abs_err * weight_arr) / total_actual * 100.0) if total_actual > 0 else None
    bias = _weighted_mean(err, weight_arr)
    bias_pct = float(np.sum(err * weight_arr) / total_actual * 100.0) if total_actual > 0 else None
    direction_acc = float(np.mean(direction_hits)) if direction_hits else None
    return {
        "mape": mape,
        "smape": smape,
        "wape": wape,
        "mae": mae,
        "rmse": rmse,
        "mae_pct": (float(mae) / mean_abs_actual * 100.0) if mae is not None else None,
        "rmse_pct": (float(rmse) / mean_abs_actual * 100.0) if rmse is not None else None,
        "bias": bias,
        "bias_pct": bias_pct,
        "directional_accuracy": direction_acc,
        "validation_windows": int(len(direction_hits)),
        "resid_std": float(np.std(np.asarray(residuals, dtype=float), ddof=1)) if len(residuals) > 1 else 0.0,
    }


def _forecast_robust_trend_generic(
    history: pd.Series,
    horizon: int,
    *,
    granularity: str,
    seasonal_period: int | None = None,
    recent_window: int = RECENT_TREND_WINDOW,
    damp: float = 0.88,
) -> pd.Series:
    clean = history.dropna().astype("float64")
    if clean.empty:
        return pd.Series(dtype="float64")
    sample = clean.tail(max(3, min(recent_window, len(clean))))
    idx = _future_index(pd.Timestamp(clean.index[-1]), horizon, granularity)
    base = float(sample.tail(min(3, len(sample))).median() if len(sample) else 0.0)
    slope = _recent_slope(sample, window=len(sample))
    future = np.asarray([base + (slope * step * (damp ** max(0, step - 1))) for step in range(1, horizon + 1)], dtype=float)
    if seasonal_period is not None and len(clean) >= seasonal_period:
        season = _future_seasonal_component(clean, horizon, seasonal_period, granularity)
        future = future + season.values.astype(float)
    return pd.Series(future, index=idx, dtype="float64")


def _forecast_level_baseline_generic(
    history: pd.Series,
    horizon: int,
    *,
    granularity: str,
    window: int = 6,
) -> pd.Series:
    clean = history.dropna().astype("float64")
    if clean.empty:
        return pd.Series(dtype="float64")
    sample = clean.tail(max(2, min(window, len(clean))))
    base = float(sample.median() if len(sample) else 0.0)
    idx = _future_index(pd.Timestamp(clean.index[-1]), horizon, granularity)
    return pd.Series([base] * horizon, index=idx, dtype="float64")


def _forecast_theta_generic(
    history: pd.Series,
    horizon: int,
    *,
    granularity: str,
    seasonal_period: int | None = None,
    recent_window: int = RECENT_SHORT_WINDOW,
) -> pd.Series:
    clean = history.dropna().astype("float64")
    if clean.empty:
        return pd.Series(dtype="float64")
    sample = clean.tail(max(6, min(recent_window, len(clean))))
    idx = _future_index(pd.Timestamp(clean.index[-1]), horizon, granularity)
    if seasonal_period is not None and len(sample) >= seasonal_period:
        seasonal_hist = _seasonal_profile(sample, seasonal_period, granularity)
        deseasonal = sample - seasonal_hist
    else:
        seasonal_hist = pd.Series(np.zeros(len(sample)), index=sample.index, dtype="float64")
        deseasonal = sample
    level = float(deseasonal.ewm(alpha=0.35, adjust=False).mean().iloc[-1] if not deseasonal.empty else 0.0)
    slope = _recent_slope(deseasonal, window=min(12, len(deseasonal)))
    future_season = _future_seasonal_component(sample, horizon, seasonal_period or 1, granularity)
    preds: List[float] = []
    last_val = float(deseasonal.iloc[-1]) if len(deseasonal) else level
    for step in range(1, horizon + 1):
        line = last_val + (slope * step)
        ses = level
        preds.append((0.58 * ses) + (0.42 * line))
    future = np.asarray(preds, dtype=float)
    if seasonal_period is not None and len(sample) >= seasonal_period:
        future = future + future_season.values.astype(float)
    return pd.Series(future, index=idx, dtype="float64")


def _forecast_stl_trend_generic(
    history: pd.Series,
    horizon: int,
    *,
    granularity: str,
    seasonal_period: int,
    recent_window: int = RECENT_MEDIUM_WINDOW,
) -> Tuple[pd.Series, float]:
    clean = history.dropna().astype("float64")
    if clean.empty:
        return pd.Series(dtype="float64"), 0.0
    sample = clean.tail(max(seasonal_period * 2, min(recent_window, len(clean))))
    if len(sample) < max(8, seasonal_period * 2):
        fc = _forecast_theta_generic(sample, horizon, granularity=granularity, seasonal_period=seasonal_period)
        return fc, float(sample.diff().std(skipna=True) or 0.0)

    from statsmodels.tsa.seasonal import STL  # type: ignore

    def _fit_and_forecast():
        stl = STL(sample, period=seasonal_period, robust=True)
        fitted = stl.fit()
        deseasonal = pd.Series(sample.values - fitted.seasonal, index=sample.index, dtype="float64")
        base = float(deseasonal.tail(min(3, len(deseasonal))).mean() if len(deseasonal) else 0.0)
        slope = _recent_slope(deseasonal, window=min(18, len(deseasonal)))
        idx = _future_index(pd.Timestamp(sample.index[-1]), horizon, granularity)
        future_season = _future_seasonal_component(pd.Series(fitted.seasonal, index=sample.index), horizon, seasonal_period, granularity)
        preds = np.asarray([base + (slope * step * (0.9 ** max(0, step - 1))) for step in range(1, horizon + 1)], dtype=float)
        preds = preds + future_season.values.astype(float)
        resid_std = float(np.nanstd(fitted.resid)) if len(fitted.resid) else 0.0
        return pd.Series(preds, index=idx, dtype="float64"), resid_std

    fc_series, resid_std = _forecast_with_timeout(_fit_and_forecast, FORECAST_TIMEOUT_SECONDS)
    return pd.Series(fc_series), float(resid_std or 0.0)


def _candidate_wrapper(
    fn: Callable[..., Any],
    *,
    window_points: int | None = None,
    as_tuple: bool = False,
    **kwargs: Any,
) -> Callable[[pd.Series, int], pd.Series]:
    def _wrapped(history: pd.Series, horizon: int) -> pd.Series:
        sample = history.tail(window_points) if window_points and len(history) > window_points else history
        result = fn(sample, horizon, **kwargs)
        if as_tuple:
            return result[0] if isinstance(result, tuple) else result
        return result

    return _wrapped


def _candidate_residual(
    fn: Callable[..., Any],
    history: pd.Series,
    horizon: int,
    *,
    window_points: int | None = None,
    fallback_std: float = 0.0,
    **kwargs: Any,
) -> Tuple[pd.Series, float]:
    sample = history.tail(window_points) if window_points and len(history) > window_points else history
    result = fn(sample, horizon, **kwargs)
    if isinstance(result, tuple):
        series, resid_std = result
        return pd.Series(series), float(resid_std or 0.0)
    return pd.Series(result), float(fallback_std or 0.0)


def _model_display_name(name: str | None) -> str | None:
    mapping = {
        "seasonal_naive": "Seasonal Naive",
        "seasonal_naive_recent24": "Seasonal Naive (Recent 24)",
        "holt_winters_add": "Holt-Winters Additive",
        "holt_winters_mul": "Holt-Winters Multiplicative",
        "holt_winters_recent36": "Holt-Winters Recent 36",
        "stl_trend_recent36": "STL + Damped Trend",
        "stl_trend_full": "STL + Damped Trend (Full)",
        "theta_recent24": "Theta-Style Trend",
        "robust_trend_recent18": "Robust Recent Trend",
        "level_baseline": "Conservative Baseline",
    }
    return mapping.get(str(name or "").strip().lower(), name)


def _forecastability_score(
    *,
    history_points: int,
    selected_metrics: Dict[str, Any],
    seasonality_strength: float,
    trend_strength: float,
    volatility_pct: float,
    level_shift_score: float,
    zero_share_pct: float,
    outlier_share_pct: float,
    partial_included: bool,
) -> float:
    score = 58.0
    score += min(18.0, (history_points / 36.0) * 18.0)
    if history_points < 12:
        score -= 20.0
    elif history_points < 18:
        score -= 10.0
    score += min(10.0, seasonality_strength * 0.10)
    score += min(8.0, trend_strength * 0.08)
    smape = float(selected_metrics.get("smape") or 35.0)
    score -= min(22.0, smape * 0.55)
    score -= min(14.0, volatility_pct * 0.12)
    score -= min(10.0, level_shift_score * 0.10)
    score -= min(12.0, zero_share_pct * 0.12)
    score -= min(8.0, outlier_share_pct * 0.35)
    if partial_included:
        score -= 6.0
    return float(max(0.0, min(100.0, score)))


def _selected_model_reason(selected: Dict[str, Any], diagnostics: Dict[str, Any]) -> str:
    name = str(selected.get("name") or "")
    history_mode = str(selected.get("history_mode") or "full")
    seasonality_strength = float(diagnostics.get("seasonality_strength_score") or 0.0)
    level_shift = float(diagnostics.get("level_shift_score") or 0.0)
    if name.startswith("stl_"):
        if history_mode.startswith("recent") or level_shift >= 35:
            return "Recent regime shift was material, so a decomposition model anchored level and trend on the latest business run-rate."
        return "A decomposition model balanced recurring seasonality with smoother trend behavior across the full history."
    if name.startswith("holt_winters"):
        if "mul" in name:
            return "Positive seasonal amplitude scaled with business level, so multiplicative Holt-Winters outperformed flatter additive baselines."
        if history_mode.startswith("recent"):
            return "Recent Holt-Winters fit beat longer-history alternatives, indicating current trend and level matter more than older periods."
        return "Holt-Winters captured both recurring seasonality and trend with lower validation error than simpler baselines."
    if name.startswith("seasonal_naive"):
        if seasonality_strength >= 45:
            return "Recurring monthly seasonality dominated the series, so the safest high-signal forecast came from repeating comparable periods."
        return "A seasonal baseline was the most stable option under the current filtered slice."
    if name.startswith("theta_"):
        return "A theta-style trend model balanced recent direction with conservative mean reversion better than heavier smoothing models."
    if name.startswith("robust_trend"):
        return "Recent movement was informative but noisy, so a damped recent-trend model outperformed broader history fits."
    return "Filtered history is limited or unstable, so the forecast stayed on a conservative baseline."


def _build_forecast_summary(metric: str, selected: Dict[str, Any], diagnostics: Dict[str, Any], partial_meta: Dict[str, Any]) -> str:
    metric_label = {"revenue": "Revenue", "profit": "Profit", "margin": "Margin"}.get(metric, metric.title())
    confidence = diagnostics.get("confidence_badge") or "Watch"
    seasonality_strength = float(diagnostics.get("seasonality_strength_score") or 0.0)
    level_shift = float(diagnostics.get("level_shift_score") or 0.0)
    partial_note = ""
    if partial_meta.get("detected") and partial_meta.get("excluded"):
        partial_note = " Incomplete current month was excluded from training."
    elif partial_meta.get("detected") and partial_meta.get("included"):
        partial_note = " Incomplete current month is included, so near-term uncertainty is wider."
    if selected.get("name", "").startswith("seasonal_naive") and seasonality_strength >= 45:
        return f"{metric_label} outlook follows a strong recurring seasonal pattern with {confidence.lower()} confidence.{partial_note}"
    if level_shift >= 35 and str(selected.get("history_mode") or "").startswith("recent"):
        return f"{metric_label} outlook is anchored to the recent regime rather than older history because the business level shifted materially.{partial_note}"
    return f"{metric_label} outlook balances recent trend, seasonal rhythm, and forecast uncertainty with {confidence.lower()} confidence.{partial_note}"


def _build_candidate_specs(
    history: pd.Series,
    *,
    metric: str,
    granularity: str,
    seasonal_period: int,
    diagnostics: Dict[str, Any],
) -> List[Dict[str, Any]]:
    specs: List[Dict[str, Any]] = []
    n = len(history)
    positive_only = metric in {"revenue", "profit"} and bool((history.dropna() > 0).all())
    seasonality_strength = float(diagnostics.get("seasonality_strength_score") or 0.0)
    level_shift = float(diagnostics.get("level_shift_score") or 0.0)

    def _add(
        name: str,
        family: str,
        history_mode: str,
        forecast_fn: Callable[[pd.Series, int], pd.Series],
        runner: Callable[[pd.Series, int], Tuple[pd.Series, float]],
        *,
        max_windows: int = MAX_CANDIDATE_WINDOWS,
        priority: int = 5,
    ) -> None:
        specs.append(
            {
                "name": name,
                "family": family,
                "history_mode": history_mode,
                "forecast_fn": forecast_fn,
                "runner": runner,
                "max_windows": max_windows,
                "priority": int(priority),
            }
        )

    _add(
        "level_baseline",
        "fallback",
        "recent_6",
        _candidate_wrapper(_forecast_level_baseline_generic, window_points=6, granularity=granularity, window=6),
        lambda s, h: (_forecast_level_baseline_generic(s.tail(6), h, granularity=granularity, window=6), float(s.tail(6).std(skipna=True) or 0.0)),
        priority=9,
    )
    _add(
        "robust_trend_recent18",
        "trend",
        "recent_18",
        _candidate_wrapper(
            _forecast_robust_trend_generic,
            window_points=min(RECENT_TREND_WINDOW, n),
            granularity=granularity,
            seasonal_period=seasonal_period if seasonality_strength >= 30 and n >= seasonal_period else None,
            recent_window=min(RECENT_TREND_WINDOW, n),
        ),
        lambda s, h: (
            _forecast_robust_trend_generic(
                s.tail(min(RECENT_TREND_WINDOW, len(s))),
                h,
                granularity=granularity,
                seasonal_period=seasonal_period if seasonality_strength >= 30 and len(s) >= seasonal_period else None,
                recent_window=min(RECENT_TREND_WINDOW, len(s)),
            ),
            float(s.tail(min(RECENT_TREND_WINDOW, len(s))).diff().std(skipna=True) or 0.0),
        ),
        priority=7,
    )

    if n >= 8:
        _add(
            "theta_recent24",
            "theta",
            "recent_24",
            _candidate_wrapper(
                _forecast_theta_generic,
                window_points=min(RECENT_SHORT_WINDOW, n),
                granularity=granularity,
                seasonal_period=seasonal_period if n >= seasonal_period else None,
                recent_window=min(RECENT_SHORT_WINDOW, n),
            ),
            lambda s, h: (
                _forecast_theta_generic(
                    s.tail(min(RECENT_SHORT_WINDOW, len(s))),
                    h,
                    granularity=granularity,
                    seasonal_period=seasonal_period if len(s) >= seasonal_period else None,
                    recent_window=min(RECENT_SHORT_WINDOW, len(s)),
                ),
                float(s.tail(min(RECENT_SHORT_WINDOW, len(s))).diff().std(skipna=True) or 0.0),
            ),
            priority=5,
        )

    if n >= seasonal_period:
        _add(
            "seasonal_naive",
            "seasonal_naive",
            "full",
            _candidate_wrapper(_forecast_seasonal_naive_generic, granularity=granularity, period=seasonal_period),
            lambda s, h: (
                _forecast_seasonal_naive_generic(s, h, seasonal_period, granularity),
                float((s - s.shift(seasonal_period)).std(skipna=True) or 0.0),
            ),
            priority=4,
        )

    if n >= max(12, seasonal_period * 2):
        _add(
            "stl_trend_recent36",
            "stl",
            "recent_36",
            _candidate_wrapper(
                _forecast_stl_trend_generic,
                window_points=min(RECENT_MEDIUM_WINDOW, n),
                as_tuple=True,
                granularity=granularity,
                seasonal_period=seasonal_period,
                recent_window=min(RECENT_MEDIUM_WINDOW, n),
            ),
            lambda s, h: _candidate_residual(
                _forecast_stl_trend_generic,
                s,
                h,
                window_points=min(RECENT_MEDIUM_WINDOW, len(s)),
                granularity=granularity,
                seasonal_period=seasonal_period,
                recent_window=min(RECENT_MEDIUM_WINDOW, len(s)),
            ),
            max_windows=4,
            priority=2,
        )
        _add(
            "holt_winters_recent36",
            "ets",
            "recent_36",
            _candidate_wrapper(
                _forecast_ets_generic,
                window_points=min(RECENT_MEDIUM_WINDOW, n),
                as_tuple=True,
                granularity=granularity,
                seasonal_periods=seasonal_period,
                damped=True,
                seasonal_mode="add",
            ),
            lambda s, h: _candidate_residual(
                _forecast_ets_generic,
                s,
                h,
                window_points=min(RECENT_MEDIUM_WINDOW, len(s)),
                granularity=granularity,
                seasonal_periods=seasonal_period,
                damped=True,
                seasonal_mode="add",
            ),
            max_windows=4,
            priority=3,
        )
        if positive_only and seasonality_strength >= 45:
            _add(
                "holt_winters_mul",
                "ets",
                "recent_36",
                _candidate_wrapper(
                    _forecast_ets_generic,
                    window_points=min(RECENT_MEDIUM_WINDOW, n),
                    as_tuple=True,
                    granularity=granularity,
                    seasonal_periods=seasonal_period,
                    damped=True,
                    seasonal_mode="mul",
                ),
                lambda s, h: _candidate_residual(
                    _forecast_ets_generic,
                    s,
                    h,
                    window_points=min(RECENT_MEDIUM_WINDOW, len(s)),
                    granularity=granularity,
                    seasonal_periods=seasonal_period,
                    damped=True,
                    seasonal_mode="mul",
                ),
                max_windows=4,
                priority=3,
            )

    if n >= max(18, seasonal_period * 2) and level_shift < 40:
        _add(
            "stl_trend_full",
            "stl",
            "full",
            _candidate_wrapper(
                _forecast_stl_trend_generic,
                as_tuple=True,
                granularity=granularity,
                seasonal_period=seasonal_period,
                recent_window=min(MAX_HISTORY_MONTHS, n),
            ),
            lambda s, h: _candidate_residual(
                _forecast_stl_trend_generic,
                s,
                h,
                granularity=granularity,
                seasonal_period=seasonal_period,
                recent_window=min(MAX_HISTORY_MONTHS, len(s)),
            ),
            max_windows=4,
            priority=4,
        )

    return specs


def _upper_cap(history: pd.Series) -> float:
    if history.empty:
        return 0.0
    recent_mean = float(history.tail(min(12, len(history))).mean() or 0.0)
    recent_max = float(history.tail(min(24, len(history))).max() or 0.0)
    hist_max = float(history.max() or 0.0)
    return max(recent_mean * 2.1, recent_max * 1.4, hist_max * 1.25, 0.0)


def _v2_band_for_step(resid_std: float | None, step: int) -> float | None:
    if resid_std is None or not np.isfinite(resid_std) or resid_std <= 0:
        return None
    horizon_step = max(1, int(step))
    return float(1.645 * float(resid_std) * math.sqrt(horizon_step))


def _serialize_v2_history(history: pd.Series) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    hist = history.dropna().astype("float64")
    for idx, value in hist.items():
        ts = pd.Timestamp(idx)
        rows.append({"ds": ts.date().isoformat(), "y": float(value)})
    return rows


def _serialize_v2_forecast(
    forecast: pd.Series,
    *,
    metric: str,
    resid_std: float | None,
    upper_cap: float | None,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    fc = forecast.copy() if isinstance(forecast, pd.Series) else pd.Series(dtype="float64")
    for step, (idx, raw_value) in enumerate(fc.items(), start=1):
        ts = pd.Timestamp(idx)
        yhat = _bound_value(metric, float(raw_value) if pd.notna(raw_value) else None)
        band = _v2_band_for_step(resid_std, step)
        lo = None
        hi = None
        if yhat is not None and band is not None:
            lo = yhat - band
            hi = yhat + band
        lo = _bound_value(metric, lo)
        hi = _bound_value(metric, hi)
        if metric in {"revenue", "profit"} and upper_cap is not None and hi is not None:
            hi = min(float(upper_cap), float(hi))
        rows.append({"ds": ts.date().isoformat(), "yhat": yhat, "yhat_lower": lo, "yhat_upper": hi})
    return rows


def _serialize_v2_series(
    history: pd.Series,
    forecast: pd.Series,
    *,
    granularity: str,
    metric: str,
    resid_std: float | None,
    upper_cap: float | None,
) -> Tuple[List[Dict[str, Any]], bool]:
    gran = _normalize_granularity(granularity)
    hist = history.dropna().astype(float).copy()
    fc = forecast.copy()
    if fc is None or fc.empty:
        fc = pd.Series(dtype="float64")

    bounded = False
    out: List[Dict[str, Any]] = []
    all_idx = list(hist.index) + [idx for idx in fc.index if idx not in hist.index]
    for idx in all_idx:
        ts = pd.Timestamp(idx)
        actual = float(hist.loc[idx]) if idx in hist.index else None
        forecast_val = None
        lo = None
        hi = None
        if idx in fc.index:
            raw = fc.loc[idx]
            if pd.notna(raw):
                forecast_val = float(raw)
                if metric in {"revenue", "profit"}:
                    forecast_val = max(0.0, forecast_val)
                    if upper_cap is not None and upper_cap > 0 and forecast_val > upper_cap:
                        forecast_val = upper_cap
                        bounded = True
                elif metric == "margin":
                    forecast_val = float(min(MARGIN_BOUNDS[1], max(MARGIN_BOUNDS[0], forecast_val)))
                band = _v2_band_for_step(resid_std, len([i for i in fc.index if i <= idx]))
                if band is not None and band > 0:
                    lo = forecast_val - band
                    hi = forecast_val + band
                    if metric in {"revenue", "profit"}:
                        lo = max(0.0, lo)
                        if upper_cap is not None and upper_cap > 0:
                            hi = min(upper_cap, hi)
                    elif metric == "margin":
                        lo = float(min(MARGIN_BOUNDS[1], max(MARGIN_BOUNDS[0], lo)))
                        hi = float(min(MARGIN_BOUNDS[1], max(MARGIN_BOUNDS[0], hi)))

        token = ts.strftime("%Y-%m") if gran == "monthly" else ts.strftime("%Y-%m-%d")
        out.append(
            {
                "t": token,
                "actual": actual,
                "forecast": forecast_val,
                "lo": lo,
                "hi": hi,
            }
        )
    return out, bounded


def forecast_metric_v2(
    filters: FilterParams,
    *,
    metric: str = "revenue",
    horizon: int = 6,
    granularity: str = "monthly",
    include_current: bool = False,
) -> Dict[str, Any]:
    metric = _normalize_metric(metric)
    if metric not in ALLOWED_METRICS:
        raise ValueError(f"Unsupported metric '{metric}'. Allowed: {', '.join(sorted(ALLOWED_METRICS))}")

    gran = _normalize_granularity(granularity)
    try:
        horizon_points = int(horizon)
    except Exception:
        horizon_points = 6
    if gran == "weekly":
        horizon_points = max(4, min(horizon_points, 24))
    else:
        horizon_points = max(3, min(horizon_points, 12))

    dataset_marker = _dataset_marker()
    cache_key = filters_cache_key(
        current_user,
        filters,
        extras={
            "scope": "overview_forecast_v2",
            "metric": metric,
            "granularity": gran,
            "horizon": horizon_points,
            "dataset": dataset_marker,
            "model_v": MODEL_VERSION_V2,
            "include_current": bool(include_current),
        },
    )
    cached = cache.get(cache_key)
    if isinstance(cached, dict):
        cached["cache_hit"] = True
        return cached

    min_points = MIN_WEEKLY_FORECAST_POINTS if gran == "weekly" else MIN_MONTHLY_FORECAST_POINTS
    notes: List[str] = []
    warnings: List[str] = []

    if gran == "weekly":
        raw_history, context = _build_weekly_history(filters, metric, include_current=include_current)
        partial_meta = {
            "detected": False,
            "included": False,
            "excluded": False,
            "note": "Weekly forecast uses the filtered weekly history.",
        }
        imputed_points = 0
    else:
        raw_history, context = _build_monthly_history(filters, metric, include_current=include_current)
        partial_meta = dict((context or {}).get("partial_period") or {})
        imputed_points = int((context or {}).get("imputed_points") or 0)

    raw_history = raw_history.dropna().astype("float64")
    if gran == "weekly":
        seasonal_period = 52 if len(raw_history) >= 104 else 13
    else:
        seasonal_period = 12
    holdout_points = min(8 if gran == "weekly" else 6, max(3, len(raw_history) // 3 if len(raw_history) else 3))

    if len(raw_history) < min_points:
        reason = f"Insufficient history for {gran} forecast ({len(raw_history)} points, need at least {min_points})."
        payload = {
            "eligible": False,
            "reason": reason,
            "summary": reason,
            "warnings": [reason],
            "notes": [reason, "Forecast stays disabled until more comparable history is available under the active filters."],
            "metric": metric,
            "granularity": gran,
            "horizon": horizon_points,
            "model": {
                "name": None,
                "display_name": None,
                "smape": None,
                "mae": None,
                "wape": None,
                "train_points": int(len(raw_history)),
                "holdout_points": int(min(holdout_points, max(0, len(raw_history) - 1))),
                "confidence": "low",
                "confidence_badge": "Limited",
                "forecastability_score": 0.0,
                "quality_score": 0.0,
                "candidate_count": 0,
                "runner_ups": [],
                "candidates": [],
            },
            "diagnostics": {
                "history_points": int(len(raw_history)),
                "history_start": raw_history.index.min().date().isoformat() if len(raw_history.index) else None,
                "history_end": raw_history.index.max().date().isoformat() if len(raw_history.index) else None,
                "training_cutoff": raw_history.index.max().date().isoformat() if len(raw_history.index) else None,
                "seasonality_strength_score": 0.0,
                "trend_strength_score": 0.0,
                "volatility_pct": 0.0,
                "level_shift_score": 0.0,
                "zero_share_pct": 0.0,
                "outliers_adjusted": 0,
                "partial_period": partial_meta,
            },
            "history": _serialize_v2_history(raw_history),
            "forecast": [],
            "series": [],
            "cache_hit": False,
            "dataset_version": dataset_marker,
            "model_version": MODEL_VERSION_V2,
        }
        cache.set(cache_key, payload, timeout=FORECAST_TTL_SECONDS)
        return payload

    clean_history, outlier_meta = _robust_outlier_adjust(
        raw_history,
        metric=metric,
        granularity=gran,
        seasonal_period=max(4, seasonal_period),
    )
    if clean_history.empty:
        clean_history = raw_history.copy()

    seasonality_strength = _seasonality_strength(clean_history, max(4, seasonal_period), gran)
    trend_strength = _trend_strength_score(clean_history)
    volatility_pct = _volatility_pct(clean_history)
    level_shift_score = _level_shift_score(clean_history)
    zero_share_pct = _zero_share_pct(raw_history if metric != "margin" else clean_history)

    diagnostics: Dict[str, Any] = {
        "history_points": int(len(raw_history)),
        "train_points": int(len(clean_history)),
        "history_start": raw_history.index.min().date().isoformat() if len(raw_history.index) else None,
        "history_end": raw_history.index.max().date().isoformat() if len(raw_history.index) else None,
        "training_cutoff": clean_history.index.max().date().isoformat() if len(clean_history.index) else None,
        "seasonality_period": int(seasonal_period),
        "seasonality_strength_score": round(float(seasonality_strength), 1),
        "seasonality_strength_label": _score_label(float(seasonality_strength)),
        "trend_strength_score": round(float(trend_strength), 1),
        "volatility_pct": round(float(volatility_pct), 1),
        "level_shift_score": round(float(level_shift_score), 1),
        "level_shift_detected": bool(level_shift_score >= 35.0),
        "zero_share_pct": round(float(zero_share_pct), 1),
        "outliers_adjusted": int(outlier_meta.get("count") or 0),
        "outlier_share_pct": float(outlier_meta.get("share_pct") or 0.0),
        "outlier_positions": outlier_meta.get("positions") or [],
        "imputed_points": int(imputed_points),
        "partial_period": partial_meta,
        "history_scope": "recent-aware",
    }

    if partial_meta.get("note"):
        notes.append(str(partial_meta.get("note")))
    if outlier_meta.get("count"):
        notes.append(f"Adjusted {int(outlier_meta.get('count') or 0)} isolated outlier period(s) before fitting.")
    if imputed_points:
        notes.append(f"Filled {int(imputed_points)} missing margin period(s) to stabilize bounded margin forecasting.")
    if diagnostics["level_shift_detected"]:
        notes.append("Recent level shift detected, so recent-history candidates receive extra weight in selection.")
    if seasonality_strength >= 45:
        notes.append("Strong recurring seasonality detected in the training history.")
    elif seasonality_strength < 20:
        warnings.append("Seasonality is weak under the active filters, so the forecast leans more on recent trend than repeating annual patterns.")
    if zero_share_pct >= 30:
        warnings.append("Sparse periods are elevated under the current filters; forecast uncertainty is wider.")

    candidate_specs = _build_candidate_specs(
        clean_history,
        metric=metric,
        granularity=gran,
        seasonal_period=max(4, seasonal_period),
        diagnostics=diagnostics,
    )

    candidates: List[Dict[str, Any]] = []
    for spec in candidate_specs:
        metrics = _rolling_eval(
            clean_history,
            forecast_fn=spec["forecast_fn"],
            holdout_points=holdout_points,
            eval_horizon=min(2, horizon_points) if gran == "monthly" else 1,
            max_windows=int(spec.get("max_windows") or MAX_CANDIDATE_WINDOWS),
        )
        prefer_recent = str(spec.get("history_mode") or "").startswith("recent") and diagnostics["level_shift_detected"]
        selection_score = _selection_score(metrics, prefer_recent=prefer_recent) if metrics.get("smape") is not None else float("inf")
        quality_score = _quality_score_from_metrics(metrics) if metrics.get("smape") is not None else 0.0
        candidates.append(
            {
                **spec,
                **metrics,
                "selection_score": round(float(selection_score), 3) if np.isfinite(selection_score) else None,
                "quality_score": round(float(quality_score), 1),
                "display_name": _model_display_name(spec.get("name")),
            }
        )

    valid_candidates = [c for c in candidates if c.get("smape") is not None and c.get("selection_score") is not None]
    ranked_candidates = sorted(
        valid_candidates,
        key=lambda item: (
            float(item.get("selection_score")) if item.get("selection_score") is not None else float("inf"),
            int(item.get("priority") or 9),
            float(item.get("smape")) if item.get("smape") is not None else float("inf"),
        ),
    )

    selected = ranked_candidates[0] if ranked_candidates else next((c for c in candidates if c.get("name") == "level_baseline"), None)
    if selected is None:
        selected = {
            "name": "level_baseline",
            "display_name": "Conservative Baseline",
            "history_mode": "recent_6",
            "family": "fallback",
            "runner": lambda s, h: (_forecast_level_baseline_generic(s, h, granularity=gran, window=6), float(s.std(skipna=True) or 0.0)),
            "smape": None,
            "wape": None,
            "mae": None,
            "rmse": None,
            "bias_pct": None,
            "directional_accuracy": None,
            "quality_score": 0.0,
            "selection_score": None,
            "priority": 9,
        }
        warnings.append("Model validation was incomplete, so the forecast fell back to a conservative baseline.")

    try:
        forecast_series, resid_std = selected["runner"](clean_history, horizon_points)
    except Exception:
        forecast_series = _forecast_level_baseline_generic(clean_history, horizon_points, granularity=gran, window=6)
        resid_std = float(clean_history.std(skipna=True) or 0.0)
        warnings.append("Selected model failed during final scoring; conservative baseline used instead.")
        selected["name"] = "level_baseline"
        selected["display_name"] = "Conservative Baseline"
        selected["family"] = "fallback"

    forecast_series = _apply_metric_bounds(pd.Series(forecast_series), metric)
    if not isinstance(forecast_series.index, pd.DatetimeIndex):
        forecast_series.index = _future_index(pd.Timestamp(clean_history.index[-1]), horizon_points, gran)

    cap_val = _upper_cap(clean_history) if metric in {"revenue", "profit"} else None
    series_rows, bounded = _serialize_v2_series(
        raw_history,
        forecast_series,
        granularity=gran,
        metric=metric,
        resid_std=float(resid_std or selected.get("resid_std") or 0.0),
        upper_cap=cap_val,
    )
    if bounded:
        notes.append("Applied a high-end cap to keep projected scale within observed business bounds.")

    history_rows = _serialize_v2_history(raw_history)
    forecast_rows = _serialize_v2_forecast(
        forecast_series,
        metric=metric,
        resid_std=float(resid_std or selected.get("resid_std") or 0.0),
        upper_cap=cap_val,
    )

    selected_metrics = {
        "smape": selected.get("smape"),
        "wape": selected.get("wape"),
        "mae": selected.get("mae"),
        "rmse": selected.get("rmse"),
        "bias_pct": selected.get("bias_pct"),
        "directional_accuracy": selected.get("directional_accuracy"),
        "quality_score": selected.get("quality_score"),
    }
    forecastability = _forecastability_score(
        history_points=int(len(clean_history)),
        selected_metrics=selected_metrics,
        seasonality_strength=float(seasonality_strength),
        trend_strength=float(trend_strength),
        volatility_pct=float(volatility_pct),
        level_shift_score=float(level_shift_score),
        zero_share_pct=float(zero_share_pct),
        outlier_share_pct=float(outlier_meta.get("share_pct") or 0.0),
        partial_included=bool(partial_meta.get("included")),
    )
    combined_confidence_score = max(0.0, min(100.0, (forecastability * 0.55) + (float(selected.get("quality_score") or 0.0) * 0.45)))
    confidence_badge = _score_label(combined_confidence_score)
    confidence_tier = _confidence_tier(combined_confidence_score)
    diagnostics["forecastability_score"] = round(float(forecastability), 1)
    diagnostics["confidence_score"] = round(float(combined_confidence_score), 1)
    diagnostics["confidence_badge"] = confidence_badge

    if combined_confidence_score < 40:
        warnings.append("Forecastability is limited under the current filters; use the outlook directionally rather than as a hard plan.")
    elif combined_confidence_score < 60:
        warnings.append("Forecast quality is moderate; validate the outlook against the underlying movers and risk panels.")

    model_reason = _selected_model_reason(selected, diagnostics)
    notes.append(model_reason)
    summary = _build_forecast_summary(metric, selected, diagnostics, partial_meta)

    runner_ups = []
    for cand in ranked_candidates[1:3]:
        runner_ups.append(
            {
                "name": cand.get("name"),
                "display_name": cand.get("display_name"),
                "smape": cand.get("smape"),
                "wape": cand.get("wape"),
                "selection_score": cand.get("selection_score"),
                "history_mode": cand.get("history_mode"),
            }
        )

    model_payload = {
        "name": selected.get("name"),
        "display_name": selected.get("display_name"),
        "family": selected.get("family"),
        "history_mode": selected.get("history_mode"),
        "smape": selected.get("smape"),
        "mape": selected.get("mape"),
        "wape": selected.get("wape"),
        "mae": selected.get("mae"),
        "rmse": selected.get("rmse"),
        "bias_pct": selected.get("bias_pct"),
        "directional_accuracy": selected.get("directional_accuracy"),
        "selection_score": selected.get("selection_score"),
        "quality_score": round(float(selected.get("quality_score") or 0.0), 1),
        "forecastability_score": round(float(forecastability), 1),
        "train_points": int(len(clean_history)),
        "holdout_points": int(holdout_points),
        "validation_windows": int(selected.get("validation_windows") or 0),
        "confidence": confidence_tier,
        "confidence_badge": confidence_badge,
        "candidate_count": int(len(candidates)),
        "selection_reason": model_reason,
        "runner_ups": runner_ups,
        "candidates": [
            {
                "name": c.get("name"),
                "display_name": c.get("display_name"),
                "family": c.get("family"),
                "history_mode": c.get("history_mode"),
                "smape": c.get("smape"),
                "wape": c.get("wape"),
                "mae": c.get("mae"),
                "rmse": c.get("rmse"),
                "bias_pct": c.get("bias_pct"),
                "directional_accuracy": c.get("directional_accuracy"),
                "selection_score": c.get("selection_score"),
                "quality_score": c.get("quality_score"),
            }
            for c in ranked_candidates[:6]
        ],
    }

    payload = {
        "eligible": True,
        "reason": None,
        "summary": summary,
        "warnings": warnings,
        "notes": notes,
        "metric": metric,
        "granularity": gran,
        "horizon": horizon_points,
        "history": history_rows,
        "forecast": forecast_rows,
        "series": series_rows,
        "model": model_payload,
        "diagnostics": diagnostics,
        "confidence": confidence_tier,
        "confidence_badge": confidence_badge,
        "cache_hit": False,
        "dataset_version": dataset_marker,
        "model_version": MODEL_VERSION_V2,
    }
    cache.set(cache_key, payload, timeout=FORECAST_TTL_SECONDS)
    return payload


def forecast_metric(
    filters: FilterParams,
    *,
    metric: str = "revenue",
    horizon_months: int = 6,
    include_current_month: bool = False,
) -> Dict[str, Any]:
    metric = _normalize_metric(metric)
    if metric not in ALLOWED_METRICS:
        raise ValueError(f"Unsupported metric '{metric}'. Allowed: {', '.join(sorted(ALLOWED_METRICS))}")
    try:
        horizon = max(1, min(int(horizon_months), 12))
    except Exception:
        horizon = 6

    dataset_marker = _dataset_marker()
    cache_key = filters_cache_key(
        current_user,
        filters,
        extras={
            "scope": "overview_forecast_legacy",
            "metric": metric,
            "horizon": horizon,
            "dataset": dataset_marker,
            "model_v": MODEL_VERSION,
            "include_current_month": bool(include_current_month),
        },
    )
    cached = cache.get(cache_key)
    if isinstance(cached, dict):
        cached["cache_hit"] = True
        return cached

    v2_payload = forecast_metric_v2(
        filters,
        metric=metric,
        horizon=horizon,
        granularity="monthly",
        include_current=include_current_month,
    )

    history_rows = list(v2_payload.get("history") or [])
    forecast_rows = list(v2_payload.get("forecast") or [])
    model = dict(v2_payload.get("model") or {})
    diagnostics = dict(v2_payload.get("diagnostics") or {})
    warnings = list(v2_payload.get("warnings") or [])
    notes = list(v2_payload.get("notes") or [])

    legacy_series: List[Dict[str, Any]] = []
    for row in v2_payload.get("series") or []:
        token = row.get("t")
        month = f"{token}-01" if token and len(str(token)) == 7 else token
        legacy_series.append(
            {
                "month": month,
                "actual": row.get("actual"),
                "yhat": row.get("forecast"),
                "yhat_lower": row.get("lo"),
                "yhat_upper": row.get("hi"),
            }
        )

    payload: Dict[str, Any] = {
        "metric": metric,
        "horizon_months": horizon,
        "include_partial_current_month": bool(include_current_month),
        "history_points": int(diagnostics.get("history_points") or model.get("train_points") or 0),
        "model_used": model.get("name"),
        "warnings": warnings + [note for note in notes if note not in warnings],
        "series": legacy_series,
        "history": history_rows,
        "forecast": forecast_rows,
        "model_info": {
            "name": model.get("name"),
            "display_name": model.get("display_name"),
            "mape": model.get("mape"),
            "smape": model.get("smape"),
            "mae": model.get("mae"),
            "wape": model.get("wape"),
            "n_points": int(diagnostics.get("train_points") or model.get("train_points") or 0),
            "candidate_count": int(model.get("candidate_count") or 0),
            "quality_score": model.get("quality_score"),
            "forecastability_score": model.get("forecastability_score"),
        },
        "model_candidates": list(model.get("candidates") or []),
        "error": None if v2_payload.get("eligible") else (v2_payload.get("reason") or "Forecast unavailable."),
        "cache_hit": False,
        "model_version": MODEL_VERSION,
        "dataset_version": dataset_marker,
        "backtest": {
            "mape": model.get("mape"),
            "smape": model.get("smape"),
            "mae": model.get("mae"),
            "wape": model.get("wape"),
            "rmse": model.get("rmse"),
            "bias_pct": model.get("bias_pct"),
            "directional_accuracy": model.get("directional_accuracy"),
            "n": model.get("validation_windows"),
        },
        "model_selection": {
            "selected_model": model.get("name"),
            "criterion": "rolling_walk_forward_weighted_score",
            "selection_score": model.get("selection_score"),
        },
        "confidence": model.get("confidence"),
        "confidence_badge": model.get("confidence_badge"),
        "last_train_date": diagnostics.get("training_cutoff"),
        "summary": v2_payload.get("summary"),
        "eligible": v2_payload.get("eligible"),
        "reason": v2_payload.get("reason"),
        "diagnostics": diagnostics,
    }

    if payload["error"] and not payload["series"]:
        payload["history"] = history_rows
        payload["forecast"] = []

    cache.set(cache_key, payload, timeout=FORECAST_TTL_SECONDS)
    return payload


def _serialize_history(history: pd.Series) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    hist_idx = history.index if isinstance(history.index, pd.PeriodIndex) else pd.Index([])
    for period in hist_idx:
        month = period.to_timestamp().normalize() if hasattr(period, "to_timestamp") else None
        raw_val = history.loc[period]
        val = None
        if pd.notna(raw_val):
            try:
                val = float(raw_val)
            except Exception:
                val = None
        out.append(
            {
                "ds": month.strftime("%Y-%m-%d") if month is not None else None,
                "y": val,
            }
        )
    return out


def _serialize_forecast(forecast: pd.Series, *, resid_std: float = 0.0, metric: str = "revenue") -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    fc_idx = forecast.index if isinstance(forecast.index, pd.PeriodIndex) else pd.Index([])
    band = float(resid_std or 0.0)
    metric = _normalize_metric(metric)
    for period in fc_idx:
        month = period.to_timestamp().normalize() if hasattr(period, "to_timestamp") else None
        raw_val = forecast.loc[period]
        yhat = None
        if pd.notna(raw_val):
            try:
                yhat = float(raw_val)
            except Exception:
                yhat = None
        lower = None
        upper = None
        if yhat is not None and band:
            lower = yhat - 1.96 * band
            upper = yhat + 1.96 * band
        yhat = _bound_value(metric, yhat)
        lower = _bound_value(metric, lower)
        upper = _bound_value(metric, upper)
        out.append(
            {
                "ds": month.strftime("%Y-%m-%d") if month is not None else None,
                "yhat": yhat,
                "yhat_lower": lower,
                "yhat_upper": upper,
            }
        )
    return out


def _serialize_series(history: pd.Series, forecast: pd.Series, resid_std: float = 0.0, metric: str = "revenue") -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    hist_idx = history.index if isinstance(history.index, pd.PeriodIndex) else pd.Index([])
    fc_idx = forecast.index if isinstance(forecast.index, pd.PeriodIndex) else pd.Index([])
    hist_map = {p: float(history.loc[p]) if pd.notna(history.loc[p]) else None for p in hist_idx}
    fc_map = {p: float(forecast.loc[p]) if pd.notna(forecast.loc[p]) else None for p in fc_idx}

    all_periods = list(hist_idx) + [p for p in fc_idx if p not in hist_idx]
    band = float(resid_std or 0.0)
    metric = _normalize_metric(metric)

    for period in all_periods:
        month = period.to_timestamp().normalize() if hasattr(period, "to_timestamp") else None
        actual = hist_map.get(period)
        yhat = fc_map.get(period)
        lower = None
        upper = None
        if yhat is not None and band:
            lower = yhat - 1.96 * band
            upper = yhat + 1.96 * band
        out.append(
            {
                "month": month.strftime("%Y-%m-%d") if month is not None else None,
                "actual": actual,
                "yhat": _bound_value(metric, yhat),
                "yhat_lower": _bound_value(metric, lower),
                "yhat_upper": _bound_value(metric, upper),
            }
        )
    return out
