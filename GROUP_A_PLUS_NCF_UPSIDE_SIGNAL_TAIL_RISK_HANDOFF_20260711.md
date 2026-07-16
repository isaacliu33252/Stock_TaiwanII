# Group A+ NCF Upside Signal Tail-Risk Fix — Handoff 2026-07-11

## Context

Follow-on to `GROUP_A_PLUS_NCF_DOWNSIDE_SIGNAL_BOTH_CONFLICT_FIX_HANDOFF_20260711.md`
(same day, earlier), which found and fixed a bug in `ncf_downside_signal`:
when both 00631L and 00632R simultaneously have `direction_conflict=True`,
the directional component is forced to 0, and the fixed 0.75/0.25 blend
diluted the tail-risk component for no reason (since directional
contributes 0 either way). That handoff explicitly flagged the mirror-image
gap as unaddressed:

> `ncf_upside_signal` has the same `direction_conflict`-zeroing pattern and
> was not touched — out of scope for this session, flagged here for anyone
> who picks up the equivalent upside-side investigation later.

This document is that follow-up, done later the same day after a separate
research arc (three more academic papers + chip-trigger directions, see
`GROUP_A_PLUS_GOOD_BAD_VOLATILITY_AND_CHIP_TRIGGERS_HANDOFF_20260711.md`,
`GROUP_A_PLUS_00631L_CED_DRAWDOWN_SERIAL_CORRELATION_HANDOFF_20260711.md`,
`GROUP_A_PLUS_ML_REWARD_RISK_TIMING_VOL_SCALING_HANDOFF_20260711.md`) all
converged on the same "return/vol-timing doesn't work on this data"
conclusion and the user asked what to do next. This fix was chosen
specifically because it is a known, understood, low-risk correction —
not another speculative signal test.

## What was found, and why the fix is bigger than "just mirror the downside fix"

Investigating `ncf_upside_signal` (in `group_a_plus/integrations/ncf.py`)
revealed the gap is not quite symmetric to what was fixed for downside:
`ncf_downside_signal` already had a tail-risk fallback component
(`ncf_tail_downside_signal`) before today's fix — the bug was only that the
both-conflict branch diluted it to 25% weight instead of using it at full
weight. `ncf_upside_signal`, by contrast, had **no tail-risk mechanism at
all** — no `include_tail_risk` parameter, no blend, always exactly
`raw = directional`. So both-conflict days didn't just dilute a fallback,
they had literally nothing to fall back to and always returned exactly 0.0.

The fix therefore does two things, not one:
1. Adds `ncf_tail_upside_signal()` — the mirror image of
   `ncf_tail_downside_signal()`, using `prob_fwd_gain_gt5_h20` for 00631L
   (high forward-gain probability for the direct ETF is bullish),
   `prob_fwd_mdd_gt5_h20` for 00632R (high forward-drawdown probability for
   the *inverse* ETF implies the market rising, also bullish), and
   `tail_reward_risk_score` signed the opposite way per ticker from the
   downside version (positive for 00631L, negative for 00632R).
2. Gives `ncf_upside_signal()` the same `0.75*directional + 0.25*tail`
   blend `ncf_downside_signal` already had, with the both-conflict
   full-tail-weight fix built in from the start (not fixed after the fact,
   since this mechanism never existed before today).

**Consequence: this change affects every day's `composite_upside_signal`
value, not just both-conflict days** — previously the signal was 100%
directional with zero tail-risk information; now tail risk is blended in on
every day tail inputs are available. Verified against the same 11 dated
NCF snapshot pairs used for the downside fix
(`results/ncf_00631l_latest_2026*.json` / `results/ncf_00632r_latest_2026*.json`):
only 2026-07-10 (the single both-conflict day) shows the full-tail-weight
behavior (0.0 -> 0.259), but every other day's value also changed from its
old directional-only number to the new blended one (e.g. 2026-07-08 went
from directional-only to a real 0.75/0.25 blend for the first time).

