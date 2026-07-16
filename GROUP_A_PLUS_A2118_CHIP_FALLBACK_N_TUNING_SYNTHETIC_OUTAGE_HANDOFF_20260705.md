# GroupA+ A21.18 Chip-Fallback N Tuning — Synthetic Gradual-Outage Replay — 2026-07-05

## Summary

Follow-up to `GROUP_A_PLUS_A2118_CHIP_FALLBACK_HANDOFF_20260704.md`, which promoted
`chip_data_fallback_max_stale_days = 10` to production but flagged that neither the 2008 proxy
nor 2025-2026 real data can actually tune `N`: the 2008 proxy has core chip/derivative coverage
absent from day one (every `N` triggers immediately), and 2025-2026 real data has core coverage
stale by 0 days for all 361 rows (no `N` ever triggers). Both only prove the mechanism exists.

This session built a synthetic gradual-outage replay
(`scripts/misc/a2118_chip_fallback_synthetic_gradual_outage_20260705.py`, read-only research, no
production files touched) to test what `N` actually trades off. Output:
`results/a2118_chip_fallback_synthetic_gradual_outage_20260705.json`.

## Method

Two scenarios, both built on the real 2008 TWII proxy price series (the only window with a real
crash) with a synthetic `chip_data_core_days_since_source_update` ramp overriding the sentinel:

**Scenario A — calm-market false-trigger floor**: isolated, fully-recovering reporting gaps of
1/2/3/5/7 trading days sprinkled through the pre-crash period. Checks which `N` would spuriously
bypass the chip/derivative/total-risk gates during an ordinary reporting hiccup rather than a
real outage.

**Scenario B/C — sustained-outage response-lag ceiling**: a permanent, never-recovered outage
starting at one of three anchor points, replayed for `N in {1,2,3,5,7,10,15,20,30}`:
- worst case: outage starts exactly at the first genuine price-eligible trigger day (position
  100, 2007-11-23 — an early tremor, not the Lehman crash itself; the naive "first `True`"
  detection initially returned position 0 due to a `ma_gap`/`drawdown` `fillna(0.0)`
  rolling-window warm-up artifact — fixed by skipping the first `max(ma_window,
  drawdown_window)` rows before searching)
- best case: outage starts 90 trading days earlier (well before any real trigger)
- edge case: outage starts at the deepest point of the crash itself (2008-10-27, -50% drawdown)

## Results

**Scenario A**: gaps of length `k` false-trigger every `N <= k`. With gaps up to 7 trading days
tested, `N <= 7` would spuriously fire; `N=10` (production default) survives every gap tested.
This is an assumption-based bound, not empirical — real 2025-2026 data has never shown a
core-source gap at all, so there's no historical precedent for how large a real reporting hiccup
could actually be.

**Scenario B (worst-case timing, outage starts at the first real trigger)**: final equity
(vs-cash variant) across `N`: 1→4.06, 2→3.91, 3→4.09, 5→3.85, 7→4.14, **10→4.23**, 15→4.05,
20→3.59, 30→3.74. `N=10` is not worse than smaller `N` here — it's actually the best value in
the sweep — and MDD stays at -31.8% for `N<=15`, only degrading to -37.7% at `N=20/30`. The
relationship is not monotonic (path-dependent: whether price conditions are still true exactly
when the fallback unlocks depends on where the crash's up/down chop lands relative to `N` days
later), so this is not a clean optimization surface, but it gives no evidence that `N=10` is
worse than smaller values, and mild evidence that `N>=20` starts to cost something.

**Scenario C (best-case timing, outage starts 90 days before the trigger)**: differences across
`N` are small (final value 4.50–5.55, MDD -20.9% for all `N<=20`, only `N=30` degrades to
-31.8%) — confirms that when an outage is already well underway before a crisis, `N` barely
matters because days-since-update is already far past any tested threshold by the time price
conditions align.

**Scenario D (outage starts at the crash's deepest point)**: all `N` perform poorly (final value
0.74–1.11, MDD -80% to -84%) regardless of choice — because the -50% drawdown has already
happened *before* the outage (and thus the fallback) is even relevant. This isn't an `N`-tuning
result; it just confirms the fallback can't retroactively protect against damage sustained
before the outage starts, which is expected and not a reason to change `N`.

## Verdict

`N=10` clears the calm-market false-trigger floor (survives all gaps tested up to 7 trading
days) and shows no degradation — sometimes the best result in the sweep — in the worst-case
response-lag ceiling test. This is not proof `N=10` is globally optimal (the response-lag
relationship is noisy/path-dependent, and both floor and ceiling evidence here are
synthetic/assumption-based, not from a real historical outage), but it is a real, if modest,
confirmation that the already-promoted default survives the specific stress this session was
asked to test. **No production change made or recommended** — `group_a_plus/runners/a2118.py`'s
`CHIP_DATA_FALLBACK_MAX_STALE_DAYS = 10` is left as-is.

## Files Added This Session (Read-Only Research)

- `scripts/misc/a2118_chip_fallback_synthetic_gradual_outage_20260705.py`
- `results/a2118_chip_fallback_synthetic_gradual_outage_20260705.json`

No production code, tests, `group_a_plus_config.json`, or `report/*` files were modified in this
part of the session. (Separately, this session also closed the alert push-notification gap —
see `group_a_plus/operations/push_notifications.py` and its own memory entry — which does touch
production code and is part of the same pending, uncommitted batch.)
