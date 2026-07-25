# Detailed Handoff: 1610.09404 LETF Tracking Error for GroupA+（2026-07-19）

## Scope

- Source PDF: `C:\Users\isaac\Downloads\1610.09404.pdf`
- Paper title: `Understanding the Tracking Errors of Commodity Leveraged ETFs`
- Authors: Kevin Guo, Tim Leung
- arXiv: `1610.09404v1`
- Paper date: 2016-10-28
- GroupA+ decision context: 2026-07-20 estimate, `Golden1_0531`
- Taiwan instruments mapped:
  - `0050.TW`: reference Taiwan 50 ETF
  - `00631L.TW`: 2x long Taiwan 50 LETF
  - `00632R.TW`: inverse Taiwan 50 ETF

## Final Strategy Decision

No live strategy change.

- Do not auto rebalance.
- Do not add `00631L`.
- Do not open `00632R`.
- Do not import double-short or LETF-pair strategy.
- Keep `Golden1_0531` unchanged.
- Use this paper only as research/governance evidence.

## Paper Ideas Imported

Imported as governance checks only:

- LETF holding-horizon risk.
- Tracking error by horizon, not just daily target return.
- Realized variance decay proxy.
- Realized effective fee / effective drag proxy.
- Inverse ETF hedge-neutrality warning.
- LETF pair trades can look attractive on average but carry large tail risk and
  should not be promoted into live GroupA+.

Not imported:

- commodity ETF parameters;
- US LETF fee constants;
- futures/swap replication assumptions;
- short LETF-pair trade;
- any rule that automatically adds `00631L` or opens `00632R`.

## Implemented Artifact

Artifact name:

- `letf_tracking_error_effective_fee_readiness_review`

Primary builder:

- `scripts/evaluate/build_group_a_plus_letf_tracking_error_effective_fee_readiness_review.py`

Latest output:

- `report/group_a_plus/latest/letf_tracking_error_effective_fee_readiness_review.json`

History output:

- `report/group_a_plus/letf_tracking_error_effective_fee_readiness/history/letf_tracking_error_effective_fee_readiness_20260720.json`

Test:

- `tests/test_build_group_a_plus_letf_tracking_error_effective_fee_readiness_review.py`

## Pipeline Integration

The artifact is now part of daily GroupA+ governance.

Updated files:

- `scripts/run/run_ncf_daily_pipeline.py`
  - Adds best-effort step:
    `letf_tracking_error_effective_fee_readiness_review`
  - Passes the output into research shadow.
  - Passes the output into daily status.

- `scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py`
  - Adds default input:
    `report/group_a_plus/latest/letf_tracking_error_effective_fee_readiness_review.json`
  - Adds blocker when status is blocked:
    `letf_tracking_error_effective_fee_readiness_blocked`
  - Adds summary fields:
    - `letf_tracking_status`
    - `letf_tracking_error_readiness_ready`
    - `letf_effective_fee_proxy_ready`
    - `letf_hedge_neutrality_ready`
    - `letf_allow_00631l_add`
    - `letf_allow_00632r_open`

- `scripts/misc/check_group_a_plus_daily_status.py`
  - Adds CLI:
    `--letf-tracking-error-effective-fee-readiness-review`
  - Adds markdown section:
    `LETF Tracking Error / Effective Fee Readiness`

## Computation Summary

Input data:

- DB: `FinRL/data/stock_data.db`
- Table: `ohlcv`
- Required tickers:
  - `0050.TW`
  - `00631L.TW`
  - `00632R.TW`
- Default start: `2020-01-01`
- Requested as-of for current run: `2026-07-20`
- Actual common data end: `2026-07-17`

Horizon metrics:

- 1 day
- 5 days
- 10 days
- 20 days
- 30 days

For each LETF and horizon:

- reference log return: `log(0050_t / 0050_t-h)`
- LETF log return: `log(LETF_t / LETF_t-h)`
- tracking error: `LETF_horizon_return - beta * reference_horizon_return`
- realized variance: rolling sum of squared daily `0050` log returns
- variance decay proxy: `((beta - beta^2) / 2) * realized_variance`
- effective drag proxy: `tracking_error - variance_decay_proxy`

Beta assumptions:

- `00631L.TW`: `beta = 2.0`
- `00632R.TW`: `beta = -1.0`

Hedge-neutrality check:

- 60-day realized beta of `00632R.TW` versus `0050.TW`
- 60-day correlation of `00632R.TW` versus `0050.TW`
- This is review-only and does not unlock a hedge.

## Current 2026-07-20 Result

From:

- `report/group_a_plus/latest/letf_tracking_error_effective_fee_readiness_review.json`

Status:

- `blocked`

Actual data end:

- `2026-07-17`

Decision flags:

- `tracking_error_readiness_ready = false`
- `realized_effective_fee_proxy_ready = false`
- `hedge_neutrality_ready = false`
- `promote_to_live = false`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `allow_00631l_add = false`
- `allow_00632r_open = false`
- `letf_pair_trade_allowed = false`
- `keep_golden1_0531_unchanged = true`

