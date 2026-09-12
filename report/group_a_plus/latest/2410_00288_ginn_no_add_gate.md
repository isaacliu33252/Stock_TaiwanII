# 2410.00288 Volatility No-Add Gate

- Policy: `research_only_no_weight_change`
- Decision: `do_not_promote_keep_shadow`
- Best gate: `realized_var_20_top25_and_weak_ncf`
- Strict no-add gate passed: `False`
- Window: `2025-01-02` to `2026-08-07` rows=`387`

## Gate Summary

| gate | ok folds | pass | blocked rows | allowed rows | blocked gain | allowed gain | blocked mdd>5 | allowed mdd>5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| realized_var_20_top25_and_weak_ncf | 4 | 1/4 | 7 | 65 | 0.1169 | 0.2326 | 0.3333 | 0.2415 |
| realized_var_20_top25 | 4 | 0/4 | 35 | 37 | 0.2324 | 0.1336 | 0.3571 | 0.4400 |
| vol_cluster_score_top25 | 4 | 0/4 | 31 | 41 | 0.2075 | 0.2293 | 0.2073 | 0.3316 |
| garch_gjr_var_top25 | 4 | 0/4 | 30 | 42 | 0.2177 | 0.2242 | 0.1176 | 0.3578 |
| ewma_var_94_top25 | 4 | 0/4 | 28 | 44 | 0.2905 | 0.1337 | 0.2500 | 0.4101 |
| garch_sym_var_top25 | 4 | 0/4 | 26 | 46 | 0.2213 | 0.2185 | 0.1094 | 0.3542 |
| realized_vol_ratio_20_60_top25 | 4 | 0/4 | 18 | 54 | 0.2341 | 0.2276 | 0.1667 | 0.2831 |
| garch_disagreement_top25 | 4 | 0/4 | 17 | 55 | 0.2622 | 0.2240 | 0.0667 | 0.3369 |
| garch_gjr_over_sym_bottom25 | 4 | 0/4 | 13 | 59 | 0.2592 | 0.2278 | 0.0000 | 0.2990 |
| garch_disagreement_top25_and_negative_1d | 4 | 0/4 | 9 | 63 | 0.3338 | 0.2183 | 0.0714 | 0.2992 |
| garch_sym_top25_and_weak_ncf | 4 | 0/4 | 3 | 69 | 0.1699 | 0.2271 | 0.0000 | 0.2633 |
| realized_var_20_top25_and_negative_5d | 4 | 0/4 | 0 | 72 | nan | 0.2278 | nan | 0.2470 |
| vol_cluster_top25_and_negative_5d | 4 | 0/4 | 0 | 72 | nan | 0.2278 | nan | 0.2470 |
| garch_sym_top25_and_negative_5d | 4 | 0/4 | 0 | 72 | nan | 0.2278 | nan | 0.2470 |
| garch_gjr_top25_and_negative_5d | 4 | 0/4 | 0 | 72 | nan | 0.2278 | nan | 0.2470 |

## Conclusion

此 no-add gate 評估仍是 shadow-only。若 gate 不能穩定找出 NCF 看多但後續 H20 較差的樣本，就不能導入 groupA++ 最新策略。
