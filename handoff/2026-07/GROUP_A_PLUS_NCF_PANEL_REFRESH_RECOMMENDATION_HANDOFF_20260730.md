# GroupA+ NCF Panel Refresh Recommendation Handoff - 2026-07-30

## Status

Completed. The 2026-07-27 manual "pinned panel vs candidate panel" outcome-
aware refresh decision has been converted into a repeatable governance tool
and wired into the daily NCF pipeline.

This does not auto-update the pinned production NCF panel. It produces a
machine-readable and Markdown recommendation so the human pin-refresh decision
does not have to be re-investigated from scratch every time a candidate panel
changes.

## Starting Point

User raised a process gap:

- On 2026-07-27, the pinned panel (`results/ncf_00631l_panel_latest_20260716.csv`)
  was compared with the freshest candidate panel
  (`results/ncf_00631l_panel_latest_20260725.csv`).
- The decision not to refresh was based on outcome-aware accuracy checks:
  candidate-favorable rates were roughly 42%-49% across resolved outcome
  columns.
- That showed the drift looked like retraining noise, not better signal.
- But the conclusion lived in handoff/manual investigation notes; future
  candidate changes would require the same manual reconstruction.

Independent verification:

- `scripts/evaluate/evaluate_ncf_panel_drift.py` already supported
  `--outcome-aware`.
- `GROUP_A_PLUS_20260727_SESSION_HANDOFF_INDEX.md` documented the manual
  0716-vs-0725 conclusion and the 42.5%-49.3% candidate-favorable rates.
- `scripts/run/run_ncf_daily_pipeline.py` already produced
  `ncf_panel_drift_active_vs_<stamp>.json`, but without `--outcome-aware` and
  without a refresh/keep/manual-review recommendation.

## Decision

Implement this as a small governance builder on top of the existing drift
audit, not by changing the drift diff algorithm itself.

Rationale:

- `evaluate_ncf_panel_drift.py` remains the measurement tool.
- New recommendation logic is explicitly policy/governance:
  it reads the outcome-aware audit and converts it into one of:
  - `keep_current_pin`;
  - `refresh_candidate_supported`;
  - `manual_review`.
- This keeps the data comparison reusable in other contexts while making the
  pin-refresh decision repeatable.

## New Tool

File added:

- `scripts/evaluate/build_ncf_panel_refresh_recommendation.py`

Inputs:

- `--drift-audit`: JSON from `evaluate_ncf_panel_drift.py --outcome-aware`.
- Optional policy thresholds:
  - `--min-resolved-rows`, default `30`;
  - `--min-candidate-favorable-rate`, default `0.55`;
  - `--max-risk-relevant-delta`, default `0.13`;
  - `--columns`, default:
    - `h20_prob_up`;
    - `prob_fwd_mdd_gt5_h20`;
    - `prob_fwd_gain_gt5_h20`.

Outputs:

- JSON report.
- Markdown report.
- Optional dated history JSON.

Decision logic:

- If requested columns are missing or lack enough resolved outcome-aware rows:
  `manual_review`.
- If any evaluable reviewed column has candidate-favorable rate below 55%:
  `keep_current_pin`.
- If candidate is more accurate but risk-relevant drift still exceeds 0.13:
  `manual_review`.
- If all evaluable reviewed columns meet the accuracy and risk-delta gates:
  `refresh_candidate_supported`.

Decision boundary:

- `auto_pin_update_allowed = false`.
- `target_weight_change_allowed = false`.
- `creates_orders = false`.

## Pipeline Wiring

File changed:

- `scripts/run/run_ncf_daily_pipeline.py`

Changes:

1. Active pinned-vs-candidate drift audit now includes `--outcome-aware`:

```bash
scripts/evaluate/evaluate_ncf_panel_drift.py \
  --baseline-panel <active pinned 00631L panel> \
  --candidate-panel results/ncf_00631l_panel_latest_<stamp>.csv \
  --outcome-aware \
  --output results/ncf_panel_drift_active_vs_<stamp>.json \
  --csv-output results/ncf_panel_drift_active_vs_<stamp>.csv
```

2. New command step added immediately after `ncf_panel_drift`:

```bash
scripts/evaluate/build_ncf_panel_refresh_recommendation.py \
  --drift-audit results/ncf_panel_drift_active_vs_<stamp>.json \
  --output report/group_a_plus/latest/ncf_panel_refresh_recommendation.json \
  --output-md report/group_a_plus/latest/ncf_panel_refresh_recommendation.md
```

