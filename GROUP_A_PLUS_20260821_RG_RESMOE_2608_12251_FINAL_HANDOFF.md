# GroupA+ 2608.12251 RG-ResMoE Final Handoff - 2026-08-21

## Scope

User provided `C:\Users\isaac\Downloads\2608.12251.pdf`, arXiv:2608.12251,
"Regime-Gated Residual Mixture-of-Experts for Cross-Sectional Volatility
Forecasting", and asked whether its advantages could be introduced into
GroupA+ / latest strategy.

This handoff records the final state after all GroupA+-relevant experiments:

- RG-ResMoE-lite pathway replication.
- Multi-ticker 0050.TW / 00631L.TW evaluation.
- H5/H10/H20 volatility forecast evaluation.
- High-vol-only gate threshold sweep.
- Residual-calibrated VaR sweep.
- Daily signal shadow wiring.
- Deep neural residual MoE follow-up.

Final decision:

- Full RG-ResMoE: do not promote.
- Deep MoE: do not promote and do not wire into daily signal.
- H5 high-vol-only RG-ResMoE-lite: keep as shadow advisory only.
- Residual-calibrated VaR: keep as shadow diagnostic only.
- No target weight or execution behavior may change from this research without
  a separate signed promotion review.

## Paper Takeaways

The paper's central claim is architectural:

- Bad pathway: append regime variables directly to the predictive input.
- Good pathway: keep base forecast separate and use regime variables only as a
  soft gate over residual correction experts.
- Soft routing is better than hard routing.
- K=2 to K=4 experts is enough; more experts do not necessarily improve.
- Benefits are concentrated in high-volatility periods.

Important limitation for GroupA+:

- The paper uses large cross-sectional equity pools.
- GroupA+ risk-bearing production surface is a small ETF set, mainly 0050 and
  00631L for this test.
- That small asset pool does not provide the same cross-sectional pooling that
  makes the paper's deep MoE stable.

## Implemented Research Components

### RG-ResMoE-lite integration

File:

- `group_a_plus/integrations/rg_resmoe_volatility_gate_shadow.py`

Important functions:

- `regime_scalar()`
- `rg_resmoe_pathways()`
- `build_rg_resmoe_shadow()`
- `latest_rg_resmoe_snapshot()`
- `compute_rg_resmoe_volatility_gate_shadow()`
- `compute_group_a_plus_rg_resmoe_volatility_gate_shadow()`
- `append_rg_resmoe_volatility_gate_shadow_log()`
- `load_rg_resmoe_readiness_review()`
- `build_rg_resmoe_h5_high_vol_shadow_advisory()`
- `append_rg_resmoe_h5_high_vol_shadow_advisory_log()`

Design:

- Base forecast is frozen HAR-RV.
- Input pathway appends regime scalar directly to HAR features.
- Gate pathway adds a residual correction on top of frozen HAR-RV.
- Soft gate uses trailing regime percentile rank.
- Default shadow tickers: `0050.TW`, `00631L.TW`.
- H5 high-vol gate quantile for advisory: `0.80`.

### Lite evaluator

File:

- `scripts/evaluate/evaluate_group_a_plus_rg_resmoe_volatility_gate_pilot.py`

Metrics:

- QLIKE.
- Win rate versus frozen HAR-RV base.
- log-variance R2.
- Diebold-Mariano test.
- Top realized volatility decile slice.
- Recent 2025-2026 slice.
- Raw Gaussian VaR.
- Residual-calibrated VaR.

Final defaults that matter:

- residual VaR window: `756`
- residual VaR min rows: `130`
- VaR 5pct tail buffer: `1.0`
- VaR 1pct tail buffer: `1.35`
- high-vol gate quantile: `0.80`

### Readiness review builder

File:

- `scripts/evaluate/build_group_a_plus_rg_resmoe_volatility_gate_readiness_review.py`

Outputs:

- `report/group_a_plus/latest/rg_resmoe_volatility_gate_readiness_review.json`
- `report/group_a_plus/latest/rg_resmoe_volatility_gate_readiness_review.md`

Latest readiness source:

- `results/group_a_plus_rg_resmoe_volatility_gate_pilot_multi_highvol_q080_b135_20260820.json`

### Deep MoE evaluator

File:

- `scripts/evaluate/evaluate_group_a_plus_deep_rg_resmoe_volatility_pilot.py`

Design:

