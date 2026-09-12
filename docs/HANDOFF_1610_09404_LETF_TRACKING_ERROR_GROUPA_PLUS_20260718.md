# Handoff: 1610.09404 LETF Tracking Error for GroupA+（2026-07-18）

## Scope

- Source PDF: `C:\Users\isaac\Downloads\1610.09404.pdf`
- Paper: `Understanding the Tracking Errors of Commodity Leveraged ETFs`
- Target: GroupA+ latest strategy, Golden1_0531, 2026-07-20 decision context
- Import type: LETF tracking-error governance only
- Detailed implementation handoff:
  `docs/DETAILED_HANDOFF_1610_09404_LETF_TRACKING_ERROR_GROUPA_PLUS_20260719.md`

## Final Decision

No live strategy change.

- No auto rebalance.
- No new `00631L` add.
- No direct `00632R` hedge.
- Keep `Golden1_0531` unchanged.
- Do not import double-short LETF trading strategy.

## Useful Import

Imported concepts for future research-only governance:

- leveraged ETF holding horizon risk;
- realized variance decay term;
- tracking error measured across 1/5/10/20/30-day horizons;
- realized effective fee / effective drag proxy;
- inverse ETF hedge neutrality warning;
- LETF pair strategies have large tail risk and should not be used live.

## Current GroupA+ Mapping

Relevant existing gates:

- `00631l_leveraged_compounding_regime_20260720.json`
- `trigate_vol_memory_shadow.json`
- `dynamic_cvar_tail_cost_readiness_review.json`
- `intervention_fatigue_risk_budget_readiness_review.json`
- `research_shadow_decision_snapshot.json`
- `broker_holdings_reconciliation_review.json`

This paper supports the current no-add / no-hedge stance:

- `00631L` add should remain blocked unless holding-horizon and realized
  variance conditions are favorable.
- `00632R` should not be opened automatically because inverse ETF tracking error
  and hedge non-neutrality can create unexpected losses.
- Any LETF allocation needs tracking-error and effective-drag diagnostics before
  promotion.

## Implemented Artifact

Research-only:

- `letf_tracking_error_effective_fee_readiness_review`

Files:

- `scripts/evaluate/build_group_a_plus_letf_tracking_error_effective_fee_readiness_review.py`
- `tests/test_build_group_a_plus_letf_tracking_error_effective_fee_readiness_review.py`
- `report/group_a_plus/latest/letf_tracking_error_effective_fee_readiness_review.json`
- `report/group_a_plus/letf_tracking_error_effective_fee_readiness/history/letf_tracking_error_effective_fee_readiness_20260720.json`

Pipeline wiring:

- `run_ncf_daily_pipeline.py`: best-effort step
  `letf_tracking_error_effective_fee_readiness_review`
- `build_group_a_plus_research_shadow_decision_snapshot.py`: adds
  `letf_tracking_error_effective_fee_readiness_blocked`
- `check_group_a_plus_daily_status.py`: renders LETF tracking-error section

Current 2026-07-20 result:

- `status = blocked`
- `actual_data_end = 2026-07-17`
- `allow_00631l_add = false`
- `allow_00632r_open = false`
- `auto_rebalance_allowed = false`
- `target_weight_change_allowed = false`
- `keep_golden1_0531_unchanged = true`

Current blockers:

- `research_only_letf_tracking_error_review`
- `realized_effective_fee_proxy_not_validated`
- `00632r_hedge_neutrality_not_promoted`
- `letf_pair_strategy_not_imported`
- `intervention_fatigue_risk_budget_readiness_blocked`
- `00631l_tw_mean_30d_tracking_error_drag_present`

Current diagnostics:

- `00631L` 30d mean/latest tracking error:
  `-0.004888744513726964` / `-0.05898968415234139`
- `00632R` 30d mean/latest tracking error:
  `0.02914141424224918` / `0.0081190680562589`
- `00632R` 60d hedge beta/correlation:
  `-0.9943236718895596` / `-0.9779260056912819`
- `00632R` full-sample 30d tracking-error p05:
  `-0.04194782042073657`
