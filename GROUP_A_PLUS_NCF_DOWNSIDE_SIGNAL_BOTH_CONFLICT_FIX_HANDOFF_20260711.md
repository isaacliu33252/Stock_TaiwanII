# Group A+ NCF Downside Signal "Both-Conflict" Fix — Handoff 2026-07-11

## Trigger

User provided `Downside_20260711.pdf` and asked why it's "導入 Group A+ 效果不對"
(imported into Group A+, the effect is wrong). The PDF turned out to be
Wang & Yan (2021, JBF), *"Downside risk and the performance of
volatility-managed portfolios"* — the same paper already read and tested
earlier the same day (see `GROUP_A_PLUS_PAPER_IMPORTS_HANDOFF_20260711.md`,
Part 2). That investigation is unrelated to this one and its conclusion is
unchanged: **null result, not integrated into any live gate.** See that
handoff and memory `project_downside_vol_return_timing_20260711.md` for the
full record; this document does not revisit it.

The user's "effect is wrong" premise pointed at the wrong mechanism. This
session redirected to the actual live, production "downside" signal —
`ncf.py`'s `ncf_downside_signal` — and found (and fixed) a real edge case in
it. Unrelated to the Wang & Yan paper; discovered only because reading the
paper prompted checking what "downside" actually means in this codebase.

## What was found

`report/group_a_plus/latest/live_signal.json`'s
`ncf_live_overlay.gated_downside_signal` read **0.0** on 2026-07-10, versus a
normal historical range of ~0.02–0.14 (checked against 4 dated snapshots:
06/28, 06/29, 07/01). This signal is live — it drives `adjust_golden1_weights`,
which trims 00631L.TW allocation within the golden1 regime.

### Root cause

`ncf.py:ncf_downside_signal()` zeroes out each ticker's contribution when that
ticker's `direction_conflict` flag is true (direction from
`calibrated_probability_up` disagrees with the sign of `weighted_return`):

```python
l_bear = 0.0 if l_conflict else max(0.0, (0.5 - l_prob)) * 2.0 * l_conf
r_bull = 0.0 if r_conflict else max(0.0, (r_prob - 0.5)) * 2.0 * r_conf
```

On 2026-07-10, **both** 00631L and 00632R had `direction_conflict=True`
simultaneously, zeroing `directional` entirely. The tail-risk component
(`ncf_tail_downside_signal`) also happened to net to exactly 0.0 that day (all
four of its sub-scores — `prob_fwd_mdd_gt5_h20`, `prob_fwd_gain_gt5_h20`, both
`tail_reward_risk_score`s — landed on the "no risk" side), so the composite
signal came out to a legitimate 0.0 for that specific day. But the code path
that produced it had a real, general-case gap: see below.

### Why 73% single-ticker conflict rate is not a threshold-tuning bug

Investigated whether `direction_magnitude_gate`'s thresholds
(`min_probability_edge=0.05`, `min_abs_return=0.002`) were mistuned. They are
not — `direction_conflict` doesn't even use them:

```python
"direction_conflict": (
    _gate["return_side"] not in {"FLAT"} and _gate["return_side"] != _gate["direction"]
)
```

Traced `calibrated_probability_up` and `weighted_return` back to
`scripts/misc/ncf_00631l.py:2963-3049`: they are **two independently-weighted
ensembles over the same h1/h5/h20 sub-models**, using different validation
metrics —
- `calibrated_probability_up` uses `dir_w`, weighted by **classification AUC**
- `weighted_return` uses `return_w`, weighted by **inverse regression MAE²**

Different horizons can be reliable for classification but not regression (or
vice versa), so the two blends disagreeing is a structural, expected property
of this design, not a bug. Measured across the 11 available dated NCF
snapshot pairs (2026-06-27 to 2026-07-10):

| Metric | Rate |
|---|---|
| At least one ticker `direction_conflict=True` | 8/11 (73%) |
| Both tickers `direction_conflict=True` simultaneously | 1/11 (07-10 only) |

