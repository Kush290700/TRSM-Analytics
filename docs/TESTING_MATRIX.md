# Testing Matrix

## Default Validation Flow
- Run `make lint` before broad refactors or shared-layer edits.
- Run the smallest relevant pytest subset first.
- If the change touches filters, RBAC, exports, or shared bundles, expand validation beyond the page you edited.
- Use smoke scripts when the change depends on real parquet/DuckDB data behavior.

## Overview Changes
- Use when editing:
  - `app/blueprints/overview.py`
  - `app/services/overview_*.py`
  - overview templates/JS
- Targeted tests:
  - `python3 -m pytest tests/test_overview.py tests/test_overview_api.py tests/test_overview_bundle.py tests/test_overview_metric_contract.py tests/test_overview_v2_smoke.py -q`
- Add when KPI/comparison logic changes:
  - `python3 -m pytest tests/test_overview_parity.py tests/test_overview_insights.py -q`
  - `python3 scripts/overview_golden_smoke.py --start 2025-01-01 --end 2025-03-31` if a representative local dataset is available
- Add when forecast logic changes:
  - `python3 -m pytest tests/test_overview_forecast.py -q`
- Frontend smoke:
  - `python3 -m pytest tests/test_overview_playwright.py -q`
  - `bash scripts/check_static_assets.sh`

## Customer Page or Drilldown Changes
- Use when editing:
  - `app/blueprints/customers.py`
  - `app/services/customers_bundle.py`
  - `app/services/customers_cohorts_v2.py`
  - customer templates or drilldown JS/CSS
- Targeted tests:
  - `python3 -m pytest tests/test_customers_bundle_sections.py tests/test_customers_bundle_extra.py tests/test_customers_drilldown_v2.py -q`
- Add based on touched page:
  - CLV: `tests/test_customers_clv_v2.py`
  - Cohorts: `tests/test_customers_cohorts_v2.py`
  - KPIs: `tests/test_customers_kpis_v2.py tests/test_customers_kpis_v3.py`
  - RFM: `tests/test_customers_rfm_v2.py`
- If exports changed:
  - rerun the relevant customer tests and inspect `/customers/export` code paths in the same change

## Product Page or Drilldown Changes
- Use when editing:
  - `app/blueprints/products.py`
  - `app/services/products_bundle.py`
  - `app/services/product_drilldown_service.py`
  - product templates/JS/CSS
- Targeted tests:
  - `python3 -m pytest tests/test_products_bundle_api.py tests/test_products_overview_service.py tests/test_products_drilldown.py tests/test_product_drilldown_v2.py -q`
- Add based on touched area:
  - filters: `tests/test_products_filters.py`
  - exports: `tests/test_products_exports.py`
  - static assets/page shell: `tests/test_products_static_assets.py`
  - frontend smoke: `tests/test_products_playwright.py`
  - forecast: `tests/test_products_forecast.py`

## Supplier / Region / Sales Rep Changes
- Suppliers:
  - `python3 -m pytest tests/test_suppliers_v2.py tests/test_supplier_drilldown_v2.py tests/test_suppliers_metrics.py tests/test_suppliers_products_export.py -q`
- Regions:
  - `python3 -m pytest tests/test_regions_bundle.py tests/test_regions_drilldown_bundle.py tests/test_regions_drilldown_v2.py tests/test_regions_v2.py -q`
- Sales reps:
  - `python3 -m pytest tests/test_salesreps_bundle.py tests/test_salesreps_drilldown_bundle.py tests/test_salesreps_exports.py tests/test_salesreps_v2.py -q`

## Labor Changes
- Use when editing:
  - `app/blueprints/labor.py`
  - `app/services/labor_*.py`
  - `app/services/synerion_client.py`
  - labor template/JS/CSS
- Targeted tests:
  - `python3 -m pytest tests/test_labor_blueprint.py tests/test_labor_loader.py tests/test_labor_store.py tests/test_synerion_client.py -q`
- Add if ETL/storage logic changed:
  - `python3 scripts/fact_smoke.py`

## Filter Changes
- Use when editing:
  - `app/services/filters.py`
  - `app/services/filters_service.py`
  - `app/blueprints/filters_api.py`
  - `app/blueprints/filters_actions.py`
  - shared filter templates or JS
- Targeted tests:
  - `python3 -m pytest tests/test_filters_canonical_v2.py tests/test_filters_global.py tests/test_filters_options_contract.py tests/test_filters_options_endpoint.py tests/test_filter_form_contract.py tests/test_sticky_filters.py -q`
- Add when protein filters change:
  - `python3 -m pytest tests/test_filters_protein.py -q`
- Frontend smoke:
  - `python3 -m pytest tests/test_filters_ui_smoke.py -q`
  - `npx playwright test tests/playwright/filters.spec.ts` if local browser deps are installed

## Forecast Logic Changes
- Overview forecast:
  - `python3 -m pytest tests/test_overview_forecast.py -q`
- Product forecast:
  - `python3 -m pytest tests/test_products_forecast.py -q`
- Also validate:
  - warnings/partial-period behavior
  - export payload shape if forecast rows are exposed to UI/API
  - recent-history / sparse-history fallbacks

## RBAC / Access Control Changes
- Use when editing:
  - `app/core/access_policy.py`
  - `app/core/rbac.py`
  - `app/auth/permissions.py`
  - admin/user visibility code
- Targeted tests:
  - `python3 -m pytest tests/test_rbac_access.py tests/test_rbac_scope.py tests/test_admin_permissions_v2.py tests/test_admin_rbac_portal.py tests/test_admin_user_select.py tests/test_auth_gate.py -q`
- Quick smoke:
  - `python3 scripts/smoke_rbac.py`

## Export Logic Changes
- Use when editing:
  - `app/core/exports.py`
  - `app/core/sensitive_data.py`
  - module export endpoints
- Targeted tests:
  - customer exports are covered by the relevant customer page tests
  - `python3 -m pytest tests/test_products_exports.py tests/test_salesreps_exports.py tests/test_suppliers_products_export.py tests/test_returns_module.py -q`
- Required manual review:
  - confirm export dataset matches on-screen scope/filters
  - confirm cost/margin/profit masking still applies to unauthorized roles

## Returns Changes
- Use when editing `app/returns/*`
- Targeted tests:
  - `python3 -m pytest tests/test_returns_module.py -q`
- Add if auth/permissions changed:
  - RBAC set above

## Assistant Changes
- Use when editing `app/assistant/*`
- Targeted tests:
  - `python3 -m pytest tests/test_assistant_feature.py tests/test_assistant_provider.py -q`
- Add if export/download flow changed:
  - validate assistant export endpoints still require authenticated user ownership

## Backend/Data Checks After KPI or Query Changes
- Use when editing query logic, aggregations, bundle metrics, or fact-store behavior.
- Targeted tests:
  - `python3 -m pytest tests/test_data_access_consistency.py tests/test_fact_etl.py tests/test_fact_normalization_costs.py tests/test_fact_packs_only.py tests/test_schema.py -q`
- Smoke scripts:
  - `python3 scripts/smoke.py`
  - `python3 scripts/fact_smoke.py`
  - `python3 scripts/fact_freshness_check.py` when freshness assumptions changed

## Frontend-Only Changes
- Use when changing templates, page JS, CSS, or shared UI assets without backend logic changes.
- Minimum checks:
  - `bash scripts/check_static_assets.sh`
  - the page-specific pytest/Playwright tests from the relevant section above
- Also confirm:
  - no console errors
  - filter shell still renders where expected
  - export buttons still point at the correct endpoints
