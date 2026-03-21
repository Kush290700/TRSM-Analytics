import pandas as pd
import pytest

from app.services import bundle_cache
from app.services import fact_store
from app.services import products_bundle


@pytest.fixture
def seed_products(tmp_path, monkeypatch):
    df = pd.DataFrame(
        [
            {
                "Date": "2025-12-01",
                "DateExpected": "2025-12-01",
                "ProductId": "SKU-1",
                "ProductName": "Ribeye",
                "CustomerId": "C-1",
                "CustomerName": "Chef A",
                "OrderId": "O-1",
                "OrderStatus": "packed",
                "Revenue": 1200.0,
                "Cost": 800.0,
                "QuantityShipped": 100,
                "WeightLb": 300,
                "UnitOfBillingId": 1,
                "pack_item_count_sum": 100.0,
                "pack_weight_lb_sum": 300.0,
                "pack_count": 1,
                "Price": 12.0,
                "CostPrice": 8.0,
            },
            {
                "Date": "2025-12-15",
                "DateExpected": "2025-12-15",
                "ProductId": "SKU-2",
                "ProductName": "Tenderloin",
                "CustomerId": "C-2",
                "CustomerName": "Chef B",
                "OrderId": "O-2",
                "OrderStatus": "packed",
                "Revenue": 900.0,
                "Cost": 500.0,
                "QuantityShipped": 60,
                "WeightLb": 180,
                "UnitOfBillingId": 1,
                "pack_item_count_sum": 60.0,
                "pack_weight_lb_sum": 180.0,
                "pack_count": 1,
                "Price": 15.0,
                "CostPrice": 8.3333333333,
            },
            {
                "Date": "2026-01-05",
                "DateExpected": "2026-01-05",
                "ProductId": "SKU-1",
                "ProductName": "Ribeye",
                "CustomerId": "C-3",
                "CustomerName": "Chef C",
                "OrderId": "O-3",
                "OrderStatus": "packed",
                "Revenue": 600.0,
                "Cost": 350.0,
                "QuantityShipped": 40,
                "WeightLb": 120,
                "UnitOfBillingId": 1,
                "pack_item_count_sum": 40.0,
                "pack_weight_lb_sum": 120.0,
                "pack_count": 1,
                "Price": 15.0,
                "CostPrice": 8.75,
            },
        ]
    )
    parquet_path = tmp_path / "fact.parquet"
    df.to_parquet(parquet_path)
    monkeypatch.setenv("PARQUET_PATH", str(parquet_path))
    # Reset DuckDB view to point at test parquet
    fact_store.reset_duckdb_state()
    fact_store.init_views()
    yield parquet_path
    # Cleanup: drop view so other tests can re-init with their own paths
    fact_store.reset_duckdb_state()


def test_products_bundle_has_keys(app_client, seed_products):
    resp = app_client.get("/api/products/bundle")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "kpis" in data and "charts" in data and "table" in data
    assert "comparison" in data
    assert "comparison_summary" in data
    assert "story" in data
    assert "price_vs_velocity" in data
    assert "performance_bubble" in data
    assert "recommendations" in data
    assert "ai_signals" in data
    assert "projected_next_month" in data
    assert "health_matrix" in data
    assert "decision_signals" in data
    assert "portfolio_posture" in data
    assert "focus_actions" in data
    assert data["kpis"]["customers"] >= 0
    assert data["kpis"]["qty"] >= 0
    assert isinstance(data["table"].get("total"), int)
    health_matrix = data.get("health_matrix") or {}
    assert isinstance(health_matrix.get("quadrants"), list)
    assert "pricing_guardrails" in data
    assert "execution_lists" in data
    assert "mix_shift" in ((data.get("charts") or {}).get("segments") or {})
    if data["table"].get("rows"):
        row0 = data["table"]["rows"][0]
        assert "last_sold" in row0
        assert "quick_rec" in row0
        assert "intel_url" in row0
        assert "profit_share" in row0
        assert "margin_risk" in row0
        assert "volatility_score" in row0
        assert "revenue_current" in row0
        assert "revenue_prior" in row0
        assert "revenue_delta" in row0
        assert "revenue_delta_pct" in row0
        assert "profit_current" in row0
        assert "profit_prior" in row0
        assert "profit_delta" in row0
        assert "orders_current" in row0
        assert "orders_prior" in row0
        assert "customer_count" in row0
        assert "supplier_count" in row0
        assert "top_customer_share" in row0
        assert "customer_hhi" in row0


