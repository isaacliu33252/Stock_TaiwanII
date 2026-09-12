# GroupA+ BAWS Extended Experiments

- Generated: `2026-08-14T12:39:09`
- Source paper: `arXiv:2603.01157v2 Adaptive Window Selection for Financial Risk Forecasting`
- Policy: `research_only_no_active_weight_or_order_change`
- Promotion ready: `False`

## Summary

- BAWS quantile-score wins: `0/4`
- BAWS average quantile-score delta vs best fixed: `0.0002837931194114619`
- BAWS FZ-style wins: `0/4`
- BAWS average FZ-style delta vs best fixed: `0.15331120266239212`
- SAWS-like wins: `0/4`
- Portfolio guard days: `7`

## Portfolio Replay

| Metric | Delta proxy - baseline |
|---|---:|
| final_value | -20102.31 |
| annual_return | -0.020186 |
| sharpe_ratio | -0.092379 |
| sortino_ratio | -0.095536 |
| max_drawdown | -0.001664 |

## Decision

BAWS must improve quantile score, FZ-style joint score, comparator robustness, and portfolio replay before promotion; current evidence does not clear that bar.

Research-only. No latest strategy, golden1_0531, live signal, execution plan, or order file was changed.
