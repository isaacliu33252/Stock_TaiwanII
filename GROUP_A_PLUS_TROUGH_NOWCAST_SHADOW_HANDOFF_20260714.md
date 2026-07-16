# GroupA+ Trough Nowcast Shadow Audit - 2026-07-14

## Conclusion

Do **not** promote `FULL_REENTRY` as an automatic full-speed re-entry
accelerator.

After the v7 tightening pass, the safer policy is:

- `CAPITULATION_WARNING`: report only.
- `PARTIAL_REENTRY`: diagnostic re-entry watch; may allow staged-buy
  acceleration to 0.7, still subject to all pre-trade guards.
- `FULL_REENTRY`: disabled for now. Full-reentry candidates are demoted back
  to `CAPITULATION_WARNING` and surfaced in `full_reentry_checks`.

Keep the live integration diagnostic-first. The execution-plan hook may use
`PARTIAL_REENTRY` only for buy-staging speed, not target-weight changes.

## Files

Implemented:

- `group_a_plus/integrations/trough_nowcast.py`
- `scripts/evaluate/evaluate_group_a_plus_trough_nowcast_shadow.py`
- `tests/test_group_a_plus_trough_nowcast.py`
- `tests/test_evaluate_group_a_plus_trough_nowcast_shadow.py`

Updated live diagnostics / execution planning:

- `group_a_plus/operations/daily_signal.py`
  - adds `trough_nowcast`
  - emits `market_trough_nowcast` alert when state is not `NO_TROUGH`
- `group_a_plus/operations/execution_plan.py`
  - reads `trough_nowcast`
  - only changes buy-staging fraction for `PARTIAL_REENTRY` / `FULL_REENTRY`
  - does not change target weights
  - adds `trough_high_vol_override_watch`, a research-only diagnostic when
    high-vol guard blocks a 00631L buy that matches the trough/no-lower-low
    shadow candidate; it has no live execution effect

Result:

- `results/group_a_plus_trough_nowcast_shadow_20260714.json`
- `results/group_a_plus_trough_nowcast_shadow_v2_20260714.json`
- `results/group_a_plus_trough_nowcast_shadow_v3_20260714.json`
- `results/group_a_plus_trough_nowcast_shadow_v4_20260714.json`
- `results/group_a_plus_trough_nowcast_shadow_v5_20260714.json`
- `results/group_a_plus_trough_nowcast_shadow_v6_20260714.json`
- `results/group_a_plus_trough_nowcast_shadow_v7_20260714.json`
- `results/group_a_plus_trough_nowcast_param_sweep_20260714.json`
- `results/group_a_plus_trough_nowcast_buy_attempt_alignment_20260714.json`
- `results/group_a_plus_trough_nowcast_vol_gate_override_shadow_20260714.json`
- `results/group_a_plus_trough_nowcast_vol_gate_override_confirmation_shadow_20260714.json`

`v7` is the current live-code policy.

## v7 Tightening

Changes versus the initial version:

- `PARTIAL_REENTRY` now requires:
  - capitulation score >= 3,
  - re-entry score >= 4,
  - local price confirmation: 0050 rebound plus GroupA breadth,
  - and at least one of risk-unwind confirmation or cross-market confirmation.
- `FULL_REENTRY` is disabled:
  - candidates are still recorded in `full_reentry_checks`,
  - but they are not emitted as `FULL_REENTRY`,
  - and they are not promoted to `PARTIAL_REENTRY`.

Aggregate improvement:

| Version | PARTIAL+FULL days | False re-entry events |
|---|---:|---:|
| v1 | 93 | 47 |
| v3 | 59 | 29 |
| v6 | 40 | 17 |
| v7 | 39 | 16 |

The v7 change came from `evaluate_group_a_plus_trough_nowcast_param_sweep.py`.
The practical best candidate kept v6's thresholds except for
`reentry_score_min: 3 -> 4`:

```json
{
  "cap_min": 3,
  "reentry_min": 4,
  "rebound_0050_min": 0.02,
  "rebound_00631l_min": 0.04,
  "breadth_min": 0.5,
  "risk_unwind_chg_max": -0.5
}
```

## Shadow Results

### active_2025_2026 v7

State counts:

- `NO_TROUGH`: 296
- `CAPITULATION_WARNING`: 60
- `PARTIAL_REENTRY`: 10
- `FULL_REENTRY`: 0

