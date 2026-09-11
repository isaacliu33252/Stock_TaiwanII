# 2609.07946 Vol-Control Cash Scaler Shadow

- generated_at: `2026-09-12T07:43:32`
- policy: `shadow_only_no_orders_no_live_weight_change`
- robust_combo_count: `0`
- promotion_ready: `False`

| target_vol | max_extra_cash | pass | avg_d_return | avg_d_sharpe | avg_d_mdd | avg_turnover |
|---:|---:|---:|---:|---:|---:|---:|
| 21.0% | 5.0% | 0/5 | -0.5626% | 0.0041 | 0.1375% | 0.102 |
| 21.0% | 10.0% | 0/5 | -1.0320% | 0.0062 | 0.2731% | 0.187 |
| 15.0% | 5.0% | 0/5 | -1.3249% | -0.0096 | 0.5566% | 0.167 |
| 21.0% | 15.0% | 0/5 | -1.6114% | 0.0044 | 0.4089% | 0.267 |
| 21.0% | 20.0% | 0/5 | -2.1529% | 0.0012 | 0.5216% | 0.342 |

## Latest Snapshot

- latest_trailing_ann_vol: `0.16448185156392042`
- latest_weights: `{'0050.TW': 0.4977485488030475, '00631L.TW': 0.16122211919007085, '00632R.TW': 0.0, '00679B.TWO': 0.0, '00713.TW': 0.11269778463465227, 'cash': 0.2283315473722294}`

## Decision

- Keep as shadow-only candidate.
- Current screen did not find a robust parameter set that improves return, Sharpe, and drawdown in every validation window.
- Do not modify latest GroupA++ live weights, signals, execution plans, or orders.
- `golden1_0531` and `golden2_0830` are lockdown comparators; do not modify or overwrite them.
