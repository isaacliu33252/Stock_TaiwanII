# 2602.24037 SCR Scenario Stress Score

Generated: `2026-09-12T08:39:30`
Status: `available_for_shadow_monitoring`
As of: `2026-09-10`

## Summary

- Scenario count: `60`
- Mean next return: `0.001626`
- Median next return: `0.000309`
- P10 next return: `-0.00684`
- VaR next return: `-0.007878`
- ES next return: `-0.012866`
- Probability loss: `0.45`
- Downside warning active: `False`

## Decision

- Shadow downside stress score only.
- Do not create orders or target weights.
- Do not train SCR-PPO from this score.
- Keep `Golden1_0531` unchanged.

