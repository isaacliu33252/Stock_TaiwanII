# Handoff: 2606.26625 Commodity ETF CVaR Tail/Cost Review for GroupA+（2026-07-18）

## Scope

- Source PDF: `C:\Users\isaac\Downloads\2606.26625.pdf`
- Paper: `Portfolio Optimization for Commodity ETFs under Heavy-Tailed Returns`
- Target: GroupA+ latest strategy, Golden1_0531, 2026-07-20 execution context
- Import type: research-only governance

## Final Decision

No live trading change.

- No auto rebalance for 2026-07-20.
- No new `00631L` add.
- No direct `00632R` hedge.
- Keep Golden1_0531 unchanged.
- Do not import commodity ETF allocations or a live dynamic optimizer.

## What Was Imported

Imported only as governance / readiness checks:

- CVaR before return-seeking tangency.
- EVT / Hill tail-thickness diagnostics after optimization.
- Turnover and transaction-cost robustness before optimizer promotion.
- ARMA-GARCH / Student-t copula scenario concept as future research only.

## Implemented Artifacts

- Builder: `scripts/evaluate/build_group_a_plus_dynamic_cvar_tail_cost_readiness_review.py`
- Unit test: `tests/test_build_group_a_plus_dynamic_cvar_tail_cost_readiness_review.py`
- Latest JSON: `report/group_a_plus/latest/dynamic_cvar_tail_cost_readiness_review.json`
- History JSON: `report/group_a_plus/dynamic_cvar_tail_cost_readiness/history/20260720.json`
- Review doc: `docs/2606_26625_COMMODITY_ETF_CVAR_TAIL_RISK_GROUPA_PLUS_REVIEW_20260718.md`

Integrated into:

- `scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py`
- `scripts/run/run_ncf_daily_pipeline.py`
- `scripts/misc/check_group_a_plus_daily_status.py`
- `docs/GROUPA_PLUS_PDF_RESEARCH_DECISION_MATRIX_20260717.md`

Validation daily-status outputs:

- `results/group_a_plus_daily_status_20260720_dynamic_cvar.json`
- `results/group_a_plus_daily_status_20260720_dynamic_cvar.md`

## Latest Result

`dynamic_cvar_tail_cost_readiness_review.json`:

- `status = blocked`
- `as_of = 2026-07-20`
- `dynamic_optimizer_ready = false`
- `tail_cost_readiness_ready = false`
- `promote_to_live = false`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `allow_00631l_add = false`
- `keep_golden1_0531_unchanged = true`

Key numeric diagnostics:

- `00631l_expected_shortfall_loss_95 = 0.07640461608576213`
- `00631l_expected_shortfall_loss_99 = 0.13086026671133563`
- `00631l_max_drawdown = -0.5022632537851175`
- `00631l_hill_xi_95 = 0.3262529593802684`
- `00631l_pot_gpd_shape_xi_95 = 0.15947448794631444`
- `golden1_starr_95 = 17.339408036642002`
- `market_impact.turnover = 0.5915811038461518`

Blocking reasons:

- `cvar_tail_risk_diagnostic_research_only`
- `00631l_hill_tail_index_positive_heavy_tail`
- `00631l_pot_gpd_shape_positive_heavy_tail`
- `density_tail_model_unstable_research_only`
- `market_impact_readiness_blocked`
- `market_impact_disallows_auto_rebalance`
- `rebalance_review_disallows_auto_rebalance`
- `rebalance_review_disallows_target_weight_change`
- `systemic_bubble_time_at_risk_blocks_leverage_add`
- `systemic_bubble_disallows_00631l_add`
- `hmm_wj_scenario_readiness_blocked`
- `scenario_generator_not_decision_ready`
- `dynamic_cvar_optimizer_not_implemented`
- `taiwan_etf_walkforward_validation_missing`

## Research Snapshot Impact

`report/group_a_plus/latest/research_shadow_decision_snapshot.json` now includes:

