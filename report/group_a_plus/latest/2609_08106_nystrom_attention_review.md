# 2609.08106 Nyström Attention Review

- generated_at: `2026-09-12T07:27:20`
- paper: `Nyström Attention Matches Full Attention for Cross-Sectional Stock Prediction`
- pdf: `/mnt/c/Users/isaac/Downloads/2609.08106_nystrom_attention_cross_sectional_stock_prediction.pdf`
- decision: `shadow_only`
- changes_latest_strategy: `False`
- changes_golden1_0531: `False`
- changes_golden2_0830: `False`

## Paper Takeaways

- Inter-stock attention contributes the largest ablation value in MASTER-style cross-sectional stock prediction.
- Attention is near-uniform but its small deviation from uniformity carries cross-sectional discrimination.
- The deviation matrix is low-rank; top modes capture most energy.
- Nyström attention with m=32 matches full attention at N=300 and N=800 in the reported tests.
- Sparse/top-K/graph-masked alternatives degrade performance.
- At N≈3500, cross-stock modules did not significantly beat a per-stock LSTM baseline.
- Reported economic Sharpe results are frictionless and exclude transaction costs.

## GroupA++ Fit

- Active strategy: `a2118_a2111_ncf_late_bull_deleverage`
- Current watchlist size: `6`
- Mismatch: GroupA++ currently trades a small ETF sleeve; the paper's strongest efficiency benefit appears at large cross-sections, so live adoption is not justified from this paper alone.

## Adoption Candidates

| candidate | status | live change | expected advantage |
|---|---|---:|---|
| `cross_asset_low_rank_attention_shadow` | `recommended_shadow` | `False` | Tests whether GroupA++ can extract complementarity among 0050/00631L/00632R/00679B/00713/2330 without hand-coded correlation masks. |
| `nystrom_attention_scaling_path` | `conditional_shadow` | `False` | Lower memory and inference cost for broad-universe shadow research. |
| `anti_correlation_complementarity_feature` | `recommended_shadow` | `False` | May improve 00631L deleverage and 00713/cash sleeve decisions by avoiding redundant risk exposure. |
| `avoid_graph_or_topk_sparse_masks` | `do_not_adopt` | `False` | None for current evidence; the paper finds sparse/graph alternatives degrade performance. |

## Recommendation

- Build cross_asset_low_rank_attention_shadow with Taiwan PIT data and cost-aware forward validation.
- Do not promote into latest strategy until Taiwan-specific purged walk-forward, multi-seed, cost-aware evidence passes.