**Conclusion: the conservative zeroing itself is reasonable design ("don't
trust a model whose direction and return heads disagree"). The bug is what
happens when both tickers hit this simultaneously** — the composite fully
collapses to 0.0 (or, more precisely, dilutes tail risk to 25% weight) exactly
when directional information is least trustworthy and tail-risk information
should matter most.

## Fix

`group_a_plus/integrations/ncf.py`, `ncf_downside_signal()`: when both
`l_conflict` and `r_conflict` are true, use `tail_downside_signal` at full
weight instead of the standard `0.75×directional + 0.25×tail` blend (which,
with `directional` forced to 0, would otherwise silently discount tail risk to
25% for no reason — `directional` contributes nothing in this branch either
way, so diluting `tail`'s weight was pure information loss, not a deliberate
trade-off).

```python
if l_conflict and r_conflict:
    raw = tail
else:
    raw = float(min(max(0.75 * directional + 0.25 * tail, 0.0), 1.0))
```

Scope: **downside signal only**. `ncf_upside_signal` has the same
`direction_conflict`-zeroing pattern and was not touched — out of scope for
this session, flagged here for anyone who picks up the equivalent upside-side
investigation later.

## Verification

1. **New unit tests** (`tests/test_group_a_plus_ncf_integration.py`,
   `NCFDownsideSignalTests`):
   - `test_both_conflict_falls_back_to_full_tail_weight` — both conflict +
     tail inputs present → signal equals tail at full weight, not 25%.
   - `test_both_conflict_with_no_tail_risk_stays_zero` — both conflict + no
     tail inputs → still a clean 0.0 (no crash, no regression).
   - `test_single_conflict_unaffected_by_fix` — only one side conflicts →
     output identical to the pre-fix 0.75/0.25 blend formula.
2. **Existing test suite**: 69/69 in `test_group_a_plus_ncf_integration.py`,
   99/99 across `test_group_a_plus_daily_signal_v2.py` /
   `test_group_a_plus_signal_alignment.py` /
   `test_group_a_plus_execution_plan_v2.py` /
   `test_group_a_plus_latest_strategy.py`, and 551/551 across the full
   `-k "ncf or downside or group_a_plus"` selection. All pass, 0 failures.
3. **Historical replay** against all 11 dated NCF snapshot pairs
   (`results/ncf_00631l_latest_2026*.json` /
   `results/ncf_00632r_latest_2026*.json`, loaded via the real
   `load_ncf_signal`): **10/11 days produce bit-identical output** (no
   regression on any single-conflict or no-conflict day — the branch is only
   reachable when both flags are true). The 1 both-conflict day (07-10) also
   produces the same 0.0 post-fix, because — separately, and confirmed
   independently — `tail_downside_signal` itself was 0.0 that day. **This fix
   does not change today's live number.** It closes the gap for a future day
   where both-conflict coincides with a non-zero tail signal (e.g. 06-27 had
   `tail=0.2267`; had that day also been both-conflict, the old code would
   have diluted it to 0.057, the new code would use the full 0.2267).

## Status

- **Uncommitted**, consistent with the large amount of other uncommitted work
  already in this repo from prior sessions.
- Production impact: none observed retroactively (07-10's live number is
  unchanged), but the fix is live code, not shadow-only — it will change
  future days' `gated_downside_signal` (and therefore `adjust_golden1_weights`
  output) whenever both-conflict + nonzero-tail co-occurs.
- Not a promotion/backtest-tuning candidate — this is a bug-fix in already-live
  logic, not a new strategy or parameter sweep, so the usual
  overfitting/OOS-validation caution
  (`feedback_overfitting_fixed_window_tuning`) does not apply here.

## What's open for the future

1. **`ncf_upside_signal` has the mirror-image gap** (both-conflict → fully
   zeroed, no tail-risk fallback exists for upside at all — only downside has
   a tail component). Not investigated or fixed this session; flagged for
   whoever picks up the equivalent upside-side check.
2. Sample size for the 73%/9% conflict-rate statistics is small (11 days —
   all the dated NCF snapshots that currently exist). Worth re-checking once
   more daily snapshots accumulate to see if the both-conflict rate stays
   near what independence would predict (~0.73² ≈ 53% if the two tickers'
   conflicts were correlated that strongly, or lower if roughly independent —
   current 1/11 sample is too small to distinguish).
3. Whether the underlying AUC-vs-MAE dual-ensemble design (separate weights
   for the probability head and the return head) should itself be revisited
   is a bigger, separate question not addressed here — this session only
   fixed how the composite downside signal *responds* to that disagreement,
   not the disagreement's source.
