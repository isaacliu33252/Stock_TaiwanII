# 2609.08106 Complementarity Sleeve Backtest

- generated_at: `2026-09-10T13:20:51`
- window: `2020-01-02 -> 2020-06-30`
- policy: `shadow_only_no_orders_no_live_weight_change`
- events: `51`

| metric | baseline | shadow | delta |
|---|---:|---:|---:|
| total_return | 0.023828965994867612 | 0.02412094359405459 | 0.00029197759918697663 |
| annual_return | 0.05249046901833365 | 0.053142630947521585 | 0.0006521619291879333 |
| sharpe_ratio | 0.17558977814649374 | 0.18374623038401997 | 0.00815645223752623 |
| max_drawdown | -0.2953702423140989 | -0.2892251572452881 | 0.0061450850688108405 |
| total_turnover | 0.0 | 0.72 | 0.72 |

## Latest Score

```json
{
  "dt": "2020-06-30",
  "score_00631l": -0.6363203265676255,
  "score_00713": -0.22681099137115404,
  "best_bond": "00751B.TWO",
  "best_bond_score": 1.4516842118634414,
  "corr_00631l_0050": 0.9791396948114461,
  "corr_00713_0050": 0.874474344926109
}
```

## Decision

- promotion_ready: `True`
- promote_to_live: `False`
- No target-weight change and no order generation.
