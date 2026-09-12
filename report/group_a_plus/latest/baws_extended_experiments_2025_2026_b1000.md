# GroupA+ BAWS Extended Experiments

- Generated: `2026-08-14T12:40:07`
- Source paper: `arXiv:2603.01157v2 Adaptive Window Selection for Financial Risk Forecasting`
- Policy: `research_only_no_active_weight_or_order_change`
- Promotion ready: `False`

## Summary

- BAWS quantile-score wins: `0/4`
- BAWS average quantile-score delta vs best fixed: `3.645125081274162e-05`
- BAWS FZ-style wins: `0/4`
- BAWS average FZ-style delta vs best fixed: `0.03846268315861101`
- SAWS-like wins: `0/4`
- Portfolio guard days: `20`

## Portfolio Replay

| Metric | Delta proxy - baseline |
|---|---:|
| final_value | -125421.16 |
| annual_return | -0.063580 |
| sharpe_ratio | 0.050308 |
| sortino_ratio | 0.083568 |
| max_drawdown | 0.005518 |

## Decision

BAWS must improve quantile score, FZ-style joint score, comparator robustness, and portfolio replay before promotion; current evidence does not clear that bar.

Research-only. No latest strategy, golden1_0531, live signal, execution plan, or order file was changed.