def test_products_bundle_exposes_portfolio_posture_and_signals(app_client, seed_products):
    resp = app_client.get("/api/products/bundle")
    assert resp.status_code == 200
    data = resp.get_json()

    posture = data.get("portfolio_posture") or {}
    assert posture.get("headline")
    assert posture.get("detail")
    assert posture.get("quadrant")

    signals = data.get("decision_signals") or []
    assert len(signals) >= 4
    keys = {signal.get("key") for signal in signals if isinstance(signal, dict)}
    assert {"margin_pressure", "pricing_action", "demand_trend", "portfolio_posture"}.issubset(keys)

    focus_actions = data.get("focus_actions") or []
    assert len(focus_actions) >= 1
    assert all((row.get("title") and row.get("owner")) for row in focus_actions if isinstance(row, dict))


def test_products_bundle_core_kpis_match_seed_data(app_client, seed_products):
    resp = app_client.get("/api/products/bundle")
    assert resp.status_code == 200
    data = resp.get_json()
    kpis = data.get("kpis") or {}

    assert kpis.get("revenue") == pytest.approx(2700.0, abs=0.01)
    assert kpis.get("qty") == pytest.approx(200.0, abs=0.01)
    assert kpis.get("weight") == pytest.approx(600.0, abs=0.01)
    assert kpis.get("products") == 2
    assert kpis.get("customers") == 3
    assert kpis.get("revenue_per_product") == pytest.approx(1350.0, abs=0.01)
    assert kpis.get("revenue_per_customer") == pytest.approx(900.0, abs=0.01)
    assert kpis.get("risk_profit_uplift_target", 0) >= 0


@pytest.fixture
def seed_products_mtd(tmp_path, monkeypatch):
    df = pd.DataFrame(
        [
            {
                "Date": "2026-02-01",
                "DateExpected": "2026-02-01",
                "ProductId": "SKU-1",
                "ProductName": "Ribeye",
                "CustomerId": "C-1",
                "CustomerName": "Chef A",
                "OrderId": "O-1",
                "OrderStatus": "packed",
                "Revenue": 100.0,
                "Cost": 70.0,
                "QuantityShipped": 10,
                "WeightLb": 30,
                "UnitOfBillingId": 1,
                "pack_item_count_sum": 10.0,
                "pack_weight_lb_sum": 30.0,
                "pack_count": 1,
                "Price": 10.0,
                "CostPrice": 7.0,
            },
            {
                "Date": "2026-02-10",
                "DateExpected": "2026-02-10",
                "ProductId": "SKU-2",
                "ProductName": "Tenderloin",
                "CustomerId": "C-2",
                "CustomerName": "Chef B",
                "OrderId": "O-2",
                "OrderStatus": "packed",
                "Revenue": 120.0,
                "Cost": 72.0,
                "QuantityShipped": 8,
                "WeightLb": 24,
                "UnitOfBillingId": 1,
                "pack_item_count_sum": 8.0,
                "pack_weight_lb_sum": 24.0,
                "pack_count": 1,
                "Price": 15.0,
                "CostPrice": 9.0,
            },
            {
                "Date": "2026-02-20",
                "DateExpected": "2026-02-20",
                "ProductId": "SKU-1",
                "ProductName": "Ribeye",
                "CustomerId": "C-3",
                "CustomerName": "Chef C",
                "OrderId": "O-3",
                "OrderStatus": "packed",
                "Revenue": 250.0,
                "Cost": 180.0,
                "QuantityShipped": 15,
                "WeightLb": 45,
                "UnitOfBillingId": 1,
                "pack_item_count_sum": 15.0,
                "pack_weight_lb_sum": 45.0,
                "pack_count": 1,
                "Price": 16.7,
                "CostPrice": 12.0,
            },
            {
                "Date": "2026-03-01",
                "DateExpected": "2026-03-01",
                "ProductId": "SKU-1",
                "ProductName": "Ribeye",
                "CustomerId": "C-1",
                "CustomerName": "Chef A",
                "OrderId": "O-4",
                "OrderStatus": "packed",
                "Revenue": 150.0,
                "Cost": 105.0,
                "QuantityShipped": 12,
                "WeightLb": 36,
                "UnitOfBillingId": 1,
                "pack_item_count_sum": 12.0,
                "pack_weight_lb_sum": 36.0,
                "pack_count": 1,
                "Price": 12.5,
                "CostPrice": 8.75,
            },
            {
                "Date": "2026-03-10",
                "DateExpected": "2026-03-10",
                "ProductId": "SKU-2",
                "ProductName": "Tenderloin",
                "CustomerId": "C-2",
                "CustomerName": "Chef B",
                "OrderId": "O-5",
                "OrderStatus": "packed",
                "Revenue": 180.0,
                "Cost": 108.0,
                "QuantityShipped": 9,
                "WeightLb": 27,
                "UnitOfBillingId": 1,
                "pack_item_count_sum": 9.0,
                "pack_weight_lb_sum": 27.0,
                "pack_count": 1,
                "Price": 20.0,
                "CostPrice": 12.0,
            },
            {
                "Date": "2026-03-25",
                "DateExpected": "2026-03-25",
                "ProductId": "SKU-1",
                "ProductName": "Ribeye",
                "CustomerId": "C-4",
                "CustomerName": "Chef D",
                "OrderId": "O-6",
                "OrderStatus": "packed",
                "Revenue": 400.0,
                "Cost": 260.0,
                "QuantityShipped": 20,
                "WeightLb": 60,
                "UnitOfBillingId": 1,
                "pack_item_count_sum": 20.0,
                "pack_weight_lb_sum": 60.0,
                "pack_count": 1,
                "Price": 20.0,
                "CostPrice": 13.0,
            },
        ]
    )
    parquet_path = tmp_path / "fact_mtd.parquet"
    df.to_parquet(parquet_path)
    monkeypatch.setenv("PARQUET_PATH", str(parquet_path))
    fact_store.reset_duckdb_state()
    fact_store.init_views()
    yield parquet_path
    fact_store.reset_duckdb_state()


