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

## Latest Strategy Recheck（2026-08-31）

User asked whether `C:\Users\isaac\Downloads\2606.26625.pdf` has advantages
that can be imported into GroupA+ latest strategy.

Existing paper mapping remains valid:

- useful import: CVaR-before-return-seeking governance;
- useful import: EVT / Hill tail-thickness diagnostics after optimization;
- useful import: turnover and transaction-cost robustness before optimizer
  promotion;
- useful import: ARMA-GARCH / Student-t copula scenario concept as future
  research only;
- not imported: commodity ETF allocation, dynamic tangent optimizer, live
  CVaR optimizer, or long-short commodity assumptions.

Re-ran the current readiness builder:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_dynamic_cvar_tail_cost_readiness_review.py
.venv/bin/python -m pytest tests/test_build_group_a_plus_dynamic_cvar_tail_cost_readiness_review.py
```

Outputs:

- latest JSON:
  `report/group_a_plus/latest/dynamic_cvar_tail_cost_readiness_review.json`
- history snapshot:
  `report/group_a_plus/dynamic_cvar_tail_cost_readiness/history/20260831.json`

Validation result:

- pytest passed: `2 passed`;
- readiness builder completed successfully.

Latest 2026-08-31 readiness result:

- `status = blocked`;
- `as_of = 2026-08-31`;
- `policy = research_only_dynamic_cvar_tail_cost_readiness_no_optimizer_no_weight_change`;
- `dynamic_optimizer_ready = false`;
- `tail_cost_readiness_ready = false`;
- `promote_to_live = false`;
- `target_weight_change_allowed = false`;
- `auto_rebalance_allowed = false`;
- `allow_00631l_add = false`;
- `keep_golden1_0531_unchanged = true`.

Latest key diagnostics:

- `00631l_expected_shortfall_loss_95 = 0.08078600090702569`;
- `00631l_expected_shortfall_loss_99 = 0.13168472126438435`;
- `00631l_max_drawdown = -0.5022632537851175`;
- `00631l_hill_xi_95 = 0.3300723192722778`;
- `00631l_pot_gpd_shape_xi_95 = 0.03562302984788215`;
- `golden1_starr_95 = 14.677547483632779`;
- `golden1_expected_shortfall_loss_95 = 0.03461214267712127`;
- `market_impact.turnover = 0.027267395831765216`;
- `market_impact.auto_rebalance_allowed = false`;
- `rebalance.target_weight_change_allowed = false`;
- `systemic_bubble.overall_state = blocked_for_leverage_add`;
- `hmm_wj_scenario_readiness.can_generate_scenarios_for_decision = false`.

Latest blocking reasons:

- `cvar_tail_risk_diagnostic_research_only`;
- `00631l_hill_tail_index_positive_heavy_tail`;
- `00631l_pot_gpd_shape_positive_heavy_tail`;
- `density_tail_model_unstable_research_only`;
- `market_impact_readiness_blocked`;
- `market_impact_disallows_auto_rebalance`;
- `rebalance_review_disallows_auto_rebalance`;
- `rebalance_review_disallows_target_weight_change`;
- `systemic_bubble_time_at_risk_blocks_leverage_add`;
- `systemic_bubble_disallows_00631l_add`;
- `hmm_wj_scenario_readiness_blocked`;
- `scenario_generator_not_decision_ready`;
- `dynamic_cvar_optimizer_not_implemented`;
- `taiwan_etf_walkforward_validation_missing`.

2026-08-31 decision:

The paper still has importable value for GroupA+ latest strategy only as a
research/shadow governance layer. It strengthens the rule that any future
optimizer must pass tail-risk, EVT, turnover, transaction-cost, and Taiwan ETF
walk-forward checks before consideration.

It does not authorize any live action:

- no change to `a2118_a2111_ncf_late_bull_deleverage`;
- no change to target weights;
- no automatic rebalance;
- no `00631L.TW` add;
- no `00632R.TW` hedge/open;
- no `00679B.TWO` add;
- no SCR/CVaR/ARMA-GARCH model promotion;
- no PPO/model retraining from this paper.

## Continued CVaR/Cost Window-Split Audit（2026-08-31）

After the latest-strategy recheck, the user asked to continue. The next
practical gap was `taiwan_etf_walkforward_validation_missing`, so a lightweight
Taiwan ETF window-split audit was added. This is not a dynamic optimizer and
does not attempt to tune weights. It only tests whether the current latest
weights survive the paper's CVaR/cost robustness idea against conservative
variants.

Implemented:

- `scripts/evaluate/evaluate_group_a_plus_2606_26625_cvar_cost_window_split.py`
- `tests/test_evaluate_group_a_plus_2606_26625_cvar_cost_window_split.py`
- `report/group_a_plus/latest/2606_26625_cvar_cost_window_split.json`
- `report/group_a_plus/latest/2606_26625_cvar_cost_window_split.md`

Method:

- read current GroupA+ latest target weights from
  `report/group_a_plus/latest/live_signal.json`;
- load daily close data for `0050.TW`, `00631L.TW`, `00632R.TW`,
  and `00679B.TWO`;
- simulate monthly rebalanced fixed-weight portfolios with `10 bps` transaction
  cost on rebalance turnover;
- compare latest strategy against:
  - `no_00631l_to_cash`;
  - `no_00632r_to_cash`;
  - `no_letf_to_cash`;
  - `golden1_base_50_20_30`;
- evaluate ES95, max drawdown, STARR95, and turnover across stress/recent
  windows.

Windows:

- `covid_2020`;
- `rate_hike_2022`;
- `post_2023`;
- `recent_2024_2026`;
- `active_2025_2026`.

Real-data result:

- status: `blocked_for_live_promotion`;
- as_of: `2026-08-31`;
- valid windows: `5`;
- latest loses to `no_00631l_to_cash` on ES95 or MDD: `5/5`;
- latest loses to `no_letf_to_cash` on ES95 or MDD: `4/5`;
- tail/cost window split passed: `false`.

Window detail:

- `covid_2020`: latest ES95 `0.0174`, no-00631L ES95 `0.0101`,
  latest MDD `-0.1197`, no-00631L MDD `-0.0689`;
- `rate_hike_2022`: latest ES95 `0.0143`, no-00631L ES95 `0.0093`,
  latest MDD `-0.1971`, no-00631L MDD `-0.1421`;
- `post_2023`: latest ES95 `0.0165`, no-00631L ES95 `0.0103`,
  latest MDD `-0.1445`, no-00631L MDD `-0.0914`;
- `recent_2024_2026`: latest ES95 `0.0186`, no-00631L ES95 `0.0113`,
  latest MDD `-0.1417`, no-00631L MDD `-0.0896`;
- `active_2025_2026`: latest ES95 `0.0183`, no-00631L ES95 `0.0107`,
  latest MDD `-0.1435`, no-00631L MDD `-0.0907`.

Validation:

```bash
.venv/bin/python -m py_compile scripts/evaluate/evaluate_group_a_plus_2606_26625_cvar_cost_window_split.py tests/test_evaluate_group_a_plus_2606_26625_cvar_cost_window_split.py
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_2606_26625_cvar_cost_window_split.py
.venv/bin/python -m pytest tests/test_evaluate_group_a_plus_2606_26625_cvar_cost_window_split.py tests/test_build_group_a_plus_dynamic_cvar_tail_cost_readiness_review.py
```

Result:

- syntax check passed;
- evaluator generated latest JSON and Markdown successfully;
- pytest passed: `4 passed`.

Continued decision:

The follow-up audit strengthens the negative live-promotion decision. Current
latest weights are acceptable as the existing production strategy because they
come from the already governed `a2118_a2111_ncf_late_bull_deleverage` path, but
the 2606.26625 paper does not provide evidence to increase leverage, open new
inverse exposure, add bond exposure, or promote a CVaR optimizer. Its value
remains shadow governance only.

## Daily Pipeline Integration（2026-08-31）

The continued CVaR/cost window-split audit was promoted from a one-off local
experiment to a recurring daily shadow artifact.

Pipeline changes:

- added `cvar_cost_window_split_2606_26625` to
  `scripts/run/run_ncf_daily_pipeline.py`;
- marked it as best-effort through the existing research-shadow step list;
- wired its JSON output into `research_shadow_decision_snapshot`;
- wired its JSON output into `daily_status`;
- kept the output paths under `report/group_a_plus/latest/`:
  - `2606_26625_cvar_cost_window_split.json`;
  - `2606_26625_cvar_cost_window_split.md`.

Research snapshot impact:

- new input key: `cvar_cost_window_split_2606_26625`;
- new blocker when applicable:
  `cvar_cost_window_split_2606_26625_blocked_for_live_promotion`;
- new summary fields:
  - `cvar_cost_window_split_2606_26625_status`;
  - `cvar_cost_window_split_2606_26625_passed`;
  - `cvar_cost_window_split_2606_26625_latest_loses_to_no_00631l_windows`;
  - `cvar_cost_window_split_2606_26625_latest_loses_to_no_letf_windows`;
  - `cvar_cost_window_split_2606_26625_target_weight_change_allowed`.

Daily status impact:

- new CLI input: `--cvar-cost-window-split-2606-26625`;
- new JSON key: `group_a_plus.cvar_cost_window_split_2606_26625`;
- new Markdown section: `2606.26625 CVaR/Cost Window Split`.

Validation:

```bash
.venv/bin/python -m py_compile scripts/run/run_ncf_daily_pipeline.py scripts/misc/check_group_a_plus_daily_status.py scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py
.venv/bin/python -m pytest tests/test_run_ncf_daily_pipeline.py tests/test_check_group_a_plus_daily_status.py tests/test_build_group_a_plus_research_shadow_decision_snapshot.py tests/test_evaluate_group_a_plus_2606_26625_cvar_cost_window_split.py
.venv/bin/python scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py --output /tmp/research_shadow_snapshot_2606_26625_smoke.json
.venv/bin/python scripts/misc/check_group_a_plus_daily_status.py --output-prefix /tmp/group_a_plus_daily_status_2606_26625_smoke --canonical-output '' --skip-managed-report
```

Results:

- syntax check passed;
- pytest passed: `53 passed`;
- research shadow smoke included
  `cvar_cost_window_split_2606_26625_blocked_for_live_promotion`;
- daily status smoke rendered `2606.26625 CVaR/Cost Window Split` with
  latest-loses-to-no-00631L windows `5` and latest-loses-to-no-LETF windows `4`.

Production boundary remains unchanged:

- best-effort shadow only;
- no live strategy manifest change;
- no target-weight change;
- no automatic rebalance;
- no `00631L.TW` add;
- no `00632R.TW` open;
- no `00679B.TWO` add;
- no optimizer/model/PPO promotion.

## Dynamic Readiness Feedback Wiring（2026-08-31）

The window-split audit was then fed back into the parent
`dynamic_cvar_tail_cost_readiness_review` artifact. This removes the stale
interpretation that Taiwan ETF validation is simply missing when the new
window-split audit is present.

Code changes:

- `scripts/evaluate/build_group_a_plus_dynamic_cvar_tail_cost_readiness_review.py`
  now accepts `--cvar-cost-window-split`;
- the parent readiness review records
  `component_readiness.cvar_cost_window_split_2606_26625`;
- if the window-split audit is present but fails, the blocker is now
  `cvar_cost_window_split_2606_26625_failed`;
- `taiwan_etf_walkforward_validation_missing` is retained only when the
  window-split artifact is absent;
- daily pipeline order was changed so `cvar_cost_window_split_2606_26625` runs
  before `dynamic_cvar_tail_cost_readiness_review`.

Latest parent readiness state after rewiring:

- `as_of = 2026-08-31`;
- `status = blocked`;
- `component_readiness.cvar_cost_window_split_2606_26625.status =
  blocked_for_live_promotion`;
- `valid_windows = 5`;
- `tail_cost_window_split_passed = false`;
- `latest_loses_to_no_00631l_windows = 5`;
- `latest_loses_to_no_letf_windows = 4`;
- blocker retained: `dynamic_cvar_optimizer_not_implemented`;
- blocker changed from missing-validation to
  `cvar_cost_window_split_2606_26625_failed`.

Validation:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_dynamic_cvar_tail_cost_readiness_review.py
.venv/bin/python -m py_compile scripts/evaluate/build_group_a_plus_dynamic_cvar_tail_cost_readiness_review.py scripts/run/run_ncf_daily_pipeline.py tests/test_build_group_a_plus_dynamic_cvar_tail_cost_readiness_review.py tests/test_run_ncf_daily_pipeline.py
.venv/bin/python -m pytest tests/test_build_group_a_plus_dynamic_cvar_tail_cost_readiness_review.py tests/test_run_ncf_daily_pipeline.py tests/test_check_group_a_plus_daily_status.py tests/test_build_group_a_plus_research_shadow_decision_snapshot.py tests/test_evaluate_group_a_plus_2606_26625_cvar_cost_window_split.py
```

