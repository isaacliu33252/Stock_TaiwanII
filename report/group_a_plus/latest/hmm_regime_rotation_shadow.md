# HMM Regime-Conditioned Top-1 Rotation Shadow (arXiv:2605.27848 mechanism test)

Universe: 0050 (equity) / 00679B (bond) / 00632R (inverse, GLD-role substitute). 5-fold purged walk-forward, 1-day execution lag, 3-state Gaussian HMM (Baum-Welch EM, 5 restarts) fit fresh on each fold's train-only data.

| fold | test window | Top-1 by state | annual return | Sharpe | max drawdown |
|---|---|---|---|---|---|
| 1 | 2018-01-29..2019-10-17 | {0: 'bond', 1: 'equity', 2: 'equity'} | 0.078 | 0.692 | 0.118 |
| 2 | 2019-10-18..2021-07-01 | {0: 'equity', 1: 'bond', 2: 'equity'} | -0.133 | -0.697 | 0.407 |
| 3 | 2021-07-02..2023-03-14 | {0: 'inverse', 1: 'equity', 2: 'equity'} | -0.117 | -0.602 | 0.389 |
| 4 | 2023-03-15..2024-11-25 | {0: 'inverse', 1: 'equity', 2: 'equity'} | 0.189 | 0.920 | 0.236 |
| 5 | 2024-11-26..2026-08-10 | {0: 'inverse', 1: 'equity', 2: 'equity'} | -0.085 | -0.301 | 0.474 |

| strategy | annual return | Sharpe | max drawdown | n test days |
|---|---|---|---|---|
| HMM regime Top-1 | -0.014 | -0.068 | 0.691 | 2065 |
| Equal-weight (0050/00679B/00632R) | 0.042 | 0.182 | 0.367 | 2065 |
| Buy & hold 0050 | 0.195 | 0.903 | 0.452 | 2065 |

All three rows evaluated on the exact same pooled OOS test days for a fair comparison.