def test_products_bundle_uses_safe_mtd_comparison_window(app_client, seed_products_mtd):
    resp = app_client.get(
        "/api/products/bundle",
        query_string={"start": "2026-03-01", "end": "2026-03-15"},
    )
    assert resp.status_code == 200
    data = resp.get_json()

    comparison = data.get("comparison") or {}
    assert comparison.get("method") == "month_to_date_vs_prior_month_same_day"
    assert comparison.get("current_start") == "2026-03-01"
    assert comparison.get("current_end") == "2026-03-15"
    assert comparison.get("prior_start") == "2026-02-01"
    assert comparison.get("prior_end") == "2026-02-15"

    summary = data.get("comparison_summary") or {}
    assert summary.get("revenue_current") == pytest.approx(330.0, abs=0.01)
    assert summary.get("revenue_prior") == pytest.approx(220.0, abs=0.01)
    assert summary.get("revenue_delta_pct") == pytest.approx(50.0, abs=0.01)

    rows = (data.get("table") or {}).get("rows") or []
    sku1 = next((row for row in rows if row.get("product_id") == "SKU-1"), None)
    assert sku1 is not None
    assert sku1.get("revenue_current") == pytest.approx(150.0, abs=0.01)
    assert sku1.get("revenue_prior") == pytest.approx(100.0, abs=0.01)


def test_products_bundle_projects_partial_month_with_mtd_pace(app_client, seed_products_mtd):
    resp = app_client.get(
        "/api/products/bundle",
        query_string={"start": "2026-03-01", "end": "2026-03-15"},
    )
    assert resp.status_code == 200
    data = resp.get_json()

    projected = data.get("projected_next_month") or {}
    assert projected.get("method") == "mtd_daily_pace"
    assert projected.get("value") == pytest.approx(682.0, abs=0.5)
    assert "pace" in str(projected.get("note") or "").lower()


def test_health_matrix_has_population_in_at_least_one_quadrant(app_client, seed_products):
    resp = app_client.get("/api/products/bundle")
    assert resp.status_code == 200
    data = resp.get_json()
    quadrants = ((data.get("health_matrix") or {}).get("quadrants") or [])
    assert len(quadrants) == 4
    total = sum(int(q.get("sku_count") or 0) for q in quadrants)
    assert total > 0


