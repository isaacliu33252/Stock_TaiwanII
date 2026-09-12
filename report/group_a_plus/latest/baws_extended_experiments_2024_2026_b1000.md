# GroupA+ BAWS Extended Experiments

- Generated: `2026-08-14T12:38:28`
- Source paper: `arXiv:2603.01157v2 Adaptive Window Selection for Financial Risk Forecasting`
- Policy: `research_only_no_active_weight_or_order_change`
- Promotion ready: `False`

## Summary

- BAWS quantile-score wins: `0/4`
- BAWS average quantile-score delta vs best fixed: `2.220899259463866e-05`
- BAWS FZ-style wins: `0/4`
- BAWS average FZ-style delta vs best fixed: `0.012168006843316093`
- SAWS-like wins: `1/4`
- Portfolio guard days: `34`

## Portfolio Replay

| Metric | Delta proxy - baseline |
|---|---:|
| final_value | -199776.06 |
| annual_return | -0.047023 |
| sharpe_ratio | 0.052735 |
| sortino_ratio | 0.075132 |
| max_drawdown | 0.019396 |

## Decision

BAWS must improve quantile score, FZ-style joint score, comparator robustness, and portfolio replay before promotion; current evidence does not clear that bar.

Research-only. No latest strategy, golden1_0531, live signal, execution plan, or order file was changed.
