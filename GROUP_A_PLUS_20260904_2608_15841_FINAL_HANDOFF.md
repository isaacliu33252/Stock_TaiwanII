# GroupA+ 2608.15841 Final Handoff - 2026-09-04

## Scope

- Paper: `C:\Users\isaac\Downloads\2608.15841_self_supervised_auxiliary_task_discovery_stable_rl_stock_trading.pdf`
- Topic: Self-supervised auxiliary task discovery / QUESTrader for stable RL stock trading.
- User request: analyze whether advantages can be imported into GroupA+ / latest strategy, continue until useful points are handled, then leave detailed handoff.
- Final decision: all safely importable advantages were imported as research-only shadow/gate reports. No production strategy change was made.

## Final Production Decision

- `changes_latest_strategy=false`
- `changes_golden1_0531=false`
- `changes_golden2_0830=false`
- `promotion_allowed=false`
- `training_allowed=false`
- No target weights changed.
- No execution permission changed.
- No order generation changed.

Reason: current evidence fails policy-lift, cost/turnover, temporal/regime stability, lifecycle, and delayed-credit gates.

## Paper Concepts Reviewed

The paper proposes QUESTrader:

- PPO trading policy with auxiliary General Value Function heads.
- A question network learns cumulants and discounts, rather than using only fixed auxiliary labels.
- Non-myopic meta-gradient assigns delayed credit to auxiliary tasks through K inner PPO updates.
- Ablation suggests moderate auxiliary question banks are preferable:
  - `dq` roughly `16`, `32`, `64`
  - K roughly `10`, `20`
  - larger banks such as 128 risk redundancy/noise

Direct production transfer is blocked because:

- Paper environment is multi-stock baskets, not GroupA+ ETFs.
- It uses academic assumptions such as zero slippage / negligible market impact.
- It requires a fresh PPO/GVF training stack.
- It does not validate against GroupA+ current ETF strategy, execution rules, cash floor, inverse ETF behavior, NCF freshness, or signed-review governance.

## Imported Research-Only Components

### 1. Auxiliary Task Discovery Readiness Gate

- Script:
  - `scripts/evaluate/build_group_a_plus_2608_15841_auxiliary_task_discovery_readiness.py`
- Outputs:
  - `report/group_a_plus/latest/2608_15841_auxiliary_task_discovery_readiness.json`
  - `report/group_a_plus/latest/2608_15841_auxiliary_task_discovery_readiness.md`
- Purpose:
  - Consolidates all 2608.15841-derived gates.
  - Blocks promotion unless standalone quality, policy lift, purged WF, cost/turnover, regime stability, lifecycle, delayed credit, freshness, and blueprint availability are acceptable.

Latest checks:

- `existing_aux_heads_available=true`
- `aux_head_standalone_quality_passed=true`
- `live_feature_freshness_ok=false`
- `quest_trader_retrained_for_group_a_plus=false`
- `downstream_policy_lift_validated=false`
- `purged_walk_forward_policy_impact_passed=true`
- `multi_window_cost_turnover_passed=false`
- `temporal_regime_stability_passed=false`
- `auxiliary_head_lifecycle_passed=false`
- `delayed_credit_alignment_passed=false`
- `candidate_auxiliary_bank_blueprint_available=true`

Current blockers:

- `live_feature_freshness_ok`
- `quest_trader_retrained_for_group_a_plus`
- `downstream_policy_lift_validated`
- `multi_window_cost_turnover_passed`
- `temporal_regime_stability_passed`
- `auxiliary_head_lifecycle_passed`
- `delayed_credit_alignment_passed`

### 2. Purged Walk-Forward Auxiliary Validation

- Script:
  - `scripts/evaluate/evaluate_group_a_plus_2608_15841_auxiliary_purged_walkforward.py`
- Outputs:
  - `report/group_a_plus/latest/2608_15841_auxiliary_purged_walkforward.json`
  - `report/group_a_plus/latest/2608_15841_auxiliary_purged_walkforward.md`
