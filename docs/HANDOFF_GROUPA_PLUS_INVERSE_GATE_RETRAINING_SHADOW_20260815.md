# HANDOFF - GroupA+ 00632R Gate And Guarded Retraining Shadow

Date: 2026-08-15  
Scope: agreed sequence before any latest strategy replacement or tuning  

## Agreed Sequence

```text
1. Build 00632R / inverse ETF prevention gate.
2. Run retraining-candidate shadow backtest under that gate.
3. Only then consider replacing or tuning latest.
```

## Step 1 - 00632R / Inverse ETF Gate

Implemented a research-only manual-review gate:

- code: `group_a_plus/operations/execution_guard.py`
- function: `apply_inverse_etf_manual_review_gate`
- default ticker: `00632R.TW`
- report builder:
  `scripts/evaluate/build_group_a_plus_inverse_etf_manual_review_gate.py`
- tests:
  - `tests/test_inverse_etf_manual_review_gate.py`
  - `tests/test_build_group_a_plus_inverse_etf_manual_review_gate.py`

Policy:

```text
No automatic 00632R / inverse ETF action.
Opening, increasing, reducing, or closing 00632R is blocked until manual review
has artifact freshness, cost basis, realized P&L review, hedge rationale, and
manual approval.
```

Generated reports:

- latest plan:
  `report/group_a_plus/latest/inverse_etf_manual_review_gate.md`
- 2026-08-04 incident replay:
  `report/group_a_plus/latest/inverse_etf_manual_review_gate_20260804_incident_replay.md`

Important result:

- latest plan had current `00632R.TW = 0`, target `00632R.TW = 0`;
  gate status was `inactive`;
  report status was blocked only because the source execution plan itself was
  already `manual_review_required` / `manual_confirmation_required`.
- 2026-08-04 replay had current `00632R.TW = 0`,
  target `00632R.TW = 10189`;
  gate status was `blocked`.

This confirms the 2026-08-04 style 00632R action would now be stopped before
automatic execution.

## Step 2 - Guarded Retraining Candidate Shadow Backtest

Added a governance wrapper:

- code:
  `scripts/evaluate/build_group_a_plus_guarded_retraining_candidate_shadow.py`
- tests:
  `tests/test_build_group_a_plus_guarded_retraining_candidate_shadow.py`

Purpose:

```text
Read a GroupA+ overlay shadow backtest report, then apply the 00632R governance
filter before any candidate can be considered for retraining, promotion,
replacement, or latest tuning.
```

Shadow backtest command run:

```text
.venv/bin/python backtest_group_a_plus_overlay.py --plus-variants cap_guard_optimized,focused_tdcc_0135_stab0_turn18_stop_disabled_fast_tight_inv03 --output results/group_a_plus_guarded_retraining_candidate_shadow_backtest_20260815.json
```

Backtest outputs:

- JSON:
  `results/group_a_plus_guarded_retraining_candidate_shadow_backtest_20260815.json`
- CSV:
  `results/group_a_plus_guarded_retraining_candidate_shadow_backtest_20260815.csv`
- curve CSV:
  `results/group_a_plus_guarded_retraining_candidate_shadow_backtest_20260815_curve.csv`

Backtest headline result:

```text
Base approx:
final=2,207,967.17
sharpe=2.7675
mdd=-16.8630%
vol=21.9810%

GroupA+_cap_guard_optimized:
final=2,221,641.56
sharpe=2.8225
mdd=-16.4585%
vol=21.6913%

GroupA+_focused_tdcc_0135_stab0_turn18_stop_disabled_fast_tight_inv03:
final=2,258,816.38
sharpe=2.9116
mdd=-15.6668%
vol=21.4290%
```

The raw backtest promotion gate said:

```text
promotion_candidate
```

But the guarded report found both candidates touched `00632R.TW`.

Guarded report command:

```text
.venv/bin/python scripts/evaluate/build_group_a_plus_guarded_retraining_candidate_shadow.py --as-of 2026-08-15 --backtest results/group_a_plus_guarded_retraining_candidate_shadow_backtest_20260815.json
```

Guarded report outputs:

- JSON:
  `report/group_a_plus/latest/guarded_retraining_candidate_shadow.json`
- Markdown:
  `report/group_a_plus/latest/guarded_retraining_candidate_shadow.md`

Guarded decision:

```text
blocked_by_inverse_etf_governance
```

Detected inverse exposure:

```text
GroupA+_cap_guard_optimized:
first_touch_date=2025-04-01
last_touch_date=2025-08-20
touch_count=9
max_target_weight=0.4075
max_executable_weight=0.4075

GroupA+_focused_tdcc_0135_stab0_turn18_stop_disabled_fast_tight_inv03:
first_touch_date=2025-04-01
last_touch_date=2025-08-20
touch_count=9
max_target_weight=0.4075
max_executable_weight=0.4075
```

Key lesson:

