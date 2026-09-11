# 2609.08106 Complementarity Sleeve Backtest

- generated_at: `2026-09-12T07:27:53`
- window: `2022-01-03 -> 2022-10-31`
- policy: `shadow_only_no_orders_no_live_weight_change`
- events: `107`

| metric | baseline | shadow | delta |
|---|---:|---:|---:|
| total_return | -0.27831210406550233 | -0.2573551062329992 | 0.020956997832503155 |
| annual_return | -0.3342864495293737 | -0.3100837922800497 | 0.024202657249324022 |
| sharpe_ratio | -1.6784327809082025 | -1.6202095253640776 | 0.058223255544124886 |
| max_drawdown | -0.3154918201704846 | -0.2965702326324898 | 0.018921587537994777 |
| total_turnover | 0.0 | 3.24 | 3.24 |

## Latest Score

```json
{
  "dt": "2022-10-31",
  "score_00631l": -0.991410439658128,
  "score_00713": 0.11719683336517686,
  "best_bond": "00679B.TWO",
  "best_bond_score": 1.3755211088117825,
  "corr_00631l_0050": 0.9570520259607715,
  "corr_00713_0050": 0.7135787857820466,
  "momentum_5d_00631l": 0.00918086713425259,
  "momentum_20d_00631l": -0.0751199257752897,
  "ann_vol_00631l": 0.46204750900112823,
  "drawdown_window_00631l": -0.2716506852783561
}
```

## Decision

- promotion_ready: `True`
- promote_to_live: `False`
- No target-weight change and no order generation.
- `golden1_0531` and `golden2_0830` are lockdown comparators; this report cannot modify or overwrite them.
