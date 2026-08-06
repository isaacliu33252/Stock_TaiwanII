# Outputs Schema Migration

Detailed implementation handoff:

- `handoff/OUTPUTS_SCHEMA_MIGRATION_HANDOFF_20260729.md`

## Decision

Use `outputs/` as the canonical destination for new report artifacts, while keeping legacy compatibility paths during migration:

- Current compatibility paths:
  - `report/`
  - `results/`
  - `FinRL/report/`
  - `FinRL/results/`
- New canonical root:
  - `outputs/group_a_plus/`

Do not bulk-move existing files until the consuming scripts and tests have been migrated.

## Canonical Layout

```text
outputs/
  group_a_plus/
    latest/
    production/
      backtest/
      dashboard/
      pipeline/
      portfolio/
      signal/
      validation/
    shadow/
      backtest/
      research/
      signal/
      validation/
    research/
      backtest/
      research/
      validation/
```

## Common JSON Envelope

New JSON reports should use this top-level schema:

```json
{
  "schema_version": 1,
  "artifact_name": "daily_status",
  "artifact_kind": "pipeline",
  "run_mode": "production",
  "generated_at": "2026-07-29T10:00:00+00:00",
  "payload": {}
}
```

Supported `artifact_kind` values:

- `backtest`
- `signal`
- `validation`
- `dashboard`
- `portfolio`
- `research`
- `pipeline`

Supported `run_mode` values:

- `production`
- `shadow`
- `research`

## Migration Rule

For each script, migrate one output at a time:

1. Write the new canonical artifact through `group_a_plus.outputs.output_path(...)`.
2. Wrap new JSON reports with `group_a_plus.outputs.report_envelope(...)`.
3. Keep the existing legacy output path as a compatibility copy if another script, test, dashboard, or manifest still reads it.
4. Move readers to `outputs/`.
5. Remove the compatibility copy only after tests prove no legacy consumer remains.

## Migrated Writers

These writers currently keep their legacy path and also write a canonical `outputs/` copy:

| Artifact | Legacy Path | Canonical Path | Status |
| --- | --- | --- | --- |
| `strategy_env_health` | `report/group_a_plus/latest/strategy_env_health.json` | `outputs/group_a_plus/latest/strategy_env_health.json` | dual-write |
| `ops_health` | `report/group_a_plus/latest/ops_health.json` | `outputs/group_a_plus/latest/ops_health.json` | dual-write |
| `signal_alignment` | `report/group_a_plus/latest/signal_alignment.json` | `outputs/group_a_plus/latest/signal_alignment.json` | dual-write |
| `watchlist_news` | `report/group_a_plus/latest/watchlist_news.json` | `outputs/group_a_plus/latest/watchlist_news.json` | dual-write |
| `daily_status` | `results/group_a_plus_daily_status*.json` and managed latest pointer | `outputs/group_a_plus/latest/daily_status.json` | dual-write |

The canonical copies are wrapped with `group_a_plus.outputs.report_envelope(...)`.

## Do Not Do Yet

- Do not rename `report/group_a_plus/latest/strategy.json` until `group_a_plus.governance.latest` and related tests are migrated.
- Do not move `results/ncf_*` panel artifacts until `scripts/run/run_ncf_daily_pipeline.py` and its tests are updated.
- Do not move `data/private/group_a_plus_dashboard.html`; that is a private local dashboard output, not a public backtest report.