```text
Do not only block variants with names such as *_invXX.
The base replay events can already contain 00632R exposure, so governance must
inspect actual target/executable weights.
```

## Verification

Commands run:

```text
.venv/bin/python -m py_compile group_a_plus/operations/execution_guard.py scripts/evaluate/build_group_a_plus_inverse_etf_manual_review_gate.py
.venv/bin/python -m pytest tests/test_inverse_etf_manual_review_gate.py tests/test_build_group_a_plus_inverse_etf_manual_review_gate.py -q
.venv/bin/python -m py_compile scripts/evaluate/build_group_a_plus_guarded_retraining_candidate_shadow.py
.venv/bin/python -m pytest tests/test_build_group_a_plus_guarded_retraining_candidate_shadow.py -q
```

Results:

```text
inverse gate tests: 6 passed
guarded retraining shadow tests: 2 passed
```

## Production Safety

No production latest artifacts were intentionally changed:

```text
report/group_a_plus/latest/strategy.json
report/group_a_plus/latest/live_signal.json
report/group_a_plus/latest/execution_plan.json
```

This work is research-only / shadow governance.

## Current Decision

Do not replace latest.  
Do not tune latest.  
Do not treat the raw promotion-candidate result as actionable.

Reason:

```text
The candidate set touched 00632R.TW and is blocked by the new inverse ETF
governance gate until manual cost-basis / realized-P&L / hedge-rationale review
is complete.
```

## Next Step

Run a new retraining-candidate shadow backtest using candidates that have zero
00632R target/executable exposure, or explicitly provide the required manual
review package before allowing any inverse ETF candidate to proceed.

## Continuation - Zero-Inverse Candidate Shadow

Added a research-only overlay variant:

- code: `backtest_group_a_plus_overlay.py`
- variant: `cap_guard_no_inverse`
- behavior:
  - starts from `cap_guard_optimized`;
  - removes any base-event `00632R.TW` target weight before execution;
  - releases removed inverse ETF weight to cash;
  - does not alter latest strategy, live signal, execution plan, or orders.

Added tests:

- `tests/test_backtest_group_a_plus_overlay_no_inverse.py`

Verification commands:

```text
.venv/bin/python -m py_compile backtest_group_a_plus_overlay.py
.venv/bin/python -m pytest tests/test_backtest_group_a_plus_overlay_no_inverse.py tests/test_build_group_a_plus_guarded_retraining_candidate_shadow.py -q
```

Result:

```text
4 passed
```

Zero-inverse shadow backtest command:

```text
.venv/bin/python backtest_group_a_plus_overlay.py --plus-variants cap_guard_no_inverse --output results/group_a_plus_zero_inverse_retraining_candidate_shadow_backtest_20260815.json
```

Generated files:

- `results/group_a_plus_zero_inverse_retraining_candidate_shadow_backtest_20260815.json`
- `results/group_a_plus_zero_inverse_retraining_candidate_shadow_backtest_20260815.csv`
- `results/group_a_plus_zero_inverse_retraining_candidate_shadow_backtest_20260815_curve.csv`

Backtest result:

```text
Base approx:
final=2,207,967.17
sharpe=2.7675
mdd=-16.8630%
vol=21.9810%
rebalances=69
total_cost=22,174.54

GroupA+_cap_guard_no_inverse:
final=2,282,682.88
sharpe=2.8428
mdd=-18.2073%
vol=22.2873%
rebalances=73
total_cost=19,998.38

Delta vs base:
final_value=+74,715.71
sharpe=+0.0754
max_drawdown=-1.3443 percentage points
volatility=+0.3063 percentage points
```

Guarded report command:

```text
.venv/bin/python scripts/evaluate/build_group_a_plus_guarded_retraining_candidate_shadow.py --as-of 2026-08-15 --backtest results/group_a_plus_zero_inverse_retraining_candidate_shadow_backtest_20260815.json --output-json report/group_a_plus/latest/zero_inverse_guarded_retraining_candidate_shadow.json --output-md report/group_a_plus/latest/zero_inverse_guarded_retraining_candidate_shadow.md --no-history
```

Guarded result:

```text
decision=guarded_promotion_candidate
guarded_promotion_candidates=['GroupA+_cap_guard_no_inverse']
inverse_blocked_candidates=[]
00632R max_target_weight=0.0
00632R max_executable_weight=0.0
replace_latest=False
tune_latest=False
```

## Replacement / Tuning Decision

Do not replace latest yet.  
Do not tune latest yet.

Reason:

```text
cap_guard_no_inverse clears the new 00632R governance blocker and improves
final value / Sharpe in this replay, but it worsens maximum drawdown and
volatility. It is only a single-window shadow result, not enough evidence for
latest replacement.
```

Required before replacement can be reconsidered:

- multi-window replay, including 2020 COVID, 2022 rate-hike, 2024-2026,
  2025-2026, and the current 2026-08 issue window;
- explicit confirmation that every candidate has zero `00632R.TW` target and
  executable exposure unless a signed manual inverse ETF review package exists;
