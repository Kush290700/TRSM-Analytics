## Fact dataset ETL runbook

### Paths
- Dataset directory: `cache/fact_dataset/`
- Manifest: `cache/fact_dataset/_manifest.json`
- Lock file: `cache/fact_dataset/.refresh.lock`

### Quick diagnostics (duplicates + 2026)
Preferred (self-contained) smoke check:
```bash
python3 scripts/fact_smoke.py
```

DuckDB SQL checks (run from the app/ETL repo root; uses `cache/fact_dataset/**/*.parquet`):
```bash
# If you have a duckdb CLI available:
duckdb -c ".read scripts/fact_checks.sql"
```

### One-time build
```bash
python run.py build-fact --start 2017-01-01 --end today
```

### One-time dedupe / rebuild (use if duplicates already exist)
This will rebuild the dataset keeping the newest row per `OrderLineId` (UpdatedAt desc, then Date desc).
```bash
python3 scripts/dedupe_fact_dataset.py --keep-prev
```

### Incremental refresh (manual)
```bash
python run.py refresh-fact --once
```

### Refresh idempotency check (runs refresh twice)
```bash
python3 scripts/check_refresh_idempotency.py \
  --cmd "python run.py refresh-fact --once --mode gap-backfill --backfill-days 90"
```

### Continuous refresh (loop)
```bash
python run.py refresh-fact --loop --interval 300
```

### Scheduling (systemd)
Examples live in `deploy/fact-refresh.service` and `deploy/fact-refresh.timer`.
- Service (continuous loop):
  ```ini
  ExecStart=/opt/app/.venv/bin/python run.py refresh-fact --loop --interval 300
  ```
- Timer (preferred):
  ```ini
  ExecStart=/opt/app/.venv/bin/python run.py refresh-fact --once
  ```

### Monitoring
- Inspect `_manifest.json`:
  - `dataset_version`: bumps on each refresh
  - `built_at_utc` / `last_refresh_utc`: UTC timestamp of last successful write
  - `watermark` / `last_sql_watermark`: watermark sent to SQL
  - `row_count`, `min_date`, `max_date`, `schema_hash`
- Check `.refresh.lock` timestamp; remove only if clearly stale.
- Logs:
  - Parquet writes: `cache.parquet.write.*`, `cache.parquet.rewrite.*`
  - SQL fetch timing: `cache.fetch.complete`
  - Request timing: `fact.request.timing`

### When the API says "Dataset not built"
- Build once with `python run.py build-fact --start 2017-01-01 --end today`
- Ensure the manifest file exists and is readable by the web workers.
- Verify filesystem permissions on `cache/fact_dataset/` and the lock file.
