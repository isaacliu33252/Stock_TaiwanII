# Ops Health Check and NCF Panel Refresh Attempt — 2026-07-27

## Status

**Pipeline healthy, no crashes. One active medium-severity alert
investigated in depth; refresh attempted following this project's own
established procedure, found unsafe, NOT executed.** No production
setting was changed. Read-only investigation throughout; the only file
this thread wrote is a throwaway drift-audit JSON
(`results/ncf_panel_drift_0716_vs_0725_20260727.json`).

## Origin

User asked to check on the daily automation pipeline's health, since the
2026-07-25 governance-chain/`None`-crash fix
(`project_daily_pipeline_broken_since_0721_fixed_20260725`) had not been
re-verified in a few days. Chosen as one of two parallel next steps
alongside the `decision_confidence` Phase 2 calibration work (see
`GROUP_A_PLUS_DFL_ACTION_VALUE_CALIBRATION_PHASE2_20260727.md`).

## Part 1: pipeline health

`report/group_a_plus/latest/daily_status.json` is dated `check_date:
2026-07-25`, `generated_at: 2026-07-26T01:53:20` -- the last full nightly
batch covers Friday 2026-07-24's close (2026-07-25/26 were Sat/Sun, no
trading). This matches the documented 23:00-download /23:30-NCF schedule
and today (Monday 2026-07-27)'s own batch had not run yet at the time of
this check (still before 23:00). No gap, no crash.

**One false alarm caught and ruled out**: five lighter report files
(`crash_risk_alert.json`, `ops_health.json`, `watchlist_news.json`,
`signal_alignment_shadow_variant.json`, `strategy_env_health.json`) had
mtimes overlapping almost exactly with a `pytest tests/ -q` full-suite run
happening in this same session, raising a real concern that the test
suite might be writing to live production report paths instead of
`tmp_path`. Ruled out by content inspection:
`crash_risk_alert.json`'s `generated_at: 2026-07-27T12:41:41Z` (UTC) =
20:41:41 Taiwan time, matching the suspicious mtime -- but the payload
contains real TXO/VIX/SOXX market-condition flags, not test-fixture
values, confirming this is a separate, more-frequent, legitimate
monitoring job independent of the main nightly batch, not test
contamination.

## Part 2: the active `ncf_panel_stale` alert

`report/group_a_plus/latest/alert_state.json` (generated
`2026-07-25T17:54:17Z`) has 3 active alerts:

1. **`ncf_panel_stale`, medium**: `ncf_panel_631l` last covers
   `2026-07-16`, 6 trading days behind signal date `2026-07-24` (more now).
2. `network_spillover_snapshot_stale`, medium: a shadow/advisory-only
   snapshot 15 days stale -- lower priority, not investigated further.
3. `00631l_crash_risk_family_degraded`, watch: one crash-risk source
   family stale, only reduces confidence, not a hard gate.

Focused on (1) since it's the only one touching the actual live production
NCF signal.

### Why is the panel pinned at all?

`report/group_a_plus/latest/strategy.json`'s `active_strategy.runner_params`
hard-pins `ncf_panel_631l_path` to
`results/ncf_00631l_panel_latest_20260716.csv` -- a *fixed* file, not "use
whatever's freshest." `daily_signal.py:1346-1372` has an explicit comment
explaining why this alert exists at all: pinning the panel means its mtime
stops advancing, which silently neuters
`_previous_a2118_hold_active`'s `min_previous_generated_at` guard (a
different, older mechanism meant to auto-invalidate a stale hold once the
panel regenerates) -- discovered in the 2026-07-02 Fable 5 audit
(`M3`). `ncf_panel_stale` is the deliberate compensating control: a
human-facing warning that ages independently of that broken mtime check,
exactly because the automatic mechanism can't catch a pinned path.

`git log -S` on `strategy.json`'s `ncf_panel_631l_path` field shows this
is **not** a permanent reproducibility freeze like `golden1_0531` --
the pin has moved routinely before (`...20260630.csv` ->
`...20260707.csv` -> `...20260716.csv`), each time accompanied by an
explicit `a2118_trigger_stability` check comparing old-panel vs new-panel
trigger days before the switch was made. `20260716` is simply the last
routine update before the pipeline broke on 2026-07-21; nobody has done
the next routine update since the 2026-07-25 fix, because that step is a
deliberate human/reviewed action, not part of the automated daily batch
(the raw panel CSVs *do* keep regenerating daily on their own --
`results/ncf_00631l_panel_latest_20260725.csv`, dated through
2026-07-24, already existed and was sitting unused).

### Attempting the routine refresh, following the established procedure

