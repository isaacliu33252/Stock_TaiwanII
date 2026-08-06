# GroupA+ TSMC Weakness Trim Wiring Handoff - 2026-07-30

## Status

Completed. `_apply_tsmc_weakness_trim()` is no longer dead code in the
GroupA+ live daily signal path.

The function was already implemented and unit-tested, and downstream alert
logic already read `tsmc_weakness_trim_applied`, but `build_daily_signal()`
never called it. That meant the trim could never affect live `target_weights`
and the downstream `tsmc_weakness_trim` alert was structurally unreachable.

This session wired the trim into `build_daily_signal()`, added a regression
test for the call ordering, and corrected stale audit/backtest documentation
that still described the trim as not live.

## Starting Point

User reported:

- `group_a_plus/operations/daily_signal.py:702`
  `_apply_tsmc_weakness_trim()` was defined with complete logic.
- No call site existed in `daily_signal.py`.
- Downstream alert construction around line 1171 read
  `tsmc_weakness_trim_applied`, which therefore stayed no-op forever.
- Decision needed: formally wire it with validation, or delete it to avoid
  misleading future audits.

Independent verification:

- `rg -n "_apply_tsmc_weakness_trim|tsmc_weakness_trim_applied|weakness_trim"`
  showed only the function definition, its overlay fields, unit tests, and
  downstream alert consumption.
- `scripts/evaluate/evaluate_a2118_live_overlay_backtest_gap.py` also
  documented the same state: the trim was "defined and unit-tested but never
  called from build_daily_signal".
- Existing unit tests already covered the function-level behavior:
  `test_tsmc_weakness_trim_requires_tsmc_and_00631l_confirmation` and
  `test_tsmc_narrow_leadership_is_diagnostic_only`.

The repo already had a large dirty worktree before this change. This handoff
documents only the TSMC weakness trim wiring work and does not claim ownership
of unrelated modified/deleted/untracked files.

## Decision

Wire the existing trim rather than delete it.

Rationale:

- The function already had narrowly gated policy:
  - only when `current_regime == "golden1"`;
  - only when `tsmc_0050_health.state == "tsmc_weak_confirmed"`;
  - only when 00631L's own NCF risk confirms weakness through low H20 upside
    probability or high H20 forward MDD risk.
- Downstream alerting already expected its output fields.
- The research/backtest script already had an opt-in reconstruction path for
  this exact production function, so the behavior was not an unreviewed new
  abstraction.
- Leaving it uncalled was worse operationally: it made the codebase look more
  defensive than live behavior actually was.

## Production Code Change

File changed:

- `group_a_plus/operations/daily_signal.py`

Change:

```python
target_weights, ncf_live_overlay = _apply_bearish_high_risk_trim(
    target_weights,
    latest_features,
    signal_alignment,
    ncf_live_overlay,
)
target_weights, ncf_live_overlay = _apply_tsmc_weakness_trim(
    target_weights,
    ncf_live_overlay,
)
```

Placement:

- Immediately after `_apply_bearish_high_risk_trim()`.
- Before `classify_market_state(...)` and before final signal payload
  construction.

Why after high-risk trim:

- Both functions are live golden1-local 00631L trims operating on resolved
  `target_weights`.
- `_apply_bearish_high_risk_trim()` uses broader `latest_features` and
  `signal_alignment` context.
- `_apply_tsmc_weakness_trim()` is a narrower confirmation trim that reads the
  NCF/TSMC overlay state and should apply to the remaining 00631L exposure if
  high-risk trim has already fired.
- The existing trim function recalculates cumulative `00631l_reduction` from
  `base_golden1_weights`, so sequential application preserves an aggregate
  reduction number.

Operational effect:

- If the TSMC weakness conditions do not hold, no weight change occurs.
- If conditions do hold, the function trims 25% of current 00631L exposure
  into cash by default, normalizes weights, and sets:
  - `tsmc_weakness_trim_applied`;
  - `tsmc_weakness_trim_fraction`;
  - `tsmc_weakness_trim_reduction`;
  - `tsmc_weakness_trim_reason`;
  - `adjusted_golden1_weights_before_tsmc_trim`;
  - `adjusted_golden1_weights`;
  - `00631l_reduction`;
  - `action = "reduce_00631l_tsmc_weakness"`.
- The existing `_build_signal_alerts()` branch for
  `tsmc_weakness_trim_applied` can now become reachable.

## Tests Added

File changed:

- `tests/test_group_a_plus_daily_signal_v2.py`

Added:

```python
def test_daily_signal_wires_tsmc_weakness_trim_after_high_risk_trim(self) -> None:
    source = inspect.getsource(daily_signal.build_daily_signal)

    high_risk_pos = source.index("_apply_bearish_high_risk_trim")
    tsmc_pos = source.index("_apply_tsmc_weakness_trim")

    self.assertLess(high_risk_pos, tsmc_pos)
```

Purpose:

- Locks in that `build_daily_signal()` contains a real call to
  `_apply_tsmc_weakness_trim()`.
- Locks in ordering after `_apply_bearish_high_risk_trim()`.
- Complements existing function-level tests rather than duplicating all TSMC
  trigger-condition logic.

Existing tests retained:

- TSMC weakness confirmed + 00631L weak reduces 00631L from 0.10 to 0.075 and
  moves the difference to cash.
- TSMC-led narrow leadership remains diagnostic-only and does not trim.

## Documentation / Research Script Update

File changed:

- `scripts/evaluate/evaluate_a2118_live_overlay_backtest_gap.py`

Updates:

- Replaced stale docstring language saying `_apply_tsmc_weakness_trim` was
  never called from `build_daily_signal`.
- Updated experiment `context` text to say the trim is live as of
  2026-07-30.
- Updated `--include-tsmc-trim` help text.

Important nuance:

- The script default still leaves `--include-tsmc-trim` off.
- That is intentional, so older audit comparisons can preserve the
  pre-2026-07-30 baseline.
- Passing `--include-tsmc-trim` now mirrors the current live daily signal path
  for this layer.

## Validation Run

Command:

```bash
python3 -m pytest tests/test_group_a_plus_daily_signal_v2.py -q
```

Result:

```text
49 passed
```

Additional grep check:

```bash
rg -n "never actually called|never called from build_daily_signal|not live today|not actually called from build_daily_signal" \
  scripts/evaluate/evaluate_a2118_live_overlay_backtest_gap.py \
  group_a_plus/operations/daily_signal.py \
  tests/test_group_a_plus_daily_signal_v2.py
```

Result:

- No matches.

## Files Touched In This Session

- `group_a_plus/operations/daily_signal.py`
- `tests/test_group_a_plus_daily_signal_v2.py`
- `scripts/evaluate/evaluate_a2118_live_overlay_backtest_gap.py`
- `handoff/2026-07/GROUP_A_PLUS_TSMC_WEAKNESS_TRIM_WIRING_HANDOFF_20260730.md`

## Residual Risk / Follow-Up

- Full test suite was not run in this session; only focused daily signal tests
  were run.
- Historical impact analysis is still opt-in via:

```bash
python3 scripts/evaluate/evaluate_a2118_live_overlay_backtest_gap.py --include-tsmc-trim
```

- If this trim later proves too aggressive in live monitoring, the right
  rollback point is the single call in `build_daily_signal()`, not deletion of
  the helper or downstream alert logic.
- The trim is cumulative with `_apply_bearish_high_risk_trim()` by design.
  Future audits should evaluate combined live behavior, not each layer in
  isolation.

