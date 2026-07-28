# 2026-07-26 Session Handoff Index

**Read this file first** if picking up work from today -- this was a long
session (six threads, later extended). If starting a fresh session next,
this file plus the three linked documents below are the complete record;
you should not need to re-derive anything in them.

**Bottom line: Group A+ (a2118) is unchanged and remains the sole
production strategy.** Three threads produced real code changes: Thread 4
(purely additive -- a new signal contract + snapshot store, no decision
logic touched), Thread 6 (a data-pointer bug fix + automation, in a
shadow-only advisory report that has never driven a real decision), and
Thread 5 (a new shadow-only diagnostic module, explicitly scoped down from
its original proposal, no weights touched). No gate threshold, regime
table, or trim rule was modified anywhere this session.

## How the session unfolded

1. Opened with a request to analyze `2601.04062v3.pdf` ("Smart
   Predict-then-Optimize Paradigm for Portfolio Optimization in Real
   Markets") for importable ideas -> Thread 1.
2. Thread 1's gate-robustness diagnostic led to the user asking "所以?"
   for a plain-language bottom line, then "下一步?" twice, then a direct
   question -- "optimization solve 層, 應該加?" -- that opened Thread 2 and
   grew much larger than expected once the real scope of the user's
   holdings turned out to be bigger than assumed.
3. Thread 2 ended in "算了, 還是做groupA+" (never mind, stick with
   Group A+) and an explicit request to record it in detail.
4. User then asked for a second paper (`2605.01176v4`) to be analyzed the
   same way -> Thread 3, closed quickly (no applicable mechanism at all).
5. User then proposed a concrete piece of infrastructure (a
   `TargetWeightSignal` contract + point-in-time snapshot store) and asked
   whether it was reasonable, then to build it -> Thread 4, the one thread
   that resulted in real code changes.
6. User proposed a third paper's idea (arXiv:2601.07852, utility-weighted
   decision-loss calibration) as new `direction_confidence`/
   `decision_confidence` NCF fields for A21.18 -> Thread 5. Investigating
   whether this duplicated existing work uncovered a large pre-existing
   "DFL" (decision-focused-learning) research line already live in shadow
   mode, including a real, currently-active bug (a live report serving a
   claim already disproven 10 days earlier) -> Thread 6, fixed the same
   turn per the user's "需要就重跑" (rerun if needed).
7. While fixing Thread 6, preparing to automate the fix surfaced a
   **second, larger** problem: `run_a2118()` itself had drifted since
   07-16, so a byte-identical rerun didn't reproduce the 07-16 numbers.
   Corrected that too (Thread 6, extended), then automated the whole
   sub-chain so this failure class structurally can't recur (new
   `dfl_shadow_refresh_*` pipeline steps writing to stable, non-dated
   filenames).
8. Asked "下一步?" -- offered a menu, user picked **"2+3"**: automate the
   DFL refresh (item 7 above, folded into Thread 6) **and** still build
   out Thread 5's `direction_confidence`/`decision_confidence` fields
   despite the small-sample problem, as an explicitly scoped-down Phase 1
   shadow diagnostic. Completed as Thread 5 (below) -- superseding the
   earlier "status: open, not decided" note for that thread.

## Thread 1 -- arXiv:2601.04062v3 (SPO) review + gate-robustness checklist item 7

**Full detail**: `GROUP_A_PLUS_2601_04062_SPO_PAPER_REVIEW_HANDOFF_20260726.md`,
sections "Trigger" through "Finding 3".