- comparison against `golden1_0531` / current latest on final value, Sharpe,
  max drawdown, volatility, turnover, realized-cost sensitivity, and 8/4-style
  closed-trade P&L attribution.

## Continuation - 1M Training Step Count Guarded Review

Built a guarded review for the already completed PPO step-count ablation:

- script:
  `scripts/evaluate/build_group_a_plus_1m_step_count_guarded_shadow_review.py`
- tests:
  `tests/test_build_group_a_plus_1m_step_count_guarded_shadow_review.py`
- output JSON:
  `report/group_a_plus/latest/ppo_1m_step_count_guarded_shadow_review.json`
- output Markdown:
  `report/group_a_plus/latest/ppo_1m_step_count_guarded_shadow_review.md`

Inputs:

- 100k:
  `results/group_a_backtest_20250101_20260814_20260814_231928.json`
- 500k:
  `results/group_a_backtest_20250101_20260814_20260814_224346.json`
- 1M:
  `results/group_a_backtest_20250101_20260814_20260815_002023.json`

Overall metrics:

```text
100k final=2,062,235.02 | Sharpe=2.028 | MDD=-23.83% | Vol=23.39% | Trades=66 | Fees=20,978.85
500k final=2,276,460.16 | Sharpe=2.169 | MDD=-23.83% | Vol=24.98% | Trades=66 | Fees=20,884.86
1M   final=2,372,666.88 | Sharpe=2.257 | MDD=-23.83% | Vol=25.22% | Trades=66 | Fees=25,206.98
```

1M vs 100k:

```text
final_value=+310,431.85
sharpe=+0.2290
MDD=0.00 percentage points
volatility=+1.83 percentage points
fees=+4,228.13
```

Focus windows:

```text
2026Q3:
100k=-0.87%
500k=-2.04%
1M=-1.68%

2026-08-04 to 2026-08-14:
100k=+5.04%
500k=+4.70%
1M=+4.96%
```

00632R governance evidence from saved logs:

```text
100k: PVA logged 00632R touch count=2, max target=0.2826, forced exits=2
500k: PVA logged 00632R touch count=2, max target=0.2826, forced exits=2
1M:   PVA logged 00632R touch count=2, max target=0.2826, forced exits=2
```

Important limitation:

```text
The saved backtest JSONs do not include a complete daily target-weight log.
The review therefore only uses saved PVA and inverse forced-exit evidence for
00632R governance. This is enough to block promotion, but not enough to claim
full exposure attribution.
```

Guarded decision:

```text
decision=keep_1m_shadow_only
one_m_training_steps_helpful=True
replace_latest=False
tune_latest=False
promote_1m_to_production=False
blocking_reasons=[
  1m_saved_logs_include_00632r_exposure,
  1m_underperforms_100k_in_2026q3_downturn_proxy
]
warning_reasons=[
  1m_volatility_above_100k,
  complete_daily_00632r_exposure_log_missing
]
```

Interpretation:

```text
1M training steps are useful as a research signal because full-window final
value and Sharpe improved monotonically. They are not sufficient for latest
replacement because the run still contains 00632R exposure evidence, raises
volatility, and underperforms 100k in 2026Q3 / slightly underperforms 100k in
the 2026-08-04 to 2026-08-14 issue window.
```

Overfit diagnostic added to the same report:

```text
overfit_risk.label=high_overfit_risk
overfit_risk.risk_score=6
production_implication=do_not_replace_latest
```

Signals:

```text
full_window_final_and_sharpe_improved=True
q3_2026_weaker_than_100k=True
issue_window_weaker_than_100k=True
volatility_higher_than_100k=True
fees_higher_than_100k=True
saved_logs_include_00632r_exposure=True
complete_daily_exposure_log_missing=True
```

This is not a formal statistical proof that 1M is overfit. It is a governance
classification: the improvement is likely window-specific enough that 1M must
stay shadow-only until multi-window, zero-00632R, and complete daily exposure
evidence exist.

## Continuation - 500k Guarded Shadow Review

User question:

```text
500k 還能做什麼驗証?
```

Implemented a 500k-specific guarded shadow review:

- script:
  `scripts/evaluate/build_group_a_plus_500k_guarded_shadow_review.py`
- tests:
  `tests/test_build_group_a_plus_500k_guarded_shadow_review.py`
- output JSON:
  `report/group_a_plus/latest/ppo_500k_guarded_shadow_review.json`
- output Markdown:
  `report/group_a_plus/latest/ppo_500k_guarded_shadow_review.md`
- history JSON:
  `report/group_a_plus/ppo_500k_guarded_shadow_review/history/ppo_500k_guarded_shadow_review_20260815.json`

Command run:

```text
.venv/bin/python scripts/evaluate/build_group_a_plus_500k_guarded_shadow_review.py --as-of 2026-08-15
```

Verification:

