# CODEX Working Guide

## Project Overview
TRSM Analytics is a production Flask analytics application with RBAC-scoped dashboards and drilldowns for overview, customers, products, suppliers, regions, sales reps, labor, returns, and assistant workflows.

The application is not a simple CRUD app. Most user-visible pages sit on top of shared filter state, shared RBAC scope, DuckDB/parquet-backed analytics queries, and export paths that must stay consistent with page payloads.

Use this file as the authoritative repo-specific working guide. Use `docs/REPO_MAP.md` for file lookup and `docs/TESTING_MATRIX.md` for targeted validation.

Read these before editing:
- `README.md` for runtime/setup basics
- `docs/REPO_MAP.md` for route/service/template ownership
- `docs/TESTING_MATRIX.md` for targeted validation
- `docs/overview_architecture.md`
- `docs/customers_architecture.md`
- `docs/products_architecture.md`
- `docs/labor_architecture.md`

Deep dives when the task touches those areas:
- `docs/FILTERS_CANONICAL_V2_RUNBOOK.md` for canonical filter behavior and sticky views
- `docs/admin_rbac_architecture.md` for permissions/admin scope work
- `docs/returns_runbook.md` for returns workflows
- `docs/runbook_products_v4.md` and `docs/product_drilldown_v2_runbook.md` for active products variants

## Fast Start for Future Codex Sessions
1. Read `CODEX.md`, then `docs/REPO_MAP.md`, then the relevant module note, then `docs/TESTING_MATRIX.md`.
2. Identify the owning route first, then trace service/bundle logic, template, JS/CSS, export path, and tests before editing.
3. If the task touches filters, RBAC, exports, forecasting, or `app/templates/base.html`, inspect the shared systems before changing page-local code.
4. Confirm the active variant before editing when legacy and `v2`/`v3`/`v4` paths coexist or feature flags control template selection.
5. Run the smallest relevant validation first, then expand to smoke/static checks only where the change actually crosses module boundaries.

## Stack and Runtime
- Flask app factory: `app/__init__.py`
- Runtime entrypoints: `wsgi.py`, `run.py`, `manage.py`
- Data path: MSSQL -> `data_loader.py` / `etl/*.py` -> parquet -> DuckDB/read views -> service layer
- Core analytics storage/query layer: `app/services/fact_store.py`, `data/store.py`
- Templates: `app/templates/`
- Frontend assets: `app/static/js/`, `app/static/css/`
- Tests: `tests/` plus Playwright specs in `tests/playwright/`

## Important Directories
- `app/blueprints/`: Flask route layer for page and API endpoints
- `app/services/`: analytics/service layer; most business logic lives here
- `app/core/`: cross-cutting runtime, RBAC scope, exports, logging, masking
- `app/auth/`: auth models, canonical permission catalog, auth routes
- `app/returns/`: returns-specific blueprints, models, service logic
- `app/assistant/`: assistant routes, tool execution, export storage
- `app/templates/`: Jinja pages and shared partials
- `app/static/`: JS/CSS/image assets
- `docs/`: runbooks and repo guidance
- `etl/`: dataset build and incremental refresh
- `scripts/`: smoke/diagnostic helpers

## Module Ownership Quick Map
- Overview: `app/blueprints/overview.py` + `app/services/overview_*.py` + `app/templates/overview/`
- Customers: `app/blueprints/customers.py` + `app/services/customers_bundle.py` / `app/services/customers_cohorts_v2.py`
- Products: `app/blueprints/products.py` + `app/services/products_bundle.py` / `app/services/product_drilldown_service.py` / `app/services/products.py`
- Suppliers, regions, sales reps: entity blueprint + `app/services/bundle_service.py` + entity `*_bundle.py`
- Labor: `app/blueprints/labor.py` + `app/services/labor_bundle.py` / `app/services/labor_store.py`
- Returns: `app/returns/blueprints.py` + `app/returns/service.py` + `app/templates/returns/`
- Assistant: `app/assistant/routes.py` + `app/assistant/service.py` / `app/assistant/tools.py` / `app/assistant/provider.py`
- Shared systems: filters, exports/masking, RBAC, auth/admin, base shell assets

## Key Terms
- Bundle: the server-built payload for cards/tables/drilldowns, often assembled through `app/services/bundle_service.py` or an entity bundle module.
- Drilldown: the entity-detail surface behind a table/card click; often paired with separate export endpoints.
- `FilterParams`: the shared analytics filter envelope used across most sales/overview modules.
- `LaborFilters`: labor-specific filter model; do not treat it as interchangeable with `FilterParams`.
- Scope: the RBAC-constrained data visibility for the current user, enforced through `app/core/access_policy.py` and `app/core/rbac.py`.

