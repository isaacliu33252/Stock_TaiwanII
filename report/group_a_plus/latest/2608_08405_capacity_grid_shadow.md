# 2608.08405 Capacity Grid Shadow

- status: not_identified_shadow_only
- as_of: 2026-09-09
- policy: finite_grid_capacity_interval_shadow_no_weight_change
- capital: 1000000.00
- arm_count: 5
- simultaneous_band_required: True
- capacity_interval_identified: False
- point_estimate_allowed: False
- capacity_scaling_allowed: False

## Blocking Reasons
- assigned_realized_deployment_not_ready
- market_impact_not_ready_for_capacity_grid
- randomized_parallel_sleeve_observations_missing
- edge_erosion_by_deployment_arm_missing
- simultaneous_band_not_estimable

## Grid Rows
- beta=0.0: scaled_risky_notional=0.00, impact_proxy_max_pov=0.0
- beta=0.5: scaled_risky_notional=410000.00, impact_proxy_max_pov=2.531684e-05
- beta=1.0: scaled_risky_notional=820000.00, impact_proxy_max_pov=5.063368e-05
- beta=1.5: scaled_risky_notional=1230000.00, impact_proxy_max_pov=7.595052e-05
- beta=2.0: scaled_risky_notional=1640000.00, impact_proxy_max_pov=0.00010126736

## Decision
A finite deployment grid can be specified, but no capacity interval is identified without randomized sleeve observations, realized deployment, and observed edge erosion by arm. Keep this as shadow governance only.