- `00632R` recent-60 30d tracking-error p05:
  `-0.010876108225421257`
- `00632R` tail-gate split recommendation:
  `true`

Additional tail-gate artifact:

- `scripts/evaluate/build_group_a_plus_00632r_tail_tracking_error_gate_review.py`
- `tests/test_build_group_a_plus_00632r_tail_tracking_error_gate_review.py`
- `report/group_a_plus/latest/00632r_tail_tracking_error_gate_review.json`
- `report/group_a_plus/00632r_tail_tracking_error_gate/history/00632r_tail_tracking_error_gate_20260720.json`
- `scripts/evaluate/build_group_a_plus_00632r_effective_fee_proxy_validation_review.py`
- `tests/test_build_group_a_plus_00632r_effective_fee_proxy_validation_review.py`
- `report/group_a_plus/latest/00632r_effective_fee_proxy_validation_review.json`
- `report/group_a_plus/00632r_effective_fee_proxy_validation/history/00632r_effective_fee_proxy_validation_20260720.json`
- `scripts/evaluate/build_group_a_plus_live_hedge_policy_review.py`
- `tests/test_build_group_a_plus_live_hedge_policy_review.py`
- `report/group_a_plus/latest/live_hedge_policy_review.json`
- `report/group_a_plus/live_hedge_policy/history/live_hedge_policy_20260720.json`

Tail-gate decision:

- full-sample auto-trade tail gate passed: `false`
- manual recent tail gate passed: `true`
- gate split recommended: `true`
- manual hedge discussion allowed: `false`
- `allow_00632r_open = false`

Interpretation: split the gate for monitoring only. Keep the original
full-sample p05 gate as an automatic-trading blocker, while tracking the
recent-tail tier separately for manual review evidence.

Effective-fee proxy validation:

- status: `blocked`
- proxy validated for manual review: `false`
- failed horizons: `20:tail_overlap`, `30:tail_overlap`
- 5d tracking-vs-drag correlation / tail overlap:
  `0.99987025107381` / `0.8625`
- 10d tracking-vs-drag correlation / tail overlap:
  `0.9998335441804744` / `0.8354430379746836`
- 20d tracking-vs-drag correlation / tail overlap:
  `0.999800905765244` / `0.759493670886076`
- 30d tracking-vs-drag correlation / tail overlap:
  `0.999782278198798` / `0.717948717948718`

Interpretation: the proxy tracks broad tracking-error movement but misses too
much of the longer-horizon left tail. Keep
`realized_effective_fee_proxy_not_validated` as a blocker.

Live hedge policy review:

- status: `blocked`
- policy defined: `true`
- policy validated for manual discussion: `false`
- live hedge policy validated: `false`
- manual hedge discussion allowed: `false`
- `allow_00632r_open = false`
- blockers:
  - `manual_hedge_eligibility_blocks_discussion`
  - `effective_fee_proxy_not_validated_for_manual_review`
  - `live_hedge_policy_not_validated_for_live_action`

Interpretation: the hedge policy boundary is explicit but still not live
validated. It forbids LLM/PPO/script-generated orders and target weights.

## 2026-07-20 Practical Impact

No change to latest strategy.

Current action remains:

- freeze/no-add `00631L`;
- do not open `00632R`;
- no auto rebalance;
- no target-weight change;
- keep `Golden1_0531` unchanged;
- use this paper as manual-review evidence only.

## 2026-08-29 Refresh Against 2026-08-31 Latest Strategy

Context:

- Review date: `2026-08-29`
- Latest LETF readiness artifact:
  `report/group_a_plus/latest/letf_tracking_error_effective_fee_readiness_review.json`
- Artifact `as_of`: `2026-08-28`
- Artifact `actual_data_end`: `2026-08-28`
- 2026-08-31 preview file:
  `results/group_a_plus_latest_strategy_predict_20260831_from_20260828_total1000000.json`

The 2026-08-31 preview latest-strategy weights for 1,000,000 TWD are:

- `0050.TW`: `47.0000%`
- `00631L.TW`: `10.0388%`
- `00632R.TW`: `16.4782%`
- `00679B.TWO`: `0.0000%`
- `cash`: `26.4830%`

The LETF tracking-error/effective-fee readiness review remains blocked:

- `status = blocked`
- `allow_00631l_add = false`
- `allow_00632r_open = false`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`

Current failed checks:

- `00631l_30d_mean_tracking_error_floor`:
  value `-0.005443384995685611`, threshold `-0.003`, failed.
- `00631l_30d_p05_tracking_error_floor`:
  value `-0.06726248295164249`, threshold `-0.05`, failed.
- `00631l_30d_latest_realized_variance_ceiling`:
  value `0.01674647848524199`, threshold `0.01`, failed.
- `00632r_30d_p05_tracking_error_floor`:
  value `-0.04179082076309815`, threshold `-0.03`, failed.
- `effective_fee_proxy_independently_validated`: failed.
- `live_hedge_policy_validated`: failed.

Current passed-but-insufficient checks:

- `00631l_30d_latest_tracking_error_floor` passes:
  value `-0.010601223372096472`, threshold `-0.02`.
- `00632r_60d_abs_beta_error_ceiling` passes:
  value `0.012952470882646505`, threshold `0.10`.
- `00632r_60d_correlation_ceiling` passes:
  value `-0.9848231951491087`, threshold `-0.95`.

Interpretation:

- The paper supports tracking-error and effective-drag monitoring for 00631L
  and 00632R, but it does not support promoting either LETF into automatic
  orders under the current readiness state.
- `00632R` hedge beta/correlation is currently close to the intended inverse
  exposure, but its 30-day left-tail tracking-error gate still fails and the
  live hedge policy remains unvalidated.
- `00631L` has both mean tracking-error drag and high current realized variance,
  so the paper's volatility-decay argument supports caution rather than adding
  exposure.
- If latest-strategy preview and LETF readiness disagree, the readiness review
  is a blocker for promotion/manual relaxation evidence, not a new alpha signal.

Operational decision for this refresh:

- Do not import the LETF pair trade.
- Do not use this paper to justify adding `00631L`.
- Do not use this paper to justify opening `00632R`.
- Keep the existing pipeline step
  `letf_tracking_error_effective_fee_readiness_review`.
- Treat the paper as supporting evidence for LETF caution, tracking-error
  monitoring, and hedge-neutrality review only.

## Final Archive Decision

Decision date: `2026-08-29`.

Status: experiments complete for GroupA+ import purposes. Best treatment is to
leave this paper as a detailed LETF tracking-error / effective-drag governance
record and daily shadow blocker.

Do not promote:

- no LETF pair trade;
- no paper-driven `00631L` add;
- no paper-driven `00632R` open;
- no auto rebalance;
- no target-weight change;
- no override of `Golden1_0531`, `a2118`, NCF, or latest-strategy governance.

Keep:

- `letf_tracking_error_effective_fee_readiness_review` in the daily pipeline;
- 00631L holding-horizon / volatility-decay checks;
- 00632R hedge-neutrality and left-tail tracking-error checks;
- effective-fee proxy validation as a hard blocker until separately proven.

Re-open only if:

- a new daily pipeline run materially changes LETF readiness gates;
- effective-fee proxy validation is separately approved and passes;
- live hedge policy validation for `00632R` is separately approved and passes;
- the question is explicitly about blocking/reducing an LETF leg, not creating
  a new alpha signal.

## Verification

2026-07-18: documentation only in this step.

2026-08-29 refresh verification:

- `tests/test_build_group_a_plus_letf_tracking_error_effective_fee_readiness_review.py`
  passed: `2 passed in 6.85s`.

Files updated:

- `docs/1610_09404_LETF_TRACKING_ERROR_GROUPA_PLUS_REVIEW_20260718.md`
- `docs/HANDOFF_1610_09404_LETF_TRACKING_ERROR_GROUPA_PLUS_20260718.md`
- `docs/GROUPA_PLUS_PDF_RESEARCH_DECISION_MATRIX_20260717.md`
