# 2609.08106 Complementarity Sleeve Backtest

- generated_at: `2026-09-12T07:27:53`
- window: `2020-01-02 -> 2020-12-31`
- policy: `shadow_only_no_orders_no_live_weight_change`
- events: `52`

| metric | baseline | shadow | delta |
|---|---:|---:|---:|
| total_return | 0.35137488494837155 | 0.3686702725205344 | 0.017295387572162868 |
| annual_return | 0.3630515973331523 | 0.38099811856736654 | 0.017946521234214252 |
| sharpe_ratio | 1.556912962629803 | 1.674270595950344 | 0.11735763332054105 |
| max_drawdown | -0.2953702423140989 | -0.2892251572452881 | 0.0061450850688108405 |
| total_turnover | 0.0 | 2.2800000000000002 | 2.2800000000000002 |

## Latest Score

```json
{
  "dt": "2020-12-31",
  "score_00631l": -0.8166644215221871,
  "score_00713": 0.421862941022008,
  "best_bond": "00751B.TWO",
  "best_bond_score": 1.1095256978754424,
  "corr_00631l_0050": 0.9540564605586106,
  "corr_00713_0050": 0.4188579014633289,
  "momentum_5d_00631l": 0.061947910427983865,
  "momentum_20d_00631l": 0.12010061407828099,
  "ann_vol_00631l": 0.2980565437367434,
  "drawdown_window_00631l": 0.0
}
```

## Decision

- promotion_ready: `True`
- promote_to_live: `False`
- No target-weight change and no order generation.
- `golden1_0531` and `golden2_0830` are lockdown comparators; this report cannot modify or overwrite them.
