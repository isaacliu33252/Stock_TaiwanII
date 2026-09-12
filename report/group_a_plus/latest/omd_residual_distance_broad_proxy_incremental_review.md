# OMD Residual-Distance Incremental Review

- as_of: `2026-08-20`
- actual data: `2019-06-27` to `2026-08-20`
- status: `research_complete_do_not_promote`
- policy: `research_only_no_weight_change`

## H20 Severe Drawdown Classifier

| signal | signal rate | precision | recall | FPR | lift |
| --- | ---: | ---: | ---: | ---: | ---: |
| `omd_high` | `0.37078` | `0.175824` | `0.287918` | `0.395034` | `0.776519` |
| `vol_high` | `0.347497` | `0.318258` | `0.488432` | `0.306245` | `1.405571` |
| `drawdown_high` | `0.294529` | `0.395257` | `0.514139` | `0.230248` | `1.745633` |
| `baseline_high` | `0.470896` | `0.346106` | `0.719794` | `0.398044` | `1.528562` |
| `omd_only` | `0.231665` | `0.170854` | `0.174807` | `0.248307` | `0.75457` |
| `both_high` | `0.139115` | `0.1841` | `0.113111` | `0.146727` | `0.813071` |

## Buckets

| bucket | days | H20 mean fwd DD | H20 mean fwd return |
| --- | ---: | ---: | ---: |
| `omd_only` | `445` | `-0.027975` | `0.000957` |
| `baseline_only` | `590` | `-0.051604` | `0.004415` |
| `both_high` | `239` | `-0.023009` | `0.049205` |
| `neither_high` | `590` | `-0.015559` | `0.041647` |
| `omd_high` | `684` | `-0.026112` | `0.019059` |
| `baseline_high` | `829` | `-0.043156` | `0.017647` |

## Decision

- promote_to_live: `False`
- target_weight_change_allowed: `False`
- allow_00631l_add: `False`
- blockers: `not_promoted_shadow_only, omd_only_days_do_not_improve_severe_drawdown_precision, omd_precision_lift_not_above_vol_drawdown_baseline`
