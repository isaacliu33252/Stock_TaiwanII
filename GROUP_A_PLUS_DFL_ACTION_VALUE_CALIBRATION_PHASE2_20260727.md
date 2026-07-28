# DFL Action-Value Calibration -- Phase 2 (2026-07-27)

## Status

Additive, tested, opt-in only. Does not change any weight, guard, or
production default. `decision_confidence` still defaults to the Phase 1
rank proxy; the new empirical calibration is available via
`--use-calibration-model` on `evaluate_ncf_decision_calibration.py` but is
**not recommended as a default** given the out-of-sample result below.

## Origin

Same-day continuation of a session that opened with the user re-proposing
arXiv:2601.04062/2605.01176's SPO/decision-focused-action idea as a fresh
5-action ("KEEP_A2118/NO_ADD_00631L/ROTATE10_TO_0050/PARTIAL_REENTRY/
FULL_REENTRY" + conservative-lower-bound-on-action-value) mechanism.
Investigation found this is not new -- it is the same
`evaluate_a2118_decision_focused_action_shadow.py` line built 2026-07-13/14
and already run through a relief-gate REENTER fix that a fresh 2021 OOS
backfill overturned on 2026-07-26 (see
`GROUP_A_PLUS_H20_CALIBRATION_PANEL_DRIFT_GATE_DEADLOCK_HANDOFF_20260726.md`
Part H). That line was not reopened. Separately, a genuinely open thread
from 2026-07-26 (Thread 5 of that session) was picked instead: replacing
`decision_confidence`'s Phase 1 rank-proxy with a real
`P(overlay_utility > 0)` calibration, which that session had explicitly
identified as needing the DFL evaluator to export realized regret labels
per decision -- not attempted then "to avoid modifying an already-
delicate, actively-relied-on simulation script without a dedicated review."

## What was built

### 1. `calibration_pairs` export (additive, evaluator unchanged otherwise)

`scripts/evaluate/evaluate_a2118_decision_focused_action_shadow.py`:
new function `_build_calibration_pairs(labels, predicted, ...)` and one new
key in `evaluate_window()`'s return dict, `calibration_pairs`: a long-format
list of `{date, action, predicted_regret, realized_regret}` for every
(date, action) pair that has cleared the same `min_train_days`/
`train_window_days` warm-up `_predict_action_regrets` itself requires.
Reuses the already-computed `predicted` and `labels` DataFrames --
zero changes to `_predict_action_regrets`, `_select_actions`,
`_select_actions_stateful`, `_build_action_labels`, or any existing output
key. 3 new tests (`tests/test_evaluate_a2118_decision_focused_action_shadow.py`),
20/20 passing in that file, 63/63 passing across
`-k "decision_focused_action_shadow or dfl or daily_pipeline"`.

This is a much larger sample than Phase 1's 46 points: running the
production best-candidate config (`--stateful-actions
--require-panel-signal --min-train-days 60 --edge-threshold 0.0005
--reenter-edge-threshold -0.0005 --regret-clip 0.02
--adjustment-fraction 0.75 --turnover-cap 0.05`) across the existing
7-window promotion-style set produced **4,845 calibration pairs** (3,408 in
the `tuning_window` bucket: covid_2020/inflation_2022/live_2024_2026/
active_2025_2026; 1,437 in `out_of_sample`: 2017_bull/2018_correction/
2019_recovery), regardless of whether `--require-panel-signal` gated the
*action selection* to KEEP that day -- `calibration_pairs` reflects every
date's prediction/label, not just the days the evaluator actually deviated.
Output: `results/a2118_decision_focused_action_shadow_calibration_phase2_20260727.json`.

### 2. Empirical binned calibration in `ncf_decision_calibration.py`

New: `load_calibration_pairs()`, `RegretCalibrationModel`,
`fit_regret_calibration()`, `predict_calibrated_probability()`.
Deliberately a simple binned-empirical-rate model (5 quantile bins per
action by default, fit on `tuning_window` bucket only, `min_bin_size=20`
minimum before an action gets a fitted model at all) -- not a parametric
model, consistent with the DFL evaluator's own "avoids neural networks"
design philosophy and this project's general preference for auditable
methods over ones easy to overfit with a modest sample.

`build_snapshot()` now accepts an optional `calibration_model`: when a bin
match exists, `decision_confidence` becomes `P(realized_regret > 0)` from
that bin (`calibration_method="empirical_realized_regret_calibration"`);
otherwise it falls back to the unchanged Phase 1 rank proxy
(`calibration_method="predicted_regret_percentile_rank_proxy"`). 8 new
tests in `tests/test_ncf_decision_calibration.py` (22/22 passing in that
file), including a leakage check (an OOS-bucket row with reversed sign
must not influence the fitted bins).

`scripts/evaluate/evaluate_ncf_decision_calibration.py` gained
`--use-calibration-model` (and `--calibration-bins`/
`--calibration-min-bin-size`), **default off** -- see verdict below for why.

## Out-of-sample validation (the actual test)

Fit `fit_regret_calibration()` on the 3,408 `tuning_window` pairs only,
then checked whether the 1,437 `out_of_sample` pairs (2017/2018/2019 --
never used to pick bin edges or win-rates) actually realize the win-rate
each trained bin predicts. Per action:

**REENTER**: could not be calibrated at all -- `predicted_regret` is a
constant `0.0` across all 1,136 tuning_window REENTER rows (`nunique=1`).
This is the same, already-documented REENTER-starvation finding from
2026-07-26 (REENTER's ridge regressor is data-starved and effectively
never predicts anything but the KEEP anchor) -- `fit_regret_calibration`
correctly detects the degenerate quantile edges and skips it rather than
fitting nonsense. Not a new problem, not fixed by this work.

**NO_ADD**: `realized_regret` is `<= 0.0` for every single one of the
1,136 tuning_window rows *and* all 479 out_of_sample rows -- NO_ADD never
once beat KEEP anywhere in this dataset (plausible: trimming 00631L
into cash gives up upside that, across 2020/2022/2024/2025-2026 and
2017-2019, was worth more than the downside protection saved often
enough that it never paid off in this window set). The calibration
degenerates to a constant ~0% in every bin, which trivially "matches" OOS
exactly (weighted error 0.000) -- but this is a constant answer, not
evidence of a working calibration curve.

**CAP10 -- the one action that matters** (the only non-KEEP action that
has ever actually fired in the currently-deployed best-candidate
config): a real relationship exists in both halves of the data (OOS
`corr(predicted_regret, realized_regret>0) = +0.353`, i.e. the direction
is genuinely right), but the **calibrated probability values do not
transfer**:

```
bin (predicted_regret)         train_rate  train_n   oos_rate  oos_n
[-0.0140,-0.0067)                   0.154      227      0.067     60
[-0.0067,-0.0051)                   0.198      227      0.101     89
[-0.0051,-0.0031)                   0.184      228      0.107    150
[-0.0031,-0.0001)                   0.159      226      0.280    143
[-0.0001,+0.0116)                   0.083      228      0.595     37
weighted mean |train_rate - oos_rate| = 0.129 (n=479)
```

The top bin is the starkest failure: trained on 8.3% win probability,
actual out-of-sample win rate was 59.5% -- a 51-point miss in the
direction that would matter most (this is exactly the bin a live gate
would use to decide "is this CAP10 worth it"). The training curve isn't
even monotonic (0.154 -> 0.198 -> 0.184 -> 0.159 -> 0.083, a mild hump),
while the OOS curve is cleanly monotonic increasing -- the shape of the
relationship itself differs between the two data slices, not just its
level.

## Regime-conditioned follow-up (same day) -- also does not fix it

Given the pooled calibration's failure mode looked like a regime-dependence
problem, extended both layers to optionally condition on a regime label:

- `evaluate_a2118_decision_focused_action_shadow.py`: `_build_calibration_pairs`
  now accepts an optional `features` argument and attaches that date's
  `total_risk_score` (already a `FEATURE_COLUMNS` entry) to each exported
  row when given. `evaluate_window()` passes its already-computed
  `features` through -- still additive, no other behavior change. 1 new
  test (21/21 passing in that file).
- `ncf_decision_calibration.py`: `fit_regret_calibration()` gained
  `regime_column`/`regime_edges` -- when set, fits *separate* bins per
  regime bucket (`low`/`elevated`/`severe`, matching this project's
  existing `total_risk_score` gate-threshold vocabulary, default split at
  6.0/9.0) instead of one pooled calibration. `RegretCalibrationModel.by_action`
  is now nested (`action -> regime_label -> bins`); `GLOBAL_REGIME_LABEL`
  (`"__all__"`) preserves the old pooled behavior when `regime_column` is
  omitted. `predict_calibrated_probability()` gained `regime_value` and
  **deliberately does not fall back to a pooled estimate when the specific
  regime bucket has no fitted bins** -- silently blending would hide
  exactly the gap this was built to test. 4 new tests (26/26 passing).

**Result: regime-conditioning by `total_risk_score` does not fix the OOS
transfer problem, and mildly hurts it.** Fitting `total_risk_score`
buckets on the `tuning_window` data (`edges=(6.0, 9.0)`) put CAP10's
2020/2022/2024/2025-2026 tuning data into `elevated` (n=176) and `low`
(n=931) -- but **every single one of the 479 CAP10 `out_of_sample` pairs
(2017/2018/2019) falls into the `low` bucket**. This isn't new: it
directly confirms the 2026-07-26 finding in
[[project_spo_paper_robustness_checklist_item7_20260726]] that
`total_risk_score`'s yearly ceiling never exceeded 2 before 2020. There is
no cross-regime variation in the OOS years to test against on this axis at
all, so conditioning on it cannot help by construction, and the `low`
bucket's calibration is fit on fewer rows (931 vs the pooled 1,136) for no
offsetting benefit -- weighted OOS calibration error actually rises
slightly, 0.129 (pooled) -> 0.158 (regime-conditioned, `low` bucket only).

**Conclusion: whatever separates 2017-2019 from 2020/2022/2024/2025-2026
for CAP10's calibration, it is not `total_risk_score`.** Per
[[feedback_overfitting_fixed_window_tuning]] (more than 2-3 tuning rounds
against the same fixed OOS sample requires a fresh validation set before
claiming anything further), this is the second attempt against the same
2017/2018/2019 OOS set (pooled, then regime-conditioned) -- stopping here
rather than trying a third regime variable (e.g. an execution-regime
label, a bull/bear market proxy, or VIX level) against the same fixed OOS
years. A genuinely different conditioning variable is a reasonable future
direction, but it needs either a fresh OOS year or to be tried once, not
iterated, against this one.

## Verdict

**Same overall pattern as the rest of this project's July research**:
directionally real in one slice, does not reliably transfer to a
genuinely different regime once tested honestly OOS. The sample-size
problem Phase 1 flagged (46 points) is genuinely fixed (thousands of
pairs now available for any future work on this), but fixing the sample
size did not fix the underlying issue -- the mapping from predicted_regret
to actual win probability is itself regime-dependent, similar in spirit to
2026-07-26's relief-gate finding (a mechanism that worked when iterated
against 7 in-sample windows failed a fresh 2021 OOS check).

