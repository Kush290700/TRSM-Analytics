# Cleanup Notes

## Plan Checklist
- [x] Inventory recommendation page references and remove end-to-end (routes, templates, bundles, nav, tests, docs).
- [x] Add/confirm fast smoke test entrypoint using Flask test_client for key routes and bundles.
- [x] Identify unused/legacy files with reference evidence; delete or move to `app/deprecated/`.
- [x] Apply production hardening updates (API error shape, cache keys, health endpoint, logging).
- [ ] Run tests/smoke and record results.

## Deletion Evidence Log
- Recommendations page removed: `app/blueprints/recommendations.py`, `app/templates/recommendations/`, `/api/recommendations/bundle` route, nav link, and tests/docs references (no remaining `/recommendations` links in `app/templates`; `rg -n "recommendations" app` now only shows product/overview features).
- Legacy options blueprint removed: `app/blueprints/options.py` (not registered; `rg -n "/api/options" app` returned no references).
- Unused templates removed: `app/templates/_filters_backup.html`, `app/templates/overview.html`, `app/templates/products/overview.html`, `app/templates/bundle_page.html` (no references via `rg -n "overview.html|products/overview.html|bundle_page.html|_filters_backup.html" app`).
- Unused JS removed: `app/static/js/bundle-page.js`, `app/static/js/overview-enhanced.js`, `app/static/js/overview-enhanced-fixed.js`, `app/static/js/products_overview.js`, `app/static/js/utils.js` (no references in templates).
- Unused CSS removed: `app/static/css/app.css`, `app/static/css/products.css`, `app/static/css/sales_rep.css` (no references in templates).

## Test Runs
- Pending
