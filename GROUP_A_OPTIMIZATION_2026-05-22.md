# Group A Runtime Optimization

Date: 2026-05-22
Scope: Group A runtime-only sweep

## Result

Promote the runtime-only candidate from:

- `results/group_a_runtime_opt_sweep_20260522.json`

The checkpoint is unchanged:

- `models/portfolio/group_a_microopt_b060_p030_20260521_233524.zip`

## Best Candidate

Runtime overrides:

- `pva_weight = 0.30`
- `pva_j_state_weight = 0.17`
- `pva_drift_threshold = 0.05`
- `pva_min_leverage_scale = 0.40`
- `pva_buy_dip_strength = 0.70`
- `dca_day = 20`

Performance on `2024-01-02` to `2026-05-21`:

| Metric | Previous release | Optimized candidate | Delta |
|---|---:|---:|---:|
| Final value | 3,701,904.44 | 3,720,143.22 | +18,238.79 |
| Sharpe | 2.314227 | 2.330360 | +0.016133 |
| Max drawdown | -23.5605% | -23.0082% | +0.5523 pp |
| Trades | 99 | 99 | 0 |
| PVA activations | 52 | 54 | +2 |

This is a runtime adjustment only. No PPO retraining was performed.

## Implementation Update

Updated defaults in `train_dual_group_2024_2026.py`:

- `DEFAULT_GROUP_A_DCA_DAY = 20`
- `DEFAULT_GROUP_A_PVA_J_STATE_WEIGHT = 0.17`
- `DEFAULT_GROUP_A_PVA_MIN_LEVERAGE_SCALE = 0.40`
- `DEFAULT_GROUP_A_PVA_BUY_DIP_STRENGTH = 0.70`

Added reusable sweep tooling:

- `optimize_group_a_runtime.py`

Compatibility fixes needed to run the local validation environment:

- `train_dual_group_2024_2026.py`
  - Added `FloatSchedule` fallback for the installed Stable-Baselines3 version.
- `FinRL/__init__.py`
  - Made heavy optional `backtesting` / `strategies` imports tolerant of missing optional dependencies so lightweight data and signal workflows can still run.

Environment note:

- The existing venv launcher pointed at Python 3.12 but the shell could not use it directly.
- Validation was run with Python 3.12 and `PYTHONPATH=FinRL\.venv-backtest\Lib\site-packages`.
- `duckdb` was installed into that existing site-packages path because the DB-first loader required it.

Signal note:

- `results/group_a_runtime_opt_sweep_20260522.json` is experiment evidence, not a full production signal payload.
- Before production signal generation, create or update a runtime payload carrying the optimized overrides above.
- The existing signal snapshot remains from the previous release payload.

## Validation

Commands run:

```bash
python optimize_group_a_runtime.py \
  --pva-weight-grid 0.30 \
  --pva-j-grid 0.15 \
  --pva-drift-grid 0.05 \
  --pva-min-leverage-grid 0.35 \
  --pva-buy-dip-grid 0.60 \
  --dca-day-grid 20 \
  --output results/group_a_runtime_opt_smoke_20260522.json

python optimize_group_a_runtime.py \
  --output results/group_a_runtime_opt_sweep_20260522.json
```

The smoke run reproduced the prior release baseline:

- Final value: `3,701,904.44`
- Sharpe: `2.314227`
- Max drawdown: `-23.5605%`
- Trades: `99`

The full sweep tested the default local grid around the prior release settings and required no worse max drawdown and no extra trades.
