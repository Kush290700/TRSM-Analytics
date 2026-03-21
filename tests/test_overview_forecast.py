import types

import pandas as pd
import pytest

from app.services.filters import FilterParams
from app.services import overview_forecast
from app.services import overview_v2 as ov2


def _fake_ctx(df):
    return ov2.FrameContext(
        df=df,
        colmap={
            "date": "Date",
            "revenue": "Revenue",
            "cost": "Cost",
            "qty": "QuantityShipped",
            "order_id": "OrderId",
            "customer_id": "CustomerId",
            "weight": None,
        },
        flags={},
        missing=[],
        window={},
        last_refresh=None,
        version="test",
        cache_hit=False,
    )


def test_monthly_series_computes_profit_and_asp(monkeypatch, app):
    df = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-05", "2024-01-20", "2024-02-02"]),
            "Revenue": [100, 200, 300],
            "Cost": [40, 60, 90],
            "QuantityShipped": [10, 20, 30],
            "OrderId": [1, 2, 3],
            "CustomerId": ["c1", "c2", "c1"],
        }
    )
    ctx = _fake_ctx(df)
    monkeypatch.setattr(ov2, "get_filtered_frame", lambda user, filters: ctx)

    with app.test_request_context():
        monthly, _ = overview_forecast.monthly_series(FilterParams())

    jan = monthly.loc[pd.Period("2024-01", freq="M")]
    feb = monthly.loc[pd.Period("2024-02", freq="M")]
    assert pytest.approx(jan["revenue"]) == 300
    assert pytest.approx(jan["profit"]) == 200
    assert pytest.approx(jan["asp"]) == 10
    assert -100 <= jan["margin_pct"] <= 100
    assert pytest.approx(feb["profit"]) == 210


def test_forecast_clips_negative_values(monkeypatch, app):
    monthly = pd.DataFrame(
        {
            "revenue": [-100, -80, -60, -50, -40, -30, -25, -20, -15, -10, -5, -1],
            "cost": [0.0] * 12,
            "qty": [10.0] * 12,
            "profit": [-100, -80, -60, -50, -40, -30, -25, -20, -15, -10, -5, -1],
            "margin_pct": [-100.0] * 12,
        },
        index=pd.period_range("2023-01", periods=12, freq="M"),
    )
    ctx = ov2.FrameContext(
        df=pd.DataFrame({"Date": pd.date_range("2023-01-01", periods=12, freq="MS")}),
        colmap={},
        flags={},
        missing=[],
        window={},
        last_refresh=None,
        version="test",
        cache_hit=False,
    )
    monkeypatch.setattr(overview_forecast, "monthly_series", lambda filters, include_partial_current=False: (monthly, ctx))

    with app.test_request_context():
        result = overview_forecast.forecast_metric(FilterParams(), metric="revenue", horizon_months=3)

    yhat_values = [pt.get("yhat") for pt in result.get("series", []) if pt.get("yhat") is not None]
    assert yhat_values, "forecast should include predictions"
    assert all(v >= 0 for v in yhat_values)


def test_forecast_cache_hit(monkeypatch, app):
    fake_cache = types.SimpleNamespace(store={})

    def _get(key):
        return fake_cache.store.get(key)

    def _set(key, value, timeout=None):
        fake_cache.store[key] = value

    fake_cache.get = _get
    fake_cache.set = _set
    monkeypatch.setattr(overview_forecast, "cache", fake_cache)

    calls = {"count": 0}

    monthly = pd.DataFrame(
        {
            "revenue": [100.0] * 12,
            "cost": [40.0] * 12,
            "qty": [10.0] * 12,
            "profit": [60.0] * 12,
            "margin_pct": [60.0] * 12,
        },
        index=pd.period_range("2023-01", periods=12, freq="M"),
    )
    ctx = ov2.FrameContext(
        df=pd.DataFrame({"Date": pd.date_range("2023-01-01", periods=12, freq="MS")}),
        colmap={},
        flags={},
        missing=[],
        window={},
        last_refresh=None,
        version="test",
        cache_hit=False,
    )

    def _monthly(filters, include_partial_current=False):
        calls["count"] += 1
        return monthly, ctx

    monkeypatch.setattr(overview_forecast, "monthly_series", _monthly)

    with app.test_request_context():
        first = overview_forecast.forecast_metric(FilterParams(), metric="revenue", horizon_months=3)
        second = overview_forecast.forecast_metric(FilterParams(), metric="revenue", horizon_months=3)

    assert calls["count"] == 1
    assert second.get("cache_hit") is True


