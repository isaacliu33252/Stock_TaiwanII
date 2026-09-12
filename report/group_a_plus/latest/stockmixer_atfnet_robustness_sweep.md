# StockMixer/ATFNet Robustness Sweep

- Generated: `2026-08-21T14:46:22`
- Universe: `full50_202606`
- Windows: `3`
- Seeds: `[1, 2, 3]`
- Promote to live: `False`
- Target weight change allowed: `False`

## Aggregate

- StockMixer IC: `0.005464140939580255`
- Logistic IC: `0.008180105098964415`
- Persistence IC: `-0.013537556855067698`
- StockMixer weighted return corr: `0.05594683937445735`
- StockMixer weighted long-short Sharpe: `-0.518739566666475`

## Live Blocking Reasons

- `no_execution_cost_or_turnover_backtest`
- `research_shadow_only_no_live_target_path`
- `stockmixer_ic_not_above_logistic_baseline`
- `weighted_proxy_sharpe_not_above_logistic_baseline`
