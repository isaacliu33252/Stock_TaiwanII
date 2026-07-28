# 2026-07-25 Session Handoff Index

**Read this file first** if picking up work from today. It indexes five
separate threads across three existing handoff documents plus two new
documents, in the order they happened, with pointers to the detailed
section in each. Each underlying document already has its own detailed
addenda; this file exists because today's work sprawled across multiple
documents and none of them alone tells the whole story.

**Updated later the same day**: Thread 1 (A21.19) grew substantially past
its original addendum #12 stopping point -- addenda #13-15 tested and
diagnosed a new interaction-term component in detail (see Thread 1's
update below). Thread 5 is entirely new, added after the rest of this
index was first written.

## How the session unfolded

1. Opened mid-conversation with "之前有當未完成，要繼續" (prior work left
   unfinished, continue it) and no other context. Asked the user which
   thread via `AskUserQuestion`; they picked **A21.19's next step**.
2. Spent the first half of the session on A21.19 (Thread 1 below):
   tested and rejected two turnover-reduction ideas, reviewed a new paper
   (Thread 2), built and tested two new signal components from it, then
   discovered and chased down a significant methodological bug that
   forced re-evaluating everything (Thread 1 continued).
3. User then explicitly asked to "換方向, 再試試" (switch direction, try
   something else) and, when offered choices, said "全部都試...要找到好
   的方向" (try them all, find a good one) -- Threads 3 and 4 below are
   the result: two independent, unrelated historical-evidence audits,
   both of which turned up real, previously-undetected problems.
4. User then pushed back on Thread 2's "no direct import" framing with
   three specific mechanisms from the paper that might still transfer.
   Testing the first (a VIX-credit confirmation gate) reopened Thread 1
   with three more addenda (#13-15); the third (correlation
   de-duplication) became the new Thread 5. The second (fixed signal
   universe + walk-forward-only-reweights-lambdas) was discussed but not
   implemented today.

## Thread 1 -- A21.19 continuous defensive-tilt shadow candidate

**Full detail**: `GROUP_A_PLUS_A2119_CONTINUOUS_DEFENSIVE_TILT_SHADOW_HANDOFF_20260724.md`,
addenda #5 through #15 (its own top section has a self-contained "2026-07-25
session summary" -- read that first if you only read one section from this
thread).

