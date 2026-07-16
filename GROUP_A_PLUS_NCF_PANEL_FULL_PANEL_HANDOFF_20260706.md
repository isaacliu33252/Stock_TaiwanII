# GroupA+ NCF Panel Full-Panel Handoff - 2026-07-06

## Status

This sub-workstream is implemented and smoke-verified.

The original issue was that the NCF panel manifest exposed a date coverage mismatch:

- `00631L` panel had live-tail rows and reached near-current coverage.
- `00632R` and `2330` panels stopped around 2026-06-03.
- Source OHLCV was available through early July, so these panels were stale for live advisory/promotion use.

The fix adds opt-in full-panel live-tail support to `00632R` and `2330`, then enables it in the daily pipeline.

No live allocation, strategy pointer, model weight, or promotion decision was changed.

## Root Cause

`scripts/misc/ncf_00631l.py` already supported:

```bash
--full-panel
```

That mode extends the validation panel with unlabeled tail rows after the last row that has forward labels. The live-tail rows are marked with:

```text
is_live = True
```

Before this work:

- `ncf_00632r.py` did not support `--full-panel`.
- `ncf_2330.py` did not support `--full-panel`.
- Daily pipeline passed `--full-panel` only to 00631L.

Therefore, 00632R and 2330 panel CSVs were effectively labeled-only panels and naturally stopped roughly one H=20 label horizon before the latest OHLCV date.

## Files Changed

### NCF Model Scripts

- `ncf_00632r.py`
  - Added `--full-panel`.
  - Added `all_clf_models` storage for per-horizon classifiers.
  - Stores bull/bear classifiers, selected features, and dropped horizon features.
  - Extends panel rows after the last labeled validation row when `--full-panel` is set.
  - Marks original labeled rows as `is_live=False`.
  - Marks generated unlabeled tail rows as `is_live=True`.

- `ncf_2330.py`
  - Same live-tail support as `ncf_00632r.py`.
  - Uses the already-loaded `raw` and `ext_df` data, so no change to 2330's `external_market_ohlcv` source logic was needed.

### Daily Pipeline

- `scripts/run/run_ncf_daily_pipeline.py`
  - Adds `--full-panel` to `ncf_00632r`.
  - Adds `--full-panel` to `ncf_2330`.
  - Keeps existing `--full-panel` for `scripts/misc/ncf_00631l.py`.
  - Daily pipeline now generates all three NCF panels in live-tail mode.

### Tests

- `tests/test_run_ncf_daily_pipeline.py`
  - Asserts `--full-panel` is present for `ncf_00631l`, `ncf_00632r`, and `ncf_2330`.
  - Existing command-order tests now include:
    - `ncf_panel_manifest`
    - `ncf_panel_coverage`
    - `promotion_gate`

### Existing Support Added Earlier In This Thread

- `scripts/evaluate/build_ncf_panel_manifest.py`
  - Builds panel fingerprints: row/date/schema/content/missing/key column stats.

- `scripts/evaluate/evaluate_ncf_panel_coverage.py`
  - Audits panel end date against source OHLCV.
  - Supports ordinary `ohlcv` tickers.
  - Supports 2330 via:

```text
external_market_ohlcv:yfinance:2330.TW
```

- `tests/test_build_ncf_panel_manifest.py`
- `tests/test_evaluate_ncf_panel_coverage.py`

## Real Findings Before Fix

Manifest output:

- `results/ncf_panel_manifest_20260703.json`

Panel date coverage from manifest:

| Panel | Rows | Date start | Date end | Columns |
| --- | ---: | --- | --- | ---: |
| `ncf_00631l_panel_latest_20260703.csv` | 361 | 2025-01-02 | 2026-07-02 | 22 |
| `ncf_00632r_panel_latest_20260703.csv` | 341 | 2025-01-02 | 2026-06-03 | 21 |
| `ncf_2330_panel_latest_20260703.csv` | 340 | 2025-01-02 | 2026-06-03 | 21 |

Coverage audit output:

- `results/ncf_panel_coverage_20260703.json`

Coverage result:

| Panel | Panel end | Source latest | Business-day gap | Live tail rows | Status |
| --- | --- | --- | ---: | ---: | --- |
| `00631L.TW` | 2026-07-02 | 2026-07-03 | 1 | 20 | warn |
| `00632R.TW` | 2026-06-03 | 2026-07-03 | 22 | 0 | fail |
| `2330.TW` | 2026-06-03 | 2026-07-02 | 21 | 0 | fail |

Interpretation:

- 00631L was already live-tail capable.
- 00632R and 2330 were stale for live-panel usage because they had no unlabeled tail rows.

## Smoke Verification After Fix

These were short-window smoke runs to verify the new live-tail code path without running the full daily pipeline.

### 00632R Smoke

Command:

```bash
.venv/bin/python ncf_00632r.py \
  --train-start 2024-01-01 \
  --val-start 2026-04-01 \
  --val-end latest \
  --no-external-features \
  --output /tmp/ncf_00632r_smoke.json \
  --val-predictions-output /tmp/ncf_00632r_smoke_panel.csv \
  --full-panel
```

Observed in output:

```text
[FULL PANEL] Extended by 20 unlabeled tail rows -> total 64
```

Coverage command:

```bash
.venv/bin/python scripts/evaluate/evaluate_ncf_panel_coverage.py \
  --panel-ticker /tmp/ncf_00632r_smoke_panel.csv=00632R.TW \
  --output /tmp/ncf_00632r_smoke_coverage.json
```

