# 2609.08106 Complementarity Sleeve Backtest

- generated_at: `2026-09-10T13:20:52`
- window: `2018-01-02 -> 2018-12-28`
- policy: `shadow_only_no_orders_no_live_weight_change`
- events: `151`

| metric | baseline | shadow | delta |
|---|---:|---:|---:|
| total_return | -0.059836117386956156 | -0.04105142277712326 | 0.018784694609832897 |
| annual_return | -0.06149206084819192 | -0.0421992221749905 | 0.019292838673201418 |
| sharpe_ratio | -0.39216393143388373 | -0.2845346624056886 | 0.10762926902819514 |
| max_drawdown | -0.146049312859019 | -0.13486292239098707 | 0.011186390468031937 |
| total_turnover | 0.0 | 2.2199999999999998 | 2.2199999999999998 |

## Latest Score

```json
{
  "dt": "2018-12-28",
  "score_00631l": -0.8286592527639518,
  "score_00713": 0.7064153533067411,
  "best_bond": "00679B.TWO",
  "best_bond_score": 1.180874836511796,
  "corr_00631l_0050": 0.96892195928652,
  "corr_00713_0050": 0.5572865857631476
}
```

## Decision

- promotion_ready: `True`
- promote_to_live: `False`
- No target-weight change and no order generation.
