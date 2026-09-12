# GroupA+ 2608.15841 Auxiliary Task Discovery Handoff - 2026-09-04

## Scope

- Paper: `2608.15841_self_supervised_auxiliary_task_discovery_stable_rl_stock_trading.pdf`
- Request: analyze whether useful ideas can be imported into GroupA+ latest strategy.
- Decision: research-only import completed; no target-weight, Golden1_0531, Golden2_0830, execution permission, or order change.

## Paper Takeaways

- QUESTrader learns self-supervised GVF auxiliary tasks with a question network and uses them to stabilize PPO stock-trading policies.
- Transferable point for this codebase is not the full PPO architecture. The useful point is a validation framework: auxiliary heads must prove standalone signal quality and downstream portfolio improvement after costs.
- The paper's empirical environment differs from GroupA+: stock baskets, Yahoo daily close data, zero-slippage / negligible-market-impact assumptions, and a dedicated PPO policy. Direct promotion to GroupA+ ETF weights is not justified.

## Imported Research-Only Components

- Added auxiliary-task readiness gate:
  - `scripts/evaluate/build_group_a_plus_2608_15841_auxiliary_task_discovery_readiness.py`
  - Output:
    - `report/group_a_plus/latest/2608_15841_auxiliary_task_discovery_readiness.json`
    - `report/group_a_plus/latest/2608_15841_auxiliary_task_discovery_readiness.md`
- Added purged walk-forward auxiliary policy-impact validation:
  - `scripts/evaluate/evaluate_group_a_plus_2608_15841_auxiliary_purged_walkforward.py`
  - Output:
    - `report/group_a_plus/latest/2608_15841_auxiliary_purged_walkforward.json`
    - `report/group_a_plus/latest/2608_15841_auxiliary_purged_walkforward.md`
- Extended existing NCF downside/upside net de-risk evaluator with:
  - transaction cost
  - turnover value
  - rebalance count
  - golden1 score churn
  - missed-upside proxy using `forward_gain_h20`
- Added auxiliary churn/cost shadow gate:
  - `scripts/evaluate/build_group_a_plus_2608_15841_auxiliary_churn_shadow.py`
  - Output:
    - `report/group_a_plus/latest/2608_15841_auxiliary_churn_shadow.json`
    - `report/group_a_plus/latest/2608_15841_auxiliary_churn_shadow.md`
- Added auxiliary regime/decay stability audit:
  - `scripts/evaluate/build_group_a_plus_2608_15841_auxiliary_regime_decay_audit.py`
  - Output:
    - `report/group_a_plus/latest/2608_15841_auxiliary_regime_decay_audit.json`
    - `report/group_a_plus/latest/2608_15841_auxiliary_regime_decay_audit.md`
- Added candidate auxiliary bank blueprint / admission gate:
  - `scripts/evaluate/build_group_a_plus_2608_15841_candidate_auxiliary_bank_blueprint.py`
  - Output:
    - `report/group_a_plus/latest/2608_15841_candidate_auxiliary_bank_blueprint.json`
    - `report/group_a_plus/latest/2608_15841_candidate_auxiliary_bank_blueprint.md`
  - This is only a future offline-research spec. It does not train a model.
- Added auxiliary head lifecycle / redundancy / retirement audit:
  - `scripts/evaluate/build_group_a_plus_2608_15841_auxiliary_lifecycle_audit.py`
  - Output:
    - `report/group_a_plus/latest/2608_15841_auxiliary_lifecycle_audit.json`
    - `report/group_a_plus/latest/2608_15841_auxiliary_lifecycle_audit.md`
  - This is only a warning layer. It does not retire production heads.
- Added delayed-credit auxiliary audit:
  - `scripts/evaluate/build_group_a_plus_2608_15841_delayed_credit_audit.py`
  - Output:
    - `report/group_a_plus/latest/2608_15841_delayed_credit_audit.json`
    - `report/group_a_plus/latest/2608_15841_delayed_credit_audit.md`
  - This approximates the paper's delayed auxiliary-task contribution idea
    with h1/h5/h20 direction alignment and h20 forward gain/drawdown quartile
    separation. It does not train a PPO or GVF question network.
- Wired these into daily NCF pipeline as best-effort research steps:
  - `auxiliary_policy_lift_shadow_2608_15841`
  - `auxiliary_churn_shadow_2608_15841`
  - `auxiliary_purged_walkforward_2608_15841`
  - `auxiliary_regime_decay_audit_2608_15841`
  - `auxiliary_lifecycle_audit_2608_15841`
  - `delayed_credit_audit_2608_15841`
  - `candidate_auxiliary_bank_blueprint_2608_15841`
  - `auxiliary_task_discovery_readiness_2608_15841`
