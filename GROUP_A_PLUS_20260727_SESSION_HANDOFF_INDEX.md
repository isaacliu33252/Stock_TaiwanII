# 2026-07-27 Session Handoff Index

**Read this file first** if picking up work from today. Six threads, four
fully-documented in their own files (linked below), one resolved as an
addendum to yesterday's tail_conformal document, one (the SPO/DFL
re-proposal) closed without new code because it turned out to already
exist.

**Bottom line: Group A+ (a2118)'s decision logic -- gate thresholds,
regime table, trim rules, NCF panel pin -- is unchanged and it remains the
sole production strategy.** The one real production-*infrastructure* fix
this session was Thread 5: a previously-unwired dependency gap in the
daily automation pipeline that had been silently relying on manual
intervention and, on this occasion, crashed the entire pipeline run
(including that day's `daily_signal`/`execution_plan`/`alert_state`
regeneration) -- fixed, tested, and verified against a real end-to-end run
that produced today's (2026-07-27) live signal. Thread 3 also produced
real code (a new, additive, opt-in-only diagnostic module two layers
removed from any live decision) -- fully tested, nothing wired into
`daily_signal.py`/`execution_plan.py`. No gate threshold, regime table,
trim rule, or NCF panel pin was modified anywhere today; the only other
production-adjacent artifact touched was a decision *not* to refresh the
pinned NCF panel, after testing showed doing so was unsafe (Thread 4).

## How the session unfolded

1. Continuing from yesterday's (2026-07-26) `GROUP_A_PLUS_H20_CALIBRATION_PANEL_DRIFT_GATE_DEADLOCK_HANDOFF_20260726.md`
   Part H (relief-gate OOS rejection), the session opened this morning
   with two more paper-review threads before this document's coverage
   starts: the trough re-entry proposal (arXiv:2509.05922) and the
   tail-conformal ACI enhancement (arXiv:2606.18199) -- both fully
   documented in their own files (see Threads 1-2 below), reaching "don't
   pursue further" and "built but not adopted yet" respectively.
2. User then re-proposed a discrete-action/utility-lower-bound mechanism
   citing arXiv:2601.04062 + 2605.01176 (the same SPO papers reviewed
   2026-07-13/14 and again 2026-07-26) -- investigating its lineage found
   it is not a new idea at all: it is
   `scripts/evaluate/evaluate_a2118_decision_focused_action_shadow.py`,
   built 2026-07-13/14, whose REENTER-fix branch was OOS-rejected just
   the day before (2026-07-26 Part H). Not reopened -> Thread 3's opening.
3. Asked "下一步?" repeatedly; recommended (and the user picked) the one
   genuinely still-open item from 2026-07-26: Thread 5 of that session
   (`decision_confidence` needing a real, not rank-proxy, probability
   calibration) -> became Thread 3, the session's main implementation
   work.
4. Asked "下一步?" again; user chose both surfaced options at once
   ("1+2"): an ops-health check on the daily automation pipeline, and
   extending Thread 3 with regime-conditioned calibration -> Threads 4
   and 3-continued, run in that order.
5. Thread 4's ops-health check surfaced an active `ncf_panel_stale`
   alert; investigating it further (still "1+2" -- check why, then
   refresh) led to attempting the routine panel-pin update the project's
   own established procedure calls for, which uncovered real panel drift
   and was **not executed**.
6. Asked "下一步?" a final time; user asked to diagnose Thread 4's
   panel-drift finding using the project's existing drift-audit tool ->
   confirmed with `--outcome-aware` data that the drift is retraining
   noise, not real signal.
7. Asked for a detailed written record -> this index plus the two new
   documents below (at that point, covering Threads 1-4).
8. Asked to manually download today's data ("下載今天的資料") and start
   NCF training ("開始訓練") ahead of the nightly schedule -> the fetch
   step succeeded, but the training run crashed at step 13/72 -> Thread 5.
9. Presented two options (fix the root cause vs. skip past the broken
   step); user chose to fix the root cause -> Thread 5's fix, verified
   against a real pipeline run for today's date stamp.
10. Asked for a detailed written record of Thread 5 -> this index updated
    plus a new document below.

## Threads

### Thread 1: Trough re-entry proposal (arXiv:2509.05922)

**Fully analyzed, not promoted.** Three new NCF backfills (2021, 2023,
2024) built; production re-entry mechanism confirmed to already work
correctly but with negligible economic value (+1,527.6 TWD net over 9
years). Full detail:
`GROUP_A_PLUS_TROUGH_REENTRY_2509_05922_REVIEW_AND_SAMPLE_EXPANSION_20260727.md`.
Memory: `project_trough_reentry_2509_05922_review_20260727`.

