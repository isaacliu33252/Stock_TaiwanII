# 2609.08106 Adoption Matrix

- generated_at: `2026-09-12T07:29:04`
- policy: `research_summary_no_orders_no_live_weight_change`
- latest_strategy: `a2118_a2111_ncf_late_bull_deleverage`
- adopt_into_latest_strategy_now: `False`
- advisory_import_allowed: `True`
- live_weight_change_allowed: `False`
- forward_gate_passed: `False`
- forward_samples: `2`
- triggered_forward_samples: `0`
- realized_forward_samples: `0`

| candidate | verdict | advisory | live weights | reason |
|---|---|---:|---:|---|
| nystrom_attention_replacement | broad_universe_research_only | `False` | `False` | Current GroupA++ is a small ETF sleeve; Nystrom's practical edge is scaling large cross-sections, not improving a 6-asset live allocation directly. |
| graph_or_topk_sparse_masks | reject | `False` | `False` | The paper's useful cross-sectional signal is near-global and low-rank; hard sparsification is the wrong import path. |
| cross_asset_complementarity_score | advisory_ready | `True` | `False` | The anti-correlation/complementarity insight fits the current 0050/00631L/bond sleeve as a daily diagnostic without mutating target weights. |
| mom5_gated_bond_sleeve | continue_forward_shadow | `True` | `False` | Historical mom5-gated tests, latest-target replay, and parameter sweep are encouraging, but live forward evidence is still insufficient. |

## Decision

- Import the complementarity score into advisory/reporting only.
- Continue daily forward shadow logging with realized after-cost attribution.
- Do not change latest GroupA++ target weights, execution plans, or orders.
- Do not import graph masks, top-K masks, or a Nystrom replacement into the current small live sleeve.
- `golden1_0531` and `golden2_0830` are lockdown comparators.