def test_forecast_returns_metadata(monkeypatch, app):
    monthly = pd.DataFrame(
        {
            "revenue": [100.0] * 18,
            "cost": [40.0] * 18,
            "qty": [10.0] * 18,
            "profit": [60.0] * 18,
            "margin_pct": [60.0] * 18,
        },
        index=pd.period_range("2023-01", periods=18, freq="M"),
    )
    ctx = ov2.FrameContext(
        df=pd.DataFrame({"Date": pd.date_range("2023-01-01", periods=18, freq="MS")}),
        colmap={},
        flags={},
        missing=[],
        window={},
        last_refresh=None,
        version="test",
        cache_hit=False,
    )
    monkeypatch.setattr(overview_forecast, "monthly_series", lambda filters, include_partial_current=False: (monthly, ctx))

    with app.test_request_context():
        result = overview_forecast.forecast_metric(FilterParams(), metric="revenue", horizon_months=3)

    assert "backtest" in result
    assert "model_version" in result
    assert "last_train_date" in result
    assert "model_info" in result


def test_forecast_history_serialization(monkeypatch, app):
    monthly = pd.DataFrame(
        {
            "revenue": [100.0] * 12,
            "cost": [40.0] * 12,
            "qty": [10.0] * 12,
            "profit": [60.0] * 12,
            "margin_pct": [60.0] * 12,
        },
        index=pd.period_range("2023-01", periods=12, freq="M"),
    )
    ctx = ov2.FrameContext(
        df=pd.DataFrame({"Date": pd.date_range("2023-01-01", periods=12, freq="MS")}),
        colmap={},
        flags={},
        missing=[],
        window={},
        last_refresh=None,
        version="test",
        cache_hit=False,
    )
    monkeypatch.setattr(overview_forecast, "monthly_series", lambda filters, include_partial_current=False: (monthly, ctx))

    with app.test_request_context():
        result = overview_forecast.forecast_metric(FilterParams(), metric="revenue", horizon_months=3)

    history = result.get("history") or []
    assert history, "history series should be present"
    assert all(pt.get("ds") for pt in history)
    assert all(isinstance(pt.get("y"), (int, float)) or pt.get("y") is None for pt in history)


def test_margin_series_handles_zero_revenue(monkeypatch, app):
    monthly = pd.DataFrame(
        {
            "revenue": [0.0, 100.0, 0.0, 200.0, 150.0, 0.0, 120.0, 130.0, 0.0, 180.0, 160.0, 0.0],
            "cost": [0.0, 60.0, 0.0, 120.0, 90.0, 0.0, 70.0, 80.0, 0.0, 110.0, 100.0, 0.0],
            "qty": [0.0] * 12,
            "profit": [0.0, 40.0, 0.0, 80.0, 60.0, 0.0, 50.0, 50.0, 0.0, 70.0, 60.0, 0.0],
            "margin_pct": [0.0, 40.0, float("nan"), 40.0, 40.0, float("nan"), 41.7, 38.5, float("nan"), 38.9, 37.5, float("nan")],
        },
        index=pd.period_range("2023-01", periods=12, freq="M"),
    )
    ctx = ov2.FrameContext(
        df=pd.DataFrame({"Date": pd.date_range("2023-01-01", periods=12, freq="MS")}),
        colmap={},
        flags={},
        missing=[],
        window={},
        last_refresh=None,
        version="test",
        cache_hit=False,
    )
    monkeypatch.setattr(overview_forecast, "monthly_series", lambda filters, include_partial_current=False: (monthly, ctx))

    with app.test_request_context():
        result = overview_forecast.forecast_metric(FilterParams(), metric="margin", horizon_months=3)

    history = result.get("history") or []
    assert history, "margin history should be present even with zero revenue months"
    assert all(pt.get("ds") for pt in history)
    for pt in history:
        val = pt.get("y")
        if val is None:
            continue
        assert not pd.isna(val)