Paper's core mechanism (SPO+/PyEPO end-to-end differentiable training
through a portfolio optimizer) doesn't transfer -- Group A+ has no
optimization-solve decision layer, confirmed via code exploration. One
idea adopted: RobustSPO's worst-case-perturbation philosophy, adapted into
checklist item 7 of `GROUP_A_PLUS_SIGNAL_VALIDATION_CHECKLIST_20260723.md`
plus a new diagnostic script,
`scripts/evaluate/evaluate_total_risk_score_gate_robustness.py`. Swept all
four production `total_risk_score` thresholds (6/7/8/9): all show 27-51%
same-day decision-flip risk at the boundary under simulated sub-indicator
noise, but the forward-return regret proxy splits cleanly by direction --
the one bottom-detection/reversal gate (8, `trough_nowcast`) shows a real
signal even at marginal fires, while the three defensive/bearish gates
(6, 7, 9, including the one that actually trims live 00631L exposure) show
no separation between marginal and non-fires. Not acted on (samples too
small: e.g. only 17 marginal-fire days for the >=9 gate) -- logged as a
tracked pattern, not a verdict. Mid-thread, a real analysis mistake was
caught and corrected after the user asked "回測所有年份?": the initial
"10 years of history" framing was wrong because `total_risk_score`'s 14
sub-indicators were onboarded in phases (several only exist from 2025-01),
so the gate was structurally unfireable before 2025 regardless of price
history depth -- see [[feedback_check_data_coverage_before_multiyear_framing]].
A second idea (soft turnover penalty replacing the hard `max_turnover_ratio`
cap) was investigated and rejected with concrete evidence: the one real
historical trigger of that hard cap (2026-06-28) was a genuine structural
rebalance the block correctly caught.

## Thread 2 -- "optimization solve 層, 應該加?" -> groupFull -> abandoned

**Full detail**: same document,
"groupFull exploration and abandonment (same session, continued)" section.

