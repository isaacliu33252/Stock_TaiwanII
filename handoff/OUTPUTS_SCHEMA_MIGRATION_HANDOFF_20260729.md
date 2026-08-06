# Outputs Schema Migration Handoff - 2026-07-29

## Scope

This handoff covers recommendation 9:

> Unify backtest/report output format. Current artifacts are scattered under `report/`, `results/`, `FinRL/report/`, and `FinRL/results/`; recommended direction is a single `outputs/` tree with a common JSON schema.

## Decision

The recommendation is reasonable and should continue, but the migration must be incremental.

Do not bulk-move the existing directories. Active code still reads these legacy paths directly:

- `report/group_a_plus/latest/strategy.json`
- `report/group_a_plus/latest/*.json`
- `results/ncf_*`
- `FinRL/report/`
- `FinRL/results/`

The safe migration pattern is:

1. Keep the old writer path.
2. Add a canonical `outputs/` copy.
3. Wrap only the canonical JSON copy with the common envelope.
4. Move readers to prefer `outputs/` with legacy fallback.
5. Remove old compatibility writes only after tests prove no active reader remains.

## Canonical Output Layout

New canonical root:

```text
outputs/group_a_plus/
```

Current intended layout:

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

Canonical JSON outputs should use:

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

## Implemented Files

Added:

- `group_a_plus/outputs.py`
- `tests/test_group_a_plus_outputs.py`
- `docs/OUTPUTS_SCHEMA_MIGRATION.md`
- `handoff/OUTPUTS_SCHEMA_MIGRATION_HANDOFF_20260729.md`

Modified:

- `scripts/run/run_ncf_daily_pipeline.py`
- `group_a_plus/integrations/signal_alignment.py`
- `group_a_plus/integrations/watchlist_news.py`
- `scripts/misc/check_group_a_plus_daily_status.py`
- `tests/test_group_a_plus_signal_alignment.py`
- `tests/test_group_a_plus_watchlist_news.py`
- `tests/test_check_group_a_plus_daily_status.py`
- `FINRL_CONSOLIDATION_ARCHIVE_CANDIDATES_20260729.md`

## New Helper API

Module:

```python
group_a_plus.outputs
```

Helpers:

```python
output_path(...)
report_envelope(...)
write_json_report(...)
```

Important behavior:

- `output_path(..., latest=True)` writes under `outputs/group_a_plus/latest/`.
- `output_path(..., latest=False)` writes under `outputs/group_a_plus/{run_mode}/{kind}/`.
- `write_json_report(...)` writes the common envelope and creates parent directories.
- Existing legacy files are not automatically redirected.

## Dual-Write Status

These artifacts now keep their legacy output and also write canonical enveloped JSON:

| Artifact | Legacy Path | Canonical Path | Writer |
| --- | --- | --- | --- |
| `strategy_env_health` | `report/group_a_plus/latest/strategy_env_health.json` | `outputs/group_a_plus/latest/strategy_env_health.json` | `scripts/run/run_ncf_daily_pipeline.py` |
| `ops_health` | `report/group_a_plus/latest/ops_health.json` | `outputs/group_a_plus/latest/ops_health.json` | `scripts/run/run_ncf_daily_pipeline.py` |
| `signal_alignment` | `report/group_a_plus/latest/signal_alignment.json` | `outputs/group_a_plus/latest/signal_alignment.json` | `group_a_plus/integrations/signal_alignment.py` |
| `watchlist_news` | `report/group_a_plus/latest/watchlist_news.json` | `outputs/group_a_plus/latest/watchlist_news.json` | `group_a_plus/integrations/watchlist_news.py` |
| `daily_status` | `results/group_a_plus_daily_status*.json` and managed latest pointer | `outputs/group_a_plus/latest/daily_status.json` | `scripts/misc/check_group_a_plus_daily_status.py` |

Legacy output format remains unchanged for compatibility.

## Daily Status Detail

`scripts/misc/check_group_a_plus_daily_status.py` gained:

```text
--canonical-output
```

Default:

```text
outputs/group_a_plus/latest/daily_status.json
```

Use an empty value to skip the canonical copy:

```bash
--canonical-output ""
```

## Validation Completed

Commands run:

```bash
.venv/bin/python -m pytest -q tests/test_group_a_plus_outputs.py tests/test_group_a_plus_latest_strategy.py tests/test_run_ncf_daily_pipeline.py
.venv/bin/python -m pytest -q tests/test_group_a_plus_outputs.py tests/test_run_ncf_daily_pipeline.py
.venv/bin/python -m pytest -q tests/test_group_a_plus_outputs.py tests/test_group_a_plus_signal_alignment.py tests/test_group_a_plus_watchlist_news.py
.venv/bin/python -m pytest -q tests/test_check_group_a_plus_daily_status.py tests/test_group_a_plus_signal_alignment.py tests/test_group_a_plus_watchlist_news.py tests/test_group_a_plus_outputs.py tests/test_run_ncf_daily_pipeline.py
```

Results:

- `52 passed`
- `28 passed`
- `40 passed`
- `86 passed`

Compile checks run:

```bash
.venv/bin/python -m py_compile group_a_plus/outputs.py tests/test_group_a_plus_outputs.py
.venv/bin/python -m py_compile group_a_plus/outputs.py scripts/run/run_ncf_daily_pipeline.py tests/test_group_a_plus_outputs.py
.venv/bin/python -m py_compile group_a_plus/outputs.py group_a_plus/integrations/signal_alignment.py group_a_plus/integrations/watchlist_news.py tests/test_group_a_plus_signal_alignment.py tests/test_group_a_plus_watchlist_news.py
.venv/bin/python -m py_compile scripts/misc/check_group_a_plus_daily_status.py group_a_plus/integrations/signal_alignment.py group_a_plus/integrations/watchlist_news.py group_a_plus/outputs.py tests/test_check_group_a_plus_daily_status.py
```

All returned success.

## Next Recommended Work

Next step should be reader migration, not more writer migration.

Good first reader candidates:

1. Dashboard health panels:
   - prefer `outputs/group_a_plus/latest/daily_status.json`
   - fallback to `report/group_a_plus/latest/daily_status.json`
   - unwrap canonical `payload` when present

2. Alert-state ops health reader:
   - prefer `outputs/group_a_plus/latest/ops_health.json`
   - fallback to `report/group_a_plus/latest/ops_health.json`
   - unwrap canonical `payload` when present

3. Final governance snapshot:
   - prefer canonical health/status artifacts
   - keep legacy fallback

## Do Not Do Yet

- Do not move or rename `report/group_a_plus/latest/strategy.json`.
- Do not move `results/ncf_*` panel CSVs.
- Do not move `data/private/group_a_plus_dashboard.html`; it is a private local dashboard output.
- Do not remove legacy compatibility writes yet.
- Do not change active/latest strategy resolution before adding reader fallback tests.

## Quick Resume

If continuing this work, start with:

```bash
rg "ops_health_path|daily_status_path|strategy_env_health|signal_alignment|watchlist_news" group_a_plus scripts tests -n
```

Then migrate one reader at a time to:

1. read canonical output first,
2. unwrap `payload` if the canonical envelope is present,
3. fallback to legacy path,
4. add focused tests,
5. run the related test file plus `tests/test_run_ncf_daily_pipeline.py`.
