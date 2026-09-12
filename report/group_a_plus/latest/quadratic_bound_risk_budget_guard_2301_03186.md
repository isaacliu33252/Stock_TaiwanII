# Quadratic Bound Risk-Budget Guard Backtest

- Generated: `2026-08-22T22:51:33`
- Source: `arXiv:2301.03186 (Fable 00631L direction #10, backward-looking risk-budget use, not the already-refuted forward regime-forecast use)`
- Decision: `do_not_promote_keep_shadow`

## Summary

- Promotion-ready windows: `0`
- Average delta final value: `-222050.43`
- Worst delta final value: `-755878.62`
- Average delta Sharpe: `-0.0517`
- Worst delta max drawdown: `-0.0004`

## Window Results
- `full_2016_2026`: final `-755878.62`, Sharpe `-0.0512`, Sortino `-0.0455`, MDD `0.0139`, warning_days `795`, changed_days `795`, promotion_ready `False`
- `rate_hike_2022_2023`: final `-20889.09`, Sharpe `-0.0859`, Sortino `-0.0902`, MDD `-0.0004`, warning_days `269`, changed_days `269`, promotion_ready `False`
- `live_2024_2026`: final `-84192.70`, Sharpe `-0.0335`, Sortino `-0.0403`, MDD `0.0000`, warning_days `121`, changed_days `121`, promotion_ready `False`
- `active_2025_2026`: final `-27241.30`, Sharpe `-0.0361`, Sortino `-0.0405`, MDD `0.0006`, warning_days `91`, changed_days `91`, promotion_ready `False`

## Decision

Keep shadow unless every tested window improves final value, Sharpe, Sortino, and does not worsen max drawdown after costs.
