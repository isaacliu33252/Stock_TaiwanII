# A21.20 LETF Compounding Regime Shadow Handoff - 2026-07-15

## Reference

Paper:

```text
C:\Users\isaac\Downloads\2504.20116v1.pdf
Compounding Effects in Leveraged ETFs: Beyond the Volatility Drag Paradigm
```

Main takeaway for GroupA+:

```text
00631L risk should not be judged by volatility drag alone.
Positive return persistence can make daily-reset leverage compound favorably.
Mean-reverting / choppy paths can make incremental leverage additions costly.
```

## Existing Diagnostic

Module:

```text
group_a_plus/integrations/leveraged_compounding_regime.py
```

Daily evaluator:

```text
scripts/evaluate/evaluate_00631l_leveraged_compounding_regime.py
```

Latest 2026-07-15 report:

```text
results/00631l_leveraged_compounding_regime_20260715.json
results/00631l_leveraged_compounding_regime_20260715.csv
```

Latest state:

```text
date = 2026-07-15
compounding_regime = TRANSITIONAL
recommended_policy = maintain_a2118_no_active_overlay
rolling_AR1_5d = -0.897699
rolling_AR1_20d = 0.033935
variance_ratio = 1.006138
trend_persistence = 0.526316
reversal_speed = 0.388889
00631L_vs_0050_relative_momentum = -0.011014
compounding_effect_20d = -0.014791
compounding_effect_60d = -0.089325
compounding_effect_120d = -0.015186
volatility_persistence_ratio = 0.966570
trend_score = 1
mean_reversion_score = 2
```

Operational meaning:

```text
No compounding-regime block is active for 2026-07-15.
```

## New Shadow Evaluator

Added:

```text
scripts/evaluate/evaluate_00631l_compounding_regime_no_add_shadow.py
tests/test_evaluate_00631l_compounding_regime_no_add_shadow.py
```

Policy tested:

```text
If compounding_regime == MEAN_REVERTING:
  block incremental 00631L additions only

Never:
  sell existing 00631L
  cut 00631L below current holdings
  add above A21.18 target
  change production weights
```

The evaluator compares daily A21.18 target rebalancing against the same path
with this no-add guard applied.

## Baseline Threshold Result

Report:

```text
results/00631l_compounding_regime_no_add_shadow_20260715.json
```

Default thresholds were too loose:

```text
blocked_days = 585
delta_final_value_sum = -8281.77
delta_sharpe_sum = +0.003134
delta_max_drawdown_sum = +0.004308
positive_final_value_windows = 2 / 5
```

Interpretation:

```text
The concept is directionally useful for risk smoothing, but a loose
MEAN_REVERTING label blocks too many rebound/top-up days and hurts return.
```

## Parameter Sweep

Tested variants:

```text
mrscore4:
  mean_reversion_score_min = 4
  blocked_days = 328
  delta_final_value_sum = -3103.21
  positive_final_value_windows = 1 / 5

mrscore5:
  mean_reversion_score_min = 5
  blocked_days = 122
  delta_final_value_sum = +2530.69
  delta_sharpe_sum = +0.004480
  delta_max_drawdown_sum = +0.001518
  positive_final_value_windows = 2 / 5

mrscore6:
  mean_reversion_score_min = 6
  blocked_days = 2
  delta_final_value_sum = -1.88
  positive_final_value_windows = 0 / 5
```

Best current candidate:

```text
results/00631l_compounding_regime_no_add_shadow_mrscore5_arneg15_20260715.json
```

Thresholds:

```text
mean_reversion_score_min = 5
ar1_revert_max = -0.15
trend_score_min = 4
variance_ratio_revert_max = 0.98
trend_persistence_revert_max = 0.55
reversal_speed_revert_min = 0.55
drawdown_recovery_revert_min = 0.50
```

Totals:

```text
blocked_days = 94
delta_final_value_sum = +2905.97
delta_sharpe_sum = +0.006085
delta_max_drawdown_sum = +0.001430
positive_final_value_windows = 3 / 5
```

Window split:

```text
live_2024_2026:
blocked_days = 29
delta final value = +3130.12
delta sharpe = +0.004911
delta max drawdown = +0.001218

active_2025_2026:
blocked_days = 22
delta final value = -445.05
delta sharpe = -0.000736
delta max drawdown = 0.0

2017_bull:
blocked_days = 15
delta final value = +18.94
delta sharpe = +0.000346

2018_correction:
blocked_days = 19
delta final value = +219.99
delta sharpe = +0.001594
delta max drawdown = +0.000191

2019_recovery:
blocked_days = 9
delta final value = -18.03
delta sharpe = -0.000031
```

## Step 2: Rolling CE and Slower Rebalancing Proxy

Added rolling compounding-effect features:

```text
compounding_effect_20d = 00631L 20d return - 2 * 0050 20d return
compounding_effect_60d = 00631L 60d return - 2 * 0050 60d return
compounding_effect_120d = 00631L 120d return - 2 * 0050 120d return
realized_volatility_20d
realized_volatility_60d
volatility_persistence_ratio = realized_volatility_20d / realized_volatility_60d
```

Updated files:

```text
group_a_plus/integrations/leveraged_compounding_regime.py
scripts/evaluate/evaluate_00631l_leveraged_compounding_regime.py
scripts/evaluate/evaluate_00631l_compounding_regime_no_add_shadow.py
tests/test_leveraged_compounding_regime.py
tests/test_evaluate_00631l_compounding_regime_no_add_shadow.py
```

The shadow evaluator now supports:

```text
--mean-reversion-add-fraction
  0.00 = full NO_ADD
  0.25 = allow 25% of requested incremental 00631L add
  0.50 = allow 50% of requested incremental 00631L add

--ce-filter
  none
  ce20_negative
  ce20_or_60_negative
  ce20_and_60_negative
```

Slow-add results using the strict `mrscore5_arneg15` signal:

```text
slowadd25:
blocked_days = 92
delta_final_value_sum = +2378.63
delta_sharpe_sum = +0.004952
delta_max_drawdown_sum = +0.001062
positive_final_value_windows = 3 / 5

slowadd50:
blocked_days = 87
delta_final_value_sum = +1617.34
delta_sharpe_sum = +0.003389
delta_max_drawdown_sum = +0.000700
positive_final_value_windows = 4 / 5
```

CE-filtered results were worse:

```text
noadd + ce20_negative:
blocked_days = 39
delta_final_value_sum = -378.27
positive_final_value_windows = 1 / 5

noadd + ce20_and_60_negative:
blocked_days = 27
delta_final_value_sum = -375.50
positive_final_value_windows = 1 / 5

slowadd50 + ce20_negative:
blocked_days = 36
delta_final_value_sum = -187.94
positive_final_value_windows = 1 / 5

slowadd50 + ce20_and_60_negative:
blocked_days = 24
delta_final_value_sum = -177.66
positive_final_value_windows = 1 / 5
```

Interpretation:

```text
Rolling CE is useful as a diagnostic, but negative CE is too lagging as a
trade filter in this setup.  It removes many useful strict mean-reversion
signals and leaves weak late signals.

The best production-shaped behavior is slowadd50 because it wins 4 / 5 windows,
but its total return improvement is smaller than full NO_ADD.  Full NO_ADD
has higher total delta but only wins 3 / 5 windows.
```

## Step 3: Trend-Persistent Faster Reentry

The paper's strongest practical implication is asymmetric rebalancing speed:

```text
Trend-persistent path:
  faster daily-reset LETF add / reentry can help compounding

Mean-reverting path:
  slower add or no-add can reduce path drag
```

The shadow evaluator now supports:

```text
--baseline-add-fraction
--mean-reversion-add-fraction
--trend-persistent-add-fraction
```

This lets us compare staged 00631L execution against a staged baseline.  The
most relevant proxy is:

```text
baseline_add_fraction = 0.40
mean_reversion_add_fraction = 0.00
trend_persistent_add_fraction = 1.00
thresholds = mrscore5_arneg15
```

Report:

```text
results/00631l_compounding_regime_staged_base40_mr0_trend100_20260715.json
```

Totals:

```text
blocked_days = 105
accelerated_days = 126
event_days = 231
delta_final_value_sum = +10761.85
delta_sharpe_sum = +0.010933
delta_max_drawdown_sum = +0.000650
positive_final_value_windows = 5 / 5
```

Window split:

```text
live_2024_2026:
blocked_days = 33
accelerated_days = 39
delta final value = +6337.73
delta sharpe = +0.004880
delta max drawdown = +0.000487

active_2025_2026:
blocked_days = 25
accelerated_days = 24
delta final value = +4234.55
delta sharpe = +0.004590
delta max drawdown = 0.0

2017_bull:
blocked_days = 15
accelerated_days = 23
delta final value = +8.19
delta sharpe = +0.000104

2018_correction:
blocked_days = 22
accelerated_days = 18
delta final value = +154.98
delta sharpe = +0.001432
delta max drawdown = +0.000151

2019_recovery:
blocked_days = 10
accelerated_days = 22
delta final value = +26.39
delta sharpe = -0.000073
delta max drawdown = +0.000012
```

Decomposition:

```text
Trend acceleration only:
baseline_add_fraction = 0.40
mean_reversion_add_fraction = 0.40
trend_persistent_add_fraction = 1.00

blocked_days = 97
accelerated_days = 126
delta_final_value_sum = +10748.97
positive_final_value_windows = 4 / 5

Mean-reversion no-add only:
baseline_add_fraction = 0.40
mean_reversion_add_fraction = 0.00
trend_persistent_add_fraction = 0.40

blocked_days = 105
accelerated_days = 0
delta_final_value_sum = +13.17
positive_final_value_windows = 3 / 5
```

Interpretation:

```text
Most of the improvement comes from TREND_PERSISTENT faster reentry, not from
MEAN_REVERTING no-add.  This is consistent with the paper: daily-reset leverage
benefits when return persistence is positive.

This is the strongest A21.20 result so far, but it is still a shadow because
the baseline is a staged-execution proxy rather than the live execution engine.
```