- Wired readiness into paper convergence review:
  - `report/group_a_plus/latest/paper_convergence_review.json`
  - `report/group_a_plus/paper_convergence_review/history/paper_convergence_review_20260904.json`

## Latest 2026-09-03 Panel Results

- Existing auxiliary heads are available and standalone metrics pass the readiness threshold.
- Purged walk-forward policy-impact gate passes overall:
  - `downside_score`: 4 folds, 3 pass, pass fraction 0.75
  - `net_derisk_score`: 4 folds, 2 pass, pass fraction 0.50
- Downstream full-window policy lift still fails because final value is negative versus baseline:
  - `downside_only`: final value delta `-141309.18`, Sharpe delta `+0.1385`, max drawdown delta `+0.0389`
  - `net_derisk`: final value delta `-135378.51`, Sharpe delta `+0.1474`, max drawdown delta `+0.0382`
- Churn/cost gate fails:
  - `downside_only`: turnover `5183826.13`, transaction cost `12369.40`, rebalances `250`, missed-upside proxy days `207`
  - `net_derisk`: turnover `4516457.21`, transaction cost `10739.21`, rebalances `124`, missed-upside proxy days `87`
- Regime/decay audit fails:
  - `00631L.TW h20_forward_gain_gt5`: recent AUC `0.5721`, but weak slices include `first_half`, `direction_down`, `tail_score_low`
  - `00632R.TW h20_forward_drawdown_gt5`: recent AUC `0.5388`, but weak slices include `first_half`, `direction_up`, `confidence_low`, `tail_score_high`
  - `00632R.TW h20_forward_gain_gt5`: recent AUC `0.4943`, below floor
  - `0050.TW h20_forward_drawdown_gt5`: recent AUC `0.5213`, second-half AUC decay `0.1696`
  - `0050.TW h20_forward_gain_gt5`: second-half AUC decay `0.1865`
- Candidate auxiliary bank blueprint generated:
  - `training_allowed=false`
  - candidate banks:
    - `gvf_bank_16_k10`
    - `gvf_bank_32_k10`
    - `gvf_bank_32_k20`
    - `gvf_bank_64_k20`
  - hard rejections include standalone-AUC-only promotion, high turnover/churn,
    weak recent/regime slices, unbounded question counts, and zero-slippage
    assumptions for live decisions.
- Auxiliary head lifecycle audit fails:
  - status counts: `redundant_candidate=4`, `watchlist=4`, `retire_candidate=1`
  - `00632R.TW h20_forward_gain_gt5`: `retire_candidate`, recent AUC `0.4943`,
    reasons `recent_auc_below_floor`, `regime_or_decay_failed`
  - `00631L.TW h20_forward_drawdown_gt5`: `redundant_candidate`, recent AUC
    `0.5786`, reason `high_redundancy`
  - `00631L.TW h20_forward_gain_gt5`: `watchlist`, recent AUC `0.5721`,
    reason `regime_or_decay_failed`
  - `00631L.TW tail_reward_risk_score`: `redundant_candidate`, recent AUC
    `0.4134`, reasons `recent_auc_below_floor`, `high_redundancy`
  - `00632R.TW h20_forward_drawdown_gt5`: `watchlist`, recent AUC `0.5388`,
    reason `regime_or_decay_failed`
  - `00632R.TW tail_reward_risk_score`: `watchlist`, recent AUC `0.5135`,
    reason `recent_auc_below_floor`
  - `0050.TW h20_forward_drawdown_gt5`: `redundant_candidate`, recent AUC
    `0.5213`, reasons `regime_or_decay_failed`, `high_redundancy`
  - `0050.TW h20_forward_gain_gt5`: `watchlist`, recent AUC `0.5782`,
    reason `regime_or_decay_failed`
  - `0050.TW tail_reward_risk_score`: `redundant_candidate`, recent AUC
    `0.5172`, reasons `recent_auc_below_floor`, `high_redundancy`
- Delayed-credit audit fails:
  - blocker: `delayed_credit_alignment_failed`
  - failed heads:
    - `00632R.TW direction_prob`: `h20_direction_auc_below_floor`
    - `00632R.TW gain_prob`: `h20_direction_auc_below_floor`
    - `00632R.TW tail_reward_risk_score`: `h20_direction_auc_below_floor`
  - Interpretation: 00632R auxiliary heads do not currently provide enough
    delayed h20 direction evidence to support strategy changes.
