# Group A+ 00631L NCF PIT Historical Panel Handoff - 2026-07-13

## Objective

Build a point-in-time historical NCF panel for 00631L that can be used by
backtests and live-style diagnostics without accidentally consuming realized
future labels.

## Outputs

Builder:

- `scripts/evaluate/build_ncf_pit_historical_panel.py`

Generated artifacts:

- `results/ncf_00631l_pit_historical_panel_20260713.csv`
- `results/ncf_00631l_pit_historical_panel_20260713.json`
- `results/ncf_00631l_pit_historical_panel_manifest_20260713.json`

Panel coverage:

- rows: 1097
- date_start: 2017-01-03
- date_end: 2026-07-09

Sources:

| Source | Path | Rows | Date range |
|---|---|---:|---|
| `oos_2017_2019` | `results/ncf_00631l_panel_backfill_2017_2019_20260710.csv` | 731 | 2017-01-03 to 2019-12-31 |
| `panel_2025_2026` | `results/ncf_00631l_panel_latest_20260710.csv` | 366 | 2025-01-02 to 2026-07-09 |

## PIT Definition

Each row contains only model outputs and metadata available as of that row's
`signal_date` after market close.

Added metadata columns:

- `asof_date`
- `signal_date`
- `available_after_close`
- `next_trading_date_in_source`
- `source_panel`
- `source_panel_path`
- `source_panel_sha256`

Execution timing:

- Same-day close execution remains research-only unless a delay model is
  explicitly applied.
- `next_trading_date_in_source` is provided for t+1 execution studies inside
  each source panel.
- Do not treat the 2019 to 2025 gap as continuous trading history.

## Leakage Policy

Dropped realized future columns:

- `actual_fwd_mdd_gt5_h20`
- `forward_mdd_h20`
- `actual_fwd_gain_gt5_h20`
- `forward_gain_h20`

The builder also rejects retained columns with these prefixes:

- `actual_`
- `forward_`
- `target_`
- `label_`

Retained prediction columns with forward-looking names:

- `prob_fwd_mdd_gt5_h20`
- `prob_fwd_gain_gt5_h20`
- `tail_reward_risk_score_h20`

These are kept because they are model probability outputs available at the
as-of date, not realized future labels.

## Intended Use

Use this PIT panel for:

- A21.18 / Group A+ signal diagnostics
- shadow backtests that need NCF signals without label leakage
- crash-risk warning audits
- point-in-time H20 warning research

Do not use this PIT panel for:

- calibration that needs realized outcomes
- event studies requiring realized forward return / MDD labels
- model training labels

For those tasks, use the original research panels and keep the evaluation code
explicitly separated.

## Verification

Commands run:

```bash
python3 scripts/evaluate/build_ncf_pit_historical_panel.py
python3 scripts/evaluate/build_ncf_panel_manifest.py --panels results/ncf_00631l_pit_historical_panel_20260713.csv --output results/ncf_00631l_pit_historical_panel_manifest_20260713.json
python3 -m py_compile scripts/evaluate/build_ncf_pit_historical_panel.py
pytest -q tests/test_build_ncf_pit_historical_panel.py tests/test_build_ncf_panel_manifest.py
```

Result:

```text
5 passed
```

Manual schema check:

```text
rows 1097
cols 25
date 2017-01-03 to 2026-07-09
leakage_cols []
source_counts:
  oos_2017_2019      731
  panel_2025_2026    366
```

## Decision

Use `results/ncf_00631l_pit_historical_panel_20260713.csv` as the clean
historical NCF signal surface for future no-lookahead diagnostics. Keep the
original source panels for calibration and label-based research only.
