from __future__ import annotations

import io

import pandas as pd
import pytest

from app.services import fact_store


@pytest.fixture
def seed_suppliers_v2(tmp_path, monkeypatch):
    rows = [
        {
            "Date": "2025-02-10",
            "DateExpected": "2025-02-10",
            "OrderId": "O-A-PRIOR",
            "SupplierId": "SUP_A",
            "SupplierName": "Supplier A",
            "ProductId": "P1",
            "ProductName": "Prod 1",
            "CustomerId": "C1",
            "CustomerName": "Cust 1",
            "Revenue": 1000.0,
            "Cost": 700.0,
            "QuantityShipped": 100.0,
            "WeightLb": 200.0,
            "SalesRepId": "R1",
            "SalesRepName": "Rep One",
            "OrderStatus": "packed",
        },
        {
            "Date": "2025-03-10",
            "DateExpected": "2025-03-10",
            "OrderId": "O-A-CUR",
            "SupplierId": "SUP_A",
            "SupplierName": "Supplier A",
            "ProductId": "P1",
            "ProductName": "Prod 1",
            "CustomerId": "C1",
            "CustomerName": "Cust 1",
            "Revenue": 1500.0,
            "Cost": 990.0,
            "QuantityShipped": 120.0,
            "WeightLb": 210.0,
            "SalesRepId": "R1",
            "SalesRepName": "Rep One",
            "OrderStatus": "packed",
        },
        {
            "Date": "2025-02-12",
            "DateExpected": "2025-02-12",
            "OrderId": "O-B-PRIOR",
            "SupplierId": "SUP_B",
            "SupplierName": "Supplier B",
            "ProductId": "P2",
            "ProductName": "Prod 2",
            "CustomerId": "C2",
            "CustomerName": "Cust 2",
            "Revenue": 800.0,
            "Cost": 560.0,
            "QuantityShipped": 80.0,
            "WeightLb": 170.0,
            "SalesRepId": "R1",
            "SalesRepName": "Rep One",
            "OrderStatus": "packed",
        },
        {
            "Date": "2025-03-14",
            "DateExpected": "2025-03-14",
            "OrderId": "O-C-CUR",
            "SupplierId": "SUP_C",
            "SupplierName": "Supplier C",
            "ProductId": "P3",
            "ProductName": "Prod 3",
            "CustomerId": "C3",
            "CustomerName": "Cust 3",
            "Revenue": 600.0,
            "Cost": 390.0,
            "QuantityShipped": 60.0,
            "WeightLb": 120.0,
            "SalesRepId": "R1",
            "SalesRepName": "Rep One",
            "OrderStatus": "packed",
        },
        {
            "Date": "2025-02-20",
            "DateExpected": "2025-02-20",
            "OrderId": "O-D-PRIOR",
            "SupplierId": "SUP_D",
            "SupplierName": "Supplier D",
            "ProductId": "P4",
            "ProductName": "Prod 4",
            "CustomerId": "C4",
            "CustomerName": "Cust 4",
            "Revenue": 500.0,
            "Cost": None,
            "QuantityShipped": 50.0,
            "WeightLb": 90.0,
            "SalesRepId": "R1",
            "SalesRepName": "Rep One",
            "OrderStatus": "packed",
        },
        {
            "Date": "2025-03-20",
            "DateExpected": "2025-03-20",
            "OrderId": "O-D-CUR",
            "SupplierId": "SUP_D",
            "SupplierName": "Supplier D",
            "ProductId": "P4",
            "ProductName": "Prod 4",
            "CustomerId": "C4",
            "CustomerName": "Cust 4",
            "Revenue": 400.0,
            "Cost": None,
            "QuantityShipped": 40.0,
            "WeightLb": 80.0,
            "SalesRepId": "R1",
            "SalesRepName": "Rep One",
            "OrderStatus": "packed",
        },
        {
            "Date": "2025-02-18",
            "DateExpected": "2025-02-18",
            "OrderId": "O-E-PRIOR",
            "SupplierId": "SUP_E",
            "SupplierName": "Supplier E",
            "ProductId": "P5",
            "ProductName": "Prod 5",
            "CustomerId": "C5",
            "CustomerName": "Cust 5",
            "Revenue": 700.0,
            "Cost": 500.0,
            "QuantityShipped": 70.0,
            "WeightLb": 130.0,
            "SalesRepId": "R1",
            "SalesRepName": "Rep One",
            "OrderStatus": "packed",
        },
        {
            "Date": "2025-03-22",
            "DateExpected": "2025-03-22",
            "OrderId": "O-E-CUR",
            "SupplierId": "SUP_E",
            "SupplierName": "Supplier E",
            "ProductId": "P5",
            "ProductName": "Prod 5",
            "CustomerId": "C5",
            "CustomerName": "Cust 5",
            "Revenue": 200.0,
            "Cost": 170.0,
            "QuantityShipped": 20.0,
            "WeightLb": 40.0,
            "SalesRepId": "R1",
            "SalesRepName": "Rep One",
            "OrderStatus": "packed",
        },
        {
            "Date": "2025-03-08",
            "DateExpected": "2025-03-08",
            "OrderId": "O-OTHER-CUR",
            "SupplierId": "SUP_OTHER",
            "SupplierName": "Supplier Other",
            "ProductId": "P9",
            "ProductName": "Prod 9",
            "CustomerId": "C9",
            "CustomerName": "Cust 9",
            "Revenue": 900.0,
            "Cost": 600.0,
            "QuantityShipped": 90.0,
            "WeightLb": 180.0,
            "SalesRepId": "R2",
            "SalesRepName": "Rep Two",
            "OrderStatus": "packed",
        },
    ]

    df = pd.DataFrame(rows)
    # Ensure canonical revenue/cost candidates are present in the DuckDB fact view.
    df["revenue_ordered"] = df["Revenue"]
    df["cost_ordered"] = df["Cost"]
    parquet_path = tmp_path / "fact_suppliers_v2.parquet"
    df.to_parquet(parquet_path)
    monkeypatch.setenv("PARQUET_PATH", str(parquet_path))
    fact_store.reset_duckdb_state()
    fact_store.init_views()
    yield parquet_path
    fact_store.reset_duckdb_state()