```text
.venv/bin/python -m py_compile scripts/evaluate/build_group_a_plus_500k_guarded_shadow_review.py
.venv/bin/python -m pytest tests/test_build_group_a_plus_500k_guarded_shadow_review.py -q
```

Result:

```text
2 passed
```

500k vs 100k:

```text
final_value=+214,225.14
sharpe=+0.1413
MDD=0.00 percentage points
volatility=+1.59 percentage points
fees=-93.99
```

1M vs 500k:

```text
final_value=+96,206.71
sharpe=+0.0877
MDD=0.00 percentage points
volatility=+0.24 percentage points
fees=+4,322.12
```

Focus windows:

```text
2026Q3:
100k=-0.87%
500k=-2.04%
1M=-1.68%

2026-08-04 to 2026-08-14:
100k=+5.04%
500k=+4.70%
1M=+4.96%
```

00632R governance evidence from saved logs:

```text
500k status=blocked
PVA logged 00632R touch count=2
PVA max target=0.2826
forced exits=2
complete_daily_exposure_log_available=False
```

Guarded decision:

```text
status=blocked_for_latest_replacement
decision=keep_500k_shadow_only
five_hundred_k_training_steps_helpful=True
replace_latest=False
tune_latest=False
promote_500k_to_production=False
```

Blocking reasons:

```text
500k_saved_logs_include_00632r_exposure
500k_underperforms_100k_in_2026q3_downturn_proxy
500k_underperforms_100k_in_20260804_issue_window
```

Warnings:

```text
complete_daily_00632r_exposure_log_missing
500k_volatility_above_100k
candidate_risk:high_overfit_or_window_specific_risk
```

Interpretation:

```text
500k is useful as a research candidate because full-window final value and
Sharpe improved versus 100k and fees were slightly lower. It is still not
eligible for latest replacement or tuning because it underperforms 100k in the
2026Q3 proxy window and the 2026-08-04 issue window, has higher volatility,
and saved logs still include 00632R exposure evidence.
```

Required next evidence before reconsidering 500k:

```text
1. zero_00632r_replay_for_500k
2. complete_daily_target_weight_log
3. multi_window_oos_replay
4. seed_sensitivity_check
5. 2026q3_and_20260804_window_resilience_improvement
```

Production safety:

```text
No latest strategy, live signal, execution plan, or order file was changed.
```

## Continuation - 500k Zero-00632R Replay

User approved continuing 500k validation. First priority was:

```text
zero_00632R replay for 500k
```

Added a backtest-only CLI path so an existing PPO checkpoint can be replayed
without continuing training:

- code:
  `train_dual_group_2024_2026.py`
- new argument:
  `--group-a-backtest-only-model`

Purpose:

```text
Load an existing Group A PPO model checkpoint, construct the same Group A
environment, and run `_backtest_group` without calling `model.learn`.
```

Replay command:

```text
.venv/bin/python train_dual_group_2024_2026.py --xlsx taiwan_stock_20260516_group.xlsx --group-filter group_a --group-a-backtest-only-model last_ppo_group_a_500k --group-a-profile default --group-a-action-schema triplet_v4 --group-a-enable-dca --group-a-enable-pva-sigmoid --group-a-00631l-max-weight 0.30 --group-a-00632r-max-weight 0.0 --group-a-pva-inverse-hedge-budget 0.0 --initial-cash 1000000 --train-start 2020-01-01 --train-end 2024-12-31 --backtest-start 2025-01-01 --backtest-end 2026-08-14 --timesteps 500000 --seed 42
```

Replay output:

```text
results/group_a_backtest_20250101_20260814_20260815_100944.json
```

Added formal zero-inverse review:

- script:
  `scripts/evaluate/build_group_a_plus_500k_zero_inverse_replay_review.py`
- tests:
  `tests/test_build_group_a_plus_500k_zero_inverse_replay_review.py`
- output JSON:
  `report/group_a_plus/latest/ppo_500k_zero_inverse_replay_review.json`
- output Markdown:
  `report/group_a_plus/latest/ppo_500k_zero_inverse_replay_review.md`
- history JSON:
  `report/group_a_plus/ppo_500k_zero_inverse_replay_review/history/ppo_500k_zero_inverse_replay_review_20260815.json`

Verification:

```text
.venv/bin/python -m py_compile scripts/evaluate/build_group_a_plus_500k_zero_inverse_replay_review.py train_dual_group_2024_2026.py
.venv/bin/python -m pytest tests/test_build_group_a_plus_500k_zero_inverse_replay_review.py -q
```

Result:

```text
2 passed
```

Zero-inverse replay metrics:

```text
100k:
final=2,062,235.02 | Sharpe=2.028 | MDD=-23.83% | Vol=23.39% | Fees=20,978.85

500k original:
final=2,276,460.16 | Sharpe=2.169 | MDD=-23.83% | Vol=24.98% | Fees=20,884.86

500k zero-inverse:
final=2,260,836.62 | Sharpe=2.048 | MDD=-23.95% | Vol=26.42% | Fees=21,152.92
```

