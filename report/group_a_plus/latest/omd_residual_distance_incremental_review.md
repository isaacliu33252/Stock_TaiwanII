# OMD Residual-Distance Incremental Review

- as_of: `2026-08-20`
- actual data: `2009-07-14` to `2026-08-20`
- status: `research_complete_do_not_promote`
- policy: `research_only_no_weight_change`

## H20 Severe Drawdown Classifier

| signal | signal rate | precision | recall | FPR | lift |
| --- | ---: | ---: | ---: | ---: | ---: |
| `omd_high` | `0.591749` | `0.187272` | `0.578947` | `0.594779` | `0.978367` |
| `vol_high` | `0.28616` | `0.236379` | `0.353383` | `0.270246` | `1.234917` |
| `drawdown_high` | `0.277525` | `0.259291` | `0.37594` | `0.254227` | `1.354618` |
| `baseline_high` | `0.411609` | `0.244172` | `0.525063` | `0.384752` | `1.275633` |
| `omd_only` | `0.362437` | `0.176042` | `0.333333` | `0.369327` | `0.9197` |
| `both_high` | `0.229312` | `0.205021` | `0.245614` | `0.225452` | `1.071093` |

## Buckets

| bucket | days | H20 mean fwd DD | H20 mean fwd return |
| --- | ---: | ---: | ---: |
| `omd_only` | `1515` | `-0.035412` | `-0.003349` |
| `baseline_only` | `761` | `-0.039221` | `0.0046` |
| `both_high` | `975` | `-0.029541` | `0.020131` |
| `neither_high` | `944` | `-0.020399` | `0.016911` |
| `omd_high` | `2490` | `-0.033137` | `0.00575` |
| `baseline_high` | `1736` | `-0.033828` | `0.013252` |

## Decision

- promote_to_live: `False`
- target_weight_change_allowed: `False`
- allow_00631l_add: `False`
- blockers: `not_promoted_shadow_only, omd_only_days_do_not_improve_severe_drawdown_precision, omd_precision_lift_not_above_vol_drawdown_baseline`
