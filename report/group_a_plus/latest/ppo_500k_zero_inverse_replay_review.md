# GroupA+ PPO 500k Zero-Inverse Replay Review

- Generated: `2026-08-15T10:48:47`
- Status: `blocked_for_latest_replacement`
- Decision: `keep_500k_zero_inverse_shadow_only`
- Policy: `research_only_no_latest_replacement`

## Overall Metrics

| Run | Final value | Sharpe | MDD | Vol | Trades | Fees |
|---|---:|---:|---:|---:|---:|---:|
| 100k | 2,062,235.02 | 2.028 | -23.83% | 23.39% | 66 | 20,978.85 |
| 500k | 2,276,460.16 | 2.169 | -23.83% | 24.98% | 66 | 20,884.86 |
| 500k_zero_inverse | 2,260,836.62 | 2.048 | -23.95% | 26.42% | 66 | 21,152.92 |

## Zero-Inverse Delta

- Vs 100k final value: `198,601.60`
- Vs 100k Sharpe: `0.0199`
- Vs 100k MDD: `-0.12%`
- Vs 100k volatility: `3.03%`
- Vs 100k fees: `174.07`
- Vs original 500k final value: `-15,623.54`
- Vs original 500k Sharpe: `-0.1214`
- Vs original 500k MDD: `-0.12%`
- Vs original 500k volatility: `1.44%`
- Vs original 500k fees: `268.06`

## Focus Windows

- 2026Q3 100k: `-0.87%`
- 2026Q3 500k: `-2.04%`
- 2026Q3 500k zero-inverse: `-3.05%`
- 2026-08-04 to 2026-08-14 100k: `5.04%`
- 2026-08-04 to 2026-08-14 500k: `4.70%`
- 2026-08-04 to 2026-08-14 500k zero-inverse: `4.90%`

## 00632R Governance

- 100k: status `blocked`, PVA touch count `2`, PVA max target `0.2826`, forced exits `2`, daily log `False`
- 500k: status `blocked`, PVA touch count `2`, PVA max target `0.2826`, forced exits `2`, daily log `False`
- 500k_zero_inverse: status `not_blocked_by_saved_logs`, PVA touch count `0`, PVA max target `0.0000`, forced exits `0`, daily log `True`
  - daily rows `391`, daily max 00632R `0.0000`

## Decision

- Zero-inverse governance cleared: `True`
- Still better than 100k: `True`
- Retains original 500k edge: `False`
- Replace latest: `False`
- Tune latest: `False`
- Promote 500k zero-inverse to production: `False`
- Blocking reasons: `['zero_inverse_replay_does_not_retain_original_500k_edge', 'zero_inverse_replay_underperforms_100k_in_2026q3', 'zero_inverse_replay_underperforms_100k_in_20260804_issue_window']`
- Warning reasons: `['zero_inverse_replay_volatility_above_100k']`

No latest strategy, live signal, execution plan, or order file was changed.
