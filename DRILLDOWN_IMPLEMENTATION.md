# Products Drilldown Implementation Guide

## Summary

The **Products Drilldown** page is now fully functional and production-ready. All template variables are properly computed, forecast logic is toggled via URL parameter, RBAC controls cost visibility, and export endpoints support both XLSX and CSV formats.

## Files Changed

### 1. `app/blueprints/products.py`
- **New Imports**: Added `BytesIO`, `can_view_costs` from RBAC module
- **New Helper Functions**:
  - `_simple_forecast(df, periods=6)` - Simple moving average forecast (6-month, no Prophet)
  - `_lifecycle_stage(df)` - Product lifecycle classification (Growth/Stable/Mature/Decline)
  - `_anomalies(df, z_threshold=3.0)` - Revenue anomaly detection using z-scores
  - `_price_optimization_insights(df)` - Sales-only price guidance
  - `_top_customers_for_product(df, limit=10)` - Top customers by revenue
  - `_customer_options_for_product(df)` - Customer dropdown list
  - `_price_suggestion_for_customer(df, customer_id)` - Per-customer price suggestion
  - `_abc_xyz_classification(df)` - ABC-XYZ demand classification

- **New Routes**:
  - `GET /products/<product_id>/drilldown` - Main drilldown page
  - `GET /products/<product_id>/export` - XLSX/CSV export endpoint

### 2. `tests/test_products_drilldown.py` (NEW)
- Comprehensive smoke tests covering:
  - Drilldown page rendering
  - Forecast toggle (`?forecast=1`)
  - Customer filter (`?customer=<id>`)
  - 404 handling for missing products
  - Template variable presence verification
  - XLSX/CSV export functionality
  - Empty data graceful handling
  - Analytics classifications (Lifecycle, ABC-XYZ)

## Template Variables Provided

All 30+ variables required by `products/drilldown.html` are now properly populated:

| Variable | Type | Description |
|----------|------|-------------|
| `product_id` | str | Product SKU/ID |
| `product_name` | str | Human-readable product name |
| `currency_code` | str | Currency (from config, default "CAD") |
| `qty_title` | str | Quantity unit label (default "Quantity") |
| `show_costs` | bool | RBAC permission for cost view |
| `product_snapshot` | dict | KPIs: revenue, qty, weight, customers, velocity, MoM%, YoY%, ASP, etc. |
| `months` | list[str] | YYYY-MM format month strings |
| `monthly_revenue` | list[float] | Revenue per month |
| `monthly_qty` | list[float] | Quantity per month |
| `forecast` | dict | Rich forecast object {model, confidence, mape, dates, yhat, lower, upper} |
| `forecast_ds` | list[str] | Forecast dates (YYYY-MM) |
| `forecast_yhat` | list[float] | Forecast point estimates |
| `forecast_lower` | list[float] | Forecast 95% lower bound |
| `forecast_upper` | list[float] | Forecast 95% upper bound |
| `unit_price_stats` | dict | {p10, p50, p90} percentiles |
| `unit_prices` | list[float] | Sample of transaction unit prices |
| `region_labels` | list[str] | Top 10 regions |
| `region_values` | list[float] | Revenue per region |
| `supplier_labels` | list[str] | Top 10 suppliers |
| `supplier_values` | list[float] | Revenue per supplier |
| `top_cust_rows` | list[dict] | Top 10 customers [{customer_id, Customer, Revenue}] |
| `cust_options` | list[dict] | All customers for dropdown [{id, label}] |
| `selected_cid` | int/str/None | Currently selected customer from `?customer=<id>` |
| `price_suggestion` | dict | {current_price, suggested_price, rationale} for selected customer |
| `lifecycle` | dict | {stage, confidence, growth_rate, recent_avg, message} |
| `abc_xyz_class` | str | Classification like "AX", "BZ", etc. |
| `cv_value` | float | Coefficient of variation % |
| `anomalies` | list[dict] | Detected revenue spikes/drops [{date, value, expected, z_score, severity}] |
| `price_insights` | dict | {elasticity, current_avg_price, optimal_price_min/max, recommendation} |
| `recommendations` | list[dict] | Co-purchase bundle recommendations |

## Key Features

### 1. Forecast Toggle
- **Default**: No forecast (faster page load)
- **?forecast=1**: Computes 6-month moving average forecast with confidence bands
- **Implementation**: `_simple_forecast()` uses pandas rolling/polynomial without Prophet dependency
- **Format**: YYYY-MM dates, suitable for Plotly rendering

### 2. RBAC-Aware Cost Visibility
```python
show_costs = can_view_costs(current_user)
# Passed to template; controls visibility of cost-based metrics
# Price suggestions use sales-only heuristics if costs hidden
```

### 3. Customer-Specific Price Suggestion
- **URL**: `?customer=<customer_id>`
- **Computes**: Current avg price, suggested price (75th percentile), rationale
- **Fallback**: Form shows dropdown of all customers, defaults to empty