**Decision: `--use-calibration-model` defaults off.** The Phase 1 rank
proxy (already honestly labeled as "not a calibrated probability") remains
the default `decision_confidence` source. The calibration machinery is
kept, tested, and available as an opt-in research path -- do not turn it
on by default without either (a) a materially larger and more diverse
`tuning_window` sample (more real crisis years, not just 2020/2022/
2024/2025-2026), or (b) a calibration method that's regime-aware rather
than a single global binning (e.g. conditioning bins on a regime label,
analogous to what DtACI does for `tail_conformal`'s conformal intervals --
see [[project_tail_conformal_aci_20260727]] for the same underlying
"single fixed calibration doesn't survive regime change" pattern showing
up in a completely different part of this codebase the same week).

## What was NOT done

- Regime-conditioning was tried once (`total_risk_score`, see above) and
  found not to help -- an ACI-style online-adaptive calibration
  (analogous to `tail_conformal`'s) or a different conditioning variable
  (execution-regime label, bull/bear proxy, VIX level) was not attempted.
  Per the tuning-round discipline cited above, do not try a third variant
  against this same 2017/2018/2019 OOS set -- get a fresh OOS year first
  (e.g. a genuine 2023 backfill, following the same pattern
  [[project_h20_calibration_drift_gate_deadlock_20260726]]'s H6 used).
- REENTER's underlying data-starvation problem was not touched (out of
  scope for this thread; see the 2026-07-26 relief-gate work and its
  OOS-rejection instead).
- The calibration bin count (5) and `min_bin_size` (20) were not swept --
  kept at first reasonable values to avoid tuning against the same
  tuning_window bucket used to fit the bins in the first place.
- Nothing was wired into `daily_signal.py`, `execution_plan.py`, or any
  production guard -- this entire thread is a diagnostic-only module two
  layers removed from the live signal (`ncf_decision_calibration.py` is
  itself downstream of the still-research-only DFL advisory shadow).

## Reproduction

```bash
python3 -m pytest tests/test_evaluate_a2118_decision_focused_action_shadow.py tests/test_ncf_decision_calibration.py -q

python3 scripts/evaluate/evaluate_a2118_decision_focused_action_shadow.py \
  --stateful-actions --require-panel-signal --min-train-days 60 \
  --edge-threshold 0.0005 --reenter-edge-threshold -0.0005 \
  --regret-clip 0.02 --adjustment-fraction 0.75 --turnover-cap 0.05 \
  --windows covid_2020:2020-01-02:2020-12-31:results/ncf_00631l_panel_latest_20260707.csv:tuning_window,inflation_2022:2022-01-03:2022-12-30:results/ncf_00631l_panel_latest_20260707.csv:tuning_window,live_2024_2026:2024-01-02:latest:results/ncf_00631l_panel_latest_20260707.csv:tuning_window,active_2025_2026:2025-01-02:latest:results/ncf_00631l_panel_latest_20260707.csv:tuning_window,2017_bull:2017-01-03:2017-12-29:results/ncf_00631l_panel_backfill_2017_2019_20260710.csv:out_of_sample,2018_correction:2018-01-02:2018-12-31:results/ncf_00631l_panel_backfill_2017_2019_20260710.csv:out_of_sample,2019_recovery:2019-01-02:2019-12-31:results/ncf_00631l_panel_backfill_2017_2019_20260710.csv:out_of_sample \
  --output results/a2118_decision_focused_action_shadow_calibration_phase2_20260727.json

python3 scripts/evaluate/evaluate_ncf_decision_calibration.py --use-calibration-model \
  --dfl-shadow results/a2118_decision_focused_action_shadow_calibration_phase2_20260727.json
```
