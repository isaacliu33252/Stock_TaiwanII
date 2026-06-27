# Group A Regime-Aware 00632R Ranking 2026-06-05

目的：同時考慮 2024-2026 近期回測與 2008 TWII proxy 壓力測試，避免只為近期報酬而犧牲壓力情境。

## Inputs

- Recent replay: `results/group_a_00632r_dca_sweep_20240102_20260604.csv`
- 2008 proxy stress: `results/group_a_twii_proxy_2008_inverse_sweep_20070701_20101231.csv`

## Ranking

| Rank | Candidate | Dual Score | 2024 Final | 2024 Sharpe | 2024 MDD | 2008 Final | 2008 Sharpe | 2008 MDD |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | balanced_hold10 | 0.7836 | 3,323,211 | 2.2416 | -26.43% | 1,525,036 | 0.5395 | -50.44% |
| 2 | cap05_inverse | 0.6874 | 3,492,929 | 2.2566 | -28.08% | 1,521,158 | 0.5362 | -50.56% |
| 3 | cap10_inverse | 0.6676 | 3,426,038 | 2.2481 | -27.74% | 1,523,464 | 0.5382 | -50.44% |
| 4 | conditional_below_ma60_with_dca | 0.5581 | 3,210,941 | 2.1965 | -26.05% | 1,525,036 | 0.5395 | -50.44% |
| 5 | conditional_below_ma60 | 0.5521 | 3,175,683 | 2.1789 | -26.31% | 1,525,036 | 0.5395 | -50.44% |
| 6 | current_baseline | 0.5407 | 3,168,631 | 2.1789 | -26.43% | 1,525,036 | 0.5395 | -50.44% |
| 7 | aggressive_disable_inverse | 0.0850 | 3,566,548 | 2.2622 | -28.30% | 1,452,024 | 0.4787 | -51.96% |

## Conclusion

最佳雙目標候選是：

**`destination_primary + post-target 00632R hold10 -> 0050`**

原因：

- 2024-2026：比 current baseline 明顯更好。
- 2008 proxy：約束上保留 baseline 00632R hedge 能力。
- 不像永久禁用 00632R，沒有破壞 2008 壓力測試。

## Rejected

`aggressive_disable_inverse` 不建議當正式版。

雖然近期數字最好：

- 2024 final: 3,566,548
- 2024 Sharpe: 2.2622

但 2008 proxy 明顯變差：

- final -73,012
- Sharpe -0.0608
- MDD -1.52 pct

## Recommendation

Group A 目前正式候選排序：

1. **Balanced**: `destination_primary + 00632R hold10 overlay`
2. **Aggressive research only**: `disable 00632R -> 0050`
3. **Fallback stable baseline**: `destination_primary`

下一步若要再改善，應該以 `balanced_hold10` 為基準重跑 Group A + Group B allocation，而不是再回到單獨 Group A 亂加規則。

## Outputs

- Script: `rank_group_a_regime_aware_00632r.py`
- JSON: `results/group_a_regime_aware_00632r_dual_ranking_20260605.json`
- CSV: `results/group_a_regime_aware_00632r_dual_ranking_20260605.csv`
