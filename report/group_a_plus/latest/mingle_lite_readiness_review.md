# GroupA+ MINGLE-lite Readiness Review

- status: `research_only`
- paper: `2608.06618`
- method: `mingle_lite_pca_exposure_similarity_graph_not_full_admm`
- production_effect: `none`
- promotion_allowed: `False`

## Representation

- available_tickers: `16`
- observations: `519`
- sample_condition_number: `887.62`
- factor_condition_number: `15.18`
- condition_improvement_ratio: `58.47`

## Current Target Diversification

- risky_weight_sum: `0.6145`
- exposure_similarity_concentration: `0.150479`
- weighted_graph_degree: `8.873065`
- peripheral_alignment: `0.003734`

```json
{
  "0050.TW": 0.8624968605228295,
  "00631L.TW": 0.13750313947717055
}
```

## Assessment

MINGLE's exposure-locality idea is useful for diagnostics, but this report
implements only a PCA exposure-graph approximation, not the paper's full ADMM
joint optimiser. Keep it shadow-only until multi-window performance evidence
exists on the GroupA+ asset universe.

## Blocking Reasons

```json
[
  "research_only_no_live_weight_change",
  "full_mingle_admm_not_implemented"
]
```