Results:

- parent readiness regenerated successfully;
- syntax check passed;
- pytest passed: `55 passed`.

Governance interpretation:

The evidence is stronger than before: GroupA+ now has a Taiwan ETF
CVaR/cost/tail window-split check for this paper, and that check fails live
promotion. This is no longer just a missing-validation blocker; it is a
measured negative promotion result.

## Cross-Index / Convergence Update（2026-08-31）

The 2606.26625 result was also propagated into the higher-level research
indexes so future reviews do not need to discover it only through this handoff.

Updated:

- `docs/GROUPA_PLUS_PDF_RESEARCH_DECISION_MATRIX_20260717.md`
- `docs/GROUPA_PLUS_SIMILAR_RESEARCH_CROSSCHECK_20260807.md`
- `docs/GROUPA_PLUS_RECENT_PAPER_IMPORT_STATUS_20260807.md`
- `group_a_plus/integrations/paper_convergence_review.py`
- `scripts/evaluate/build_group_a_plus_paper_convergence_review.py`

Convergence review changes:

- the `tail_risk_governance_not_optimizer` candidate now accepts
  `cvar_cost_window_split_2606_26625`;
- it records window-split status and fail/pass evidence;
- it adds blocker
  `cvar_cost_window_split_2606_26625_blocked_for_live_promotion` when the
  window-split audit fails;