### Thread 2: Tail-conformal ACI enhancement (arXiv:2606.18199)

**Built, tested, calibration-quality OOS-validated; NOT adopted (Part
4); the "most urgent open follow-up" from Part 4 was resolved this
session (Part 5, added today) and turned out to be a false alarm** -- the
82.5%/100% "block rate" numbers could not have reflected real production
history (the guard was only wired in 2026-07-16) and even today the guard
is advisory-only by design since 2026-07-23 (`enforce_advisory_pre_trade_guards`
defaults `False`) -- nothing has ever been auto-blocked. Calibration-
quality conclusion (adaptive tracks nominal exceedance better than static)
is unaffected. Full detail: `GROUP_A_PLUS_TAIL_CONFORMAL_ACI_20260727.md`
(Part 5 is the new section from today). Memory:
`project_tail_conformal_aci_20260727`.

### Thread 3: SPO/DFL action-value re-proposal -> `decision_confidence` Phase 2 calibration

**The re-proposed SPO/DFL mechanism itself was not reopened** -- it is
the same `evaluate_a2118_decision_focused_action_shadow.py` line whose
REENTER-fix (relief-gate) was OOS-rejected on 2026-07-26. Instead,
completed the one genuinely open thread from that day (Thread 5 of
`GROUP_A_PLUS_20260726_SESSION_HANDOFF_INDEX.md`): replacing
`decision_confidence`'s Phase 1 rank-proxy (46 points) with a real
`P(realized_regret > 0)` empirical calibration.

- Added `calibration_pairs` export to the DFL evaluator (additive, no
  existing behavior changed) -- 4,845 (date, action) pairs from a single
  7-window run, vs Phase 1's 46.
- Built binned-empirical-rate calibration in `ncf_decision_calibration.py`
  (`fit_regret_calibration`/`predict_calibrated_probability`), fit on
  `tuning_window` only.
- **OOS-validated on 2017/2018/2019 (never used to fit): the sample-size
  problem is solved, but the calibrated probabilities do not transfer**
  -- CAP10's top bin trained on 8.3% win probability, actual OOS was
  59.5%.
- Extended to regime-condition on `total_risk_score` (low/elevated/severe
  buckets) -- **also does not help**: every single 2017-2019 OOS pair
  falls in the "low" bucket (matching the already-known finding that
  `total_risk_score` never exceeded 2 before 2020), so there is no
  cross-regime variation to test against on this axis, and the weighted
  OOS calibration error actually got slightly worse (0.129 -> 0.158).
- Per this project's 2-3-rounds-then-stop tuning discipline, stopped
  after this second attempt rather than trying a third regime variable
  against the same fixed OOS years.
- `--use-calibration-model` defaults **off** on
  `evaluate_ncf_decision_calibration.py`; Phase 1's honestly-labeled rank
  proxy remains the default `decision_confidence` source.

96 tests added/updated across
`tests/test_evaluate_a2118_decision_focused_action_shadow.py` (21) and
`tests/test_ncf_decision_calibration.py` (26), all passing; full relevant
suite (`-k "decision_focused_action_shadow or ncf_decision_calibration or
dfl"`) at 70/70; full repo suite at 1452 passed / 9 skipped / 0 failed.
Full detail: `GROUP_A_PLUS_DFL_ACTION_VALUE_CALIBRATION_PHASE2_20260727.md`.
Memory: `project_spo_dfl_action_value_already_closed_20260727`,
`project_dfl_decision_confidence_phase2_calibration_20260727`.

### Thread 4: Ops health check and NCF panel refresh attempt

**Pipeline healthy. Refresh attempted per the project's own established
procedure, found unsafe, not executed.**

- No pipeline crash or scheduling gap; one false alarm (suspected test
  suite writing to live report files) investigated and ruled out by
  content inspection.
- Active `ncf_panel_stale` alert (medium severity): production's NCF
  panel has been pinned to `...20260716.csv` since before the
  2026-07-21 pipeline outage; nobody has done the routine follow-up
  re-pin since the 2026-07-25 fix (that step is a deliberate human
  action, not part of the automated batch).
