# PPO Runtime/Compression Review

- Generated: `2026-08-21T14:44:02`
- Status: `blocked`
- Policy: `runtime_governance_only_no_training_no_quantization_no_weight_change`
- Compression work allowed: `False`
- Target weight change allowed: `False`

## Blocking Reasons

- `runtime_bottleneck_not_demonstrated`
- `ppo_strategy_quality_not_improved_by_compression`
- `last_ppo_production_model_must_not_be_replaced`
- `prior_step_count_and_hnn_experiments_show_oos_tradeoff_risk`
- `no_latency_baseline_or_quantized_backend_benchmark`

## Artifacts

- `/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/models/portfolio/last_ppo_group_a_100k.zip` exists=`True` size=`207057`
- `/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/models/portfolio/last_ppo_group_a_500k.zip` exists=`True` size=`204894`
- `/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/models/portfolio/last_ppo_group_a_1000k.zip` exists=`True` size=`204897`
- `/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/models/portfolio/group_a_production_2020_2025_100k.zip` exists=`True` size=`207057`

## Decision

- Do not quantize or replace Last PPO.
- Runtime measurement is allowed only if latency becomes a measured bottleneck.
- No live strategy, target weight, rebalance, or order file was changed.
