# GroupA+ PPO 500k Multi-Window OOS Review

- Generated: `2026-08-15T10:53:11`
- Status: `blocked_for_latest_replacement`
- Decision: `keep_500k_zero_inverse_shadow_only`
- Policy: `research_only_no_latest_replacement`

## Summary

- Zero-inverse wins vs 100k by return: `4`
- Zero-inverse losses vs 100k by return: `2`
- Zero-inverse wins vs original 500k by return: `3`
- Zero-inverse losses vs original 500k by return: `3`

## OOS Windows

| Window | 100k ret | 500k ret | 500k zero ret | Zero vs 100k | Zero vs 500k | Zero vol |
|---|---:|---:|---:|---:|---:|---:|
| full_oos_2025_2026 | 106.22% | 127.65% | 126.08% | 19.86% | -1.56% | 26.42% |
| 2025_h1 | 0.00% | 2.15% | 2.63% | 2.62% | 0.48% | 27.37% |
| 2025_h2 | 32.72% | 36.65% | 37.08% | 4.35% | 0.43% | 17.30% |
| 2026_h1 | 51.30% | 60.08% | 59.23% | 7.92% | -0.85% | 28.87% |
| 2026q3_partial | -0.87% | -2.04% | -3.05% | -2.18% | -1.01% | 40.36% |
| issue_20260804_20260814 | 5.04% | 4.70% | 4.90% | -0.14% | 0.20% | 20.02% |

## Not Counted As OOS

- 2020_covid: `2020-02-01` to `2020-04-30`, reason `inside_2020_2024_training_window_for_these_checkpoints`
- 2022_rate_hike: `2022-01-01` to `2022-12-31`, reason `inside_2020_2024_training_window_for_these_checkpoints`
- 2024_2026: `2024-01-01` to `2026-08-14`, reason `starts_inside_training_window; use 2025_2026 for strict OOS`

## Decision

- Replace latest: `False`
- Tune latest: `False`
- Promote 500k zero-inverse to production: `False`
- Blocking reasons: `['500k_zero_inverse_loses_to_100k_in_at_least_one_oos_window', '500k_zero_inverse_loses_to_original_500k_in_at_least_one_oos_window', '500k_zero_inverse_underperforms_100k_in_2026q3_partial', '500k_zero_inverse_underperforms_100k_in_issue_20260804_20260814']`
- Warning reasons: `['500k_zero_inverse_full_oos_volatility_above_100k']`

No latest strategy, live signal, execution plan, or order file was changed.