Forward 5d mean:

- `PARTIAL_REENTRY`: 00631L +2.56%

False re-entry:

- `PARTIAL_REENTRY`: 50.0% 10d forward max drawdown worse than -3%
- false re-entry event count: 5

### covid_2020 v7

State counts:

- `NO_TROUGH`: 185
- `CAPITULATION_WARNING`: 52
- `PARTIAL_REENTRY`: 8
- `FULL_REENTRY`: 0

Forward 5d mean:

- `PARTIAL_REENTRY`: 00631L +2.07%

False re-entry event count: 3

### inflation_2022 v7

State counts:

- `NO_TROUGH`: 98
- `CAPITULATION_WARNING`: 127
- `PARTIAL_REENTRY`: 21
- `FULL_REENTRY`: 0

Forward 5d mean:

- `PARTIAL_REENTRY`: 00631L +3.10%

False re-entry event count: 8

### 2018_correction v7

State counts:

- `NO_TROUGH`: 237
- `CAPITULATION_WARNING`: 8
- `PARTIAL_REENTRY`: 0
- `FULL_REENTRY`: 0

## Execution Counterfactual

The simplified staging counterfactual compares:

- baseline buy staging: 0.4
- `PARTIAL_REENTRY`: 0.7
- `FULL_REENTRY`: 1.0

Across all tested windows through v7:

- accelerated event count: 0
- final value delta: 0
- Sharpe delta: 0
- max drawdown delta: 0

Interpretation:

The nowcast states did not align with model regime-transition buy events in
this first approximation. The diagnostic may still be useful for manual
monitoring, but it has not yet demonstrated live execution value.

## Buy-Attempt Alignment

`scripts/evaluate/evaluate_group_a_plus_trough_nowcast_buy_attempt_alignment.py`
adds a more execution-like replay:

- daily target-vs-current buy attempts, not only regime transitions;
- staged deferred buys, so missed partial fills can create later buy attempts;
- volatility high-vol no-add guard for 00631L;
- extreme-risk no-new-risk-add proxy;
- compounding guard marked unavailable, not guessed historically.

Result totals:

| Metric | Count |
|---|---:|
| buy attempt days | 348 |
| PARTIAL_REENTRY days | 39 |
| PARTIAL_REENTRY buy-attempt days | 7 |
| allowed fast re-entry days | 4 |
| blocked fast re-entry days | 3 |
| blocked by volatility gate | 3 |
| blocked by extreme risk | 0 |
| missed rebound without PARTIAL | 117 |
| missed rebound blocked by guard | 2 |

Window detail:

| Window | PARTIAL days | PARTIAL buy attempts | Allowed fast | Blocked fast |
|---|---:|---:|---:|---:|
| active_2025_2026 | 10 | 3 | 0 | 3 |
| covid_2020 | 8 | 1 | 1 | 0 |
| inflation_2022 | 21 | 3 | 3 | 0 |
| 2018_correction | 0 | 0 | 0 | 0 |

Important events:

- 2020-03-23: `PARTIAL_REENTRY`, defensive regime, neutral volatility gate,
  allowed 0050 staged buy; 00631L forward 5d +19.29%.
- 2022-07-18: `PARTIAL_REENTRY`, defensive regime, neutral volatility gate,
  allowed 0050 staged buy; 00631L forward 5d +4.37%.
- 2022-11-10: `PARTIAL_REENTRY`, defensive regime, neutral volatility gate,
  allowed 0050 staged buy; 00631L forward 5d +17.40%.
- 2026-03-25 and 2026-06-29: `PARTIAL_REENTRY` aligned with buy attempts but
  high-volatility gate blocked 00631L adds; both later had positive 00631L
  forward 5d, so these are "guard-blocked missed rebound" cases to study,
  not a reason to bypass the guard yet.

Interpretation:

`PARTIAL_REENTRY` is not a broad daily trading signal. It only overlaps with
actual execution-layer buy attempts in 7/39 PARTIAL days. That is acceptable:
the module should stay diagnostic and execution-gated. The practical value is
in a small number of staged-buy days after crashes, especially 2020 and 2022.

## Volatility-Gate Override Shadow

`scripts/evaluate/evaluate_group_a_plus_trough_nowcast_vol_gate_override_shadow.py`
tests a narrow research-only exception:

