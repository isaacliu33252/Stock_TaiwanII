# 2609.08106 Complementarity Sleeve Backtest

- generated_at: `2026-09-10T13:20:52`
- window: `2024-01-02 -> 2024-12-31`
- policy: `shadow_only_no_orders_no_live_weight_change`
- events: `128`

| metric | baseline | shadow | delta |
|---|---:|---:|---:|
| total_return | 0.33846709066570546 | 0.34730794357602024 | 0.008840852910314778 |
| annual_return | 0.3546884266055641 | 0.3640074457274227 | 0.009319019121858618 |
| sharpe_ratio | 1.6238475456565358 | 1.7483850053326921 | 0.12453745967615637 |
| max_drawdown | -0.19460320491466865 | -0.18380256963396646 | 0.010800635280702187 |
| total_turnover | 0.0 | 1.7399999999999998 | 1.7399999999999998 |

## Latest Score

```json
{
  "dt": "2024-12-31",
  "score_00631l": -0.8444807170249965,
  "score_00713": 0.12353161667807033,
  "best_bond": "00679B.TWO",
  "best_bond_score": 0.9408944110000835,
  "corr_00631l_0050": 0.9707893957631597,
  "corr_00713_0050": 0.41330484787064076
}
```

## Decision

- promotion_ready: `True`
- promote_to_live: `False`
- No target-weight change and no order generation.
