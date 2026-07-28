# TargetWeightSignal Contract + Point-in-Time Snapshot Store - 2026-07-26

## Status

**Implemented, additive, wired into the live daily-signal path as a
best-effort post-processing step.** No decision logic changed. 18 new
tests, all passing; all 52 existing `daily_signal`-related tests still
pass unchanged.

## Origin

User proposed (verbatim, in the same session as the arXiv:2601.04062v3 SPO
paper review, see `GROUP_A_PLUS_2601_04062_SPO_PAPER_REVIEW_HANDOFF_20260726.md`)
a frozen `TargetWeightSignal` dataclass and two new modules
(`group_a_plus/core/signal_contract.py`, `group_a_plus/core/point_in_time_store.py`)
plus a `results/ncf_snapshots/YYYY/MM/DD/` archive, framed as P0 --
verifying a2118's edge survives under fully reproducible/executable
conditions, prioritized above any new model. Asked "是合理的嗎?" (is this
reasonable?) before building.

**Assessed as well-motivated, not speculative infrastructure**, against
four real incidents already in this project's own history: the
golden1_0531 backtest payload being silently overwritten by a later
pipeline run using a different model (original release-time evidence
became unrecoverable); a2118's original promotion evidence only being
approximately reconstructable, not exactly reproducible; NCF ensemble
weights trained on the full sample (not rolling), so predictions for a
fixed historical date drifted every retrain; and `a2118.py`'s backtest
once not calling the same NCF-overlay function the live path calls, so a
headline Sharpe number was never actually produced by the code that ran
live (the reason checklist item 5 exists). All four are the same root
cause: no point-in-time record of "what a signal actually was, and what
produced it."

Two caveats raised before building, both addressed in the implementation:
1. Scope risk -- must wrap the existing signal output, not become a second,
   independently-maintained representation of "the signal" (would recreate
   the exact drift problem it's meant to prevent). **Addressed**:
   `from_daily_signal()` is a pure mapping from `build_daily_signal()`'s
   existing return dict; nothing about signal generation itself changed.
2. "P0, above any new model" is a strong claim to just accept without
   checking for in-flight conflicting work. Not independently verified in
   this session -- flagged as still worth confirming if it matters.

## What was built

**`group_a_plus/core/signal_contract.py`** -- `TargetWeightSignal` frozen
dataclass exactly as specified (`strategy_id`, `signal_asof`,
`generated_at`, `execution_date`, `weights`, `model_version`,
`feature_version`, `data_snapshot_hash`, `signal_reason`, plus an `extra`
dict for anything not worth promoting to a first-class field yet). Also:
- `from_daily_signal(daily_signal: dict, *, execution_date=None) -> TargetWeightSignal`
  -- pure mapping from `build_daily_signal()`'s return value. Verified
  against real production data (`report/group_a_plus/latest/live_signal.json`),
  not just synthetic fixtures.
- `model_version`: best-effort, derived from the NCF panel file's name +
  its last-covered date (`ncf_panel_coverage.panel_631l_path`/
  `panel_631l_last_date`). Falls back to `"unversioned"` when no panel path
  is present (grepped the whole codebase first -- no
  `model_version`/`feature_version`/panel-hash concept exists anywhere
  today, so this is genuinely new, not a duplicate).
- `feature_version`: **honestly `"unversioned"` always** -- there is no
  tracked feature-set versioning scheme in this codebase to draw from.
  Documented as a known gap rather than inventing a fake version number.
- `data_snapshot_hash`: real SHA-256, combining (a) the NCF panel file's
  byte-content digest (not just its path/mtime -- catches a silent
  overwrite even if the filename is unchanged, the exact golden1_0531
  failure mode) with (b) the resolved `target_weights`, `actual_data_date`,
  and `execution_regime`. Verified deterministic for identical input and
  distinct when either the panel bytes or the weights change (see
  `tests/test_signal_contract.py`).

**`group_a_plus/core/point_in_time_store.py`** -- append-only JSON archive
under `results/ncf_snapshots/YYYY/MM/DD/` (already covered by the existing
blanket `/results/` gitignore rule -- no new gitignore entry needed).
`write_snapshot()` names each file by `strategy_id` + `generated_at`
timestamp + hash prefix, so **a same-day rerun with different content
produces an additional file, never an overwrite** -- this is the specific
property the golden1_0531 incident needed and didn't have. Writing the
identical signal twice is a no-op (idempotent, doesn't create a duplicate).
`list_snapshots_for_date()` / `latest_snapshot_for_date()` / `read_snapshot()`
provide the read side.

**Wiring**: `group_a_plus/operations/daily_signal.py::main()` now calls
`write_snapshot(from_daily_signal(signal))` immediately after a successful
`build_daily_signal()` call, wrapped in its own `try/except` so a
snapshot-write failure can never turn a successful signal build into a
reported failure (matches this project's existing "best-effort step"
convention, e.g. the NCF `blend_live_auc` archive step). `build_daily_signal()`
itself is untouched.

## What was explicitly NOT done

- **`execution_plan.py` is not wired in.** Only `daily_signal.py`'s live
  signal path snapshots today. If execution-time (not just signal-time)
  point-in-time records are wanted, that's a separate, deliberately
  deferred addition.
- **No drift-detection alert.** The store makes it *possible* to compare
  `data_snapshot_hash` across snapshots for the same `signal_asof` (via
  `list_snapshots_for_date`), but nothing automatically checks or alerts on
  a mismatch yet -- this was scoped as the recording mechanism, not a new
  monitoring rule.
- **No retention/pruning policy.** `results/ncf_snapshots/` will grow by
  roughly one small JSON file per daily pipeline run indefinitely. Not a
  problem at current scale; worth a policy if this runs for years.
- **`run_a2118()` and its backtest engine were not touched or
  refactored.** Consistent with the 2026-07-24 FinRL-X-addendum decision
  that restructuring `run_a2118()`'s simulation engine is separate,
  dedicated-session-sized work.
- **The "P0, above any new model" prioritization claim was not
  independently checked** against whatever new-model work might already be
  queued.

## Files touched

- `group_a_plus/core/__init__.py` -- new.
- `group_a_plus/core/signal_contract.py` -- new.
- `group_a_plus/core/point_in_time_store.py` -- new.
- `group_a_plus/operations/daily_signal.py` -- two new imports, one
  `try/except`-wrapped call added inside `main()`. `build_daily_signal()`
  itself unchanged.
- `tests/test_signal_contract.py` -- new, 10 tests.
- `tests/test_point_in_time_store.py` -- new, 8 tests.

All verified: `python3 -m py_compile` on all three new/changed source
files, `pytest tests/test_signal_contract.py tests/test_point_in_time_store.py`
(18/18 passing), `pytest tests/ -k daily_signal` (52/52 still passing,
unchanged), plus a manual smoke test running `from_daily_signal()` and
`write_snapshot()` against the real
`report/group_a_plus/latest/live_signal.json` payload (not just synthetic
test fixtures) -- caught and fixed one real bug this way (`write_snapshot`
crashed on a string `root` argument instead of a `Path`; fixed by coercing
inside `_snapshot_dir`).