def test_forecast_v2_short_history_uses_limited_confidence(monkeypatch, app):
    series = pd.Series(
        [100.0] * 10,
        index=pd.date_range("2024-01-01", periods=10, freq="MS"),
        dtype="float64",
    )
    monkeypatch.setattr(overview_forecast, "_build_monthly_history", lambda *a, **k: (series, {}))
    monkeypatch.setattr(overview_forecast, "cache", types.SimpleNamespace(get=lambda _k: None, set=lambda *_a, **_k: None))

    with app.test_request_context():
        payload = overview_forecast.forecast_metric_v2(
            FilterParams(),
            metric="revenue",
            horizon=6,
            granularity="monthly",
        )

    assert payload["eligible"] is True
    assert payload["model"]["train_points"] == 10
    assert payload["model"]["confidence"] in {"low", "medium"}
    assert payload["confidence_badge"] in {"Limited", "Watch", "Medium"}
    assert payload["diagnostics"]["history_points"] == 10
    assert payload["notes"]


def test_forecast_v2_prefers_seasonal_or_decomposition_model_when_pattern_is_strong(monkeypatch, app):
    pattern = [120.0, 135.0, 150.0, 165.0, 180.0, 195.0, 210.0, 200.0, 185.0, 170.0, 155.0, 140.0]
    vals = pattern * 3
    series = pd.Series(vals, index=pd.date_range("2022-01-01", periods=len(vals), freq="MS"), dtype="float64")
    monkeypatch.setattr(overview_forecast, "_build_monthly_history", lambda *a, **k: (series, {}))
    monkeypatch.setattr(overview_forecast, "cache", types.SimpleNamespace(get=lambda _k: None, set=lambda *_a, **_k: None))

    with app.test_request_context():
        payload = overview_forecast.forecast_metric_v2(
            FilterParams(),
            metric="revenue",
            horizon=6,
            granularity="monthly",
        )

    assert payload["eligible"] is True
    assert payload["model"]["name"] in {"seasonal_naive", "stl_trend_recent36", "stl_trend_full", "holt_winters_mul", "holt_winters_recent36"}
    assert payload["model"]["smape"] is not None
    assert payload["diagnostics"]["seasonality_strength_score"] >= 40


def test_forecast_v2_clips_negative_forecasts(monkeypatch, app):
    series = pd.Series(
        [180.0, 175.0, 190.0, 200.0, 210.0, 195.0, 205.0, 215.0, 220.0, 225.0, 230.0, 235.0] * 2,
        index=pd.date_range("2023-01-01", periods=24, freq="MS"),
        dtype="float64",
    )
    monkeypatch.setattr(overview_forecast, "_build_monthly_history", lambda *a, **k: (series, {}))
    monkeypatch.setattr(
        overview_forecast,
        "_forecast_level_baseline_generic",
        lambda history, horizon, granularity, window=6: pd.Series(
            [-50.0] * horizon,
            index=pd.date_range(history.index.max() + pd.offsets.MonthBegin(1), periods=horizon, freq="MS"),
            dtype="float64",
        ),
    )
    monkeypatch.setattr(
        overview_forecast,
        "_forecast_theta_generic",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("theta unavailable in test")),
    )
    monkeypatch.setattr(
        overview_forecast,
        "_forecast_stl_trend_generic",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("stl unavailable in test")),
    )
    monkeypatch.setattr(overview_forecast, "cache", types.SimpleNamespace(get=lambda _k: None, set=lambda *_a, **_k: None))

    with app.test_request_context():
        payload = overview_forecast.forecast_metric_v2(
            FilterParams(),
            metric="revenue",
            horizon=6,
            granularity="monthly",
        )

    forecasts = [row.get("forecast") for row in payload.get("series", []) if row.get("forecast") is not None]
    assert forecasts
    assert all(float(v) >= 0 for v in forecasts)