- Followed the project's own established re-pin procedure (the same
  `run_a2118` trigger-stability comparison used for every prior pin
  update) against the freshest already-generated panel (`...20260725.csv`,
  through 2026-07-24): **35 of 599 overlapping trading days would change
  `execution_regime`**, reviving `ncf_late_bull_hedge` (0 -> 35 triggers)
  across dates from 2025-10-23 through 2026-03-03 -- months in the past,
  directly contradicting a 2026-07-23 audit that confirmed this exact
  trigger condition never fires across 6 different panel snapshots.
- Confirmed this is genuine prediction drift (not an alignment bug) by
  diffing raw `h20_prob_up`/`confidence` for identical historical dates
  across the two panels.
- Quantified with the existing `evaluate_ncf_panel_drift.py --outcome-aware`
  tool: max drift (0.196/0.270) exceeds the 2026-07-07 fix's <=0.13
  bound (flagged as a new, unaddressed drift source, not chased down
  further); **decisively, the newer panel's changed predictions are not
  more accurate than what they replace on now-resolved outcomes** (42.5%
  -49.3% "candidate favorable" across three columns, at or below a coin
  flip) -- consistent with retraining noise, not real signal.
- **Did not refresh the pin.** Full detail:
  `GROUP_A_PLUS_OPS_HEALTH_PANEL_DRIFT_20260727.md`. Memory:
  `project_ops_health_check_20260727`.

### Thread 5: Daily pipeline governance-chain crash -- root cause and fix

**Root-caused and fixed a real, previously-unwired dependency gap in
`scripts/run/run_ncf_daily_pipeline.py`; verified against a real full
pipeline run that produced today's live signal.**

- A manually-triggered training run crashed at step 13/72 on
  `FileNotFoundError` for `ncf_panel_same_method_baseline_manifest_20260727.json`.
- Root cause: three files in a TabNet-vs-no-TabNet promotion-governance
  chain (for a *different* candidate model -- explicitly
  `"promote_to_live": false"` in its own manifest, unrelated to a2118's
  live signal) were referenced by date-stamped filename by two automated
  steps, but no automated step ever generated them -- every prior day's
  copy existed only because someone had manually run the generating
  commands that same day (per
  `docs/HANDOFF_GROUPA_PLUS_EXTERNAL_SENSITIVITY_OBSERVATION_20260722.md`).
  Compounding this, the crash aborted the *entire remaining pipeline*
  (including `daily_signal`/`execution_plan`/`alert_state`/`daily_status`)
  since this chain was not in `BEST_EFFORT_STEP_NAMES`.
- Fix: wired the three missing generation steps into the pipeline
  (reusing already-existing scripts, no new computation logic), and added
  the whole 6-step governance chain to `BEST_EFFORT_STEP_NAMES` for
  defense in depth, matching the ~40 other research/governance-only steps
  already in that set.
- 19/19 (`test_run_ncf_daily_pipeline.py`) and 36/36 (`-k
  "run_ncf_daily_pipeline or panel_drift or same_method"`) passing; full
  repo suite 1457 passed / 9 skipped / 0 failed.
- **Verified against a real end-to-end run** for the same date stamp the
  crashed run had used: 75/75 steps completed, the exact alert last
  night's crash had produced (`ops_health_pipeline`, high severity) is now
  `resolved`, and today's (2026-07-27) live signal was successfully
  regenerated (00631L UP prob_up=0.637, 00632R DOWN prob_up=0.2198,
  deleverage INACTIVE).
- Full detail: `GROUP_A_PLUS_DAILY_PIPELINE_GOVERNANCE_CHAIN_FIX_20260727.md`.

## What was NOT done (session-wide)

- The new, independent drift-magnitude finding from Thread 4 (max
  0.196/0.270, exceeding the 2026-07-07 fix's <=0.13 bound) was not
  root-caused. Worth a dedicated investigation on its own.
- Thread 3's calibration work was not extended to a third regime
  variable (execution-regime label, bull/bear proxy, VIX level) --
  deliberately, per the tuning-round discipline. A fresh OOS year (e.g.
  a genuine 2023 NCF backfill, following the same pattern as 2026-07-26's
  H6) would be needed before trying again.
- Thread 4's `network_spillover_snapshot_stale` and
  `00631l_crash_risk_family_degraded` alerts were read but not
  investigated (lower priority, shadow/watch-level only).
- No commit was made this session (all changes remain in the working
  tree, per the user's standing preference not to be prompted about
  committing).
- Thread 5 did not backfill the missing same-day governance files for any
  date between 2026-07-22 and 2026-07-27, nor investigate whether the
  underlying `blocked_observation_required` promotion-gate status (a
  separate candidate model's governance question, not a2118's) has
  changed -- only the automation gap was fixed.