3. `ncf_panel_refresh_recommendation` is marked best-effort. It is diagnostic
   governance and must not block `daily_signal`, `execution_plan`, or alerts.

## Tests Added / Updated

File added:

- `tests/test_build_ncf_panel_refresh_recommendation.py`

Coverage:

- Candidate favorable rates below threshold produce `keep_current_pin`.
- Candidate favorable rates above threshold plus acceptable risk-relevant
  drift produce `refresh_candidate_supported`.
- Sparse resolved outcomes produce `manual_review`.

File changed:

- `tests/test_run_ncf_daily_pipeline.py`

Coverage:

- `ncf_panel_drift` includes `--outcome-aware`.
- Pipeline includes `ncf_panel_refresh_recommendation`.
- Recommendation step reads `results/ncf_panel_drift_active_vs_<stamp>.json`.
- Recommendation JSON writes to
  `report/group_a_plus/latest/ncf_panel_refresh_recommendation.json`.
- Step is best-effort.
- No-external mode still keeps the active pinned-vs-candidate recommendation,
  because that recommendation does not depend on the external/no-external
  sensitivity side audit.

## Validation Run

Focused tests:

```bash
python3 -m pytest \
  tests/test_run_ncf_daily_pipeline.py \
  tests/test_evaluate_ncf_panel_drift.py \
  tests/test_build_ncf_panel_refresh_recommendation.py \
  tests/test_group_a_plus_daily_signal_v2.py \
  -q
```

Result:

```text
77 passed
```

Builder-only:

```bash
python3 -m pytest tests/test_build_ncf_panel_refresh_recommendation.py -q
```

Result:

```text
3 passed
```

Pipeline command tests:

```bash
python3 -m pytest tests/test_run_ncf_daily_pipeline.py -q
```

Result:

```text
21 passed
```

## 0716 vs 0725 Real-Data Replay

Command:

```bash
python3 scripts/evaluate/evaluate_ncf_panel_drift.py \
  --baseline-panel results/ncf_00631l_panel_latest_20260716.csv \
  --candidate-panel results/ncf_00631l_panel_latest_20260725.csv \
  --columns h20_prob_up prob_fwd_mdd_gt5_h20 prob_fwd_gain_gt5_h20 \
  --outcome-aware \
  --output results/ncf_panel_drift_active_vs_20260725_outcome_aware_20260730.json
```

Then:

```bash
python3 scripts/evaluate/build_ncf_panel_refresh_recommendation.py \
  --drift-audit results/ncf_panel_drift_active_vs_20260725_outcome_aware_20260730.json \
  --output results/ncf_panel_refresh_recommendation_20260725_candidate_20260730.json \
  --output-md results/ncf_panel_refresh_recommendation_20260725_candidate_20260730.md \
  --no-history
```

Result:

```text
recommendation = keep_current_pin
reason = candidate_not_more_accurate_on_resolved_outcomes
```

Column detail:

- `h20_prob_up`: candidate favorable `176/357`, rate `0.4930`,
  verdict `candidate_not_more_accurate`, risk-relevant max delta `0.1899`.
- `prob_fwd_mdd_gt5_h20`: candidate favorable `149/351`, rate `0.4245`,
  verdict `candidate_not_more_accurate`, risk-relevant max delta `0.1205`.
- `prob_fwd_gain_gt5_h20`: candidate favorable `171/351`, rate `0.4872`,
  verdict `candidate_not_more_accurate`, risk-relevant max delta `0.0829`.

This reproduces the 2026-07-27 manual conclusion as a repeatable check.

## Files Touched In This Session

- `scripts/evaluate/build_ncf_panel_refresh_recommendation.py`
- `scripts/run/run_ncf_daily_pipeline.py`
- `tests/test_build_ncf_panel_refresh_recommendation.py`
- `tests/test_run_ncf_daily_pipeline.py`
- `results/ncf_panel_drift_active_vs_20260725_outcome_aware_20260730.json`
- `results/ncf_panel_refresh_recommendation_20260725_candidate_20260730.json`
- `results/ncf_panel_refresh_recommendation_20260725_candidate_20260730.md`
- `handoff/2026-07/GROUP_A_PLUS_NCF_PANEL_REFRESH_RECOMMENDATION_HANDOFF_20260730.md`

## Residual Risk / Follow-Up

- This is a recommendation layer only; it intentionally does not auto-edit
  the pinned panel path.
- The 55% candidate-favorable threshold and 0.13 risk-relevant drift limit are
  governance defaults derived from prior drift handling. They should be
  revisited only with explicit evidence, not tuned day-by-day.
- Full repo test suite was not run in this session.

