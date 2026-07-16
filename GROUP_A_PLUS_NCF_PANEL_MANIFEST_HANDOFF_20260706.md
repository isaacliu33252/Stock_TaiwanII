# GroupA+ NCF Panel Manifest Handoff - 2026-07-06

## Status

Added a reproducibility manifest for NCF panel CSVs and connected it to the daily NCF pipeline.
Added a follow-up coverage audit for panel end-date coverage versus source OHLCV.
Added opt-in full-panel live-tail extension to 00632R and 2330 panels, matching the existing 00631L behavior.

This is a governance/diagnostic improvement only. It does not change model training, predictions, live allocation, strategy pointers, or promotion decisions.

## Why This Was Added

The previous blocker was large NCF panel drift. The drift audit showed that panel values changed materially, but the panel CSVs did not carry a compact fingerprint to explain whether the change came from:

- date range changes,
- schema/column changes,
- content changes,
- missing-value changes,
- or key probability/confidence distribution shifts.

The new manifest records those facts for each generated panel.

## Files Added

- `scripts/evaluate/build_ncf_panel_manifest.py`
- `tests/test_build_ncf_panel_manifest.py`
- `scripts/evaluate/evaluate_ncf_panel_coverage.py`
- `tests/test_evaluate_ncf_panel_coverage.py`

## Files Updated

- `scripts/run/run_ncf_daily_pipeline.py`
  - Adds `ncf_panel_manifest` after `ncf_2330` and before `advisory_panel`.
  - Adds `ncf_panel_coverage` after `ncf_panel_manifest` and before `advisory_panel`.
  - Passes `--full-panel` to `ncf_00632r.py` and `ncf_2330.py`.
  - Adds `panel_2330` and `ncf_panel_manifest` to daily manifest outputs.
  - Adds `ncf_panel_coverage` to daily manifest outputs.
- `ncf_00632r.py`
  - Adds `--full-panel`.
  - Stores per-horizon classifiers for unlabeled tail inference.
  - Extends panel rows after the last labeled validation row when requested.
- `ncf_2330.py`
  - Adds `--full-panel`.
  - Stores per-horizon classifiers for unlabeled tail inference.
  - Extends panel rows after the last labeled validation row when requested.
- `tests/test_run_ncf_daily_pipeline.py`
  - Updates command-order expectations.
  - Verifies the panel manifest command references the three NCF panel CSVs.
  - Verifies the coverage audit uses `external_market_ohlcv:yfinance:2330.TW` for 2330.

## Manifest Contents

For each panel, the manifest includes:

- file path and size,
- row count,
- column count,
- date start/end,
- full column list,
- schema hash,
- normalized content hash,
- missing count by column,
- key column statistics for probability/confidence fields.

The report also includes a combined hash across all panel fingerprints.

## Real Run

20260706 panel CSVs were not present because the daily pipeline was dry-run only. The latest complete panel set available locally was 20260703.

Command:

```bash
.venv/bin/python scripts/evaluate/build_ncf_panel_manifest.py \
  --panels \
  results/ncf_00631l_panel_latest_20260703.csv \
  results/ncf_00632r_panel_latest_20260703.csv \
  results/ncf_2330_panel_latest_20260703.csv \
  --output results/ncf_panel_manifest_20260703.json
```

Output:

- `results/ncf_panel_manifest_20260703.json`

Combined hash:

- `16ab7f655a47ff925ea0e6f586bd2043975672302182f4961dc084be00a78c6a`

Panel summary:

| Panel | Rows | Date start | Date end | Columns |
| --- | ---: | --- | --- | ---: |
| `ncf_00631l_panel_latest_20260703.csv` | 361 | 2025-01-02 | 2026-07-02 | 22 |
| `ncf_00632r_panel_latest_20260703.csv` | 341 | 2025-01-02 | 2026-06-03 | 21 |
| `ncf_2330_panel_latest_20260703.csv` | 340 | 2025-01-02 | 2026-06-03 | 21 |

Immediate finding:

- The 00631L panel extends to 2026-07-02.
- The 00632R and 2330 panels only extend to 2026-06-03.

This date-range mismatch is now visible in a lightweight manifest and should be investigated before relying on cross-panel advisory or trigger comparisons.

## Coverage Audit

Command:

```bash
.venv/bin/python scripts/evaluate/evaluate_ncf_panel_coverage.py \
  --panel-ticker \
  results/ncf_00631l_panel_latest_20260703.csv=00631L.TW \
  results/ncf_00632r_panel_latest_20260703.csv=00632R.TW \
  results/ncf_2330_panel_latest_20260703.csv=external_market_ohlcv:yfinance:2330.TW \
  --output results/ncf_panel_coverage_20260703.json
```

Output:

- `results/ncf_panel_coverage_20260703.json`

Result:

- Overall: `fail`

| Panel | Panel end | Source latest | Business-day gap | Live tail rows | Status |
| --- | --- | --- | ---: | ---: | --- |
| `00631L.TW` | 2026-07-02 | 2026-07-03 | 1 | 20 | warn |
| `00632R.TW` | 2026-06-03 | 2026-07-03 | 22 | 0 | fail |
| `2330.TW` | 2026-06-03 | 2026-07-02 | 21 | 0 | fail |

Interpretation:

- `00631L` has an unlabeled live tail (`is_live`) and reaches near-current coverage.
- `00632R` and `2330` do not have live-tail extension and lag their source OHLCV by more than the configured 20-business-day label horizon.

## Full-Panel Fix

Implemented `--full-panel` for:

- `ncf_00632r.py`
- `ncf_2330.py`

The daily pipeline now passes this flag for all three NCF panel generators:

- `scripts/misc/ncf_00631l.py`
- `ncf_00632r.py`
- `ncf_2330.py`

Smoke verification used short training windows and `/tmp` outputs.

00632R command:

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

00632R result:

- Full panel extension: 20 unlabeled tail rows.
- Coverage: `pass`
- Panel end: 2026-07-03
- Source latest: 2026-07-03
- Business-day gap: 0

2330 command:

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

2330 result:

- Full panel extension: 20 unlabeled tail rows.
- Coverage: `pass`
- Panel end: 2026-07-02
- Source latest: 2026-07-02
- Business-day gap: 0

## Verification

```bash
.venv/bin/python -m py_compile \
  scripts/evaluate/build_ncf_panel_manifest.py \
  scripts/evaluate/evaluate_ncf_panel_coverage.py \
  scripts/run/run_ncf_daily_pipeline.py \
  ncf_00632r.py \
  ncf_2330.py

.venv/bin/python -m pytest -q \
  tests/test_build_ncf_panel_manifest.py \
  tests/test_evaluate_ncf_panel_coverage.py \
  tests/test_run_ncf_daily_pipeline.py
```

Result:

- `14 passed` for coverage/pipeline focused tests after adding coverage audit.

## Recommended Next Step

Run the full daily NCF pipeline once, not dry-run, so the production-date outputs `results/ncf_00632r_panel_latest_20260706.csv` and `results/ncf_2330_panel_latest_20260706.csv` are regenerated with live-tail rows. Then re-run:

```bash
.venv/bin/python scripts/evaluate/evaluate_ncf_panel_coverage.py \
  --panel-ticker \
  results/ncf_00631l_panel_latest_20260706.csv=00631L.TW \
  results/ncf_00632r_panel_latest_20260706.csv=00632R.TW \
  results/ncf_2330_panel_latest_20260706.csv=external_market_ohlcv:yfinance:2330.TW \
  --output results/ncf_panel_coverage_20260706.json
```

If all three pass, rebuild the panel manifest and use those fresh artifacts for the next drift/promotion research cycle.