Ran the same kind of `run_a2118` trigger-stability comparison used for
every prior panel-pin update (`2024-01-02` to latest, both panels,
identical production params):

```
pinned_0716    (results/ncf_00631l_panel_latest_20260716.csv):
  final_value=2,787,181  sharpe=1.8557  sortino=1.8287  mdd=-0.2103
  execution_regime counts: golden1=529, group_a_plus_defensive=69, group_a_plus_recovery=1

candidate_0725 (results/ncf_00631l_panel_latest_20260725.csv):
  final_value=2,607,285  sharpe=1.8751  sortino=1.8339  mdd=-0.2103
  execution_regime counts: golden1=494, group_a_plus_defensive=69,
                            ncf_late_bull_hedge=35, group_a_plus_recovery=1
```

**35 of 599 overlapping trading days change `execution_regime`** --
specifically, `ncf_late_bull_hedge` (an overlay that reduces exposure
inside `golden1`) goes from 0 trigger days under the pinned panel to 35
under the candidate, spanning `2025-10-23` through `2026-03-03` -- several
months in the *past*, not just newly-arrived dates after 2026-07-16.

Confirmed this is genuine prediction drift, not a data-alignment bug, by
diffing the two panels' raw columns for the *same historical dates*:

```
date        OLD(0716) h20_prob_up / confidence   NEW(0725) h20_prob_up / confidence
2025-10-23  0.3852 / 0.2210                       0.2937 / 0.3343
2025-10-29  0.2823 / 0.4049                        0.2040 / 0.5259
2026-01-29  0.3408 / 0.4048                        0.2345 / 0.5618
2026-02-23  0.3081 / 0.4167                        0.1370 / 0.5907   <- crosses both trigger thresholds (h20_max=0.33, conf_min=0.55)
2026-03-02  0.4640 / 0.2640                        0.3203 / 0.4383
```

Retraining on ~9 more days of data changed the model's *retroactive*
prediction for calendar dates many months old -- textbook panel drift,
the same pathology `project_ncf_panel_drift_fix_20260707` partially fixed
(expanding-model-weights + shrinkage). This directly contradicts
`strategy.json`'s own `ncf_late_bull_hedge_dormancy_audit_20260723`
record, which checked 6 different panel snapshots (`20260707`, `20260708`,
`20260716`, `20260720`, `20260721`, `20260722` -- all 6/6) and found this
exact trigger condition never fires in any of them.

### Quantifying the drift with the existing tool, and the decisive check

Ran `scripts/evaluate/evaluate_ncf_panel_drift.py` (which gained
`--outcome-aware`/`--window-start` in the 2026-07-26 session) directly:

```bash
python3 scripts/evaluate/evaluate_ncf_panel_drift.py \
  --baseline-panel results/ncf_00631l_panel_latest_20260716.csv \
  --candidate-panel results/ncf_00631l_panel_latest_20260725.csv \
  --columns h20_prob_up confidence prob_fwd_mdd_gt5_h20 prob_fwd_gain_gt5_h20 \
  --outcome-aware --top-n 15 \
  --output results/ncf_panel_drift_0716_vs_0725_20260727.json
```

Overlap: 2025-01-02 to 2026-07-16, 371 rows.

| column | mean abs delta | max abs delta | max delta date |
|---|---:|---:|---|
| h20_prob_up | 0.079 | **0.196** | 2026-02-10 |
| confidence | 0.090 | **0.270** | 2026-02-24 |
| prob_fwd_mdd_gt5_h20 | 0.031 | 0.121 | 2025-04-14 |
| prob_fwd_gain_gt5_h20 | 0.024 | 0.099 | 2026-03-23 |

