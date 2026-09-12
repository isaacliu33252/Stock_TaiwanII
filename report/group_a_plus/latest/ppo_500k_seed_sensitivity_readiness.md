# GroupA+ PPO 500k Seed Sensitivity Readiness

- Generated: `2026-08-15T11:02:09`
- Status: `blocked_for_seed_sensitivity`
- Decision: `seed_sensitivity_not_complete`
- Policy: `research_only_no_latest_replacement`

## Seed 42 Reference

- Zero-inverse final delta vs 100k: `198,601.60`
- Zero-inverse Sharpe delta vs 100k: `0.0199`
- Zero-inverse MDD delta vs 100k: `-0.12%`
- Zero-inverse volatility delta vs 100k: `3.03%`
- Zero-inverse fee delta vs 100k: `174.07`

## Required Seeds

| Seed | Model exists | Result exists | Complete |
|---:|---:|---:|---:|
| 7 | `False` | `False` | `False` |
| 13 | `False` | `False` | `False` |
| 21 | `False` | `False` | `False` |

## Commands To Run

Seed `7`:

```text
.venv/bin/python train_dual_group_2024_2026.py --xlsx taiwan_stock_20260516_group.xlsx --group-filter group_a --group-a-model-name group_a_500k_zero_inverse_s07 --group-a-profile default --group-a-action-schema triplet_v4 --group-a-enable-dca --group-a-enable-pva-sigmoid --group-a-00631l-max-weight 0.30 --group-a-00632r-max-weight 0.0 --group-a-pva-inverse-hedge-budget 0.0 --initial-cash 1000000 --train-start 2020-01-01 --train-end 2024-12-31 --backtest-start 2025-01-01 --backtest-end 2026-08-14 --timesteps 500000 --seed 7
```

Seed `13`:

```text
.venv/bin/python train_dual_group_2024_2026.py --xlsx taiwan_stock_20260516_group.xlsx --group-filter group_a --group-a-model-name group_a_500k_zero_inverse_s13 --group-a-profile default --group-a-action-schema triplet_v4 --group-a-enable-dca --group-a-enable-pva-sigmoid --group-a-00631l-max-weight 0.30 --group-a-00632r-max-weight 0.0 --group-a-pva-inverse-hedge-budget 0.0 --initial-cash 1000000 --train-start 2020-01-01 --train-end 2024-12-31 --backtest-start 2025-01-01 --backtest-end 2026-08-14 --timesteps 500000 --seed 13
```

Seed `21`:

```text
.venv/bin/python train_dual_group_2024_2026.py --xlsx taiwan_stock_20260516_group.xlsx --group-filter group_a --group-a-model-name group_a_500k_zero_inverse_s21 --group-a-profile default --group-a-action-schema triplet_v4 --group-a-enable-dca --group-a-enable-pva-sigmoid --group-a-00631l-max-weight 0.30 --group-a-00632r-max-weight 0.0 --group-a-pva-inverse-hedge-budget 0.0 --initial-cash 1000000 --train-start 2020-01-01 --train-end 2024-12-31 --backtest-start 2025-01-01 --backtest-end 2026-08-14 --timesteps 500000 --seed 21
```

## Decision

- Replace latest: `False`
- Tune latest: `False`
- Promote 500k to production: `False`
- Blocking reasons: `['missing_required_independent_500k_zero_inverse_seed_runs', 'seed42_zero_inverse_volatility_above_100k']`
- Missing required seeds: `[7, 13, 21]`

No latest strategy, live signal, execution plan, or order file was changed.
