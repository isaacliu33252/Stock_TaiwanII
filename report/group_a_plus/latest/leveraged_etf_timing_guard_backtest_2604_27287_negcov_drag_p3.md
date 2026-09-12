# Leveraged ETF Timing Guard Backtest

- Generated: `2026-08-21T15:16:13`
- Source: `arXiv:2604.27287v1 A Levered ETF Anomaly Explained`
- Policy: `research_only_no_weight_change`
- Decision: `do_not_promote_keep_shadow`
- Latest strategy changed: `False`

## Variant Summary

### 00631l_only

- Promotion-ready windows: `1`
- Average delta final value: `-32439.20`
- Average delta Sharpe: `0.0051`
- Worst delta max drawdown: `0.0000`

### 00632r_only

- Promotion-ready windows: `0`
- Average delta final value: `-5632.43`
- Average delta Sharpe: `-0.0084`
- Worst delta max drawdown: `-0.0031`

### combined

- Promotion-ready windows: `1`
- Average delta final value: `-31904.21`
- Average delta Sharpe: `-0.0005`
- Worst delta max drawdown: `-0.0031`

## Window Results

### full_2016_2026

- `00631l_only`: final `-91863.54`, Sharpe `-0.0046`, Sortino `0.0021`, MDD `0.0000`, changed_days `754`, promotion_ready `False`
- `00632r_only`: final `-18680.94`, Sharpe `0.0001`, Sortino `0.0027`, MDD `-0.0031`, changed_days `101`, promotion_ready `False`
- `combined`: final `-87039.49`, Sharpe `-0.0028`, Sortino `0.0052`, MDD `-0.0031`, changed_days `845`, promotion_ready `False`

### rate_hike_2022_2023

- `00631l_only`: final `-2385.51`, Sharpe `-0.0198`, Sortino `-0.0192`, MDD `0.0000`, changed_days `9`, promotion_ready `False`
- `00632r_only`: final `-3848.78`, Sharpe `-0.0337`, Sortino `-0.0325`, MDD `0.0000`, changed_days `36`, promotion_ready `False`
- `combined`: final `-5069.59`, Sharpe `-0.0441`, Sortino `-0.0425`, MDD `0.0000`, changed_days `45`, promotion_ready `False`

### live_2024_2026

- `00631l_only`: final `3985.44`, Sharpe `0.0137`, Sortino `0.0144`, MDD `0.0011`, changed_days `363`, promotion_ready `True`
- `00632r_only`: final `0.00`, Sharpe `0.0000`, Sortino `0.0000`, MDD `0.0000`, changed_days `0`, promotion_ready `False`
- `combined`: final `3985.44`, Sharpe `0.0137`, Sortino `0.0144`, MDD `0.0011`, changed_days `363`, promotion_ready `True`

### active_2025_2026

- `00631l_only`: final `-39493.19`, Sharpe `0.0309`, Sortino `0.0406`, MDD `0.0000`, changed_days `131`, promotion_ready `False`
- `00632r_only`: final `0.00`, Sharpe `0.0000`, Sortino `0.0000`, MDD `0.0000`, changed_days `0`, promotion_ready `False`
- `combined`: final `-39493.19`, Sharpe `0.0309`, Sortino `0.0406`, MDD `0.0000`, changed_days `131`, promotion_ready `False`

## Decision

Keep shadow unless every tested window improves final value, Sharpe, Sortino, and does not worsen max drawdown after costs.
