# 2609.08106 Complementarity Sleeve Backtest

- generated_at: `2026-09-12T07:27:52`
- window: `2018-01-02 -> 2018-12-28`
- policy: `shadow_only_no_orders_no_live_weight_change`
- events: `100`

| metric | baseline | shadow | delta |
|---|---:|---:|---:|
| total_return | -0.059836117386956156 | -0.038536573029514076 | 0.02129954435744208 |
| annual_return | -0.06149206084819192 | -0.03961551898193072 | 0.0218765418662612 |
| sharpe_ratio | -0.39216393143388373 | -0.2651692415936195 | 0.12699468984026424 |
| max_drawdown | -0.146049312859019 | -0.13508589564156326 | 0.010963417217455751 |
| total_turnover | 0.0 | 2.5200000000000005 | 2.5200000000000005 |

## Latest Score

```json
{
  "dt": "2018-12-28",
  "score_00631l": -0.8286592527639518,
  "score_00713": 0.7064153533067411,
  "best_bond": "00679B.TWO",
  "best_bond_score": 1.180874836511796,
  "corr_00631l_0050": 0.96892195928652,
  "corr_00713_0050": 0.5572865857631476,
  "momentum_5d_00631l": 0.0006392372427623805,
  "momentum_20d_00631l": -0.03717342935285528,
  "ann_vol_00631l": 0.3161479520693405,
  "drawdown_window_00631l": -0.08842212171380726
}
```

## Decision

- promotion_ready: `True`
- promote_to_live: `False`
- No target-weight change and no order generation.
- `golden1_0531` and `golden2_0830` are lockdown comparators; this report cannot modify or overwrite them.
