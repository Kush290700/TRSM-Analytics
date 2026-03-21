import pandas as pd
import pytest

from app.services import fact_store


@pytest.fixture
def seed_salesreps_bundle(tmp_path, monkeypatch):
    rows = []
    reps = [("R1", "Alex"), ("R2", "Bea"), ("R3", "Carl")]
    order_idx = 1
    for rep_idx, (rep_id, rep_name) in enumerate(reps, start=1):
        for month in (6, 7, 8):
            for order_no in (1, 2):
                revenue = float(1000 + rep_idx * 100 + month * 10 + order_no)
                cost = revenue * 0.6
                rows.append(
                    {
                        "Date": f"2025-{month:02d}-{order_no:02d}",
                        "DateExpected": f"2025-{month:02d}-{order_no:02d}",
                        "SalesRepId": rep_id,
                        "SalesRepName": rep_name,
                        "OrderId": f"O-{order_idx}",
                        "CustomerId": f"C-{rep_idx:02d}",
                        "CustomerName": f"Customer {rep_idx:02d}",
                        "ProductId": f"P-{rep_idx:02d}",
                        "ProductName": f"Product {rep_idx:02d}",
                        "OrderStatus": "packed",
                        "Revenue": revenue,
                        "Cost": cost,
                        "QuantityOrdered": 5 + order_no,
                        "WeightLb": 10.0 + rep_idx,
                        "UnitOfBillingId": 1,
                        "pack_item_count_sum": 1.0,
                        "pack_weight_lb_sum": 10.0 + rep_idx,
                        "pack_count": 1,
                        "Price": revenue,
                        "CostPrice": cost,
                    }
                )
                order_idx += 1

    df = pd.DataFrame(rows)
    parquet_path = tmp_path / "fact_salesreps.parquet"
    df.to_parquet(parquet_path)

    monkeypatch.setenv("PARQUET_PATH", str(parquet_path))
    fact_store.reset_duckdb_state()
    fact_store.init_views()
    yield parquet_path
    fact_store.reset_duckdb_state()


def test_salesreps_bundle_keys_and_budget(app_client, seed_salesreps_bundle):
    resp = app_client.get(
        "/api/salesreps/bundle",
        query_string={"start": "2025-01-01", "end": "2025-12-31", "page_size": 10, "page": 1},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert isinstance(payload, dict)
    for key in ("kpis", "trend", "charts", "table", "meta"):
        assert key in payload

    meta = payload.get("meta", {})
    assert meta.get("dataset_version") is not None
    assert int(meta.get("duckdb_query_count", 0) or 0) <= 3

    kpis = payload.get("kpis", {})
    assert float(kpis.get("revenue") or 0.0) > 0
    assert int(kpis.get("orders") or 0) > 0
    assert int(kpis.get("customers") or 0) > 0

    charts = payload.get("charts", {})
    assert len(charts.get("top_reps") or []) > 0
    assert len(charts.get("pareto") or []) > 0
    trend = charts.get("trend") or {}
    assert len(trend.get("labels") or []) > 0

    table = payload.get("table", {})
    rows = table.get("rows") or []
    assert len(rows) > 0
    row = rows[0]
    assert row.get("rep_id") or row.get("rep_name")
    assert row.get("orders") is not None
    assert row.get("customers") is not None
