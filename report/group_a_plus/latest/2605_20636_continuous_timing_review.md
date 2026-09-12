# 2605.20636 Continuous Timing Review

Generated: `2026-08-30T00:25:20`
As of: `2026-08-28`
Status: `blocked_for_live_promotion`

## Decision

- Do not import the continuous smooth-score allocation as live strategy logic.
- Keep the validation checklist as the only adopted benefit.
- Do not change latest strategy target weights.
- Do not open or increase `00632R.TW`; do not unlock `00631L.TW`.
- Keep `Golden1_0531` unchanged.

## Latest Strategy Context

- `0050.TW`: `0.470000`
- `00631L.TW`: `0.100388`
- `00632R.TW`: `0.164782`
- `00679B.TWO`: `0.000000`
- `cash`: `0.264830`

## Imported Benefit

- Adopted: multi-window OOS / crisis-independence / cost-sensitivity validation discipline.
- Rejected for live: continuous tanh timing score, growth-crowding penalty, credit/VIX-credit overlays.

## Experiment Scope

- GroupA+ importability experiments: `complete`.
- Full paper replication: `not complete` and `not required` for this strategy decision.
- Reason: remaining paper tables validate the author's US ETF universe, not GroupA+ Taiwan LETF/inverse/bond/cash allocation.

## Decision Flags

- `process_checklist_already_imported`: `True`
- `target_weight_change_allowed`: `False`
- `allow_00631l_add`: `False`
- `allow_00632r_open`: `False`

## Blockers

- `a2119_shadow_candidate_not_promoted`
- `asset_universe_mismatch_growth_defensive_us_etfs_vs_groupa_plus_taiwan_letf_bond_cash`
- `continuous_score_replacement_of_discrete_regime_not_validated_for_latest_strategy`
- `credit_and_vix_credit_components_remain_shadow_only`
- `growth_crowding_penalty_tested_and_rejected`
- `high_turnover_risk_from_continuous_timing_style`
- `research_only_review_no_target_weight_change`

