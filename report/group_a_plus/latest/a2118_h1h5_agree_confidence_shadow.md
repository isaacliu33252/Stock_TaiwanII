# A21.18 NCF Late-Bull-Hedge h20-Specific Confidence Shadow

- Generated: `2026-08-19T01:55:23`
- Policy: `research_only_no_groupa_plus_live_change`
- Production params: `{'h20_max': 0.33, 'conf_min': 0.55, 'h5_reentry_min': 0.55}`

## Summary

| Bucket | Windows | Pass | Total Final Delta | Baseline Trigger Days | Variant Trigger Days |
|---|---:|---:|---:|---:|---:|
| all | 8 | 4/8 | -186007.46 | 0 | 28 |
| tuning_style | 5 | 3/5 | -144048.93 | 0 | 16 |
| holdout | 3 | 1/3 | -41958.53 | 0 | 12 |

## Window Details

| Window | Bucket | Final Delta | Sharpe Delta | MDD Delta | Baseline Days | Variant Days | Pass |
|---|---|---:|---:|---:|---:|---:|---|
| holdout_2025_only | holdout | -21519.50 | -0.0400 | 0.0000 | 0 | 4 | False |
| backfill_2020_covid | tuning_style | 0.00 | 0.0000 | 0.0000 | 0 | 0 | True |
| backfill_2021_may_correction | tuning_style | 0.00 | 0.0000 | 0.0000 | 0 | 0 | True |
| backfill_2022_rate_hike | tuning_style | 0.00 | 0.0000 | 0.0000 | 0 | 0 | True |
| backfill_2024_aug_unwind | tuning_style | -16693.62 | 0.1260 | 0.0238 | 0 | 4 | False |
| active_2025_2026 | tuning_style | -127355.31 | 0.1353 | 0.0153 | 0 | 12 | False |
| holdout_2023 | holdout | 0.00 | 0.0000 | 0.0000 | 0 | 0 | True |
| holdout_2026 | holdout | -20439.03 | 0.1837 | 0.0226 | 0 | 8 | False |

## Decision

- Promotion ready: `False`
- Recommended use: `research_only`
- No latest strategy, golden1_0531, live signal, execution plan, or order file was changed.
