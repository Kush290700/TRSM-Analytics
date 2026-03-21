import copy

import pytest

from app.services import filters as canonical_filters
from app.services import filters_service
from app.services.filters import filters_to_store


@pytest.fixture
def authed_client(client, monkeypatch):
    class _DummyUser:
        is_authenticated = True
        is_active = True
        is_anonymous = False
        role = "admin"

        def get_id(self):
            return "admin"

    monkeypatch.setattr("flask_login.utils._get_user", lambda *a, **k: _DummyUser())
    return client


def _stub_options_payload():
    return {
        "options": {
            "regions": [{"id": "west", "label": "West", "bucket": "regions"}],
            "methods": [{"id": "ground", "label": "Ground", "bucket": "methods"}],
            "ship_methods": [{"id": "ground", "label": "Ground", "bucket": "ship_methods"}],
            "customers": [{"id": "Customer 1", "label": "Customer 1", "bucket": "customers"}],
            "suppliers": [],
            "products": [],
            "sales_reps": [],
            "statuses": [],
        },
        "dataset_version": "v1",
        "date_min": "2023-01-01",
        "date_max": "2023-12-31",
        "filters": {},
        "scope": {},
        "cached": False,
    }


def _safe_filters_payload(params):
    if hasattr(params, "start"):
        return filters_to_store(params)
    if isinstance(params, dict):
        return dict(params)
    return {}


def test_filters_options_etag_and_schema(monkeypatch, authed_client):
    monkeypatch.setattr(
        "app.services.filters_service.get_filter_options",
        lambda *a, **k: copy.deepcopy(_stub_options_payload()),
    )

    resp = authed_client.get("/api/filters/options")
    assert resp.status_code == 200
    data = resp.get_json()
    for key in ("options", "dataset_version", "date_min", "date_max"):
        assert key in data
    opts = data["options"]
    for key in ("regions", "methods", "ship_methods", "customers", "suppliers", "products", "sales_reps", "statuses"):
        assert key in opts

    etag = resp.headers.get("ETag")
    assert etag
    cache_header = resp.headers.get("Cache-Control", "")
    assert cache_header == "no-store, no-cache, must-revalidate, max-age=0"
    assert resp.headers.get("Pragma") == "no-cache"
    assert resp.headers.get("Expires") == "0"

    resp_304 = authed_client.get("/api/filters/options", headers={"If-None-Match": etag})
    assert resp_304.status_code == 304
    assert resp_304.get_data() in (b"",)


def test_filters_schema_uses_canonical_field_names(authed_client):
    resp = authed_client.get("/api/filters/schema")
    assert resp.status_code == 200
    data = resp.get_json()
    names = {field["name"] for field in data["fields"]}
    assert {"start_date", "end_date", "regions", "customers", "suppliers", "products", "sales_reps", "shipping_methods"} <= names


def test_filters_options_sanitizes_unauthorized_values_and_reports_notice(monkeypatch, authed_client):
    def _stub(params, *_args, **_kwargs):
        payload = copy.deepcopy(_stub_options_payload())
        payload["filters"] = _safe_filters_payload(params)
        return payload

    monkeypatch.setattr("app.services.filters_service.get_filter_options", _stub)

    resp = authed_client.get("/api/filters/options?regions=East&customers=Customer%209")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["filters"]["regions"] == []
    assert data["filters"]["customers"] == []
    assert data["meta"]["sanitized"] is True
    assert data["meta"]["dropped_filters"]["regions"] == ["East"]
    assert data["meta"]["dropped_filters"]["customers"] == ["Customer 9"]
    assert data["meta"]["filters_notice"]


def test_filters_options_sanitizes_status_only_tampering(monkeypatch, authed_client):
    def _stub(params, *_args, **_kwargs):
        payload = copy.deepcopy(_stub_options_payload())
        payload["filters"] = _safe_filters_payload(params)
        return payload

    monkeypatch.setattr("app.services.filters_service.get_filter_options", _stub)

    resp = authed_client.get("/api/filters/options?statuses=forbidden")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["filters"]["statuses"] == []
    assert data["meta"]["sanitized"] is True
    assert data["meta"]["dropped_filters"]["statuses"] == ["forbidden"]
    assert data["meta"]["filters_notice"]


def test_filters_options_only_requests_needed_dimensions(monkeypatch, authed_client):
    captured = {}

    def _stub(params, _scope, *, requested_keys=None, **_kwargs):
        captured["requested_keys"] = tuple(requested_keys or ())
        payload = copy.deepcopy(_stub_options_payload())
        payload["options"] = {
            "regions": payload["options"]["regions"],
            "methods": payload["options"]["methods"],
            "ship_methods": payload["options"]["ship_methods"],
        }
        payload["filters"] = _safe_filters_payload(params)
        return payload

    monkeypatch.setattr("app.services.filters_service.get_filter_options", _stub)

    resp = authed_client.get("/api/filters/options?dimensions=regions,methods")
    assert resp.status_code == 200
    data = resp.get_json()

    assert captured["requested_keys"] == ("regions", "methods", "ship_methods")
    assert data["meta"]["requested_dimensions"] == ["regions", "methods", "ship_methods"]
    assert set(data["options"].keys()) == {"regions", "methods", "ship_methods"}


def test_filters_options_degraded_fallback_returns_200(monkeypatch, authed_client):
    monkeypatch.setattr(
        "app.services.filters_service.get_filter_options",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("options backend exploded")),
    )

    resp = authed_client.get("/api/filters/options?dimensions=regions")
    assert resp.status_code == 200
    data = resp.get_json()

    assert data["meta"]["degraded"] is True
    assert data["meta"]["requested_dimensions"] == ["regions"]
    assert data["meta"]["option_counts"]["regions"] == 0
    assert data["options"]["regions"] == []


def test_sanitize_filters_does_not_fetch_all_time_options_by_default(monkeypatch):
    monkeypatch.setattr(canonical_filters, "_OPTIONS_ALLOWLIST_SANITIZE", False)
    monkeypatch.setattr(
        "app.services.filters_service.get_filter_options",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("unexpected options fetch")),
    )

    params, meta = canonical_filters.sanitize_filters(
        {"regions": ["West"]},
        scope={"is_admin": True, "scope_mode": "all"},
        include_meta=True,
    )

    assert tuple(params.regions) == ("West",)
    assert meta["sanitized"] is False
