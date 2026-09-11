# 2609.08106 Complementarity Sleeve Backtest

- generated_at: `2026-09-10T13:19:00`
- window: `2025-01-02 -> 2026-09-09`
- policy: `shadow_only_no_orders_no_live_weight_change`
- events: `218`

| metric | baseline | shadow | delta |
|---|---:|---:|---:|
| total_return | 0.989882382130544 | 1.0014734450743754 | 0.011591062943831387 |
| annual_return | 0.5264041149430014 | 0.5318628958186087 | 0.00545878087560725 |
| sharpe_ratio | 2.054931321530307 | 2.16982820235073 | 0.11489688082042271 |
| max_drawdown | -0.2659554976437597 | -0.2564224000746065 | 0.009533097569153215 |
| total_turnover | 0.0 | 4.02 | 4.02 |

## Latest Score

```json
{
  "dt": "2026-09-09",
  "score_00631l": -0.7568590939928416,
  "score_00713": 0.3471522521397482,
  "best_bond": "00679B.TWO",
  "best_bond_score": 1.10436935951335,
  "corr_00631l_0050": 0.9903724414992089,
  "corr_00713_0050": 0.528788676735735
}
```

## Decision

- promotion_ready: `True`
- promote_to_live: `False`
- No target-weight change and no order generation.