Zero-inverse vs 100k:

```text
final_value=+198,601.60
sharpe=+0.0199
MDD=-0.12 percentage points
volatility=+3.03 percentage points
fees=+174.07
```

Zero-inverse vs original 500k:

```text
final_value=-15,623.54
sharpe=-0.1214
MDD=-0.12 percentage points
volatility=+1.44 percentage points
fees=+268.06
```

Focus windows:

```text
2026Q3:
100k=-0.87%
500k original=-2.04%
500k zero-inverse=-3.05%

2026-08-04 to 2026-08-14:
100k=+5.04%
500k original=+4.70%
500k zero-inverse=+4.90%
```

00632R governance evidence:

```text
500k zero-inverse:
status=not_blocked_by_saved_logs
PVA logged 00632R touch count=0
PVA max target=0.0000
forced exits=0
```

Guarded decision:

```text
status=blocked_for_latest_replacement
decision=keep_500k_zero_inverse_shadow_only
zero_inverse_governance_cleared=True
still_better_than_100k=True
retains_original_500k_edge=False
replace_latest=False
tune_latest=False
promote_500k_zero_inverse_to_production=False
```

Blocking reasons:

```text
zero_inverse_replay_does_not_retain_original_500k_edge
zero_inverse_replay_underperforms_100k_in_2026q3
zero_inverse_replay_underperforms_100k_in_20260804_issue_window
```

Warnings:

```text
zero_inverse_replay_volatility_above_100k
complete_daily_target_weight_log_missing
```

Interpretation:

```text
The zero-00632R replay clears the inverse ETF governance blocker, but it does
not preserve the original 500k edge. Final value remains above 100k, but Sharpe
is only marginally above 100k, volatility is materially higher, MDD is slightly
worse, and 2026Q3 / 2026-08-04 issue-window behavior remains weaker than 100k.

Therefore 500k remains a research-only candidate. Do not replace latest and do
not tune latest from this replay.
```

Production safety:

```text
Confirmed no diff in:
report/group_a_plus/latest/strategy.json
report/group_a_plus/latest/live_signal.json
report/group_a_plus/latest/execution_plan.json
```

## Continuation - Complete Daily Target-Weight Log

Next validation completed:

```text
complete_daily_target_weight_log
```

Implementation:

- code:
  `train_dual_group_2024_2026.py`
- new replay output field:
  `group_a.result.daily_target_weight_history`

The log is appended once per decision/execution day in `PortfolioEnv.step`.
It records:

```text
decision_date
execution_date
action / action_label
decision_value_before
execution_value_before
close_value_after
daily_return
decision_weights
execution_pre_trade_weights
base_target_weights
candidate_target_weights
final_target_weights
close_weights
cash weights
turnover
needs_rebalance
executed_trade
rebalance_fees
dca_fees
dividend_fees
execution_source
SJM / PVA details
risk_gate
inverse_rule
```

Reran 500k zero-inverse replay after adding the daily log:

```text
.venv/bin/python train_dual_group_2024_2026.py --xlsx taiwan_stock_20260516_group.xlsx --group-filter group_a --group-a-backtest-only-model last_ppo_group_a_500k --group-a-profile default --group-a-action-schema triplet_v4 --group-a-enable-dca --group-a-enable-pva-sigmoid --group-a-00631l-max-weight 0.30 --group-a-00632r-max-weight 0.0 --group-a-pva-inverse-hedge-budget 0.0 --initial-cash 1000000 --train-start 2020-01-01 --train-end 2024-12-31 --backtest-start 2025-01-01 --backtest-end 2026-08-14 --timesteps 500000 --seed 42
```

New replay output with complete daily log:

```text
results/group_a_backtest_20250101_20260814_20260815_104759.json
```

Daily log validation:

```text
daily_target_weight_history rows=391
backtest_rows=392

Max 00632R by field:
decision_weights=0.0000
execution_pre_trade_weights=0.0000
base_target_weights=0.0000
candidate_target_weights=0.0000
final_target_weights=0.0000
close_weights=0.0000
```

Updated zero-inverse review to use the complete daily exposure log:

- script:
  `scripts/evaluate/build_group_a_plus_500k_zero_inverse_replay_review.py`
- test:
  `tests/test_build_group_a_plus_500k_zero_inverse_replay_review.py`

Verification:

```text
.venv/bin/python -m py_compile train_dual_group_2024_2026.py scripts/evaluate/build_group_a_plus_500k_zero_inverse_replay_review.py
.venv/bin/python -m pytest tests/test_build_group_a_plus_500k_zero_inverse_replay_review.py tests/test_build_group_a_plus_500k_guarded_shadow_review.py -q
```

Result:

```text
5 passed
```

Updated report:

```text
report/group_a_plus/latest/ppo_500k_zero_inverse_replay_review.md
```

Important updated governance result:

```text
500k_zero_inverse:
status=not_blocked_by_saved_logs
PVA touch count=0
PVA max target=0.0000
forced exits=0
daily log=True
daily rows=391
daily max 00632R=0.0000
```

