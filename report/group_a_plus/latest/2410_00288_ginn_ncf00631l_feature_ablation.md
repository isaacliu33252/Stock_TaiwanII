# 2410.00288 NCF00631L Feature Ablation

- Policy: `research_only_no_weight_change`
- Decision: `do_not_promote_keep_shadow`
- Best feature set: `all_volatility_families`
- Strict shadow metric passed: `False`
- Window: `2025-01-02` to `2026-08-07` rows=`387`

## Summary

| feature set | folds | acc | dAcc | auc | dAUC | brier | dBrier | acc+ | auc+ | brier+ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| raw_ncf_prob_up_h20 | 4 | 0.6127 | 0.0000 | 0.8419 | 0.0000 | 0.2261 | 0.0000 |  |  |  |
| all_volatility_families | 4 | 0.5784 | -0.0343 | 0.6289 | -0.2130 | 0.2835 | 0.0574 | 2/4 | 0/4 | 2/4 |
| gjr_asymmetry_only | 4 | 0.5784 | -0.0343 | 0.4281 | -0.4138 | 0.2534 | 0.0273 | 1/4 | 0/4 | 1/4 |
| garch_all_only | 4 | 0.5735 | -0.0392 | 0.4447 | -0.3972 | 0.2546 | 0.0285 | 1/4 | 0/4 | 1/4 |
| realized_vol_only | 4 | 0.5588 | -0.0539 | 0.8969 | 0.0549 | 0.2895 | 0.0634 | 2/4 | 3/4 | 2/4 |
| symmetric_garch_only | 4 | 0.5343 | -0.0784 | 0.8090 | -0.0329 | 0.2437 | 0.0176 | 0/4 | 1/4 | 1/4 |
| baseline_logit_only | 4 | 0.5245 | -0.0882 | 0.8419 | 0.0000 | 0.2491 | 0.0230 | 0/4 | 0/4 | 1/4 |
| vol_cluster_only | 4 | 0.4853 | -0.1275 | 0.7450 | -0.0969 | 0.2551 | 0.0291 | 0/4 | 1/4 | 1/4 |

## Conclusion

本 ablation 只做 shadow 評估。若沒有同時改善 Acc 與 Brier 且跨 fold 穩定，不能導入 groupA++ 最新策略。