- Frozen HAR-RV base.
- Tiny neural residual mixture-of-experts.
- Expert input: HAR realized-variance features.
- Gate input: regime scalar, trailing gate percentile, 5-day regime delta.
- 3 experts.
- dropout, weight decay, early stopping.
- residual shrinkage tested.
- Research-only; never target weights.

Deep review output:

- `report/group_a_plus/latest/deep_rg_resmoe_volatility_pilot_review.md`

## Experiment Matrix

### Lite RG-ResMoE tests

Core variants:

- `base_pathway`
- `input_pathway`
- `gate_pathway`
- `gate_pathway_soft`
- `high_vol_only_gate_pathway_soft`

Tickers:

- `0050.TW`
- `00631L.TW`

Horizons:

- H5
- H10
- H20

High-vol quantile sweep:

- q=0.80
- q=0.85
- q=0.90
- q=0.95

Residual VaR sweep:

- 252-day calibration.
- 504-day calibration.
- 756-day calibration.
- 1pct tail buffer 1.25 / 1.35 / 1.50.

Best retained readiness setting:

- high-vol q=0.80
- residual VaR window=756
- residual VaR 1pct buffer=1.35

### Deep RG-ResMoE tests

Core variants:

- `deep_gate_pathway`
- `high_vol_only_deep_gate_pathway`

Shrinkage variants:

- residual_shrinkage=1.00
- residual_shrinkage=0.50
- residual_shrinkage=0.25

Best conservative setting:

- residual_shrinkage=0.25
- refit_every=126
- epochs=50
- patience=8

## Final Lite Results

Readiness review:

- Full promotion ready: `False`
- Tail calibration ready: `True`
- H5 high-vol shadow ready: `partial`
- Trade policy: `shadow_only_no_weight_change`

Full soft gate blockers:

- `0050.TW:h5_soft_gate_pooled_not_positive`
- `0050.TW:h10_soft_gate_not_dm_significant`
- `0050.TW:h20_soft_gate_not_dm_significant`
- `00631L.TW:h5_soft_gate_not_dm_significant`
- `00631L.TW:h10_soft_gate_not_dm_significant`
- `00631L.TW:h20_soft_gate_not_dm_significant`

H5 high-vol-only details:

| Ticker | Ready | QLIKE Improvement | DM p-value | Tail Ready |
|---|---:|---:|---:|---:|
| 0050.TW | True | 0.77% | 0.0340 | True |
| 00631L.TW | True | 1.04% | 0.1629 | True |

0050.TW horizon summary:

| Horizon | Full Soft QLIKE | Full DM p | HV-only QLIKE | HV-only DM p | Cal VaR5 p | Cal VaR1 p |
|---|---:|---:|---:|---:|---:|---:|
| H5 | -1.04% | 0.4414 | 0.77% | 0.0340 | 0.1990 | 0.1158 |
| H10 | 0.34% | 0.7404 | 0.98% | 0.0741 | 0.6982 | 0.1240 |
| H20 | 0.33% | 0.7852 | 0.84% | 0.0951 | 0.1511 | 0.6900 |

00631L.TW horizon summary:

| Horizon | Full Soft QLIKE | Full DM p | HV-only QLIKE | HV-only DM p | Cal VaR5 p | Cal VaR1 p |
|---|---:|---:|---:|---:|---:|---:|
| H5 | 0.94% | 0.4413 | 1.04% | 0.1629 | 0.1344 | 0.4450 |
| H10 | 2.48% | 0.2043 | 1.56% | 0.1944 | 0.6144 | 0.7882 |
| H20 | 1.71% | 0.3389 | 0.74% | 0.2957 | 0.1842 | 0.0865 |

Interpretation:

- Full soft gate is not promotion-ready.
- H5 high-vol-only is useful enough to observe in daily shadow.
- 0050 H5 high-vol-only is the strongest single result because it has positive
  QLIKE improvement and DM p=0.0340.
- 00631L H5 high-vol-only is directionally positive but not DM significant.
- Residual-calibrated VaR passes the readiness layer after the 756-day / 1.35
  tail-buffer calibration.

## Final Deep MoE Results

Decision:

- Do not promote.
- Do not wire deep MoE into daily signal.

Best conservative setting tested:

- residual_shrinkage=0.25
- refit_every=126
- epochs=50
- patience=8

H5 results:

| Ticker | Lite Soft QLIKE | Deep QLIKE | Deep DM p | Deep Recent 2025-2026 | Deep Top-Vol Slice |
|---|---:|---:|---:|---:|---:|
| 0050.TW | -1.09% | -0.92% | 0.0381, not better | -3.20% | -2.92% |
| 00631L.TW | 0.97% | 0.82% | 0.5413 | 4.76% | 0.13% |

H10/H20 results:

| Ticker | Horizon | Deep QLIKE | DM p | Recent 2025-2026 | Top-Vol Slice |
|---|---:|---:|---:|---:|---:|
| 0050.TW | H10 | -2.97% | 0.0017, not better | -4.72% | -7.93% |
| 0050.TW | H20 | 1.99% | 0.4647 | -3.16% | -0.47% |
| 00631L.TW | H10 | -2.68% | 0.0604, not better | -1.39% | -7.34% |
| 00631L.TW | H20 | -1.23% | 0.3078, not better | -2.10% | -4.85% |

Interpretation:

- Deep MoE found isolated pockets but failed stability.
- It damaged 0050 in H5/H10; this is unacceptable because 0050 is the core risk
  anchor.
- It damaged 00631L in H10/H20.
- High-vol-only deep gating did not beat the H5 lite high-vol-only shadow.
- The result supports the prior that GroupA+ does not have enough independent
  cross-sectional data for a deep MoE to generalize safely.

## Daily Signal Wiring

File modified:

- `group_a_plus/operations/daily_signal.py`

New constants:

- `RG_RESMOE_VOLATILITY_GATE_SHADOW_LOG`
- `RG_RESMOE_H5_HIGH_VOL_SHADOW_ADVISORY_LOG`
- `RG_RESMOE_READINESS_REVIEW`

New output fields:

- `rg_resmoe_volatility_gate_shadow`
- `rg_resmoe_h5_high_vol_shadow_advisory`

Log files:

- `results/rg_resmoe_volatility_gate_shadow_log.jsonl`
- `results/rg_resmoe_h5_high_vol_shadow_advisory_log.jsonl`

Important invariant:

- The H5 advisory has `outputs_target_weights=false`.
- The H5 advisory has `allow_target_weight_change=false`.
- It must not alter `target_weights`, `target_values`, execution guard, or
  rebalance action.

## Verified Daily Run

Command run:

```bash
PYTHONPATH=. .venv/bin/python group_a_plus/operations/daily_signal.py \
  --as-of 2026-08-21 \
  --portfolio-value 1000000 \
  --output results/group_a_plus_live_signal_v2_20260821_rg_resmoe_h5_advisory.json \
  --latest-pointer report/group_a_plus/latest/live_signal_rg_resmoe_h5_advisory.json
```

Result:

- actual data date: `2026-08-20`
- execution regime: `golden1`
- target weights:
  - `0050.TW`: `0.3`
  - `00631L.TW`: `0.0`
  - `00632R.TW`: `0.0`
  - `00679B.TWO`: `0.0`
  - `cash`: `0.7`
- H5 advisory status: `partial_ready_shadow_only`
- `allow_target_weight_change`: `False`
- active H5 high-vol reference: `False`
- ready tickers: `0050.TW`, `00631L.TW`
- high-vol gate quantile: `0.8`

Daily H5 inputs on actual data date 2026-08-20:

0050.TW:

- H5 base forecast variance: `9.44362044266517e-05`
- H5 gate soft forecast variance: `9.335187046861919e-05`
- soft/base ratio: `0.9885178151259276`
- H5 gate weight: `0.5873015873015873`
- high-vol active: `False`

00631L.TW:

- H5 base forecast variance: `0.00026486634002894006`
- H5 gate soft forecast variance: `0.00027214836884617956`
- soft/base ratio: `1.0274932209824919`
- H5 gate weight: `0.5714285714285714`
- high-vol active: `False`

## Current Artifact List

Primary code:

- `group_a_plus/integrations/rg_resmoe_volatility_gate_shadow.py`
- `group_a_plus/operations/daily_signal.py`
- `scripts/evaluate/evaluate_group_a_plus_rg_resmoe_volatility_gate_pilot.py`
- `scripts/evaluate/build_group_a_plus_rg_resmoe_volatility_gate_readiness_review.py`
- `scripts/evaluate/evaluate_group_a_plus_deep_rg_resmoe_volatility_pilot.py`

Primary reports:

- `report/group_a_plus/latest/rg_resmoe_volatility_gate_readiness_review.json`
- `report/group_a_plus/latest/rg_resmoe_volatility_gate_readiness_review.md`
- `report/group_a_plus/latest/deep_rg_resmoe_volatility_pilot_review.md`
- `GROUP_A_PLUS_RG_RESMOE_VOLATILITY_GATE_PILOT_HANDOFF_20260820.md`
- `GROUP_A_PLUS_20260821_RG_RESMOE_2608_12251_FINAL_HANDOFF.md`

Primary results:

- `results/group_a_plus_rg_resmoe_volatility_gate_pilot_multi_highvol_q080_b135_20260820.json`
- `results/group_a_plus_deep_rg_resmoe_volatility_pilot_h5_shrink025_20260820.json`
- `results/group_a_plus_deep_rg_resmoe_volatility_pilot_h10_h20_shrink025_20260820.json`
- `results/group_a_plus_live_signal_v2_20260821_rg_resmoe_h5_advisory.json`
- `report/group_a_plus/latest/live_signal_rg_resmoe_h5_advisory.json`
- `results/rg_resmoe_volatility_gate_shadow_log.jsonl`
- `results/rg_resmoe_h5_high_vol_shadow_advisory_log.jsonl`

Additional sweep results:

- `results/group_a_plus_rg_resmoe_volatility_gate_pilot_20260820.json`
- `results/group_a_plus_rg_resmoe_volatility_gate_pilot_latest.json`
- `results/group_a_plus_rg_resmoe_volatility_gate_pilot_multi_20260820.json`
- `results/group_a_plus_rg_resmoe_volatility_gate_pilot_multi_highvol_only_b135_20260820.json`
- `results/group_a_plus_rg_resmoe_volatility_gate_pilot_multi_highvol_q085_b135_20260820.json`
- `results/group_a_plus_rg_resmoe_volatility_gate_pilot_multi_highvol_q095_b135_20260820.json`
- `results/group_a_plus_rg_resmoe_volatility_gate_pilot_multi_residual_var_20260820.json`
- `results/group_a_plus_rg_resmoe_volatility_gate_pilot_multi_residual_var_w252_20260820.json`
- `results/group_a_plus_rg_resmoe_volatility_gate_pilot_multi_residual_var_w756_20260820.json`
- `results/group_a_plus_rg_resmoe_volatility_gate_pilot_multi_residual_var_w756_b125_20260820.json`
- `results/group_a_plus_rg_resmoe_volatility_gate_pilot_multi_residual_var_w756_b135_20260820.json`
- `results/group_a_plus_rg_resmoe_volatility_gate_pilot_multi_residual_var_w756_b150_20260820.json`
- `results/group_a_plus_rg_resmoe_volatility_gate_pilot_multi_var_20260820.json`
- `results/group_a_plus_deep_rg_resmoe_volatility_pilot_h5_20260820.json`
- `results/group_a_plus_deep_rg_resmoe_volatility_pilot_h5_shrink050_20260820.json`

## Do Not Do

Do not:

- Promote full RG-ResMoE from these results.
- Wire deep MoE into daily signal.
- Use deep MoE for alerts, execution guard, or target weights.
- Let `rg_resmoe_h5_high_vol_shadow_advisory` change target weights.
- Treat H5 high-vol shadow as a trade rule.
- Continue tuning deep MoE on the same 2018-2026 window without a new
  validation design; that would be fixed-window overfitting.
- Reinterpret the 2026-08-20 older closed-negative wording as current state;
  the 2026-08-21 addendum and this final handoff supersede it.

## Allowed Follow-Up

Allowed:

- Continue daily H5 shadow logging.
- Compare future H5 active days against GARCH high-vol gate.
- Track whether H5 active days precede realized volatility spikes.
- Rebuild the readiness review if new out-of-sample daily observations
  accumulate.
- Keep residual-calibrated VaR as diagnostic.

Promotion prerequisites before any future live use:

- New out-of-sample evidence beyond this fixed research window.
- Positive QLIKE across 0050 and 00631L.
- DM support, especially for 00631L.
- No residual VaR Kupiec rejection.
- No degradation in recent 2025-2026 style slices.
- Explicit signed promotion review.

## Final State

This paper is complete for GroupA+ as of 2026-08-21.

Final implementation state:

- H5 RG-ResMoE-lite high-vol-only advisory remains in shadow.
- Deep RG-ResMoE is rejected.
- No target weights changed.
- Latest verified target weights remain 0050.TW 30%, cash 70%.
