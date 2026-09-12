# GroupA+ PPO 500k Seed Sensitivity Aggregation

- Generated: `2026-08-15T12:18:33`
- Status: `blocked_for_latest_replacement`
- Decision: `keep_500k_zero_inverse_shadow_only`
- Policy: `research_only_no_latest_replacement`

## Baseline

- 100k final: `2,062,235.02`
- 100k Sharpe: `2.028`
- 100k MDD: `-23.83%`
- 100k volatility: `23.39%`

## Seed Summary

- Seed count: `4`
- Full OOS wins vs 100k: `4`
- 2026Q3 wins vs 100k: `0`
- Issue-window wins vs 100k: `2`
- Inverse governance blocks: `0`
- Final value range: `2,234,183.63` to `2,410,202.14`
- Sharpe range: `1.964` to `2.079`
- MDD range: `-28.81%` to `-23.95%`
- Volatility range: `26.42%` to `29.82%`

## Seed Runs

| Seed | Final | Sharpe | MDD | Vol | Full vs 100k | Q3 vs 100k | Issue vs 100k | 00632R max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 7 | 2,405,859.29 | 1.981 | -28.81% | 29.82% | 34.36% | -1.26% | 0.13% | 0.0000 |
| 13 | 2,234,183.63 | 1.964 | -26.32% | 27.27% | 17.19% | -1.56% | -0.14% | 0.0000 |
| 21 | 2,410,202.14 | 2.079 | -24.45% | 28.25% | 34.80% | -2.84% | 0.53% | 0.0000 |
| 42 | 2,260,836.62 | 2.048 | -23.95% | 26.42% | 19.86% | -2.18% | -0.14% | 0.0000 |

## Decision

- Replace latest: `False`
- Tune latest: `False`
- Promote 500k to production: `False`
- Blocking reasons: `['not_all_seeds_beat_100k_in_2026q3_partial', 'not_all_seeds_beat_100k_in_20260804_issue_window', 'at_least_one_seed_sharpe_below_100k', 'at_least_one_seed_mdd_worse_than_100k']`
- Warning reasons: `['seed_volatility_above_100k']`

No latest strategy, live signal, execution plan, or order file was changed.
