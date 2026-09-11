# 2609.07946 Vol-Control Cash Scaler Shadow

- generated_at: `2026-09-12T07:43:33`
- policy: `shadow_only_no_orders_no_live_weight_change`
- robust_combo_count: `0`
- promotion_ready: `False`

| target_vol | max_extra_cash | pass | avg_d_return | avg_d_sharpe | avg_d_mdd | avg_turnover |
|---:|---:|---:|---:|---:|---:|---:|
| 27.0% | 5.0% | 1/5 | -0.7124% | 0.0059 | 0.3354% | 0.216 |
| 21.0% | 20.0% | 1/5 | -3.4061% | 0.0229 | 1.8310% | 1.053 |
| 30.0% | 5.0% | 1/5 | -0.7374% | -0.0009 | 0.2211% | 0.156 |
| 27.0% | 10.0% | 1/5 | -1.4085% | 0.0058 | 0.5757% | 0.406 |
| 24.0% | 10.0% | 1/5 | -1.6941% | 0.0105 | 0.7696% | 0.476 |

## Latest Snapshot

- latest_trailing_ann_vol: `0.16448185156392042`
- latest_weights: `{'0050.TW': 0.4977485488030475, '00631L.TW': 0.16122211919007085, '00632R.TW': 0.0, '00679B.TWO': 0.0, '00713.TW': 0.11269778463465227, 'cash': 0.2283315473722294}`

## Decision

- Keep as shadow-only candidate.
- Current screen did not find a robust parameter set that improves return, Sharpe, and drawdown in every validation window.
- Do not modify latest GroupA++ live weights, signals, execution plans, or orders.
- `golden1_0531` and `golden2_0830` are lockdown comparators; do not modify or overwrite them.
