# GroupA+ Golden2 Promotion Candidate Review

- Status: `blocked_prepare_multi_window_backtest`
- Policy: `diagnostic_only_no_strategy_change_no_weight_change_no_orders`
- Compatible candidates: `4`
- Daily status: `ok`
- Promotion gate: `blocked_model_gates_manual_approval_pending`
- Multi-window decision: `research_only_no_multi_window_pass`
- CVaR forward passed: `None`

## Candidate Compatibility

| file | window | metrics | candidate rows | compatible | reason |
|---|---|---:|---:|---|---|
| `last_ppo_group_a_backtest_golden2_0830.json` | `-` | `False` | `0` | `False` | no candidate rows for compare_candidates |
| `group_a_plus_latest_backtest_2024_2026_after_20260813_refresh.json` | `2024-01-02..2026-08-13` | `True` | `0` | `False` | no candidate rows for compare_candidates |
| `group_a_plus_latest_backtest_2025_2026_after_20260813_refresh.json` | `2025-01-02..2026-08-13` | `True` | `0` | `False` | no candidate rows for compare_candidates |
| `2020_covid.json` | `2020-01-02..2020-12-31` | `True` | `1` | `True` | candidate rows available |
| `2022_rate_hike.json` | `2022-01-03..2022-12-30` | `True` | `1` | `True` | candidate rows available |
| `active_2025_2026.json` | `2025-01-02..2026-09-10` | `True` | `1` | `True` | candidate rows available |
| `live_2024_2026.json` | `2024-01-02..2026-09-10` | `True` | `1` | `True` | candidate rows available |

## Blockers

- `promotion_metrics_gate_failed`
- `panel_drift_gate_failed`
- `multi_window_gate_failed`
- `no_multi_window_candidate_available`
- `dfl_latest_audit_not_promotion_ready`
- `dynamic_cvar_forward_validation_blocks_live_weight_change`

## Next Required Work

- candidate rows are available (4 compatible files); remaining work is the blockers below
- resolve the promotion_gate metrics_gate failure before reconsidering golden2
- resolve the promotion_gate panel_drift_gate failure before reconsidering golden2
- resolve the promotion_gate multi_window_gate failure before reconsidering golden2
- golden2 does not pass the multi-window stability gate (see golden2_multi_window_gate.json); it must reach multi_window_pass on all evaluated windows before this blocker clears
- resolve the DFL active-date audit before reconsidering golden2
- resolve the 2608.20179 dynamic-CVaR forward validation block before reconsidering golden2
