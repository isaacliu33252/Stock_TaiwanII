# GroupA+ Slow-Bear Cash Floor Classifier Shadow Handoff - 2026-08-14

## Scope

Codex 2026-08-14 change. This is a research-only third-stage shadow after the conditional and dual-regime defensive cash-floor sweeps. It does not modify live strategy behavior, live target weights, execution plans, manifests, or daily pipeline behavior.

The purpose was to test whether the 2022 rate-hike loss pattern can be handled by a targeted slow-bear classifier instead of a generic defensive cash-floor overlay.

## Files Changed

- `scripts/evaluate/sweep_group_a_plus_slow_bear_cash_floor_classifier.py`
  - New research-only classifier sweep.
  - Uses the active latest baseline via `run_latest()`.
  - Uses existing dividend/cost simulator.
  - Classifier features:
    - defensive episode age;
    - MA recovery failure via rolling negative `ma_gap` ratio;
    - 20-day 0050 return;
    - drawdown;
    - rolling total-risk persistence.
  - Contains `Codex 2026-08-14` research-only notes.
- `tests/test_sweep_group_a_plus_slow_bear_cash_floor_classifier.py`
  - Tests defensive episode age, compounded 20-day return, crash-vs-slow labels, and non-live shadow regime labels.
  - Contains `Codex 2026-08-14` note.

## Outputs

- `results/group_a_plus_slow_bear_cash_floor_classifier_shadow_2020_covid_after_20260813_refresh.json`
- `results/group_a_plus_slow_bear_cash_floor_classifier_shadow_2022_rate_hike_after_20260813_refresh.json`
- `results/group_a_plus_slow_bear_cash_floor_classifier_shadow_2024_2026_after_20260813_refresh.json`
- `results/group_a_plus_slow_bear_cash_floor_classifier_shadow_2025_2026_after_20260813_refresh.json`

Each JSON has a paired CSV and top-variant frame CSV.

## Final Sweep Results

Variant count per window: 8,640.

| Window | Formal Pass Count | Best Variant | Final Delta | Sortino Delta | MDD Delta | Crash Days | Slow Days |
|---|---:|---|---:|---:|---:|---:|---:|
| 2020 COVID | 8,640 / 8,640 | `cr60_sl40_age0_mg000_dd05_r2012_nw20_nr80_rl5_tr6` | +16,704.64 | +0.4107 | +5.15% | 20 | 1 |
| 2022 rate hike | 0 / 8,640 | `cr50_sl50_age0_mg000_dd05_r2012_nw10_nr60_rl10_tr4` | +8,178.85 | -0.0100 | +0.74% | 89 | 14 |
| 2024-2026 | 8,640 / 8,640 | `cr60_sl50_age0_mg000_dd05_r2012_nw10_nr60_rl5_tr6` | +41,501.25 | +0.0712 | +0.00% | 20 | 2 |
| 2025-2026 | 8,640 / 8,640 | `cr60_sl50_age0_mg000_dd05_r2012_nw10_nr60_rl5_tr6` | +31,990.72 | +0.1274 | +0.00% | 20 | 2 |

## Common Parameter Check

No common parameter set passed all four windows.

The direct blocker is 2022:

- 2022 formal pass count is `0 / 8,640`.
- The best 2022 candidate improves final value by `+8,178.85` and MDD by `+0.74%`, but Sortino regresses by `-0.0100`.
- Since 2022 is the target window and no variant passes it, this classifier family should not be promoted or expanded in live code.

## Interpretation

The classifier again confirms that crash-style cash raising is useful, but it does not solve 2022.

For 2022, adding more cash during slow-bear defensive days improves final value and drawdown, but it worsens downside-return quality enough to fail the formal gate. That means the 2022 problem is likely not just "raise more cash during slow-bear"; the active defensive regime's basket and exit/recovery timing need separate attribution.

## Decision

Do not promote the slow-bear cash-floor classifier.

Do not keep adding more slow-bear cash-floor thresholds unless a new diagnostic first proves the loss comes from a specific exposure that cash-flooring can remove without worsening Sortino.

## Recommended Next Step

Move from cash-floor overlays to 2022 defensive-regime attribution:

- Compare 2022 `group_a_plus_defensive` days against alternate defensive holdings one asset at a time: 0050, 00679B, cash, and recovery basket.
- Attribute losses by sub-episode rather than full-year aggregate.
- Test whether the issue is basket composition, entry timing, exit timing, or recovery-ramp timing.
- Only after attribution, run a smaller candidate sweep on the identified mechanism.

## Verification

- `.venv/bin/python -m pytest tests/test_sweep_group_a_plus_slow_bear_cash_floor_classifier.py -q`
  - `4 passed in 5.40s`
- `.venv/bin/python -m py_compile scripts/evaluate/sweep_group_a_plus_slow_bear_cash_floor_classifier.py`
- Four slow-bear classifier sweeps completed successfully after the 2026-08-13 data refresh.
