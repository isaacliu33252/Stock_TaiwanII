# Leveraged ETF Timing Guard Partial-Cap Backtest

- Generated: `2026-08-22T22:45:21`
- Source: `arXiv:2604.27287v1 A Levered ETF Anomaly Explained (direction #9 follow-up)`
- Policy: `research_only_no_weight_change`
- Decision: `do_not_promote_keep_shadow`

## Variant Summary (cap_fraction = fraction of 00631L weight moved to 0050 on a guarded day)

### cap_fraction=0.25

- Promotion-ready windows: `0`
- Average delta final value: `-123109.94`
- Worst delta final value: `-383775.18`
- Average delta Sharpe: `0.0309`
- Worst delta max drawdown: `0.0000`

### cap_fraction=0.5

- Promotion-ready windows: `0`
- Average delta final value: `-159471.76`
- Worst delta final value: `-488562.23`
- Average delta Sharpe: `0.0408`
- Worst delta max drawdown: `0.0000`

### cap_fraction=0.75

- Promotion-ready windows: `0`
- Average delta final value: `-195625.06`
- Worst delta final value: `-592526.89`
- Average delta Sharpe: `0.0508`
- Worst delta max drawdown: `0.0000`

### cap_fraction=1.0

- Promotion-ready windows: `0`
- Average delta final value: `-231451.22`
- Worst delta final value: `-694991.02`
- Average delta Sharpe: `0.0608`
- Worst delta max drawdown: `0.0000`

## Window Results

### full_2016_2026

- `cap=0.25`: final `-383775.18`, Sharpe `0.0179`, Sortino `0.0284`, MDD `0.0269`, changed_days `756`, promotion_ready `False`
- `cap=0.5`: final `-488562.23`, Sharpe `0.0216`, Sortino `0.0349`, MDD `0.0316`, changed_days `756`, promotion_ready `False`
- `cap=0.75`: final `-592526.89`, Sharpe `0.0250`, Sortino `0.0411`, MDD `0.0320`, changed_days `756`, promotion_ready `False`
- `cap=1.0`: final `-694991.02`, Sharpe `0.0282`, Sortino `0.0402`, MDD `0.0320`, changed_days `756`, promotion_ready `False`

### rate_hike_2022_2023

- `cap=0.25`: final `-4964.05`, Sharpe `-0.0223`, Sortino `-0.0237`, MDD `0.0000`, changed_days `9`, promotion_ready `False`
- `cap=0.5`: final `-5363.50`, Sharpe `-0.0241`, Sortino `-0.0257`, MDD `0.0000`, changed_days `9`, promotion_ready `False`
- `cap=0.75`: final `-5804.59`, Sharpe `-0.0261`, Sortino `-0.0278`, MDD `0.0000`, changed_days `9`, promotion_ready `False`
- `cap=1.0`: final `-6245.58`, Sharpe `-0.0281`, Sortino `-0.0299`, MDD `0.0000`, changed_days `9`, promotion_ready `False`

### live_2024_2026

- `cap=0.25`: final `-30962.16`, Sharpe `0.0125`, Sortino `0.0134`, MDD `0.0000`, changed_days `365`, promotion_ready `False`
- `cap=0.5`: final `-65500.44`, Sharpe `0.0209`, Sortino `0.0258`, MDD `0.0000`, changed_days `365`, promotion_ready `False`
- `cap=0.75`: final `-99986.21`, Sharpe `0.0294`, Sortino `0.0381`, MDD `0.0000`, changed_days `365`, promotion_ready `False`
- `cap=1.0`: final `-134494.43`, Sharpe `0.0376`, Sortino `0.0255`, MDD `0.0000`, changed_days `365`, promotion_ready `False`

### active_2025_2026

- `cap=0.25`: final `-72738.39`, Sharpe `0.1153`, Sortino `0.1517`, MDD `0.0155`, changed_days `133`, promotion_ready `False`
- `cap=0.5`: final `-78460.85`, Sharpe `0.1447`, Sortino `0.1918`, MDD `0.0155`, changed_days `133`, promotion_ready `False`
- `cap=0.75`: final `-84182.55`, Sharpe `0.1749`, Sortino `0.2399`, MDD `0.0155`, changed_days `133`, promotion_ready `False`
- `cap=1.0`: final `-90073.84`, Sharpe `0.2054`, Sortino `0.2753`, MDD `0.0155`, changed_days `133`, promotion_ready `False`

## Decision

Keep shadow unless every tested window improves final value, Sharpe, Sortino, and does not worsen max drawdown after costs.
