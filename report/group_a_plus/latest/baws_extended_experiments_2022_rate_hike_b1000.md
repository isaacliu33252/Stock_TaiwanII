# GroupA+ BAWS Extended Experiments

- Generated: `2026-08-14T12:39:15`
- Source paper: `arXiv:2603.01157v2 Adaptive Window Selection for Financial Risk Forecasting`
- Policy: `research_only_no_active_weight_or_order_change`
- Promotion ready: `False`

## Summary

- BAWS quantile-score wins: `0/4`
- BAWS average quantile-score delta vs best fixed: `1.0209489735939692e-05`
- BAWS FZ-style wins: `0/4`
- BAWS average FZ-style delta vs best fixed: `0.00724388478270277`
- SAWS-like wins: `1/4`
- Portfolio guard days: `2`

## Portfolio Replay

| Metric | Delta proxy - baseline |
|---|---:|
| final_value | 2160.09 |
| annual_return | 0.002181 |
| sharpe_ratio | 0.018484 |
| sortino_ratio | 0.013128 |
| max_drawdown | 0.001996 |

## Decision

BAWS must improve quantile score, FZ-style joint score, comparator robustness, and portfolio replay before promotion; current evidence does not clear that bar.

Research-only. No latest strategy, golden1_0531, live signal, execution plan, or order file was changed.
