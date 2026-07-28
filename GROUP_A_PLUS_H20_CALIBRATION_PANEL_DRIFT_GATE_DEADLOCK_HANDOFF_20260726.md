# h20 Calibration Bias, Late-Bull-Hedge Trigger Discrepancy, and Panel-Drift Governance Deadlock — 2026-07-26 (Thread 7)

## Status

**Fully analyzed, root-caused, and closed (Parts A-G on the h20-calibration
/ panel-drift-governance line; Part H on the follow-on 00631L<->0050
relief-gate research line, closed on a negative-OOS finding).** Every
anchor date the h20/panel-drift investigation surfaced (2025-03-05,
2025-04-02, 2025-01-15, 2026-07-17) has a confirmed, checked-against-raw-data
explanation -- none were data bugs. Two new, tested, opt-in diagnostic
capabilities were added to `evaluate_ncf_panel_drift.py` (Parts E/F). The
follow-on Part H investigation (00631L<->0050 relief-gate prototype) added
three more composable, tested, opt-in fixes to
`evaluate_a2118_decision_focused_action_shadow.py`, then built a genuine
new-year OOS backfill (2021) that showed the whole relief-gate direction
does *not* clearly generalize (H6) -- recommendation is to stop iterating
on it, not to pursue a multi-signal version. **No production code, gate
threshold, or promotion decision was changed anywhere in this document** --
every new capability (Parts E, F, H3, H4, H5) is additive and off by
default; none is wired into production governance scripts or the daily
pipeline. One real bug was fixed separately (a script that had never
successfully run, Part A). No live allocation was touched anywhere in this
investigation -- every report in the governance chain discussed here
carries `active_allocation_impact: none` / `keep_golden1_0531_unchanged:
true`, and the Part H work is entirely inside a `status: research_only`
shadow evaluator with `advisory_active: false` throughout. This document
is the full record; see `GROUP_A_PLUS_20260726_SESSION_HANDOFF_INDEX.md`
Thread 7 for the short version and
[[project_h20_calibration_drift_gate_deadlock_20260726]] for the memory
pointer.

## Origin

User asked to "analyze unfinished handoff tasks" (分析未完成的交接任務).
While auditing today's (2026-07-26) file changes for anything not folded
into the main session index, found two scripts written earlier the same
day that were never mentioned in
`GROUP_A_PLUS_20260726_SESSION_HANDOFF_INDEX.md`'s Thread 5 (the
`direction_confidence`/`decision_confidence` work, which is the closest
related thread) and had no output recorded anywhere in the repo or memory:

- `scripts/evaluate/evaluate_ncf_h20_utility_weighted_calibration.py`
  (created 2026-07-26 11:12)
- `scripts/evaluate/evaluate_ncf_h20_walkforward_bias_correction.py`
  (created 2026-07-26 12:32, references the first script's findings in its
  own docstring)

## Part A: the orphaned calibration scripts

### A1. The bug

`evaluate_ncf_h20_walkforward_bias_correction.py` imports
`from backtest_group_a_plus_switch_policy import DB_PATH` without first
adding `PROJECT_ROOT` to `sys.path` (that module lives at the repo root,
not on the default path when running a script from `scripts/evaluate/`).
Every sibling script in the same directory that needs a repo-root import
(e.g. `evaluate_a2118_dfl_active_date_audit.py`) has the standard
`if str(PROJECT_ROOT) not in sys.path: sys.path.insert(0, str(PROJECT_ROOT))`
guard; this one script was missing it. Result: `ModuleNotFoundError` on the
very first attempt to run it -- **this script had never executed
successfully from the moment it was written until today's fix.**

Fixed by adding:
```python
import sys
...
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH
```
(moved the `PROJECT_ROOT` definition above the import block and added the
guard; previously `PROJECT_ROOT` was defined after the failing import).

### A2. Calibration diagnostic results (script 1, ran without modification)

```
python3 scripts/evaluate/evaluate_ncf_h20_utility_weighted_calibration.py \
    --panel results/ncf_00631l_panel_latest_20260725.csv
```

357 resolved rows (2025-01-02 onward, walk-forward expanding-window
`h20_prob_up` with resolved `actual_up_h20` labels).

```
Overall (unconditional):        Brier=0.2429  bias=-0.2043

Calibration bins (mean_predicted -> realized_freq -> gap):
  (0.121, 0.282]  n=72  pred=0.220  realized=0.569  gap=-0.349
  (0.282, 0.435]  n=71  pred=0.360  realized=0.761  gap=-0.401
  (0.435, 0.628]  n=71  pred=0.532  realized=0.817  gap=-0.285
  (0.628, 0.861]  n=71  pred=0.766  realized=0.803  gap=-0.037
  (0.861, 0.971]  n=72  pred=0.910  realized=0.861  gap=+0.049

Near vs far from the 0.5 decision threshold:
  NEAR (decision-sensitive): n=179  Brier=0.2817  bias=-0.3309
  FAR  (confident):          n=178  Brier=0.2039  bias=-0.0771

Realized-vol-20d terciles:
  low:    n=119  Brier=0.2162  bias=-0.2774
  medium: n=119  Brier=0.2952  bias=-0.1127
  high:   n=119  Brier=0.2174  bias=-0.2230

Combined "decisive" cell (near-threshold AND high-vol):
  decisive:      n=55   Brier=0.3095  bias=-0.3819
  everything else: n=302 Brier=0.2308  bias=-0.1720
```

**Reading**: `h20_prob_up` is systematically underconfident about "up"
across the whole sample (bias -0.20), but the miscalibration roughly
*doubles* in the region that actually drives trading decisions (near the
0.5 threshold: -0.33 vs -0.08 far from it; the near-threshold+high-vol
"decisive" cell: -0.38 vs -0.17 elsewhere). This is exactly the pattern
arXiv:2601.07852 (Wright, 2026) predicts: global/unconditional calibration
metrics look passable-ish while error concentrates specifically where
decisions get made.

### A3. Walk-forward bias-correction backtest (script 2, ran after the fix)

```
python3 scripts/evaluate/evaluate_ncf_h20_walkforward_bias_correction.py \
    --panel results/ncf_00631l_panel_latest_20260725.csv
```

Method: at each date, additively shift `prob_up_h20` by the trailing
`mean(predicted) - mean(actual)` computed only from labels resolved
strictly before that date (same `resolved_end = pos - HORIZON` convention
as `_build_expanding_horizon_ensemble_panel` in
`scripts/misc/ncf_00631l.py`; `min_history=60` before any correction is
applied), then re-run `run_a2118()` against both the original and the
corrected panel over the same window.

```
Calibration, out-of-sample:
  Original   Brier=0.2429  bias=-0.2043
  Corrected  Brier=0.2491  bias=-0.1731

AUC original:  0.6545
AUC corrected: 0.6136   (expected ~identical -- daily shift should
                          preserve same-day ranking; it did not, because
                          the correction magnitude itself drifts over time)

Mean confidence original:  0.3076
Mean confidence corrected: 0.4608

Backtest (production panel vs bias-corrected panel, same window,
same run_a2118() call):
  production_panel:      sharpe=2.1022  sortino=2.2027  annual_return=0.5239
                          max_dd=-0.1356  late_bull_trigger_days=3
    events: 2025-09-30 (ma_gap=0.149, prob_up_h20=0.180, confidence=0.577,
                         trigger_type=initial)
            2026-01-29 (ma_gap=0.169, prob_up_h20=0.235, confidence=0.562,
                         trigger_type=initial)
            2026-02-23 (ma_gap=0.191, prob_up_h20=0.137, confidence=0.591,
                         trigger_type=initial)

  bias_corrected_panel:  sharpe=2.0299  sortino=2.1224  annual_return=0.5517
                          max_dd=-0.1356  late_bull_trigger_days=2
    events: 2025-08-11 (ma_gap=0.147, prob_up_h20=0.211, confidence=0.577,
                         trigger_type=initial)
            2025-09-08 (ma_gap=0.110, prob_up_h20=0.166, confidence=0.669,
                         trigger_type=initial)
```

