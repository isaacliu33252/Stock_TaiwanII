# GroupA+ TSI Stress OOS

- status: `research_only`
- as_of: `2026-09-09`
- actual_data: `2020-01-20` to `2026-09-09`
- policy: `research_only_tsi_stress_oos_no_weight_change`
- primary_threshold: `0.9`
- promotion_allowed: `False`
- target_weight_change_allowed: `False`

## Threshold Sweep

| threshold | alert_days | stress_window_alert_rate | non_window_alert_rate |
|---:|---:|---:|---:|
| 0.80 | 279 | 26.77% | 13.15% |
| 0.85 | 194 | 19.68% | 8.77% |
| 0.90 | 134 | 12.36% | 6.49% |
| 0.95 | 60 | 2.52% | 3.98% |

## Stress Windows

| window | days | alert_rate_at_primary_threshold | max_tsi_memory_percentile |
|---|---:|---:|---:|
| taiwan_2020_covid_crash | 97 | 13.40% | 100.00% |
| taiwan_2022_rate_hike_stress | 205 | 12.68% | 94.57% |
| taiwan_2026_q1q2_stress | 64 | 0.00% | 87.28% |
| taiwan_2026_recent | 71 | 21.13% | 94.51% |

## 20D Forward Outcome

Primary threshold only. Samples are alert/quiet.

| ticker | alert_avg_return | quiet_avg_return | alert_avg_max_drawdown | quiet_avg_max_drawdown | samples |
|---|---:|---:|---:|---:|---:|
| 0050.TW | 1.84% | 2.31% | -7.17% | -4.95% | 132/1515 |
| 00631L.TW | 3.45% | 4.60% | -12.97% | -9.11% | 132/1515 |

## Governance

TSI remains research-only. The paper frames it as a coincident stress-state
index, not a forecast. Golden1_0531 and latest strategy weights remain
unchanged.