Also added, for symmetry in diagnostics: `ncf_has_tail_upside_inputs()`
(mirrors `ncf_has_tail_downside_inputs`), and `directional_upside_signal` /
`tail_upside_signal` fields in `ncf_regime_gated_signal()`'s and
`ncf_overlay_summary()`'s output dicts, matching the equivalent downside
fields that already existed there.

## Why this is safe despite the broad numeric change

`raw_upside_signal` / `composite_upside_signal` is **purely diagnostic** —
it is logged in `ncf_overlay_summary()`'s output but never read by
`adjust_golden1_weights()` (which only consumes the downside signal) or any
other live decision path. Confirmed by grep: the only production consumer
of `ncf_upside_signal`'s output is the summary dict itself. So despite
changing every day's number, this fix has zero effect on any live trading
weight, alert, or gate today. It matters for future correctness (if an
upside-aware overlay is ever built on top of this field) and for consistency
between the two signal families.

## Verification

1. **New tests** (`tests/test_group_a_plus_ncf_integration.py`, new
   `NCFUpsideSignalTailTests` class, 4 tests):
   - `test_tail_risk_boosts_upside_signal` — tail inputs present, no
     conflict -> blended value exceeds directional-only value.
   - `test_both_conflict_falls_back_to_full_tail_weight` — both conflict +
     tail inputs -> signal equals tail at full weight.
   - `test_both_conflict_with_no_tail_risk_stays_zero` — both conflict, no
     tail inputs -> still a clean 0.0.
   - `test_single_conflict_unaffected_by_fix` — only one side conflicts ->
     output matches the standard 0.75/0.25 blend formula.
   - Existing tests (`test_downside_upside_complement`,
     `test_upside_signal_unaffected_by_ma_gap`) use signal dicts with no
     tail-risk fields, so `ncf_has_tail_upside_inputs` returns False and
     behavior is unchanged for those specific tests — verified they still
     pass unmodified.
2. **Full test suite**: 73/73 in `test_group_a_plus_ncf_integration.py`
   (69 pre-existing + 4 new), 555/555 across the full
   `-k "ncf or group_a_plus"` selection. All pass, 0 failures.
3. **Historical replay** against all 11 dated NCF snapshot pairs
   (2026-06-27 to 2026-07-10): confirmed the pattern described above --
   broad change to the diagnostic value, zero effect on any weight (since
   nothing reads it).

## Files touched this session

**Modified:**
- `group_a_plus/integrations/ncf.py`: added `ncf_has_tail_upside_inputs`,
  `ncf_tail_upside_signal`; gave `ncf_upside_signal` an `include_tail_risk`
  parameter and the tail-blend/both-conflict logic; added
  `directional_upside_signal`/`tail_upside_signal` to
  `ncf_regime_gated_signal` and `ncf_overlay_summary` output dicts.
- `tests/test_group_a_plus_ncf_integration.py`: new
  `NCFUpsideSignalTailTests` class (4 tests), added
  `ncf_tail_upside_signal` to imports.

**Production impact: none** (diagnostic-only field, not consumed by any
live decision path, as established above).

## Status

Uncommitted, consistent with the rest of today's work.

## What's open for the future

If an upside-aware overlay is ever built (e.g. a symmetric
"increase 00631L when composite_upside_signal is high" rule), it would now
correctly incorporate tail-risk information including on both-conflict
days, matching the downside side's behavior from day one rather than
inheriting the gap that was found and fixed for downside first. No further
action needed on this specific asymmetry.

Related: `project_ncf_downside_signal_both_conflict_fix_20260711.md`
(the original downside fix this mirrors),
`GROUP_A_PLUS_GOOD_BAD_VOLATILITY_AND_CHIP_TRIGGERS_HANDOFF_20260711.md`,
`GROUP_A_PLUS_00631L_CED_DRAWDOWN_SERIAL_CORRELATION_HANDOFF_20260711.md`,
`GROUP_A_PLUS_ML_REWARD_RISK_TIMING_VOL_SCALING_HANDOFF_20260711.md`.