**Reading**: correcting the bias does have a real, mechanical effect on
late-bull-hedge (trigger count changes, and *which* days trigger changes
completely -- zero overlap between the two event lists), confirming the
hypothesized mechanism (undershoot near 0.5 suppresses confidence, which
suppresses triggering). But the net effect on risk-adjusted return is
mixed-to-negative (Sharpe/Sortino/AUC all worse; only annual return and
MaxDD are flat-to-better), so this is **not** adopted -- it is a mechanism
verification only, consistent with how every other tactical-overlay
candidate in this project has been treated (evidence-gated, not
auto-adopted from a single backtest).

## Part B: an unexpected contradiction with 07-23's finding

[[project_a2118_ncf_hedge_dormancy_root_cause_20260723]] did an exhaustive,
byte-identical-confirmed investigation on 2026-07-23 (extended 07-24) and
concluded **0 late-bull-hedge triggers** across four independent
backtested years (2017-2019, 2020, 2022, 2025-2026), using panel
`ncf_00631l_panel_latest_20260722.csv`. That investigation's headline
result: `a2118`'s current Sharpe improvement over `a2111` is 100%
attributable to the 2020 COVID switch-rule fix
([[project_2020_switch_rule_fix_promotion_ready_20260706]]); NCF
late-bull-hedge's own contribution is exactly zero, confirmed to the
decimal place across three parallel `run_a2118()` configurations.

Today's Part A backtest (`production_panel`, panel `20260725`) shows
**3 triggers**, all in 2025-2026, one of them (2026-02-23) on a date well
before 07-23's investigation. If the same panel and thresholds had been in
effect on 07-23, that investigation should have seen this trigger too.

Both findings are individually correct for the exact panel snapshot each
one used -- this is not a methodology error in either investigation. The
implication is that `h20_prob_up` (or `confidence`, which is derived from
it via `ensemble_prob_up`) moved across the trigger thresholds
(`h20_max=0.33`, `conf_min=0.55`, `ma_gap_min=0.10`) on specific historical
dates *between panel regeneration 20260722 and 20260725* -- i.e., the
underlying panel is not stable across regenerations even for dates that
are years in the past and should never change once resolved.

## Part C: root cause, traced through a pre-existing governance chain

This governance chain was **not built during this session** -- it already
existed, running as part of the daily pipeline, and had already caught
this exact drift. It was simply never written up in prose anywhere
(memory or handoff docs), so nobody had connected it to the Part B
contradiction until today.

Chain (each file linked to the next via an internal `source_*`/`inputs`
field):

```
results/ncf_panel_drift_diagnosis_20260725.json
  -> results/ncf_panel_drift_remediation_plan_20260725.json
       -> results/ncf_panel_drift_model_set_isolation_report_20260725.json
       -> results/ncf_panel_external_feature_sensitivity_governance_20260725.json
            -> report/group_a_plus/latest/external_sensitivity_observation_log.json
  -> report/group_a_plus/panel_drift_triage/history/panel_drift_triage_2026072{5,6}.json
  -> report/group_a_plus/panel_drift_resolution_progress/history/panel_drift_resolution_progress_20260726.json
```

### C1. Diagnosis: `h20_prob_up` exceeds drift limits, baseline vs candidate

`ncf_panel_drift_diagnosis_20260725.json`:
- `baseline_panel`: `results/ncf_00631l_panel_latest_20260716.csv`
- `candidate_panel`: `results/ncf_00631l_panel_latest_20260725.csv`
- overlap: 2025-01-02 to 2026-07-16, 371 rows
- `exceeded_columns` / `trigger_critical_exceeded`: `["h20_prob_up"]`
- `source_hypotheses`: `["model_set_changed"]`

`panel_drift_triage_20260726.json` (the daily-pipeline-facing summary of
the same diagnosis): `h20_prob_up` max_abs_delta 0.1964 on 2026-02-10
(baseline 0.3438 -> candidate 0.1474), limit 0.15. Top exceed months:
2026-04 (8 rows), 2026-02 (6), 2026-06 (6). `status: blocked`,
`target_weight_change_allowed: false`, `auto_rebalance_allowed: false`,
`keep_golden1_0531_unchanged: true`.

### C2. TabNet model-set change -- isolated and effectively resolved

`ncf_panel_drift_remediation_plan_20260725.json`, action
`isolate_model_set_change`: **resolved**. `removed_models: ["tabnet"]`,
`added_models: []` -- TabNet was present in the ensemble that generated
the 07-16 baseline panel and absent from the one that generated the 07-25
candidate panel.

`ncf_panel_drift_model_set_isolation_report_20260725.json` verifies this
explains most (not all) of the raw drift, via a same-method comparison
(comparing a no-TabNet-vs-no-TabNet rebuild against the raw
baseline-vs-candidate numbers):

```
                          h20_prob_up max_abs_delta   passes 0.15 limit?
original_vs_today (raw)         0.1995 (2026-02-10)    NO
original_vs_no_tabnet           0.2641 (2025-09-18)    NO
no_tabnet_vs_today (apples-to-apples)  0.1237 (2026-02-10)  YES
```

`conclusion.same_method_no_tabnet_passes_configured_limits: true`. So once
you control for the TabNet removal, this specific drift source is back
within the configured tolerance. This part of the puzzle is understood and
not the live blocker.

### C3. External-feature sensitivity -- the actual, larger blocker

`ncf_panel_external_feature_sensitivity_governance_20260725.json` compares
a panel built **with** the `EXT_FEATURES` block (see `scripts/misc/ncf_00631l.py`
lines ~156-199: US overnight returns/VIX/USDTWD, same-day TWII/TSMC/0050
technicals, T-1 institutional net-buy and margin/short data, TX night
session, and TXO options positioning) against the same panel built
**without** it (`--no-external-features`):

```
trigger_critical:
  h20_prob_up:  max_abs_delta=0.5114  limit=0.15  date=2025-04-02  EXCEEDS
  confidence:   max_abs_delta=0.6373  limit=0.28  date=2025-03-05  EXCEEDS
diagnostic:
  ensemble_prob_up: max_abs_delta=0.4532  limit=0.15  date=2025-01-15  EXCEEDS
```

`governance.resolution_allowed: false`, `reason: "external-feature
sensitivity exceeds trigger-critical limits"`, requiring
`required_observation_sessions: 3` with **all three** stable (no
trigger-critical column exceeding its limit) before the blocker clears.
As of 2026-07-26: `completed_observation_sessions: 2`,
`stable_observation_sessions: 0`.

### C4. The "3 stable observation sessions" gate cannot resolve by waiting

`report/group_a_plus/latest/external_sensitivity_observation_log.json`
records two logged observations, 2026-07-22 and 2026-07-25. Their
`trigger_critical` blocks are **byte-identical**: `h20_prob_up`
max_abs_delta = 0.5113554732054251 at 2025-04-02 in both;
`confidence` max_abs_delta = 0.6372621107070484 at 2025-03-05 in both.

Traced to `scripts/evaluate/evaluate_ncf_panel_drift.py`: `overlap_start`/
`overlap_end` are computed as `common_idx.min()`/`common_idx.max()` -- the
**full intersection of both panels' date indices**, with no `--start` /
trailing-window CLI option to restrict the comparison to recent data. Since
2025-03-05 and 2025-04-02 are historical, already-resolved rows that never
change, and the `max_abs_delta` reported for each trigger-critical column
is a maximum over the *entire* multi-year overlap, **no future daily
observation session can ever produce a smaller max unless it happens to
also exceed the current record on some other date** (which would make
things worse, not resolve the gate) or the methodology itself changes. The
`build_group_a_plus_external_sensitivity_observation_log.py` stability
check (`stable = valid and not trigger_exceeded`) will therefore assign
`stable_observation: false` to every future session indefinitely, and
`stable_observation_count` is structurally locked at 0.

