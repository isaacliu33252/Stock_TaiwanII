# 2604.11335 00679B Tail-Dependence Break Alert

Generated: `2026-08-31T00:02:40`
Status: `available_for_shadow_monitoring`

## Summary

- Asset: `00679B.TWO` versus `0050.TW`
- Latest proxy: `0.076923`
- Baseline mean: `0.11592`
- Recent mean: `0.128816`
- Latest-baseline: `-0.038997`
- Recent-baseline: `0.012896`
- Break alert active: `False`

## Decision

- Shadow diagnostic only.
- Do not change target weights.
- Do not add `00679B.TWO` from low tail co-exceedance alone.
- If active, use only as a warning to downgrade bond-hedge confidence.
- Keep `Golden1_0531` unchanged.