def _scope_admin():
    return {
        "is_admin": True,
        "scope_mode": "all",
        "allowed_erp_user_ids": [],
        "sales_rep_ids": [],
        "allowed_count": 0,
        "scope_hash": "scope-admin-suppliers-v2",
        "permissions_version": "1",
        "user_id": 1,
        "role": "admin",
    }


def _scope_sales(rep_ids: list[str]):
    return {
        "is_admin": False,
        "scope_mode": "list",
        "allowed_erp_user_ids": rep_ids,
        "sales_rep_ids": rep_ids,
        "allowed_count": len(rep_ids),
        "scope_hash": "scope-sales-suppliers-v2",
        "permissions_version": "1",
        "user_id": 77,
        "role": "sales",
    }


def _csv_frame(resp) -> pd.DataFrame:
    return pd.read_csv(io.StringIO(resp.get_data(as_text=True)))


def test_suppliers_v2_trend_binning_sorted(app_client, seed_suppliers_v2, monkeypatch):
    monkeypatch.setattr("app.services.filters_service.scope_from_user", lambda _u: _scope_admin())
    payload = app_client.get(
        "/api/suppliers/bundle",
        query_string={"suppliers_v2": "1", "start": "2025-02-01", "end": "2025-03-31"},
    ).get_json()
    labels = ((payload or {}).get("trend") or {}).get("labels") or []
    assert labels == sorted(labels)
    assert labels == ["2025-02", "2025-03"]


def test_suppliers_v2_movers_new_and_lost_status(app_client, seed_suppliers_v2, monkeypatch):
    monkeypatch.setattr("app.services.filters_service.scope_from_user", lambda _u: _scope_admin())
    resp = app_client.get(
        "/api/suppliers/bundle",
        query_string={"suppliers_v2": "1", "start": "2025-03-01", "end": "2025-03-31", "page_size": 200},
    )
    assert resp.status_code == 200
    movers = ((resp.get_json() or {}).get("movers") or {}).get("rows") or []
    by_id = {str(r.get("supplier_id")): r for r in movers}
    assert by_id["SUP_C"]["delta_revenue_status"] == "new"
    assert by_id["SUP_B"]["delta_revenue_status"] == "lost"


def test_suppliers_v2_export_parity_matches_filtered_table(app_client, seed_suppliers_v2, monkeypatch):
    monkeypatch.setattr("app.services.filters_service.scope_from_user", lambda _u: _scope_admin())
    query = {
        "suppliers_v2": "1",
        "start": "2025-03-01",
        "end": "2025-03-31",
        "quick_filter": "data_risk",
        "search": "Supplier",
        "page_size": 25,
    }
    bundle_resp = app_client.get("/api/suppliers/bundle", query_string=query)
    assert bundle_resp.status_code == 200
    table = ((bundle_resp.get_json() or {}).get("table") or {})
    filtered_count = int(table.get("total_rows") or 0)

    export_resp = app_client.get("/api/suppliers/export.csv", query_string={**query, "scope": "table"})
    assert export_resp.status_code == 200
    export_df = _csv_frame(export_resp)
    assert len(export_df.index) == filtered_count


def test_suppliers_v2_rbac_scope_bundle_and_export(app_client, seed_suppliers_v2, monkeypatch):
    monkeypatch.setattr("app.services.filters_service.scope_from_user", lambda _u: _scope_sales(["r1"]))
    query = {
        "suppliers_v2": "1",
        "start": "2025-03-01",
        "end": "2025-03-31",
        "page_size": 200,
        "export_all": "1",
    }
    bundle_resp = app_client.get("/api/suppliers/bundle", query_string=query)
    assert bundle_resp.status_code == 200
    rows = ((bundle_resp.get_json() or {}).get("table") or {}).get("rows") or []
    ids = {str(r.get("supplier_id")) for r in rows}
    assert "SUP_OTHER" not in ids
    assert "SUP_A" in ids

    export_resp = app_client.get("/api/suppliers/export.csv", query_string={**query, "scope": "table"})
    assert export_resp.status_code == 200
    export_df = _csv_frame(export_resp)
    assert "SUP_OTHER" not in set(export_df["supplier_id"].astype(str).tolist())


def test_suppliers_v2_flag_on_renders_new_template(app_client, seed_suppliers_v2, monkeypatch):
    monkeypatch.setattr("app.services.filters_service.scope_from_user", lambda _u: _scope_admin())
    monkeypatch.setitem(app_client.application.config, "SUPPLIERS_V2", True)
    resp = app_client.get("/suppliers/", query_string={"start": "2025-03-01", "end": "2025-03-31"})
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Supplier Command Center" in body
    assert "Supplier Segments" in body


def test_suppliers_v2_flag_off_keeps_v1_template(app_client, seed_suppliers_v2, monkeypatch):
    monkeypatch.setattr("app.services.filters_service.scope_from_user", lambda _u: _scope_admin())
    monkeypatch.setitem(app_client.application.config, "SUPPLIERS_V2", False)
    resp = app_client.get("/suppliers/", query_string={"start": "2025-03-01", "end": "2025-03-31"})
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Suppliers — Current Filters" in body
    assert "Supplier Command Center" not in body
