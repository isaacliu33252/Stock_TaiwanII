# 2608.15841 Auxiliary Task Discovery Readiness

- Policy: `research_only_no_weight_change`
- Decision: `shadow_readiness_only`
- Promotion allowed: `False`
- No target-weight change: `True`

## Checks

| check | pass |
|---|---:|
| `existing_aux_heads_available` | `True` |
| `aux_head_standalone_quality_passed` | `True` |
| `live_feature_freshness_ok` | `False` |
| `quest_trader_retrained_for_group_a_plus` | `False` |
| `downstream_policy_lift_validated` | `False` |
| `purged_walk_forward_policy_impact_passed` | `True` |
| `multi_window_cost_turnover_passed` | `False` |
| `temporal_regime_stability_passed` | `False` |
| `auxiliary_head_lifecycle_passed` | `False` |
| `delayed_credit_alignment_passed` | `False` |
| `candidate_auxiliary_bank_blueprint_available` | `True` |

## Panel Metrics

### 00631L.TW

- rows: `408`
- range: `2025-01-02` to `2026-09-07`
- `h20_forward_drawdown_gt5`: rows=388 positives=164 auc=0.658155487804878 brier=0.22818518083539233
- `h20_forward_gain_gt5`: rows=388 positives=295 auc=0.6033898305084746 brier=0.2016639689587323

### 00632R.TW

- rows: `408`
- range: `2025-01-02` to `2026-09-07`
- `h20_forward_drawdown_gt5`: rows=388 positives=238 auc=0.5761344537815126 brier=0.3326174423405888
- `h20_forward_gain_gt5`: rows=388 positives=90 auc=0.6670395227442207 brier=0.19243344621524616

### 0050.TW

- rows: `407`
- range: `2025-01-02` to `2026-09-07`
- `h20_forward_drawdown_gt5`: rows=387 positives=102 auc=0.7083935328517372 brier=0.20761784220459956
- `h20_forward_gain_gt5`: rows=387 positives=236 auc=0.6975530362554719 brier=0.26079940958249065

## Policy Lift Shadow

- available: `True`
- validated: `False`
- best variant: `net_derisk`
- `downside_only`: dFV=-143779.34885287937 dSharpe=0.15067773432815335 dMDD=0.03909921129523486 joint_pass=False
- `net_derisk`: dFV=-135561.1802681191 dSharpe=0.16062440997586291 dMDD=0.03845666527262037 joint_pass=False

## Purged Walk-Forward Shadow

- available: `True`
- passed: `True`
- best score: `downside_score`
- `downside_score`: folds=4 pass_count=3 pass_fraction=0.75 passed=True
- `net_derisk_score`: folds=4 pass_count=2 pass_fraction=0.5 passed=False

## Churn / Cost Shadow

- available: `True`
- passed: `False`
- decision: `churn_cost_not_cleared`
- blockers: `negative_delta_final_value_after_costs, turnover_above_limit`

## Regime / Decay Audit

- available: `True`
- passed: `False`
- decision: `temporal_regime_stability_not_cleared`
- blockers: `unstable_auxiliary_task_slices`

## Auxiliary Head Lifecycle Audit

- available: `True`
- passed: `False`
- decision: `head_lifecycle_review_required`
- status counts: `{'redundant_candidate': 4, 'watchlist': 4, 'retire_candidate': 1}`

## Delayed Credit Audit

- available: `True`
- passed: `False`
- decision: `delayed_credit_alignment_not_cleared`

## Candidate Auxiliary Bank Blueprint

- available: `True`
- training allowed: `False`
- decision: `blocked_until_readiness_gates_pass`

This report is a QUESTrader-inspired shadow/readiness gate only.