## Step 4: Real Execution Plan Replay Shadow

Added:

```text
scripts/evaluate/evaluate_00631l_compounding_execution_replay_shadow.py
tests/test_evaluate_00631l_compounding_execution_replay_shadow.py
```

Purpose:

```text
Read an existing execution_plan.json and compounding-regime report.
Replay only the 00631L add-speed decision.
Do not mutate execution_plan.json.
Do not override hard guards.
Do not write production pointers.
```

Real replay output:

```text
results/00631l_compounding_execution_replay_shadow_20260715.json
results/00631l_compounding_execution_replay_shadow_20260715_aligned.json
```

Latest replay used:

```text
execution plan actual_data_date = 2026-07-14
compounding regime date = 2026-07-15
compounding_regime = TRANSITIONAL
raw_action = MAINTAIN
recommended_action = BLOCKED_BY_HARD_GUARD
```

00631L shares:

```text
current_shares = 0
theoretical_target_shares = 1402
staged_target_shares_before_guards = 560
final_execution_plan_target_shares = 0
shadow_target_shares_before_hard_guards = 560
shadow_notional_before_hard_guards = 20092.80
```

Hard blockers:

```text
compounding regime date does not align with execution_plan actual_data_date: 2026-07-15 != 2026-07-14
required strategy sources are stale or missing: ['institutional_0050']
turnover ratio 73.72% exceeds automatic limit 50.00%
blocked pre-trade guard: volatility_gate_no_00631l_add
```

Interpretation:

```text
The real execution replay is wired and working.
Today it cannot advise any live change because the execution plan is stale /
misaligned and volatility gate is blocking 00631L.

This is correct behavior: A21.20 does not override hard execution guards.
```

Aligned 2026-07-15 replay:

```text
execution plan actual_data_date = 2026-07-15
compounding regime date = 2026-07-15
compounding_regime = TRANSITIONAL
raw_action = MAINTAIN
recommended_action = BLOCKED_BY_HARD_GUARD
```

00631L shares:

```text
current_shares = 0
theoretical_target_shares = 942
staged_target_shares_before_guards = 376
final_execution_plan_target_shares = 376
shadow_target_shares_before_hard_guards = 376
shadow_notional_before_hard_guards = 13927.04
```

Hard blockers after alignment:

```text
required strategy sources are stale or missing: ['day_trading_0050', 'institutional_0050']
turnover ratio 59.16% exceeds automatic limit 50.00%
```

Interpretation:

```text
After date alignment, A21.20 and volatility gate are not blocking 00631L.
The replay is MAINTAIN because the compounding regime is TRANSITIONAL.
Execution still requires manual review because source freshness and turnover
limits are outside A21.20.
```

After chip refresh:

```text
institutional_data 0050 latest = 2026-07-15
day_trading_data 0050 latest = 2026-07-15
```

Refreshed execution plan:

```text
results/group_a_plus_execution_plan_v2_20260715_after_chip_refresh.json
report/group_a_plus/latest/execution_plan.json
```

Post-refresh blockers:

```text
turnover ratio 59.16% exceeds automatic limit 50.00%
```

Post-refresh A21.20 replay:

```text
results/00631l_compounding_execution_replay_shadow_20260715_after_chip_refresh.json

compounding_regime = TRANSITIONAL
raw_action = MAINTAIN
recommended_action = BLOCKED_BY_HARD_GUARD
hard_blockers = ['turnover ratio 59.16% exceeds automatic limit 50.00%']
shadow_target_shares_before_hard_guards = 376
```

Turnover 60% shadow:

```text
results/group_a_plus_execution_plan_v2_20260715_after_chip_refresh_turnover60_shadow.json

planning_status = ready
execution_allowed = true
turnover_ratio = 59.16%
max_automatic_turnover_ratio = 60.00%
```

Trades in turnover-60 shadow:

```text
SELL 00679B.TWO: 5000 -> 0, notional 133750.00
BUY 0050.TW: 1342 -> 1491, notional 15838.70
BUY 00631L.TW: 0 -> 376, notional 13927.04
estimated_cash_after_execution = 103669.49
```

Interpretation:

```text
After refreshing 7/15 chip data, stale-source blockers are cleared.
A21.20, volatility gate, risk-add guard, and Graph NO_ADD are not blocking.
The only remaining automatic blocker is turnover cap.

If manually allowing a 60% turnover cap, the plan becomes ready.  This should
remain an explicit turnover-risk decision, not an A21.20 model promotion.
```

## Step 5: 50% Turnover-Capped Execution Shadow

Added:

```text
scripts/evaluate/evaluate_turnover_capped_execution_shadow.py
tests/test_evaluate_turnover_capped_execution_shadow.py
```

Purpose:

```text
Keep production turnover cap at 50%.
Find a partial execution target that fits the cap.
Do not change the model target or production execution plan.
```

Reports:

```text
results/turnover_capped_execution_shadow_20260715_buys_first.json
results/turnover_capped_execution_shadow_20260715_risk_first.json
results/turnover_capped_execution_shadow_20260715_sell_first.json
```

Full refreshed plan:

```text
turnover_ratio = 59.16%
target_shares:
  0050.TW = 1491
  00631L.TW = 376
  00679B.TWO = 0
```

50% cap, buys_first / risk_first:

```text
turnover_ratio = 49.993%
buy_notional = 29765.74
sell_notional = 108417.75
target_shares:
  0050.TW = 1491
  00631L.TW = 376
  00679B.TWO = 947

executed:
  BUY 0050.TW: 1342 -> 1491
  BUY 00631L.TW: 0 -> 376
  SELL 00679B.TWO: 5000 -> 947

deferred:
  SELL 00679B.TWO: 947 shares
```

50% cap, sell_first:

```text
turnover_ratio = 49.993%
target_shares:
  0050.TW = 1383
  00631L.TW = 2
  00679B.TWO = 0

deferred:
  BUY 0050.TW: 108 shares
  BUY 00631L.TW: 374 shares
```

Interpretation:

```text
If staying strictly inside the 50% cap, buys_first/risk_first is the better
reentry-shaped shadow: it completes the 0050/00631L recovery buys and defers
only the final 947 shares of 00679B liquidation.

sell_first preserves the bond exit but almost entirely misses the 00631L
reentry, which conflicts with the current research direction.
```

## Step 6: Staged Rebalancing Grid

Added:

```text
scripts/evaluate/sweep_00631l_compounding_rebalance_grid.py
tests/test_sweep_00631l_compounding_rebalance_grid.py
```

Reports:

```text
results/00631l_compounding_rebalance_grid_20260715.json
results/00631l_compounding_rebalance_grid_20260715.csv
```

Grid:

```text
baseline_add_fraction = 0.20, 0.40, 0.60
mean_reversion_add_fraction = 0.00, 0.25, 0.50
trend_persistent_add_fraction = 0.80, 1.00
thresholds = mrscore5_arneg15
ce_filter = none
```

Ranking rule:

```text
positive windows
then active_2025_2026 delta
then total delta
then Sharpe delta
```

Best robust candidate:

```text
baseline_add_fraction = 0.40
mean_reversion_add_fraction = 0.00
trend_persistent_add_fraction = 1.00

blocked_days = 105
accelerated_days = 126
event_days = 231
delta_final_value_sum = +10761.85
delta_sharpe_sum = +0.010933
delta_max_drawdown_sum = +0.000650
positive_final_value_windows = 5 / 5
active_2025_2026_delta_final_value = +4234.55
live_2024_2026_delta_final_value = +6337.73
```

Top alternatives:

```text
base60 / mr50 / trend100:
positive windows = 5 / 5
delta_final_value_sum = +7596.69
active_2025_2026_delta = +3071.33

base60 / mr25 / trend100:
positive windows = 5 / 5
delta_final_value_sum = +8117.39
active_2025_2026_delta = +2991.90

base60 / mr0 / trend100:
positive windows = 5 / 5
delta_final_value_sum = +8351.74
active_2025_2026_delta = +2815.24

base40 / mr0 / trend80:
positive windows = 5 / 5
delta_final_value_sum = +6953.74
active_2025_2026_delta = +2614.93
```

High-return but less robust:

```text
base20 / mr25 / trend100:
delta_final_value_sum = +18551.69
active_2025_2026_delta = +7766.29
positive windows = 4 / 5
delta_max_drawdown_sum = -0.000071

base20 / mr0 / trend100:
delta_final_value_sum = +18168.81
active_2025_2026_delta = +7592.52
positive windows = 4 / 5
```

Interpretation:

```text
The previous best candidate was not a local accident.  base40/mr0/trend100
remains the best robust setting under the 5/5 positive-window gate.

base20 variants produce larger total gains but fail one window and can worsen
drawdown, so they should not replace the robust candidate.
```

## Step 7: Local Parameter Tune Around Robust Candidate

Reports:

```text
results/00631l_compounding_rebalance_grid_local_tune_20260715.json
results/00631l_compounding_rebalance_grid_local_tune_20260715.csv
```

Local grid:

```text
baseline_add_fraction = 0.30, 0.35, 0.40, 0.45, 0.50
mean_reversion_add_fraction = 0.00, 0.10
trend_persistent_add_fraction = 0.90, 1.00
thresholds = mrscore5_arneg15
ce_filter = none
```

Best local-tune result:

```text
baseline_add_fraction = 0.40
mean_reversion_add_fraction = 0.00
trend_persistent_add_fraction = 1.00

blocked_days = 105
accelerated_days = 126
event_days = 231
delta_final_value_sum = +10761.85
delta_sharpe_sum = +0.010933
delta_max_drawdown_sum = +0.000650
positive_final_value_windows = 5 / 5
active_2025_2026_delta_final_value = +4234.55
live_2024_2026_delta_final_value = +6337.73
```

Next local alternatives:

```text
base45 / mr10 / trend100:
positive windows = 5 / 5
delta_final_value_sum = +10044.98
active_2025_2026_delta = +3936.61
live_2024_2026_delta = +5954.57

base35 / mr0 / trend90:
positive windows = 5 / 5
delta_final_value_sum = +9837.56
active_2025_2026_delta = +3884.41
live_2024_2026_delta = +5732.61

base45 / mr0 / trend100:
positive windows = 5 / 5
delta_final_value_sum = +10012.48
active_2025_2026_delta = +3850.72
live_2024_2026_delta = +5984.41
```

Interpretation:

```text
The local tune did not improve the robust setting.  base40/mr0/trend100
remains best by the same ranking rule and also leads active_2025_2026 and
live_2024_2026 among the local 5/5 positive-window candidates.

Slightly higher baseline add speed, small mean-reversion allowance, or slower
trend acceleration all reduce the active/live deltas.  There is no parameter
change to promote from this local tune.
```

## Step 8: Trend-Persistent Threshold Tune

Added:

```text
scripts/evaluate/sweep_00631l_compounding_trend_thresholds.py
tests/test_sweep_00631l_compounding_trend_thresholds.py
```

Purpose:

```text
Keep the best staged add-speed policy fixed:
  baseline_add_fraction = 0.40
  mean_reversion_add_fraction = 0.00
  trend_persistent_add_fraction = 1.00

Tune only the TREND_PERSISTENT trigger thresholds.
```

Mid-grid reports:

```text
results/00631l_compounding_trend_threshold_grid_mid_20260715.json
results/00631l_compounding_trend_threshold_grid_mid_20260715.csv
```

Mid-grid:

```text
trend_score_min = 3, 4, 5
ar1_trend_min = 0.00, 0.05
trend_persistence_min = 0.55, 0.60
reversal_speed_trend_max = 0.45, 0.50
```

Best mid-grid candidate:

```text
trend_score_min = 3
ar1_trend_min = 0.00
trend_persistence_min = 0.55
reversal_speed_trend_max = 0.50

trend_persistent_days = 902
mean_reverting_days = 175
blocked_days = 102
accelerated_days = 374
event_days = 476
delta_final_value_sum = +19979.15
delta_sharpe_sum = +0.019938
delta_max_drawdown_sum = +0.000865
positive_final_value_windows = 5 / 5
active_2025_2026_delta_final_value = +5813.96
live_2024_2026_delta_final_value = +13434.85
```

Edge-grid reports:

```text
results/00631l_compounding_trend_threshold_grid_edge_20260715.json
results/00631l_compounding_trend_threshold_grid_edge_20260715.csv
```

Edge-grid:

```text
trend_score_min = 3
ar1_trend_min = -0.05, 0.00, 0.05
trend_persistence_min = 0.50, 0.55
reversal_speed_trend_max = 0.50, 0.55
```

Preferred edge-grid candidate by existing ranking rule:

```text
trend_score_min = 3
ar1_trend_min = 0.00
trend_persistence_min = 0.50
reversal_speed_trend_max = 0.50

trend_persistent_days = 953
mean_reverting_days = 175
blocked_days = 102
accelerated_days = 391
event_days = 493
delta_final_value_sum = +20523.29
delta_sharpe_sum = +0.021773
delta_max_drawdown_sum = +0.000750
positive_final_value_windows = 5 / 5
active_2025_2026_delta_final_value = +6074.40
live_2024_2026_delta_final_value = +13583.59
```

Preferred edge-grid window split:

```text
live_2024_2026:
  final = +13583.59
  sharpe = +0.008282
  max_drawdown = +0.000485

active_2025_2026:
  final = +6074.40
  sharpe = +0.006179
  max_drawdown = +0.000004

2017_bull:
  final = +291.82
  sharpe = +0.003068
  max_drawdown = -0.000013

2018_correction:
  final = +422.98
  sharpe = +0.003693
  max_drawdown = +0.000235

2019_recovery:
  final = +150.50
  sharpe = +0.000551
  max_drawdown = +0.000038
```

Higher-total but more aggressive edge candidate:

```text
trend_score_min = 3
ar1_trend_min = -0.05
trend_persistence_min = 0.50
reversal_speed_trend_max = 0.55

trend_persistent_days = 1105
blocked_days = 94
accelerated_days = 444
delta_final_value_sum = +20614.65
positive_final_value_windows = 5 / 5
active_2025_2026_delta_final_value = +6027.00
live_2024_2026_delta_final_value = +13790.15
```

Interpretation:

```text
The main improvement is not from changing add fractions.  It comes from
making TREND_PERSISTENT easier to trigger, so the shadow model restores 00631L
faster during favorable compounding paths.

The preferred threshold candidate improves all five windows and beats the
previous base40/mr0/trend100 result:
  previous total delta = +10761.85
  tuned-trend total delta = +20523.29

This is still a shadow/advisory result.  trend_score_min = 3 marks many more
days as TREND_PERSISTENT, so it should be validated with stress windows and
execution constraints before any production promotion.
```

## Step 9: Seven-Window Stress Check

Purpose:

```text
Check whether the tuned TREND_PERSISTENT threshold survives additional stress
windows instead of only improving the original five-window set.
```

Seven-window set:

```text
covid_2020: 2020-01-02..2020-12-31
inflation_2022: 2022-01-03..2022-12-30
live_2024_2026: 2024-01-02..latest
active_2025_2026: 2025-01-02..latest
2017_bull: 2017-01-03..2017-12-29
2018_correction: 2018-01-02..2018-12-31
2019_recovery: 2019-01-02..2019-12-31
```

Reports:

```text
results/00631l_compounding_regime_staged_base40_mr0_trend100_7win_20260715.json
results/00631l_compounding_regime_tunedtrend_score3_ar0_persist50_rev50_7win_20260715.json
results/00631l_compounding_regime_tunedtrend_score3_arneg05_persist50_rev55_7win_20260715.json
```

Seven-window comparison:

```text
robust base40/mr0/trend100:
  blocked_days = 115
  accelerated_days = 147
  event_days = 262
  delta_final_value_sum = +10885.70
  delta_sharpe_sum = +0.011864
  delta_max_drawdown_sum = +0.000650
  positive_final_value_windows = 7 / 7

preferred tuned trend score3/ar0/persist50/rev50:
  blocked_days = 111
  accelerated_days = 450
  event_days = 561
  delta_final_value_sum = +27106.57
  delta_sharpe_sum = +0.084399
  delta_max_drawdown_sum = +0.000748
  positive_final_value_windows = 7 / 7

aggressive tuned trend score3/arneg05/persist50/rev55:
  blocked_days = 103
  accelerated_days = 504
  event_days = 607
  delta_final_value_sum = +27196.00
  delta_sharpe_sum = +0.083361
  delta_max_drawdown_sum = +0.000732
  positive_final_value_windows = 7 / 7
```

Preferred tuned stress-window split:

```text
covid_2020:
  final = +3275.54
  sharpe = +0.015741
  max_drawdown = -0.000024

inflation_2022:
  final = +3307.75
  sharpe = +0.046885
  max_drawdown = +0.000022

live_2024_2026:
  final = +13583.59
  sharpe = +0.008282
  max_drawdown = +0.000485

active_2025_2026:
  final = +6074.40
  sharpe = +0.006179
  max_drawdown = +0.000004
```

Interpretation:

```text
Adding 2020 COVID and 2022 inflation stress windows strengthens the preferred
tuned-threshold case: it remains 7/7 positive and improves materially over the
original robust base40/mr0/trend100.

The aggressive threshold has slightly higher total final-value delta, but it
uses more TREND_PERSISTENT days, has lower Sharpe and drawdown improvement, and
is weaker in active_2025_2026, 2017, 2018, and 2019.  Keep it as an aggressive
shadow only; do not replace the preferred candidate.
```

## Step 10: Tuned Daily Diagnostic and Execution Replay

Updated:

```text
scripts/evaluate/evaluate_00631l_leveraged_compounding_regime.py
```

Change:

```text
Daily diagnostic now accepts threshold CLI parameters and writes the threshold
set into the report.  This allows the preferred tuned candidate to be replayed
against real execution plans.
```

Reports:

```text
results/00631l_leveraged_compounding_regime_tunedtrend_score3_ar0_persist50_rev50_20260715.json
results/00631l_leveraged_compounding_regime_tunedtrend_score3_ar0_persist50_rev50_20260715.csv
results/00631l_compounding_execution_replay_shadow_tunedtrend_score3_ar0_persist50_rev50_20260715.json
```

Tuned 2026-07-15 daily state:

```text
date = 2026-07-15
compounding_regime = TREND_PERSISTENT
recommended_policy = do_not_reduce_00631l_for_high_volatility_alone
```

Real execution replay with tuned diagnostic:

```text
raw_action = FAST_REENTER_CANDIDATE
recommended_action = BLOCKED_BY_HARD_GUARD
hard_blockers = ['turnover ratio 59.16% exceeds automatic limit 50.00%']

current_00631L = 0
theoretical_target_00631L = 942
staged_target_before_guards = 376
final_execution_plan_target = 376
shadow_target_before_hard_guards = 942
shadow_notional_before_hard_guards = 34891.68
```

Interpretation:

```text
The tuned threshold changes 2026-07-15 from TRANSITIONAL to TREND_PERSISTENT.
It correctly asks for faster 00631L reentry, but hard guards still win.
Production effect remains none.
```

## Step 11: Cost and Turnover Feasibility Stress

Updated:

```text
scripts/evaluate/evaluate_00631l_compounding_regime_no_add_shadow.py
tests/test_evaluate_00631l_compounding_regime_no_add_shadow.py
scripts/evaluate/evaluate_turnover_capped_execution_shadow.py
tests/test_evaluate_turnover_capped_execution_shadow.py
```

Cost-model change:

```text
--transaction-cost-bps applies the same simple turnover cost to both baseline
and candidate.  When target positions plus cost exceed NAV, target positions
are scaled down after reserving estimated cost.
```

Seven-window preferred tuned cost stress:

```text
0 bps:
  delta_final_value_sum = +27106.57
  delta_sharpe_sum = +0.084399
  positive_final_value_windows = 7 / 7

5 bps:
  delta_final_value_sum = +26668.31
  delta_sharpe_sum = +0.083270
  positive_final_value_windows = 7 / 7

10 bps:
  delta_final_value_sum = +26231.12
  delta_sharpe_sum = +0.082138
  positive_final_value_windows = 7 / 7

20 bps:
  delta_final_value_sum = +25359.94
  delta_sharpe_sum = +0.079863
  positive_final_value_windows = 7 / 7
```

Turnover-capped tuned replay target:

```text
Override only for shadow:
  00631L.TW target = 942

50% cap, risk_first / buys_first:
  turnover_ratio = 49.9905%
  target_shares:
    0050.TW = 1491
    00631L.TW = 942
    00679B.TWO = 1731
  buy_notional = 50730.38
  sell_notional = 87445.75
  total_execution_cost = 265.99

executed:
  BUY 0050.TW: 1342 -> 1491
  BUY 00631L.TW: 0 -> 942
  SELL 00679B.TWO: 5000 -> 1731

deferred:
  SELL 00679B.TWO: 1731 shares
```

Interpretation:

```text
The preferred tuned candidate survives 5/10/20 bps cost stress.

The 50% turnover cap can still complete the tuned 00631L fast reentry target
of 942 shares if buys are prioritized; the trade-off is deferring part of the
00679B exit.  This supports a staged execution interpretation, not a hard-guard
override.
```

## Step 12: A21.19 Overlap Audit

Reports:

```text
results/a2119_reentry_regret_gate_7win_20260715.json
results/a2120_a2119_tunedtrend_overlap_audit_20260715.json
```

A21.19 seven-window summary:

```text
windows = 7
triple_pass_windows = 7
action_counts = {'KEEP': 2161}
candidate_non_keep_days = 0

event_count = 15
00631l_increase_events = 10
no_add_help_count = 1
no_add_hurt_count = 9
```

Overlap audit:

```text
A21.20 tuned TREND_PERSISTENT dates = 1688
A21.19 00631L increase events = 10
overlap_events = 9
overlap_no_add_help = 0
overlap_no_add_hurt = 9
non_overlap_events = 1
```

Overlapped events:

```text
2020-06-03 covid_2020: NO_ADD regret = -0.017669
2020-06-04 covid_2020: NO_ADD regret = -0.004671
2022-11-11 inflation_2022: NO_ADD regret = -0.017274
2025-06-09 live/active: NO_ADD regret = -0.015611
2025-06-10 live/active: NO_ADD regret = -0.003124
2017-01-24 2017_bull: NO_ADD regret = -0.005589
2017-03-16 2017_bull: NO_ADD regret = -0.000096
```

Interpretation:

```text
There is no material conflict between A21.20 tuned fast reentry and A21.19
NO_ADD regret evidence in this audit.  The A21.20 trend signal overlaps only
with A21.19 events where NO_ADD would have hurt, which supports faster reentry.

A21.19 still remains the higher-level action-regret gate.  A21.20 should only
act as a reentry-speed advisory and must not override hard guards.
```

## Step 13: Promotion Gate Scorecard

Added:

```text
scripts/evaluate/build_a2120_letf_compounding_shadow_scorecard.py
tests/test_build_a2120_letf_compounding_shadow_scorecard.py
```

Scorecard:

```text
report/group_a_plus/shadow/a2120_letf_compounding_shadow_scorecard_20260715.json
```

Gate checks:

```text
seven_window_positive = pass
  positive_final_value_windows = 7
  delta_final_value_sum = +27106.57

cost20_positive = pass
  transaction_cost_bps = 20
  positive_final_value_windows = 7
  delta_final_value_sum = +25359.94

rolling_cost20_stability = pass
  windows = 11
  transaction_cost_bps = 20
  preferred_positive_rate = 1.0
  preferred_median = +3045.77
  preferred_min = +63.89
  incremental_positive_rate = 1.0
  incremental_min = +34.07

turnover50_reentry_complete = pass
  turnover_ratio = 49.9905%
  target_00631L = 942
  required_00631L = 942

a2119_no_conflict = pass
  overlap_events = 9
  overlap_no_add_help = 0
  overlap_no_add_hurt = 9

hard_guards_not_overridden = pass
  raw_action = FAST_REENTER_CANDIDATE
  recommended_action = BLOCKED_BY_HARD_GUARD
  production_effect = none
```

Scorecard decision:

```text
shadow_gate = pass
daily_advisory = enable_daily_advisory_shadow_only
production = do_not_promote
production_upgrade_pass = false
```

Production blockers:

```text
research_only_shadow_candidate
hard_guards_must_remain_precedence
requires_daily_ops_integration
requires_t_plus_1_execution_alignment_audit
requires_rolling_window_shadow_monitoring_before_production
```

Interpretation:

```text
A21.20 preferred tuned candidate now passes the current shadow evidence gate.
The right next promotion level is daily advisory shadow-only, not production
execution.  Hard guards remain authoritative.
```

## Step 14: Daily Ops Shadow Integration

Added:

```text
scripts/run/run_a2120_daily_shadow_pipeline.py
tests/test_run_a2120_daily_shadow_pipeline.py
```

Purpose:

```text
Produce daily A21.20 shadow-only artifacts from existing inputs:
  tuned compounding diagnostic
  real execution replay
  turnover-capped tuned replay
  scorecard
  latest summary pointer

Never:
  mutate production strategy
  mutate production execution plan
  override hard guards
```

Command run:

```bash
.venv/bin/python scripts/run/run_a2120_daily_shadow_pipeline.py \
  --date-stamp 20260715 \
  --execution-plan results/group_a_plus_execution_plan_v2_20260715_after_chip_refresh.json
```

Artifacts:

```text
results/00631l_leveraged_compounding_regime_tunedtrend_score3_ar0_persist50_rev50_20260715.json
results/00631l_leveraged_compounding_regime_tunedtrend_score3_ar0_persist50_rev50_20260715.csv
results/00631l_compounding_execution_replay_shadow_tunedtrend_score3_ar0_persist50_rev50_20260715.json
results/turnover_capped_execution_shadow_20260715_tunedtrend_00631l942_risk_first.json
report/group_a_plus/shadow/a2120_letf_compounding_shadow_scorecard_20260715.json
report/group_a_plus/latest/a2120_letf_compounding_shadow.json
```

Latest summary:

```text
report_type = a2120_letf_compounding_daily_shadow
production_effect = none
compounding_regime = TREND_PERSISTENT
raw_action = FAST_REENTER_CANDIDATE
recommended_action = BLOCKED_BY_HARD_GUARD
hard_blockers = ['turnover ratio 59.16% exceeds automatic limit 50.00%']
shadow_target_00631l_before_hard_guards = 942
turnover50_target_00631l = 942
turnover50_ratio = 49.9905%
scorecard.shadow_gate = pass
scorecard.daily_advisory = enable_daily_advisory_shadow_only
scorecard.production = do_not_promote
```

Interpretation:

```text
Daily shadow integration is now available.  The output can be consumed by
operations dashboards or review notes as advisory context, but it remains
explicitly non-production and hard-guard aware.
```

## Step 15: A21.19 + A21.20 Combined Policy Simulator

Added:

```text
scripts/evaluate/evaluate_a2119_a2120_combined_policy_shadow.py
tests/test_evaluate_a2119_a2120_combined_policy_shadow.py
```

Integrated into:

```text
scripts/run/run_a2120_daily_shadow_pipeline.py
report/group_a_plus/latest/a2120_letf_compounding_shadow.json
```

Policy order:

```text
1. hard_guard
2. A21.19 action-regret gate
3. A21.20 LETF compounding reentry-speed advisory
```

Rules:

```text
hard guard active
  -> BLOCKED_BY_HARD_GUARD

A21.19 = NO_ADD
  -> NO_ADD
  -> A21.20 cannot override

A21.19 = REENTER and A21.20 = TREND_PERSISTENT
  -> FAST_REENTER_CANDIDATE

A21.19 = KEEP and A21.20 raw action = FAST_REENTER_CANDIDATE
  -> FAST_REENTER_CANDIDATE

A21.20 = MEAN_REVERTING
  -> NO_ADD advisory

otherwise
  -> KEEP
```

Report:

```text
report/group_a_plus/shadow/a2119_a2120_combined_policy_shadow_20260715.json
```

2026-07-15 combined result:

```text
A21.19 action = KEEP
A21.20 regime = TREND_PERSISTENT
A21.20 raw action = FAST_REENTER_CANDIDATE
hard_blockers = ['turnover ratio 59.16% exceeds automatic limit 50.00%']

combined_action = BLOCKED_BY_HARD_GUARD
production_effect = none
reason = Hard guards have precedence over A21.19 and A21.20 shadow advisories.
```

Latest summary now includes:

```text
combined_action = BLOCKED_BY_HARD_GUARD
artifacts.combined_policy = report/group_a_plus/shadow/a2119_a2120_combined_policy_shadow_20260715.json
```

Interpretation:

```text
The simulator fixes A21.20's role: it can accelerate reentry only when A21.19
does not block and hard guards are clear.  It is not a standalone risk gate and
does not perform automatic de-risking.
```

## Step 16: Rolling-Window Stability Audit

Added:

```text
scripts/evaluate/evaluate_00631l_compounding_rolling_windows.py
tests/test_evaluate_00631l_compounding_rolling_windows.py
```

Purpose:

```text
Check whether the preferred tuned A21.20 candidate is stable across rolling
252-trading-day windows, instead of only passing hand-picked event windows.
Compare:
  robust = score4/ar05/persist60/rev45
  preferred = score3/ar0/persist50/rev50
```

Reports:

```text
results/00631l_compounding_rolling_windows_252d_step126_12win_20260715.json
results/00631l_compounding_rolling_windows_252d_step126_12win_20260715.csv
results/00631l_compounding_rolling_windows_252d_step126_12win_cost20bps_20260715.json
results/00631l_compounding_rolling_windows_252d_step126_12win_cost20bps_20260715.csv
```

