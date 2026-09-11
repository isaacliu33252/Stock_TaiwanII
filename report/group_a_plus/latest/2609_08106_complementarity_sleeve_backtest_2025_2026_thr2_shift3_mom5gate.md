# 2609.08106 Complementarity Sleeve Backtest

- generated_at: `2026-09-12T07:27:27`
- window: `2025-01-02 -> 2026-09-09`
- policy: `shadow_only_no_orders_no_live_weight_change`
- events: `127`

| metric | baseline | shadow | delta |
|---|---:|---:|---:|
| total_return | 0.989882382130544 | 1.059564503093013 | 0.06968212096246895 |
| annual_return | 0.5264041149430014 | 0.5590393394809603 | 0.03263522453795886 |
| sharpe_ratio | 2.054931321530307 | 2.2520887019040448 | 0.19715738037373765 |
| max_drawdown | -0.2659554976437597 | -0.25317175643957857 | 0.012783741204181132 |
| total_turnover | 0.0 | 4.5600000000000005 | 4.5600000000000005 |

## Latest Score

```json
{
  "dt": "2026-09-09",
  "score_00631l": -0.7287689670543498,
  "score_00713": 0.20141882652718096,
  "best_bond": "00679B.TWO",
  "best_bond_score": 1.2218815491060933,
  "corr_00631l_0050": 0.9892011324000411,
  "corr_00713_0050": 0.6538239458321627,
  "momentum_5d_00631l": 0.04480934264262437,
  "momentum_20d_00631l": 0.05895625365530299,
  "ann_vol_00631l": 0.7490718285475513,
  "drawdown_window_00631l": -0.007928122393714432
}
```

## Decision

- promotion_ready: `True`
- promote_to_live: `False`
- No target-weight change and no order generation.
- `golden1_0531` and `golden2_0830` are lockdown comparators; this report cannot modify or overwrite them.