- Current readiness blockers:
  - `live_feature_freshness_ok`
  - `quest_trader_retrained_for_group_a_plus`
  - `downstream_policy_lift_validated`
  - `multi_window_cost_turnover_passed`
  - `temporal_regime_stability_passed`
  - `auxiliary_head_lifecycle_passed`
  - `delayed_credit_alignment_passed`
- Current readiness non-blocking positive:
  - `candidate_auxiliary_bank_blueprint_available=true`

## Current Decision

- `promotion_allowed=false`
- `changes_latest_strategy=false`
- `changes_golden1_0531=false`
- `changes_golden2_0830=false`
- The useful parts have been imported as shadow/readiness gates only.
- No evidence supports changing production GroupA+ weights from this paper today.

## Remaining Research-Only References

- Full QUESTrader-style learned auxiliary task bank is still not imported. It would require a separate GroupA+ ETF training environment and purged walk-forward validation.
- The blueprint now defines the constrained candidate bank grid and admission
  tests, but training remains blocked until readiness gates clear.
- The lifecycle audit now identifies weak/redundant heads, but any actual
  retirement requires a separate policy-impact backtest and manual review.
- The delayed-credit audit now checks the paper's non-myopic idea with
  available GroupA+ panel labels. Full meta-gradient credit assignment remains
  future research only.
- Reasonable future grid, if research continues:
  - GVF question counts: `16`, `32`, `64`
  - meta unroll length: `10`, `20`
  - hard constraints: no forward-label leakage, realistic costs, turnover cap, multi-window final-value nonnegative versus baseline
- Do not promote on standalone AUC alone. Promotion requires portfolio-level lift after costs and fresh live features.

## Verification

- Focused tests:
  - `.venv/bin/python -m pytest tests/test_evaluate_ncf_downside_upside_net_derisk_score.py tests/test_build_group_a_plus_2608_15841_auxiliary_churn_shadow.py tests/test_build_group_a_plus_2608_15841_auxiliary_task_discovery_readiness.py tests/test_run_ncf_daily_pipeline.py -q`
  - Result: `31 passed`
  - `.venv/bin/python -m pytest tests/test_build_group_a_plus_2608_15841_auxiliary_regime_decay_audit.py tests/test_evaluate_ncf_downside_upside_net_derisk_score.py tests/test_build_group_a_plus_2608_15841_auxiliary_churn_shadow.py tests/test_build_group_a_plus_2608_15841_auxiliary_task_discovery_readiness.py tests/test_run_ncf_daily_pipeline.py -q`
  - Result: `33 passed`
  - `.venv/bin/python -m pytest tests/test_build_group_a_plus_2608_15841_candidate_auxiliary_bank_blueprint.py tests/test_build_group_a_plus_2608_15841_auxiliary_regime_decay_audit.py tests/test_evaluate_ncf_downside_upside_net_derisk_score.py tests/test_build_group_a_plus_2608_15841_auxiliary_churn_shadow.py tests/test_build_group_a_plus_2608_15841_auxiliary_task_discovery_readiness.py tests/test_run_ncf_daily_pipeline.py -q`
  - Result: `35 passed`
  - `.venv/bin/python -m pytest tests/test_build_group_a_plus_2608_15841_auxiliary_lifecycle_audit.py tests/test_build_group_a_plus_2608_15841_candidate_auxiliary_bank_blueprint.py tests/test_build_group_a_plus_2608_15841_auxiliary_regime_decay_audit.py tests/test_evaluate_ncf_downside_upside_net_derisk_score.py tests/test_build_group_a_plus_2608_15841_auxiliary_churn_shadow.py tests/test_build_group_a_plus_2608_15841_auxiliary_task_discovery_readiness.py tests/test_run_ncf_daily_pipeline.py -q`
  - Result: `38 passed`
  - `.venv/bin/python -m pytest tests/test_build_group_a_plus_2608_15841_delayed_credit_audit.py tests/test_build_group_a_plus_2608_15841_auxiliary_lifecycle_audit.py tests/test_build_group_a_plus_2608_15841_candidate_auxiliary_bank_blueprint.py tests/test_build_group_a_plus_2608_15841_auxiliary_regime_decay_audit.py tests/test_evaluate_ncf_downside_upside_net_derisk_score.py tests/test_build_group_a_plus_2608_15841_auxiliary_churn_shadow.py tests/test_build_group_a_plus_2608_15841_auxiliary_task_discovery_readiness.py tests/test_run_ncf_daily_pipeline.py -q`
  - Result: `40 passed`
