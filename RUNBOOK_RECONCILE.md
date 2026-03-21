# Revenue / Product Parity Runbook (Admin)

1) **Validate loader vs SQL**
   - `python data_loader.py validate-revenue-parity --start 2018-01-01 --end 2035-01-01 --status packed`
   - Expect pct_diff within 1%.

2) **Audit persisted snapshot**
   - `python data_loader.py audit-persisted --start 2018-01-01 --end 2035-01-01 --statuses packed`
   - Compares parquet vs live loader (rows, products, revenue). Fail if >1% gap.

3) **Backend checkpoints**
   - Hit `/admin/overview` (or APIs). Check logs for `fact_checkpoint` stages:
     - `loader.extract.pack_sql`, `loader.finalize.fact`, `loader.persist.parquet`
     - `backend.request.pre_sql`, `backend.fact.filtered`
     - `backend.overview.frame_loaded`, `backend.overview.frame_filtered`
   - Headers in responses: `X-Cache-Hit`, `X-Cache-Key`, `X-Cache-Age-Seconds`.

4) **Admin scope**
   - Admin requests should log `scope_applied=False` and no region/sales filters. If scope appears, fix the user scope record then retry.

5) **Cache and joins**
   - If stale data suspected: `curl -X POST /api/_admin/debug/cache/flush`.
   - Dimension gaps are logged (`fact_context.dimension_gaps`). Any gaps require LEFT joins/fill logic, not row drops.
