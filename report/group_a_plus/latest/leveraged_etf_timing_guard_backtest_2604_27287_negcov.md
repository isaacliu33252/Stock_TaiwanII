# Leveraged ETF Timing Guard Backtest

- Generated: `2026-08-21T15:16:14`
- Source: `arXiv:2604.27287v1 A Levered ETF Anomaly Explained`
- Policy: `research_only_no_weight_change`
- Decision: `do_not_promote_keep_shadow`
- Latest strategy changed: `False`

## Variant Summary

### 00631l_only

- Promotion-ready windows: `1`
- Average delta final value: `-34552.27`
- Average delta Sharpe: `-0.0003`
- Worst delta max drawdown: `0.0000`

### 00632r_only

- Promotion-ready windows: `0`
- Average delta final value: `-21600.62`
- Average delta Sharpe: `-0.0106`
- Worst delta max drawdown: `0.0000`

### combined

- Promotion-ready windows: `1`
- Average delta final value: `-34208.21`
- Average delta Sharpe: `-0.0011`
- Worst delta max drawdown: `0.0000`

## Window Results

### full_2016_2026

- `00631l_only`: final `-97417.03`, Sharpe `-0.0043`, Sortino `0.0021`, MDD `0.0000`, changed_days `815`, promotion_ready `False`
- `00632r_only`: final `-81945.68`, Sharpe `-0.0037`, Sortino `0.0020`, MDD `0.0000`, changed_days `1259`, promotion_ready `False`
- `combined`: final `-95512.59`, Sharpe `-0.0017`, Sortino `0.0064`, MDD `0.0000`, changed_days `2007`, promotion_ready `False`

### rate_hike_2022_2023

- `00631l_only`: final `-4330.21`, Sharpe `-0.0360`, Sortino `-0.0348`, MDD `0.0000`, changed_days `15`, promotion_ready `False`
- `00632r_only`: final `-4456.79`, Sharpe `-0.0386`, Sortino `-0.0372`, MDD `0.0000`, changed_days `197`, promotion_ready `False`
- `combined`: final `-4858.43`, Sharpe `-0.0419`, Sortino `-0.0405`, MDD `0.0000`, changed_days `212`, promotion_ready `False`

### live_2024_2026

- `00631l_only`: final `3293.52`, Sharpe `0.0120`, Sortino `0.0126`, MDD `0.0007`, changed_days `365`, promotion_ready `True`
- `00632r_only`: final `0.00`, Sharpe `0.0000`, Sortino `0.0000`, MDD `0.0000`, changed_days `0`, promotion_ready `False`
- `combined`: final `3293.52`, Sharpe `0.0120`, Sortino `0.0126`, MDD `0.0007`, changed_days `365`, promotion_ready `True`

### active_2025_2026

- `00631l_only`: final `-39755.34`, Sharpe `0.0272`, Sortino `0.0308`, MDD `0.0000`, changed_days `133`, promotion_ready `False`
- `00632r_only`: final `0.00`, Sharpe `0.0000`, Sortino `0.0000`, MDD `0.0000`, changed_days `0`, promotion_ready `False`
- `combined`: final `-39755.34`, Sharpe `0.0272`, Sortino `0.0308`, MDD `0.0000`, changed_days `133`, promotion_ready `False`

## Decision

Keep shadow unless every tested window improves final value, Sharpe, Sortino, and does not worsen max drawdown after costs.