- daily pipeline passes the window-split artifact into
  `paper_convergence_review`.

Latest regenerated convergence evidence:

- candidate: `tail_risk_governance_not_optimizer`;
- decision: `research_candidate_needs_validation`;
- blockers:
  - `optimizer_not_promoted`;
  - `dynamic_cvar_tail_cost_blocked`;
  - `asian_etf_tail_analytics_blocked`;
  - `cvar_cost_window_split_2606_26625_blocked_for_live_promotion`;
- evidence:
  - `cvar_cost_window_split_2606_26625_status = blocked_for_live_promotion`;
  - `cvar_cost_window_split_2606_26625_passed = false`;
  - `latest_loses_to_no_00631l_windows = 5`;
  - `latest_loses_to_no_letf_windows = 4`.

Regenerated:

- `report/group_a_plus/latest/paper_convergence_review.json`
- `report/group_a_plus/paper_convergence_review/history/paper_convergence_review_20260831.json`

Validation:

```bash
.venv/bin/python -m py_compile group_a_plus/integrations/paper_convergence_review.py scripts/evaluate/build_group_a_plus_paper_convergence_review.py
.venv/bin/python -m pytest tests/test_group_a_plus_paper_convergence_review.py tests/test_build_group_a_plus_paper_convergence_review.py tests/test_run_ncf_daily_pipeline.py
.venv/bin/python scripts/evaluate/build_group_a_plus_paper_convergence_review.py --as-of 2026-08-31 --output report/group_a_plus/latest/paper_convergence_review.json --history-dir report/group_a_plus/paper_convergence_review/history
```

