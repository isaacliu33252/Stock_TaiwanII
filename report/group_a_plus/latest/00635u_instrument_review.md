# 00635U Instrument Review

- generated_at: `2026-09-12T07:45:51`
- policy: `review_only_no_watchlist_change_no_orders`
- ticker: `00635U.TW`
- name: `元大標普高盛黃金ER指數股票型期貨信託基金`
- category: `期貨ETF`
- benchmark: `S&P GSCI Gold Excess Return Index`

## Local Data

- min_dt: `2015-02-05`
- max_dt: `2026-09-10`
- rows: `2789`
- latest_close: `45.5600`
- latest_volume: `1,587,117`
- avg_volume_20: `4,441,137.9`
- avg_traded_value_20: `206,146,984`
- ann_vol_20: `26.84%`
- return_20d: `-0.22%`

## 252D Correlation

| peer | corr_to_00635U |
|---|---:|
| 0050.TW | 0.3227 |
| 00631L.TW | 0.3302 |
| 00679B.TWO | 0.0579 |
| 00751B.TWO | 0.1115 |
| 00713.TW | 0.3161 |

## Checks

- data_latest_pass: `True`
- liquidity_pass: `True`
- watchlist_monitoring_pass: `False`

## Decision

- Ready for forward shadow only.
- Do not add to live watchlist/tradable core without explicit approval.
- Do not change latest GroupA++ target weights, execution plans, or orders.
- `golden1_0531` and `golden2_0830` are lockdown comparators.