- `dynamic_cvar_status = blocked`
- `dynamic_cvar_tail_cost_ready = false`
- `dynamic_cvar_optimizer_ready = false`
- `dynamic_cvar_allow_00631l_add = false`
- blocker: `dynamic_cvar_tail_cost_readiness_blocked`

The consolidated snapshot remains:

- `status = blocked`
- `allow_00631l_add = false`

## Daily Status Impact

Daily status now accepts:

- `--dynamic-cvar-tail-cost-readiness-review`

Daily status JSON key:

- `group_a_plus.dynamic_cvar_tail_cost_readiness_review`

Daily status Markdown section:

- `Dynamic CVaR Tail/Cost Readiness`

Validation run:

- `results/group_a_plus_daily_status_20260720_dynamic_cvar.json`
- `results/group_a_plus_daily_status_20260720_dynamic_cvar.md`
- Overall remained `block`, mainly because live execution/data freshness checks
  were still blocked. Dynamic CVaR is display/governance only, not a new live
  execution gate.

## Verification

Passed:

- `.venv/bin/python -m pytest tests/test_build_group_a_plus_dynamic_cvar_tail_cost_readiness_review.py tests/test_build_group_a_plus_research_shadow_decision_snapshot.py tests/test_run_ncf_daily_pipeline.py`
  - `19 passed`
- `.venv/bin/python -m pytest tests/test_check_group_a_plus_daily_status.py tests/test_run_ncf_daily_pipeline.py`
  - `30 passed`
- `.venv/bin/python -m py_compile scripts/evaluate/build_group_a_plus_dynamic_cvar_tail_cost_readiness_review.py scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py scripts/run/run_ncf_daily_pipeline.py`
- `.venv/bin/python -m py_compile scripts/misc/check_group_a_plus_daily_status.py scripts/run/run_ncf_daily_pipeline.py`

## Next Practical Step

If continuing this line, do not tune live weights yet. The next useful work is:

Completed after this handoff:

- Added compact daily-status summary lines under `Research Shadow Decision Snapshot`:
  - `Dynamic CVaR status`
  - `Dynamic CVaR tail/cost ready`
  - `Dynamic CVaR optimizer ready`
- Rebuilt `results/group_a_plus_daily_status_20260720_dynamic_cvar.md`.
- Verified:
  - `.venv/bin/python -m pytest tests/test_check_group_a_plus_daily_status.py`
    - `15 passed`
  - `.venv/bin/python -m py_compile scripts/misc/check_group_a_plus_daily_status.py`

Remaining next steps:

1. Run full daily pipeline after latest data refresh, then compare the fresh
   `dynamic_cvar_tail_cost_readiness_review.json` against this 2026-07-20
   handoff.
2. Only consider optimizer research after Taiwan ETF walk-forward validation and
   transaction-cost validation exist.

## Full Pipeline Refresh（2026-07-18 15:15）

Ran:

- `.venv/bin/python scripts/run/run_ncf_daily_pipeline.py --date-stamp 20260720 --refresh-target-date 2026-07-17 --chip-end 2026-07-17 --per-start 2023-07-17 --val-end latest --checklist-external-end 2026-07-18`

Pipeline completed all `52 / 52` steps.

Key outputs:

- Manifest: `results/ncf_daily_pipeline_20260720.json`
- Live signal: `results/group_a_plus_live_signal_v2_20260720.json`
- Daily status: `results/group_a_plus_daily_status_20260720.json`
- Final decision record: `docs/GROUPA_PLUS_20260720_FULL_PIPELINE_FINAL_DECISION_RECORD.md`
- Dynamic CVaR readiness: `report/group_a_plus/latest/dynamic_cvar_tail_cost_readiness_review.json`
- Research shadow snapshot: `report/group_a_plus/latest/research_shadow_decision_snapshot.json`
- Promotion gate: `results/group_a_plus_promotion_gate_20260720.json`

