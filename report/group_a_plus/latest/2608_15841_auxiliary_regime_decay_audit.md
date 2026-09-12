# 2608.15841 Auxiliary Regime / Decay Audit

- Policy: `research_only_no_weight_change`
- Decision: `temporal_regime_stability_not_cleared`
- Stability passed: `False`
- Promotion allowed: `False`

| ticker | task | recent AUC | AUC decay | weak slices | pass |
|---|---|---:|---:|---|---:|
| `00631L.TW` | `h20_forward_drawdown_gt5` | 0.5689285714285715 | -0.0020583717357911535 | `none` | `True` |
| `00631L.TW` | `h20_forward_gain_gt5` | 0.5638233514821537 | -0.1252684269731562 | `tail_score_low` | `False` |
| `00632R.TW` | `h20_forward_drawdown_gt5` | 0.5360772357723578 | -0.041112997514614724 | `first_half, direction_up, confidence_low, tail_score_high` | `False` |
| `00632R.TW` | `h20_forward_gain_gt5` | 0.5072463768115942 | 0.1157331729910156 | `recent_126` | `False` |
| `0050.TW` | `h20_forward_drawdown_gt5` | 0.5260477869173521 | 0.1651329882057645 | `direction_down, tail_score_low` | `False` |
| `0050.TW` | `h20_forward_gain_gt5` | 0.5684121621621622 | 0.22387514212285597 | `none` | `False` |

This audit is shadow-only and does not alter live weights.