def test_products_bundle_trajectory_grain_switches_to_weekly_for_short_window(app_client, seed_products):
    resp = app_client.get(
        "/api/products/bundle",
        query_string={"start": "2026-01-01", "end": "2026-01-20"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    grain = (((data.get("charts") or {}).get("trajectory") or {}).get("grain"))
    assert grain in {"weekly", "monthly"}
    assert grain == "weekly"


def test_uplift_and_risk_values_are_non_negative(app_client, seed_products):
    resp = app_client.get("/api/products/bundle")
    assert resp.status_code == 200
    data = resp.get_json()
    kpis = data.get("kpis") or {}
    assert float(kpis.get("risk_profit_uplift_target") or 0) >= 0
    assert float(kpis.get("profit_at_risk") or 0) >= 0


def test_products_bundle_display_name(app_client, seed_products):
    resp = app_client.get("/api/products/bundle")
    assert resp.status_code == 200
    data = resp.get_json()
    rows = (data.get("table") or {}).get("rows") or []
    if rows:
        row0 = rows[0]
        assert row0.get("display_name")
        assert str(row0.get("product_id")) in str(row0.get("display_name"))
    top = (data.get("charts") or {}).get("top_products") or []
    if top:
        assert top[0].get("display_name")


def test_empty_multi_filters_are_noop(app_client, seed_products):
    resp = app_client.get(
        "/api/products/bundle",
        query_string=[("start", "2025-12-01"), ("end", "2026-01-31"), ("regions", ""), ("customers", ""), ("products", "")],
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["kpis"]["revenue"] > 0
    assert data["kpis"]["products"] > 0


def test_products_drilldown_bundle(app_client, seed_products):
    resp = app_client.get("/api/products/drilldown/bundle", query_string={"sku": "SKU-1"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "kpis" in data and "trend" in data and "table" in data
    assert data["kpis"]["customers"] >= 0
    assert data["kpis"]["qty"] >= 0
    assert data.get("meta", {}).get("entity_display_name")
    assert data.get("trend", {}).get("labels")
    assert isinstance(data["table"].get("rows"), list)
    for key in ("monthly_series", "top_customers", "top_regions", "weekday_distribution", "price_distribution", "cross_sell"):
        assert key in data


def test_products_bundle_cache_hit(app_client, seed_products):
    query = {"start": "2025-12-01", "end": "2026-01-31"}
    resp1 = app_client.get("/api/products/bundle", query_string=query)
    assert resp1.status_code == 200
    resp2 = app_client.get("/api/products/bundle", query_string=query)
    assert resp2.status_code == 200
    data2 = resp2.get_json()
    assert data2.get("meta", {}).get("cached") is True


def test_products_bundle_cache_key_changes_for_quick_filters(app_client, seed_products):
    base = {"start": "2025-12-01", "end": "2026-01-31"}
    low_margin = app_client.get("/api/products/bundle", query_string={**base, "quick_filters": "below_target_margin"})
    top_revenue = app_client.get("/api/products/bundle", query_string={**base, "quick_filters": "top_revenue_20"})

    assert low_margin.status_code == 200
    assert top_revenue.status_code == 200

    low_payload = low_margin.get_json()
    top_payload = top_revenue.get_json()

    low_key = (low_payload.get("meta") or {}).get("cache_key")
    top_key = (top_payload.get("meta") or {}).get("cache_key")
    assert low_key and top_key and low_key != top_key


@pytest.mark.parametrize("watchlist_key", ["protect_core", "recover_margin", "promote_candidate", "rationalize_candidate"])
def test_products_bundle_supports_workspace_watchlist_filters(app_client, seed_products, watchlist_key):
    resp = app_client.get(
        "/api/products/bundle",
        query_string={"start": "2025-12-01", "end": "2026-01-31", "quick_filters": watchlist_key},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    table = data.get("table") or {}
    assert watchlist_key in (table.get("quick_filters") or [])
    assert isinstance(table.get("rows"), list)


def test_products_bundle_cache_key_separates_user_scope():
    filters = {"start": "2025-12-01", "end": "2026-01-31"}
    base_scope = {
        "role": "sales",
        "scope_mode": "scoped",
        "permissions_version": "v1",
    }
    key_a = bundle_cache._cache_key(  # noqa: SLF001
        endpoint="products.bundle",
        filters=filters,
        scope={**base_scope, "user_id": "user-a", "scope_hash": "scope-a"},
        dataset_version="dataset-1",
        extras={"quick_filters": "below_target_margin"},
    )
    key_b = bundle_cache._cache_key(  # noqa: SLF001
        endpoint="products.bundle",
        filters=filters,
        scope={**base_scope, "user_id": "user-b", "scope_hash": "scope-b"},
        dataset_version="dataset-1",
        extras={"quick_filters": "below_target_margin"},
    )

    assert key_a != key_b


def test_unit_price_quantiles_float_or_none(app_client, seed_products):
    resp = app_client.get("/api/products/bundle")
    data = resp.get_json()
    kpis = data.get("kpis", {})
    for key in ("unit_price_p10", "unit_price_p50", "unit_price_p90"):
        val = kpis.get(key)
        assert val is None or isinstance(val, (int, float))


def test_health_matrix_tolerates_pandas_na_values():
    out = products_bundle._build_health_matrix(  # noqa: SLF001
        summary_rows=[pd.NA, {"quadrant": pd.NA, "sku_count": pd.NA, "revenue": 10}],
        top_rows=[pd.NA, {"quadrant": pd.NA, "display_name": pd.NA, "product_name": "P1", "revenue": 1}],
        velocity_cutoff=None,
        margin_cutoff=None,
        total_revenue=10,
    )
    assert isinstance(out, dict)
    assert isinstance(out.get("quadrants"), list)
    assert len(out.get("quadrants") or []) == 4


def test_mover_status_labels_for_new_lost_and_low_base():
    new_status = products_bundle._mover_status(250.0, 0.0)  # noqa: SLF001
    lost_status = products_bundle._mover_status(0.0, 320.0)  # noqa: SLF001
    low_base_status = products_bundle._mover_status(520.0, 300.0)  # noqa: SLF001

    assert new_status[0] == "New"
    assert lost_status[0] == "Lost"
    assert low_base_status[0] == "Low base"