The previous warning:

```text
complete_daily_target_weight_log_missing
```

is now removed for the 500k zero-inverse replay.

Remaining warnings / blockers:

```text
blocking_reasons=[
  zero_inverse_replay_does_not_retain_original_500k_edge,
  zero_inverse_replay_underperforms_100k_in_2026q3,
  zero_inverse_replay_underperforms_100k_in_20260804_issue_window
]

warning_reasons=[
  zero_inverse_replay_volatility_above_100k
]
```

Interpretation:

```text
The complete daily exposure log confirms that the 500k zero-inverse replay had
no 00632R exposure in decision, execution, target, or close weights. Governance
for inverse ETF exposure is cleared for this replay.

However, the zero-inverse replay still does not retain the original 500k edge,
underperforms 100k in 2026Q3 / 2026-08-04 issue-window checks, and has higher
volatility. Therefore it remains shadow-only.
```

## Continuation - 500k Multi-Window OOS Review

Next validation completed:

```text
multi_window_oos_replay
```

Implemented a report that slices the existing OOS equity curves for:

```text
100k
500k original
500k zero-inverse
```

Script:

```text
scripts/evaluate/build_group_a_plus_500k_multi_window_oos_review.py
```

Test:

```text
tests/test_build_group_a_plus_500k_multi_window_oos_review.py
```

Output:

```text
report/group_a_plus/latest/ppo_500k_multi_window_oos_review.json
report/group_a_plus/latest/ppo_500k_multi_window_oos_review.md
report/group_a_plus/ppo_500k_multi_window_oos_review/history/ppo_500k_multi_window_oos_review_20260815.json
```

Command:

```text
.venv/bin/python scripts/evaluate/build_group_a_plus_500k_multi_window_oos_review.py --as-of 2026-08-15
```

Verification:

```text
.venv/bin/python -m py_compile scripts/evaluate/build_group_a_plus_500k_multi_window_oos_review.py
.venv/bin/python -m pytest tests/test_build_group_a_plus_500k_multi_window_oos_review.py -q
```

Result:

```text
2 passed
```

OOS window summary:

```text
500k zero-inverse wins vs 100k by return: 4
500k zero-inverse losses vs 100k by return: 2
500k zero-inverse wins vs original 500k by return: 3
500k zero-inverse losses vs original 500k by return: 3
```

Window table:

```text
full_oos_2025_2026:
100k=+106.22%
500k original=+127.65%
500k zero-inverse=+126.08%
zero vs 100k=+19.86%
zero vs original 500k=-1.56%
zero vol=26.42%

2025_h1:
100k=+0.00%
500k original=+2.15%
500k zero-inverse=+2.63%
zero vs 100k=+2.62%
zero vs original 500k=+0.48%
zero vol=27.37%

2025_h2:
100k=+32.72%
500k original=+36.65%
500k zero-inverse=+37.08%
zero vs 100k=+4.35%
zero vs original 500k=+0.43%
zero vol=17.30%

2026_h1:
100k=+51.30%
500k original=+60.08%
500k zero-inverse=+59.23%
zero vs 100k=+7.92%
zero vs original 500k=-0.85%
zero vol=28.87%

2026q3_partial:
100k=-0.87%
500k original=-2.04%
500k zero-inverse=-3.05%
zero vs 100k=-2.18%
zero vs original 500k=-1.01%
zero vol=40.36%

issue_20260804_20260814:
100k=+5.04%
500k original=+4.70%
500k zero-inverse=+4.90%
zero vs 100k=-0.14%
zero vs original 500k=+0.20%
zero vol=20.02%
```

Windows explicitly not counted as strict OOS:

```text
2020_covid:
2020-02-01 to 2020-04-30
reason=inside_2020_2024_training_window_for_these_checkpoints

2022_rate_hike:
2022-01-01 to 2022-12-31
reason=inside_2020_2024_training_window_for_these_checkpoints

2024_2026:
2024-01-01 to 2026-08-14
reason=starts_inside_training_window; use 2025_2026 for strict OOS
```

Decision:

```text
status=blocked_for_latest_replacement
decision=keep_500k_zero_inverse_shadow_only
replace_latest=False
tune_latest=False
promote_500k_zero_inverse_to_production=False
```

Blocking reasons:

```text
500k_zero_inverse_loses_to_100k_in_at_least_one_oos_window
500k_zero_inverse_loses_to_original_500k_in_at_least_one_oos_window
500k_zero_inverse_underperforms_100k_in_2026q3_partial
500k_zero_inverse_underperforms_100k_in_issue_20260804_20260814
```

Warning:

```text
500k_zero_inverse_full_oos_volatility_above_100k
```

Interpretation:

```text
500k zero-inverse is still useful as a research signal in ordinary OOS windows:
it beats 100k in full 2025-2026, 2025H1, 2025H2, and 2026H1.

It fails the windows that matter most for current governance: 2026Q3 partial
and the 2026-08-04 issue window. This means the candidate still behaves worse
than 100k when the recent failure mode is active. Keep it shadow-only.
```

## Continuation - 500k Seed Sensitivity Readiness

Next validation started:

```text
seed_sensitivity_check
```

Current inventory check:

```text
models/portfolio/last_ppo_group_a_500k.zip exists
No independent 500k zero-inverse seed checkpoints were found for seed 7, 13, or 21.
No matching seed-specific 500k zero-inverse result JSONs were found.
```

Important governance point:

```text
Seed sensitivity is not complete. Do not infer seed robustness from seed 42.
```

Added readiness/blocker report:

- script:
  `scripts/evaluate/build_group_a_plus_500k_seed_sensitivity_readiness.py`
- test:
  `tests/test_build_group_a_plus_500k_seed_sensitivity_readiness.py`
- output JSON:
  `report/group_a_plus/latest/ppo_500k_seed_sensitivity_readiness.json`
- output Markdown:
  `report/group_a_plus/latest/ppo_500k_seed_sensitivity_readiness.md`
- history JSON:
  `report/group_a_plus/ppo_500k_seed_sensitivity_readiness/history/ppo_500k_seed_sensitivity_readiness_20260815.json`

Command:

```text
.venv/bin/python scripts/evaluate/build_group_a_plus_500k_seed_sensitivity_readiness.py --as-of 2026-08-15
```

Verification:

```text
.venv/bin/python -m py_compile scripts/evaluate/build_group_a_plus_500k_seed_sensitivity_readiness.py
.venv/bin/python -m pytest tests/test_build_group_a_plus_500k_seed_sensitivity_readiness.py -q
```

Result:

```text
1 passed
```

Seed 42 reference, zero-inverse vs 100k:

```text
final_value=+198,601.60
sharpe=+0.0199
MDD=-0.12 percentage points
volatility=+3.03 percentage points
fees=+174.07
```

Required independent seeds:

```text
seed 7:  missing model, missing result
seed 13: missing model, missing result
seed 21: missing model, missing result
```

Status:

```text
status=blocked_for_seed_sensitivity
decision=seed_sensitivity_not_complete
replace_latest=False
tune_latest=False
promote_500k_to_production=False
```

Blocking reasons:

```text
missing_required_independent_500k_zero_inverse_seed_runs
seed42_zero_inverse_volatility_above_100k
```

Commands prepared for required runs:

```text
.venv/bin/python train_dual_group_2024_2026.py --xlsx taiwan_stock_20260516_group.xlsx --group-filter group_a --group-a-model-name group_a_500k_zero_inverse_s07 --group-a-profile default --group-a-action-schema triplet_v4 --group-a-enable-dca --group-a-enable-pva-sigmoid --group-a-00631l-max-weight 0.30 --group-a-00632r-max-weight 0.0 --group-a-pva-inverse-hedge-budget 0.0 --initial-cash 1000000 --train-start 2020-01-01 --train-end 2024-12-31 --backtest-start 2025-01-01 --backtest-end 2026-08-14 --timesteps 500000 --seed 7

.venv/bin/python train_dual_group_2024_2026.py --xlsx taiwan_stock_20260516_group.xlsx --group-filter group_a --group-a-model-name group_a_500k_zero_inverse_s13 --group-a-profile default --group-a-action-schema triplet_v4 --group-a-enable-dca --group-a-enable-pva-sigmoid --group-a-00631l-max-weight 0.30 --group-a-00632r-max-weight 0.0 --group-a-pva-inverse-hedge-budget 0.0 --initial-cash 1000000 --train-start 2020-01-01 --train-end 2024-12-31 --backtest-start 2025-01-01 --backtest-end 2026-08-14 --timesteps 500000 --seed 13

.venv/bin/python train_dual_group_2024_2026.py --xlsx taiwan_stock_20260516_group.xlsx --group-filter group_a --group-a-model-name group_a_500k_zero_inverse_s21 --group-a-profile default --group-a-action-schema triplet_v4 --group-a-enable-dca --group-a-enable-pva-sigmoid --group-a-00631l-max-weight 0.30 --group-a-00632r-max-weight 0.0 --group-a-pva-inverse-hedge-budget 0.0 --initial-cash 1000000 --train-start 2020-01-01 --train-end 2024-12-31 --backtest-start 2025-01-01 --backtest-end 2026-08-14 --timesteps 500000 --seed 21
```

Interpretation:

```text
500k zero-inverse cannot be promoted, tuned into latest, or treated as robust
until independent 500k zero-inverse seeds are trained and their OOS / 2026Q3 /
2026-08-04 issue-window results are aggregated.
```

Production safety:

```text
Confirmed no diff in:
report/group_a_plus/latest/strategy.json
report/group_a_plus/latest/live_signal.json
report/group_a_plus/latest/execution_plan.json
```

## Continuation - 500k Seed Sensitivity Executed

