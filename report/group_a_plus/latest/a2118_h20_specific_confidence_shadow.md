# A21.18 NCF Late-Bull-Hedge h20-Specific Confidence Shadow

- Generated: `2026-08-19T01:47:30`
- Policy: `research_only_no_groupa_plus_live_change`
- Production params: `{'h20_max': 0.33, 'conf_min': 0.55, 'h5_reentry_min': 0.55}`

## Summary

| Bucket | Windows | Pass | Total Final Delta | Baseline Trigger Days | Variant Trigger Days |
|---|---:|---:|---:|---:|---:|
| all | 7 | 4/7 | -78402.67 | 0 | 3 |
| tuning_style | 5 | 3/5 | -67390.31 | 0 | 2 |
| holdout | 2 | 1/2 | -11012.36 | 0 | 1 |

## Window Details

| Window | Bucket | Final Delta | Sharpe Delta | MDD Delta | Baseline Days | Variant Days | Pass |
|---|---|---:|---:|---:|---:|---:|---|
| backfill_2020_covid | tuning_style | 0.00 | 0.0000 | 0.0000 | 0 | 0 | True |
| backfill_2021_may_correction | tuning_style | 0.00 | 0.0000 | 0.0000 | 0 | 0 | True |
| backfill_2022_rate_hike | tuning_style | 0.00 | 0.0000 | 0.0000 | 0 | 0 | True |
| backfill_2024_aug_unwind | tuning_style | -8033.94 | 0.0707 | 0.0143 | 0 | 1 | False |
| active_2025_2026 | tuning_style | -59356.37 | 0.1104 | 0.0153 | 0 | 1 | False |
| holdout_2023 | holdout | 0.00 | 0.0000 | 0.0000 | 0 | 0 | True |
| holdout_2026 | holdout | -11012.36 | 0.0433 | 0.0051 | 0 | 1 | False |

## Decision

- Promotion ready: `False`
- Recommended use: `research_only`
- No latest strategy, golden1_0531, live signal, execution plan, or order file was changed.
