# 2609.08106 Latest Target-Weight Replay

- generated_at: `2026-09-12T07:28:14`
- policy: `shadow_only_no_orders_no_live_weight_change`
- window: `2025-07-01 -> 2026-09-10`
- event_count: `79`
- days_with_00631l_weight: `287`
- promotion_ready: `False`

| metric | latest baseline | 08106 sleeve | delta |
|---|---:|---:|---:|
| total_return | 1.2665837867723533 | 1.307873950564864 | 0.041290163792510715 |
| annual_return | 1.0361314908341241 | 1.0683249817267728 | 0.03219349089264867 |
| sharpe_ratio | 3.9620942674083817 | 4.1745658950930205 | 0.2124716276846388 |
| max_drawdown | -0.1225554841951223 | -0.12118750596720262 | 0.001367978227919675 |
| total_turnover | 2.974693557089355 | 6.214693557089355 | 3.2399999999999998 |

## Decision

- Use as latest-target-weight validation evidence only.
- Keep the complementarity score in advisory/reporting and continue forward shadow logging.
- Do not change latest GroupA++ target weights, execution plans, or orders.
