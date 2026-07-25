# GroupA+ Rebalance Review Decision Record（2026-07-20）

## Scope

This record summarizes the 2026-07-20 rebalance review built from:

- `report/group_a_plus/latest/live_signal_20260720_estimate.json`
- `report/group_a_plus/latest/rebalance_review_20260720.json`
- `report/group_a_plus/latest/heterogeneous_vol_regime_advisory.json`
- `results/group_a_release_Golden1_0531.json`
- `C:\Users\isaac\Downloads\2606.30997.pdf`

## Post-Refresh Addendum（2026-07-18 15:15）

A later full 2026-07-20 pipeline run refreshed data through the 2026-07-17
market date and supersedes the stale-source details below.

Authoritative final record:

- `docs/GROUPA_PLUS_20260720_FULL_PIPELINE_FINAL_DECISION_RECORD.md`

Fresh outputs:

- `results/ncf_daily_pipeline_20260720.json`
- `results/group_a_plus_live_signal_v2_20260720.json`
- `results/group_a_plus_daily_status_20260720.json`
- `report/group_a_plus/latest/dynamic_cvar_tail_cost_readiness_review.json`
- `report/group_a_plus/latest/research_shadow_decision_snapshot.json`
- `report/group_a_plus/latest/deployment_consistency_review.json`
- `results/group_a_plus_promotion_gate_20260720.json`

Post-refresh changes:

- `execution_allowed = true`
- `source_freshness = ok`
- `execution_guard_reasons = []`
- daily status improved from `block` to `warn`

This does not authorize automatic trading. The final decision remains:

- do not auto-rebalance;
- do not add `00631L`;
- do not open a direct `00632R` hedge;
- do not change Golden1_0531;
- require manual review before any broker-actionable change.

Reason: stale source blockers were resolved, but governance layers still block
auto rebalance and target-weight changes:

- dynamic CVaR tail/cost readiness: `blocked`
- research shadow decision snapshot: `blocked`
- deployment consistency: `manual_review_required`
- promotion gate: `blocked_multi_window`

## Strategy

- Active strategy: `a2118_a2111_ncf_late_bull_deleverage`
- Execution regime: `golden1`
- Requested as-of date: `2026-07-20`
- Actual data date: `2026-07-17`

Reference target weights:

| asset | weight |
| --- | ---: |
| `0050.TW` | 50% |
| `00631L.TW` | 20% |
| `00632R.TW` | 0% |
| `00679B.TWO` | 0% |
| cash | 30% |

## Decision

Do not auto-rebalance for `2026-07-20`.

Current decision fields:

- `auto_rebalance_allowed = false`
- `manual_review_required = true`
- `allow_00631l_add = false`
- `target_weight_change_allowed = false`
- `active_allocation_impact = none`

## Blocking Reasons

Historical blockers from the earlier estimate:

- Required strategy source is stale or missing: `institutional_0050`.
- NCF live overlay is skipped because panel dates are `2026-07-16` while actual data date is `2026-07-17`.
- Existing `execution_plan.json` is dated `2026-07-15`, so it is stale versus the `2026-07-17` live estimate data.
- Heterogeneous volatility advisory is high and recommends avoiding `00631L` adds until manual review.

Post-refresh blockers are governance blockers, not stale-source blockers. See
`docs/GROUPA_PLUS_20260720_FULL_PIPELINE_FINAL_DECISION_RECORD.md`.

## 2606.30997 Concepts Imported

Only execution-governance concepts were imported:

- Cash is an active risk buffer, not a leftover.
- Rebalance should be previewed before apply.
- Weight drift should be reviewed before execution.
- `00631L` add should be gated by objective/risk/freshness review.
- Turnover and redeployment should be reviewed before execution.

Not imported:

- Chronos foundation model branch
- DRL / PPO / MoE live trading model
- tax-aware LoRA personalization
- natural language goal parser

## Practical Instruction

Use the target weights as reference only.

Before any real trade:

1. Use the post-refresh outputs listed in the addendum.
2. Rebuild a broker-actionable execution plan only with real holdings and real
   cash balance.
3. Execute only after manual confirmation.

Until then:

- Do not auto-add `00631L`.
- Do not change GroupA+ latest strategy weights.
- Do not change `Golden1_0531`.
