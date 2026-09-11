# 2609.08106 Complementarity Sleeve Backtest

- generated_at: `2026-09-10T13:20:52`
- window: `2022-01-03 -> 2022-10-31`
- policy: `shadow_only_no_orders_no_live_weight_change`
- events: `167`

| metric | baseline | shadow | delta |
|---|---:|---:|---:|
| total_return | -0.27831210406550233 | -0.2672938606380312 | 0.011018243427471153 |
| annual_return | -0.3342864495293737 | -0.32158315907188684 | 0.01270329045748686 |
| sharpe_ratio | -1.6784327809082025 | -1.7069366477494703 | -0.028503866841267822 |
| max_drawdown | -0.3154918201704846 | -0.3049155860099536 | 0.010576234160530995 |
| total_turnover | 0.0 | 1.26 | 1.26 |

## Latest Score

```json
{
  "dt": "2022-10-31",
  "score_00631l": -0.991410439658128,
  "score_00713": 0.11719683336517686,
  "best_bond": "00679B.TWO",
  "best_bond_score": 1.3755211088117825,
  "corr_00631l_0050": 0.9570520259607715,
  "corr_00713_0050": 0.7135787857820466
}
```

## Decision

- promotion_ready: `False`
- promote_to_live: `False`
- No target-weight change and no order generation.