**This is a governance-design bug, not a "needs more time" situation.**
`remaining_stable_observation_sessions: 3` will never decrement under the
current implementation.

## Part D: the two anchor dates are not bugs -- they are correctly-caught crises

Given C3/C4 hinge entirely on 2025-03-05 and 2025-04-02, checked the raw
`external_market_ohlcv` table (DuckDB, `FinRL/data/stock_data.db`) for
`^VIX` and `QQQ` around both dates, and diffed the actual panel rows
(`ncf_00631l_panel_latest_20260725.csv` vs
`ncf_00631l_panel_latest_20260725_no_external.csv`) at each date.

### 2025-03-05

Real market context: VIX climbed from 18.98 (02-24) through 21.93 (03-05)
to 24.87 (03-06) amid a real US equity selloff (QQQ fell from ~516 on
02-24 to ~469 by 03-10).

Panel row deltas (external-features model minus no-external-features
model) on 2025-03-05:
```
prob_up_h1:    0.1711 vs 0.8507   (Δ -0.680)
prob_up_h5:    0.6807 vs 0.8954   (Δ -0.215)
prob_up_h20:   0.7717 vs 0.8332   (Δ -0.062)  -- h20 itself barely moves
ensemble_prob_up: 0.5412 vs 0.8598 (Δ -0.319)
confidence/prob_magnitude: 0.0823 vs 0.7196   (Δ -0.637)  -- this is the
                                                             trigger_critical hit
```
The with-external-features model's confidence collapses (0.72 -> 0.08)
specifically because its 1-day-horizon call swings hugely (0.85 -> 0.17)
in response to the deteriorating macro backdrop, while the no-external
model stays confidently bullish across all horizons, blind to it.

### 2025-04-02

Real market context: this is the "Liberation Day" US tariff announcement
date. VIX closed 21.51 that day, then exploded to 30.02 (04-03), 45.31
(04-04), and an intraday high of 60.13 on 04-07 -- one of the sharpest VIX
spikes in the dataset's history. QQQ fell from 473 (04-02) to 420 by
04-04.

Panel row deltas on 2025-04-02:
```
prob_up_h1:    0.5862 vs 0.3234   (Δ +0.263)
prob_up_h5:    0.7029 vs 0.2908   (Δ +0.412)
prob_up_h20:   0.1450 vs 0.6563   (Δ -0.511)  -- this is the
                                                 trigger_critical hit
ensemble_prob_up: 0.4780 vs 0.4235 (Δ +0.055)
confidence/prob_magnitude: 0.0439 vs 0.1530  (Δ -0.109)
```
The with-external-features model's 20-day call flips bearish (0.145) the
same day the tariff shock hits, ahead of the crash that followed over the
next week. The no-external model stays bullish (0.656), with no way to
have known about the tariff announcement from price/technical data alone.

### Conclusion

**Both anchor dates are the external-features model correctly
differentiating from the price-only model during a real, subsequently-
confirmed regime shift.** Neither is a data gap, a stale value, or a
computation bug -- checked directly against the underlying `^VIX`/`QQQ`
OHLCV and found genuine, large, real-world moves exactly where the panel
diff shows the largest deltas.

The governance gate in Part C is measuring "how much does including
external features change the prediction" as a pure risk signal to be
minimized. But the two data points currently blocking it are exactly the
cases the external features exist to catch. **The gate cannot currently
distinguish "the model is unstable/noisy" from "the model is correctly
sensitive to real regime shifts"** -- both produce a large delta, and the
methodology only measures magnitude, not whether the more-informed
(with-external) side was actually the better call in hindsight (both of
these two cases, it clearly was). This is a methodology blind spot in the
governance design, not evidence that the external-feature panel is
unreliable.

## Part E: fixed the C4 structural deadlock (trailing-window support)

Added an optional `--window-start` argument to
`scripts/evaluate/evaluate_ncf_panel_drift.py`'s `evaluate_panel_drift()`.
When set, `common_idx` (and therefore every downstream `column_summary`
stat, including `max_abs_delta`/`max_abs_delta_date`) is restricted to
dates on or after the cutoff, while `full_overlap_start`/
`full_overlap_end`/`full_overlap_rows` are still recorded in the output for
reference. **Default is `None` (unchanged, full-history behavior)** -- this
is additive; every existing call site (`ncf_panel_drift_active_vs_*`, the
main TabNet-triage comparison) keeps its exact current behavior unless a
caller explicitly opts in. Two new tests added to
`tests/test_evaluate_ncf_panel_drift.py` (window excludes a
synthetically-large-delta date from the summary while the full-overlap
metadata still reports it) -- `pytest tests/ -k "panel_drift or
evaluate_ncf_panel_drift"`: 14/14 passing (12 pre-existing + 2 new).

This is the fix for Part C4 -- the reason the "3 stable observation
sessions" governance gate could never resolve is that its underlying
`max_abs_delta` was computed over the full multi-year history with no way
to exclude dates that will never be superseded. With `--window-start`, a
future observation session can be pointed at a genuinely trailing window
(e.g. last ~180 calendar days) so old, permanently-fixed outlier dates
stop dominating the "is this stable *now*" question forever.

**Verification with a real rerun** (not just unit tests): reran the same
external-vs-no-external comparison that produces
`ncf_panel_drift_no_external_vs_external_20260725.json`, this time with
`--window-start 2026-01-26` (~180 calendar days back from the panel's last
row):

```
Max drift: h20_prob_up=0.365740@2026-03-23, confidence=0.376906@2026-03-11,
           ensemble_prob_up=0.241968@2026-03-12
```

Still exceeds the 0.15/0.28 trigger-critical limits -- **but this is now an
honest reading of recent behavior, not an artifact of 2025-03-05/04-02
being permanently frozen into the max.** Checked `^VIX`/`QQQ` for
2026-03-01 to 2026-03-25 and found another real, independent volatility
episode (VIX 21.44 -> 29.49 -> settling around 24-27, QQQ declining from
~607 to ~587) -- so the current panel genuinely is going through another
period where external features are legitimately swinging predictions, not
a governance-methodology artifact. **The trailing-window fix does not
unblock the gate today** (recent data has its own real volatility driving
real sensitivity), but it makes the block meaningful again -- it now
reflects current conditions instead of two-year-old, permanently-frozen
history, and can actually converge to "stable" once a genuinely calm
stretch occurs.

