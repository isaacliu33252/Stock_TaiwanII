# GroupA+ Fable combination-opportunities session - 2026-07-16

## One-line conclusion

Ran a Fable-style audit asking "given everything added recently plus every
past experiment, is there a combination that clears a bar a single signal
couldn't." Produced a ranked top-10 list, then worked through all 10 items
one at a time. Net result: two real, still-open positive leads (#1 override
eligibility union, #5 crash-detector coverage gap), five infrastructure/bug
fixes that close real drift/staleness risks (#2, #4, #6, #7, #8), one
genuinely important negative finding that downgrades a previously-"passing"
research candidate (#9: A21.18 DFL's covid_2020 window was never actually
tested), one line closed on data-availability grounds (#3, redirected to
live logging), and one line closed because the evidence contradicts the
hypothesis (#10). Nothing here was promoted to production; every new
artifact is `research_only: true` / `production_effect: "none"`.

Also ran two operational tasks at the end of the session (not part of the
Fable review): a manual full daily-pipeline run with today's (2026-07-16)
close data, and a one-off comparison of the latest strategy (a2118) vs. the
frozen `golden1_0531` reference for 2026-07-17.

## How this session started

User asked for a Fable-style review of the whole `group_a_plus` directory,
including everything added in roughly the last week (trough_nowcast, a2120
LETF compounding regime, GARCH specialist routing, cross-market directed
graph, network-volatility spillover, the DFL decision-focused-learning line,
crash_risk_alert, a2121-a2129 shadow runners) cross-referenced against the
user's memory of every closed/promoted experiment going back weeks. A
sub-agent (model: fable) did the actual directory audit and returned a
ranked top-10 list of combination opportunities. This document is the
record of working through that list, one item at a time, as directed ("一步
一步來").

---

## #1 - "Re-entry guard-release" combination (trough_nowcast + a2120 compounding regime)

**Finding.** The vol-gate override for trough re-entry
(`scripts/evaluate/evaluate_group_a_plus_trough_nowcast_vol_gate_override_shadow.py`)
had eligibility = `trough_state == PARTIAL_REENTRY` only, which produced just
2 eligible events across the entire backtest history -- too few to ever
promote. A21.20's compounding-regime `TREND_PERSISTENT` state is an
independent signal (serial-return-dependence based, not trough
microstructure) that could be unioned in.

Fable's original hypothesis named a 4-way union (trough + compounding +
cross-market-graph REENTER + DFL REENTER). **Deliberately implemented only a
2-way union** (trough + compounding): cross-market graph's own evaluator
documents its REENTER side is unstable (`evaluate_cross_market_directed_graph_shadow.py`'s
`promotion_assessment.recommended_use = NO_ADD_ONLY_SHADOW_FILTER`, explicitly
"REENTER is unstable and should not drive re-entry"), and DFL's own
handoffs note "no effective REENTER case demonstrated." Folding either in
would have laundered an already-rejected signal into a new eligibility gate.

**What was done.**
- Added `ELIGIBILITY_MODES = ("trough_partial_reentry_only", "trough_or_compounding_trend_persistent")`
  and a `_build_compounding_regime_series()` helper (using the same
  `TUNED_COMPOUNDING_THRESHOLDS` as `run_a2120_daily_shadow_pipeline.py`'s
  daily shadow, for consistency with the live signal) to
  `evaluate_group_a_plus_trough_nowcast_vol_gate_override_shadow.py`.
  `simulate_override_policy()` and `evaluate_window()` now accept
  `eligibility_mode` and `compounding_regime`; events log a `trigger_source`
  (`"trough"` / `"compounding_trend_persistent"` / `"trough_and_compounding"`).
- Ran the eligibility union across the 4 existing backtest windows
  (`active_2025_2026`, `covid_2020`, `inflation_2022`, `2018_correction`).
  Result (`small_override_50pct` policy): eligible days 2 -> 20 total; the
  true out-of-sample window (`2018_correction`) went from **0 to 3** events,
  all three individually positive (forward 5d returns +4.4%/+4.3%/+3.6% on
  2018-10-30/11-23/12-06). Saved:
  `results/group_a_plus_trough_nowcast_vol_gate_override_shadow_eligibility_union_20260716.json`.
- Ran a follow-up sweep over `override_fraction in {25%,50%,100%}` x
  `confirmation_mode in {none, second_partial, no_lower_low_3d,
  second_or_no_lower_low_3d}` (added `full_override_100pct = 1.0` to
  `OVERRIDE_POLICIES`). Best-supported combination: `override_fraction=0.50,
  confirmation_mode="none"` -- keeps all 3 OOS events (the `no_lower_low_3d`
  filter cuts that to 1, and `second_partial` cuts to 0 because it only
  checks for a second consecutive `PARTIAL_REENTRY` day, with no analogous
  check for the compounding leg). 100% fraction has the best raw numbers but
  has never seen a negative event at full size, so it's not yet trustworthy.
  Saved: `results/group_a_plus_trough_nowcast_vol_gate_override_shadow_fraction_confirmation_sweep_20260716.json`.
- Built a live shadow-logging mechanism so the OOS sample grows at live
  speed instead of waiting on more historical proxy data: new module
  `group_a_plus/integrations/trough_override_eligibility_shadow.py`
  (`build_shadow_log_row`, `append_shadow_log_row` -- both reuse
  `simulate_override_policy` directly, zero reimplemented eligibility logic)
  and runner `scripts/run/build_group_a_plus_trough_override_eligibility_shadow_log.py`
  (recomputes a 90-day a2118 window ending "latest", logs today's
  eligibility state). Wired into `run_ncf_daily_pipeline.py` as a
  best-effort step (`trough_override_eligibility_shadow_log`). Log:
  `results/group_a_plus_trough_override_eligibility_shadow_log.jsonl`.

**Status: still open, not promoted.** 3 OOS events is real signal but not
enough to promote. Next milestone: let the live shadow log accumulate; the
50%/none configuration is the one to watch.

**Tests:** `tests/test_evaluate_group_a_plus_trough_nowcast_vol_gate_override_shadow.py`
(6 -> 10 tests), `tests/test_group_a_plus_trough_override_eligibility_shadow.py`
(4 new tests).

---

## #2 - a2120/DFL frozen-input and unscheduled-pipeline bugs

**Finding A.** `scripts/run/run_a2120_daily_shadow_pipeline.py` (the A21.20
LETF-compounding shadow pipeline) was never scheduled anywhere -- it existed
but nothing called it, so `report/group_a_plus/latest/a2120_letf_compounding_shadow.json`
was frozen at whatever date someone last ran it by hand.

**Finding B.** `scripts/run/build_a2118_dfl_advisory.py` matches
`live_signal`'s `actual_data_date` against dates inside a **frozen** DFL
backtest result file (default:
`results/a2118_decision_focused_action_shadow_fixed_7win_20260714_rerun.json`).
Since that file is never re-run, and its live-window (`tuning_window`
bucket) coverage stops at whatever date it was generated, `matched_decision_count`
becomes structurally 0 forever once the gap opens -- the advisory step keeps
"running" every day but can never again report a non-KEEP action. This looks
identical to ordinary sparse-output KEEP behavior, so nobody would notice.

**What was done.**
- Added `"a2120_shadow_pipeline"` to `run_ncf_daily_pipeline.py`'s
  `BEST_EFFORT_STEP_NAMES` and `build_commands()` (runs
  `run_a2120_daily_shadow_pipeline.py --date-stamp {stamp}`, positioned right
  after `compounding_regime`). Confirmed cheap (a few seconds) and produces a
  correct fresh state on first live run: `TREND_PERSISTENT` regime,
  `FAST_REENTER_CANDIDATE` raw action, blocked by the 50% turnover hard
  guard.
- Added a new check to `scripts/misc/check_group_a_plus_daily_status.py`:
  `_dfl_frozen_input_staleness()` reads the DFL advisory's `input` path,
  finds the max date across its non-`out_of_sample` (`tuning_window`)
  buckets' `recent_decisions`, and reports the calendar-day gap vs.
  `check_date`. New check `dfl_advisory_frozen_input_staleness`: `warn` when
  the gap exceeds `--max-dfl-frozen-staleness-days` (default 14; never
  `block`, since this is advisory-only). Surfaced in
  `report["group_a_plus"]["dfl_frozen_input_staleness"]` too. Verified
  against live data: 3 days behind at time of writing (under threshold, so
  `ok`, but now visible and will flip to `warn` once it crosses 14 days
  without a re-run).

**Status: fixed and live.** Both gaps are closed; the DFL frozen-input
problem itself (needing a periodic re-run of the underlying backtest) is not
fixed -- only made visible.

**Tests:** `tests/test_run_ncf_daily_pipeline.py` (+3 assertions),
`tests/test_check_group_a_plus_daily_status.py` (6 -> 9 tests).

---

## #3 - GNHAR/spillover-gated recovery boost five-crisis validation

**Finding.** The spillover-gated recovery boost
(`evaluate_group_a_plus_recovery_boost_spillover_gate.py`) has never had its
gate actually fire in any of its 7 tested windows
(`spillover_blocked_recovery_days == 0` everywhere) -- not a bug, but
because GroupA+'s `group_a_plus_recovery` regime is rare (32 days across all
7 windows, 26 of them in 2017) and none of those recovery episodes happened
to coincide with a systemic spillover spike. Investigated whether the true
target scenario (a 2011-style long, weak recovery that turns into a false
dawn -- the actual failure mode that got a2127 rejected) could be tested
against the five-crisis proxy folds
(`scripts/misc/backtest_group_a_plus_latest_vs_golden1_0531_five_crises_20260706.py`).
**It cannot**: all five crisis fold price CSVs (including the one labeled
"real ETF OHLCV" for 2015) contain only 4 tickers' **close** prices, no
open/high/low, and the spillover network needs full OHLC across 7 tickers
(3 of which -- 00646/00713/00878 -- did not exist as instruments in
2008/2011 at all). This is a hard data-structure wall, not something more
engineering effort can route around cheaply.

**What was done (redirected).** Rather than force a degraded close-only
proxy version (low expected value given this repo's repeated prior
experience that price-only substitutes can't distinguish crash types), built
a live shadow-logging mechanism instead, matching the "accumulate real
samples going forward" pattern used everywhere else this session:
- New module `group_a_plus/integrations/recovery_boost_spillover_gate_shadow.py`
  (`build_shadow_log_row`: computes recovery-regime age via
  `_recovery_age()`, layers the spillover gate via existing
  `latest_spillover_snapshot`/`spillover_recovery_boost_gate` from
  `network_volatility_spillover_shadow.py`; `boost_reason` explains which of
  3 layers blocked -- `not_in_recovery_regime` / `recovery_age_exceeds_max` /
  spillover-specific).
- Runner `scripts/run/build_group_a_plus_recovery_boost_spillover_gate_shadow_log.py`
  (recomputes a 90-day a2118 window + 600-day OHLCV window ending "latest").
  Wired into `run_ncf_daily_pipeline.py` as best-effort step
  `recovery_boost_spillover_gate_shadow_log`.

**Status: closed as originally scoped, redirected to live logging.** Live
data as of 2026-07-15: `execution_regime=golden1` (not in recovery), so
`boost_allowed=False, reason=not_in_recovery_regime` -- correctly inactive.

**Tests:** `tests/test_group_a_plus_recovery_boost_spillover_gate_shadow.py` (7 tests, new).

---

## #4 - governance catalog two generations behind

**Finding.** `group_a_plus/governance/catalog.py`'s `active` field was
hardcoded to `"a213_runner"` (superseded by a2118 long ago), and its runner
list stopped at `a216_runner` -- 18 of the 22 entries in
`group_a_plus/governance/latest.py`'s `SUPPORTED_STRATEGIES` (the actual
live-dispatch registry read from `strategy.json`) were missing:
`a217, a2111-a2115, a2118-a2129`. Two independently-maintained lists had
silently diverged -- the exact failure mode that let the TSMC/0050 weight
constant drift to three different hardcoded values elsewhere in this repo.

**What was done.**
- `_resolve_active_strategy_id(manifest_path)`: reads the real active
  strategy id from `strategy.json` via `governance.latest.resolve_latest()`,
  falling back to `"a2118_a2111_ncf_late_bull_deleverage"` (today's true
  active id) if the manifest is missing/invalid. `build_catalog()` now takes
  an optional `manifest_path` param (default `DEFAULT_LATEST_STRATEGY`) for
  testability.
- `_supported_strategy_runner_entries(active_strategy_id)`: generates a
  catalog entry per `SUPPORTED_STRATEGIES` item whose module isn't already
  hand-curated (`_LEGACY_COVERED_MODULES = {a207, a213, a214, a215}`, which
  keep their richer legacy templates with root-level scripts). `description`
  is pulled from each runner module's own docstring (zero manual
  copy/typing); `kind` is `"active_strategy"` for whichever entry matches
  the resolved active id, `"shadow_candidate"` otherwise; `module_command_template`
  follows the same `python3 -m {module} --start {start} --end {end}
  --output ... --frame-output ...` pattern as the legacy entries -- verified
  runnable (`python3 -m group_a_plus.runners.a2121 --start 2026-06-01 --end
  2026-07-09 --output ... --frame-output ...` actually ran end-to-end).
- The legacy `a213_runner` entry's `kind` changed from `"active_strategy"`
  (wrong) to `"legacy_superseded"`.
- Runner count: 16 -> 36 (18 new SUPPORTED_STRATEGIES entries), zero
  duplicate ids.

**Status: fixed and self-maintaining.** Any future addition to
`SUPPORTED_STRATEGIES` will now appear in the catalog automatically -- this
class of drift is closed permanently, not just patched for today's snapshot.

**Tests:** `tests/test_group_a_plus_governance_catalog.py` (1 -> 6 tests).

---

## #5 - Crash/de-risk detector overlap coverage matrix

**Finding.** GroupA+ now has 4 blocking pre-trade guards
(`group_a_plus/operations/execution_guard.py`: volatility gate,
tail-conformal, A21.18 extreme-risk warning, compounding-regime
MEAN_REVERTING) and several alert-only detectors (multisource
`crash_risk_alert` 2-of-3, `market_state` crash-like states,
`specialist_router`'s `crash_deleverage` route). The one overlap analysis
that existed (`evaluate_a2118_decision_focused_overlap.py`, DFL vs.
vol-gate vs. extreme-warning) found ~0% overlap. Nobody had checked whether
this pattern holds for the other detector pairs, or whether any alert-only
detector covers days the blocking guards structurally miss.

**What was done.** New script
`scripts/evaluate/evaluate_group_a_plus_crash_detector_overlap.py`: builds 6
detector boolean series (excludes cross-market NO_ADD and tail_conformal --
no saved per-date series for either; regenerating cross-market NO_ADD needs
retraining its walk-forward model) over the shared window covered by the
reusable `results/group_a_plus_runner_latest_20250102_20260702_frame_market_state.csv`
(2025-01-02..2026-07-02, 361 rows). `specialist_router`'s `crash_deleverage`
route is derived directly from that CSV's `tail_risk_score`/`total_risk_score`/
`drawdown`/`fine_market_state` columns, matching `route_specialist`'s
condition exactly (verified by direct code comparison).

**Result** (saved: `results/group_a_plus_crash_detector_overlap_latest.json`):

| detector | type | active days | days active w/ **no** blocking guard active |
|---|---|---:|---:|
| volatility_gate | blocking | 48 | -- |
| extreme_warning_proxy | blocking | 9 | -- |
| compounding_mean_reverting | blocking | 38 | -- |
| crash_risk_alert 2-of-3 | alert-only | 130 | 85 (65%) |
| market_state crash-like | alert-only | 67 | 50 (75%) |
| specialist_router crash_deleverage | alert-only | 23 | 13 (57%) |

Pairwise Jaccard confirms the DFL finding generalizes: `extreme_warning_proxy`
vs. `market_state`/`specialist_router` = 0.000 (zero overlap); most pairs sit
in the 0.01-0.19 range. `market_state` vs. `specialist_router` has the
highest Jaccard (0.343) but that's a structural subset relationship
(specialist_router's crash condition literally includes
`market_state=="crash_risk"`), not a new finding.

**Status: analysis done, no code change yet.** 57-75% of alert-only trigger
days are genuine coverage gaps, not duplicate warnings. Candidate next step
(not done): a rule like "any two independent families active simultaneously
-> escalate to blocking" and backtest its return/drawdown impact.

**Tests:** `tests/test_evaluate_group_a_plus_crash_detector_overlap.py` (4 tests, new).

---

## #6 - Triplicated multisource crash-risk thresholds

**Finding.** The exact same 21 z-score/threshold conditions (TXO
put/call ratios, market-margin forced-repay, SOXX implied-vol skew, etc.)
were hardcoded **three times independently**: inside
`evaluate_00631l_multisource_crash_risk.py`'s own `_stress_veto_fraction`
(the original research definition), again in
`group_a_plus/integrations/trough_nowcast.py`'s capitulation-score
conditions (7 of the 21), and again in
`scripts/run/build_00631l_crash_risk_alert.py`'s `_category_flags` (all 21).
All three currently agree -- but nothing enforced that, and this is the same
failure class that let the TSMC/0050 weight constant silently diverge to
three different values elsewhere.

**What was done.**
- Added `FAMILY_STRESS_CONDITIONS: dict[str, dict[str, tuple[column, comparator, threshold]]]`
  to `evaluate_00631l_multisource_crash_risk.py` as the single source of
  truth, plus `evaluate_family_condition()` (scalar) and
  `family_condition_flags_for_row()` (row-wise dict) helpers.
- `_stress_veto_fraction` refactored to a vectorized `_family_active_series()`
  that reads from `FAMILY_STRESS_CONDITIONS` (kept vectorized for backtest
  performance -- numpy NaN comparisons already evaluate False, matching prior
  behavior exactly).
- `build_00631l_crash_risk_alert.py`'s `_category_flags` shrank from ~60
  hand-written lines to 2 (`family_condition_flags_for_row` per family).
- `trough_nowcast.py`'s 7 relevant `add_cap(...)` calls now call a local
  `shared_condition(family, name)` helper that looks up the threshold from
  `FAMILY_STRESS_CONDITIONS` instead of repeating the literal. The cap-reason
  *strings* logged (e.g. `"foreign_txo_put_call_oi_chg5_z60_ge_1"`) were left
  unchanged from their historical names, decoupled from
  `FAMILY_STRESS_CONDITIONS`'s own key names, so no downstream consumer of
  those reason strings needed to change.

**Status: fixed, zero behavior change verified.** All existing tests for all
3 files passed unmodified after the refactor (15 crash-risk-alert tests, 2
trough-nowcast tests) -- confirms the consolidation didn't alter any
production number, only removed the drift risk.

**Tests:** `tests/test_evaluate_00631l_multisource_crash_risk.py` (4 tests, new).

---

## #7 - Unified shadow-log forward-return join

**Finding.** GroupA+ now has 6 independent daily shadow logs
(`garch_regime_shadow_log.jsonl`, `specialist_routing_shadow_log.jsonl`,
`market_state_shadow_log.jsonl`, `signal_alignment_shadow_log.jsonl`,
`ncf_signal_archive.jsonl`, plus the new logs from #1/#3/#8 this session)
with completely different schemas, but nothing joins them on date against
realized forward returns the way
`evaluate_ncf_blend_live_auc_archive.py` already does for NCF. Several
previously-closed experiments (GNHAR, good/bad volatility, TXO chip
triggers) died from historical sample-size/split-sample instability; these
live logs are accumulating genuine forward-OOS samples every trading day.

**What was done.** New script
`scripts/evaluate/build_group_a_plus_shadow_log_unified_join.py`:
`load_source_frame()` reads any jsonl log, flattens nested dicts up to 2
levels deep with `{source}__{field}` prefixed column names (deeper
structures / lists get JSON-serialized into a single cell),
`ncf_signal_archive` is filtered to `00631L.TW` only (it's keyed by
ticker+date, others by date alone); `build_unified_join()` outer-joins all
sources on date and appends 1d/5d/20d forward returns for `00631L.TW`.
`DEFAULT_SOURCES` now lists 7 logs (garch_regime, specialist_routing,
market_state, signal_alignment, ncf_signal_archive,
recovery_boost_spillover_gate, signal_alignment_shadow_variant,
trough_override_eligibility -- updated twice more as #8 and #1's live logs
were added later in the session). Outputs a wide CSV + a coverage-summary
JSON (rows-with-data per source).

**Status: infrastructure only, by design.** As of 2026-07-16 each individual
log only has 1-12 rows (most started this session or this week) -- there is
nothing statistically meaningful to report yet. This is the tool that will
matter once the logs have run for months, not a finding today.

**Tests:** `tests/test_build_group_a_plus_shadow_log_unified_join.py` (6 tests, new).

---

## #8 - signal_alignment shadow variant with 3 new sources

**Finding.** `group_a_plus/integrations/signal_alignment.py`'s 9 production
sources have never included `trough_nowcast`, `compounding_regime`, or
`crash_risk_alert`, even though all three are already computed daily
(`trough_nowcast` is embedded directly in `live_signal.json`;
`compounding_regime` and `crash_risk_alert.json` are separate daily
artifacts already produced by the pipeline).

**What was done.**
- `build_signal_alignment()` gained an `extra_sources: list[dict] | None =
  None` parameter (default `None` = zero behavior change for every existing
  caller -- verified: `build_signal_alignment(signal) ==
  build_signal_alignment(signal, extra_sources=None)` for a real fixture).
  All 26 pre-existing tests passed unmodified.
- New module `group_a_plus/integrations/signal_alignment_shadow_variant.py`:
  `_trough_nowcast_source` (NO_TROUGH -> `available=False`;
  CAPITULATION_WARNING -> bearish; PARTIAL/FULL_REENTRY -> bullish, strength
  scaled by the respective score), `_compounding_regime_source`
  (TREND_PERSISTENT -> bullish, MEAN_REVERTING -> bearish, TRANSITIONAL ->
  neutral), `_crash_risk_alert_source` (bearish, strength =
  `category_score/3`). `build_signal_alignment_shadow_variant()` calls
  `build_signal_alignment(live_signal, extra_sources=[...])`, reusing the
  exact production weighting/alignment/leverage_suitability math -- no
  forked aggregation logic.
- Runner `scripts/run/build_group_a_plus_signal_alignment_shadow_variant_log.py`
  reads today's already-produced `live_signal.json` (trough_nowcast),
  latest `compounding_regime` JSON, and `crash_risk_alert.json`. Wired into
  `run_ncf_daily_pipeline.py`'s `main()` (inline try/except block, same
  pattern as the existing `[signal-alignment]`/`[crash-risk-alert]` blocks,
  right after them). Log: `results/signal_alignment_shadow_variant_log.jsonl`.

**Status: live and already showing real divergence.** On 2026-07-15,
production `signal_alignment` = `bearish_share=0.359`; shadow variant with
the 3 new sources = `bearish_share=0.416` (CAPITULATION_WARNING +
crash_risk_alert watch both pushed bearish, outweighing compounding_regime's
bullish TREND_PERSISTENT vote). Neither `alignment` nor `leverage_suitability_tier`
flipped that day, but the weighted-share shift is real. On 2026-07-16's
pipeline run, production alignment = `bullish_alignment` while shadow
variant = `mixed` -- a bigger divergence. Not enough samples yet to say
whether the shadow variant is *better*, only that it behaves differently.

**Tests:** `tests/test_group_a_plus_signal_alignment_shadow_variant.py` (13
tests, new), `tests/test_group_a_plus_signal_alignment.py` (+2 tests for the
`extra_sources` hook).

---

## #9 - PIT historical panel gap (2020-2024) and DFL re-validation

**Finding.** `results/ncf_00631l_pit_historical_panel_20260713.csv` (the
no-lookahead NCF signal surface) only covered 2017-2019 + 2025-2026. Several
research evaluators' "covid_2020"/"inflation_2022" windows
(`evaluate_group_a_plus_recovery_boost_spillover_gate.py`,
`evaluate_group_a_plus_reentry_accelerator_clean.py`, and critically the
**promoted-candidate DFL config** in
`report/group_a_plus/review/md/a2118_dfl_best_candidate_handoff_20260714.md`)
pointed their covid_2020 window at
`results/ncf_00631l_panel_latest_20260707.csv` -- a panel that only has
2025-2026 rows. Checked what this actually means: since the panel has zero
rows for 2020 dates, `run_a2118` for that window ran **completely
panel-blind**, and DFL's `--require-panel-signal` flag defaults to KEEP for
every day with no panel signal available. The original 7-window "best
candidate" report's `covid_2020: non_keep=0` result was not "the model chose
KEEP" -- it was a silent no-op the whole time. The touted "7/7 triple-pass"
claim rested on a window that had never actually been tested.

**What was done.**
1. Built a genuine 2020 NCF backfill panel:
   `python3 scripts/misc/ncf_00631l.py --train-start 2015-06-01 --val-start
   2020-01-01 --val-end 2020-12-31 --full-panel` (same command family used
   for the existing 2017-2019 backfill, per
   `GROUP_A_PLUS_00631L_DOWNSIDE_RISK_RACE_CLASSIFIER_HANDOFF_20260710.md`).
   ~20 minutes of real ML training. Output:
   `results/ncf_00631l_panel_backfill_2020_20260716.csv` (245 rows,
   2020-01-02..2020-12-31, same schema as the 2017-2019 backfill).
2. Added it as a new source (`oos_2020`) to
   `build_ncf_pit_historical_panel.py`'s `DEFAULT_SOURCES` and regenerated
   the PIT panel: `results/ncf_00631l_pit_historical_panel_20260716.csv`
   (1097 -> 1342 rows, now covers 2017-2020 + 2025-2026).
3. Re-ran the exact promoted DFL configuration
   (`--stateful-actions --require-panel-signal --min-train-days 60
   --edge-threshold 0.0005 --reenter-edge-threshold -0.0005 --regret-clip
   0.02 --adjustment-fraction 0.75 --turnover-cap 0.05`) with covid_2020
   pointed at the new real 2020 panel instead of the panel-blind one.
   Output: `results/a2118_decision_focused_action_shadow_stateful_panelgate_edge0005_adj75_7win_pit2020_20260716.json`.

**Result:**

| window | Δfinal_value | ΔSharpe | non-KEEP actions |
|---|---:|---:|---|
| **covid_2020 (real data)** | **-24,345** | **-0.0796** | 4x CAP10 |
| inflation_2022 | 0 | 0 | 0 (still panel-blind, out of this pilot's scope) |
| live_2024_2026 | +8,879 | +0.0051 | 3x CAP10 |
| active_2025_2026 | 0 | 0 | 0 |
| 2017_bull | 0 | 0 | 0 |
| 2018_correction | +5,313 | +0.0298 | 4x CAP10 |
| 2019_recovery | 0 | 0 | 0 |

Triple-pass: **6/7**, not 7/7. covid_2020 is now the single worst window in
the whole suite by a wide margin. The 4 CAP10 decisions fired on
2020-06-03/04/08 and 2020-10-06 -- exactly during the sharp V-shaped
post-crash rally. The model's own predicted regret for those actions was
small (0.0005-0.0019); the realized cost was not. Full decision-level detail
is in the JSON above (`non_keep_decisions` under the `covid_2020` window).

**Status: DFL best-candidate claim downgraded; still shadow-only, no
production impact either way** (DFL was never promoted, so this doesn't
change anything about the live system -- it just means the informal
"pending, looks promising" status should be revised to "has a demonstrated
failure mode in a real crisis"). `inflation_2022` and 2021/2023/2024
remain panel-blind; extending further would use the identical
`ncf_00631l.py --train-start/--val-start/--val-end --full-panel` command
with a different year.

**Tests:** `tests/test_build_ncf_pit_historical_panel.py` /
`tests/test_build_ncf_panel_manifest.py` re-run clean (5 tests, no changes
needed -- they use explicit synthetic sources, unaffected by the
`DEFAULT_SOURCES` change).

---

## #10 - specialist_router route as a free conditioning variable

**Finding.** `specialist_router.py`'s routing-weight sweep has never passed
on its own (`eligible_variants=[]` as of 2026-07-10), but the route
classification itself is free to compute. Fable's low-confidence hypothesis:
could route (crash_deleverage/high_volatility/low_volatility/neutral/
semiconductor_risk) still be useful as a conditioning variable for other
signals -- e.g. "only trust A21.18 DFL in neutral/low_volatility routes,"
or "trough-override eligible days should exclude crash_deleverage route."

**What was done.** New script
`scripts/evaluate/evaluate_group_a_plus_specialist_router_conditioning.py`:
derives an approximate route (crash_deleverage > high_volatility >
low_volatility > neutral, in `route_specialist`'s exact priority order;
`semiconductor_risk` skipped -- needs a per-date `ncf_2330` `tsmc_0050_health`
snapshot not cheaply reconstructable historically) for two concrete event
sets already produced by this session's other work: (a) DFL's realized
mistiming dates from #9's covid_2020 PIT re-run plus its 2018_correction/
live_2024_2026 non-KEEP dates, and (b) #1's trough-override eligible dates.

**Result** (saved: `results/group_a_plus_specialist_router_conditioning_latest.json`):
all 4 covid_2020 DFL mistiming dates classify as `neutral` route; all 4
2018_correction non-KEEP dates classify as `low_volatility` route. 8 of 11
total DFL decision dates fall in `neutral`, 2 in `low_volatility`, only 1 in
`crash_deleverage`. **The hypothesis is contradicted, not just
unconfirmed**: DFL's actual failures happened inside the exact routes the
hypothesis assumed were safe to trust. Route-gating DFL would not have
screened out the covid_2020 loss. Separately, the trough-override eligible
dates are ~all `high_volatility` route, but that's circular -- the
override's own eligibility check already requires `high_vol_gate`, so this
isn't new information.

**Status: closed, no promotion, no further work planned** unless new
evidence appears. This matches the fallback Fable itself specified going in
("若分層無差異即永久關閉此線").

**Tests:** `tests/test_evaluate_group_a_plus_specialist_router_conditioning.py` (5 tests, new).

---

## Operational work (not part of the Fable review)

1. **Manual data refresh + full daily pipeline, twice.** First run
   (`python3 scripts/run/run_ncf_daily_pipeline.py`, no flags) resolved
   `target_date=2026-07-15` via the auto/cutoff-hour logic (market hadn't
   settled 2026-07-16 data yet) -- 37/37 steps completed, one non-fatal
   `ohlcv_freshness` warning (expected pre-close lag). After the user
   confirmed the market had closed, re-ran `refresh_group_data.py --group
   both --target-date 2026-07-16 --force` (confirmed new data landed: row
   counts +1) and then the full pipeline again with `--force-refresh
   --refresh-target-date 2026-07-16`. Second run: NCF now dated
   `2026-07-16` (00631L prob_up 0.5791, 00632R prob_up 0.6219); chip/
   derivative sources (TAIFEX options, margin, etc.) still lag to
   2026-07-15 as of this writing -- expected T+1 publishing behavior for
   those providers, not a bug. `crash_risk_alert.as_of` and
   `signal_alignment`/its shadow variant are still effectively keyed to
   07-15 chip data for the same reason.
2. **2026-07-17 forecast, latest strategy vs. golden1_0531.** Ran
   `group_a_plus/operations/daily_signal.py --as-of 2026-07-17` to a
   **non-production output path**
   (`results/group_a_plus_live_signal_v2_predict_20260717.json` /
   `..._latest_pointer.json` -- did **not** touch
   `report/group_a_plus/latest/live_signal.json`). Result: a2118 resolves to
   `execution_regime=golden1`, target weights `0050=57.4%,
   00631L=12.6%, cash=30.0%` (shares 5,392 / 3,393). Compared against the
   frozen `results/signal_group_a_golden1_0531_predict_20260615_from_all_20260613_total1000000.json`
   baseline (`0050=60%, 00631L=20%`, static by construction -- it's a
   buy-and-hold reference, not something that gets "predicted" per date):
   a2118 is running about 7.4pp lighter on 00631L and 10pp heavier in cash
   than the frozen golden1_0531 reference, reflecting the NCF-driven
   de-leverage overlay on top of the golden1 base regime.

---

## File manifest

### New files (production/research code)
- `group_a_plus/integrations/recovery_boost_spillover_gate_shadow.py`
- `group_a_plus/integrations/signal_alignment_shadow_variant.py`
- `group_a_plus/integrations/trough_override_eligibility_shadow.py`
- `scripts/run/build_group_a_plus_recovery_boost_spillover_gate_shadow_log.py`
- `scripts/run/build_group_a_plus_signal_alignment_shadow_variant_log.py`
- `scripts/run/build_group_a_plus_trough_override_eligibility_shadow_log.py`
- `scripts/evaluate/evaluate_group_a_plus_crash_detector_overlap.py`
- `scripts/evaluate/evaluate_group_a_plus_specialist_router_conditioning.py`
- `scripts/evaluate/build_group_a_plus_shadow_log_unified_join.py`

### New tests
- `tests/test_group_a_plus_recovery_boost_spillover_gate_shadow.py`
- `tests/test_group_a_plus_signal_alignment_shadow_variant.py`
- `tests/test_group_a_plus_trough_override_eligibility_shadow.py`
- `tests/test_evaluate_group_a_plus_crash_detector_overlap.py`
- `tests/test_evaluate_group_a_plus_specialist_router_conditioning.py`
- `tests/test_evaluate_00631l_multisource_crash_risk.py`
- `tests/test_build_group_a_plus_shadow_log_unified_join.py`

### Modified production/research code
- `scripts/run/run_ncf_daily_pipeline.py` (3 new best-effort steps in
  `build_commands`; 1 new inline block in `main()`)
- `scripts/misc/check_group_a_plus_daily_status.py` (+`_dfl_frozen_input_staleness`, +1 check)
- `scripts/evaluate/evaluate_group_a_plus_trough_nowcast_vol_gate_override_shadow.py`
- `scripts/evaluate/evaluate_00631l_multisource_crash_risk.py`
- `scripts/run/build_00631l_crash_risk_alert.py`
- `group_a_plus/integrations/trough_nowcast.py`
- `group_a_plus/governance/catalog.py`
- `group_a_plus/integrations/signal_alignment.py` (+`extra_sources` param)
- `scripts/evaluate/build_ncf_pit_historical_panel.py` (+`oos_2020` source)

### Modified tests
- `tests/test_run_ncf_daily_pipeline.py`
- `tests/test_check_group_a_plus_daily_status.py`
- `tests/test_evaluate_group_a_plus_trough_nowcast_vol_gate_override_shadow.py`
- `tests/test_group_a_plus_governance_catalog.py`
- `tests/test_group_a_plus_signal_alignment.py`

### New research artifacts (`results/`, `report/`)
- `ncf_00631l_panel_backfill_2020_20260716.csv` / `.json` (new PIT source)
- `ncf_00631l_pit_historical_panel_20260716.csv` / `.json` (regenerated PIT panel)
- `a2118_decision_focused_action_shadow_covid2020_pit_20260716.json`
- `a2118_decision_focused_action_shadow_stateful_panelgate_edge0005_adj75_7win_pit2020_20260716.json`
- `group_a_plus_trough_nowcast_vol_gate_override_shadow_eligibility_union_20260716.json`
- `group_a_plus_trough_nowcast_vol_gate_override_shadow_fraction_confirmation_sweep_20260716.json`
- `group_a_plus_crash_detector_overlap_latest.json`
- `group_a_plus_specialist_router_conditioning_latest.json`
- `group_a_plus_shadow_log_unified_join_latest.csv` / `_summary_latest.json`
- `group_a_plus_recovery_boost_spillover_gate_shadow_log.jsonl` (new daily log)
- `group_a_plus_trough_override_eligibility_shadow_log.jsonl` (new daily log)
- `signal_alignment_shadow_variant_log.jsonl` (new daily log)
- `group_a_plus_live_signal_v2_predict_20260717.json` (2026-07-17 forecast, non-production path)
- `report/group_a_plus/latest/recovery_boost_spillover_gate_shadow.json`
- `report/group_a_plus/latest/signal_alignment_shadow_variant.json`
- `report/group_a_plus/latest/trough_override_eligibility_shadow.json`

## Verification

All touched-file test suites were run to green after each change (not just
at the end):
- `tests/test_run_ncf_daily_pipeline.py` — 15 passed
- `tests/test_run_a2120_daily_shadow_pipeline.py` — 1 passed
- `tests/test_check_group_a_plus_daily_status.py` — 9 passed
- `tests/test_evaluate_group_a_plus_trough_nowcast_vol_gate_override_shadow.py` — 10 passed
- `tests/test_group_a_plus_trough_nowcast.py` — 2 passed
- `tests/test_leveraged_compounding_regime.py` — passed
- `tests/test_group_a_plus_recovery_boost_spillover_gate_shadow.py` — 7 passed
- `tests/test_group_a_plus_network_volatility_spillover_shadow.py` — 3 passed
- `tests/test_evaluate_00631l_multisource_crash_risk.py` — 4 passed
- `tests/test_build_00631l_crash_risk_alert.py` — 15 passed
- `tests/test_group_a_plus_governance_catalog.py` — 6 passed
- `tests/test_group_a_plus_governance_compare_extended.py` — passed
- `tests/test_group_a_plus_latest_strategy.py` — passed
- `tests/test_evaluate_group_a_plus_crash_detector_overlap.py` — 4 passed
- `tests/test_group_a_plus_signal_alignment.py` — 28 passed
- `tests/test_group_a_plus_signal_alignment_shadow_variant.py` — 13 passed
- `tests/test_build_group_a_plus_shadow_log_unified_join.py` — 6 passed
- `tests/test_group_a_plus_trough_override_eligibility_shadow.py` — 4 passed
- `tests/test_build_ncf_pit_historical_panel.py` / `test_build_ncf_panel_manifest.py` — 5 passed
- `tests/test_evaluate_group_a_plus_specialist_router_conditioning.py` — 5 passed

Plus real end-to-end smoke tests (not just unit tests): `run_a2120_daily_shadow_pipeline.py`,
`build_group_a_plus_recovery_boost_spillover_gate_shadow_log.py`,
`build_group_a_plus_trough_override_eligibility_shadow_log.py`,
`build_group_a_plus_signal_alignment_shadow_variant_log.py`,
`build_group_a_plus_shadow_log_unified_join.py`, and the catalog's generated
`module_command_template` for `a2121` were all run against real production
data at least once, not just tested in isolation.

## What is NOT done / open follow-ups

- **#5**: crash-detector overlap coverage gap identified (57-75% of
  alert-only trigger days have no blocking guard active) but no
  "escalate-to-blocking" rule has been designed or backtested yet.
- **#9**: PIT panel still missing 2021/2023/2024 and `inflation_2022` is
  still panel-blind. Same `ncf_00631l.py --full-panel` command, different
  `--val-start/--val-end`, ~20 min per year.
- **#7**: unified join has almost no data yet (1-12 rows per source) --
  revisit in a few weeks/months once the 7 daily shadow logs have
  accumulated enough rows for the forward-return comparison to mean
  anything.
- **#1**: 50%/none override configuration needs more OOS samples before any
  promotion discussion; the live shadow log started 2026-07-15/16.
- **#8**: signal_alignment shadow variant is logging real divergences from
  production (`mixed` vs. `bullish_alignment` on 2026-07-16) but there's no
  forward-return evidence yet on which one is more predictive.
- Nothing in this session was promoted to production. Every new artifact is
  `research_only: true` and either `production_effect: "none"` or advisory-only.
