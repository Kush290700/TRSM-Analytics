## 👑 IMPORTANT: ALWAYS READ AI_MAP.md FIRST FOR STRATEGIC GUIDANCE
## 🌟 READ PROJECT_VISION.md FOR HIGH-LEVEL CONTEXT

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Dev server (fast, skips seed/smoke)
make run

# Run tests (excludes slow)
make test

# Run all tests
make test-all

# Run a single test file
python -m pytest tests/test_salesreps_bundle.py -x -q

# Run a single test by name
python -m pytest tests/test_salesreps_bundle.py::test_function_name -x -q

# Lint (black check + ruff + mypy + bandit)
make lint

# Auto-format (ruff import sort + black)
make format

# Smoke checks
make smoke         # parquet/DuckDB
make smoke-rbac    # auth/RBAC
make smoke-fact    # DuckDB fact
make check-static  # static asset presence (requires running app)

# User management
python manage.py init-auth-db
python manage.py create-admin --username=admin --role=admin
```

## Architecture Overview

### Data Flow
`MSSQL → data_loader.py / etl/*.py → Parquet → DuckDB (fact_store.py) → service/bundle layer → Flask blueprints → Jinja templates + JS`

The primary analytics data store is DuckDB-backed Parquet (see `app/services/fact_store.py`). Most query entry points go through `fact_store` rather than live SQL. The `FilterParams` dataclass (`app/services/filters.py`) is the canonical filter envelope passed through the stack — it is frozen/immutable and shared across all analytics modules (except Labor, which has its own `LaborFilters`).

### Request Path
`Blueprint route (app/blueprints/*.py)` → `service/bundle module (app/services/*_bundle.py)` → `Jinja template (app/templates/)` with a JSON payload embedded in a `<script>` tag, consumed by the page JS (`app/static/js/`).

For bundle pages (customers, products, suppliers, regions, salesreps) the pattern is:
1. Route resolves filters via `resolve_filters()` + applies RBAC scope via `access_policy.get_current_scope()`
2. Calls the entity `*_bundle.py` to assemble a payload dict
3. Passes payload to the template, which boots the JS and calls render functions

### RBAC + Sensitive Data
RBAC is layered: `app/core/access_policy.py` → `app/core/rbac.py` → `app/auth/permissions.py`. Key guards: `can_view_costs()`, `can_view_margin()`, `can_view_profit()`. Sensitive data masking is centralized in `app/core/sensitive_data.py` — use `sensitive_access_flags()` and `mask_sensitive_fields()` rather than hand-rolling checks. Any new field containing "cost", "margin", "profit", "cogs", or "spend" is auto-detected by the masking layer.

### Bundle Contracts
`app/services/bundle_builder.py` defines `BundleContract` with required keys per page (`kpis`, `trend`, `table`, `meta` for most entities). New bundle keys must be additive — never rename existing keys. JS must guard every new key: `const x = payload.new_key ?? fallback`.

### Module Ownership
| Module | Blueprint | Service/Bundle | Template dir |
|---|---|---|---|
| Sales Reps | `blueprints/salesreps.py` | `services/salesreps_bundle.py` | `templates/salesreps/` |
| Customers | `blueprints/customers.py` | `services/customers_bundle.py` | `templates/customers/` |
| Products | `blueprints/products.py` | `services/products_bundle.py` | `templates/products/` |
| Suppliers | `blueprints/suppliers.py` | `services/suppliers_bundle.py` | `templates/suppliers/` |
| Regions | `blueprints/regions.py` | `services/regions_bundle.py` | `templates/regions/` |
| Overview | `blueprints/overview.py` | `services/overview_v2.py` + `overview_metrics/forecast/query/summary/insights.py` | `templates/overview/` |
| Labor | `blueprints/labor.py` | `services/labor_bundle.py` | `templates/labor/` |
| Returns | `returns/blueprints.py` | `returns/service.py` | `templates/returns/` |
| Assistant | `assistant/routes.py` | `assistant/service.py` + `tools.py` | `templates/assistant/` |

### Global Filters
Global filters are shared across analytics pages via `app/templates/base.html` + `app/templates/_filters.html`. Filter state persists in session (sticky filters/saved views). The canonical filter behavior is documented in `docs/FILTERS_CANONICAL_V2_RUNBOOK.md`. Do not introduce page-local filter parsing when shared `resolve_filters()` already covers it.

### Brand Tokens (fixed — do not deviate)
```css
--trsm-primary:      #965951
--trsm-accent:       #d39c5f
--trsm-dark:         #111111
--trsm-primary-soft: #f7efec
```
These live in `app/static/css/theme.css`. Use CSS classes and variables — avoid inline styles for anything the CSS layer already handles.

### High-Risk Areas (validate carefully before changing)
- **Global filters**: `app/templates/base.html`, `_filters.html`, `app/core/filters.py`, `app/services/filters.py`, `app/services/filters_service.py`, `app/static/js/global_filters.js`
- **RBAC/permissions**: `app/core/access_policy.py`, `app/core/rbac.py`, `app/auth/permissions.py`
- **Export + masking**: `app/core/exports.py`, `app/core/sensitive_data.py`
- **Shared bundle plumbing**: `app/services/bundle_service.py`, `app/services/bundle_builder.py`
- **Shared JS utilities**: `app/static/js/exports.js`, `app/static/js/bundle-adapter.js`, `app/static/js/universal_drilldown.js`
- **Overview KPI comparisons**: `app/services/overview_metrics.py`, `app/services/overview_v2.py` — period labels and matched-day comparisons are business logic

### Revenue-Weighted Margin
Aggregate `margin_pct` must always be revenue-weighted, not a simple mean:
```python
weighted = sum(r * m for r, m in zip(revenues, margins)) / sum(revenues)
```

### Safe Division
Use `None` (never `0.0`) for undefined rates:
```python
pct = (a - b) / b if b else None
```

## Key Docs
- `CODEX.md` — authoritative repo-specific working guide
- `docs/REPO_MAP.md` — route/service/template file lookup
- `docs/TESTING_MATRIX.md` — targeted validation matrix
- `docs/FILTERS_CANONICAL_V2_RUNBOOK.md` — sticky views and filter behavior
- `docs/admin_rbac_architecture.md` — permissions and admin scope

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `python3 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"` to keep the graph current
