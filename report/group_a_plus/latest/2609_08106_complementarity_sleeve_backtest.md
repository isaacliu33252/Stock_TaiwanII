# 2609.08106 Complementarity Sleeve Backtest

- generated_at: `2026-09-10T13:18:21`
- window: `2025-01-02 -> 2026-09-09`
- policy: `shadow_only_no_orders_no_live_weight_change`
- events: `407`

| metric | baseline | shadow | delta |
|---|---:|---:|---:|
| total_return | 0.989882382130544 | 0.8461130441745943 | -0.1437693379559497 |
| annual_return | 0.5264041149430014 | 0.45764389273329953 | -0.0687602222097019 |
| sharpe_ratio | 2.054931321530307 | 1.9913448365090998 | -0.06358648502120734 |
| max_drawdown | -0.2659554976437597 | -0.24172369406394756 | 0.02423180357981214 |
| total_turnover | 0.0 | 4.0 | 4.0 |

## Latest Score

```json
{
  "dt": "2026-09-09",
  "score_00631l": -0.7287689670543498,
  "score_00713": 0.20141882652718096,
  "best_bond": "00679B.TWO",
  "best_bond_score": 1.2218815491060933,
  "corr_00631l_0050": 0.9892011324000411,
  "corr_00713_0050": 0.6538239458321627
}
```

## Decision

- promotion_ready: `False`
- promote_to_live: `False`
- No target-weight change and no order generation.