The required independent seed runs were executed:

```text
seed 7
seed 13
seed 21
```

Together with existing seed 42 zero-inverse replay, the aggregation now covers
four zero-inverse 500k runs:

```text
seed 42:
results/group_a_backtest_20250101_20260814_20260815_104759.json

seed 7:
model=models/portfolio/group_a_500k_zero_inverse_s07.zip
result=results/group_a_backtest_20250101_20260814_20260815_112823.json

seed 13:
model=models/portfolio/group_a_500k_zero_inverse_s13.zip
result=results/group_a_backtest_20250101_20260814_20260815_115227.json

seed 21:
model=models/portfolio/group_a_500k_zero_inverse_s21.zip
result=results/group_a_backtest_20250101_20260814_20260815_121626.json
```

All three new runs used:

```text
--timesteps 500000
--group-a-00632r-max-weight 0.0
--group-a-pva-inverse-hedge-budget 0.0
--group-a-enable-pva-sigmoid
--group-a-enable-dca
```

00632R governance check:

```text
seed 7:  daily max 00632R=0.0000, PVA max inverse=0.0000, forced exits=0
seed 13: daily max 00632R=0.0000, PVA max inverse=0.0000, forced exits=0
seed 21: daily max 00632R=0.0000, PVA max inverse=0.0000, forced exits=0
```

Added aggregation report:

- script:
  `scripts/evaluate/build_group_a_plus_500k_seed_sensitivity_aggregation.py`
- test:
  `tests/test_build_group_a_plus_500k_seed_sensitivity_aggregation.py`
- output JSON:
  `report/group_a_plus/latest/ppo_500k_seed_sensitivity_aggregation.json`
- output Markdown:
  `report/group_a_plus/latest/ppo_500k_seed_sensitivity_aggregation.md`
- history JSON:
  `report/group_a_plus/ppo_500k_seed_sensitivity_aggregation/history/ppo_500k_seed_sensitivity_aggregation_20260815.json`

Command:

```text
.venv/bin/python scripts/evaluate/build_group_a_plus_500k_seed_sensitivity_aggregation.py --as-of 2026-08-15
```

Verification:

```text
.venv/bin/python -m py_compile scripts/evaluate/build_group_a_plus_500k_seed_sensitivity_aggregation.py
.venv/bin/python -m pytest tests/test_build_group_a_plus_500k_seed_sensitivity_aggregation.py -q
```

Result:

```text
1 passed
```

Baseline 100k:

```text
final=2,062,235.02
Sharpe=2.028
MDD=-23.83%
volatility=23.39%
```

Seed aggregation:

```text
seed_count=4
full_oos_wins_vs_100k=4
2026Q3_wins_vs_100k=0
issue_window_wins_vs_100k=2
inverse_governance_blocks=0

final_value_range=2,234,183.63 to 2,410,202.14
Sharpe_range=1.964 to 2.079
MDD_range=-28.81% to -23.95%
volatility_range=26.42% to 29.82%
```

Per seed:

```text
seed 7:
final=2,405,859.29
Sharpe=1.981
MDD=-28.81%
vol=29.82%
full_vs_100k=+34.36%
Q3_vs_100k=-1.26%
issue_vs_100k=+0.13%

seed 13:
final=2,234,183.63
Sharpe=1.964
MDD=-26.32%
vol=27.27%
full_vs_100k=+17.19%
Q3_vs_100k=-1.56%
issue_vs_100k=-0.14%

seed 21:
final=2,410,202.14
Sharpe=2.079
MDD=-24.45%
vol=28.25%
full_vs_100k=+34.80%
Q3_vs_100k=-2.84%
issue_vs_100k=+0.53%

seed 42:
final=2,260,836.62
Sharpe=2.048
MDD=-23.95%
vol=26.42%
full_vs_100k=+19.86%
Q3_vs_100k=-2.18%
issue_vs_100k=-0.14%
```

Final seed sensitivity decision:

```text
status=blocked_for_latest_replacement
decision=keep_500k_zero_inverse_shadow_only
replace_latest=False
tune_latest=False
promote_500k_to_production=False
```

Blocking reasons:

```text
not_all_seeds_beat_100k_in_2026q3_partial
not_all_seeds_beat_100k_in_20260804_issue_window
at_least_one_seed_sharpe_below_100k
at_least_one_seed_mdd_worse_than_100k
```

Warning:

```text
seed_volatility_above_100k
```

Interpretation:

```text
The 500k zero-inverse candidate is robust in one narrow sense: all four seeds
beat 100k on full OOS final return and all four have zero 00632R exposure.

It fails the governance-sensitive robustness checks: no seed beats 100k in
2026Q3, only two of four seeds beat 100k in the 2026-08-04 issue window, at
least one seed has Sharpe below 100k, every seed has volatility above 100k, and
several seeds have materially worse MDD.

Do not replace latest. Do not tune latest from 500k. Keep 500k zero-inverse
research-only.
```
