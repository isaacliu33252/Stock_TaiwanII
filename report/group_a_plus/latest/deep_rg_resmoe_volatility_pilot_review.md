# Deep RG-ResMoE Volatility Pilot Review

Generated: 2026-08-21

Policy: research_only_no_weight_change

## Decision

Do not promote. Do not wire the deep MoE into daily signal.

The small neural residual MoE did not improve stability versus the existing RG-ResMoE-lite ridge residual gate. A residual shrinkage layer reduced the damage, but the result is still not robust enough for GroupA+.

## Tested Setup

- Base forecast: frozen HAR-RV variance forecast.
- Deep layer: tiny residual mixture-of-experts.
- Experts read HAR variance features.
- Gate reads regime scalar, trailing gate percentile, and 5-day regime delta.
- Target: residual log variance correction on top of frozen HAR-RV.
- Tickers: 0050.TW, 00631L.TW.
- Horizons: H5, H10, H20.
- Best tested conservative setting: residual_shrinkage=0.25, refit_every=126, epochs=50, patience=8.
- Outputs remain research-only and do not target weights.

## Key Results

### H5, residual_shrinkage=0.25

0050.TW:

- Lite soft gate QLIKE improvement: -1.09%, DM p=0.4353.
- Deep gate QLIKE improvement: -0.92%, DM p=0.0381, not better.
- High-vol-only deep QLIKE improvement: -0.67%, DM p=0.0002, not better.
- Recent 2025-2026 deep slice: -3.20%.
- Top-vol deep slice: -2.92%.

00631L.TW:

- Lite soft gate QLIKE improvement: +0.97%, DM p=0.4520.
- Deep gate QLIKE improvement: +0.82%, DM p=0.5413.
- High-vol-only deep QLIKE improvement: +0.04%, DM p=0.8445.
- Recent 2025-2026 deep slice: +4.76%.
- Top-vol deep slice: +0.13%.

### H10/H20, residual_shrinkage=0.25

0050.TW:

- H10 deep gate QLIKE improvement: -2.97%, DM p=0.0017, not better.
- H20 deep gate QLIKE improvement: +1.99%, DM p=0.4647.
- H10 recent slice: -4.72%; top-vol slice: -7.93%.
- H20 recent slice: -3.16%; top-vol slice: -0.47%.

00631L.TW:

- H10 deep gate QLIKE improvement: -2.68%, DM p=0.0604, not better.
- H20 deep gate QLIKE improvement: -1.23%, DM p=0.3078, not better.
- H10 recent slice: -1.39%; top-vol slice: -7.34%.
- H20 recent slice: -2.10%; top-vol slice: -4.85%.

## Interpretation

The deep MoE can find isolated positive pockets, especially 00631L H5 recent 2025-2026, but it fails the GroupA+ promotion standard:

- It is not consistently positive across tickers.
- It is not consistently positive across H5/H10/H20.
- DM tests do not support reliable improvement.
- High-vol-only deep gating does not beat the H5 lite high-vol-only shadow.
- 0050 is damaged in H5 and H10, which is unacceptable because 0050 is the core risk anchor.

## Next Action

Keep the existing RG-ResMoE-lite H5 high-vol shadow advisory. Do not add deep MoE to daily signal. The deep pilot script can remain available for future ablations, but it should not influence execution, alerts, or target weights.

Artifacts:

- results/group_a_plus_deep_rg_resmoe_volatility_pilot_h5_shrink025_20260820.json
- results/group_a_plus_deep_rg_resmoe_volatility_pilot_h10_h20_shrink025_20260820.json
- scripts/evaluate/evaluate_group_a_plus_deep_rg_resmoe_volatility_pilot.py