Summary of the arc: tested a wider no-trade band (rejected, addendum #5,
also found and fixed a floating-point boundary bug in two files) and a
lower tilt-update frequency (rejected, addendum #6) -- both were addendum
#4's leftover open questions about A21.19's turnover/cost drag. Then built
and tested two new tilt components from Thread 2's paper: `growth_crowding`
(addendum #7, cleanly rejected -- real IC but a net-negative backtest in
every window) and `credit_stress` from HYG-SHY data (addendum #8, at first
looking like the strongest evidence this candidate had ever produced).
Completing `credit_stress`'s full validation checklist (addendum #9)
surfaced a real methodological limitation: this script's z-scored
components degenerate to zero on any sub-60-trading-day window. Fixing
that properly (a new `warmup_days` parameter, addendum #10) revealed the
limitation wasn't specific to `credit_stress` or even to short windows --
**every fixed-window `vix_only` number reported for this candidate since
addendum #2 has an implicit cold-start bias**, because the z-score
restandardizes from a blank slate at each window's own start rather than
using real trailing history. Re-testing the foundational regime-floor
claim under the corrected methodology (addendum #11) was reassuring -- it
survives independently, fold-for-fold identical to the original finding.
Re-testing `credit_stress`'s full checklist under the same correction
(addendum #12) was not reassuring -- its case weakens further and lands on
a specific, concerning pattern: it helps in calm periods and hurts in both
real crisis episodes actually tested (2018, 2020).

**Update (addenda #13-15)**: user pushed back on Thread 2's "no direct
import" framing and asked to test RGRR's actual interaction-term
mechanism (a product of oriented signals) rather than the additive blend
`credit_stress` used. Built `vix_credit_confirm` (a VIX-credit
confirmation gate) -- initial results looked like this candidate's best
lead yet (addendum #13-14: 4-7 of 8 windows/folds improved, including the
2020 COVID crisis that `credit_stress` had failed). Diagnosing the one
weak point (2017/2018) at the user's request (addendum #15) instead
uncovered that the 2020 "win" was itself an artifact of the same
`_zscore` rolling-baseline-adapts-to-sustained-stress bug -- fixing the
bug properly (clip the z-score at 0, since "not confirmed" should mean
zero contribution, not a negative one) made the 2020 improvement vanish
entirely (byte-identical to `vix_only`), leaving only a small, genuinely
clean gain in 2019. **Net effect: another humbling self-correction, not
a promotion lead** -- `w7_vix_credit_gate`/`w8_vix_credit_gate_v2` both
stay at 0.0.

**Final state**: A21.19 remains **do not promote**. Its default
configuration is unchanged (VIX-only, regime floor on, `no_trade_band=
0.005`, `tilt_update_freq_days=1`, `w6_credit=0.0`, `w7_vix_credit_gate=
0.0`, `w8_vix_credit_gate_v2=0.0`, `warmup_days=0`). Two real bugs fixed
(floating-point boundary in `_apply_no_trade_band`, Python late-binding-
default in `evaluate()`'s missing `weights` parameter). One significant,
retroactive methodological finding (the `warmup_days` cold-start bias)
that applies to this candidate's entire history, not just today's new
components -- **anyone doing further serious evaluation of this
candidate should use `warmup_days=756`, not the historical default of
0** -- and, per addendum #15, should be skeptical of any headline
improvement in a fast-moving crisis window (2020) until checked for the
same rolling-baseline erosion artifact, not just windows that look weak.

## Thread 2 -- arXiv:2607.06117v1 paper review ("Relief-Gated Relative Rotation for QQQ-DIA Allocation")

**Full detail**: `docs/2607_06117_RGRR_QQQ_DIA_GROUPA_PLUS_REVIEW_20260725.md`.

Same author/methodology lineage as the paper A21.19 itself originated
from. No direct strategy import (same asset-universe mismatch as every
non-RL paper reviewed this project). Three real takeaways, all acted on
(a third was added later the same day -- see Thread 5): (1) its
incremental-OOS-admission discipline for higher-order interaction
terms was formalized as **item 6** in
`GROUP_A_PLUS_SIGNAL_VALIDATION_CHECKLIST_20260723.md` (a standing
process document -- affects how future shadow candidates should be
evaluated, not just A21.19); (2) its HYG-SHY credit-relief construction
directly fed Thread 1's `credit_stress` work.

## Thread 3 -- reconstructing a2118's original promotion evidence

**Full detail**: `GROUP_A_PLUS_FABLE_10_DIRECTIONS_AUDIT_HANDOFF_20260723.md`,
the "2026-07-25 addendum: closed" note under Finding 3.

Closed the one item flagged as unresolved in that document since 07-23:
the exact panel/threshold behind a2118's original a2111-promotion
evidence (`strategy.json`'s `sharpe_delta: 0.029`, `trigger_count_short:
3`, `trigger_accuracy: "3/3 (100%)"`) had never been located. It turned
out to still be on disk (`results/ncf_00631l_panel_2025_v4_tail.csv` +
`h20_max=0.45`, both named in `GROUP_A_PLUS_A2118_HANDOFF_20260628.md`).
Re-running `run_a2118()` with this exact configuration reproduces
`trigger_count_short=3` exactly (2025-10-30, 2026-02-23, 2026-05-04) --
almost certainly the real original configuration. **The finding**:
2026-05-04 is independently listed as a false trigger in that same 06-28
source document's own historical table (00631L +21.9% over the next 20
trading days). **The recorded `trigger_accuracy: "3/3 (100%)"` is
inconsistent with its own cited source material.** Updated
`report/group_a_plus/latest/strategy.json` (the one production file
touched today) with a `trigger_accuracy_status` annotation and a new
`original_promotion_evidence_reconstruction_20260725` block, following
the same pattern as the existing `sharpe_delta_status` annotation.
Verified: valid JSON, `tests/test_group_a_plus_latest_strategy.py` 25/25
pass. Does not change a2118's active status or the standing "do not cite
this evidence" guidance (already in place since 07-23) -- adds audit
detail to why.

## Thread 4 -- golden1_0531 release payload silently overwritten

**Full detail**: `GROUP_A_GOLDEN1_0531_STALENESS_AND_PREDICTION_HANDOFF_20260723.md`,
Finding C's "2026-07-25 addendum" and the updated "Open follow-ups"
section.

Chased a second item flagged as "not chased further" on 07-23: the
release manifest `results/group_a_release_Golden1_0531.json` names one
model checkpoint, but the backtest payload it references internally
records a different model name. File-mtime archaeology
(`ls -la --time-style=full-iso`) shows the payload file's *actual*
content on disk was last modified 2026-06-09 21:49:06 -- nine minutes
after the *other* model (the one its internal `model_name` field names)
was created, and note the release manifest itself is dated five days
after the *original* model/payload pair, self-consistent at the time.
**Finding**: this isn't a labeling typo -- the payload file was almost
certainly silently overwritten in place by a later pipeline run (its
output filename is deterministic from date-range arguments, so a rerun
with matching arguments overwrites it) using a different, newer model,
without renaming the file or updating the manifest that still references
it by name. The original 05-31 release-time evidence is presumably not
recoverable from this file. This compounds the document's existing
Finding C (the "frozen until 2026-08-31" trial was superseded 12 days in)
with an independent second problem: even the frozen release's own
supporting evidence didn't stay frozen. No code fix applied -- this is a
process/provenance finding (deterministic, unversioned output filenames),
flagged for whoever next touches Group A's release conventions. Also
fixed the document's stale "Open follow-ups" list, which still said the
`_latest_prices()` empty-holdings crash (Finding A) was unfixed when it
had already been fixed 2026-07-24 -- just a documentation sync issue, no
code change needed there.

## Thread 5 -- NCF feature-selection correlation de-duplication

**Full detail**: `GROUP_A_PLUS_NCF_CORRELATION_DEDUP_HANDOFF_20260725.md`.

The third of the three mechanisms the user pushed back with re: Thread
2's "no direct import" framing. Confirmed Group A+'s NCF feature pipeline
has no correlation-based redundancy screen (RGRR's own 0.95-threshold
de-dup step has no equivalent here). Found the layer that actually
matters for production (`identify_stable_features`, which runs
unconditionally for the H=20 horizon, unlike `_feature_selection`/
`apply_feature_selection` which are gated behind a flag the daily
pipeline never sets). Added `_deduplicate_correlated_features` and a new
opt-in `dedupe_correlated` parameter (default `False`, no existing
behavior changed). Verified on real 00631L data (not synthetic): finds
and drops a genuinely redundant pair, `close_ma200_ratio`/
`close_ma200_dist`, correlation exactly 1.000. 5 new regression tests,
13/13 total pass in `tests/test_ncf_00631l_paths.py`. Full ensemble AUC
impact not measured (would need the expensive full `train_classifier`
run) -- flagged as the next step if this is pursued toward a default flip.

## Complete file list, all five threads

**Production files modified (one, deliberately minimal)**:
- `report/group_a_plus/latest/strategy.json` (Thread 3 only)

**Data backfilled (not a code change)**:
- `HYG`/`SHY` daily closes in `external_market_ohlcv`, 2015-01-02..2026-07-24
  (Thread 1/2, via `scripts/fetch/fetch_cross_market_ohlcv.py --tickers HYG,SHY`)

**Scripts modified**:
- `scripts/evaluate/evaluate_a2119_continuous_defensive_tilt_shadow.py`
  (extensive -- see Thread 1's own document for the itemized diff list
  across addenda #5-#15, including the `warmup_days` parameter and the
  `vix_credit_confirm`/`vix_credit_confirm_v2` components)
- `scripts/evaluate/evaluate_a2118_live_overlay_backtest_gap.py`
  (one fix: the same floating-point boundary bug as above, in its own
  independent copy of `_apply_no_trade_band`)
- `scripts/misc/ncf_00631l.py` (Thread 5: `_deduplicate_correlated_features`
  new function; `identify_stable_features` gains `dedupe_correlated`/
  `corr_threshold` params, default off)

**Tests modified**:
- `tests/test_ncf_00631l_paths.py` (Thread 5: 5 new tests)

**Standing process documents modified**:
- `GROUP_A_PLUS_SIGNAL_VALIDATION_CHECKLIST_20260723.md` (new item 6)

**Handoff documents modified** (addenda appended, existing content
otherwise untouched):
- `GROUP_A_PLUS_A2119_CONTINUOUS_DEFENSIVE_TILT_SHADOW_HANDOFF_20260724.md`
- `GROUP_A_PLUS_FABLE_10_DIRECTIONS_AUDIT_HANDOFF_20260723.md`
- `GROUP_A_GOLDEN1_0531_STALENESS_AND_PREDICTION_HANDOFF_20260723.md`
- `docs/2607_06117_RGRR_QQQ_DIA_GROUPA_PLUS_REVIEW_20260725.md` (Verdict
  section updated for Thread 5 and the addendum #13-15 update)

**New documents**:
- `docs/2607_06117_RGRR_QQQ_DIA_GROUPA_PLUS_REVIEW_20260725.md`
- `GROUP_A_PLUS_NCF_CORRELATION_DEDUP_HANDOFF_20260725.md`
- This file.

**New result JSON files** (all in `results/`, all research-only):
`a2119_no_trade_band_sweep_20260725.json`,
`a2119_tilt_update_freq_sweep_20260725.json`,
`a2119_growth_crowding_penalty_sweep_20260725.json`,
`a2119_credit_stress_hyg_shy_sweep_20260725.json`,
`a2119_credit_stress_walkforward_expanding_rolling_20260725.json`,
`a2119_credit_stress_crisis_independence_20260725.json`,
`a2119_credit_stress_cost_sensitivity_20260725.json`,
`a2119_credit_stress_warmup_extension_2020_20260725.json`,
`a2119_credit_stress_warmup_main_windows_20260725.json`,
`a2119_vix_only_baseline_warmup_recheck_20260725.json`,
`a2119_credit_stress_warmup756_full_checklist_20260725.json`,
`a2118_original_promotion_evidence_reconstruction_20260725.json`,
`a2119_vix_credit_confirmation_gate_20260725.json`,
`a2119_vix_credit_gate_warmup756_full_checklist_20260725.json`,
`a2119_vix_credit_gate_v2_fix_20260725.json`.
(Thread 5's correlation-dedup check was ad hoc `python3 -c`, not saved to
a result file -- reproducible from the command in its own handoff doc.)

## What's still open, across all five threads

1. **A21.19**: the 2019-2023 structural conservatism drag (a real design
   cost of the regime floor, not a bug) and a natively lower-frequency
   signal construction both remain open, unchanged from before today. Any
   future evaluation of this candidate should default to `warmup_days=
   756`, and should be skeptical of headline wins in fast-moving windows
   until checked for the same rolling-baseline-erosion artifact addendum
   #15 found (a win there isn't automatically more trustworthy than a
   loss elsewhere).
2. **RGRR review**: nothing further -- fully closed out today (all three
   mechanisms the user proposed were tested or implemented).
3. **a2118 promotion evidence**: the metric-magnitude discrepancy
   (reconstruction gives 3-4x the recorded Sharpe/Sortino/return deltas,
   same direction) was not chased to full resolution -- the comparison
   baseline used for the original figures wasn't fully identified.
   Secondary to the accuracy-claim contradiction, which is resolved.
4. **golden1_0531**: no fix applied to the underlying process gap
   (deterministic unversioned output filenames) -- flagged, not
   implemented. Items 1 and 4 in that document's "Open follow-ups" list
   (Group A's post-06-12 config status; the governance question of
   whether the frozen-trial framing still means anything) remain open,
   unchanged from 07-23, and are explicitly Group A (not Group A+)
   governance questions outside this session's scope.
5. **NCF correlation de-dup**: full ensemble AUC impact (`train_classifier`
   with vs. without `dedupe_correlated`) not measured -- needed before
   considering a default flip or wiring into `run_ncf_daily_pipeline.py`.

## Memory saved today (Claude's persistent memory, not part of the repo)

In roughly chronological order: `project_a2119_no_trade_band_sweep_fp_bug_20260725`,
`project_a2119_tilt_update_freq_sweep_20260725`,
`project_a2119_growth_crowding_penalty_tested_20260725`,
`project_rgrr_qqq_dia_paper_review_20260725`,
`project_a2119_credit_stress_hyg_shy_20260725`,
`project_a2119_credit_stress_full_checklist_20260725`,
`project_a2119_warmup_bias_discovery_20260725`,
`project_a2119_regime_floor_survives_warmup_recheck_20260725`,
`project_a2119_credit_stress_final_verdict_20260725`,
`project_a2118_original_promotion_evidence_reconstructed_20260725`,
`project_golden1_0531_payload_overwrite_discovery_20260725`,
`reference_20260725_session_handoff_index`,
`project_a2119_vix_credit_gate_promising_20260725`,
`project_a2119_vix_credit_gate_full_checklist_20260725`,
`project_a2119_gate_v2_fix_reveals_2020_win_was_bug_20260725`,
`project_ncf_correlation_dedup_added_20260725`.
