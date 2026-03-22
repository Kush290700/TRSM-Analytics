# CODEX Working Guide

## Project Overview
TRSM Analytics is a production Flask analytics application with RBAC-scoped dashboards and drilldowns for overview, customers, products, suppliers, regions, sales reps, labor, returns, and assistant workflows.

The application is not a simple CRUD app. Most user-visible pages sit on top of shared filter state, shared RBAC scope, DuckDB/parquet-backed analytics queries, and export paths that must stay consistent with page payloads.

Read these before editing:
- `README.md` for runtime/setup basics
- `docs/REPO_MAP.md` for route/service/template ownership
- `docs/TESTING_MATRIX.md` for targeted validation
- `docs/overview_architecture.md`
- `docs/customers_architecture.md`
- `docs/products_architecture.md`
- `docs/labor_architecture.md`

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

## Core Architecture Patterns
- Blueprints should stay relatively thin. Route handlers usually delegate to service/bundle modules.
- Overview is a special stack. It uses `app/blueprints/overview.py` plus `overview_v2.py`, `overview_metrics.py`, `overview_forecast.py`, `overview_query.py`, `overview_summary.py`, and `overview_insights.py`.
- Customers, products, suppliers, regions, and sales reps are heavily bundle-driven. Start with `app/services/bundle_service.py`, then the entity-specific bundle/drilldown module.
- Global filters are shared across most analytics pages through `app/templates/base.html`, `app/templates/_filters.html`, `app/core/filters.py`, `app/services/filters.py`, `app/services/filters_service.py`, `app/blueprints/filters_api.py`, and `app/blueprints/filters_actions.py`.
- Export endpoints should usually mirror the same scoped dataset used by the page/API path, then flow through `app/core/exports.py`.
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
- High risk: auth/session/admin flows
  Files: `app/auth/*`, `app/blueprints/admin.py`, `app/blueprints/admin_api.py`, returns/assistant auth-sensitive routes

Do not casually refactor these areas without targeted validation.

## Editing Rules
1. Trace the full stack before changing behavior: route -> service -> template -> JS/CSS -> export -> tests.
2. If a page uses bundle endpoints, inspect both the rendered page handler and the JSON/export endpoints for the same entity.
3. Preserve `FilterParams` semantics and canonical filter serialization; avoid introducing page-specific filter parsing when shared logic already exists.
4. Preserve RBAC scope on any new query, drilldown, recommendation, or export path.
5. Preserve export masking. New cost/margin/profit columns should be reviewed against `app/core/sensitive_data.py`.
6. Treat overview comparison labels and current/prior windows as business logic, not display-only text.
7. Do not remove legacy template variants or feature-flag branches unless you verify they are truly unused.
8. Avoid editing deployment/runtime files (`run.py`, `wsgi.py`, `gunicorn_conf.py`, `deploy/`) unless the task is explicitly operational.
9. Do not add real secrets, live user mapping data, or local datasets to git.

## Validation Workflow
- Start with the smallest relevant command set from `docs/TESTING_MATRIX.md`.
- Use the repo command surface:
  - `make run`
  - `make test`
  - `make lint`
  - `make format`
  - `make smoke`
  - `make smoke-rbac`
  - `make smoke-fact`
- For page changes, run targeted pytest modules first, then broader smoke if the change touches filters/RBAC/data access.
- For frontend/template edits, also run `bash scripts/check_static_assets.sh` and the related Playwright or page smoke tests when available.
- For KPI/query/comparison changes, prefer a parity/smoke script in `scripts/` in addition to pytest.

## Git and Diff Hygiene
- Keep diffs narrow and module-local when possible.
- Prefer documentation and config additions that reduce future search time and editing risk.
- Avoid committing local scratch files; the repo ignores many root-level temp/debug patterns intentionally.
- If a task is exploratory, document the intended boundary in the commit message and avoid mixing unrelated cleanup.

## Production Safety Notes
- Labor intentionally uses its own filter model and hides the shared global filter shell on the page; do not force shared filters onto labor without design intent.
- Returns and admin flows are permission-sensitive and should be treated as operational surfaces, not regular dashboard pages.
- Assistant routes can create downloadable artifacts; preserve auth and export expiry/storage behavior.
- `app/core/userid.csv` is a placeholder path only. Do not replace it with live employee data.
