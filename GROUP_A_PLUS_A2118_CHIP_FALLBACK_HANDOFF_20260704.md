# GroupA+ A21.18 Chip-Data Fallback Handoff - 2026-07-04

## Summary

Follow-up to `GROUP_A_PLUS_FABLE_AUDIT_MARKET_STATE_ARBITRATION_HANDOFF_20260704.md`.

The a2118 defensive switch gap has been addressed and promoted with
`chip_data_fallback_max_stale_days = 10`.

Problem:

- A21.11/A21.18 enters `group_a_plus_defensive` only when price entry conditions are met
  and `total_risk_score >= 6`.
- If chip/derivative inputs are unavailable, those inputs silently default to zero, so
  `total_risk_score` stays below 6 and defensive entry becomes structurally impossible.
- The 2008 TWII proxy exposed this: the original rule stayed `golden1` for the entire crash.

Implemented:

- `_switch_returns(..., chip_data_fallback_max_stale_days=None)` in
  `backtest_group_a_plus_switch_policy.py`.
- Its default remains `None`, so non-a2118 callers are unchanged.
- `group_a_plus.runners.a2118` now defaults to
  `CHIP_DATA_FALLBACK_MAX_STALE_DAYS = 10`.
- `report/group_a_plus/latest/strategy.json` passes
  `"chip_data_fallback_max_stale_days": 10` in active `runner_params`.
- When explicitly set, stale core chip/derivative coverage bypasses the chip/derivative/total
  risk entry gates, allowing the existing price conditions to drive defensive entry.
- `tail_risk_score` is not bypassed, because it is price/return-derived rather than chip-source
  derived.

Important refinement:

- Source freshness is split into:
  - `chip_data_days_since_source_update`: any raw source, diagnostic only.
  - `chip_data_core_days_since_source_update`: decision-relevant core sources, used by fallback.
- This matters because `market_margin_data` exists in the 2008 DB path and can keep the any-source
  clock fresh even when ETF/institutional/derivative core sources are absent.

## Verification

Unit tests:

```bash
.venv/bin/python -m pytest tests/test_backtest_group_a_plus_switch_policy_chip_fallback.py -q
```

Result: `7 passed`.

Regression tests:

```bash
.venv/bin/python -m pytest tests/test_group_a_plus_latest_strategy.py tests/test_group_a_plus_daily_signal_v2.py -q
```

Result: `49 passed`.

2008 proxy verification:

```bash
.venv/bin/python scripts/misc/a2118_chip_fallback_2008_proxy_verify.py
```

Output: `results/a2118_chip_fallback_2008_proxy_verify_20260704.json`

Key results:

| Variant | Defensive days | Cash-defense final | Cash-defense MDD | 00632R-hedge final | 00632R-hedge MDD |
|---|---:|---:|---:|---:|---:|
| real_rule | 0 | 0.7947 | -84.59% | 0.7947 | -84.59% |
| fallback_enabled | 436 | 4.7927 | -20.92% | 9.1601 | -22.78% |
| idealized price-only | 436 | 4.7927 | -20.92% | 9.1601 | -22.78% |

Modern 2025-2026 equivalence check:

- rows: 361
- max any-source stale days: 0
- max core-source stale days: 0
- regimes identical with/without fallback: `true`
- events identical with/without fallback: `true`
- baseline defensive days: 94
- fallback defensive days: 94

Threshold sweep:

```bash
.venv/bin/python scripts/misc/a2118_chip_fallback_threshold_sweep.py
```

Output: `results/a2118_chip_fallback_threshold_sweep_20260704.json`

Verdict:

- 2008 verifies the outage fix but cannot tune `N`; core coverage is absent from the first row,
  so all tested values `{1,2,3,5,7,10,15,20,30}` trigger from day one.
- 2025-2026 cannot tune `N` either; core-source stale days are always zero, so all tested values
  are equally safe from false triggers.
- A real `N` choice still needs a synthetic gradual-outage replay or a real partial-outage
  incident.

## Production Status

Production manifest updated to `N=10`.

On normal 2025-2026 data this produces no regime/event change because core-source stale days
remain 0 throughout the verified window. It only changes behavior during core chip/derivative
source outages.

Recommended next step:

1. Regenerate `report/group_a_plus/latest/live_signal.json` / latest runner output after the
   next daily pipeline run so the report artifacts include the new `rules` metadata.
2. Add a synthetic gradual-outage replay later if we want to revisit whether `N=10` is too slow
   or too fast.
