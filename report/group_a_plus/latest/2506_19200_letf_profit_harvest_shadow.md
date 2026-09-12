# 2506.19200 LETF Profit-Harvest Shadow

- Generated: `2026-08-21T15:37:09`
- Policy: `research_only_no_groupa_plus_live_change`
- Params: `{'gain_window': 60, 'momentum_window': 20, 'momentum_peak_lookback': 20, 'gain_threshold': 0.2, 'leverage_contribution_threshold': 0.03, 'momentum_decay_threshold': 0.03, 'trim_fraction': 0.25, 'feature_warmup_days': 150}`

## Summary

| Bucket | Windows | Pass | Total Final Delta | Total Cost Delta | Total Turnover Delta | Harvest Days | Effective Harvest Days |
|---|---:|---:|---:|---:|---:|---:|---:|
| all | 9 | 3/9 | 0.00 | 0.00 | 0.00 | 47 | 0 |
| tuning_style | 6 | 2/6 | 0.00 | 0.00 | 0.00 | 37 | 0 |
| holdout | 3 | 1/3 | 0.00 | 0.00 | 0.00 | 10 | 0 |

## Window Details

| Window | Bucket | Final Delta | Sharpe Delta | MDD Delta | Cost Delta | Turnover Delta | Harvest Days | Effective Trim Weight | Pass |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| live_2024_2026 | tuning_style | 0.00 | 0.0000 | 0.0000 | 0.00 | 0.00 | 6 | 0.0000 | False |
| active_2025_2026 | tuning_style | 0.00 | 0.0000 | 0.0000 | 0.00 | 0.00 | 6 | 0.0000 | False |
| backfill_2020_covid | tuning_style | 0.00 | 0.0000 | 0.0000 | 0.00 | 0.00 | 16 | 0.0000 | False |
| backfill_2021_may_correction | tuning_style | 0.00 | 0.0000 | 0.0000 | 0.00 | 0.00 | 9 | 0.0000 | False |
| backfill_2022_rate_hike | tuning_style | 0.00 | 0.0000 | 0.0000 | 0.00 | 0.00 | 0 | 0.0000 | True |
| backfill_2024_aug_unwind | tuning_style | 0.00 | 0.0000 | 0.0000 | 0.00 | 0.00 | 0 | 0.0000 | True |
| holdout_2022_full | holdout | 0.00 | 0.0000 | 0.0000 | 0.00 | 0.00 | 0 | 0.0000 | True |
| holdout_2023 | holdout | 0.00 | 0.0000 | 0.0000 | 0.00 | 0.00 | 5 | 0.0000 | False |
| holdout_2026 | holdout | 0.00 | 0.0000 | 0.0000 | 0.00 | 0.00 | 5 | 0.0000 | False |

## Decision

- Promotion ready: `False`
- Reason: Profit-harvest trigger fired, but current golden1 has no effective 00631L trim exposure.
- Recommended use: `research_only`
- No latest strategy, golden1_0531, live signal, execution plan, or order file was changed.