Results:

- syntax check passed;
- pytest passed: `26 passed`;
- paper convergence regenerated successfully for `2026-08-31`.

## Rolling Tail No-Add Gate Added（2026-08-31）

The fixed-window audit above only checks 5 historical stress windows. To give
the paper's rolling CVaR-dashboard idea a live, always-current shadow signal
(not just a point-in-time backtest), a second, independent artifact was added:
a rolling 63/126/252-day CVaR/Hill no-add gate computed as of the latest
trading day.

Implemented:

- `scripts/evaluate/build_group_a_plus_2606_26625_rolling_tail_no_add_gate.py`
- `tests/test_build_group_a_plus_2606_26625_rolling_tail_no_add_gate.py`
- `report/group_a_plus/latest/2606_26625_rolling_tail_no_add_gate.json`
- `report/group_a_plus/latest/2606_26625_rolling_tail_no_add_gate.md`

Method:

- read current GroupA+ latest target weights from
  `report/group_a_plus/latest/live_signal.json`;
- for each of the `63`, `126`, `252` trailing trading-day windows, compute
  ES95/MDD for the latest strategy vs. `no_00631l_to_cash`, `no_00632r_to_cash`,
  and `no_letf_to_cash` conservative variants, plus a Hill tail-index (95%) on
  the latest strategy's own loss series;
