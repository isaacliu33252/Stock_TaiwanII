# 2608.15841 Auxiliary Head Lifecycle Audit

- Policy: `research_only_no_weight_change`
- Decision: `head_lifecycle_review_required`
- Lifecycle passed: `False`
- Promotion allowed: `False`

| ticker | head | status | full AUC | recent AUC | reasons |
|---|---|---|---:|---:|---|
| `00631L.TW` | `h20_forward_drawdown_gt5` | `redundant_candidate` | 0.658155487804878 | 0.5689285714285715 | `high_redundancy` |
| `00631L.TW` | `h20_forward_gain_gt5` | `watchlist` | 0.6033898305084746 | 0.5638233514821537 | `regime_or_decay_failed` |
| `00631L.TW` | `tail_reward_risk_score` | `redundant_candidate` | 0.6194277382905048 | 0.4398064125831821 | `recent_auc_below_floor, high_redundancy` |
| `00632R.TW` | `h20_forward_drawdown_gt5` | `watchlist` | 0.5761344537815126 | 0.5360772357723578 | `regime_or_decay_failed` |
| `00632R.TW` | `h20_forward_gain_gt5` | `retire_candidate` | 0.6670395227442207 | 0.5072463768115942 | `recent_auc_below_floor, regime_or_decay_failed` |
| `00632R.TW` | `tail_reward_risk_score` | `watchlist` | 0.6251304996271438 | 0.5084214649432042 | `recent_auc_below_floor` |
| `0050.TW` | `h20_forward_drawdown_gt5` | `redundant_candidate` | 0.7083935328517372 | 0.5260477869173521 | `regime_or_decay_failed, high_redundancy` |
| `0050.TW` | `h20_forward_gain_gt5` | `watchlist` | 0.6975530362554719 | 0.5684121621621622 | `regime_or_decay_failed` |
| `0050.TW` | `tail_reward_risk_score` | `redundant_candidate` | 0.6260803681670222 | 0.5257601351351352 | `high_redundancy` |

This audit is shadow-only and does not retire production heads.