- `PARTIAL_REENTRY`
- high-volatility defensive gate
- attempted 00631L buy
- no extreme-risk block

Policies tested:

| Policy | Override of attempted 00631L buy |
|---|---:|
| `no_override` | 0% |
| `micro_override_25pct` | 25% |
| `small_override_50pct` | 50% |

Totals:

| Policy | Eligible days | Final value delta sum | Sharpe delta sum | Max DD delta sum |
|---|---:|---:|---:|---:|
| `no_override` | 2 | 0.00 | 0.000000 | 0.000000 |
| `micro_override_25pct` | 2 | 634.66 | 0.000365 | 0.000000 |
| `small_override_50pct` | 2 | 1205.17 | 0.000610 | 0.000000 |

Eligible events:

| Date | Window | Attempted 00631L buy weight | 00631L fwd 5d | 00631L fwd 10d |
|---|---|---:|---:|---:|
| 2026-03-25 | active_2025_2026 | 1.0545% | +4.25% | +17.66% |
| 2026-06-29 | active_2025_2026 | 0.5417% | +6.81% | n/a |

Interpretation:

The override recovered two high-vol guard-blocked rebound cases without
worsening max drawdown in this replay, but the sample is too small and only
appears in the tuning window. Keep it out of live execution. If promoted later,
the defensible first version would be a tiny cap such as 25% of the attempted
00631L buy, still bounded by the original target and disabled under
extreme-risk.

### Confirmation Variant

The confirmation shadow adds three filters:

| Confirmation mode | Eligible days | 25% final value delta | Max DD delta |
|---|---:|---:|---:|
| none | 2 | 634.66 | 0.000000 |
| second `PARTIAL_REENTRY` | 0 | 0.00 | 0.000000 |
| no fresh 0050 lower-low versus prior 3 trading days | 2 | 634.66 | 0.000000 |
| second partial OR no fresh lower-low | 2 | 634.66 | 0.000000 |

Event diagnostics:

| Date | Previous trough state | 0050 close | Prior 3d 0050 low | Confirmation |
|---|---|---:|---:|---|
| 2026-03-25 | `NO_TROUGH` | 76.20 | 74.25 | no fresh lower-low |
| 2026-06-29 | `CAPITULATION_WARNING` | 104.45 | 103.10 | no fresh lower-low |

Interpretation:

Waiting for a second consecutive `PARTIAL_REENTRY` is too strict for these
fast rebound cases; it eliminates all high-vol override candidates. The
least-bad research candidate is:

- `PARTIAL_REENTRY`
- high-volatility defensive gate
- attempted 00631L buy above the minimum size
- no extreme-risk block
- no fresh 0050 lower-low versus the prior 3 trading days
- override capped at 25% of the attempted 00631L buy

This still should not be live-promoted from a two-event tuning-window sample.

Live diagnostic follow-up:

- `trough_nowcast.inputs.market_proxy` now includes:
  - `latest_0050_close`
  - `prior_0050_3d_low`
  - `no_fresh_0050_lower_low_3d`
- `execution_plan` now emits `trough_high_vol_override_watch`.
- The watch is `research_only: true` and `live_execution_effect: none`.
- It computes the hypothetical 25% 00631L share count only for logging and
  review; `target_shares`, `trades`, and all pre-trade guards remain unchanged.

Further work before promotion:

1. Add a persistence audit: second consecutive `PARTIAL_REENTRY` versus
   first-day signal.
2. Re-run the override shadow after more 2026+ data accumulates. Do not bypass
   the high-vol guard in live execution yet.

Current safe policy:

- `CAPITULATION_WARNING`: report only
- `PARTIAL_REENTRY`: manual review / possible staged-buy acceleration watch
- `FULL_REENTRY`: disabled

## Engineering Handoff

### Current Live Behavior

The live path is intentionally conservative:

1. `daily_signal.build_daily_signal()` computes `trough_nowcast` after
   `market_state`, `signal_alignment`, and `ncf_live_overlay` are available.
2. `daily_signal` stores the full nowcast payload in the live signal.
3. If the state is not `NO_TROUGH`, `daily_signal` emits a
   `market_trough_nowcast` alert.
