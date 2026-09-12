# GroupA+ PPO 500k Guarded Shadow Review

- Generated: `2026-08-15T10:03:34`
- Status: `blocked_for_latest_replacement`
- Decision: `keep_500k_shadow_only`
- Policy: `research_only_no_latest_replacement`

## Overall Metrics

| Steps | Final value | Sharpe | MDD | Vol | Trades | Fees |
|---|---:|---:|---:|---:|---:|---:|
| 100k | 2,062,235.02 | 2.028 | -23.83% | 23.39% | 66 | 20,978.85 |
| 500k | 2,276,460.16 | 2.169 | -23.83% | 24.98% | 66 | 20,884.86 |
| 1m | 2,372,666.88 | 2.257 | -23.83% | 25.22% | 66 | 25,206.98 |

## 500k Delta Vs 100k

- Final value: `214,225.14`
- Sharpe: `0.1413`
- MDD: `0.00%`
- Volatility: `1.59%`
- Fees: `-93.99`

## 1M Delta Vs 500k

- Final value: `96,206.71`
- Sharpe: `0.0877`
- MDD: `0.00%`
- Volatility: `0.24%`
- Fees: `4,322.12`

## Focus Windows

- 2026Q3 100k: `-0.87%`
- 2026Q3 500k: `-2.04%`
- 2026Q3 1M: `-1.68%`
- 2026-08-04 to 2026-08-14 100k: `5.04%`
- 2026-08-04 to 2026-08-14 500k: `4.70%`
- 2026-08-04 to 2026-08-14 1M: `4.96%`

## 00632R Governance

- 100k: status `blocked`, PVA touch count `2`, PVA max target `0.2826`, forced exits `2`
- 500k: status `blocked`, PVA touch count `2`, PVA max target `0.2826`, forced exits `2`
- 1m: status `blocked`, PVA touch count `2`, PVA max target `0.2826`, forced exits `2`

## Candidate Risk

- Label: `high_overfit_or_window_specific_risk`
- Risk score: `5`
- Signals: `{'full_window_final_and_sharpe_improved': True, 'q3_2026_weaker_than_100k': True, 'issue_window_weaker_than_100k': True, 'volatility_higher_than_100k': True, 'fees_higher_than_100k': False, 'saved_logs_include_00632r_exposure': True, 'complete_daily_exposure_log_missing': True}`
- Interpretation: `500k improves the full-window aggregate, but weaker 2026Q3 / incident-window behavior and saved 00632R exposure make it a shadow-only candidate until zero-inverse and complete daily exposure evidence exists.`

## Decision

- 500k helpful on full-window final value / Sharpe: `True`
- Replace latest: `False`
- Tune latest: `False`
- Promote 500k to production: `False`
- Blocking reasons: `['500k_saved_logs_include_00632r_exposure', '500k_underperforms_100k_in_2026q3_downturn_proxy', '500k_underperforms_100k_in_20260804_issue_window']`
- Warning reasons: `['complete_daily_00632r_exposure_log_missing', '500k_volatility_above_100k', 'candidate_risk:high_overfit_or_window_specific_risk']`

No latest strategy, live signal, execution plan, or order file was changed.
