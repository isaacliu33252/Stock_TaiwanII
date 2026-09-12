# GroupA+ Dual-Regime Defensive Cash Floor Shadow Handoff - 2026-08-14

## Scope

Codex 2026-08-14 change. This is a research-only second-stage shadow after the single conditional defensive cash-floor sweep. It does not change live signals, target weights, execution plans, strategy manifests, or daily pipeline behavior.

The experiment splits defensive cash-floor activation into two cases:

- Crash-style defensive: strict `ma_gap <= -5%`, high-priority, higher cash floor.
- Slow-bear defensive: broader defensive weakness, lower-priority, optional `realized_vol_ratio_20_60` floor to avoid low-volatility drag.

Crash activation always takes priority. Slow-bear activation only applies on defensive days not already classified as crash-style.

## Files Changed

- `scripts/evaluate/sweep_group_a_plus_dual_regime_defensive_cash_floor.py`
  - New research-only dual-regime sweep.
  - Uses `run_latest()` for the active latest baseline and the existing dividend/cost simulator.
  - Contains `Codex 2026-08-14` research-only notes.
- `tests/test_sweep_group_a_plus_dual_regime_defensive_cash_floor.py`
  - Tests crash priority, slow-bear vol-ratio floor, and non-mutating shadow regime assignment.
  - Contains `Codex 2026-08-14` note.

## Outputs

- `results/group_a_plus_dual_regime_defensive_cash_floor_shadow_2020_covid_after_20260813_refresh.json`
- `results/group_a_plus_dual_regime_defensive_cash_floor_shadow_2022_rate_hike_after_20260813_refresh.json`
- `results/group_a_plus_dual_regime_defensive_cash_floor_shadow_2024_2026_after_20260813_refresh.json`
- `results/group_a_plus_dual_regime_defensive_cash_floor_shadow_2025_2026_after_20260813_refresh.json`

Each JSON has a paired CSV and top-variant frame CSV.

## Final Sweep Results

Variant count per window: 1,944.

| Window | Formal Pass Count | Best Variant | Final Delta | Sortino Delta | MDD Delta | Crash Days | Slow Days |
|---|---:|---|---:|---:|---:|---:|---:|
| 2020 COVID | 1,713 / 1,944 | `cr60_sl35_smg000_sdd11_str8_stl2_sv080` | +16,678.60 | +0.4006 | +5.15% | 20 | 0 |
| 2022 rate hike | 15 / 1,944 | `cr50_sl50_smg000_sdd05_str4_stl1_sv000` | +10,012.13 | +0.0076 | +0.91% | 89 | 21 |
| 2024-2026 | 1,941 / 1,944 | `cr60_sl50_smg000_sdd05_str4_stl1_sv100` | +39,979.09 | +0.0701 | +0.00% | 20 | 2 |
| 2025-2026 | 1,296 / 1,944 | `cr60_sl50_smg000_sdd05_str4_stl1_sv100` | +30,817.39 | +0.1257 | -0.00% | 20 | 2 |

## Common Parameter Check

No single variant passed all four windows on final value, Sortino, and max drawdown at the same time.

The blocker is specific:

- 2022 formal variants require `cr50_sl50_smg000..._sv000`: broad slow-bear activation with no vol-ratio floor.
- The same family fails 2020 final value by about `-5,226` to `-7,467`.
- It also fails 2025-2026 max drawdown by about `-0.04%`.
- Adding `slow_vol_ratio_min` improves 2020 and recent windows, but removes the 2022 slow-bear days needed to pass 2022.

Representative 2022-passing family:

| Variant Family | 2020 | 2022 | 2024-2026 | 2025-2026 | Blocker |
|---|---:|---:|---:|---:|---|
| `cr50_sl50_smg000_sdd05_str4_stl1_sv000` | -5,226.30 / +0.1540 / +2.40% | +10,012.13 / +0.0076 / +0.91% | +9,932.32 / +0.0331 / +0.00% | +7,656.20 / +0.0612 / -0.04% | 2020 final and 2025 MDD fail |

Format: final delta / Sortino delta / MDD delta.

## Interpretation

The crash-style cash floor is robust in 2020, 2024-2026, and 2025-2026. The slow-bear component is not robust enough for live promotion:

- 2022 needs broader, longer slow-bear cash raising.
- 2020 and 2025 need stricter or shorter slow-bear activation.
- A simple vol-ratio floor is not enough to satisfy all windows simultaneously.

## Decision

Do not promote the dual-regime cash floor to live strategy.

Keep the crash-style component as a stronger research candidate. Treat the 2022 slow-bear component as a separate problem requiring its own bear-market classifier or episode-age state, not as a generic defensive overlay.

## Recommended Next Step

Run a targeted 2022 slow-bear classifier shadow that activates only when the defensive episode looks like a persistent macro bear rather than a crash/rebound:

- candidate features: defensive episode age, `ma_gap` recovery failure, rolling return slope, vol-ratio regime, and total-risk persistence;
- validate against 2020, 2022, 2024-2026, and 2025-2026;
- require the same parameter family to pass all four windows before any live integration.

## Verification

- `.venv/bin/python -m pytest tests/test_sweep_group_a_plus_dual_regime_defensive_cash_floor.py -q`
  - `3 passed in 5.20s`
- `.venv/bin/python -m py_compile scripts/evaluate/sweep_group_a_plus_dual_regime_defensive_cash_floor.py`
- Four dual-regime sweeps completed successfully after the 2026-08-13 data refresh.
