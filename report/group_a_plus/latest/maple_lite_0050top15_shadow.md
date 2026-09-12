# MAPLE-lite 0050-Top15 Shadow Evaluation (research diagnostic)

- Universe: 0050 top15 (`stockmixer_atfnet_0050top15_ohlcv_cache.parquet`, cached 2019-01-02..2026-07-01)
- Horizon: 5d forward return, lookback=16d, top_k=5, 5-fold purged walk-forward
- Transaction cost: 0.50% per name replaced in the top-5 basket (~0.1425% commission/side + 0.3% TW sell tax)
- Both configs run across the same 3 seeds ([0, 1000, 2000]) for a fair comparison (2026-08-11 fix: previously N_alpha=1 used only 1 seed and np.random.shuffle wasn't seeded at all)
- Independent-samples t-test (N_alpha=8 vs N_alpha=1, 3 seeds each): IC diff p=0.035, net Sharpe diff p=0.035

| config | mean rank IC | ensemble Sharpe (gross) | ensemble Sharpe (net of cost) | mean turnover | diversification gain | mean alpha correlation |
|---|---|---|---|---|---|---|
| N_alpha=1 (3-seed mean±std) | 0.0353±0.0051 | 1.912±0.054 | 0.910±0.015 | 0.24±0.01 | n/a | n/a |
| N_alpha=8 (3-seed mean±std) | 0.0115±0.0095 | 1.747±0.101 | 0.647±0.118 | 0.26±0.01 | 0.046±0.055 | 0.821±0.020 |

Reference (2026-07-02 shadow, same top15 universe, different model/eval protocol -- not directly comparable, context only): StockMixer+ATFNet IC=0.0143, single-stock logistic baseline IC=0.0244.

