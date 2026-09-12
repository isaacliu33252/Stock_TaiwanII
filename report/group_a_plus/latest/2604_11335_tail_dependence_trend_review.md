# 2604.11335 Tail Dependence Trend Review

Generated: `2026-08-31T00:00:40`
Status: `available_for_shadow_monitoring`

## Decision

- Best import: `shadow_tail_dependence_trend_diagnostic_only`.
- Do not promote a full tail-copula test to live gating.
- Do not change latest strategy target weights.
- Do not add `00631L.TW` or open `00632R.TW` from this paper.
- Keep `Golden1_0531` unchanged.

## Latest Lower-Tail Snapshot

| Asset | Lower-tail proxy | Co-exceedance days | Correlation |
| --- | ---: | ---: | ---: |
| 00631L.TW | 0.923077 | 24 | 0.975193 |
| 00632R.TW | 0.0 | 0 | -0.978399 |
| 00679B.TWO | 0.076923 | 2 | -0.027451 |

## Trend Summary

| Asset | Latest | Long-run mean | Recent-prior | Slope |
| --- | ---: | ---: | ---: | ---: |
| 00631L.TW | 0.923077 | 0.843205 | 0.050657 | -3e-06 |
| 00632R.TW | 0.0 | 0.0 | 0.0 | 0.0 |
| 00679B.TWO | 0.076923 | 0.116797 | 0.012896 | 5.4e-05 |

## Alerts

- High latest assets: `['00631L.TW']`
- Rising recent tail-dependence assets: `[]`
- Warning reasons: `['00631l_lower_tail_dependence_high_vs_0050', 'high_latest_lower_tail_dependence_present']`

