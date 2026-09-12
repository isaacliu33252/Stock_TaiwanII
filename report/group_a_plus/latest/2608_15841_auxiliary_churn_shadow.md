# 2608.15841 Auxiliary Churn Shadow

- Policy: `research_only_no_weight_change`
- Decision: `churn_cost_not_cleared`
- Promotion allowed: `False`
- Cost/turnover passed: `False`
- Blockers: `negative_delta_final_value_after_costs, turnover_above_limit`

| variant | dFV | dSharpe | dMDD | cost | turnover | rebalances | score>0 | missed-upside days | pass |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `downside_only` | -143779.34885287937 | 0.15067773432815335 | 0.03909921129523486 | 12271.540053610344 | 5147168.743137188 | 246 | 250 | 201 | `False` |
| `net_derisk` | -135561.1802681191 | 0.16062440997586291 | 0.03845666527262037 | 10739.774791952295 | 4516937.692409008 | 122 | 104 | 85 | `False` |

This is a research-only gate. It audits whether existing auxiliary heads improve realized portfolio outcomes after costs.
