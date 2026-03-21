import pandas as pd
import pytest

from app.blueprints import products as products_bp


def test_normalize_products_uses_weight_basis_and_preserves_qty():
    raw = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-01", "2024-02-01"]),
            "ProductId": ["A", "B"],
            "ProductName": ["Alpha", "Beta"],
            "Revenue": [1000.0, 500.0],
            "WeightLb": [120.0, 60.0],
            "ItemCount": [10, 5],
        }
    )

    normalized = products_bp.normalize_products_df(raw)

    assert products_bp.CAN.qty_basis in normalized.columns
    assert normalized[products_bp.CAN.qty_basis].sum() > 0
    assert normalized[products_bp.CAN.qty_basis_label].iat[0] == "Weight (lb)"


def test_margin_pct_null_when_cost_missing():
    raw = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-03-01"]),
            "ProductId": ["A"],
            "ProductName": ["Alpha"],
            "Revenue": [200.0],
            "WeightLb": [40.0],
        }
    )
    normalized = products_bp.normalize_products_df(raw)
    rows = products_bp._top_products(normalized, limit=5)

    assert rows and rows[0]["margin_pct"] is None


def test_margin_pct_null_when_cost_zero():
    raw = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-03-01"]),
            "ProductId": ["A"],
            "ProductName": ["Alpha"],
            "Revenue": [200.0],
            "Cost": [0.0],
            "WeightLb": [40.0],
        }
    )
    normalized = products_bp.normalize_products_df(raw)
    rows = products_bp._top_products(normalized, limit=5)

    assert rows and rows[0]["margin_pct"] is None


def test_margin_pct_null_when_revenue_negative():
    raw = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-03-01"]),
            "ProductId": ["A"],
            "ProductName": ["Alpha"],
            "Revenue": [-50.0],
            "Cost": [10.0],
            "WeightLb": [5.0],
        }
    )
    normalized = products_bp.normalize_products_df(raw)
    rows = products_bp._top_products(normalized, limit=5)

    assert rows and rows[0]["margin_pct"] is None


def test_margin_pct_uses_totals():
    raw = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-03-01", "2024-03-02"]),
            "ProductId": ["A", "A"],
            "ProductName": ["Alpha", "Alpha"],
            "Revenue": [100.0, 300.0],
            "Cost": [50.0, 270.0],
            "WeightLb": [10.0, 30.0],
        }
    )
    normalized = products_bp.normalize_products_df(raw)
    rows = products_bp._top_products(normalized, limit=5)

    assert rows
    assert rows[0]["margin_pct"] == pytest.approx(20.0, abs=0.01)