0 bps rolling result:

```text
windows = 11
preferred_delta_final_value positive = 11 / 11
preferred_delta_final_value median = +3157.91
preferred_delta_final_value min = +168.27
preferred_delta_final_value max = +4212.54
incremental_delta_final_value positive = 11 / 11
incremental_delta_final_value median = +2413.78
incremental_delta_final_value min = +111.43
pass = true
```

20 bps rolling result:

```text
windows = 11
preferred_delta_final_value positive = 11 / 11
preferred_delta_final_value median = +3045.77
preferred_delta_final_value min = +63.89
preferred_delta_final_value max = +4017.75
incremental_delta_final_value positive = 11 / 11
incremental_delta_final_value median = +2243.35
incremental_delta_final_value min = +34.07
pass = true
```

Weakest 20 bps window:

```text
roll_2023-02-14_2024-02-29:
  preferred_delta_final_value = +63.89
  incremental_delta_final_value = +34.07
  robust_delta_final_value = +29.82
  preferred_event_days = 75
```

Scorecard integration:

```text
build_a2120_letf_compounding_shadow_scorecard.py now requires the 20 bps
rolling report and adds rolling_cost20_stability as a shadow gate.
```

Interpretation:

```text
The tuned preferred candidate is not only better on fixed event windows; it
also survives rolling 252-day windows with 20 bps transaction cost.  The edge
is thin in 2023-02-14..2024-02-29, so this supports shadow advisory status,
not production promotion.
```

## Step 17: Strict Rolling and Trend-Speed Variant

Updated:

```text
scripts/evaluate/evaluate_00631l_compounding_rolling_windows.py
tests/test_evaluate_00631l_compounding_rolling_windows.py
```

Change:

```text
The rolling evaluator now accepts preferred threshold and add-speed parameters.
Defaults remain unchanged:
  score3/ar0/persist50/rev50
  baseline_add_fraction = 0.40
  mean_reversion_add_fraction = 0.00
  trend_persistent_add_fraction = 1.00
```

Strict 20 bps rolling tests for the main preferred candidate:

```text
126d / step63:
  windows = 24
  preferred positive = 19 / 24
  preferred median = +455.93
  preferred min = -130.78
  incremental positive = 17 / 24
  incremental median = +243.46
  incremental min = -40.44
  pass = true

189d / step63:
  windows = 23
  preferred positive = 19 / 23
  preferred median = +2463.24
  preferred min = -65.56
  incremental positive = 19 / 23
  incremental median = +854.40
  incremental min = -7.74
  pass = true

252d / step63:
  windows = 22
  preferred positive = 20 / 22
  preferred median = +3071.93
  preferred min = -104.43
  incremental positive = 20 / 22
  incremental median = +1526.45
  incremental min = -32.50
  pass = true
```

Conservative threshold attempts:

```text
score3/ar0/persist55/rev50:
  126d preferred positive = 18 / 24
  preferred median = +349.51
  preferred min = -134.65

score3/ar0/persist55/rev45:
  126d preferred positive = 18 / 24
  preferred median = +268.13
  preferred min = -136.49
```

Interpretation:

```text
Tightening the trend threshold does not improve robustness.  It removes useful
reentry events, lowers median benefit, and slightly worsens the short-window
tail.  Do not replace the preferred threshold with these conservative variants.
```

Aggressive threshold attempt:

```text
score3/arneg05/persist50/rev55:
  126d preferred positive = 19 / 24
  preferred median = +398.63
  preferred min = -129.58
  incremental positive = 17 / 24
  incremental min = -68.34
```

Interpretation:

```text
The aggressive threshold can raise the max window, but it lowers median and
worsens incremental tail versus the main preferred candidate.  Keep it as
research-only; do not promote.
```

Trend-speed variants:

```text
trend_persistent_add_fraction = 0.80, 126d / step63:
  preferred positive = 20 / 24
  preferred median = +353.40
  preferred min = -117.57
  incremental positive = 19 / 24
  incremental median = +183.42
  incremental min = -22.99

trend_persistent_add_fraction = 0.90, 126d / step63:
  preferred positive = 19 / 24
  preferred median = +408.55
  preferred min = -122.97
  incremental positive = 19 / 24
  incremental median = +214.77
  incremental min = -31.11

trend_persistent_add_fraction = 0.90, 189d / step63:
  preferred positive = 19 / 23
  preferred median = +2243.21
  preferred min = -52.05
  incremental positive = 20 / 23
  incremental median = +888.43
  incremental min = -4.62

trend_persistent_add_fraction = 0.90, 252d / step63:
  preferred positive = 20 / 22
  preferred median = +2661.14
  preferred min = -89.60
  incremental positive = 21 / 22
  incremental median = +1368.96
  incremental min = -24.54
```

Decision from Step 17:

```text
Keep the main preferred candidate as:
  score3/ar0/persist50/rev50 + trend100

Add a risk-sensitive shadow variant:
  score3/ar0/persist50/rev50 + trend90

Do not replace the main candidate.  trend90 improves rolling tail behavior but
gives up median upside.  It is useful as a diagnostic alternative when the
operator wants less aggressive reentry under the same hard-guard hierarchy.
```

## Step 18: Minimum-Edge Weak Trend Gate

Updated:

```text
scripts/evaluate/evaluate_00631l_compounding_regime_no_add_shadow.py
scripts/evaluate/evaluate_00631l_compounding_rolling_windows.py
tests/test_evaluate_00631l_compounding_regime_no_add_shadow.py
tests/test_evaluate_00631l_compounding_rolling_windows.py
```

Purpose:

```text
Avoid applying full trend100 fast reentry on TREND_PERSISTENT dates where the
edge is thin.  This is not an exit rule and does not reduce existing 00631L.
It only changes the add speed from 1.00 to 0.90 on selected weak-edge dates.
```

Weak-edge gates tested on 126d / step63 / 20 bps:

```text
base trend100:
  preferred positive = 19 / 24
  preferred median = +455.93
  preferred min = -130.78
  incremental positive = 17 / 24
  incremental median = +243.46
  incremental min = -40.44

trend_score_eq_min -> trend90:
  preferred positive = 19 / 24
  preferred median = +398.29
  preferred min = -130.31
  incremental positive = 19 / 24
  incremental median = +354.92
  incremental min = -30.73

relative_momentum_nonpositive -> trend90:
  preferred positive = 19 / 24
  preferred median = +411.93
  preferred min = -129.83
  incremental positive = 17 / 24
  incremental median = +228.15
  incremental min = -52.90

ce20_negative -> trend90:
  preferred positive = 19 / 24
  preferred median = +419.09
  preferred min = -126.74
  incremental positive = 19 / 24
  incremental median = +227.92
  incremental min = -29.49

any -> trend90:
  preferred positive = 19 / 24
  preferred median = +406.39
  preferred min = -127.30
  incremental positive = 19 / 24
  incremental median = +215.27
  incremental min = -31.13
```

Best candidate carried forward:

```text
weak_trend_edge_gate = ce20_negative
weak_trend_add_fraction = 0.90
```

Why:

```text
It improves preferred tail and incremental tail with smaller median sacrifice
than full trend90.  relative_momentum_nonpositive worsens incremental tail,
and any is too broad.
```

CE20 weak-edge full strict rolling:

```text
126d / step63:
  preferred positive = 19 / 24
  preferred median = +419.09
  preferred min = -126.74
  incremental positive = 19 / 24
  incremental median = +227.92
  incremental min = -29.49

189d / step63:
  preferred positive = 19 / 23
  preferred median = +2254.01
  preferred min = -50.76
  incremental positive = 22 / 23
  incremental median = +845.86
  incremental min = 0.00

252d / step63:
  preferred positive = 20 / 22
  preferred median = +2751.99
  preferred min = -80.92
  incremental positive = 21 / 22
  incremental median = +1381.79
  incremental min = -7.01
```

Decision from Step 18:

```text
Keep main preferred candidate:
  score3/ar0/persist50/rev50 + trend100

Keep risk-sensitive global variant:
  score3/ar0/persist50/rev50 + trend90

Add minimum-edge shadow variant:
  score3/ar0/persist50/rev50 + trend100
  but if compounding_effect_20d < 0, use trend90 for that date.

This variant is useful when the operator wants less tail risk without globally
slowing every TREND_PERSISTENT reentry.  It should remain shadow-only until it
also passes event-window, A21.19 overlap, daily replay, and scorecard gates.
```

## Step 19: Daily Pipeline Minimum-Edge Variant

Updated:

```text
scripts/evaluate/evaluate_00631l_compounding_execution_replay_shadow.py
scripts/run/run_a2120_daily_shadow_pipeline.py
tests/test_evaluate_00631l_compounding_execution_replay_shadow.py
tests/test_run_a2120_daily_shadow_pipeline.py
```

Change:

```text
Daily A21.20 shadow pipeline now writes both:
  main replay = trend100
  risk-sensitive replay = ce20_negative -> trend90

The risk-sensitive replay is an advisory comparison only.  The scorecard still
uses the main preferred candidate and production effect remains none.
```

Command run:

```bash
.venv/bin/python scripts/run/run_a2120_daily_shadow_pipeline.py --date-stamp 20260716
```

Artifacts:

```text
results/00631l_leveraged_compounding_regime_tunedtrend_score3_ar0_persist50_rev50_20260716.json
results/00631l_compounding_execution_replay_shadow_tunedtrend_score3_ar0_persist50_rev50_20260716.json
results/00631l_compounding_execution_replay_shadow_tunedtrend_score3_ar0_persist50_rev50_ce20neg_to_trend90_20260716.json
results/turnover_capped_execution_shadow_20260716_tunedtrend_00631l942_risk_first.json
results/turnover_capped_execution_shadow_20260716_tunedtrend_ce20neg90_00631l848_risk_first.json
report/group_a_plus/shadow/a2120_letf_compounding_shadow_scorecard_20260716.json
report/group_a_plus/shadow/a2119_a2120_combined_policy_shadow_20260716.json
report/group_a_plus/latest/a2120_letf_compounding_shadow.json
```