Blocking reasons:

- `00631l_tw_mean_30d_tracking_error_drag_present`
- `00632r_hedge_neutrality_not_promoted`
- `intervention_fatigue_risk_budget_readiness_blocked`
- `letf_pair_strategy_not_imported`
- `realized_effective_fee_proxy_not_validated`
- `research_only_letf_tracking_error_review`

Current diagnostics:

- `00631L` 30d mean tracking error:
  `-0.004888744513726964`
- `00631L` 30d latest tracking error:
  `-0.05898968415234139`
- `00631L` 30d mean effective-drag proxy:
  `0.001198008212201039`
- `00631L` 30d latest effective-drag proxy:
  `-0.04477677952573382`
- `00632R` 30d mean tracking error:
  `0.02914141424224918`
- `00632R` 30d latest tracking error:
  `0.0081190680562589`
- `00632R` 30d mean effective-drag proxy:
  `0.03522816696817718`
- `00632R` 30d latest effective-drag proxy:
  `0.022331972682866474`
- `00632R` 60d realized beta:
  `-0.9943236718895596`
- `00632R` 60d beta error:
  `0.005676328110440387`
- `00632R` 60d correlation:
  `-0.9779260056912819`

## Parameter Threshold Review

The LETF readiness artifact now includes:

- `parameter_threshold_review`

Purpose:

- define what would need to improve before manual review could even consider
  relaxing the LETF gate;
- keep the thresholds advisory-only;
- prevent accidental promotion into live orders.

Current threshold status:

- `all_thresholds_passed = false`
- `can_consider_00631l_add_after_manual_review = false`
- `can_consider_00632r_open_after_manual_review = false`

Failed checks:

- `00631l_30d_mean_tracking_error_floor`
  - value: `-0.004888744513726964`
  - threshold: `-0.003`
- `00631l_30d_latest_tracking_error_floor`
  - value: `-0.05898968415234139`
  - threshold: `-0.02`
- `00631l_30d_p05_tracking_error_floor`
  - value: `-0.06766467069057348`
  - threshold: `-0.05`
- `00631l_30d_latest_realized_variance_ceiling`
  - value: `0.014212904626607573`
  - threshold: `0.01`
- `00632r_30d_p05_tracking_error_floor`
  - value: `-0.04194782042073657`
  - threshold: `-0.03`
- `effective_fee_proxy_independently_validated`
  - value: `false`
  - threshold: `true`
- `live_hedge_policy_validated`
  - value: `false`
  - threshold: `true`

Passed but not sufficient:

- `00632R` 60d beta error is within threshold.
- `00632R` 60d correlation is below the negative-correlation threshold.

Interpretation:

- `00632R` currently looks directionally hedge-like by 60d beta/correlation, but
  this is not enough to open a live hedge because 30d left-tail tracking error
  fails and live hedge policy is not validated.
- `00631L` fails multiple 30d LETF tracking/variance conditions, so the paper's
  governance import actively supports keeping leverage add blocked.

Interpretation:

- `00631L` shows negative 30-day latest tracking error and a 30-day drag
  blocker.
- `00632R` currently has near -1 realized beta, but the hedge is still not
  promoted because the hedge-neutrality method is review-only and not tied to
  live execution validation.
- The artifact confirms the same practical decision: no leverage add, no inverse
  hedge, no rebalance.

## Research Shadow Impact

From:

- `report/group_a_plus/latest/research_shadow_decision_snapshot.json`

Research shadow status:

- `blocked`

New blocker included:

- `letf_tracking_error_effective_fee_readiness_blocked`

Research shadow still disallows:

- `promote_to_live = false`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `allow_00631l_add = false`
- `keep_golden1_0531_unchanged = true`

Note:

- Research shadow does not currently expose `allow_00632r_open` as a top-level
  decision. The LETF artifact itself does expose `allow_00632r_open = false`.

## Daily Status Impact

From:

- `results/group_a_plus_daily_status_20260720.md`
- `results/group_a_plus_daily_status_20260720.json`
- `report/group_a_plus/latest/daily_status.json`

Daily status:

- `warn`

Reason:

- `data_freshness = warn`
- Requested check date: `2026-07-20`
- Actual live signal data date: `2026-07-17`
- Business stale days: `1`
- Calendar stale days: `3`

New markdown section:

- `LETF Tracking Error / Effective Fee Readiness`

Key lines:

- `Status: blocked`
- `Actual data end: 2026-07-17`
- `00631L add: blocked`
- `00632R open: blocked`
- `Tracking-error readiness: False`
- `Effective-fee proxy ready: False`
- `Hedge-neutrality ready: False`

## Commands Used / Re-run Commands

Build LETF readiness:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_letf_tracking_error_effective_fee_readiness_review.py --as-of 2026-07-20
```

Build research shadow:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py
```