- Purpose:
  - Prevents forward-label leakage and checks whether high auxiliary scores separate future gain/drawdown behavior.

Latest result:

- `purged_walk_forward_policy_impact_passed=true`
- `downside_score`: 4 folds, 3 pass, pass fraction `0.75`
- `net_derisk_score`: 4 folds, 2 pass, pass fraction `0.50`

This is a positive research signal but not enough for production because other gates fail.

### 3. Policy-Lift Shadow With Simulation Diagnostics

- Updated script:
  - `scripts/evaluate/evaluate_ncf_downside_upside_net_derisk_score.py`
- Output:
  - `report/group_a_plus/latest/2608_15841_existing_aux_heads_policy_lift_shadow.json`
- Added fields:
  - `simulation.transaction_cost`
  - `simulation.turnover_value`
  - `simulation.rebalance_count`
  - `score_behavior.golden1_days_score_gt_0`
  - `score_behavior.golden1_score_change_days`
  - `score_behavior.missed_upside_proxy_days`
  - forward-gain comparison during active vs inactive de-risk periods

Latest full-window result, 2025-01-02 to 2026-09-03:

- Baseline final value: `2089507.73`
- `downside_only`:
  - final value delta `-141309.18`
  - Sharpe delta `+0.1385`
  - max drawdown delta `+0.0389`
- `net_derisk`:
  - final value delta `-135378.51`
  - Sharpe delta `+0.1474`
  - max drawdown delta `+0.0382`

Interpretation:

- Risk metrics improve, but final value loss is too large.
- This blocks strategy promotion.

### 4. Churn / Cost Shadow Gate

- Script:
  - `scripts/evaluate/build_group_a_plus_2608_15841_auxiliary_churn_shadow.py`
- Outputs:
  - `report/group_a_plus/latest/2608_15841_auxiliary_churn_shadow.json`
  - `report/group_a_plus/latest/2608_15841_auxiliary_churn_shadow.md`
- Purpose:
  - Checks whether auxiliary-head-driven de-risking pays for its turnover and transaction costs.

Latest result:

- `multi_window_cost_turnover_passed=false`
- Decision: `churn_cost_not_cleared`
- Blockers:
  - `negative_delta_final_value_after_costs`
  - `turnover_above_limit`

Variant details:

- `downside_only`:
  - turnover `5183826.13`
  - transaction cost `12369.40`
  - rebalances `250`
  - missed-upside proxy days `207`
- `net_derisk`:
  - turnover `4516457.21`
  - transaction cost `10739.21`
  - rebalances `124`
  - missed-upside proxy days `87`

### 5. Regime / Time-Decay Stability Audit

- Script:
  - `scripts/evaluate/build_group_a_plus_2608_15841_auxiliary_regime_decay_audit.py`
- Outputs:
  - `report/group_a_plus/latest/2608_15841_auxiliary_regime_decay_audit.json`
  - `report/group_a_plus/latest/2608_15841_auxiliary_regime_decay_audit.md`
- Purpose:
  - Checks first-half / second-half / recent-126 / direction / confidence / tail-score slices.

Latest result:

- `temporal_regime_stability_passed=false`
- Decision: `temporal_regime_stability_not_cleared`
- Blocker:
  - `unstable_auxiliary_task_slices`

Key failed slices:

- `00631L.TW h20_forward_gain_gt5`:
  - recent AUC `0.5721`
  - weak slices: `first_half`, `direction_down`, `tail_score_low`
- `00632R.TW h20_forward_drawdown_gt5`:
  - recent AUC `0.5388`
  - weak slices: `first_half`, `direction_up`, `confidence_low`, `tail_score_high`
- `00632R.TW h20_forward_gain_gt5`:
  - recent AUC `0.4943`
  - below floor