Actual latest data date:

```text
date_stamp = 20260716
diagnostic latest date = 2026-07-15
```

This means the 2026-07-16 pipeline run still used the latest available
2026-07-15 market data.  It did not assume 2026-07-16 close data existed.

Main replay:

```text
compounding_regime = TREND_PERSISTENT
raw_action = FAST_REENTER_CANDIDATE
recommended_action = BLOCKED_BY_HARD_GUARD
requested_delta_shares = 942
allowed_fraction_for_regime = 1.0
shadow_target_00631l_before_hard_guards = 942
turnover50_target_00631l = 942
turnover50_ratio = 49.9905%
hard_blocker = turnover ratio 59.16% exceeds automatic limit 50.00%
```

Risk-sensitive CE20 replay:

```text
compounding_effect_20d = -0.014791
weak_trend_edge_gate = ce20_negative
weak_trend_edge_active = true
allowed_fraction_for_regime = 0.9
shadow_target_00631l_before_hard_guards = 848
turnover50_target_00631l = 848
turnover50_ratio = 49.9987%
recommended_action = BLOCKED_BY_HARD_GUARD
```

Interpretation:

```text
For the latest available data, the risk-sensitive variant is active because
20d compounding effect is negative.  It would reduce the shadow reentry target
from 942 to 848 shares before hard guards.  However, both main and risk-
sensitive variants remain blocked by the same hard turnover guard, so there is
no production effect.
```

## Step 20: CE20 Variant Event-Window Stress

Added:

```text
scripts/evaluate/build_a2120_variant_comparison.py
tests/test_build_a2120_variant_comparison.py
```

Purpose:

```text
Check whether the CE20 weak-edge variant remains viable on the fixed seven
event/stress windows, not only on rolling windows and daily replay.
```

Reports:

```text
results/00631l_compounding_regime_tunedtrend_score3_ar0_persist50_rev50_ce20neg90_7win_20260716.json
results/00631l_compounding_regime_tunedtrend_score3_ar0_persist50_rev50_ce20neg90_7win_cost20bps_20260716.json
report/group_a_plus/shadow/a2120_variant_comparison_20260716.json
```

CE20 weak-edge 7-window result:

```text
transaction_cost_bps = 0
positive_final_value_windows = 7 / 7
delta_final_value_sum = +24501.95
delta_sharpe_sum = +0.079045
delta_max_drawdown_sum = +0.000759

transaction_cost_bps = 20
positive_final_value_windows = 7 / 7
delta_final_value_sum = +22965.92
delta_sharpe_sum = +0.075105
delta_max_drawdown_sum = +0.000677
```

Comparison versus main trend100:

```text
0 bps:
  main delta_final_value_sum = +27106.57
  CE20 variant delta_final_value_sum = +24501.95
  CE20 minus main = -2604.62

20 bps:
  main delta_final_value_sum = +25359.94
  CE20 variant delta_final_value_sum = +22965.92
  CE20 minus main = -2394.03
```

Largest cost20 opportunity cost:

```text
live_2024_2026:
  main = +12654.82
  CE20 variant = +11457.38
  difference = -1197.44

active_2025_2026:
  main = +5681.73
  CE20 variant = +4755.27
  difference = -926.46
```

Interpretation:

```text
The CE20 weak-edge variant passes event-window and 20 bps stress, but gives up
meaningful upside in live/active 2024-2026 windows.  It should remain a risk-
sensitive shadow variant, not replace the main trend100 candidate.
```

## Step 21: CE20 Variant A21.19 Overlap Audit

Added:

```text
scripts/evaluate/evaluate_a2120_ce20_variant_a2119_overlap.py
tests/test_evaluate_a2120_ce20_variant_a2119_overlap.py
```

Purpose:

```text
Check whether CE20 weak-edge trend90 slows A21.19 00631L increase events where
the A21.19 event study says NO_ADD would hurt.
```

Report:

```text
results/a2120_ce20_variant_a2119_overlap_audit_20260716.json
```

Summary:

```text
a2119_00631l_increase_events = 10
a2120_main_fast_reentry_overlap_events = 8
ce20_variant_slowed_overlap_events = 5
ce20_variant_slowed_no_add_hurt_events = 5
ce20_variant_slowed_no_add_help_events = 0
ce20_variant_slowed_total_no_add_regret = -0.054745
pass = true
```

Slowed A21.19 high-value reentry events:

```text
2022-11-11 inflation_2022:
  NO_ADD regret = -0.017274
  compounding_effect_20d = -0.006570
  delta_00631l_weight = +0.126261

2025-06-09 live_2024_2026:
  NO_ADD regret = -0.015611
  compounding_effect_20d = -0.011174
  delta_00631l_weight = +0.103373

2025-06-10 live_2024_2026:
  NO_ADD regret = -0.003124
  compounding_effect_20d = -0.025816
  delta_00631l_weight = +0.022888

2025-06-09 active_2025_2026:
  duplicate active-window view of the 2025-06-09 event

2025-06-10 active_2025_2026:
  duplicate active-window view of the 2025-06-10 event
```

Interpretation:

```text
CE20 weak-edge variant does not slow any event where NO_ADD would help, which
is good.  But it does slow five overlap rows where NO_ADD would hurt, including
2022-11-11 and 2025-06-09/10 reentry events.

Therefore CE20 remains a risk-sensitive advisory, not a superior replacement.
When A21.19 explicitly says REENTER, main trend100 should retain precedence
unless the operator intentionally wants less aggressive reentry.
```

## Decision

Shadow gate passes.  Do not promote to production.

Keep as:

```text
A21.20_LETF_COMPOUNDING_REGIME_SHADOW
Preferred candidate = mrscore5_arneg15
Production-shaped candidate = slowadd50_mrscore5_arneg15
Best staged-execution candidate = staged_base40_mr0_trend100
Best grid candidate = base40_mr0_trend100
Best local-tune candidate = base40_mr0_trend100
Best trend-threshold candidate = score3_ar0_persist50_rev50
Risk-sensitive trend-speed variant = score3_ar0_persist50_rev50_trend90
Minimum-edge variant = score3_ar0_persist50_rev50_trend100_ce20_negative_to_trend90
Aggressive trend-threshold candidate = score3_arneg05_persist50_rev55
Real execution replay = available, blocked today by hard guards
Scorecard = pass for daily advisory shadow-only
Production effect = none
```

Reason:

```text
The tuned candidate passes 7-window, cost20bps, turnover50, A21.19 overlap,
rolling-cost20 stability, and hard-guard precedence gates.  It is strong
enough for daily advisory shadow-only integration, but not enough for
production execution because T+1 alignment, daily ops integration, and ongoing
rolling-window monitoring are still pending.
```

Best near-term use:

```text
Advisory only:
  MEAN_REVERTING_STRICT -> warn that new 00631L adds have path-drag risk
  MEAN_REVERTING_STRICT + slowadd50 -> best execution-shaped shadow, not production
  TREND_PERSISTENT + staged baseline -> faster 00631L reentry is the best A21.20 shadow
  TREND_PERSISTENT -> do not reduce 00631L for volatility alone
  TRANSITIONAL -> maintain A21.18
  Real execution replay -> run daily after execution_plan and compounding report align
```

## Relationship to A21.19

This does not replace the A21.19 trough/guard-release finding.

Current hierarchy:

```text
H20 crash diagnostic
  -> warns, does not auto-sell

Trough nowcast + volatility gate override
  -> best current reentry improvement candidate

A21.20 LETF compounding regime
  -> useful advisory/risk label
  -> not yet reliable enough as no-add execution guard
```

## Regeneration Commands

Daily diagnostic:

```bash
.venv/bin/python scripts/evaluate/evaluate_00631l_leveraged_compounding_regime.py \
  --output results/00631l_leveraged_compounding_regime_20260715.json \
  --csv results/00631l_leveraged_compounding_regime_20260715.csv
```

Baseline shadow:

```bash
.venv/bin/python scripts/evaluate/evaluate_00631l_compounding_regime_no_add_shadow.py \
  --output results/00631l_compounding_regime_no_add_shadow_20260715.json
```

Best current strict shadow:

```bash
.venv/bin/python scripts/evaluate/evaluate_00631l_compounding_regime_no_add_shadow.py \
  --mean-reversion-score-min 5 \
  --ar1-revert-max -0.15 \
  --output results/00631l_compounding_regime_no_add_shadow_mrscore5_arneg15_20260715.json
```

Slow-add 50% strict shadow:

```bash
.venv/bin/python scripts/evaluate/evaluate_00631l_compounding_regime_no_add_shadow.py \
  --mean-reversion-score-min 5 \
  --ar1-revert-max -0.15 \
  --mean-reversion-add-fraction 0.50 \
  --output results/00631l_compounding_regime_slowadd50_mrscore5_arneg15_20260715.json
```

CE-filter diagnostic:

```bash
.venv/bin/python scripts/evaluate/evaluate_00631l_compounding_regime_no_add_shadow.py \
  --mean-reversion-score-min 5 \
  --ar1-revert-max -0.15 \
  --mean-reversion-add-fraction 0.50 \
  --ce-filter ce20_negative \
  --output results/00631l_compounding_regime_slowadd50_mrscore5_arneg15_ce20neg_20260715.json
```

Best staged trend-reentry shadow:

```bash
.venv/bin/python scripts/evaluate/evaluate_00631l_compounding_regime_no_add_shadow.py \
  --mean-reversion-score-min 5 \
  --ar1-revert-max -0.15 \
  --baseline-add-fraction 0.40 \
  --mean-reversion-add-fraction 0.00 \
  --trend-persistent-add-fraction 1.00 \
  --output results/00631l_compounding_regime_staged_base40_mr0_trend100_20260715.json
```

Trend-only decomposition:

```bash
.venv/bin/python scripts/evaluate/evaluate_00631l_compounding_regime_no_add_shadow.py \
  --mean-reversion-score-min 5 \
  --ar1-revert-max -0.15 \
  --baseline-add-fraction 0.40 \
  --mean-reversion-add-fraction 0.40 \
  --trend-persistent-add-fraction 1.00 \
  --output results/00631l_compounding_regime_staged_base40_mr40_trend100_20260715.json
```

Mean-reversion-only decomposition:

```bash
.venv/bin/python scripts/evaluate/evaluate_00631l_compounding_regime_no_add_shadow.py \
  --mean-reversion-score-min 5 \
  --ar1-revert-max -0.15 \
  --baseline-add-fraction 0.40 \
  --mean-reversion-add-fraction 0.00 \
  --trend-persistent-add-fraction 0.40 \
  --output results/00631l_compounding_regime_staged_base40_mr0_trend40_20260715.json
```

Real execution replay:

```bash
.venv/bin/python scripts/evaluate/evaluate_00631l_compounding_execution_replay_shadow.py \
  --execution-plan report/group_a_plus/latest/execution_plan.json \
  --compounding-regime results/00631l_leveraged_compounding_regime_20260715.json \
  --output results/00631l_compounding_execution_replay_shadow_20260715.json
```

Aligned 2026-07-15 execution replay:

```bash
.venv/bin/python -m group_a_plus.operations.execution_plan \
  --workbook taiwan_stock_20260619.xlsx \
  --as-of 2026-07-15 \
  --cash-balance 0 \
  --compounding-regime results/00631l_leveraged_compounding_regime_20260715.json \
  --output results/group_a_plus_execution_plan_v2_20260715.json \
  --latest-pointer report/group_a_plus/latest/execution_plan.json
```

```bash
.venv/bin/python scripts/evaluate/evaluate_00631l_compounding_execution_replay_shadow.py \
  --execution-plan results/group_a_plus_execution_plan_v2_20260715.json \
  --compounding-regime results/00631l_leveraged_compounding_regime_20260715.json \
  --output results/00631l_compounding_execution_replay_shadow_20260715_aligned.json
```

Refresh 7/15 chip data and rerun:

```bash
python3 FinRL/data/stock_db.py \
  --add-institutional 0050.TW \
  --start 2026-07-15 \
  --end 2026-07-15
```

```bash
.venv/bin/python scripts/fetch/fetch_finmind_chip_data.py \
  --datasets day_trading \
  --tickers 0050.TW \
  --start 2026-07-15 \
  --end 2026-07-15
```

```bash
.venv/bin/python -m group_a_plus.operations.execution_plan \
  --workbook taiwan_stock_20260619.xlsx \
  --as-of 2026-07-15 \
  --cash-balance 0 \
  --compounding-regime results/00631l_leveraged_compounding_regime_20260715.json \
  --output results/group_a_plus_execution_plan_v2_20260715_after_chip_refresh.json \
  --latest-pointer report/group_a_plus/latest/execution_plan.json
```

```bash
.venv/bin/python scripts/evaluate/evaluate_00631l_compounding_execution_replay_shadow.py \
  --execution-plan results/group_a_plus_execution_plan_v2_20260715_after_chip_refresh.json \
  --compounding-regime results/00631l_leveraged_compounding_regime_20260715.json \
  --output results/00631l_compounding_execution_replay_shadow_20260715_after_chip_refresh.json
```

Turnover 60% shadow:

```bash
.venv/bin/python -m group_a_plus.operations.execution_plan \
  --workbook taiwan_stock_20260619.xlsx \
  --as-of 2026-07-15 \
  --cash-balance 0 \
  --compounding-regime results/00631l_leveraged_compounding_regime_20260715.json \
  --max-turnover-ratio 0.60 \
  --output results/group_a_plus_execution_plan_v2_20260715_after_chip_refresh_turnover60_shadow.json \
  --latest-pointer /tmp/group_a_plus_execution_plan_turnover60_shadow_latest.json
```

50% turnover-capped partial execution:

```bash
.venv/bin/python scripts/evaluate/evaluate_turnover_capped_execution_shadow.py \
  --execution-plan results/group_a_plus_execution_plan_v2_20260715_after_chip_refresh.json \
  --cap-ratio 0.50 \
  --priority-mode buys_first \
  --output results/turnover_capped_execution_shadow_20260715_buys_first.json
```

```bash
.venv/bin/python scripts/evaluate/evaluate_turnover_capped_execution_shadow.py \
  --execution-plan results/group_a_plus_execution_plan_v2_20260715_after_chip_refresh.json \
  --cap-ratio 0.50 \
  --priority-mode risk_first \
  --output results/turnover_capped_execution_shadow_20260715_risk_first.json
```

```bash
.venv/bin/python scripts/evaluate/evaluate_turnover_capped_execution_shadow.py \
  --execution-plan results/group_a_plus_execution_plan_v2_20260715_after_chip_refresh.json \
  --cap-ratio 0.50 \
  --priority-mode sell_first \
  --output results/turnover_capped_execution_shadow_20260715_sell_first.json
```

Staged rebalancing grid:

```bash
.venv/bin/python scripts/evaluate/sweep_00631l_compounding_rebalance_grid.py \
  --output results/00631l_compounding_rebalance_grid_20260715.json \
  --csv results/00631l_compounding_rebalance_grid_20260715.csv
```

Local tune around robust candidate:

```bash
.venv/bin/python scripts/evaluate/sweep_00631l_compounding_rebalance_grid.py \
  --base-add-fractions 0.30,0.35,0.40,0.45,0.50 \
  --mean-reversion-add-fractions 0.00,0.10 \
  --trend-add-fractions 0.90,1.00 \
  --output results/00631l_compounding_rebalance_grid_local_tune_20260715.json \
  --csv results/00631l_compounding_rebalance_grid_local_tune_20260715.csv
```

Trend-threshold mid-grid:

```bash
.venv/bin/python scripts/evaluate/sweep_00631l_compounding_trend_thresholds.py \
  --trend-score-min-values 3,4,5 \
  --ar1-trend-min-values 0.00,0.05 \
  --trend-persistence-min-values 0.55,0.60 \
  --reversal-speed-trend-max-values 0.45,0.50 \
  --output results/00631l_compounding_trend_threshold_grid_mid_20260715.json \
  --csv results/00631l_compounding_trend_threshold_grid_mid_20260715.csv
```

Trend-threshold edge-grid:

```bash
.venv/bin/python scripts/evaluate/sweep_00631l_compounding_trend_thresholds.py \
  --trend-score-min-values=3 \
  --ar1-trend-min-values=-0.05,0.00,0.05 \
  --trend-persistence-min-values=0.50,0.55 \
  --reversal-speed-trend-max-values=0.50,0.55 \
  --output results/00631l_compounding_trend_threshold_grid_edge_20260715.json \
  --csv results/00631l_compounding_trend_threshold_grid_edge_20260715.csv
```

Seven-window stress check:

```bash
SEVEN_WINDOWS="covid_2020,2020-01-02,2020-12-31,results/ncf_00631l_panel_latest_20260707.csv,stress_window;inflation_2022,2022-01-03,2022-12-30,results/ncf_00631l_panel_latest_20260707.csv,stress_window;live_2024_2026,2024-01-02,latest,results/ncf_00631l_panel_latest_20260707.csv,tuning_window;active_2025_2026,2025-01-02,latest,results/ncf_00631l_panel_latest_20260707.csv,tuning_window;2017_bull,2017-01-03,2017-12-29,results/ncf_00631l_panel_backfill_2017_2019_20260710.csv,out_of_sample;2018_correction,2018-01-02,2018-12-31,results/ncf_00631l_panel_backfill_2017_2019_20260710.csv,out_of_sample;2019_recovery,2019-01-02,2019-12-31,results/ncf_00631l_panel_backfill_2017_2019_20260710.csv,out_of_sample"
```

```bash
.venv/bin/python scripts/evaluate/evaluate_00631l_compounding_regime_no_add_shadow.py \
  --windows "$SEVEN_WINDOWS" \
  --mean-reversion-score-min 5 \
  --ar1-revert-max -0.15 \
  --baseline-add-fraction 0.40 \
  --mean-reversion-add-fraction 0.00 \
  --trend-persistent-add-fraction 1.00 \
  --output results/00631l_compounding_regime_staged_base40_mr0_trend100_7win_20260715.json
```

```bash
.venv/bin/python scripts/evaluate/evaluate_00631l_compounding_regime_no_add_shadow.py \
  --windows "$SEVEN_WINDOWS" \
  --mean-reversion-score-min 5 \
  --ar1-revert-max -0.15 \
  --baseline-add-fraction 0.40 \
  --mean-reversion-add-fraction 0.00 \
  --trend-persistent-add-fraction 1.00 \
  --trend-score-min 3 \
  --ar1-trend-min 0.00 \
  --trend-persistence-min 0.50 \
  --reversal-speed-trend-max 0.50 \
  --output results/00631l_compounding_regime_tunedtrend_score3_ar0_persist50_rev50_7win_20260715.json
```

```bash
.venv/bin/python scripts/evaluate/evaluate_00631l_compounding_regime_no_add_shadow.py \
  --windows "$SEVEN_WINDOWS" \
  --mean-reversion-score-min 5 \
  --ar1-revert-max -0.15 \
  --baseline-add-fraction 0.40 \
  --mean-reversion-add-fraction 0.00 \
  --trend-persistent-add-fraction 1.00 \
  --trend-score-min 3 \
  --ar1-trend-min -0.05 \
  --trend-persistence-min 0.50 \
  --reversal-speed-trend-max 0.55 \
  --output results/00631l_compounding_regime_tunedtrend_score3_arneg05_persist50_rev55_7win_20260715.json
```

CE20 weak-edge seven-window stress:

```bash
.venv/bin/python scripts/evaluate/evaluate_00631l_compounding_regime_no_add_shadow.py \
  --windows "$SEVEN_WINDOWS" \
  --mean-reversion-score-min 5 \
  --ar1-revert-max -0.15 \
  --baseline-add-fraction 0.40 \
  --mean-reversion-add-fraction 0.00 \
  --trend-persistent-add-fraction 1.00 \
  --trend-score-min 3 \
  --ar1-trend-min 0.00 \
  --trend-persistence-min 0.50 \
  --reversal-speed-trend-max 0.50 \
  --weak-trend-edge-gate ce20_negative \
  --weak-trend-add-fraction 0.90 \
  --output results/00631l_compounding_regime_tunedtrend_score3_ar0_persist50_rev50_ce20neg90_7win_20260716.json
```

```bash
.venv/bin/python scripts/evaluate/evaluate_00631l_compounding_regime_no_add_shadow.py \
  --windows "$SEVEN_WINDOWS" \
  --mean-reversion-score-min 5 \
  --ar1-revert-max -0.15 \
  --baseline-add-fraction 0.40 \
  --mean-reversion-add-fraction 0.00 \
  --trend-persistent-add-fraction 1.00 \
  --trend-score-min 3 \
  --ar1-trend-min 0.00 \
  --trend-persistence-min 0.50 \
  --reversal-speed-trend-max 0.50 \
  --weak-trend-edge-gate ce20_negative \
  --weak-trend-add-fraction 0.90 \
  --transaction-cost-bps 20 \
  --output results/00631l_compounding_regime_tunedtrend_score3_ar0_persist50_rev50_ce20neg90_7win_cost20bps_20260716.json
```

CE20 weak-edge comparison:

```bash
.venv/bin/python scripts/evaluate/build_a2120_variant_comparison.py \
  --output report/group_a_plus/shadow/a2120_variant_comparison_20260716.json
```

CE20 weak-edge A21.19 overlap audit:

```bash
.venv/bin/python scripts/evaluate/evaluate_a2120_ce20_variant_a2119_overlap.py \
  --output results/a2120_ce20_variant_a2119_overlap_audit_20260716.json
```

Promotion gate scorecard:

```bash
.venv/bin/python scripts/evaluate/build_a2120_letf_compounding_shadow_scorecard.py \
  --output report/group_a_plus/shadow/a2120_letf_compounding_shadow_scorecard_20260715.json
```

Rolling-window stability:

```bash
.venv/bin/python scripts/evaluate/evaluate_00631l_compounding_rolling_windows.py \
  --start 2020-01-02 \
  --end latest \
  --window-days 252 \
  --step-days 126 \
  --max-windows 12 \
  --transaction-cost-bps 0 \
  --output results/00631l_compounding_rolling_windows_252d_step126_12win_20260715.json \
  --csv results/00631l_compounding_rolling_windows_252d_step126_12win_20260715.csv
```

```bash
.venv/bin/python scripts/evaluate/evaluate_00631l_compounding_rolling_windows.py \
  --start 2020-01-02 \
  --end latest \
  --window-days 252 \
  --step-days 126 \
  --max-windows 12 \
  --transaction-cost-bps 20 \
  --output results/00631l_compounding_rolling_windows_252d_step126_12win_cost20bps_20260715.json \
  --csv results/00631l_compounding_rolling_windows_252d_step126_12win_cost20bps_20260715.csv
```

Strict rolling variants:

```bash
.venv/bin/python scripts/evaluate/evaluate_00631l_compounding_rolling_windows.py \
  --start 2020-01-02 \
  --end latest \
  --window-days 126 \
  --step-days 63 \
  --max-windows 24 \
  --transaction-cost-bps 20 \
  --output results/00631l_compounding_rolling_windows_126d_step63_24win_cost20bps_20260715.json \
  --csv results/00631l_compounding_rolling_windows_126d_step63_24win_cost20bps_20260715.csv
```

```bash
.venv/bin/python scripts/evaluate/evaluate_00631l_compounding_rolling_windows.py \
  --start 2020-01-02 \
  --end latest \
  --window-days 189 \
  --step-days 63 \
  --max-windows 24 \
  --transaction-cost-bps 20 \
  --output results/00631l_compounding_rolling_windows_189d_step63_24win_cost20bps_20260715.json \
  --csv results/00631l_compounding_rolling_windows_189d_step63_24win_cost20bps_20260715.csv
```

```bash
.venv/bin/python scripts/evaluate/evaluate_00631l_compounding_rolling_windows.py \
  --start 2020-01-02 \
  --end latest \
  --window-days 252 \
  --step-days 63 \
  --max-windows 24 \
  --transaction-cost-bps 20 \
  --output results/00631l_compounding_rolling_windows_252d_step63_24win_cost20bps_20260715.json \
  --csv results/00631l_compounding_rolling_windows_252d_step63_24win_cost20bps_20260715.csv
```

Risk-sensitive trend90 variant:

```bash
.venv/bin/python scripts/evaluate/evaluate_00631l_compounding_rolling_windows.py \
  --start 2020-01-02 \
  --end latest \
  --window-days 252 \
  --step-days 63 \
  --max-windows 24 \
  --transaction-cost-bps 20 \
  --trend-persistent-add-fraction 0.90 \
  --output results/00631l_compounding_rolling_windows_252d_step63_24win_cost20bps_trend90_20260715.json \
  --csv results/00631l_compounding_rolling_windows_252d_step63_24win_cost20bps_trend90_20260715.csv
```

Minimum-edge CE20 weak trend variant:

```bash
.venv/bin/python scripts/evaluate/evaluate_00631l_compounding_rolling_windows.py \
  --start 2020-01-02 \
  --end latest \
  --window-days 126 \
  --step-days 63 \
  --max-windows 24 \
  --transaction-cost-bps 20 \
  --weak-trend-edge-gate ce20_negative \
  --weak-trend-add-fraction 0.90 \
  --output results/00631l_compounding_rolling_windows_126d_step63_24win_cost20bps_edge_ce20neg90_20260715.json \
  --csv results/00631l_compounding_rolling_windows_126d_step63_24win_cost20bps_edge_ce20neg90_20260715.csv
```

```bash
.venv/bin/python scripts/evaluate/evaluate_00631l_compounding_rolling_windows.py \
  --start 2020-01-02 \
  --end latest \
  --window-days 189 \
  --step-days 63 \
  --max-windows 24 \
  --transaction-cost-bps 20 \
  --weak-trend-edge-gate ce20_negative \
  --weak-trend-add-fraction 0.90 \
  --output results/00631l_compounding_rolling_windows_189d_step63_24win_cost20bps_edge_ce20neg90_20260715.json \
  --csv results/00631l_compounding_rolling_windows_189d_step63_24win_cost20bps_edge_ce20neg90_20260715.csv
```

```bash
.venv/bin/python scripts/evaluate/evaluate_00631l_compounding_rolling_windows.py \
  --start 2020-01-02 \
  --end latest \
  --window-days 252 \
  --step-days 63 \
  --max-windows 24 \
  --transaction-cost-bps 20 \
  --weak-trend-edge-gate ce20_negative \
  --weak-trend-add-fraction 0.90 \
  --output results/00631l_compounding_rolling_windows_252d_step63_24win_cost20bps_edge_ce20neg90_20260715.json \
  --csv results/00631l_compounding_rolling_windows_252d_step63_24win_cost20bps_edge_ce20neg90_20260715.csv
```

Combined A21.19/A21.20 policy:

```bash
.venv/bin/python scripts/evaluate/evaluate_a2119_a2120_combined_policy_shadow.py \
  --a2119-report results/a2119_reentry_regret_gate_7win_20260715.json \
  --a2120-latest report/group_a_plus/latest/a2120_letf_compounding_shadow.json \
  --output report/group_a_plus/shadow/a2119_a2120_combined_policy_shadow_20260715.json
```

Daily shadow pipeline:

```bash
.venv/bin/python scripts/run/run_a2120_daily_shadow_pipeline.py \
  --date-stamp 20260715 \
  --execution-plan results/group_a_plus_execution_plan_v2_20260715_after_chip_refresh.json \
  --a2119-report results/a2119_reentry_regret_gate_7win_20260715.json
```

## Verification

```text
.venv/bin/python -m pytest -q \
  tests/test_evaluate_a2119_a2120_combined_policy_shadow.py \
  tests/test_run_a2120_daily_shadow_pipeline.py \
  tests/test_build_a2120_letf_compounding_shadow_scorecard.py \
  tests/test_evaluate_00631l_compounding_rolling_windows.py \
  tests/test_sweep_00631l_compounding_trend_thresholds.py \
  tests/test_evaluate_turnover_capped_execution_shadow.py \
  tests/test_sweep_00631l_compounding_rebalance_grid.py \
  tests/test_evaluate_00631l_compounding_execution_replay_shadow.py \
  tests/test_evaluate_00631l_compounding_regime_no_add_shadow.py \
  tests/test_leveraged_compounding_regime.py

Result: targeted turnover/replay tests passed
```

Latest targeted result:

```text
.venv/bin/python -m pytest -q \
  tests/test_build_a2120_letf_compounding_shadow_scorecard.py \
  tests/test_evaluate_00631l_compounding_rolling_windows.py

Result: 6 passed
```

```text
.venv/bin/python -m py_compile \
  group_a_plus/integrations/leveraged_compounding_regime.py \
  scripts/run/run_a2120_daily_shadow_pipeline.py \
  scripts/evaluate/evaluate_a2119_a2120_combined_policy_shadow.py \
  scripts/evaluate/build_a2120_letf_compounding_shadow_scorecard.py \
  scripts/evaluate/evaluate_00631l_compounding_rolling_windows.py \
  scripts/evaluate/evaluate_turnover_capped_execution_shadow.py \
  scripts/evaluate/sweep_00631l_compounding_rebalance_grid.py \
  scripts/evaluate/evaluate_00631l_compounding_execution_replay_shadow.py \
  scripts/evaluate/evaluate_00631l_compounding_regime_no_add_shadow.py \
  scripts/evaluate/evaluate_00631l_leveraged_compounding_regime.py

Result: passed
```