Build 2026-07-20 daily status:

```bash
.venv/bin/python scripts/misc/check_group_a_plus_daily_status.py --mode live --live-signal results/group_a_plus_live_signal_v2_20260720.json --execution-plan report/group_a_plus/latest/execution_plan.json --compounding-regime results/00631l_leveraged_compounding_regime_20260720.json --dfl-advisory report/group_a_plus/latest/a2118_dfl_advisory.json --dfl-shadow-ensemble report/group_a_plus/latest/a2118_dfl_shadow_ensemble.json --dfl-active-date-audit results/a2118_dfl_active_date_audit_20260720.json --finstressts-decision-snapshot report/group_a_plus/latest/finstressts_decision_snapshot.json --trigate-vol-memory-shadow report/group_a_plus/latest/trigate_vol_memory_shadow.json --systemic-bubble-time-at-risk-review report/group_a_plus/latest/systemic_bubble_time_at_risk_review.json --hmm-wj-synthetic-scenario-readiness-review report/group_a_plus/latest/hmm_wj_synthetic_scenario_readiness_review.json --dynamic-cvar-tail-cost-readiness-review report/group_a_plus/latest/dynamic_cvar_tail_cost_readiness_review.json --synthetic-augmentation-validation-readiness-review report/group_a_plus/latest/synthetic_augmentation_validation_readiness_review.json --intervention-fatigue-risk-budget-readiness-review report/group_a_plus/latest/intervention_fatigue_risk_budget_readiness_review.json --letf-tracking-error-effective-fee-readiness-review report/group_a_plus/latest/letf_tracking_error_effective_fee_readiness_review.json --research-shadow-decision-snapshot report/group_a_plus/latest/research_shadow_decision_snapshot.json --check-date 2026-07-20 --output-prefix results/group_a_plus_daily_status_20260720
```

Run focused tests:

```bash
.venv/bin/python -m pytest tests/test_build_group_a_plus_letf_tracking_error_effective_fee_readiness_review.py tests/test_build_group_a_plus_research_shadow_decision_snapshot.py tests/test_check_group_a_plus_daily_status.py tests/test_run_ncf_daily_pipeline.py
```

Latest verification result:

- `37 passed`

## Files Added / Updated

New files:

- `scripts/evaluate/build_group_a_plus_letf_tracking_error_effective_fee_readiness_review.py`
- `tests/test_build_group_a_plus_letf_tracking_error_effective_fee_readiness_review.py`
- `docs/DETAILED_HANDOFF_1610_09404_LETF_TRACKING_ERROR_GROUPA_PLUS_20260719.md`
- `report/group_a_plus/latest/letf_tracking_error_effective_fee_readiness_review.json`
- `report/group_a_plus/letf_tracking_error_effective_fee_readiness/history/letf_tracking_error_effective_fee_readiness_20260720.json`

Updated files:

- `scripts/run/run_ncf_daily_pipeline.py`
- `scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py`
- `scripts/misc/check_group_a_plus_daily_status.py`
- `tests/test_build_group_a_plus_research_shadow_decision_snapshot.py`
- `tests/test_check_group_a_plus_daily_status.py`
- `tests/test_run_ncf_daily_pipeline.py`
- `docs/1610_09404_LETF_TRACKING_ERROR_GROUPA_PLUS_REVIEW_20260718.md`
- `docs/HANDOFF_1610_09404_LETF_TRACKING_ERROR_GROUPA_PLUS_20260718.md`
- `docs/GROUPA_PLUS_PDF_RESEARCH_DECISION_MATRIX_20260717.md`
- `report/group_a_plus/latest/research_shadow_decision_snapshot.json`
- `results/group_a_plus_daily_status_20260720.json`
- `results/group_a_plus_daily_status_20260720.md`
- `report/group_a_plus/latest/daily_status.json`

## Current Open Limits

The artifact intentionally remains blocked because:

- realized effective-fee proxy is not independently validated;
- `00632R` hedge neutrality is not promoted into live order logic;
- LETF pair strategy is explicitly not imported;
- intervention fatigue / risk-budget readiness is blocked;
- broker reconciliation remains a separate blocker for live orders;
- latest data for 2026-07-20 estimate still ends at 2026-07-17.

## Next Step Candidates

Only after newer market data is available:

1. Re-run data refresh and daily pipeline for a true 2026-07-20 market close.
2. Re-run LETF readiness and compare whether `00631L` 30d tracking-error drag
   persists.
3. Keep `00632R` blocked unless a separate live hedge policy validates sizing,
   execution cost, hedge decay, and broker holdings reconciliation.
4. Do not change `Golden1_0531` based on this paper alone.

## Bottom Line

The paper has useful ideas, but the only safe GroupA+ import is a research-only
LETF tracking-error/effective-fee readiness gate. Current output supports the
same operational decision: no `00631L` add, no `00632R` hedge, no auto rebalance,
and no change to `Golden1_0531`.