Fresh NCF signal summary:

- `00631L.TW`
  - data date: `2026-07-17`
  - freshness: `ok`
  - direction: `DOWN`
  - `probability_up = 0.4912`
  - `calibrated_probability_up = 0.4953`
  - `confidence = 0.3332`
  - `weighted_return = -0.00619`
- `00632R.TW`
  - data date: `2026-07-17`
  - freshness: `ok`
  - direction: `UP`
  - `probability_up = 0.5207`
  - `calibrated_probability_up = 0.5124`
  - `confidence = 0.4279`
  - `weighted_return = 0.020023`
- `2330.TW`
  - data date: `2026-07-17`
  - direction: `UP`
  - `probability_up = 0.531`
  - `calibrated_probability_up = 0.5156`
  - `confidence = 0.2914`
  - NCF 2330 data freshness is `degraded_missing` for local `ohlcv`,
    `institutional`, and `margin`, while external 2330 OHLCV is current.

Fresh daily status:

- `overall_status = warn`
- `execution_allowed = ok`
- `source_freshness = ok`
- `data_freshness = warn` because actual data date is `2026-07-17` for the
  `2026-07-20` check date.
- pre-trade guards remain `blocked,blocked`.

Fresh dynamic CVaR readiness:

- `status = blocked`
- `as_of = 2026-07-20`
- `dynamic_optimizer_ready = false`
- `tail_cost_readiness_ready = false`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `allow_00631l_add = false`
- `keep_golden1_0531_unchanged = true`

Updated key diagnostics:

- `00631l_expected_shortfall_loss_95 = 0.0811159172627952`
- `00631l_expected_shortfall_loss_99 = 0.13958238180763255`
- `00631l_max_drawdown = -0.5022632537851175`
- `00631l_hill_xi_95 = 0.36369464063958445`
- `00631l_pot_gpd_shape_xi_95 = -0.06744554391369038`
- `golden1_starr_95 = 14.567266529463351`
- `golden1_expected_shortfall_loss_95 = 0.03457081702818987`
- `market_impact.turnover = 0.5006477801878955`

Updated blockers:

- `cvar_tail_risk_diagnostic_research_only`
- `00631l_hill_tail_index_positive_heavy_tail`
- `density_tail_model_unstable_research_only`
- `market_impact_readiness_blocked`
- `market_impact_disallows_auto_rebalance`
- `rebalance_review_disallows_auto_rebalance`
- `rebalance_review_disallows_target_weight_change`
- `systemic_bubble_time_at_risk_blocks_leverage_add`
- `systemic_bubble_disallows_00631l_add`
- `hmm_wj_scenario_readiness_blocked`
- `scenario_generator_not_decision_ready`
- `dynamic_cvar_optimizer_not_implemented`
- `taiwan_etf_walkforward_validation_missing`

Note: `00631l_pot_gpd_shape_positive_heavy_tail` disappeared after the refresh
because the updated POT-GPD shape estimate turned negative, but the Hill
tail-index, GMM, market-impact, rebalance, systemic, HMM-WJ, and validation
blockers still keep the artifact blocked.

Fresh research shadow snapshot remains:

- `status = blocked`
- `dynamic_cvar_status = blocked`
- `dynamic_cvar_tail_cost_ready = false`
- `dynamic_cvar_optimizer_ready = false`
- blocker: `dynamic_cvar_tail_cost_readiness_blocked`

Fresh deployment / promotion governance:

- Deployment consistency: `manual_review_required`
- Deployment decision:
  - `target_weight_change_allowed = false`
  - `auto_rebalance_allowed = false`
  - `broker_actionable = false`
  - `allow_00631l_add = false`
- Promotion gate: `blocked_multi_window`

Final refreshed 2026-07-20 decision:

- no auto rebalance;
- no new `00631L` add;
- no direct `00632R` hedge;
- no Golden1_0531 change;
- dynamic CVaR remains research-only and blocked from live execution.
