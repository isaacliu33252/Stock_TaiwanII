# MAPLE-lite 0050-Top15 Shadow Evaluation (research diagnostic)

- Universe: 50 tickers (`stockmixer_atfnet_full50_202606_ohlcv_cache.parquet`, cached 2019-04-10..2026-07-02)
- Horizon: 5d forward return, lookback=16d, top_k=5, 5-fold purged walk-forward
- Transaction cost: 0.50% per name replaced in the top-5 basket (~0.1425% commission/side + 0.3% TW sell tax)
- Both configs run across the same 3 seeds ([0, 1000, 2000]) for a fair comparison (2026-08-11 fix: previously N_alpha=1 used only 1 seed and np.random.shuffle wasn't seeded at all)
- Independent-samples t-test (N_alpha=8 vs N_alpha=1, 3 seeds each): IC diff p=0.854, net Sharpe diff p=0.200

| config | mean rank IC | ensemble Sharpe (gross) | ensemble Sharpe (net of cost) | mean turnover | diversification gain | mean alpha correlation |
|---|---|---|---|---|---|---|
| N_alpha=1 (3-seed mean±std) | 0.0104±0.0028 | 1.456±0.095 | 0.461±0.069 | 0.25±0.01 | n/a | n/a |
| N_alpha=8 (3-seed mean±std) | 0.0094±0.0062 | 1.405±0.059 | 0.376±0.039 | 0.26±0.01 | -0.136±0.012 | nan±nan |

Reference (2026-07-02 shadow, same top15 universe, different model/eval protocol -- not directly comparable, context only): StockMixer+ATFNet IC=0.0143, single-stock logistic baseline IC=0.0244.