- `0050.TW h20_forward_drawdown_gt5`:
  - recent AUC `0.5213`
  - second-half AUC decay `0.1696`
- `0050.TW h20_forward_gain_gt5`:
  - second-half AUC decay `0.1865`

### 6. Candidate Auxiliary Bank Blueprint

- Script:
  - `scripts/evaluate/build_group_a_plus_2608_15841_candidate_auxiliary_bank_blueprint.py`
- Outputs:
  - `report/group_a_plus/latest/2608_15841_candidate_auxiliary_bank_blueprint.json`
  - `report/group_a_plus/latest/2608_15841_candidate_auxiliary_bank_blueprint.md`
- Purpose:
  - Converts the paper's GVF question-bank concept into a constrained future offline experiment spec.
  - Does not train a model.

Latest result:

- `training_allowed=false`
- `promotion_allowed=false`
- Decision: `blocked_until_readiness_gates_pass`

Candidate grid:

- `gvf_bank_16_k10`
- `gvf_bank_32_k10`
- `gvf_bank_32_k20`
- `gvf_bank_64_k20`

Hard rejections:

- standalone-AUC-only promotion
- high turnover / score churn
- weak recent or regime slices
- unbounded auxiliary question count
- zero-slippage / negligible-impact assumptions for live decisions

### 7. Auxiliary Head Lifecycle / Redundancy / Retirement Audit

- Script:
  - `scripts/evaluate/build_group_a_plus_2608_15841_auxiliary_lifecycle_audit.py`
- Outputs:
  - `report/group_a_plus/latest/2608_15841_auxiliary_lifecycle_audit.json`
  - `report/group_a_plus/latest/2608_15841_auxiliary_lifecycle_audit.md`
- Purpose:
  - Classifies fixed NCF auxiliary heads into `keep_shadow`, `watchlist`, `retire_candidate`, or `redundant_candidate`.
  - Does not actually retire production heads.

Latest result:

- `head_lifecycle_passed=false`
- Status counts:
  - `redundant_candidate=4`
  - `watchlist=4`
  - `retire_candidate=1`

Most important retirement candidate:

- `00632R.TW h20_forward_gain_gt5`
  - status `retire_candidate`
  - recent AUC `0.4943`
  - reasons:
    - `recent_auc_below_floor`
    - `regime_or_decay_failed`

Other notable warnings:

- `00631L.TW tail_reward_risk_score`:
  - status `redundant_candidate`
  - recent AUC `0.4134`
- `0050.TW tail_reward_risk_score`:
  - status `redundant_candidate`
  - recent AUC `0.5172`

### 8. Delayed-Credit Audit

- Script:
  - `scripts/evaluate/build_group_a_plus_2608_15841_delayed_credit_audit.py`
- Outputs:
  - `report/group_a_plus/latest/2608_15841_delayed_credit_audit.json`
  - `report/group_a_plus/latest/2608_15841_delayed_credit_audit.md`
- Purpose:
  - Approximates the paper's non-myopic delayed auxiliary contribution concept using available GroupA+ panel labels.
  - Checks h1/h5/h20 alignment and h20 forward gain/drawdown quartile separation.
  - Does not implement a true meta-gradient PPO/GVF unroll.

Latest result:

- `delayed_credit_passed=false`
- Decision: `delayed_credit_alignment_not_cleared`
- Blocker:
  - `delayed_credit_alignment_failed`

Failed heads:

- `00632R.TW direction_prob`: `h20_direction_auc_below_floor`
- `00632R.TW gain_prob`: `h20_direction_auc_below_floor`
- `00632R.TW tail_reward_risk_score`: `h20_direction_auc_below_floor`

Interpretation:

- 00632R auxiliary heads do not currently provide enough delayed h20 direction evidence to support strategy changes.

## Pipeline Wiring

The following best-effort research steps are now in `scripts/run/run_ncf_daily_pipeline.py`:

