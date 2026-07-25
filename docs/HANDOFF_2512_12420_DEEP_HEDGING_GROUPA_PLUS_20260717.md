# Handoff: 2512.12420 Deep Hedging x GroupA+（2026-07-17）

## User Request

Analyze:

- `C:\Users\isaac\Downloads\2512.12420.pdf`

Question:

- 是否有優點可以導入 GroupA+ 最新策略？
- 下一步是否能改善？
- 留下交接記錄。

## Paper

Title:

- `Deep Hedging with Reinforcement Learning: A Practical Framework for Option Risk Management`

Core idea:

- Use option-surface, realized-volatility, and macro-rate state features to run
  a bounded, cost-aware hedge overlay.
- The paper trains a compact stochastic actor-critic policy for SPX/SPY option
  risk management.
- The useful part for GroupA+ is the governance / execution framework, not the
  trained RL actor.

Important paper settings:

- transaction cost: `10 bps` per unit of absolute position change
- slippage: `8 bps`
- selected rebalance cadence: `25` steps
- position limit: `2.0`
- final standalone test Sharpe: about `0.50`
- 50/50 overlay + long SPY test Sharpe: about `0.65`

Important limitation:

- The paper does not prove formal dominance over long SPY because confidence
  intervals overlap the long-SPY benchmark.

## GroupA+ Import Decision

Imported concepts:

- cost-aware overlay review
- position / leverage cap
- rebalance cadence review
- option-state and macro-state coverage gate
- deterministic replay / monitoring
- overlay as risk-management sleeve, not alpha engine

Not imported:

- SPX/SPY actor-critic RL policy
- automatic hedge execution
- replacement of `a2118_a2111_ncf_late_bull_deleverage`
- change to `Golden1_0531`
- live target weight change

## Current 7/20 Decision

GroupA+ target remains reference-only:

- `0050.TW = 50%`
- `00631L.TW = 20%`
- `cash = 30%`

Execution / add decision:

- `promote_to_live = false`
- `target_weight_change_allowed = false`
- `allow_00631l_add = false`
- `manual_review_required = true`
- `Golden1_0531` unchanged

Blockers from deep-hedging overlay review:

- `live_signal_execution_not_allowed`
- `option_surface_state_incomplete`
- `medium_high_or_high_risk_context`
- `rebalance_review_disallows_00631l_add`

Missing option-state fields:

- `txo_pcr_volume_z20`
- `txo_pcr_oi_z20`
- `soxx_put_call_iv_skew_z252`
- `soxx_put_call_volume_ratio_z60`
- `soxx_put_call_oi_ratio_z60`

Warnings:

- `density_head_gmm_not_promoted`
- `cvar_ranking_does_not_prefer_golden1_proxy`

## Produced Artifacts

Review doc:

- `docs/2512_12420_DEEP_HEDGING_GROUPA_PLUS_REVIEW_20260717.md`

Governance / overlay review:

- `scripts/evaluate/build_group_a_plus_deep_hedging_overlay_review.py`
- `report/group_a_plus/latest/deep_hedging_overlay_review_20260720.json`

Deep-hedging-lite shadow:

- `scripts/evaluate/evaluate_deep_hedging_lite_overlay_shadow.py`
- `results/deep_hedging_lite_overlay_shadow_20260717.json`

Option-state coverage:

- `scripts/evaluate/build_group_a_plus_option_state_coverage_review.py`
- `report/group_a_plus/latest/option_state_coverage_review.json`
- `report/group_a_plus/option_state_coverage/history/20260717.json`
- `scripts/fetch/fetch_soxx_options_iv.py`
- `tests/test_fetch_soxx_options_iv.py`
- `tests/test_build_group_a_plus_option_state_coverage_review.py`
- `scripts/run/run_ncf_daily_pipeline.py`

Updated matrix:

- `docs/GROUPA_PLUS_PDF_RESEARCH_DECISION_MATRIX_20260717.md`

This handoff:

- `docs/HANDOFF_2512_12420_DEEP_HEDGING_GROUPA_PLUS_20260717.md`

## Deep-Hedging-Lite Shadow Result

The first non-RL Taiwan baseline was tested before considering any RL:

- max `00631L` overlay: `20%`
- rebalance cadence: `20` trading days
- cost stress: `18 bps` per absolute `00631L` weight change
- signals:
  - `0050` drawdown
  - `0050` 5-day momentum
  - realized-volatility ratio
  - `0050` MA trend
- benchmarks:
  - `no_add_0050_only`
  - `golden1_frozen_50_20_30_proxy`

Aggregate result:

- windows tested: `4`
- beats golden1 proxy by STARR95: `1 / 4`
- beats no-add by STARR95: `2 / 4`
- `promote_to_live = false`

Window result:

| Window | Best by STARR95 | Lite beats golden1 | Lite beats no-add |
| --- | --- | --- | --- |
| `2018_correction` | `golden1_frozen_50_20_30_proxy` | false | false |
| `2020_covid` | `golden1_frozen_50_20_30_proxy` | false | true |
| `2022_rate_hike` | `golden1_frozen_50_20_30_proxy` | false | true |
| `2025_2026` | `no_add_0050_only` | true | false |

