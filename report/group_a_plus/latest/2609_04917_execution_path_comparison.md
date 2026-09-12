# 2609.04917 Execution Path Comparison

- status: shadow_bridge_is_best_manual_review_candidate
- best_shadow_path: turnover_bridge_shadow
- live_promotion_allowed: False

| path | joint | market impact | rebalance | turnover | execution allowed | auto rebalance |
| --- | --- | --- | --- | ---: | --- | --- |
| official | blocked | blocked | available | 0.14215824542363484 | True | False |
| same_day_shadow | blocked | blocked | missing | 0.5821315005324671 | False | None |
| turnover_bridge_shadow | blocked | blocked | ready_for_human_rebalance_review | 0.4997751330003984 | False | False |

## Decision

Turnover bridge is the best current manual-review shadow path, but it does not clear live promotion gates.
