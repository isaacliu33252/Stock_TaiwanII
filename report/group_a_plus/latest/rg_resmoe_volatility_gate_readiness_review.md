# RG-ResMoE Volatility Gate Readiness Review

- Generated: `2026-08-21T06:23:13`
- Decision: `do_not_promote_keep_shadow`
- Policy: `research_only_no_weight_change`
- Source: `results/group_a_plus_rg_resmoe_volatility_gate_pilot_multi_highvol_q080_b135_20260820.json`

## Layered Decision

- Full promotion ready: `False`
- Tail calibration ready: `True`
- H5 high-vol shadow ready: `partial`
- Trade policy: `shadow_only_no_weight_change`
- Interpretation: Full promotion remains blocked; calibrated tail references and H5 high-vol-only advisory can be observed in shadow without changing target weights.

## Blockers

- `0050.TW:h5_soft_gate_pooled_not_positive`
- `0050.TW:h10_soft_gate_not_dm_significant`
- `0050.TW:h20_soft_gate_not_dm_significant`
- `00631L.TW:h5_soft_gate_not_dm_significant`
- `00631L.TW:h10_soft_gate_not_dm_significant`
- `00631L.TW:h20_soft_gate_not_dm_significant`

## H5 Shadow Details

| Ticker | Ready | QLIKE Improvement | DM p-value | Tail Ready |
|---|---:|---:|---:|---:|
| 0050.TW | True | 0.77% | 0.0340 | True |
| 00631L.TW | True | 1.04% | 0.1629 | True |

## Ticker Summary

### 0050.TW

- Decision: `do_not_promote_keep_shadow`
- Blockers: `h5_soft_gate_pooled_not_positive, h10_soft_gate_not_dm_significant, h20_soft_gate_not_dm_significant`
- High-vol-only decision: `do_not_promote_keep_shadow`
- High-vol-only blockers: `h10_soft_gate_not_dm_significant, h20_soft_gate_not_dm_significant, h20_soft_gate_residual_var_1pct_kupiec_reject`

| Horizon | Full Soft QLIKE | Full DM p | HV-only QLIKE | HV-only DM p | Top Vol Decile | Recent 2025-2026 | Cal VaR5 Breach | Cal VaR5 Kupiec p | Cal VaR1 Breach | Cal VaR1 Kupiec p |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| H5 | -1.04% | 0.4414 | 0.77% | 0.0340 | 3.35% | -3.95% | 0.057 | 0.1990 | 0.006 | 0.1158 |
| H10 | 0.34% | 0.7404 | 0.98% | 0.0741 | 4.43% | -0.25% | 0.048 | 0.6982 | 0.007 | 0.1240 |
| H20 | 0.33% | 0.7852 | 0.84% | 0.0951 | 3.27% | 1.27% | 0.058 | 0.1511 | 0.009 | 0.6900 |

### 00631L.TW

- Decision: `do_not_promote_keep_shadow`
- Blockers: `h5_soft_gate_not_dm_significant, h10_soft_gate_not_dm_significant, h20_soft_gate_not_dm_significant`
- High-vol-only decision: `do_not_promote_keep_shadow`
- High-vol-only blockers: `h5_soft_gate_not_dm_significant, h10_soft_gate_not_dm_significant, h20_soft_gate_not_dm_significant`

| Horizon | Full Soft QLIKE | Full DM p | HV-only QLIKE | HV-only DM p | Top Vol Decile | Recent 2025-2026 | Cal VaR5 Breach | Cal VaR5 Kupiec p | Cal VaR1 Breach | Cal VaR1 Kupiec p |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| H5 | 0.94% | 0.4413 | 1.04% | 0.1629 | 3.06% | -3.46% | 0.058 | 0.1344 | 0.008 | 0.4450 |
| H10 | 2.48% | 0.2043 | 1.56% | 0.1944 | 6.44% | -1.18% | 0.053 | 0.6144 | 0.011 | 0.7882 |
| H20 | 1.71% | 0.3389 | 0.74% | 0.2957 | 4.76% | 0.34% | 0.057 | 0.1842 | 0.014 | 0.0865 |

## Promotion Requirements

- soft gate must show positive pooled QLIKE improvement for every tracked horizon
- DM test must support lower QLIKE than frozen HAR-RV base at 5% significance
- 0050 and 00631L must both pass before any combined gate can enter manual promotion review
- VaR breach rates must remain calibrated against 5% and 1% nominal levels in pooled and high-vol slices
- separate signed promotion review is required before target-weight or execution-guard wiring