**Not done**: did not wire `--window-start` into the actual production
governance scripts (`build_group_a_plus_external_sensitivity_observation_log.py`,
`build_ncf_panel_external_feature_sensitivity_governance.py`,
`run_ncf_daily_pipeline.py`'s command construction) or change what window
length/policy the observation-log builder should use by default -- that is
a real behavior change to production governance (which window length,
whether to apply it retroactively to the existing 07-22/07-25 log
entries, whether calm-vs-crisis classification should factor in too) and
was left for the user to decide. This session only added the *capability*
and verified it works as intended; it is not yet load-bearing anywhere.

The C2/Part D "blind spot" (methodology can't distinguish beneficial
regime-sensitivity from harmful noise) still needed a separate fix --
implemented next, in Part F.

## Part F: outcome-aware scoring (addresses the Part D "blind spot")

Extended `evaluate_panel_drift()` with an opt-in `--outcome-aware` flag.
For probability-of-event columns with a known resolved-label pairing
(`DEFAULT_OUTCOME_PAIRS`: `h20_prob_up`/`prob_up_h1`/`prob_up_h5`/
`prob_up_h20`/`ensemble_prob_up` -> `actual_up_h1`/`actual_up_h5`/
`actual_up_h20` as appropriate; `prob_fwd_mdd_gt5_h20`/`prob_fwd_gain_gt5_h20`
-> their own `actual_*` columns), each date's baseline/candidate squared
error against the realized label is compared. A date is `"candidate"`-favorable
if the candidate (the panel/config being audited) was closer to the truth
than the baseline, `"baseline"`-favorable if the reverse, `"tie"`, or
unresolved (label not yet realized -- e.g. a live prediction still inside
its horizon). `column_summary[col]["outcome_aware"]` reports
`resolved_rows`/`candidate_favorable_rows`/`baseline_favorable_rows`/
`tie_rows` plus a new `risk_relevant_max_abs_delta(_date)`: the largest
delta **excluding dates where the candidate was demonstrably the better
call** (unresolved dates are conservatively kept in the risk-relevant pool
-- absence of proof isn't proof of safety). `confidence` has no direct
probability-of-event pairing and is intentionally left with only the raw
metric, unchanged. Default `outcome_aware=False` -- fully additive, no
existing caller's output changes unless it opts in. 2 new tests added
(`tests/test_evaluate_ncf_panel_drift.py`): one confirms the
candidate-favorable date is excluded and the next-worst genuinely-adverse
date becomes the reported risk-relevant max; one confirms `confidence` gets
no `outcome_aware` block. `pytest tests/ -k "panel_drift or
evaluate_ncf_panel_drift"`: 16/16 passing (14 prior + 2 new).

**Verification with a real rerun** against the same
`ncf_00631l_panel_latest_20260725(_no_external).csv` pair used throughout
this document:

```
Max drift: h20_prob_up=0.511355@2025-04-02, confidence=0.637262@2025-03-05,
           ensemble_prob_up=0.453218@2025-01-15
Risk-relevant drift (excludes candidate-favorable dates):
  h20_prob_up=0.347772@2026-07-17 (candidate_favorable=216/357 resolved)
  ensemble_prob_up=0.453218@2025-01-15 (candidate_favorable=208/357 resolved)
```

This directly confirms Part D's conclusion with a concrete number: on
**216 of 357 resolved days (60.5%)**, the with-external-features panel was
closer to the realized `actual_up_h20` outcome than the without-external
panel -- and 2025-04-02 (the tariff-crash date that was pinning the whole
gate) is specifically one of the candidate-favorable dates, so it drops
out of the risk-relevant view entirely. The new risk-relevant worst case
for `h20_prob_up` moves to **2026-07-17** -- checked directly: this date's
`actual_up_h20` is still `NaN` (`is_live: True`, the label hasn't resolved
yet since h20 needs 20 trading days), so it's correctly retained by the
conservative "unresolved counts as risk-relevant" rule, not because it's a
proven bad call -- there simply isn't a verdict yet. This is a fresh,
current, legitimately-still-open question rather than a two-year-old
fossil, which is exactly the intended effect.

`ensemble_prob_up`'s risk-relevant max is **unchanged** at 2025-01-15 --
that date is *not* excluded, meaning the candidate was not the more
accurate side there. Root-caused in Part G: a genuine false positive, not
a bug -- see Part G for the full explanation.

**Not done**: same as Part E -- not wired into the production governance
scripts or the daily pipeline. The two capabilities (`--window-start`,
`--outcome-aware`) are independent and composable (e.g. a future call
could pass both together for a trailing-window, outcome-aware audit); this
session verified each individually against real data but did not combine
them, and did not decide production defaults for either.

## Part G: root-causing the remaining `ensemble_prob_up` 2025-01-15 residual

Part F left one open item: unlike `h20_prob_up`, `ensemble_prob_up`'s
`risk_relevant_max_abs_delta` stayed pinned at 2025-01-15 (0.4532) even
after outcome-aware filtering -- meaning the candidate (with-external)
panel was *not* the more accurate side that day. Checked it the same way
as Part D's two anchor dates.

**Row-level values on 2025-01-15**: `ensemble_prob_up` with-external=0.374
(bearish) vs no-external=0.827 (bullish); `actual_up_h20=1.0` (the ETF did
go up over the following 20 trading days) -- so the no-external side was
right and the with-external side was wrong here, the reverse of the two
Part D dates.

**Market/flow context**: `^VIX` had spiked to a local high (22.04
intraday, 19.19 close) on 2025-01-13, then fell sharply through
2025-01-15 (opened 19.08, closed 16.12) and kept falling the following
week (15.97, 15.06, 15.10) -- a real, already-reversing volatility episode,
not an ongoing one. More decisively: `institutional_data` for `0050.TW`
shows five consecutive days of real net institutional selling immediately
before this call --

```
2025-01-08: foreign_net_buy=-2,790,647   institutional_total=-3,370,121
2025-01-09: foreign_net_buy=-2,947,520   institutional_total=-3,599,985
2025-01-10: foreign_net_buy=-2,206,597   institutional_total=-2,518,463
2025-01-13: foreign_net_buy=-9,604,680   institutional_total=-15,193,825  <- peak
2025-01-14: foreign_net_buy=-6,218,740   institutional_total=-4,983,438
```

Since `inst_foreign_net`/`inst_foreign_ma5` in `EXT_FEATURES` are T-1
("published after previous close"), the model's 2025-01-15 call would see
2025-01-14's still-heavily-negative flow, on the heels of 2025-01-13's
much larger sell day. This is genuine, not a data artifact -- checked
directly against the raw `institutional_data` table.

**Conclusion: this is not a bug, and not evidence the external-feature
signal is unreliable in general -- it is an ordinary false positive from
an imperfect-but-net-beneficial signal.** The same mechanism that
correctly caught the 2025-03-05 VIX spike and the 2025-04-02 tariff shock
(real, elevated caution flowing from genuine external stress) fired again
here on real, genuine institutional selling -- it just didn't predict a
real correction this time; the market rallied instead. This is
statistically expected and consistent with the Part F headline number:
the with-external panel is closer to truth on 216/357 days (60.5%), which
by construction means it is *not* closer to truth on the other 141 days
(39.5%) -- 2025-01-15 is one instance of that residual, not a special
case requiring a fix. No further action taken; this closes the last open
question from Part F.

## Part H: 00631L<->0050 relative-rotation proposal review, and a relief-gate prototype for the existing DFL shadow line

**Origin**: user proposed a new module ("A2118_00631L_0050_relative_rotation")
inspired by arXiv:2607.06117 (Relief-Gated Relative Rotation for QQQ-DIA),
rotating 00631L into 0050 (not cash) via a two-action KEEP/ROTATE10 design
with relative-return (`ret_00631L_h{5,10,20} - ret_0050_h{5,10,20}`) as the
target, plus no-trade-band/min-holding-days/max-turnover constraints.

### H1. Grounding check (read-only, via a background research fork)

Two things checked against this repo before any design opinion was formed:

1. `docs/2607_06117_RGRR_QQQ_DIA_GROUPA_PLUS_REVIEW_20260725.md` (this exact
   paper, reviewed the day before) concluded "no direct import -- confirmed
   asset-universe mismatch," but **only evaluated an unlevered-vs-unlevered
   QQQ/DIA-style pairing** -- a leveraged-vs-unlevered same-underlying pair
   (00631L vs 0050) was never considered or ruled out. The user's new framing
   is genuinely different from what was already closed.
2. `evaluate_a2118_decision_focused_action_shadow.py` (the DFL shadow line
   extensively tested in Parts A-G above) **already implements almost
   exactly this mechanism**: `_cap_00631l_to_0050()` (rotates excess 00631L
   weight into 0050, not cash -- distinct from the cash-routing
   `_cap_00631l_to_cash()` used by `NO_ADD`), a `CAP10` action functionally
   equivalent to the proposed `ROTATE10`, and `spread_00631l_0050_5d =
   ret_00631l_5d - ret_0050_5d` already present as a ridge-model input
   feature (`FEATURE_COLUMNS`). This line has `advisory_active: false`
   throughout and has never been promoted (main config 3/7 triple-pass
   across the 7 historical windows tested in Part B/C).
3. `letf_tracking_error_effective_fee_readiness` (built from arXiv:1610.09404,
   `docs/1610_09404_LETF_TRACKING_ERROR_GROUPA_PLUS_REVIEW_20260718.md`)
   already quantifies a real mechanical confound in any 00631L-vs-0050
   relative-return target: 20-day tracking error mean **-0.318%**,
   variance-decay-proxy mean **-0.409%** (n=1591, since 2020) -- i.e. a
   meaningful share of `ret_00631L - ret_0050` is leverage/volatility decay,
   not exogenous timing signal. Status `blocked`
   (`realized_effective_fee_proxy_not_validated`).

**Verdict communicated to the user**: directionally reasonable (the
KEEP/ROTATE10 + no-trade-band/min-holding/max-turnover design is sound and
consistent with this project's established anti-high-turnover discipline),
but (a) a near-identical mechanism already exists and has already been
tested with weak results, so a genuinely new module risks re-deriving the
same evidence rather than adding new information, and (b) the proposed
target needs to be checked against the known leverage-decay confound before
any predictive claim can be trusted. Recommended checking *why* the
existing CAP10 mechanism underperforms before building anything new.

### H2. Root-causing the existing DFL shadow line's per-window failure pattern

Read the regenerated `results/a2118_decision_focused_action_shadow_dfl_main_latest.json`
(from Part(Thread) 6 of this document's parent session, main config, 7
windows) directly:

```
window            CAP10  ΔSharpe  ΔAnnualReturn
2018_correction     15   +0.066   +0.013   <- the one clean win
2019_recovery        7   +0.098   -0.030   <- risk-adjusted win, real-money loss
covid_2020          14   -0.163   -0.058   <- clear loss
live_2024_2026       8   +0.0001  -0.036
active_2025_2026     2   +0.004   -0.022
inflation_2022       0     0        0
2017_bull            0     0        0
```

Not a target-design problem -- `spread_00631l_0050_5d` was already a
feature. The actual pattern: the mechanism works in a slow, grinding
correction (2018) and fails specifically in sharp V-shaped rebounds
(2020's -5.8pp being the worst case).

**Root cause, found by inspecting `action_counts` across all 7 windows**:
`REENTER` fired **zero times, in every single window, across all 46
historical non-KEEP days**. Traced to
`_select_actions_stateful()`/`_predict_action_regrets()`: REENTER competes
symmetrically against KEEP (fixed at a `0.0` regret anchor), NO_ADD, and
CAP10 in the same per-action ridge-regression argmax. Since REENTER is only
even a live candidate on days the position is already below the A21.18
target (i.e. a subset of the already-tiny 46 non-KEEP days), its own ridge
coefficients are estimated on almost no data and it essentially never wins
the argmax -- so once CAP10 fires, there is no *modeled* path back to full
exposure; the position only drifts back passively as the A21.18 baseline
itself moves. This directly explains the V-shaped-rebound losses: capped
exposure has no active, timely way to un-cap during the fastest recoveries.

This maps precisely onto arXiv:2607.06117's actual innovation -- the paper
is titled "Relief-**Gated**" specifically because it models the
risk-off and the relief/re-entry condition as two *separate* gated signals
(VIX/rate/credit relief), not one symmetric action-regret regression. The
existing codebase's REENTER implementation is missing exactly that half.

### H3. Prototype: a rule-based VIX relief gate for REENTER

Added (additive, opt-in, default off) to
`scripts/evaluate/evaluate_a2118_decision_focused_action_shadow.py`:

- `_vix_relief_signal(index, vix_close, lookback_days=20, relief_ratio=0.85)`:
  boolean signal, True when yesterday's (T-1, no same-day lookahead) VIX
  close is below `relief_ratio` (default 0.85) of its own trailing
  `lookback_days`-day peak.
- `_load_vix_close(db_path)`: pulls raw `^VIX` close from
  `external_market_ohlcv`.
- `_select_actions_stateful(..., relief_signal=None)`: when the position is
  below the A21.18 target AND `relief_signal` is True that day (and the
  action-allowed gate passes), REENTER is **forced unconditionally** --
  bypassing `edge_threshold` and the `selective_reliability` filter
  entirely, since this is a rule-based gate, not a learned-regret
  comparison. Recorded per-decision as a new `relief_triggered` field.
- CLI: `--relief-gate`, `--relief-lookback-days` (default 20),
  `--relief-ratio` (default 0.85). Only affects `--stateful-actions` runs;
  fully backward compatible (`relief_signal=None` preserves prior behavior
  exactly).
- 4 new tests in `tests/test_evaluate_a2118_decision_focused_action_shadow.py`:
  the VIX-signal's T-1/no-lookahead behavior, the forced-REENTER override
  itself (against a regret model that would never pick REENTER on its own),
  a no-op check when the position isn't below target, and that
  `action_allowed=False` still blocks the forced REENTER. `pytest tests/ -k
  "decision_focused_action_shadow"`: 15/15 passing (11 prior + 4 new).
  `pytest tests/ -k "dfl or daily_pipeline"`: 43/43 passing (unaffected).

**Real rerun**, identical 7-window config to the production DFL main run
(`--stateful-actions --require-panel-signal --min-train-days 60
--edge-threshold 0.0005 --reenter-edge-threshold -0.0005 --regret-clip 0.02
--adjustment-fraction 0.75 --turnover-cap 0.05`, plus `--relief-gate` with
defaults):

```
window            base ΔSharpe  relief ΔSharpe  base ΔFinal  relief ΔFinal  base CAP10  relief CAP10  relief REENTER
covid_2020            -0.1626        -0.1045      -58,068        -32,441         14           10             41
inflation_2022         0.0000         0.0000            0              0          0            0              0
live_2024_2026         0.0001        -0.0032     -170,903       -161,133          8            4             45
active_2025_2026       0.0041        -0.0051      -43,605        -19,747          2            1             13
2017_bull              0.0000         0.0000            0              0          0            0              0
2018_correction        0.0660         0.0018       12,819            628         15            4             36
2019_recovery          0.0983         0.1209      -29,777         -3,115          7            7             32
```

**Honest verdict: directionally real, but not a clean win.** Effects:

- covid_2020's loss shrinks materially (Sharpe -0.163 -> -0.105, dollar loss
  -58k -> -32k) -- REENTER now fires 41 times (vs 0 before), pulling
  exposure back toward target faster during the V-shaped rebound. Still a
  net loss, not fixed.
- Both tuning windows (`live_2024_2026`, `active_2025_2026`) shrink their
  dollar losses too, but their Sharpe deltas turn slightly *negative*
  (previously ~flat/positive).
- **2019_recovery genuinely improves** on both axes (Sharpe +0.098 ->
  +0.121, dollar loss -29.8k -> -3.1k).
- **2018_correction -- the one previously clean win -- is nearly wiped
  out** (Sharpe +0.066 -> +0.0018, dollar gain +12,819 -> +628). The
  simple VIX-only relief rule apparently fires during 2018's correction
  too (VIX likely had temporary retracements mid-correction that don't
  represent genuine "all clear"), forcing premature re-entry that gives
  back most of the previously-earned edge.
- **Triple-pass count is unchanged: 3/7 in both configurations** (same
  three windows: `inflation_2022`, `2017_bull`, `2018_correction` -- the
  first two trivially, since both have 0 fires either way). The relief
  gate does not flip any window from fail to pass, and turns the one real
  pass into a razor-thin one.

**Conclusion**: the root cause (REENTER structurally never fires) is real
and now demonstrated to matter -- a working relief gate measurably changes
behavior and shrinks the worst-case 2020 loss. But a **VIX-only** relief
condition is too blunt: it correctly identifies genuine crisis-easing
(2020, 2019) but also fires on temporary calm spells inside an ongoing
correction (2018), which is exactly the failure mode arXiv:2607.06117's
own multi-signal design (VIX + rate + credit relief, not any single
indicator) exists to avoid. **Not promoted, not adopted as a default.**
The natural next step, if pursued, is a stricter or multi-signal relief
condition (e.g. requiring VIX relief *and* a minimum number of consecutive
calm days, or combining with the credit-stress (HYG-SHY) signal already
explored in A21.19 -- see
[[project_a2119_credit_stress_hyg_shy_20260725]]) rather than treating this
single-signal prototype as validated.

**Not done**: no multi-signal (credit/rate) relief variant was built or
tested; the `relief_ratio`/`lookback_days` defaults (0.85/20) were not
swept or tuned (deliberately -- to avoid the exact fixed-window
multi-round-tuning-without-OOS-validation pattern already flagged as
overfitting risk in [[feedback_overfitting_fixed_window_tuning]]); the
user's original relative-return-target/two-action-only module proposal was
not built, pending this evidence.

### H4. Gap found in the H3 prototype: no turnover guard, and a fix

Asked "少了什麼?" (what's missing) after H3. Re-examined the H3 prototype's
own decision log (`non_keep_decisions` for `covid_2020`) and found relief-
triggered REENTER fires on **nearly every single trading day** for as long
as the relief signal and below-target condition both hold (e.g.
2020-06-04 through 2020-06-29, almost daily) -- because each REENTER step
only walks `turnover_cap`-limited fraction of the way back, a full walk-back
takes many days, and H3 had no guard against re-forcing it every one of
those days. This is the exact "high turnover" failure mode the user
explicitly warned about when proposing this whole investigation (citing it
as arXiv:2607.06117's own main weakness) -- H3's prototype reproduced it
rather than avoiding it. Confirmed via `rebalance_count`: roughly
2.7-3.8x baseline across every window with any CAP10/REENTER activity
(e.g. `live_2024_2026`: 12 -> 46; `covid_2020`: 18 -> 49).

**Fix**: added `relief_min_holding_days` (CLI: `--relief-min-holding-days`,
default 0 = old H3 behavior) to `_select_actions_stateful()` -- a cooldown,
in trading days, enforced between consecutive relief-triggered REENTER
steps. While in cooldown, the day falls through to the normal
regret-argmax decision (so CAP10 can still fire if genuinely warranted)
instead of being forced. One new test
(`test_relief_gate_min_holding_days_suppresses_consecutive_forced_reenters`)
confirms the cooldown blocks a second forced REENTER within the window and
allows it again once the cooldown elapses. `pytest tests/ -k
"decision_focused_action_shadow or dfl or daily_pipeline"`: 59/59 passing
(16 in this file + 43 unaffected elsewhere).

**Reran the same 7 windows at three cooldown settings** (0 = H3's original,
5, 10 trading days):

```
window            dSharpe: base / h0 / h5 / h10        rebalance_count: base / h0 / h5 / h10
covid_2020          -0.163 / -0.105 / -0.114 / -0.128      18 / 49 / 34 / 27
inflation_2022        0.0  /   0.0  /   0.0  /   0.0        3 /  3 /  3 /  3
live_2024_2026       0.0001/ -0.003 / -0.012 / -0.007      12 / 46 / 32 / 33
active_2025_2026     0.004 / -0.005 / -0.007 / -0.001       4 / 13 / 13 / 13
2017_bull              0.0 /   0.0  /   0.0  /   0.0        3 /  3 /  3 /  3
2018_correction      0.066 /  0.002 /  0.047 /  0.050      16 / 37 / 27 / 25
2019_recovery        0.098 /  0.121 /  0.108 /  0.114       8 / 36 / 30 / 22
```

**Reading**: the cooldown does what it's meant to -- turnover drops
meaningfully as the holding period lengthens (covid_2020: 49 -> 34 -> 27
rebalances), and **2018_correction's previously-destroyed edge is
substantially recovered** (Sharpe delta 0.002 -> 0.047 -> 0.050, versus
baseline's 0.066) -- confirming the H3 diagnosis that uncapped daily
re-forcing, not the relief concept itself, was what wrecked 2018.
covid_2020's improvement shrinks somewhat as the cooldown lengthens (less
aggressive re-entry -> less benefit during the fastest rebound), a real,
expected trade-off. **Turnover is reduced but not eliminated** -- even at a
10-day cooldown, rebalance_count is still roughly 1.5-2.8x the no-relief
baseline in every window with any activity; a genuine no-trade-band or an
explicit annual-turnover budget (as the user originally requested) would
bound this further and was not built this round.

**New finding, not previously flagged**: `live_2024_2026` and
`active_2025_2026` (the two windows that include the current, live regime)
are worse than baseline on Sharpe **at every cooldown setting tested**
(0/5/10), unlike `covid_2020`/`2019_recovery` where the relief mechanism
clearly helps and `2018_correction` where the cooldown recovers most of the
edge. This is unexplained -- not chased down this round -- and is a
concrete reason for caution about the live/current-regime applicability of
this whole relief-gate direction, separate from the crisis-window results.

**Still not promoted, still not adopted as a default.** Triple-pass count
is unchanged at 3/7 across every configuration tested (base, h0, h5, h10) --
none of these variants flip any window's pass/fail outcome.

### H5. Root-causing and fixing the `live_2024_2026`/`active_2025_2026` regression

Asked to investigate H4's unexplained finding (both windows worse than
baseline at every cooldown setting). Inspected `non_keep_decisions` for
`live_2024_2026` directly, printing `base_00631l_weight - final_00631l_weight`
(the actual 00631L weight gap) for every relief-triggered event. Found a
clean pattern: a real CAP10-driven de-risking cycle in Jan-Feb 2025 (gaps
0.03-0.08, legitimate), followed by REENTER events gradually closing that
gap through mid-2025 -- but from **2025-08-22 through 2026-07-02, REENTER
kept firing every 2-6 weeks against a gap that was already ~0.0000-0.0016**
(i.e. the position was already essentially at the A21.18 target). Root
cause: `is_below_a2118`'s epsilon (`1e-10`) treats any sub-basis-point
residual as "below target," and ordinary VIX noise in a calm market
satisfies the relief condition often enough to keep firing effectively
no-op rebalances -- each one still charged transaction costs for zero
economic benefit. `active_2025_2026` showed the same pattern even more
starkly: only **1** real CAP10 fire the entire window, but **13** REENTER
fires, almost all against a near-zero residual.

**Fix**: added `relief_min_gap` (CLI: `--relief-min-gap`, default 0.0 = H3/H4
behavior) -- the relief gate now additionally requires the 00631L weight
gap to clear this minimum before firing at all. One new test
(`test_relief_gate_min_gap_suppresses_no_op_reenter_against_a_tiny_residual`)
confirms a tiny residual gap is suppressed at `relief_min_gap=0.01` and
still fires at `relief_min_gap=0.0`. `pytest tests/ -k
"decision_focused_action_shadow or dfl or daily_pipeline"`: 60/60 passing
(17 in this file + 43 elsewhere).

**Reran the same 7 windows** at `--relief-min-holding-days 10
--relief-min-gap 0.01` (combining both fixes) versus the h10-only
(cooldown alone) result and the no-relief baseline:

```
window            metric      base        h10 (cooldown only)   h10+gap1%
covid_2020        dSharpe    -0.163            -0.128              -0.113
                  dFinal     -58,068           -44,080             -38,063
                  rebal          18                27                  23
live_2024_2026    dSharpe     0.0001            -0.0065             -0.0119
                  dFinal    -170,903          -278,638            -169,681
                  rebal          12                33                  18
active_2025_2026  dSharpe     0.0041            -0.0007             -0.0007
                  dFinal     -43,605          -133,256             -15,596
                  rebal           4                13                   5
2018_correction   dSharpe     0.066             0.050               0.050
                  dFinal      12,819            9,584               9,528
                  rebal          16                25                  24
2019_recovery     dSharpe     0.098             0.114               0.132
                  dFinal     -29,777           -11,599              -4,315
                  rebal           8                22                  14
```

**The gap fix resolves H4's regression almost completely.** Rebalance
counts in `live_2024_2026`/`active_2025_2026` drop back close to baseline
(18 vs 12, and 5 vs 4, respectively -- down from 33/13 with cooldown
alone). `active_2025_2026`'s dollar outcome actually improves *past*
baseline (-15,596 vs baseline's own -43,605); `live_2024_2026`'s nearly
matches baseline (-169,681 vs -170,903) though its Sharpe delta is still
slightly negative (-0.0119). **2019_recovery becomes the best result seen
in any configuration** (Sharpe +0.132, dollar loss shrunk from -29,777 to
-4,315). `2018_correction` and `covid_2020` are essentially unaffected by
the gap threshold (their real gaps were always well above 1%, so the
fix targets exactly the no-op-rebalance failure mode without touching
genuine crisis cycles). Triple-pass count remains 3/7.

**Status after H3-H5: three composable, tested, opt-in fixes now exist**
(`relief_signal`/VIX rule, `relief_min_holding_days` cooldown,
`relief_min_gap` minimum-gap) that together turn a diagnosed-but-broken
mechanism (REENTER never fires) into one that measurably helps in 3 of 5
non-trivial windows (`covid_2020`, `2019_recovery` clearly;
`active_2025_2026`/`live_2024_2026` roughly neutral vs baseline) while
recovering most (not all) of `2018_correction`'s previously-clean edge.
**Still not promoted** -- this remains a VIX-only single-signal prototype;
the residual `2018_correction` gap (0.050 vs baseline's 0.066) was
hypothesized as the ceiling of a VIX-only relief condition, with a
multi-signal (VIX + credit_stress) version considered as a natural next
step. **H6 below overturns that plan** -- see H6 before pursuing it.

### H6. Genuine out-of-sample check (2021 backfill) -- the relief-gate direction does not generalize

H1-H5 all iterated on the same 7 historical windows (`covid_2020`,
`inflation_2022`, `live_2024_2026`, `active_2025_2026`, `2017_bull`,
`2018_correction`, `2019_recovery`). By H5 that is four rounds of tuning
against identical windows (VIX-only gate -> cooldown -> min-gap -> combined),
which crosses the threshold this project's own prior finding
([[feedback_overfitting_fixed_window_tuning]]: "more than 2-3 rounds of
tuning against the same window(s) requires an OOS check before claiming
improvement") flags as an overfitting risk. Before doing a fifth round
(e.g. adding a credit-stress signal), got a genuinely fresh OOS sample
instead.

**Built a real 2021 NCF backfill** -- 2021 has never been used anywhere in
this DFL research line (only 2017-2019, 2020, 2022-partial, 2025-2026 exist
as backfilled panels before today). Ran the same command family used for
every prior backfill in this project
(`GROUP_A_PLUS_FABLE_COMBINATION_OPPORTUNITIES_HANDOFF_20260716.md`'s 2020
backfill):

```bash
python3 scripts/misc/ncf_00631l.py --train-start 2015-06-01 \
    --val-start 2021-01-01 --val-end 2021-12-31 --full-panel \
    --val-predictions-output results/ncf_00631l_panel_backfill_2021_20260726.csv \
    --output results/ncf_00631l_2021_backfill_20260726.json
```

~real ML training (ran in background, completed same session). Output: 243
rows, 2021-01-04 to 2021-12-30, same schema as the other backfills.

**Result, no-relief-gate baseline vs the H5 combined fix
(`--relief-min-holding-days 10 --relief-min-gap 0.01`), identical flags to
every other window in this document**:

```
                        no relief-gate      relief-gate (H5 combined)
delta_sharpe_ratio          +0.2016              +0.1586
delta_max_drawdown          +0.0264              +0.0196
delta_final_value          +26,559              +20,608
rebalance_count                 51                    60
transaction_cost           19,896                21,776
action_counts        KEEP=202,CAP10=41    KEEP=193,CAP10=40,REENTER=10
triple-pass                    yes                    yes
```

**Both configurations triple-pass on this fresh year -- but the relief
gate makes the result *worse*, not better, than plain CAP10 alone.**
Sharpe delta drops from +0.2016 to +0.1586, dollar gain from +26,559 to
+20,608, MDD improvement shrinks too, and turnover/transaction cost both
increase (10 REENTER events fire, none of which existed in the no-relief
baseline since REENTER never fires without the gate). This is the exact
opposite of the pattern seen in `covid_2020`/`2019_recovery` (where the
relief gate clearly helped) -- in 2021, whatever caused CAP10 to work well
here (2021 was a choppier, more range-bound year than 2020's clean
V-shaped crash-recovery) apparently didn't need or benefit from
VIX-relief-driven early re-entry; forcing it back in early cost some of
the edge CAP10 alone had already captured.

**Conclusion: the relief-gate direction (H3-H5) does not clearly
generalize beyond the 7 windows it was diagnosed and iterated against.**
On the one genuinely fresh sample built this session, plain CAP10 (the
pre-existing, never-promoted mechanism, doing nothing about REENTER at
all) outperforms every relief-gate variant tested. This does not mean the
root-cause diagnosis (H2: REENTER structurally never fires) was wrong, or
that the three fixes (H3 VIX rule, H4 cooldown, H5 min-gap) don't do
exactly what they were built to do -- they demonstrably do, verified
against real data at every step. It means the *net effect on realized
performance* of forcing early re-entry via a VIX-only relief condition is
regime-dependent in a way the 7 in-sample windows did not reveal, and the
weight of evidence after this OOS check no longer favors continuing to
iterate on this specific mechanism (e.g. adding a credit-stress signal as
a plausible sixth round of tuning against the same fundamental approach).

**Recommendation communicated to the user and accepted: stop iterating on
this line.** Not promoted, not adopted as a default, and further tuning
(multi-signal relief, parameter sweeps) is not recommended without first
expanding the OOS sample set further (e.g. a genuine 2023 backfill) --
one fresh year is suggestive, not conclusive, but is enough to withdraw
confidence in the direction rather than invest further tuning effort in it.

## What was fixed today

- `scripts/evaluate/evaluate_ncf_h20_walkforward_bias_correction.py`:
  added the missing `sys.path.insert(0, str(PROJECT_ROOT))` guard so the
  script can run at all. No other logic changed.
- `scripts/evaluate/evaluate_ncf_panel_drift.py`: added optional
  `--window-start` (Part E) and `--outcome-aware` (Part F). Both additive,
  both default to prior behavior, neither changes output for any existing
  caller unless explicitly passed.
- `tests/test_evaluate_ncf_panel_drift.py`: four new tests total (2 for
  `--window-start`, 2 for `--outcome-aware`).
- `scripts/evaluate/evaluate_a2118_decision_focused_action_shadow.py`
  (Part H): added optional `--relief-gate`/`--relief-lookback-days`/
  `--relief-ratio`/`--relief-min-holding-days`, `_vix_relief_signal()`,
  `_load_vix_close()`, and `relief_signal`/`relief_min_holding_days`
  parameters to `_select_actions_stateful()`. Additive, default off, does
  not change any existing caller's output (including the live
  `dfl_shadow_refresh_*` pipeline steps from Part(Thread) 6, which don't
  pass `--relief-gate`).
- `tests/test_evaluate_a2118_decision_focused_action_shadow.py`: six new
  tests for the relief gate (Part H: 4 for the base gate, 1 for the
  min-holding-days cooldown added in H4, 1 for the min-gap fix added in H5).

## What was NOT done / open questions

- The panel-drift governance methodology gained two new, tested, opt-in
  capabilities (Parts E/F: `--window-start`, `--outcome-aware`) that
  directly address the C4 deadlock and the Part D blind spot -- but
  **neither is wired into the actual production governance scripts**
  (`build_group_a_plus_external_sensitivity_observation_log.py`,
  `build_ncf_panel_external_feature_sensitivity_governance.py`) or the
  daily pipeline's command construction. Deciding to make either the
  production default (window length, whether to apply retroactively to
  the existing 07-22/07-25 log entries, whether to combine both flags) is
  left to the user.
- Did not check whether the other flagged high-exceed months (2026-02,
  2026-04, 2026-06 in the TabNet-driven triage, and whatever months drive
  the external-feature sensitivity numbers beyond the two anchor dates)
  follow the same "real event, not noise" pattern -- only the two specific
  `max_abs_delta_date` anchors were checked. If someone wants to fully
  clear this gate's finding as "not a real problem," the other exceed
  months would need the same treatment.
- Did not attempt to reconcile this with Thread 6 Part B (`run_a2118()`
  drift 07-16 -> 07-26, from `GROUP_A_PLUS_DFL_ADVISORY_STALE_INPUT_FIX_20260726.md`)
  -- these are two independent instances of "the pipeline's outputs on a
  fixed historical date range are not stable across regenerations," but
  one is in the simulation engine and one is in the NCF panel/model set;
  no evidence either causes the other.
- The late-bull-hedge trigger-count question (Part B) itself is not
  resolved to a single "correct" number -- both 0 (07-23, panel `20260722`)
  and 3 (07-26, panel `20260725`) are artifacts of which panel snapshot was
  used, and the panel itself is provably unstable across regenerations
  (TabNet in/out, external-feature sensitivity). [[project_a2118_ncf_hedge_dormancy_root_cause_20260723]]'s
  core conclusion (a2118's Sharpe improvement is 100% from the 2020 fix,
  not NCF late-bull-hedge) is not invalidated by this -- that was verified
  byte-identically against a fixed panel snapshot -- but its "0 triggers"
  framing should now be read as "0 triggers as of that specific panel
  snapshot," not as a stable structural property of the 2025-2026 regime.

## Reproduction commands

```bash
# Calibration diagnostic (Part A2)
python3 scripts/evaluate/evaluate_ncf_h20_utility_weighted_calibration.py \
    --panel results/ncf_00631l_panel_latest_20260725.csv

# Walk-forward bias-correction backtest (Part A3; requires the sys.path fix above)
python3 scripts/evaluate/evaluate_ncf_h20_walkforward_bias_correction.py \
    --panel results/ncf_00631l_panel_latest_20260725.csv

# Trailing-window drift audit (Part E)
python3 scripts/evaluate/evaluate_ncf_panel_drift.py \
    --baseline-panel results/ncf_00631l_panel_latest_20260725_no_external.csv \
    --candidate-panel results/ncf_00631l_panel_latest_20260725.csv \
    --columns h20_prob_up confidence ensemble_prob_up \
    --window-start 2026-01-26 \
    --output /tmp/no_external_vs_external_trailing180.json

# Outcome-aware drift audit (Part F)
python3 scripts/evaluate/evaluate_ncf_panel_drift.py \
    --baseline-panel results/ncf_00631l_panel_latest_20260725_no_external.csv \
    --candidate-panel results/ncf_00631l_panel_latest_20260725.csv \
    --columns h20_prob_up confidence ensemble_prob_up \
    --outcome-aware \
    --output /tmp/no_external_vs_external_outcome_aware.json

# Raw market data check for the 2025-03-05 / 2025-04-02 / 2026-03 anchor dates (Parts D, E)
python3 -c "
import duckdb
con = duckdb.connect('FinRL/data/stock_data.db', read_only=True)
print(con.execute(\"SELECT dt, ticker, open, high, low, close FROM external_market_ohlcv \
    WHERE ticker IN ('^VIX','QQQ') AND dt BETWEEN '2025-02-24' AND '2025-04-10' \
    ORDER BY ticker, dt\").fetchdf().to_string())
"

# Raw institutional flow check for the 2025-01-15 anchor date (Part G)
python3 -c "
import duckdb
con = duckdb.connect('FinRL/data/stock_data.db', read_only=True)
print(con.execute(\"SELECT dt, foreign_net_buy, institutional_total_net_buy \
    FROM institutional_data WHERE ticker='0050.TW' \
    AND dt BETWEEN '2025-01-06' AND '2025-01-17' ORDER BY dt\").fetchdf().to_string())
"

# Relevant tests
python3 -m pytest tests/test_evaluate_ncf_panel_drift.py -q
python3 -m pytest tests/ -k "panel_drift or evaluate_ncf_panel_drift or daily_pipeline" -q
```

## Files referenced

Modified this session:
- `scripts/evaluate/evaluate_ncf_h20_walkforward_bias_correction.py` --
  one-line `sys.path` fix (Part A1).
- `scripts/evaluate/evaluate_ncf_panel_drift.py` -- added `--window-start`
  (Part E) and `--outcome-aware` (Part F), both additive/opt-in.
- `tests/test_evaluate_ncf_panel_drift.py` -- 4 new tests.
- `scripts/evaluate/evaluate_a2118_decision_focused_action_shadow.py` --
  added `--relief-gate`/`--relief-lookback-days`/`--relief-ratio` (Part H3),
  `--relief-min-holding-days` (Part H4), `--relief-min-gap` (Part H5), all
  additive/opt-in/off by default.
- `tests/test_evaluate_a2118_decision_focused_action_shadow.py` -- 6 new
  tests (Part H3-H5).
- `results/ncf_00631l_panel_backfill_2021_20260726.csv` (243 rows,
  2021-01-04 to 2021-12-30) / `ncf_00631l_2021_backfill_20260726.json` --
  new, genuine NCF backfill built for the Part H6 OOS check (~20 min of
  real ML training, same command family as the existing 2017-2019/2020/2022
  backfills).

Pre-existing, read/analyzed but not modified:
- `results/ncf_panel_drift_diagnosis_20260725.json`
- `results/ncf_panel_drift_remediation_plan_20260725.json`
- `results/ncf_panel_drift_model_set_isolation_report_20260725.json`
- `results/ncf_panel_external_feature_sensitivity_governance_20260725.json`
- `results/ncf_panel_drift_no_external_vs_external_20260722.json` /
  `_20260725.json`
- `report/group_a_plus/latest/external_sensitivity_observation_log.json`
- `report/group_a_plus/panel_drift_triage/history/panel_drift_triage_20260725.json`
  / `_20260726.json`
- `report/group_a_plus/panel_drift_resolution_progress/history/panel_drift_resolution_progress_20260726.json`
- `scripts/evaluate/build_group_a_plus_external_sensitivity_observation_log.py`
- `scripts/evaluate/build_ncf_panel_external_feature_sensitivity_governance.py`
- `scripts/misc/ncf_00631l.py` (`EXT_FEATURES` list, lines ~156-199)
- `results/ncf_00631l_panel_latest_20260725.csv` /
  `_20260725_no_external.csv` / `_20260722.csv` / `_20260716.csv`
- `FinRL/data/stock_data.db` tables `external_market_ohlcv`,
  `institutional_data` (raw market/flow verification, Parts D and G)
