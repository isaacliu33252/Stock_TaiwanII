# Leveraged ETF Timing Guard Backtest

- Generated: `2026-08-21T15:07:16`
- Source: `arXiv:2604.27287v1 A Levered ETF Anomaly Explained`
- Policy: `research_only_no_weight_change`
- Decision: `do_not_promote_keep_shadow`
- Latest strategy changed: `False`

## Variant Summary

### 00631l_only

- Promotion-ready windows: `1`
- Average delta final value: `-16479.54`
- Average delta Sharpe: `0.0028`
- Worst delta max drawdown: `0.0000`

### 00632r_only

- Promotion-ready windows: `0`
- Average delta final value: `-55429.51`
- Average delta Sharpe: `-0.0134`
- Worst delta max drawdown: `0.0000`

### combined

- Promotion-ready windows: `0`
- Average delta final value: `-68331.38`
- Average delta Sharpe: `-0.0064`
- Worst delta max drawdown: `0.0000`

## Window Results

### full_2016_2026

- `00631l_only`: final `-26752.28`, Sharpe `-0.0043`, Sortino `-0.0027`, MDD `0.0000`, changed_days `2056`, promotion_ready `False`
- `00632r_only`: final `-161044.11`, Sharpe `0.0020`, Sortino `0.0077`, MDD `0.0000`, changed_days `1579`, promotion_ready `False`
- `combined`: final `-174836.71`, Sharpe `-0.0056`, Sortino `-0.0014`, MDD `0.0000`, changed_days `2056`, promotion_ready `False`

### rate_hike_2022_2023

- `00631l_only`: final `-2704.05`, Sharpe `-0.0236`, Sortino `-0.0228`, MDD `0.0000`, changed_days `233`, promotion_ready `False`
- `00632r_only`: final `-4456.79`, Sharpe `-0.0386`, Sortino `-0.0372`, MDD `0.0000`, changed_days `197`, promotion_ready `False`
- `combined`: final `-4456.79`, Sharpe `-0.0386`, Sortino `-0.0372`, MDD `0.0000`, changed_days `233`, promotion_ready `False`

### live_2024_2026

- `00631l_only`: final `3293.52`, Sharpe `0.0120`, Sortino `0.0126`, MDD `0.0007`, changed_days `365`, promotion_ready `True`
- `00632r_only`: final `-56217.12`, Sharpe `-0.0170`, Sortino `-0.0317`, MDD `0.0007`, changed_days `218`, promotion_ready `False`
- `combined`: final `-54276.66`, Sharpe `-0.0085`, Sortino `-0.0231`, MDD `0.0007`, changed_days `365`, promotion_ready `False`

### active_2025_2026

- `00631l_only`: final `-39755.34`, Sharpe `0.0272`, Sortino `0.0308`, MDD `0.0000`, changed_days `133`, promotion_ready `False`
- `00632r_only`: final `0.00`, Sharpe `0.0000`, Sortino `0.0000`, MDD `0.0000`, changed_days `0`, promotion_ready `False`
- `combined`: final `-39755.34`, Sharpe `0.0272`, Sortino `0.0308`, MDD `0.0000`, changed_days `133`, promotion_ready `False`

## Decision

Keep shadow unless every tested window improves final value, Sharpe, Sortino, and does not worsen max drawdown after costs.
