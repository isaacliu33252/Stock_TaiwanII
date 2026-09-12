# GroupA+ Conditional Defensive Cash Floor Shadow Handoff - 2026-08-14

## Scope

Codex 2026-08-14 change. This is a research-only shadow for the latest GroupA+ strategy after the 2026-08-13 data refresh. It does not change live weights, execution plans, strategy manifests, or daily pipeline behavior.

The experiment tests a narrower alternative to the static defensive basket replacement:

- Only fire inside `execution_regime == group_a_plus_defensive`.
- Require weak price action: `ma_gap <= threshold` and `exit_momentum <= 0`.
- Require at least one risk confirmation: drawdown, total risk score, or tail risk score.
- Raise cash floor by proportionally reducing risky ETF weights.

## Files Changed

- `scripts/evaluate/sweep_group_a_plus_conditional_defensive_cash_floor.py`
  - New research-only sweep.
  - Uses `group_a_plus.runners.latest.run_latest()` for baseline frame/report.
  - Replays baseline and shadow with `_simulate_costed_curve()` and `_load_total_return_prices()` from the existing defensive basket evaluator.
  - Contains explicit `Codex 2026-08-14` note that it must not write live targets.
- `tests/test_sweep_group_a_plus_conditional_defensive_cash_floor.py`
  - Tests cash-floor weight math, activation gating, and shadow-regime mutation behavior.
  - Contains explicit `Codex 2026-08-14` note.

## Outputs

- `results/group_a_plus_conditional_defensive_cash_floor_shadow_2020_covid_after_20260813_refresh.json`
- `results/group_a_plus_conditional_defensive_cash_floor_shadow_2020_covid_after_20260813_refresh.csv`
- `results/group_a_plus_conditional_defensive_cash_floor_shadow_2022_rate_hike_after_20260813_refresh.json`
- `results/group_a_plus_conditional_defensive_cash_floor_shadow_2022_rate_hike_after_20260813_refresh.csv`
- `results/group_a_plus_conditional_defensive_cash_floor_shadow_2024_2026_after_20260813_refresh.json`
- `results/group_a_plus_conditional_defensive_cash_floor_shadow_2024_2026_after_20260813_refresh.csv`
- `results/group_a_plus_conditional_defensive_cash_floor_shadow_2025_2026_after_20260813_refresh.json`
- `results/group_a_plus_conditional_defensive_cash_floor_shadow_2025_2026_after_20260813_refresh.csv`

Each run also wrote the top variant frame CSV with suffix `_*_frame.csv`.

## Backtest Windows

Initial value: 1,000,000.

Baseline is active latest strategy after 2026-08-13 refresh.

| Window | Baseline Final | Baseline Sortino | Baseline MDD | Best Variant | Final Delta | Sortino Delta | MDD Delta | Active Days | Formal Pass Count |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| 2020 COVID | 1,245,754.34 | 1.6095 | -13.93% | `cf55_mg050_dd05_tr4_tl1` | +14,768.84 | +0.3441 | +4.28% | 20 | 129 / 324 |
| 2022 rate hike | 846,876.29 | -1.5007 | -21.73% | `cf50_mg000_dd05_tr4_tl1` | +9,818.80 | +0.0041 | +0.89% | 110 | 83 / 324 |
| 2024-2026 | 2,299,183.52 | 1.8060 | -16.70% | `cf55_mg050_dd05_tr4_tl1` | +33,430.02 | +0.0589 | +0.00% | 20 | 315 / 324 |
| 2025-2026 | 1,772,296.99 | 2.0365 | -13.80% | `cf55_mg050_dd05_tr4_tl1` | +25,769.11 | +0.1053 | +0.00% | 20 | 216 / 324 |

## Multi-Window Common Parameter Check

No single parameter set passed all four windows on final value, Sortino, and max drawdown at the same time.

Representative common candidates:

| Variant | 2020 | 2022 | 2024-2026 | 2025-2026 | Reason Not Promoted |
|---|---:|---:|---:|---:|---|
| `cf55_mg050_dd05_tr4_tl1` | +14,768.84 / +0.3441 / +4.28% | -4,538.03 / -0.1506 / -0.31% | +33,430.02 / +0.0589 / +0.00% | +25,769.11 / +0.1053 / +0.00% | 2022 fails |
| `cf50_mg000_dd05_tr4_tl1` | -5,726.23 / +0.1388 / +2.33% | +9,818.80 / +0.0041 / +0.89% | +9,782.99 / +0.0329 / +0.00% | +7,541.10 / +0.0610 / -0.04% | 2020 final and 2025 MDD fail |
| `cf55_mg020_dd11_tr8_tl99` | +9,621.16 / +0.3117 / +4.28% | +4,038.22 / -0.0820 / +0.49% | +21,925.94 / +0.0492 / +0.00% | +16,901.34 / +0.0894 / +0.00% | 2022 Sortino fails |
| `cf40_mg020_dd11_tr8_tl99` | +7,007.95 / +0.1373 / +1.65% | +1,651.39 / -0.0025 / -0.11% | +14,160.56 / +0.0242 / +0.00% | +10,915.49 / +0.0427 / -0.00% | 2022 Sortino/MDD fail |

Format in common-candidate table: final delta / Sortino delta / MDD delta.

## Conclusion

The conditional cash-floor idea is better than static defensive basket replacement in this round:

- Every individual window has many passing variants.
- 2022 can be improved by a conditional floor without fully abandoning the current defensive basket.
- Recent windows do not show the large drag seen in the static defensive basket sweep.

However, it is not ready for live promotion because the best parameter differs by regime window, and no single common parameter passes all four windows. This should remain a shadow candidate.

## Recommended Next Step

Run a second-stage conditional design that separates two cases:

- Crash-style defensive episodes: stricter `ma_gap <= -5%` and higher cash floor, because 2020/2024/2025 liked short, strict activation.
- Slow bear defensive episodes: broader `ma_gap <= 0` but lower cash floor and an explicit Sortino guard, because 2022 liked longer activation but current broad variants hurt Sortino in other checks.

Do not promote either path until the same parameter family passes 2020, 2022, 2024-2026, and 2025-2026 together.

## Verification

- `.venv/bin/python -m pytest tests/test_sweep_group_a_plus_conditional_defensive_cash_floor.py -q`
  - `3 passed in 5.08s`
- `.venv/bin/python -m py_compile scripts/evaluate/sweep_group_a_plus_conditional_defensive_cash_floor.py`
- Four shadow sweeps completed successfully after the 2026-08-13 data refresh.