### 4. Advanced Analytics
- **Lifecycle**: Growth/Stable/Mature/Decline classification based on trend
- **ABC-XYZ**: Product portfolio matrix (e.g., "AY" = high revenue, moderate variability)
- **Anomalies**: Z-score detection of revenue spikes/drops
- **Price Optimization**: Conservative sales-only guidance (optimal price range)

### 5. Export Functionality
- **XLSX**: Multi-sheet (Product Data + Summary), styled header, auto-width columns
- **CSV**: Simple transaction-level export
- **Route**: `GET /products/<product_id>/export?format=xlsx|csv`

## Safe Defaults

**All analytics have graceful fallbacks for missing/empty data:**

```python
# Example: Unit price stats default to None
unit_price_stats = {
    "p10": float(...) if not up.empty else None,
    "p50": float(...) if not up.empty else None,
    "p90": float(...) if not up.empty else None,
}

# Forecast returns empty dict if insufficient data
forecast_obj = {}  # page renders with empty arrays in JS

# Price suggestion only shown if customer selected AND data exists
price_suggestion = {} or {...}

# Recommendations always included (may be empty list)
recommendations = build_product_recommendations(...)
```

## Running Tests

### Full Test Suite
```bash
pytest tests/test_products_drilldown.py -v
```

### Specific Test
```bash
pytest tests/test_products_drilldown.py::test_drilldown_page_renders -v
```

### With Coverage
```bash
pytest tests/test_products_drilldown.py --cov=app.blueprints.products --cov-report=term-missing
```

## Local Testing (Flask Development Server)

### Prerequisites
```bash
# Install dependencies (if not already done)
pip install -r requirements-dev.txt
pip install openpyxl  # for XLSX export

# Ensure parquet file configured
export PRODUCTS_SALES_PARQUET=/path/to/sales.parquet
```

### Run App
```bash
flask run
# Or
python run.py
```

### Access Drilldown
```
http://localhost:5000/products/SKU-001/drilldown
http://localhost:5000/products/SKU-001/drilldown?forecast=1
http://localhost:5000/products/SKU-001/drilldown?customer=123
http://localhost:5000/products/SKU-001/drilldown?forecast=1&customer=123
```

### Export
```
http://localhost:5000/products/SKU-001/export?format=xlsx
http://localhost:5000/products/SKU-001/export?format=csv
```

## Design Decisions

### Why Simple Forecast (Not Prophet)
- ✅ No external heavy dependencies
- ✅ Fast computation (in-process)
- ✅ Suitable for UI display (not required to be ML-grade)
- ✅ Easy to explain (moving average + linear trend)
- ⚠️ If Prophet needed later, can drop-in replace `_simple_forecast()`

### Why Sales-Only Price Heuristics
- ✅ Works even without cost data
- ✅ RBAC controls when to use cost-based (future)
- ✅ Conservative recommendations (safe for pricing team)
- ⚠️ Can extend with cost-based logic if `show_costs=True`

### DataFrame Filtering
- Uses `apply_filters()` from existing products blueprint
- Respects time window, regions, suppliers, customers filters
- Ensures analytics reflect same data as overview page

### Lazy Chart Rendering
- Template uses `IntersectionObserver` to render Plotly on-demand
- Avoids loading unused charts
- Forecast chart only rendered if forecast data present

## Common Issues & Fixes

| Issue | Cause | Fix |
|-------|-------|-----|
| 404 on drilldown | Product has no data in parquet | Ensure product_id exists in filtered dataset |
| Empty forecasts | Only 1-2 months of history | Need 3+ months to compute moving average |
| Missing XLSX export | `openpyxl` not installed | `pip install openpyxl` |
| Customer dropdown empty | No customer_id column in data | Check `CAN.customer_id` mapping in `_standardize_sales_df()` |
| Price suggestion not shown | Customer not in selected product's data | Check customer filter |

## Future Enhancements

1. **Cost-Based Pricing** (if `show_costs=True`)
   - Compute margin-aware optimal price
   - Add cost trend to drilldown

2. **Improved Forecasting**
   - Optional Prophet integration (feature flag)
   - Seasonality detection

3. **Anomaly Detail Pages**
   - Root cause analysis (which customers, regions drove anomaly?)
   - Comparison to peer products

4. **Cohort Analysis**
   - Customer lifetime value by product
   - Purchase frequency patterns

## Logging

Production logs include:
```python
logger.info(f"Drilldown rendered for product {product_id}, with {len(months_list)} months, forecast={bool(forecast_obj)}")
logger.error(f"Forecast generation failed for {product_id}: {e}")
logger.error(f"XLSX export failed for {product_id}: {e}")
```

Monitor these for debugging rendering issues.

## Compliance Notes

✅ **RBAC**: Cost view controlled by `can_view_costs()`  
✅ **Performance**: LRU cache on top-level payload builders; lazy chart rendering  
✅ **Error Handling**: 404 for missing products, graceful fallbacks for missing data  
✅ **Security**: All user input (product_id, customer_id) sanitized before DataFrame ops  
✅ **Testing**: 14 tests covering happy path, edge cases, and error conditions  

---

**Status**: Production-Ready ✅  
**Last Updated**: 2025-12-08  
**Tested with**: Python 3.9+, pandas 2.0+, numpy 1.24+