Conclusion:

- The governance framework is useful.
- The simple deep-hedging-lite rule is not robust enough.
- Do not promote.

## Validation Commands Run

```bash
.venv/bin/python -m py_compile scripts/evaluate/build_group_a_plus_deep_hedging_overlay_review.py
```

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_deep_hedging_overlay_review.py
```

```bash
.venv/bin/python -m py_compile scripts/evaluate/evaluate_deep_hedging_lite_overlay_shadow.py
```

```bash
.venv/bin/python scripts/evaluate/evaluate_deep_hedging_lite_overlay_shadow.py \
  --output results/deep_hedging_lite_overlay_shadow_20260717.json
```

## Next Step

Do not move to RL yet.

Completed next diagnostic:

- `scripts/run/build_00631l_crash_risk_alert.py --as-of 2026-07-17`
- `scripts/evaluate/build_group_a_plus_option_state_coverage_review.py --as-of 2026-07-17`

Result:

- TXO option data exists through `2026-07-16` and PCR fields are usable at the
  latest fully available alert date.
- `crash_risk_alert.json` could only advance to `as_of = 2026-07-16`; requested
  `2026-07-17` was blocked by incomplete liquidity-family data.
- SOXX options are the real option-state blocker after the quality fix:
  - snapshots: `4`
  - required minimum snapshots: `20`
  - valid ATM-IV rows in latest 10: below required `10`
  - latest ATM IV and put/call OI are now usable, but history is too short for
    z-score gates.

Current option-state blockers:

- `soxx_options_iv_history_lt_20_snapshots`
- `soxx_options_iv_valid_history_lt_10_snapshots`

Completed quality fix:

- `scripts/fetch/fetch_soxx_options_iv.py` now rejects implausible option IV
  values outside `5% ~ 200%` before selecting nearest strikes.
- A regression test was added so near-zero Yahoo placeholder IV values are not
  accepted as valid ATM IV.
- After refetching SOXX options, the `2026-07-16` snapshot improved:
  - ATM IV: `0.062509375`
  - put/call volume ratio: `1.8680851063829786`
  - put/call OI ratio: `2.460093896713615`
  - SOXX IV health: `ok`
- `crash_risk_alert.json` no longer reports `atm_iv_outside_5pct_200pct`.

Remaining option-state blockers after the fix:

- `soxx_options_iv_history_lt_20_snapshots`
- `soxx_options_iv_valid_history_lt_10_snapshots`

Validation after fix:

- `tests/test_run_ncf_daily_pipeline.py`
- `tests/test_fetch_soxx_options_iv.py`
- `tests/test_build_00631l_crash_risk_alert.py`
- result: `33 passed`

Daily pipeline integration:

- `option_state_coverage_review` is now wired into
  `scripts/run/run_ncf_daily_pipeline.py`.
- It runs after `cvar_tail_risk_diagnostic`.
- It is included in `BEST_EFFORT_STEP_NAMES`; failure records diagnostics but
  does not block NCF/signal/promotion workflow.
- The coverage script now writes both the latest report and dated history
  snapshots under `report/group_a_plus/option_state_coverage/history/`.
- The coverage script now supports shadow threshold tuning:
  - `--soxx-options-snapshot-rows-min`
  - `--soxx-options-valid-atm-iv-rows-min`
  - `--txo-options-lag-days-max`

Parameter sensitivity on `2026-07-17`:

- strict `20/10`: `blocked`
- warmup `10/5`: `blocked`
- floor `4/2`: `available`, but this only matches the current four SOXX
  snapshots and two valid ATM-IV rows; keep it research-only and do not use it
  to unlock live overlay decisions.

Parameter sensitivity artifacts:

- `report/group_a_plus/option_state_coverage/params/strict_20_10_20260717.json`
- `report/group_a_plus/option_state_coverage/params/warmup_10_5_20260717.json`
- `report/group_a_plus/option_state_coverage/params/floor_4_2_20260717.json`

Recommended next research step:

1. Fill missing option-state features where possible:
   - prioritize SOXX option skew / put-call ratios;
   - keep accumulating daily SOXX option snapshots until the z-score windows
     have enough valid rows;
   - TXO PCR is not the main blocker after the latest check.
2. Re-run the overlay review after fresh data and option-state coverage improve.
3. If still researching overlay improvement, test a hybrid rule:
   - no 00631L add under medium-high/high risk
   - allow only bounded 00631L exposure when trend, volatility, and option-state
     gates all pass
   - require win versus both `no_add_0050_only` and `golden1_frozen_50_20_30_proxy`
     after costs across 2018, 2020, 2022, and 2025-2026.

Promotion rule:

- Must pass all stress windows after cost.
- Must not fail 2018 / 2020 crash windows.
- Must remain research-only until manual approval.

## Final Position

Keep:

- GroupA+ latest strategy unchanged
- `Golden1_0531` unchanged
- `00631L` auto-add blocked
- auto-rebalance blocked

Use 2512.12420 only as:

- research-only governance framework
- cost/cadence/position-cap checklist
- future overlay monitoring template
