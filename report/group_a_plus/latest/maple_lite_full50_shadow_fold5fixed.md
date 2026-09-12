# MAPLE-lite full50 Shadow Evaluation -- fold5 NaN-guard fix (2026-08-12)

All 5 folds now genuinely trained (fold5 previously corrupted by a NaN-propagating stock -- see GROUP_A_PLUS_20260812_MAPLE_2607_24131_DIVERSITY_ALPHA_SHADOW_HANDOFF.md).

- Independent-samples t-test (N_alpha=8 vs N_alpha=1, 3 seeds each): IC diff p=0.052, net Sharpe diff p=0.159

| config | mean rank IC | ensemble Sharpe (gross) | ensemble Sharpe (net of cost) | mean turnover | diversification gain | mean alpha correlation |
|---|---|---|---|---|---|---|
| N_alpha=1 | 0.0248±0.0020 | 1.719±0.082 | 0.647±0.085 | 0.31±0.01 | n/a | n/a |
| N_alpha=8 | 0.0139±0.0052 | 1.658±0.051 | 0.540±0.019 | 0.32±0.01 | -0.015±0.018 | 0.870±0.024 |