Coverage result:

```text
Overall: pass
00632R.TW: pass panel_end=2026-07-03 latest=2026-07-03 gap_bdays=0 live_tail=20
```

### 2330 Smoke

Command:

```bash
.venv/bin/python ncf_2330.py \
  --train-start 2024-01-01 \
  --val-start 2026-04-01 \
  --val-end latest \
  --no-external-features \
  --output /tmp/ncf_2330_smoke.json \
  --val-predictions-output /tmp/ncf_2330_smoke_panel.csv \
  --full-panel
```

Observed in output:

```text
[FULL PANEL] Extended by 20 unlabeled tail rows -> total 63
```

Coverage command:

```bash
.venv/bin/python scripts/evaluate/evaluate_ncf_panel_coverage.py \
  --panel-ticker /tmp/ncf_2330_smoke_panel.csv=external_market_ohlcv:yfinance:2330.TW \
  --output /tmp/ncf_2330_smoke_coverage.json
```

Coverage result:

```text
Overall: pass
2330.TW: pass panel_end=2026-07-02 latest=2026-07-02 gap_bdays=0 live_tail=20
```

## Pipeline Dry Run

Command:

```bash
.venv/bin/python scripts/run/run_ncf_daily_pipeline.py \
  --date-stamp 20260706 \
  --skip-refresh \
  --skip-commentary \
  --dry-run
```

Observed command order:

1. `ohlcv_freshness`
2. `ncf_00631l`
3. `ncf_00632r`
4. `ncf_2330`
5. `ncf_panel_manifest`
6. `ncf_panel_coverage`
7. `advisory_panel`
8. `factor_lens`
9. `daily_signal`
10. `daily_status`
11. `promotion_gate`
12. `ncf_2330_checklist`

Confirmed dry-run commands include:

```text
ncf_00631l ... --full-panel
ncf_00632r ... --full-panel
ncf_2330 ... --full-panel
```

## Verification

Syntax checks:

```bash
.venv/bin/python -m py_compile \
  ncf_00632r.py \
  ncf_2330.py \
  scripts/run/run_ncf_daily_pipeline.py
```

Focused tests:

```bash
.venv/bin/python -m pytest -q \
  tests/test_run_ncf_daily_pipeline.py \
  tests/test_evaluate_ncf_panel_coverage.py
```

Result:

```text
14 passed
```

Broader related tests:

```bash
.venv/bin/python -m pytest -q \
  tests/test_build_ncf_panel_manifest.py \
  tests/test_evaluate_ncf_panel_coverage.py \
  tests/test_run_ncf_daily_pipeline.py \
  tests/test_evaluate_ncf_panel_drift.py \
  tests/test_group_a_plus_governance_compare_extended.py \
  tests/test_evaluate_group_a_plus_promotion_gate.py \
  tests/test_evaluate_group_a_plus_multi_window_gate.py
```

Result:

```text
27 passed
```

## What Was Not Done

The full daily NCF pipeline was not run end to end after this fix.

Reason:

- Full NCF model generation is heavier and can take materially longer.
- Smoke runs verified the new full-panel code path for both affected scripts.
- The daily pipeline dry-run verified the actual command wiring.

Therefore, official `results/*_20260706.csv` panel outputs still need to be regenerated by a non-dry-run daily pipeline before using them for fresh promotion/drift research.

## Recommended Next Commands

Run the full pipeline without dry-run when ready:

```bash
.venv/bin/python scripts/run/run_ncf_daily_pipeline.py \
  --date-stamp 20260706 \
  --skip-refresh \
  --skip-commentary
```

Then verify panel coverage:

```bash
.venv/bin/python scripts/evaluate/evaluate_ncf_panel_coverage.py \
  --panel-ticker \
  results/ncf_00631l_panel_latest_20260706.csv=00631L.TW \
  results/ncf_00632r_panel_latest_20260706.csv=00632R.TW \
  results/ncf_2330_panel_latest_20260706.csv=external_market_ohlcv:yfinance:2330.TW \
  --output results/ncf_panel_coverage_20260706.json
```

Expected result after full-panel regeneration:

- 00631L: `pass` or near-current `warn` depending on source date.
- 00632R: should no longer be a 20+ business-day `fail`.
- 2330: should no longer be a 20+ business-day `fail`.

Then rebuild panel manifest:

```bash
.venv/bin/python scripts/evaluate/build_ncf_panel_manifest.py \
  --panels \
  results/ncf_00631l_panel_latest_20260706.csv \
  results/ncf_00632r_panel_latest_20260706.csv \
  results/ncf_2330_panel_latest_20260706.csv \
  --output results/ncf_panel_manifest_20260706.json
```

Only after that should the next drift/promotion research cycle use the regenerated 20260706 artifacts.

## Risk Notes

- Tail rows are unlabeled by design. They should be used for live advisory/context, not for historical validation metrics.
- The `is_live` column distinguishes labeled validation rows from generated tail rows.
- Promotion research should continue to rely on the promotion gate, panel drift gate, and multi-window gate.
- This fix improves panel coverage but does not by itself clear any promotion blocker.

## Current Decision

Current production decision remains unchanged:

- Do not promote reviewed candidates.
- Do not change live allocation.
- Do not change strategy pointer or model weights.

This work only improves NCF panel observability and daily panel freshness readiness.
