# OMD Residual-Distance Shadow Evaluation

- as_of: `2026-08-20`
- actual data: `2009-07-14` to `2026-08-20`
- status: `research_complete_do_not_promote`
- policy: `research_only_no_weight_change`

## Aggregate

- total days: `4195`
- stress manual review rate: `0.297992`
- non-stress manual review rate: `0.750508`
- high-risk days >= 0.75: `2490`
- high-risk rate >= 0.75: `0.593564`

## H20 Forward Drawdown Check

- high-risk mean H20 forward max drawdown: `-0.033137`
- normal mean H20 forward max drawdown: `-0.028804`

## Windows

| window | days | manual review rate | max risk pct | mean H20 fwd drawdown |
| --- | ---: | ---: | ---: | ---: |
| 2018_correction | 245 | 0.212245 | 0.948413 | -0.033821 |
| 2020_covid | 116 | 0.12069 | 0.607143 | -0.056749 |
| 2022_rate_hike | 246 | 0.211382 | 0.97619 | -0.052932 |
| 2024_2026_live | 638 | 0.396552 | 1.0 | -0.032366 |
| 2025_2026_active | 396 | 0.520202 | 1.0 | -0.03379 |

## Decision

- promote_to_live: `False`
- target_weight_change_allowed: `False`
- allow_00631l_add: `False`
- blockers: `manual_review_rate_not_higher_in_stress_windows, not_promoted_shadow_only`
