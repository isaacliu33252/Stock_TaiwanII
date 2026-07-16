# Group A+ 00631L Leveraged Compounding Regime Handoff - 2026-07-13

## Context

User referenced:

```text
C:\Users\isaac\Downloads\2504.20116v1.pdf
2025 Compounding Effects in Leveraged ETFs: Beyond the Volatility Drag Paradigm
```

User summary:

- Leveraged ETF outcomes are not determined by volatility alone.
- Trend / positive autocorrelation can strengthen compounding.
- Mean reversion can create negative compounding by cutting exposure after
  declines and failing to restore exposure before rebounds.
- Therefore high volatility alone is not a sufficient reason to de-lever
  00631L.

This session converts that idea into a no-lookahead diagnostic regime layer.
Production allocation is not changed.

## Files Added

- `group_a_plus/integrations/leveraged_compounding_regime.py`
- `scripts/evaluate/evaluate_00631l_leveraged_compounding_regime.py`
- `tests/test_leveraged_compounding_regime.py`

Outputs:

- `results/00631l_leveraged_compounding_regime_20260713.json`
- `results/00631l_leveraged_compounding_regime_20260713.csv`

## Features

All features are backward-looking and computed from daily closes:

- `rolling_AR1_5d`
- `rolling_AR1_20d`
- `variance_ratio`
- `trend_persistence`
- `reversal_speed`
- `positive_return_streak`
- `negative_return_streak`
- `drawdown_recovery_ratio`
- `00631L_vs_0050_relative_momentum`

## Regime Labels

The classifier emits exactly three states:

```text
TREND_PERSISTENT
MEAN_REVERTING
TRANSITIONAL
```

Policy mapping:

| Regime | Policy |
|---|---|
| `TREND_PERSISTENT` | Do not reduce 00631L for high volatility alone. |
| `MEAN_REVERTING` | Prohibit new leverage or reduce rebalance frequency. |
| `TRANSITIONAL` | Maintain A21.18; do not actively overlay. |

The implementation uses a conservative scorecard. A single feature does not
decide the regime.

## Latest Result

Run command:

```bash
.venv/bin/python scripts/evaluate/evaluate_00631l_leveraged_compounding_regime.py
```

Latest classified date:

```text
2026-07-13
```

Latest regime:

```text
MEAN_REVERTING
```

Latest policy:

```text
prohibit_new_leverage_or_reduce_rebalance_frequency
```

Latest feature snapshot:

| Feature | Value |
|---|---:|
| `rolling_AR1_5d` | -0.1589 |
| `rolling_AR1_20d` | +0.0872 |
| `variance_ratio` | 0.9568 |
| `trend_persistence` | 0.5263 |
| `reversal_speed` | 0.2778 |
| `positive_return_streak` | 1 |
| `negative_return_streak` | 0 |
| `drawdown_recovery_ratio` | 0.2640 |
| `00631L_vs_0050_relative_momentum` | +0.0186 |
| `trend_score` | 3 |
| `mean_reversion_score` | 3 |

Interpretation:

- 20d AR1 and relative momentum are supportive.
- Short AR1, variance ratio, and weak trend persistence argue against a clean
  trend-persistent regime.
- The scorecard therefore classifies the latest state as mean-reverting.
- This is a leverage-addition guard, not an automatic de-risk instruction.

Recent 20 classified trading days:

```text
TREND_PERSISTENT: 9
MEAN_REVERTING: 6
TRANSITIONAL: 5
```

Full classified history:

```text
TREND_PERSISTENT: 550
MEAN_REVERTING: 1684
TRANSITIONAL: 541
```

## Production Decision

No production allocation, threshold, or A21.18 regime behavior was changed.

Allowed use:

- daily diagnostic,
- leverage-addition guard,
- explanatory context for why high volatility alone should not force 00631L
  reduction.

Not allowed from this result alone:

- automatic 00631L de-risk overlay,
- production threshold change,
- replacement of A21.18 regime logic.

## Daily Status Integration

User approved step 1:

```text
把 00631l_leveraged_compounding_regime 加進 daily status
```

Implemented:

- `scripts/misc/check_group_a_plus_daily_status.py` now loads an optional
  compounding-regime JSON.
- `scripts/run/run_ncf_daily_pipeline.py` now runs
  `scripts/evaluate/evaluate_00631l_leveraged_compounding_regime.py` before
  `daily_status` in full pipeline mode.
- `daily_status` receives the exact same-date compounding JSON path through
  `--compounding-regime`.

Daily status now records:

- `compounding_regime`
- `recommended_policy`
- `trend_score`
- `mean_reversion_score`
- feature snapshot:
  - `rolling_AR1_5d`
  - `rolling_AR1_20d`
  - `variance_ratio`
  - `trend_persistence`
  - `reversal_speed`
  - `positive_return_streak`
  - `negative_return_streak`
  - `drawdown_recovery_ratio`
  - `00631L_vs_0050_relative_momentum`

Validation run:

```bash
.venv/bin/python scripts/misc/check_group_a_plus_daily_status.py \
  --mode live \
  --live-signal report/group_a_plus/latest/live_signal.json \
  --execution-plan report/group_a_plus/latest/execution_plan.json \
  --compounding-regime results/00631l_leveraged_compounding_regime_20260713.json \
  --check-date 2026-07-13 \
  --output-prefix results/group_a_plus_daily_status_20260713
```

Generated:

- `results/group_a_plus_daily_status_20260713.json`
- `results/group_a_plus_daily_status_20260713.md`
- `report/group_a_plus/latest/daily_status.json`

Confirmed daily status payload:

```json
{
  "status": "ok",
  "date": "2026-07-13",
  "compounding_regime": "MEAN_REVERTING",
  "recommended_policy": "prohibit_new_leverage_or_reduce_rebalance_frequency",
  "trend_score": 3,
  "mean_reversion_score": 3,
  "active_allocation_impact": "none"
}
```

The daily status overall status was `warn`, but for pre-existing reasons:

- live signal actual data date was stale versus the 2026-07-13 check date,
- execution plan did not have an aligned pre-trade guard.

The new compounding diagnostic itself loaded successfully and did not block
execution.

## Verification

Commands run:

```bash
python3 -m py_compile group_a_plus/integrations/leveraged_compounding_regime.py scripts/evaluate/evaluate_00631l_leveraged_compounding_regime.py
pytest -q tests/test_leveraged_compounding_regime.py
python3 -m py_compile scripts/misc/check_group_a_plus_daily_status.py scripts/run/run_ncf_daily_pipeline.py
pytest -q tests/test_check_group_a_plus_daily_status.py tests/test_run_ncf_daily_pipeline.py tests/test_leveraged_compounding_regime.py
```

Result:

```text
3 passed
20 passed
```
