from __future__ import annotations

from app.services import labor_store
from tests.labor_helpers import build_labor_dataset


def _make_client():
    import os
    from app import create_app

    os.environ.setdefault("FLASK_ENV", "development")
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, SECRET_KEY="test", LOGIN_DISABLED=True, PROPAGATE_EXCEPTIONS=True)
    return app.test_client()


def test_labor_page_renders_workforce_command_center(tmp_path, monkeypatch):
    dataset_path = tmp_path / "labor_dataset"
    build_labor_dataset(dataset_path)
    monkeypatch.setenv("LABOR_PARQUET_PATH", dataset_path.as_posix())
    monkeypatch.setenv("LABOR_ANALYTICS_ENABLED", "1")
    labor_store.reset_duckdb_state()
    client = _make_client()

    response = client.get("/labor/")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Labor Intelligence" in body
    assert "Workforce Command Center" in body
    assert "Executive Labor Scorecard" in body
    assert "Department Investigation Layer" in body
    assert "Category And Composition Layer" in body
    assert "Worker And Assignment Layer" in body
    assert "Trend And Operating Rhythm Layer" in body
    assert "Watchlist And Action Layer" in body


def test_labor_bundle_api_exposes_focus_layers_and_exports(tmp_path, monkeypatch):
    dataset_path = tmp_path / "labor_dataset"
    build_labor_dataset(dataset_path)
    monkeypatch.setenv("LABOR_PARQUET_PATH", dataset_path.as_posix())
    monkeypatch.setenv("LABOR_ANALYTICS_ENABLED", "1")
    labor_store.reset_duckdb_state()
    client = _make_client()

    bundle = client.get("/labor/api/bundle?start=2024-02-01&end=2024-02-10")
    assert bundle.status_code == 200
    payload = bundle.get_json()
    assert payload["kpis"]["total_labor_cost"] == 380.0
    assert payload["hero"]["active_departments"] == 2
    assert payload["focus"]["department"]["department_name"] == "Packaging"
    assert payload["focus"]["category"]["time_category"] == "Regular"
    assert payload["focus"]["worker"]["employee_code"] == "E100"
    assert payload["charts"]["worker_cost"][0]["employee_code"] == "E100"
    assert payload["watchlists"]["workers"][0]["employee_code"] == "E100"

    csv_resp = client.get("/labor/export/detail?format=csv")
    assert csv_resp.status_code == 200
    assert csv_resp.headers["Content-Type"].startswith("text/csv")

    for dataset in ["snapshot", "department-summary", "category-summary", "employee-summary"]:
        xlsx_resp = client.get(f"/labor/export/{dataset}?format=xlsx")
        assert xlsx_resp.status_code == 200
        assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in xlsx_resp.headers["Content-Type"]

    watchlist_resp = client.get("/labor/export/watchlist?format=csv")
    assert watchlist_resp.status_code == 200
    assert watchlist_resp.headers["Content-Type"].startswith("text/csv")


def test_labor_bundle_drilldown_filters_inherit_scope(tmp_path, monkeypatch):
    dataset_path = tmp_path / "labor_dataset"
    build_labor_dataset(dataset_path)
    monkeypatch.setenv("LABOR_PARQUET_PATH", dataset_path.as_posix())
    monkeypatch.setenv("LABOR_ANALYTICS_ENABLED", "1")
    labor_store.reset_duckdb_state()
    client = _make_client()

    department_bundle = client.get("/labor/api/bundle?department=Packaging")
    assert department_bundle.status_code == 200
    department_payload = department_bundle.get_json()
    assert department_payload["kpis"]["total_labor_cost"] == 204.0
    assert department_payload["focus"]["department"]["department_name"] == "Packaging"
    assert {row["time_category"] for row in department_payload["focus"]["department"]["category_rows"]} == {"Regular", "Overtime"}

    category_bundle = client.get("/labor/api/bundle?time_category=Absence")
    assert category_bundle.status_code == 200
    category_payload = category_bundle.get_json()
    assert category_payload["kpis"]["total_labor_cost"] == 44.0
    assert category_payload["focus"]["category"]["time_category"] == "Absence"
    assert category_payload["focus"]["category"]["department_rows"][0]["department_name"] == "Receiving"

    worker_bundle = client.get("/labor/api/bundle?employee=E200")
    assert worker_bundle.status_code == 200
    worker_payload = worker_bundle.get_json()
    assert worker_payload["kpis"]["total_labor_cost"] == 176.0
    assert worker_payload["focus"]["worker"]["employee_code"] == "E200"
    assert worker_payload["focus"]["worker"]["employee_name"] == "Mark Ops"


def test_labor_page_handles_missing_dataset(tmp_path, monkeypatch):
    missing_path = tmp_path / "missing_labor_dataset"
    monkeypatch.setenv("LABOR_PARQUET_PATH", missing_path.as_posix())
    monkeypatch.setenv("LABOR_ANALYTICS_ENABLED", "1")
    labor_store.reset_duckdb_state()
    client = _make_client()

    response = client.get("/labor/")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Labor dataset is not built yet" in body