def test_build_monthly_history_excludes_partial_terminal_month_by_default(monkeypatch, app):
    monthly = pd.DataFrame(
        {
            "revenue": [100.0, 120.0, 60.0],
            "cost": [50.0, 60.0, 30.0],
            "qty": [10.0, 12.0, 6.0],
        },
        index=pd.period_range("2026-01", periods=3, freq="M"),
    )
    monkeypatch.setattr(overview_forecast, "monthly_series", lambda filters, include_partial_current=True: (monthly, {}))

    with app.test_request_context():
        series, meta = overview_forecast._build_monthly_history(
            FilterParams(start=pd.Timestamp("2026-01-01"), end=pd.Timestamp("2026-03-19")),
            metric="revenue",
            include_current=False,
        )

    assert list(series.index.strftime("%Y-%m")) == ["2026-01", "2026-02"]
    assert meta["partial_period"]["detected"] is True
    assert meta["partial_period"]["excluded"] is True


def test_build_monthly_history_can_include_partial_terminal_month(monkeypatch, app):
    monthly = pd.DataFrame(
        {
            "revenue": [100.0, 120.0, 60.0],
            "cost": [50.0, 60.0, 30.0],
            "qty": [10.0, 12.0, 6.0],
        },
        index=pd.period_range("2026-01", periods=3, freq="M"),
    )
    monkeypatch.setattr(overview_forecast, "monthly_series", lambda filters, include_partial_current=True: (monthly, {}))

    with app.test_request_context():
        series, meta = overview_forecast._build_monthly_history(
            FilterParams(start=pd.Timestamp("2026-01-01"), end=pd.Timestamp("2026-03-19")),
            metric="revenue",
            include_current=True,
        )

    assert list(series.index.strftime("%Y-%m")) == ["2026-01", "2026-02", "2026-03"]
    assert meta["partial_period"]["detected"] is True
    assert meta["partial_period"]["included"] is True


def test_forecast_v2_long_history_not_flat_under_trend_shift(monkeypatch, app):
    first = [95.0, 96.0, 98.0, 100.0, 102.0, 105.0, 108.0, 110.0, 112.0, 114.0, 116.0, 118.0] * 4
    second = [165.0, 170.0, 178.0, 185.0, 194.0, 202.0, 210.0, 218.0, 225.0, 232.0, 240.0, 248.0] * 2
    vals = first + second
    series = pd.Series(vals, index=pd.date_range("2018-01-01", periods=len(vals), freq="MS"), dtype="float64")
    monkeypatch.setattr(overview_forecast, "_build_monthly_history", lambda *a, **k: (series, {"partial_period": {"detected": False}}))
    monkeypatch.setattr(overview_forecast, "cache", types.SimpleNamespace(get=lambda _k: None, set=lambda *_a, **_k: None))

    with app.test_request_context():
        payload = overview_forecast.forecast_metric_v2(FilterParams(), metric="revenue", horizon=6, granularity="monthly")

    forecasts = [row["yhat"] for row in payload.get("forecast", []) if row.get("yhat") is not None]
    assert forecasts
    assert max(forecasts) - min(forecasts) > 1.0
    assert payload["diagnostics"]["level_shift_detected"] is True
    assert payload["model"]["runner_ups"]