Initial no (too few assets in Group A+'s 4-ticker universe) was correctly
challenged by the user asking "若是所有持股?" -- the user's real holdings
turned out to span 8-9 real tickers across what used to be labeled "Group
A++" and "Group B", not just Group A+'s 4. Investigation (one background
fork) found a prior, fully parameter-optimized (768 candidates) "GroupAB"
combined-governance system that was **research-only, never deployed
live**; an explicit, documented rejection of ticker 00751B
(`GROUP_A_PLUS_PLUS_00751B_CASH_20260619.md`, worse than cash on both
return and MaxDD); and a real, working, bug-fixed Group B RL policy that
simply stopped being invoked after 2026-06-28 with no documented reason
found. User then asked to build "groupAB(full)" (renamed "groupFull"
mid-request), rejected a clarifying-question round about Group B's signal
source, and said to just proceed. Built
`scripts/backtest/backtest_group_full.py` (classical Max-Sharpe over all 8
real tickers, paper's own Section 3.3.1 baseline formula) using the
updated `taiwan_stock_20260725.xlsx` holdings snapshot. Backtest: Sharpe
1.22, MaxDD -20.1% (2021-2026). Current-day recommendation showed large
deltas including 00751B independently landing at 0% (matching the 06-19
finding without being told to) -- but flagged two real caveats (a2118's
tactical signal was never actually integrated as originally described; the
knife-edge 0%/large-weight outputs are naive mean-variance's classic
estimation-error sensitivity, not executable as-is). User read the results
and said "算了, 還是做groupA+" -- script kept in the repo as a dormant,
non-production reference, not deleted. See also
[[project_groupfull_explored_and_abandoned_20260726]].

## Thread 3 -- arXiv:2605.01176v4 (SPO instability/turnover) review -- closed, no action

**Full detail**: same document as Thread 1,
"Companion paper reviewed (arXiv:2605.01176v4)" section (near the end).

Companion/self-critique paper by the same authors: KKT-based proof that
SPO-optimized decisions are a ranking over risk/cost-adjusted marginal
scores, and that SPO+ training causes "prediction inflation" (unrealistic
predicted-return magnitudes) and turnover near 85-96% regardless of risk
aversion. Proposes clipping/rescaling predictions and partial portfolio
adjustment (delta-smoothing toward target weights) as stabilizers.
**Verdict: does not transfer at all**, more cleanly than Thread 1's paper
-- the pathology this paper diagnoses (a self-inflating SPO+-trained
predictor) has no counterpart anywhere in Group A+, since nothing here is
SPO+/DFL-trained. The one superficially relevant idea (partial portfolio
adjustment) was recognized as the same category of intervention as two
things already tested and rejected on A21.19 for the identical reason
(delaying reaction to a target signal cost 2020-COVID-window protection) --
closed by citing that prior evidence rather than re-testing from scratch.
No code written for this thread.

## Thread 4 -- TargetWeightSignal contract + point-in-time snapshot store (real code change)

**Full detail**: `GROUP_A_PLUS_SIGNAL_CONTRACT_POINT_IN_TIME_STORE_20260726.md`
(separate document).

User proposed a frozen `TargetWeightSignal` dataclass and a point-in-time
snapshot archive (`results/ncf_snapshots/YYYY/MM/DD/`), framed as P0 (above
any new model) since it verifies a2118's edge holds under reproducible
conditions rather than raising Sharpe directly. Assessed as well-motivated
against four real prior incidents in this project (golden1_0531 payload
silently overwritten; a2118 promotion evidence only approximately
reconstructable; NCF ensemble weight drift from non-rolling training;
`a2118.py`'s backtest once not calling the live path's real overlay
function) -- all the same root cause: no point-in-time record of what a
signal was and what produced it. Implemented additively:
`group_a_plus/core/signal_contract.py` (`TargetWeightSignal` +
`from_daily_signal()`, a pure mapping, verified against real production
data) and `group_a_plus/core/point_in_time_store.py` (append-only,
never-overwrites JSON archive), wired into
`daily_signal.py::main()` as a `try/except`-wrapped best-effort call. 18
new tests pass; all 52 existing `daily_signal` tests still pass unchanged.
A real-data smoke test caught and fixed one real bug (`write_snapshot`
crashed on a string `root` argument). See also
[[project_signal_contract_point_in_time_store_20260726]].

**Explicitly not done in Thread 4**: `execution_plan.py` not wired in; no
automated drift-detection alert on mismatched hashes; no snapshot
retention/pruning policy; `run_a2118()` untouched; the "P0 above any new
model" priority claim itself was not independently checked against other
in-flight work.

## Thread 5 -- arXiv:2601.07852 (utility-weighted calibration) proposal -- investigated, then built as a scoped-down Phase 1 shadow diagnostic

**Full detail**: this section plus
[[project_ncf_decision_calibration_shadow_20260726]] (no separate handoff
document -- the module's own docstring is the detailed record).

User proposed `direction_confidence`/`decision_confidence` NCF fields for
A21.18, with `decision_confidence = P(overlay_utility > 0 | ...)`
calibrated per arXiv:2601.07852's utility-weighted calibration philosophy.
Read the paper in full (76 pages): it actually recalibrates a *predictive
distribution* via decision-sensitivity-weighted calibration error (a
distinct estimator, with dominance theorems under stated regularity
conditions), not literally "train P(decision profitable)" -- the user's
framing is inspired by the paper's philosophy, not its literal method, and
this gap was flagged. Checked for prior art and found
`scripts/evaluate/evaluate_a2118_decision_focused_action_shadow.py`
already implements almost exactly the user's `overlay_utility` formula
term-for-term (`utility = log(final_value) - lambda*MDD - gamma*turnover -
eta*missed_rebound`, with `missed_rebound_penalty` already present
verbatim), already trains a regret predictor per candidate action, and is
already live-wired via `build_a2118_dfl_advisory.py` -- that investigation
is what surfaced Thread 6's bug.

**Built after the "2+3" decision** (see item 8 in "How the session
unfolded" above), deliberately scoped down from the original proposal:
- `direction_confidence`: reuses the existing composite-confidence formula
  (`evaluate_a2118_composite_confidence_sweep.py`'s consensus*0.4 +
  magnitude*0.4 + spread*0.2), inlined as a small standalone function.
- `decision_confidence`: **not** a calibrated probability, despite the
  original ask. A true `P(overlay_utility > 0)` requires realized regret
  labels paired with each historical prediction, and the DFL evaluator
  computes these internally (its `labels` DataFrame, used to train the
  ridge regressors) but never exports them -- only its own predictions
  (`predicted_regret`) are in the output. Extending that evaluator to
  export realized labels was identified as the natural Phase 2 but
  deliberately not attempted (too large a change to an already-delicate,
  actively-relied-on script without dedicated review). Instead:
  `decision_confidence` is a percentile rank of `predicted_regret` against
  the DFL shadow's own historical distribution for the same action (46
  candidates as of today, pooled from `non_keep_decisions` across all 7
  windows) -- explicitly documented and tested as a rank proxy, not a
  probability.

Files: `group_a_plus/integrations/ncf_decision_calibration.py`,
`scripts/evaluate/evaluate_ncf_decision_calibration.py`,
`tests/test_ncf_decision_calibration.py` (14 tests, all passing). Verified
against real data: today's snapshot correctly returns
`decision_confidence: None` (no live DFL candidate today),
`direction_confidence: 0.69` from the real (but statically-frozen, last
row 2026-07-06) NCF reference panel.

**Status: Phase 1 complete, shadow-only, no weights touched.** Sample-size
caveat from the original investigation still applies and is restated in
the module's own docstring -- 46 points is weak evidence; treat
`decision_confidence` as rough relative signal only, not a validated
metric.

## Thread 6 -- A21.18 DFL advisory stale-input bug + code-drift + automation (real code change, found via Thread 5)

**Full detail**: `GROUP_A_PLUS_DFL_ADVISORY_STALE_INPUT_FIX_20260726.md`
(this is the most detailed single document from today -- read it in full
if touching anything DFL-related).

**Part A -- the original stale-claim bug.** While auditing the DFL line
for Thread 5, found that `report/group_a_plus/latest/a2118_dfl_advisory.json`
(regenerated daily, live-wired) was reading a frozen 2026-07-14 input file
claiming `"triple_pass_windows": 7, "all_windows_triple_pass": true` -- a
claim disproven on **2026-07-16**
(`GROUP_A_PLUS_FABLE_COMBINATION_OPPORTUNITIES_HANDOFF_20260716.md` item
#9: `covid_2020` had been silently panel-blind, defaulting every day to
KEEP; after backfilling real 2020 NCF data, `covid_2020` became the worst
window in the suite). Nobody had repointed the live pipeline at the
corrected file for 10 days.

**Part B -- a second, larger problem found while preparing to automate
the fix.** A byte-identical rerun of the main (non-selective) config
against the exact 07-16 flags did **not** reproduce the 07-16 numbers --
covid_2020 went from 4 CAP10 actions to 14, triple-pass dropped from 6/7
to **3/7**. Static NCF panel files confirmed unchanged (md5). Only
remaining explanation: `run_a2118()`, the shared simulation engine, had
itself drifted from unrelated work in the 10 days since 07-16 -- not
chased to a root cause (would need bisecting 10 days of unrelated
changes), flagged as an open question (legitimate improvement vs. a
lookahead/leakage bug). This meant today's initial p50/p70 regeneration
had been using a different code snapshot than the still-07-16-vintage main
file -- a subtler version of the same inconsistency bug. Regenerated the
main config too so all variants are from one consistent run.

**Part C -- automated so this whole failure class can't recur.** Replaced
every dated-snapshot-filename default (in `run_ncf_daily_pipeline.py`,
`build_a2118_dfl_advisory.py`, `evaluate_a2118_dfl_active_date_audit.py`)
with **stable, non-dated filenames**
(`results/a2118_decision_focused_action_shadow_dfl_main_latest.json` etc.)
that four new best-effort pipeline steps (`dfl_shadow_refresh_main/p50/p70/overlap`,
~2-3 min total) regenerate every single daily-pipeline run. No default
filename should ever need manual repointing again.

**Final, fully-consistent numbers** (main/p50/p70, all same generation
run, all 46 candidate days): main config **3/7** triple-pass (not 6/7, not
the original disproven 7/7), p50 **6/7** (covid_2020's reliability filter
correctly rejects every candidate there, unlike the main config's
misfire), p70 **5/7**. Verified by regenerating the real live advisory
end-to-end multiple times and running the full test suite after each
change (`pytest tests/ -k "dfl or daily_pipeline"`: 43/43 passing in the
final state; several tests' hardcoded filename/step-order assertions
updated across the three rounds of fixes, since they had been asserting
the bug/intermediate states as correct behavior). See also
[[project_dfl_advisory_stale_input_fix_20260726]].

**No trading impact from the bug or either fix round**: the advisory has
`advisory_active: false` throughout (never matched a real decision date),
so this was entirely a live-serving correctness/reporting problem, never a
position-sizing one.

## Files changed today (complete list, final state)

- `GROUP_A_PLUS_SIGNAL_VALIDATION_CHECKLIST_20260723.md` -- item 7 added
  (Thread 1).
- `scripts/evaluate/evaluate_total_risk_score_gate_robustness.py` -- new,
  read-only diagnostic (Thread 1).
- `scripts/backtest/backtest_group_full.py` -- new, read-only research
  script, abandoned but kept as reference (Thread 2).
- `group_a_plus/core/__init__.py`, `group_a_plus/core/signal_contract.py`,
  `group_a_plus/core/point_in_time_store.py` -- new (Thread 4).
- `group_a_plus/operations/daily_signal.py` -- two new imports plus one
  `try/except`-wrapped call inside `main()`; `build_daily_signal()` itself
  unchanged (Thread 4).
- `tests/test_signal_contract.py`, `tests/test_point_in_time_store.py` --
  new, 18 tests total (Thread 4).
- `group_a_plus/integrations/ncf_decision_calibration.py`,
  `scripts/evaluate/evaluate_ncf_decision_calibration.py` -- new (Thread 5).
- `tests/test_ncf_decision_calibration.py` -- new, 14 tests (Thread 5).
- `scripts/run/run_ncf_daily_pipeline.py` -- four new best-effort
  `dfl_shadow_refresh_*` steps added; `dfl_advisory_input`/
  `dfl_selective_p50_input`/`dfl_selective_p70_input`/`dfl_shadow_result`/
  `dfl_overlap_result` repointed to stable filenames (Thread 6, final
  state -- went through two intermediate dated-filename states first, see
  the fix document for the full history).
- `scripts/run/build_a2118_dfl_advisory.py`,
  `scripts/evaluate/evaluate_a2118_dfl_active_date_audit.py` -- matching
  stable-filename defaults (Thread 6).
- `tests/test_run_ncf_daily_pipeline.py` -- step-order and filename
  assertions updated across three rounds of fixes (Thread 6).
- `results/a2118_decision_focused_action_shadow_dfl_main_latest.json`,
  `..._dfl_selective_p50_latest.json`, `..._dfl_selective_p70_latest.json`,
  `results/a2118_decision_focused_action_overlap_dfl_latest.json` -- new
  stable research artifacts, regenerated every pipeline run going forward
  (Thread 6). Superseded intermediate dated files
  (`..._pit2020_20260716.json`, `..._pit2020_20260726.json`, etc.) left in
  place as historical record, no longer referenced as defaults anywhere.
- `report/group_a_plus/latest/a2118_dfl_advisory.json` -- regenerated with
  corrected, consistent inputs (Thread 6); still `advisory_active: false`.
- `GROUP_A_PLUS_2601_04062_SPO_PAPER_REVIEW_HANDOFF_20260726.md`,
  `GROUP_A_PLUS_SIGNAL_CONTRACT_POINT_IN_TIME_STORE_20260726.md`,
  `GROUP_A_PLUS_DFL_ADVISORY_STALE_INPUT_FIX_20260726.md`, this index --
  handoff documents.

**No production decision logic changed anywhere.** Every gate threshold,
regime table, and trim rule discussed across all six threads is
byte-identical to before this session started. Threads 4, 5, and 6 are all
additive/shadow/data-integrity changes, not decision-logic changes.

## Memory index (all entries from today, newest first in MEMORY.md)

[[project_ncf_decision_calibration_shadow_20260726]],
[[project_dfl_advisory_stale_input_fix_20260726]],
[[project_spo_companion_paper_2605_01176_closed_20260726]],
[[reference_spo_paper_handoff_20260726]] (secondary index, points back
here), [[feedback_check_data_coverage_before_multiyear_framing]],
[[project_signal_contract_point_in_time_store_20260726]],
[[project_groupfull_explored_and_abandoned_20260726]],
[[feedback_avoid_askuserquestion_for_short_replies]] (updated, not new --
2026-07-26 addendum about not blocking on AskUserQuestion once a build
instruction has been given).

## Thread 7 (added after a /clear, same day) -- orphaned h20 calibration scripts + panel-drift governance deadlock

**Full detail**: `GROUP_A_PLUS_H20_CALIBRATION_PANEL_DRIFT_GATE_DEADLOCK_HANDOFF_20260726.md`
(exact numbers, reproduction commands, raw-market-data verification); see
also [[project_h20_calibration_drift_gate_deadlock_20260726]].

Follow-up request ("分析未完成的交接任務") surfaced two scripts written earlier the
same day (`evaluate_ncf_h20_utility_weighted_calibration.py`,
`evaluate_ncf_h20_walkforward_bias_correction.py`) that were never folded into
this index and never had their output recorded anywhere. The second one had
never successfully run at all -- missing `sys.path.insert(PROJECT_ROOT)`,
`ModuleNotFoundError` on its first import. Fixed and ran both:

1. **h20_prob_up miscalibration confirmed**: bias -0.33 near the 0.5 decision
   threshold (vs -0.08 far from it), -0.38 in the "near-threshold + high-vol"
   decisive cell (vs -0.17 elsewhere) -- confirms arXiv:2601.07852's core claim
   that global calibration can look fine while error concentrates where
   decisions actually get made.
2. **Walk-forward bias correction has a real but mixed effect** on
   late-bull-hedge: Sharpe 2.10->2.03, Sortino 2.20->2.12 (worse), annual
   return 0.524->0.552 (better), AUC 0.65->0.61 (worse), trigger count 3->2
   with an entirely different set of trigger dates. Not adopted -- mechanism
   verification only.
3. **Surfaced a real contradiction**: [[project_a2118_ncf_hedge_dormancy_root_cause_20260723]]
   byte-identically verified 0 late-bull-hedge triggers using panel `20260722`;
   today's backtest against panel `20260725` shows 3 triggers
   (2025-09-30, 2026-01-29, 2026-02-23). Both are correct for their own
   panel snapshot -- the panel itself drifted across `h20_prob_up`.
4. **Root cause traced through a pre-existing (not built this session)
   panel-drift governance chain** that had already caught this but was never
   written up: `ncf_panel_drift_diagnosis_20260725.json` ->
   `ncf_panel_drift_remediation_plan_20260725.json` ->
   `ncf_panel_drift_model_set_isolation_report_20260725.json` +
   `ncf_panel_external_feature_sensitivity_governance_20260725.json` ->
   `report/group_a_plus/latest/external_sensitivity_observation_log.json`.
   Two separate drift sources: (a) TabNet removed from the ensemble between
   the 07-16 baseline and current panel -- isolated, and back within limits
   once compared same-method (no-TabNet vs no-TabNet); (b) external-feature
   sensitivity -- h20_prob_up/confidence deltas up to 0.51/0.64 (limits
   0.15/0.28) when comparing with-external-features vs without, currently
   the live blocker (`blocked_observation_required`).
5. **The "3 stable observation sessions" gate is structurally deadlocked**:
   `evaluate_ncf_panel_drift.py` computes `max_abs_delta` over the *entire*
   historical overlap (2025-01-02 onward), no trailing window. The 07-22 and
   07-25 observation log entries have byte-identical `max_abs_delta` /
   `max_abs_delta_date` (pinned to 2025-03-05 and 2025-04-02) -- since
   historical rows never change, no future daily observation can ever
   supersede those two fixed dates. `stable_observation_count` is
   structurally locked at 0 regardless of how many more sessions run, unless
   the methodology changes (e.g., trailing window) or the underlying dates
   are specifically addressed.
6. **Root-caused the two anchor dates directly against `external_market_ohlcv`**:
   neither is a data bug. 2025-03-05 sits inside a real VIX spike (18->24,
   US equity selloff); 2025-04-02 is the "Liberation Day" tariff announcement
   date, immediately preceding VIX's 21->60 spike over the following week. In
   both cases the with-external-features model correctly turned cautious
   (low confidence / bearish h20) while the no-external-features model
   stayed confidently bullish, blind to the macro deterioration. **The gate
   is currently blocked by evidence that argues external features are
   working correctly during crises, not evidence of harmful instability** --
   the governance methodology (raw delta magnitude, full-history window)
   can't tell the two apart. This is a methodology blind spot, not a model
   defect.

**No trading impact**: every report in the chain carries
`active_allocation_impact: none` and `keep_golden1_0531_unchanged: true` --
this only blocks promotion/training, never touched live allocation.

**Status: root-caused, and the two governance-methodology fixes it implied
were both built and verified against real data** (not wired into
production). `scripts/evaluate/evaluate_ncf_panel_drift.py` gained two
independent, additive, opt-in capabilities: `--window-start` (trailing
window instead of a full-history max that can never be superseded -- fixes
the C4 structural deadlock) and `--outcome-aware` (excludes dates where the
audited/candidate panel was demonstrably closer to the realized label than
the baseline, so a large delta that turned out to be the *better* call
isn't penalized the same as one that was wrong -- fixes the Part D blind
spot). Real-data verification: with `--outcome-aware`, 216/357 resolved
days (60.5%) show the with-external-features panel was closer to truth;
2025-04-02 (the tariff-crash date pinning the whole gate) is one of them
and is correctly excluded, moving the risk-relevant worst case to
2026-07-17 -- a still-unresolved live prediction, not a proven bad call.
16/16 related tests passing (12 pre-existing + 4 new). Neither flag was
wired into `build_group_a_plus_external_sensitivity_observation_log.py`,
`build_ncf_panel_external_feature_sensitivity_governance.py`, or the daily
pipeline -- that production-default decision (window length, whether to
apply retroactively, whether to combine both flags) is left to the user.
The last open item (`ensemble_prob_up`'s 2025-01-15 residual, the one
anchor date outcome-awareness did *not* excuse) was also root-caused:
`institutional_data` shows five real consecutive days of net institutional
selling into 2025-01-14 (peaking -15.2M total on 01-13), which the model
correctly registered as bearish on 2025-01-15 -- the market rallied instead
(`actual_up_h20=1.0`). **A genuine false positive from the same mechanism
that succeeded on the other two anchor dates, not a bug.** All four anchor
dates this investigation touched (2025-03-05, 2025-04-02, 2025-01-15,
2026-07-17) are now individually confirmed against raw market/flow data;
none are data bugs. **This thread is fully closed.**

Full detail: `GROUP_A_PLUS_H20_CALIBRATION_PANEL_DRIFT_GATE_DEADLOCK_HANDOFF_20260726.md`
Parts E, F, and G.

**Extended same session (Parts H1-H6, same document)**: user proposed a new
00631L<->0050 relative-rotation module (arXiv:2607.06117-inspired); found
it substantially duplicates the existing DFL shadow line
(`evaluate_a2118_decision_focused_action_shadow.py`), root-caused why that
line's `REENTER` action structurally never fires, built and iterated a
VIX-based "relief gate" fix (three composable additions: `--relief-gate`,
`--relief-min-holding-days`, `--relief-min-gap`), then built a genuine 2021
NCF backfill for an out-of-sample check that showed the whole relief-gate
direction does **not** clearly generalize (plain CAP10 alone beat every
relief-gate variant on the fresh year) -- concluded to stop iterating on
it. See that document's Parts H1-H6.

**Continued into 2026-07-27, new document**: user proposed a further
`trough_reentry_nowcast.py` module (arXiv:2509.05922-inspired); found it
also substantially duplicates an existing, already-live-wired module
(`group_a_plus/integrations/trough_nowcast.py`, wired into
`execution_plan.py`); built two more real backfills (2023, 2024) to reach
a 9-window (2017-2026) sample; found and worked around a second
panel-mismatch bug (in `evaluate_group_a_plus_trough_nowcast_shadow.py`'s
`DEFAULT_WINDOWS`, same class as the 07-16 DFL-advisory bug); went through
three rounds of self-correction on the economic value question before
landing on a clean final number (+1,527.6 TWD net over 9 years across 7
genuinely-eligible events -- negligible). Full detail:
`GROUP_A_PLUS_TROUGH_REENTRY_2509_05922_REVIEW_AND_SAMPLE_EXPANSION_20260727.md`.

**Fourth and last paper-review thread, same 07-27 continuation**: user
proposed a `conformal_tail_warning.py` module (arXiv:2606.18199-inspired);
found it substantially duplicates `group_a_plus/integrations/tail_conformal.py`,
which is **already a blocking pre-trade guard** in `execution_guard.py`
(not diagnostic-only). Unlike the three threads above, this one found a
real, quantified gap in the existing module (2020 replay: 15% empirical
lower-tail exceedance vs 10% nominal, 26.8% in the "elevated" risk
bucket specifically) and built a genuine fix: single-rate ACI (Gibbs &
Candès 2021) as an additive, opt-in enhancement, tuned across 4 rounds on
2020 then validated clean on a held-out 2018 window (real, consistent,
if modest, improvement on both tested horizons). When asked "導入?"
(adopt into production?), a full corrected 2017-2026 replay (after first
catching and discarding a methodology bug in a faster reimplementation)
confirmed the calibration improvement but surfaced a much more urgent
issue: switching to adaptive would push blocking frequency to 58% of
2020 and 100% of 2022 (vs static's 4.5%/82.5%), and separately the
*existing, currently-live* static method already blocks 100% of 2023 in
this replay -- recommendation was explicitly **not** to adopt yet, and to
first verify the static method's own extreme block rates against real
historical `execution_guard.py` decisions (flagged as the single most
urgent open item from today, ranked above the ACI question itself). Not
wired into production. Full detail:
`GROUP_A_PLUS_TAIL_CONFORMAL_ACI_20260727.md`.

## If starting a fresh session next

**Most urgent open item, ranked above everything else below**: the
tail-conformal thread's Part 4 found that replaying
`compute_tail_conformal_diagnostic()` (the *existing, currently-live*
static calibration, no proposed change involved) across 2022 and 2023
gives block rates of 82.5% and 100% respectively -- i.e., in this replay,
new `00631L.TW` exposure would have been blocked essentially the entire
year in 2023. This needs independent verification against real historical
`execution_guard.py` decisions/logs before anything else in that thread
(or arguably before trusting this guard generally) -- not done this
session. See `GROUP_A_PLUS_TAIL_CONFORMAL_ACI_20260727.md` Part 4b.

Every other thread above (including the H1-H6 relief-gate extension and
the 07-27 trough-reentry continuation) reached a closed verdict, a
verified-and-tested code change, or an explicit "deferred, needs dedicated
review" note. Three small, lower-priority, NOT-yet-fixed items surfaced
along the way: (1) `evaluate_group_a_plus_trough_nowcast_shadow.py`'s
`DEFAULT_WINDOWS` uses the wrong panel for `covid_2020`/`inflation_2022`
(worked around via explicit `--windows`, not fixed at the source); (2) the
same file's `simulate_staging_policy()` only re-evaluates `buy_fraction` on
regime-change days, understating `trough_nowcast`'s true value in that
evaluator's counterfactual (production's `execution_plan.py` does not have
this limitation); (3) the tail-conformal ACI enhancement itself is built,
tested, and calibration-OOS-validated but explicitly not recommended for
adoption pending the urgent item above plus a portfolio-level economic
backtest of the blocking decisions. None of these three affect any live
decision as of today. The one open, unresolved technical question from
earlier today is Thread 6 Part B (why did `run_a2118()`'s historical
backtest output change between 07-16 and 07-26?) -- not chased to a root
cause; if picked up, expect to bisect roughly 10 days of unrelated
commits/changes to find it.