## Core Architecture Patterns
- Blueprints should stay relatively thin. Route handlers usually delegate to service/bundle modules.
- Overview is a special stack. It uses `app/blueprints/overview.py` plus `app/services/overview_v2.py`, `app/services/overview_metrics.py`, `app/services/overview_forecast.py`, `app/services/overview_query.py`, `app/services/overview_summary.py`, and `app/services/overview_insights.py`.
- Customers, products, suppliers, regions, and sales reps are heavily bundle-driven. Start with `app/services/bundle_service.py`, then the entity-specific bundle/drilldown module.
- Global filters are shared across most analytics pages through `app/templates/base.html`, `app/templates/_filters.html`, `app/core/filters.py`, `app/services/filters.py`, `app/services/filters_service.py`, `app/blueprints/filters_api.py`, and `app/blueprints/filters_actions.py`.
- Export endpoints should usually mirror the same scoped dataset used by the page/API path. Frame-building helpers may live in services such as `app/services/exports.py`, but response generation and masking should still flow through `app/core/exports.py`.
- Sensitive export columns are masked centrally in `app/core/sensitive_data.py`; do not hand-roll masking logic in endpoints unless there is a strong reason.
- RBAC scope and permission checks are layered: `app/core/access_policy.py` -> `app/core/rbac.py` -> `app/auth/permissions.py` -> route/service checks.

## High-Risk Areas
- High risk: global filters and sticky saved views
  Files: `app/templates/base.html`, `app/templates/_filters.html`, `app/core/filters.py`, `app/static/js/global_filters.js`, `app/static/js/filters-enhanced.js`, `app/services/filters.py`, `app/services/filters_service.py`
- High risk: RBAC scope and permission enforcement
  Files: `app/core/access_policy.py`, `app/core/rbac.py`, `app/auth/permissions.py`, admin/user-management flows
- High risk: period-aware KPI comparisons
  Files: `app/services/overview_metrics.py`, `app/services/overview_v2.py`
  Rules here intentionally handle partial periods, matched-day comparisons, and current-vs-prior labels
- High risk: forecast model selection and partial-period handling
  Files: `app/services/overview_forecast.py`, product forecasting code in `app/blueprints/products.py`
- High risk: export safety and sensitive data masking
  Files: `app/core/exports.py`, `app/core/sensitive_data.py`, module export endpoints
- High risk: shared bundle plumbing
  Files: `app/services/bundle_service.py`, `app/services/bundle_builder.py`, entity bundle modules
- High risk: shared shell/template behavior
  Files: `app/templates/base.html`, shared partials, shared JS loaded globally
- High risk: shared JS utilities
  Files: `app/static/js/exports.js`, `app/static/js/bundle-adapter.js`, `app/static/js/universal_drilldown.js`
- High risk: auth/session/admin flows
  Files: `app/auth/*`, `app/blueprints/admin.py`, `app/blueprints/admin_api.py`, returns/assistant auth-sensitive routes

Do not casually refactor these areas without targeted validation.

## Editing Workflow
1. Trace the full stack before changing behavior: route -> service -> template -> JS/CSS -> export -> tests.
2. Confirm the active variant before editing when route code can render legacy and `v2`/`v3`/`v4` templates under different flags.
3. If a page uses bundle endpoints, inspect both the rendered page handler and the JSON/export endpoints for the same entity.
4. Preserve `FilterParams` semantics and canonical filter serialization; avoid introducing page-specific filter parsing when shared logic already exists.
5. Preserve RBAC scope on any new query, drilldown, recommendation, or export path.
6. Preserve export masking. New cost/margin/profit columns should be reviewed against `app/core/sensitive_data.py`.
7. Treat overview comparison labels and current/prior windows as business logic, not display-only text.
8. Do not remove legacy template variants or feature-flag branches unless you verify they are truly unused.
9. Avoid editing deployment/runtime files (`run.py`, `wsgi.py`, `gunicorn_conf.py`, `deploy/`) unless the task is explicitly operational.
10. Do not add real secrets, live user mapping data, or local datasets to git.

## Validation Workflow
- Start with the smallest relevant command set from `docs/TESTING_MATRIX.md`.
- Use the repo command surface:
  - `make run`
  - `make preflight` for runtime/setup changes only
  - `make test`
  - `make lint`
  - `make format`
  - `make check-static`
  - `make smoke`
  - `make smoke-rbac`
  - `make smoke-fact`
- For page changes, run targeted pytest modules first, then broader smoke if the change touches filters/RBAC/data access.
- For frontend/template edits, also run `make check-static` and the related Playwright or page smoke tests when available.
- For KPI/query/comparison changes, prefer a parity/smoke script in `scripts/` in addition to pytest.
- `make lint` assumes dev tooling from `requirements-dev.txt` or the project virtualenv is installed. If tools are missing, report that limitation instead of changing repo config to fit the shell.

## Git Hygiene
- Keep diffs narrow and module-local when possible.
- Prefer documentation and config additions that reduce future search time and editing risk.
- Avoid committing local scratch files; the repo ignores many root-level temp/debug patterns intentionally.
- Do not mix repo-guidance cleanup with production behavior changes in the same commit unless they are tightly coupled.
- If a task is exploratory, document the intended boundary in the commit message and avoid mixing unrelated cleanup.

## Production Safety Notes
- Labor intentionally uses its own filter model and hides the shared global filter shell on the page; do not force shared filters onto labor without design intent.
- Returns and admin flows are permission-sensitive and should be treated as operational surfaces, not regular dashboard pages.
- Assistant routes can create downloadable artifacts; preserve auth and export expiry/storage behavior.
- `app/core/userid.csv` is a placeholder path only. Do not replace it with live employee data.