- `auxiliary_policy_lift_shadow_2608_15841`
- `auxiliary_churn_shadow_2608_15841`
- `auxiliary_purged_walkforward_2608_15841`
- `auxiliary_regime_decay_audit_2608_15841`
- `auxiliary_lifecycle_audit_2608_15841`
- `delayed_credit_audit_2608_15841`
- `candidate_auxiliary_bank_blueprint_2608_15841`
- `auxiliary_task_discovery_readiness_2608_15841`

These are best-effort and diagnostic only. They must not block production daily signal generation or alter live target weights.

Manifest artifact paths were added for:

- policy-lift shadow
- churn shadow JSON/MD
- purged walk-forward JSON/MD
- regime/decay audit JSON/MD
- lifecycle audit JSON/MD
- delayed-credit audit JSON/MD
- candidate auxiliary bank blueprint JSON/MD
- readiness JSON/MD

## Paper Convergence Review

The 2608.15841 readiness report is included in:

- `report/group_a_plus/latest/paper_convergence_review.json`
- `report/group_a_plus/paper_convergence_review/history/paper_convergence_review_20260904.json`

Latest convergence top candidate remains unrelated:

- top: `defensive_cash_floor_high_risk_state`
- decision: `best_candidate_but_signed_review_blocked`

2608.15841 remains a research candidate, not a production candidate.

## Verification

Latest focused test command:

```bash
.venv/bin/python -m pytest tests/test_build_group_a_plus_2608_15841_delayed_credit_audit.py tests/test_build_group_a_plus_2608_15841_auxiliary_lifecycle_audit.py tests/test_build_group_a_plus_2608_15841_candidate_auxiliary_bank_blueprint.py tests/test_build_group_a_plus_2608_15841_auxiliary_regime_decay_audit.py tests/test_evaluate_ncf_downside_upside_net_derisk_score.py tests/test_build_group_a_plus_2608_15841_auxiliary_churn_shadow.py tests/test_build_group_a_plus_2608_15841_auxiliary_task_discovery_readiness.py tests/test_run_ncf_daily_pipeline.py -q
```

Result:

- `40 passed`

Latest reports regenerated on 2026-09-04 using 2026-09-03 NCF panels:

- `report/group_a_plus/latest/2608_15841_existing_aux_heads_policy_lift_shadow.json`
- `report/group_a_plus/latest/2608_15841_auxiliary_churn_shadow.json`
- `report/group_a_plus/latest/2608_15841_auxiliary_purged_walkforward.json`
- `report/group_a_plus/latest/2608_15841_auxiliary_regime_decay_audit.json`
- `report/group_a_plus/latest/2608_15841_auxiliary_lifecycle_audit.json`
- `report/group_a_plus/latest/2608_15841_delayed_credit_audit.json`
- `report/group_a_plus/latest/2608_15841_candidate_auxiliary_bank_blueprint.json`
- `report/group_a_plus/latest/2608_15841_auxiliary_task_discovery_readiness.json`
- `report/group_a_plus/latest/paper_convergence_review.json`

## Do Not Do Without Fresh Validation

- Do not promote QUESTrader concepts into latest strategy weights.
- Do not train or enable learned GVF question banks while readiness blockers remain.
- Do not retire production heads directly from lifecycle audit alone.
- Do not use standalone AUC as a promotion criterion.
- Do not assume zero slippage / negligible market impact for 00631L or 00632R.
- Do not alter Golden1_0531 or Golden2_0830 artifacts based on this paper.

## Next Possible Research Step

Only if continuing research, the next controlled step is:

- Build an offline fixed-head-vs-candidate-bank A/B harness.
- Keep candidate banks limited to `16` and `32` first.
- Use purged walk-forward splits.
- Require final value, Sharpe, max drawdown, turnover, regime stability, lifecycle, delayed credit, and freshness gates all to pass.
- Keep every output under `report/group_a_plus/latest`.
- No production pointer changes until separate manual review.