- a window blocks `00631L.TW` (or `00632R.TW`) adds when the latest strategy's
  ES95 gap vs. the conservative variant exceeds `0.001`, or when the Hill xi
  exceeds `0.25`;
- `allow_*_add` is only `true` when zero of the three windows block.

This is a shadow monitoring gate only: it never changes target weights,
creates orders, or triggers automatic rebalance.

Latest result (`as_of = 2026-08-31`):

- `status = available_for_shadow_monitoring`;
- `block_00631l_add_windows = 3/3`, `allow_00631l_add = false`;
- `block_00632r_open_windows = 0/3`, `allow_00632r_open = true`;
- `block_any_letf_add_windows = 3/3`, `allow_any_letf_add = false`;
- `manual_review_required = true`.

Wired into:

- `scripts/run/run_ncf_daily_pipeline.py` (`rolling_tail_no_add_gate_2606_26625`
  step, runs alongside `cvar_cost_window_split_2606_26625`);
- `scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py`
  (new blocker `rolling_tail_no_add_gate_2606_26625_blocks_00631l_add` when
  `allow_00631l_add` is not `true`);
- `scripts/misc/check_group_a_plus_daily_status.py` (new
  `--rolling-tail-no-add-2606-26625` input, `Rolling Tail No-Add Gate`
  Markdown section).

Validation:

```bash
.venv/bin/python -m pytest tests/test_build_group_a_plus_2606_26625_rolling_tail_no_add_gate.py tests/test_evaluate_group_a_plus_2606_26625_cvar_cost_window_split.py tests/test_build_group_a_plus_dynamic_cvar_tail_cost_readiness_review.py tests/test_run_ncf_daily_pipeline.py tests/test_check_group_a_plus_daily_status.py tests/test_build_group_a_plus_research_shadow_decision_snapshot.py tests/test_group_a_plus_paper_convergence_review.py tests/test_build_group_a_plus_paper_convergence_review.py
```