4. `execution_plan.build_execution_plan()` reads the live signal:
   - `PARTIAL_REENTRY` can raise `max_initial_buy_fraction` from the default
     0.4 to the nowcast recommendation of 0.7.
   - `FULL_REENTRY` is still structurally supported by the staging helper but
     is disabled by the nowcast policy and should not appear in live output.
   - All pre-trade guards still run after staging.
   - High-volatility, extreme-risk, and compounding guards still decide the
     final executable target shares.
5. `trough_high_vol_override_watch` is diagnostic only:
   - no effect on `target_shares`;
   - no effect on `trades`;
   - no effect on guard decisions;
   - no effect on `execution_allowed`.

### Important Code Paths

Core nowcast:

- `group_a_plus/integrations/trough_nowcast.py`
  - `compute_trough_nowcast(...)`
  - `_market_proxy_features(...)`
  - `_multisource_snapshot(...)`
  - `_cross_market_rebound(...)`

Live signal integration:

- `group_a_plus/operations/daily_signal.py`
  - imports `compute_trough_nowcast`
  - calls it in `build_daily_signal`
  - includes `trough_nowcast` in the output payload
  - creates `market_trough_nowcast` alert in `_build_signal_alerts`

Execution plan integration:

- `group_a_plus/operations/execution_plan.py`
  - `_trough_nowcast_buy_fraction(...)`
  - `_trough_high_vol_override_watch(...)`
  - `build_execution_plan(...)`

Shadow tools:

- `scripts/evaluate/evaluate_group_a_plus_trough_nowcast_shadow.py`
- `scripts/evaluate/evaluate_group_a_plus_trough_nowcast_param_sweep.py`
- `scripts/evaluate/evaluate_group_a_plus_trough_nowcast_buy_attempt_alignment.py`
- `scripts/evaluate/evaluate_group_a_plus_trough_nowcast_vol_gate_override_shadow.py`

Tests:

- `tests/test_group_a_plus_trough_nowcast.py`
- `tests/test_evaluate_group_a_plus_trough_nowcast_shadow.py`
- `tests/test_evaluate_group_a_plus_trough_nowcast_buy_attempt_alignment.py`
- `tests/test_evaluate_group_a_plus_trough_nowcast_vol_gate_override_shadow.py`
- `tests/test_group_a_plus_execution_plan_v2.py`
- `tests/test_group_a_plus_daily_signal_v2.py`

### Data And Feature Notes

The nowcast is a Taiwan adaptation of a rare-event market-trough nowcast. It
uses available proxies rather than assuming the U.S. paper's exact features are
portable.

Current live/shadow proxies include:

- 0050 / 00631L price rebound from recent lows;
- GroupA breadth;
- 0050 volume and Amihud-style illiquidity stress;
- TXO put/call and foreign derivative-positioning proxies from multisource
  crash-risk features;
- market margin stress / forced repayment proxies;
- SOXX, TSM ADR, 2330, and USD/TWD cross-market rebound / unwind features;
- A21.18 / H20 warning context and market-state risk context.

The high-vol override watch additionally depends on:

- `trough_nowcast.state == PARTIAL_REENTRY`;
- the volatility pre-trade guard blocking a 00631L buy;
- no extreme-risk guard blocking 00631L;
- no compounding guard blocking 00631L;
- `trough_nowcast.inputs.market_proxy.no_fresh_0050_lower_low_3d == true`.

### Current Parameter Choices

Live nowcast v7:

- `PARTIAL_REENTRY`:
  - capitulation score >= 3;
  - re-entry score >= 4;
  - local price confirmation;
  - risk-unwind or cross-market confirmation;
  - not a disabled full-reentry candidate.
- `CAPITULATION_WARNING`:
  - warning context is active;
  - capitulation score >= 2;
  - partial/full re-entry conditions not met.
- `FULL_REENTRY`:
  - disabled in live policy;
  - candidates are reported in `full_reentry_checks` only.

Execution staging:

- default initial buy fraction: 0.4;
- `PARTIAL_REENTRY` recommendation: 0.7;
- `FULL_REENTRY` map value: 1.0, but not emitted by current policy.

High-vol watch:

- hypothetical override cap: 25% of the blocked 00631L buy;
- research-only;
- not executable by code.

### Commands To Reproduce

Run the relevant tests:

```bash
pytest -q \
  tests/test_group_a_plus_trough_nowcast.py \
  tests/test_evaluate_group_a_plus_trough_nowcast_shadow.py \
  tests/test_evaluate_group_a_plus_trough_nowcast_buy_attempt_alignment.py \
  tests/test_evaluate_group_a_plus_trough_nowcast_vol_gate_override_shadow.py \
  tests/test_group_a_plus_execution_plan_v2.py \
  tests/test_group_a_plus_daily_signal_v2.py
```

Last run result on 2026-07-14:

```text
75 passed in 11.41s
```

Syntax check:

```bash
python3 -m py_compile \
  group_a_plus/integrations/trough_nowcast.py \
  group_a_plus/operations/execution_plan.py \
  group_a_plus/operations/daily_signal.py \
  scripts/evaluate/evaluate_group_a_plus_trough_nowcast_shadow.py \
  scripts/evaluate/evaluate_group_a_plus_trough_nowcast_param_sweep.py \
  scripts/evaluate/evaluate_group_a_plus_trough_nowcast_buy_attempt_alignment.py \
  scripts/evaluate/evaluate_group_a_plus_trough_nowcast_vol_gate_override_shadow.py
```

Re-run shadow:

```bash
python3 scripts/evaluate/evaluate_group_a_plus_trough_nowcast_shadow.py \
  --output results/group_a_plus_trough_nowcast_shadow_v7_20260714.json
```

Re-run parameter sweep:

```bash
python3 scripts/evaluate/evaluate_group_a_plus_trough_nowcast_param_sweep.py \
  --output results/group_a_plus_trough_nowcast_param_sweep_20260714.json
```

Re-run buy-attempt alignment:

```bash
python3 scripts/evaluate/evaluate_group_a_plus_trough_nowcast_buy_attempt_alignment.py \
  --output results/group_a_plus_trough_nowcast_buy_attempt_alignment_20260714.json
```

Re-run high-vol override confirmation shadow:

```bash
python3 scripts/evaluate/evaluate_group_a_plus_trough_nowcast_vol_gate_override_shadow.py \
  --output results/group_a_plus_trough_nowcast_vol_gate_override_confirmation_shadow_20260714.json
```

### Promotion Rules

Do not promote `FULL_REENTRY` unless all of the following are true:

- false re-entry rate is materially lower across stress windows;
- improvement holds outside 2025-2026 tuning data;
- `FULL_REENTRY` adds value in an execution-like replay, not only in forward
  return buckets;
- max drawdown and tail metrics do not deteriorate.

Do not promote high-vol override unless all of the following are true:

- more than two eligible events exist;
- eligible events include out-of-sample windows, not only active 2025-2026;
- 25% cap remains positive after transaction-cost and guard-aware replay;
- no deterioration in max drawdown, VaR/ETL, or worst 20d return;
- extreme-risk and compounding guards still have absolute priority.

The only currently acceptable live behavior is:

- diagnostic alerting;
- staged-buy acceleration for `PARTIAL_REENTRY`;
- research-only high-vol override watch.

### Known Limitations

- Historical TXO / option-skew proxies are imperfect and depend on existing
  multisource feature coverage.
- The high-vol override candidate has only two eligible events.
- `second_partial` confirmation was too slow in the current sample and removed
  all high-vol override events.
- `no_fresh_0050_lower_low_3d` preserved the two candidates, but this is still
  not enough sample size for live promotion.
- The buy-attempt alignment replay approximates execution behavior; it is more
  realistic than regime-transition-only replay, but still not a broker-level
  fill simulator.

### Next Engineer Checklist

1. Keep the current live policy unchanged unless new shadow evidence is
   materially stronger.
2. Inspect `trough_high_vol_override_watch` in future execution-plan outputs
   and collect event-level evidence.
3. Re-run the override shadow after more 2026+ data is available.
4. If new eligible events accumulate, compare:
   - no override;
   - 25% cap with no fresh lower-low;
   - 25% cap with stricter confirmation;
   - no promotion.
5. Only consider live promotion if the guard-aware replay improves execution
   value across multiple market windows without worsening tail risk.

## Live Verification - 2026-07-14

After refreshing data for `2026-07-14`, the live diagnostic path was exercised.

Refresh command:

```bash
.venv/bin/python scripts/run/run_ncf_daily_pipeline.py \
  --date-stamp 20260714 \
  --only-refresh \
  --force-refresh \
  --refresh-target-date 2026-07-14 \
  --chip-end 2026-07-14 \
  --checklist-external-end 2026-07-15
```

