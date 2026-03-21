from __future__ import annotations

import io

import pandas as pd
import pytest

from app.services import fact_store


@pytest.fixture
def seed_salesreps_v2(tmp_path, monkeypatch):
    rows = []
    for rep_num in range(1, 41):
        rep_id = f"R{rep_num:03d}"
        rep_name = f"Rep {rep_num:03d}"
        for month in (1, 2):
            revenue = float(1000 + rep_num * 25 + month)
            cost = revenue * 0.72
            rows.append(
                {
                    "Date": f"2025-{month:02d}-10",
                    "DateExpected": f"2025-{month:02d}-10",
                    "SalesRepId": rep_id,
                    "SalesRepName": rep_name,
                    "OrderId": f"O-{rep_id}-{month}",
                    "CustomerId": f"C-{rep_num:03d}",
                    "CustomerName": f"Customer {rep_num:03d}",
                    "ProductId": f"P-{rep_num:03d}",
                    "ProductName": f"Product {rep_num:03d}",
                    "OrderStatus": "packed",
                    "Revenue": revenue,
                    "Cost": cost,
                    "QuantityOrdered": 10 + month,
                    "WeightLb": 30.0 + rep_num,
                    "UnitOfBillingId": 1,
                    "pack_item_count_sum": float(10 + month),
                    "pack_weight_lb_sum": 30.0 + rep_num,
                    "pack_count": 1,
                    "Price": revenue,
                    "CostPrice": cost,
                }
            )

    df = pd.DataFrame(rows)
    parquet_path = tmp_path / "fact_salesreps_v2.parquet"
    df.to_parquet(parquet_path)

    monkeypatch.setenv("PARQUET_PATH", str(parquet_path))
    fact_store.reset_duckdb_state()
    fact_store.init_views()
    yield parquet_path
    fact_store.reset_duckdb_state()


def _csv_frame(resp) -> pd.DataFrame:
    return pd.read_csv(io.StringIO(resp.get_data(as_text=True)))


def _sales_scope(rep_ids: list[str]):
    return {
        "is_admin": False,
        "scope_mode": "list",
        "allowed_erp_user_ids": rep_ids,
        "sales_rep_ids": rep_ids,
        "allowed_count": len(rep_ids),
        "scope_hash": "scope-sales",
        "permissions_version": "1",
        "user_id": 77,
        "role": "sales",
    }


def _admin_scope():
    return {
        "is_admin": True,
        "scope_mode": "all",
        "allowed_erp_user_ids": [],
        "sales_rep_ids": [],
        "allowed_count": 0,
        "scope_hash": "scope-admin",
        "permissions_version": "1",
        "user_id": 1,
        "role": "admin",
    }


def test_sales_scope_table_and_export_only_allowed_reps(app_client, seed_salesreps_v2, monkeypatch):
    monkeypatch.setattr("app.services.filters_service.scope_from_user", lambda _u: _sales_scope(["r001", "r002"]))

    bundle = app_client.get(
        "/api/salesreps/bundle",
        query_string={"start": "2025-01-01", "end": "2025-12-31", "page_size": 100},
    )
    assert bundle.status_code == 200
    rows = (bundle.get_json() or {}).get("table", {}).get("rows", [])
    assert {r.get("rep_id") for r in rows} == {"R001", "R002"}

    export = app_client.get(
        "/salesreps/export.csv",
        query_string={"start": "2025-01-01", "end": "2025-12-31"},
    )
    assert export.status_code == 200
    export_df = _csv_frame(export)
    assert set(export_df["Rep ID"].tolist()) == {"R001", "R002"}


def test_admin_scope_sees_all_reps_table_and_export(app_client, seed_salesreps_v2, monkeypatch):
    monkeypatch.setattr("app.services.filters_service.scope_from_user", lambda _u: _admin_scope())

    bundle = app_client.get(
        "/api/salesreps/bundle",
        query_string={"start": "2025-01-01", "end": "2025-12-31", "page_size": 100},
    )
    assert bundle.status_code == 200
    rows = (bundle.get_json() or {}).get("table", {}).get("rows", [])
    assert len(rows) == 40

    export = app_client.get(
        "/salesreps/export.csv",
        query_string={"start": "2025-01-01", "end": "2025-12-31"},
    )
    assert export.status_code == 200
    export_df = _csv_frame(export)
    assert len(export_df.index) == 40


def test_salesreps_export_not_truncated_over_25_rows(app_client, seed_salesreps_v2, monkeypatch):
    monkeypatch.setattr("app.services.filters_service.scope_from_user", lambda _u: _admin_scope())

    resp = app_client.get(
        "/salesreps/export.csv",
        query_string={"start": "2025-01-01", "end": "2025-12-31"},
    )
    assert resp.status_code == 200
    df = _csv_frame(resp)
    assert len(df.index) > 25


def test_salesreps_sorting_is_deterministic(app_client, seed_salesreps_v2, monkeypatch):
    monkeypatch.setattr("app.services.filters_service.scope_from_user", lambda _u: _admin_scope())

    asc = app_client.get(
        "/api/salesreps/bundle",
        query_string={
            "start": "2025-01-01",
            "end": "2025-12-31",
            "sort": "revenue",
            "dir": "asc",
            "page_size": 25,
        },
    )
    desc = app_client.get(
        "/api/salesreps/bundle",
        query_string={
            "start": "2025-01-01",
            "end": "2025-12-31",
            "sort": "revenue",
            "dir": "desc",
            "page_size": 25,
        },
    )
    assert asc.status_code == 200
    assert desc.status_code == 200

    asc_rows = (asc.get_json() or {}).get("table", {}).get("rows", [])
    desc_rows = (desc.get_json() or {}).get("table", {}).get("rows", [])
    assert len(asc_rows) == 25
    assert len(desc_rows) == 25

    assert asc_rows[0]["revenue"] <= asc_rows[-1]["revenue"]
    assert desc_rows[0]["revenue"] >= desc_rows[-1]["revenue"]
    assert asc_rows[0]["rep_id"] != desc_rows[0]["rep_id"]


def test_salesreps_page_renders_with_flag_on_off(app_client, monkeypatch):
    monkeypatch.setitem(app_client.application.config, "SALESREPS_V2", False)
    legacy = app_client.get("/salesreps/")
    assert legacy.status_code == 200
    legacy_body = legacy.get_data(as_text=True)
    assert "Unified KPIs, drilldowns, and trends" in legacy_body
    assert "Ranking &amp; Performance" not in legacy_body

    monkeypatch.setitem(app_client.application.config, "SALESREPS_V2", True)
    v2 = app_client.get("/salesreps/")
    assert v2.status_code == 200
    v2_body = v2.get_data(as_text=True)
    assert "Ranking &amp; Performance" in v2_body
    assert "id=\"srMetricToggle\"" in v2_body