Result: `63 passed`.

Combined 2606.26625 decision (unchanged in spirit, now with two independent
lines of evidence instead of one):

- fixed-window audit (5 historical stress windows): latest strategy loses to
  `no_00631l_to_cash` on ES95/MDD in `5/5` windows;
- rolling live gate (63/126/252-day, refreshed daily): currently blocks new
  `00631L.TW` adds in `3/3` windows, does not block `00632R.TW` opens;
- both agree the paper does not support increasing `00631L.TW` exposure right
  now; neither authorizes any live weight, order, or model change.

## CVaR-Optimizer In-Sample Upper Bound（2026-08-31）

User asked directly whether it is feasible to build the real dynamic mean-CVaR
optimizer the paper describes. Before writing one, a diagnostic-only Rockafellar-
Uryasev mean-CVaR LP was solved to size the theoretical headroom: for each of
the same 5 stress windows, find the static weights that minimize CVaR95 subject
to matching or beating the latest strategy's own achieved mean daily return in
that window, using full in-sample knowledge of the window's realized returns.

Implemented:

- `scripts/evaluate/evaluate_group_a_plus_2606_26625_cvar_optimizer_upper_bound.py`
- `tests/test_evaluate_group_a_plus_2606_26625_cvar_optimizer_upper_bound.py`
- `report/group_a_plus/latest/2606_26625_cvar_optimizer_upper_bound.json`
- `report/group_a_plus/latest/2606_26625_cvar_optimizer_upper_bound.md`

Result: the optimizer beats the latest strategy's ES95 and MDD in `5/5`
windows (mean ES95 gap `0.0118`, mean MDD gap `0.108`). But the "optimal"
in-sample weights are not economically credible:

- `covid_2020`: `00631L.TW 28.5%` + `00632R.TW 57.9%` simultaneously;
- `rate_hike_2022`: `00631L.TW 28.5%` + `00632R.TW 64.8%` simultaneously;
- `post_2023` / `recent_2024_2026`: `00631L.TW ~25-27%` + `00632R.TW ~62-65%`
  simultaneously.

The LP is holding large simultaneous positions in the 2x-long and -1x inverse
LETFs at the same time — a combination the production switch-regime logic
(`a2118_a2111_ncf_late_bull_deleverage`) never takes, because it is a
mutual-exclusivity regime switch, not a continuous blend. The LP can only
reach this "low CVaR, high return" region because it has look-ahead knowledge
of that specific window's realized price path; it is exploiting in-sample
noise in the 00631L/00632R return correlation, not a real, forward-usable
hedge. This is the textbook failure mode of an unconstrained in-sample
optimizer.

Conclusion: the reported `5/5` / large ES95-MDD gap is an artifact, not a
realistic estimate of what a walk-forward, cost-aware, regime-consistent CVaR
optimizer could deliver. It does not overturn the earlier recommendation
(memory: `feedback_overfitting_fixed_window_tuning`,
`feedback_strategy_promotion_caution`) against building a live optimizer.
Building the real thing would still need, at minimum, a mutual-exclusivity or
turnover-cost constraint between `00631L.TW` and `00632R.TW`, walk-forward
refitting, and re-testing against this same upper bound with those
constraints in place before the headroom estimate can be trusted.

Validation:

```bash
.venv/bin/python -m py_compile scripts/evaluate/evaluate_group_a_plus_2606_26625_cvar_optimizer_upper_bound.py tests/test_evaluate_group_a_plus_2606_26625_cvar_optimizer_upper_bound.py
.venv/bin/python -m pytest tests/test_evaluate_group_a_plus_2606_26625_cvar_optimizer_upper_bound.py
```

Result: `3 passed`.

This diagnostic is intentionally NOT wired into the daily pipeline: it is a
one-time feasibility question, not a recurring shadow gate. No live strategy
change, no target-weight change, no order, no rebalance.