Both `h20_prob_up`'s and `confidence`'s max drift **exceed the <=0.13
bound** the 2026-07-07 expanding-model-weights fix was reported to have
achieved across all 8 columns it checked at the time -- a new or
unaddressed drift source, not investigated further this round (see "What
was NOT done").

**The decisive check -- outcome-aware, i.e. does the newer panel's
changed prediction actually get closer to the real, now-resolved
outcome?**

| column | candidate favorable | baseline favorable | resolved n |
|---|---:|---:|---:|
| h20_prob_up | 176 (49.3%) | 181 (50.7%) | 357 |
| prob_fwd_mdd_gt5_h20 | 149 (42.5%) | **202 (57.5%)** | 351 |
| prob_fwd_gain_gt5_h20 | 171 (48.7%) | 180 (51.3%) | 351 |

All three are at or below a coin flip; the drawdown-risk column is
*worse* than the pinned panel more often than better. If the 2026-07-24
retraining genuinely surfaced new information, the newer panel should be
systematically *more* accurate on dates whose outcome we can already
check -- it is not. This is consistent with the 35-day
`ncf_late_bull_hedge` activation being retraining noise rather than a
real regime signal.

## Decision

**Did not refresh the pin.** Two independent, mutually-reinforcing
reasons: (1) refreshing would silently rewrite `execution_regime`
classification for several months of already-past dates and resurrect an
overlay a dedicated audit confirmed dormant four days earlier
(2026-07-23), and (2) the outcome-aware check shows the changed
predictions are not more accurate than what they replace -- there is no
evidence the newer information is worth the disruption. The
`ncf_panel_stale` alert remains active at medium severity (would escalate
to high past 10 trading days per `daily_signal.py:1363`); not urgent
enough to force a decision today given (2).

## What was NOT done

- Did not diagnose *why* this drift episode (max 0.196/0.270) exceeds the
  2026-07-07 fix's <=0.13 bound -- flagged as a real, independent, open
  question (is the shrinkage/expanding-weights fix no longer sufficient,
  or is this an unrelated new drift source e.g. a training-window-length
  threshold effect?). Worth a dedicated investigation, not attempted here
  to avoid scope creep from an ops-health check into a new research thread
  in the same sitting.
- Did not check `network_spillover_snapshot_stale` or
  `00631l_crash_risk_family_degraded` beyond reading their alert text --
  both are lower-priority (shadow-only / watch-level, not a hard gate).
- Did not attempt any drift *mitigation* (e.g. re-running the panel
  generation with different shrinkage parameters to see if the 35-day
  flip goes away) -- out of scope for an ops-health check; would be its
  own dedicated research thread if pursued.
- The pin was left at `20260716`. No `strategy.json` edit was made.

## Reproduction

```bash
# Pipeline/alert state
cat report/group_a_plus/latest/daily_status.json
cat report/group_a_plus/latest/alert_state.json
cat report/group_a_plus/latest/strategy.json | python3 -m json.tool | grep -A15 runner_params

# Trigger-stability comparison (same pattern as every prior panel-pin update)
python3 -c "
import sys; sys.path.insert(0, '.')
from group_a_plus.runners.a2118 import run_a2118, CHIP_DATA_FALLBACK_MAX_STALE_DAYS, RISK_SCORE_LOOKBACK_DAYS, MOMENTUM_FAST_EXIT_MIN, MOMENTUM_FAST_EXIT_MA_GAP_MIN
from backtest_group_a_plus_switch_policy import DB_PATH
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date
end = _resolve_end_date(DB_PATH, 'latest')
common = dict(start='2024-01-02', end=end, initial_value=1_000_000.0, db=DB_PATH,
    commission_rate=0.001425, slippage_rate=0.0005, equity_etf_sell_tax=0.001,
    h20_max=0.33, conf_min=0.55, h5_reentry_min=0.55,
    chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    risk_score_lookback_days=RISK_SCORE_LOOKBACK_DAYS,
    momentum_fast_exit_min=MOMENTUM_FAST_EXIT_MIN,
    momentum_fast_exit_ma_gap_min=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    exclude_zero_volume_rows=True)
for label, panel in [('pinned_0716','results/ncf_00631l_panel_latest_20260716.csv'),
                      ('candidate_0725','results/ncf_00631l_panel_latest_20260725.csv')]:
    report, frame = run_a2118(ncf_panel_631l_path=panel, **common)
    print(label, report['metrics'])
"

# Drift quantification
python3 scripts/evaluate/evaluate_ncf_panel_drift.py \
  --baseline-panel results/ncf_00631l_panel_latest_20260716.csv \
  --candidate-panel results/ncf_00631l_panel_latest_20260725.csv \
  --columns h20_prob_up confidence prob_fwd_mdd_gt5_h20 prob_fwd_gain_gt5_h20 \
  --outcome-aware --top-n 15 \
  --output results/ncf_panel_drift_0716_vs_0725_20260727.json
```

## Files referenced

Read/analyzed, not modified:
- `report/group_a_plus/latest/daily_status.json`, `alert_state.json`,
  `strategy.json`, `ops_health.json`, `crash_risk_alert.json`
- `group_a_plus/operations/daily_signal.py` (the `ncf_panel_stale` alert
  definition, `:1346-1372`)
- `group_a_plus/runners/a2118.py` (`run_a2118`)
- `scripts/evaluate/evaluate_ncf_panel_drift.py` (unmodified this
  session -- last changed 2026-07-26, see
  `GROUP_A_PLUS_H20_CALIBRATION_PANEL_DRIFT_GATE_DEADLOCK_HANDOFF_20260726.md`)

Output (throwaway, not committed to any pipeline):
- `results/ncf_panel_drift_0716_vs_0725_20260727.json`
