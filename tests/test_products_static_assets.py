import pytest
from flask import url_for


def test_products_js_served(app):
    """Static products.js should be reachable and served as JavaScript."""
    with app.test_client() as client:
        resp = client.get("/static/js/products.js")
        assert resp.status_code == 200
        ctype = resp.headers.get("Content-Type", "")
        assert "javascript" in ctype or "text/js" in ctype
        body = resp.get_data(as_text=True)
        assert "renderActiveFilterSummary" in body
        assert "renderSectionBriefs" in body
        assert "renderProductIntel" in body


def test_products_js_url_for(app):
    with app.test_request_context():
        path = url_for("static", filename="js/products.js")
        assert path.endswith("products.js")


def test_products_workspace_css_served(app):
    with app.test_client() as client:
        resp = client.get("/static/css/products_workspace_v4.css")
        assert resp.status_code == 200
        ctype = resp.headers.get("Content-Type", "")
        assert "css" in ctype
        body = resp.get_data(as_text=True)
        assert ".products-sku-intel-panel" in body
        assert ".products-layer-context" in body
