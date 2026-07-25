# GroupA+ Multi-Window Failure Attribution

- Source decision: `research_only_no_multi_window_pass`
- Status: `blocked`
- Candidate count: `6`
- Criteria: `{'min_pass_ratio': 1.0, 'max_final_drawdown_pct': 0.02, 'min_sharpe_delta': 0.0, 'require_mdd_nonworse': True}`

## Top Failure Reasons

- `final_value_drag`: `4`
- `max_drawdown_worse`: `3`
- `sharpe_delta`: `2`

## Candidates

- `garch_guard_frozen` pass `2/3` primary `final_value_drag` pass-ratio shortfall `0.33333333333333337`
- `garch_selector_frozen` pass `1/3` primary `max_drawdown_worse` pass-ratio shortfall `0.6666666666666667`
- `shadow_2008_candidate` pass `0/1` primary `sharpe_delta` pass-ratio shortfall `1.0`
- `best_by_final_value` pass `0/1` primary `final_value_drag` pass-ratio shortfall `1.0`
- `best_by_sharpe` pass `0/1` primary `final_value_drag` pass-ratio shortfall `1.0`
- `best_by_max_drawdown` pass `0/1` primary `final_value_drag` pass-ratio shortfall `1.0`

## Decision Boundary

- Creates orders: `False`
- Target weight change allowed: `False`
- Auto rebalance allowed: `False`
- Golden1_0531 unchanged: `True`