Refresh outputs:

- `results/ncf_daily_pipeline_20260714.json`
- `results/data_refresh_20260714.json`
- `results/ohlcv_freshness_20260714.json`

Freshness result:

- GroupA/GroupB OHLCV: target date `2026-07-14`, status OK.
- Main chip tables: updated to `2026-07-14`.
- TAIFEX futures/options: latest available date `2026-07-13`.
- Cross-market: `SOXX`, `TSM`, `TWD=X`, `^TWII`, `^VIX`, `QQQ`
  updated to `2026-07-14`; `2330.TW` external yfinance at `2026-07-13`
  and still freshness OK.

Ops-health note:

- `ops_health` reported `system_resources` error because disk free ratio was
  below 2%.
- This did not block refresh and did not invalidate data freshness.

Live signal command:

```bash
.venv/bin/python -m group_a_plus.operations.daily_signal \
  --as-of 2026-07-14 \
  --portfolio-value 1000000 \
  --max-business-stale-days 3 \
  --output results/group_a_plus_live_signal_v2_20260714_after_refresh.json \
  --latest-pointer report/group_a_plus/latest/live_signal.json
```

Live signal result:

- output success: true
- `actual_data_date`: `2026-07-14`
- `execution_regime`: `golden1`
- `execution_allowed`: false
- `trough_nowcast.state`: `CAPITULATION_WARNING`
- `capitulation_score`: 2
- `reentry_confirmation_score`: 1
- `recommended_execution_staging_fraction`: null
- `no_fresh_0050_lower_low_3d`: false
- `market_trough_nowcast` alert: present
- volatility gate: `high_vol_defensive`

Implementation note:

The first live-signal attempt found a real bug in
`trough_nowcast._zscore_latest`: pandas `pd.NA` values in the Amihud series
could fail `astype(float)`. Fixed by using `pd.to_numeric(...,
errors="coerce")` before `dropna()`.

Execution plan command:

```bash
.venv/bin/python -m group_a_plus.operations.execution_plan \
  --as-of 2026-07-14 \
  --cash-balance 0 \
  --max-business-stale-days 3 \
  --output results/group_a_plus_execution_plan_v2_20260714_after_refresh.json \
  --latest-pointer report/group_a_plus/latest/execution_plan.json
```

Execution plan result:

- output success: true
- `actual_data_date`: `2026-07-14`
- `planning_status`: `manual_review_required`
- `execution_allowed`: false
- `trough_reentry_staging.state`: `CAPITULATION_WARNING`
- `trough_reentry_staging.applied`: false
- `effective_max_initial_buy_fraction`: 0.4
- volatility pre-trade guard: blocked 560 shares of 00631L add
- risk-add guard: inactive
- compounding guard: unavailable
- `trough_high_vol_override_watch.status`: inactive
- `trough_high_vol_override_watch.blocked_00631l_buy_shares`: 560
- `trough_high_vol_override_watch.research_candidate_00631l_shares`: 0
- inactive reason: trough state was only `CAPITULATION_WARNING`, and 0050
  had a fresh lower-low versus the prior 3 trading days
  (`latest_0050_close=104.40`, `prior_0050_3d_low=105.80`).

This is the desired behavior: the high-vol watch is observable, but it does
not activate unless the stricter research candidate conditions are met.

Post-fix verification:

```text
47 passed: tests/test_group_a_plus_trough_nowcast.py and
tests/test_group_a_plus_daily_signal_v2.py
```

The broader trough/execution test set had previously passed:

```text
75 passed
```

## Full Daily Pipeline - 2026-07-14

After the refresh-only and direct live-signal checks, the full daily pipeline
was run with refresh skipped:

```bash
.venv/bin/python scripts/run/run_ncf_daily_pipeline.py \
  --date-stamp 20260714 \
  --skip-refresh \
  --chip-end 2026-07-14 \
  --checklist-external-end 2026-07-15
```

Pipeline result:

- exit code: 0
- manifest: `results/ncf_daily_pipeline_20260714.json`
- manifest mode: `full`
- pipeline health in ops report: `ok`

Key generated outputs:

- `results/ncf_00631l_latest_20260714.json`
- `results/ncf_00632r_latest_20260714.json`
- `results/ncf_2330_latest_20260714.json`
- `results/ncf_00631l_panel_latest_20260714.csv`
- `results/ncf_00632r_panel_latest_20260714.csv`
- `results/ncf_2330_panel_latest_20260714.csv`
- `results/ncf_panel_manifest_20260714.json`
- `results/ncf_panel_drift_active_vs_20260714.json`
- `results/ncf_panel_coverage_20260714.json`
- `results/group_a_plus_factor_lens_20260714.json`
- `results/group_a_plus_live_signal_v2_20260714.json`
- `results/00631l_leveraged_compounding_regime_20260714.json`
- `results/group_a_plus_daily_status_20260714.json`
- `results/group_a_plus_promotion_gate_20260714.json`
- `results/ncf_2330_checklist_20260714.json`

Latest pointers updated:

- `report/group_a_plus/latest/live_signal.json`
- `report/group_a_plus/latest/execution_plan.json`
- `report/group_a_plus/latest/daily_status.json`
- `report/group_a_plus/latest/commentary_20260714.json`
- `report/group_a_plus/latest/watchlist_news.json`
- `report/group_a_plus/latest/signal_alignment.json`
- `report/group_a_plus/latest/alert_state.json`
- `report/group_a_plus/latest/ops_health.json`

Pipeline summary:

- 00631L signal: `UP`, `prob_up=0.55`, `date=2026-07-14`,
  `data_freshness_status=degraded_stale`.
- 00632R signal: `UP`, `prob_up=0.5478`, `date=2026-07-14`,
  `data_freshness_status=degraded_stale`.
- Signal alignment: `wide_divergence`, dominant direction `bullish`,
  penalty `0.25` in pipeline log.
- Alert state: emitted 10, suppressed 0, resolved 0.
- Daily status: `overall_status=block`, `check_date=2026-07-14`.

Live trough state after full pipeline:

- `actual_data_date`: `2026-07-14`
- `execution_regime`: `golden1`
- `execution_allowed`: false
- `trough_nowcast.state`: `CAPITULATION_WARNING`
- `capitulation_score`: 2
- `reentry_confirmation_score`: 1
- `recommended_execution_staging_fraction`: null
- `no_fresh_0050_lower_low_3d`: false
- `market_trough_nowcast` alert: present

Execution plan trough/watch after full pipeline:

- `actual_data_date`: `2026-07-14`
- `planning_status`: `manual_review_required`
- `execution_allowed`: false
- `trough_reentry_staging.state`: `CAPITULATION_WARNING`
- `trough_reentry_staging.applied`: false
- `effective_max_initial_buy_fraction`: 0.4
- volatility guard: blocked 560 shares of 00631L add
- `trough_high_vol_override_watch.status`: inactive
- `trough_high_vol_override_watch.blocked_00631l_buy_shares`: 560
- `trough_high_vol_override_watch.research_candidate_00631l_shares`: 0
- inactive reason: only `CAPITULATION_WARNING` and fresh 0050 lower-low
  (`latest_0050_close=104.40`, `prior_0050_3d_low=105.80`).

Non-fatal issues observed:

- `ops_health.status=error` because disk free ratio was about 1.33%;
  `pipeline_health.status=ok`.
- `crash-risk-alert` step originally logged a non-fatal failure:
  `'Namespace' object has no attribute 'db'`.
  This did not stop the pipeline and did not affect trough nowcast or execution
  plan output.
- Follow-up fix: `scripts/run/run_ncf_daily_pipeline.py` now resolves the DB
  path through `_pipeline_db_path(args)`, falling back to
  `backtest_group_a_plus_switch_policy.DB_PATH` when `args.db` is absent.
- After the fix, `scripts/run/build_00631l_crash_risk_alert.py --as-of latest`
  succeeded and wrote `report/group_a_plus/latest/crash_risk_alert.json`.
- Crash-risk alert result:
  - `as_of`: `2026-07-14`
  - `watch_level`: `watch`
  - `alert_active`: false
  - `category_score`: 1
  - active family: `cross_market_shock`
  - freshness: OK
- Alert-state update then resolved the stale crash-risk snapshot alert:
  `00631l_crash_risk_snapshot_stale`.

Post-pipeline verification:

```text
75 passed
py_compile passed
```

Crash-risk pipeline fix verification:

```text
30 passed: tests/test_run_ncf_daily_pipeline.py and
tests/test_build_00631l_crash_risk_alert.py
```
