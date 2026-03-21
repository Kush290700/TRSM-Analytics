import pandas as pd
import pytest

from app.services import fact_store


@pytest.fixture
def seed_salesreps_drilldown(tmp_path, monkeypatch):
    rows = []
    reps = [("R1", "Alex"), ("R2", "Bea")]
    order_idx = 1
    for rep_idx, (rep_id, rep_name) in enumerate(reps, start=1):
        for month in (6, 7, 8):
            for order_no in (1, 2):
                revenue = float(900 + rep_idx * 120 + month * 8 + order_no)
                cost = revenue * 0.65
                pack_units = 4 + order_no
                rows.append(
                    {
                        "Date": f"2025-{month:02d}-{order_no:02d}",
                        "DateExpected": f"2025-{month:02d}-{order_no:02d}",
                        "SalesRepId": rep_id,
                        "SalesRepName": rep_name,
                        "OrderId": f"D-{order_idx}",
                        "CustomerId": f"C-{rep_idx:02d}",
                        "CustomerName": f"Customer {rep_idx:02d}",
                        "ProductId": f"P-{rep_idx:02d}",
                        "ProductName": f"Product {rep_idx:02d}",
                        "OrderStatus": "packed",
                        "Revenue": revenue,
                        "Cost": cost,
                        "QuantityOrdered": pack_units,
                        "WeightLb": 8.0 + rep_idx,
                        "UnitOfBillingId": 1,
                        "pack_item_count_sum": float(pack_units),
                        "pack_weight_lb_sum": 8.0 + rep_idx,
                        "pack_count": 1,
                        "Price": revenue / pack_units,
                        "CostPrice": cost / pack_units,
                    }
                )
                order_idx += 1

    df = pd.DataFrame(rows)
    parquet_path = tmp_path / "fact_salesreps_drilldown.parquet"
    df.to_parquet(parquet_path)

    monkeypatch.setenv("PARQUET_PATH", str(parquet_path))
    fact_store.reset_duckdb_state()
    fact_store.init_views()
    yield parquet_path
    fact_store.reset_duckdb_state()


def test_salesreps_drilldown_bundle_panels(app_client, seed_salesreps_drilldown):
    rep_id = "R1"
    resp = app_client.get(
        "/api/salesreps/drilldown/bundle",
        query_string={"salesrep_id": rep_id, "start": "2025-01-01", "end": "2025-12-31"},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert isinstance(payload, dict)
    for key in ("kpis", "trend", "charts", "table", "tables", "decomposition", "risk_flags", "insights", "meta"):
        assert key in payload

    meta = payload.get("meta", {})
    assert str(meta.get("entity_id")) == rep_id
    assert int(meta.get("duckdb_query_count", 0) or 0) <= 3

    kpis = payload.get("kpis", {})
    assert float(kpis.get("revenue") or 0.0) > 0
    assert int(kpis.get("orders") or 0) > 0

    charts = payload.get("charts", {})
    assert len(charts.get("top_customers") or []) > 0
    assert len(charts.get("top_products") or []) > 0
    assert isinstance(charts.get("concentration"), dict)

    trend = payload.get("trend", {})
    assert len((trend.get("monthly") or {}).get("labels") or []) > 0
    assert len((trend.get("weekly") or {}).get("labels") or []) > 0

    tables = payload.get("tables", {})
    assert len(tables.get("customers") or []) > 0
    assert len(tables.get("products") or []) > 0

    customers_rev = sum(float(r.get("revenue") or 0.0) for r in (tables.get("customers") or []))
    assert customers_rev == pytest.approx(float(kpis.get("revenue") or 0.0), rel=0.001, abs=0.01)
