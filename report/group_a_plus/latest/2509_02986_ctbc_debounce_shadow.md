# 2509.02986 CTBC Debounce Shadow

- Policy: `research_only_no_weight_change`
- Decision: `do_not_promote_keep_shadow`
- Best candidate: `realized_var_20_top25_raw`
- Strict debounce gate passed: `False`
- Window: `2025-01-02` to `2026-08-10` rows=`388`

## Candidate Summary

| candidate | ok folds | pass | blocked rows | allowed rows | blocked gain | allowed gain | blocked mdd>5 | allowed mdd>5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `realized_var_20_top25_raw` | 4 | 0/4 | 24 | 46 | 0.2320 | 0.1637 | 0.2667 | 0.3260 |
| `realized_var_20_top25_2of3` | 4 | 0/4 | 20 | 50 | 0.2449 | 0.1586 | 0.0476 | 0.3500 |
| `realized_var_20_top25_3of3` | 4 | 0/4 | 18 | 52 | 0.2473 | 0.1572 | 0.0000 | 0.3431 |
| `garch_disagreement_top25_and_negative_1d_2of3` | 4 | 0/4 | 9 | 61 | 0.1092 | 0.2325 | 0.5000 | 0.2714 |
| `garch_disagreement_top25_and_negative_1d_raw` | 4 | 0/4 | 9 | 61 | 0.3338 | 0.2238 | 0.0714 | 0.2612 |
| `realized_var_20_top25_and_weak_ncf_raw` | 4 | 0/4 | 4 | 66 | 0.0972 | 0.2323 | 0.2500 | 0.2340 |
| `realized_var_20_top25_and_weak_ncf_2of3` | 4 | 0/4 | 2 | 68 | 0.1035 | 0.2316 | 0.0000 | 0.2321 |
| `realized_var_20_top25_and_weak_ncf_3of3` | 4 | 0/4 | 0 | 70 | NA | 0.2313 | NA | 0.2197 |
| `garch_gjr_top25_and_negative_5d_raw` | 4 | 0/4 | 0 | 70 | NA | 0.2313 | NA | 0.2197 |
| `garch_gjr_top25_and_negative_5d_2of3` | 4 | 0/4 | 0 | 70 | NA | 0.2313 | NA | 0.2197 |
| `garch_gjr_top25_and_negative_5d_3of3` | 4 | 0/4 | 0 | 70 | NA | 0.2313 | NA | 0.2197 |
| `garch_disagreement_top25_and_negative_1d_3of3` | 4 | 0/4 | 0 | 70 | NA | 0.2313 | NA | 0.2197 |

## Conclusion

CTBC 的 sliding-window trigger 概念目前只保留為 shadow。若不能穩定改善 00631L no-add 分辨力，就不能導入 groupA++ 最新策略。

This report does not emit trades, target weights, NCF gates, or order-generation changes.
