# 2609.08106 Complementarity Sleeve Backtest

- generated_at: `2026-09-12T07:27:52`
- window: `2024-01-02 -> 2024-12-31`
- policy: `shadow_only_no_orders_no_live_weight_change`
- events: `76`

| metric | baseline | shadow | delta |
|---|---:|---:|---:|
| total_return | 0.33846709066570546 | 0.36499324804587996 | 0.026526157380174498 |
| annual_return | 0.3546884266055641 | 0.3826568456980042 | 0.027968419092440078 |
| sharpe_ratio | 1.6238475456565358 | 1.8250931905461945 | 0.20124564488965868 |
| max_drawdown | -0.19460320491466865 | -0.18380256963396668 | 0.010800635280701965 |
| total_turnover | 0.0 | 2.1 | 2.1 |

## Latest Score

```json
{
  "dt": "2024-12-31",
  "score_00631l": -0.8444807170249965,
  "score_00713": 0.12353161667807033,
  "best_bond": "00679B.TWO",
  "best_bond_score": 0.9408944110000835,
  "corr_00631l_0050": 0.9707893957631597,
  "corr_00713_0050": 0.41330484787064076,
  "momentum_5d_00631l": -0.011109092109766738,
  "momentum_20d_00631l": -0.003317087210090941,
  "ann_vol_00631l": 0.31677858049305163,
  "drawdown_window_00631l": -0.054298397489795036
}
```

## Decision

- promotion_ready: `True`
- promote_to_live: `False`
- No target-weight change and no order generation.
- `golden1_0531` and `golden2_0830` are lockdown comparators; this report cannot modify or overwrite them.
