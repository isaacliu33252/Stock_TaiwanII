# A21.18 Decision-Focused Action Shadow Handoff

Date: 2026-07-13
Status: research-only shadow evaluator implemented

## Source Paper

Reviewed local PDF:

- `C:\Users\isaac\Downloads\2605.01176v1.pdf`

Relevant takeaway:

- Decision-focused learning / SPO aligns training with downstream portfolio decision quality rather than pointwise forecast accuracy.
- The same paper warns that SPO can create inflated predictions and excessive turnover.
- Practical stabilizers tested in the paper include prediction clipping, min-max rescaling, partial portfolio adjustment, and portfolio-level turnover control.

This implementation follows the conservative interpretation:

- finite action set only
- clipped predicted regret
- positive edge threshold before deviating from A21.18
- partial adjustment
- portfolio-level turnover cap
- no continuous free-form weights

## Implementation

New evaluator:

- `scripts/evaluate/evaluate_a2118_decision_focused_action_shadow.py`

New tests:

- `tests/test_evaluate_a2118_decision_focused_action_shadow.py`

The evaluator does not change:

- active strategy manifest
- live signal latest pointer
- execution plan
- A21.18 target weights

## Action Set

Finite actions:

- `KEEP`: use A21.18 target weights
- `NO_ADD`: cap `00631L.TW` at prior A21.18 00631L weight; move blocked exposure to cash
- `CAP10`: cap `00631L.TW` at 10%; move excess to `0050.TW`
- `REENTER`: use A21.18 target weights

Note:

- In one-step labels, `REENTER` is equivalent to `KEEP`.
- It remains in the action set for future stateful deployment tests where the live portfolio may be below A21.18 after a prior guard.

## Target

The model predicts action-level regret:

```text
action_regret(action) = Utility(action) - Utility(KEEP)
```

Utility:

```text
log(final wealth)
- lambda_mdd * max_drawdown
- gamma_turnover * turnover
- eta_missed_rebound * missed_rebound
```

Default utility parameters:

- horizon: `20`
- `lambda_mdd=0.35`
- `gamma_turnover=0.015`
- `eta_missed_rebound=0.30`

## Model

First version deliberately avoids neural networks.

Model:

- expanding / rolling ridge-linear model per action
- each action has its own predicted regret
- only historical labels with dates earlier than the decision date are used

Default features:

- NCF probabilities: `prob_up_h1`, `prob_up_h5`, `prob_up_h20`
- NCF risk/reward: `prob_fwd_mdd_gt5_h20`, `prob_fwd_gain_gt5_h20`, `confidence`
- A21.18 state: `ma_gap`, `total_risk_score`
- baseline weights: `w_0050`, `w_00631l`
- realized trailing returns: `ret_0050_5d`, `ret_00631l_5d`, `spread_00631l_0050_5d`

Stabilizers:

- predicted regret clipping
- edge threshold
- partial adjustment
- turnover cap
- no-op action suppression

No-op suppression means actions that do not actually change target weights are counted as `KEEP`.

## Commands

Default conservative run:

```bash
python3 scripts/evaluate/evaluate_a2118_decision_focused_action_shadow.py \
  --output results/a2118_decision_focused_action_shadow_default_20260713.json
```

Exploration run that overtraded:

```bash
python3 scripts/evaluate/evaluate_a2118_decision_focused_action_shadow.py \
  --min-train-days 60 \
  --edge-threshold 0 \
  --regret-clip 0.03 \
  --adjustment-fraction 0.4 \
  --turnover-cap 0.10 \
  --output results/a2118_decision_focused_action_shadow_edge0_train60_20260713.json
```

Best current conservative candidate:

```bash
python3 scripts/evaluate/evaluate_a2118_decision_focused_action_shadow.py \
  --min-train-days 60 \
  --edge-threshold 0.001 \
  --regret-clip 0.02 \
  --adjustment-fraction 0.25 \
  --turnover-cap 0.05 \
  --output results/a2118_decision_focused_action_shadow_edge001_train60_conservative_v3_20260713.json
```

## Results

Default run:

- output: `results/a2118_decision_focused_action_shadow_default_20260713.json`
- triple-pass windows: `5/5`
- behavior: almost entirely `KEEP`
- interpretation: safe but mostly inactive

Overtrading run:

- output: `results/a2118_decision_focused_action_shadow_edge0_train60_20260713.json`
- triple-pass windows: `2/5`
- `live_2024_2026`: final value delta `-139,263`, Sharpe delta `+0.0623`, MDD delta `+0.0225`
- `active_2025_2026`: final value delta `-3,856`, Sharpe delta `-0.0015`
- interpretation: lowering the edge threshold too far causes too many deviations and confirms the paper's warning about excessive turnover / unstable decisions

Best current conservative candidate:

- output: `results/a2118_decision_focused_action_shadow_edge001_train60_conservative_v3_20260713.json`
- triple-pass windows: `5/5`
- stabilizers:
  - `edge_threshold=0.001`
  - `regret_clip=0.02`
  - `adjustment_fraction=0.25`
  - `turnover_cap=0.05`
  - `min_train_days=60`

Window results:

- `live_2024_2026`: final value delta `+20,103`, Sharpe delta `+0.0835`, max drawdown delta `+0.0235`
- `active_2025_2026`: no deviations, no metric change
- `2017_bull`: no deviations, no metric change
- `2018_correction`: no deviations, no metric change
- `2019_recovery`: no deviations, no metric change

Effective non-KEEP actions in best candidate:

- `2024-07-11`: `CAP10`
  - predicted regret: `0.0014767472`
  - base 00631L weight: `0.1262613521`
  - final 00631L weight after partial adjustment: `0.1196960141`
- `2024-07-16`: `CAP10`
  - predicted regret: `0.0010463638`
  - base 00631L weight: `0.1262613521`
  - final 00631L weight after partial adjustment: `0.1196960141`

Selected realized edge for `live_2024_2026`:

- mean selected realized regret: `0.0036862155`
- positive selected realized regret rate: `100%`

## Interpretation

This is a valid first implementation of the user's decision-focused idea, but it is not yet promotion-ready.

What worked:

- The finite-action / clipped-regret framework is implementable.
- The conservative candidate avoids overtrading.
- It improves the broad `live_2024_2026` window without hurting tested out-of-sample windows.
- The edge-threshold ablation clearly shows why unrestricted DFL-style decisions are dangerous.

What did not yet work:

- In `active_2025_2026`, the best conservative candidate makes no effective changes.
- The apparent improvement comes from only two 2024 CAP10 days.
- There is not enough evidence to connect it to the current 2026-07-14 execution decision.

## Current Decision

Do not promote to live.

Keep as research-only shadow for now.

Promotion requirements before live use:

- add more crisis windows, especially 2020 and 2022, with valid NCF/backfill coverage
- store full per-day predictions and realized labels for audit
- add stateful `REENTER` evaluation using prior shadow position, not just one-step labels
- require active_2025_2026 to show non-trivial improvement or at least useful current-period decisions
- compare against the existing volatility gate and A21.18 extreme warning guard to avoid duplicate risk controls

## 2026-07-14 Update: Stateful Actions

Added stateful action support:

- CLI flag: `--stateful-actions`
- `KEEP` now preserves the current shadow overlay relative to the current day's A21.18 baseline
- `REENTER` explicitly moves the shadow portfolio back toward A21.18
- state is carried as an overlay, not as yesterday's full absolute weights

The overlay-relative implementation matters. A first attempt carried yesterday's full shadow weights forward; that was wrong because it ignored subsequent changes in the A21.18 baseline and created artificial drift. The corrected version carries only:

```text
overlay = shadow_weight - current_day_a2118_weight
```

and reapplies that overlay to each new day's A21.18 weights before selecting the next action.

Also added no-op suppression for stateful mode:

- `CAP10` is treated as `KEEP` when both A21.18 and shadow 00631L are already below the cap
- `NO_ADD` is treated as `KEEP` when A21.18 is not adding 00631L versus the prior A21.18 target

Command:

```bash
python3 scripts/evaluate/evaluate_a2118_decision_focused_action_shadow.py \
  --stateful-actions \
  --min-train-days 60 \
  --edge-threshold 0.001 \
  --reenter-edge-threshold -0.0005 \
  --regret-clip 0.02 \
  --adjustment-fraction 0.25 \
  --turnover-cap 0.05 \
  --output results/a2118_decision_focused_action_shadow_stateful_edge001_train60_v3_20260714.json
```

Result:

- output: `results/a2118_decision_focused_action_shadow_stateful_edge001_train60_v3_20260714.json`
- triple-pass windows: `5/5`
- `live_2024_2026`: final value delta `+30,628`, Sharpe delta `+0.0945`, max drawdown delta `+0.0258`
- `active_2025_2026`: no effective deviations, no metric change
- `2017_bull`: no effective deviations, no metric change
- `2018_correction`: no effective deviations, no metric change
- `2019_recovery`: no effective deviations, no metric change

Effective non-KEEP actions:

- `2024-07-11`: `CAP10`
  - predicted regret: `0.0014767472`
  - base 00631L weight: `0.1262613521`
  - final 00631L weight after partial adjustment: `0.1196960141`
- `2024-07-16`: `CAP10`
  - predicted regret: `0.0010463638`
  - base 00631L weight: `0.1262613521`
  - final 00631L weight after partial adjustment: `0.1147720106`

Selected realized edge for `live_2024_2026`:

- mean selected realized regret: `0.0036862155`
- positive selected realized regret rate: `100%`

Interpretation:

- The stateful mechanics are now usable for future experiments.
- This run still does not justify live promotion because all effective decisions are concentrated in two 2024 dates.
- No effective `REENTER` action was selected in this conservative run; future work should test synthetic and historical scenarios where the model is forced to choose between staying capped and re-entering.

## 2026-07-14 Update: Promotion-Style 7-Window Backtest

Added two crisis windows to the prior 5-window check:

- `covid_2020`: `2020-01-02` to `2020-12-31`
- `inflation_2022`: `2022-01-03` to `2022-12-30`

The full promotion-style window set is now:

- `covid_2020`
- `inflation_2022`
- `live_2024_2026`
- `active_2025_2026`
- `2017_bull`
- `2018_correction`
- `2019_recovery`

### Finding: Missing Panel Guard Is Required

Without a panel-availability gate, the model can act in 2020 even though the selected 2025-2026 NCF panel has no actual 2020 rows. That creates false positives from default-filled features.

Failed no-panel-gate runs:

- `results/a2118_decision_focused_action_shadow_stateful_edge001_7win_20260714.json`
  - triple-pass: `6/7`
  - `covid_2020`: final value delta `-6,660`, Sharpe delta `-0.0182`
  - 3 false-positive `CAP10` actions: `2020-06-03`, `2020-06-04`, `2020-06-05`
- `results/a2118_decision_focused_action_shadow_stateful_edge0005_7win_20260714.json`
  - triple-pass: `6/7`
  - `covid_2020`: final value delta `-21,767`, Sharpe delta `-0.0656`
  - 7 false-positive `CAP10` actions

Implemented:

- CLI flag: `--require-panel-signal`
- when enabled, a date may deviate from `KEEP` only if that date exists in the selected NCF panel
- otherwise the selector forces `KEEP`

This is a deployment-relevant guard: do not let the DFL overlay trade from default-filled features.

### Panel-Gated Results

Command, edge `0.001`:

```bash
python3 scripts/evaluate/evaluate_a2118_decision_focused_action_shadow.py \
  --stateful-actions \
  --require-panel-signal \
  --min-train-days 60 \
  --edge-threshold 0.001 \
  --reenter-edge-threshold -0.0005 \
  --regret-clip 0.02 \
  --adjustment-fraction 0.25 \
  --turnover-cap 0.05 \
  --windows covid_2020:2020-01-02:2020-12-31:results/ncf_00631l_panel_latest_20260707.csv:tuning_window,inflation_2022:2022-01-03:2022-12-30:results/ncf_00631l_panel_latest_20260707.csv:tuning_window,live_2024_2026:2024-01-02:latest:results/ncf_00631l_panel_latest_20260707.csv:tuning_window,active_2025_2026:2025-01-02:latest:results/ncf_00631l_panel_latest_20260707.csv:tuning_window,2017_bull:2017-01-03:2017-12-29:results/ncf_00631l_panel_backfill_2017_2019_20260710.csv:out_of_sample,2018_correction:2018-01-02:2018-12-31:results/ncf_00631l_panel_backfill_2017_2019_20260710.csv:out_of_sample,2019_recovery:2019-01-02:2019-12-31:results/ncf_00631l_panel_backfill_2017_2019_20260710.csv:out_of_sample \
  --output results/a2118_decision_focused_action_shadow_stateful_panelgate_edge001_7win_20260714.json
```

Result:

- output: `results/a2118_decision_focused_action_shadow_stateful_panelgate_edge001_7win_20260714.json`
- triple-pass: `7/7`
- all windows: no effective deviations
- interpretation: safe but inactive

Command, edge `0.0005`:

```bash
python3 scripts/evaluate/evaluate_a2118_decision_focused_action_shadow.py \
  --stateful-actions \
  --require-panel-signal \
  --min-train-days 60 \
  --edge-threshold 0.0005 \
  --reenter-edge-threshold -0.0005 \
  --regret-clip 0.02 \
  --adjustment-fraction 0.25 \
  --turnover-cap 0.05 \
  --windows covid_2020:2020-01-02:2020-12-31:results/ncf_00631l_panel_latest_20260707.csv:tuning_window,inflation_2022:2022-01-03:2022-12-30:results/ncf_00631l_panel_latest_20260707.csv:tuning_window,live_2024_2026:2024-01-02:latest:results/ncf_00631l_panel_latest_20260707.csv:tuning_window,active_2025_2026:2025-01-02:latest:results/ncf_00631l_panel_latest_20260707.csv:tuning_window,2017_bull:2017-01-03:2017-12-29:results/ncf_00631l_panel_backfill_2017_2019_20260710.csv:out_of_sample,2018_correction:2018-01-02:2018-12-31:results/ncf_00631l_panel_backfill_2017_2019_20260710.csv:out_of_sample,2019_recovery:2019-01-02:2019-12-31:results/ncf_00631l_panel_backfill_2017_2019_20260710.csv:out_of_sample \
  --output results/a2118_decision_focused_action_shadow_stateful_panelgate_edge0005_7win_20260714.json
```

Result:

- output: `results/a2118_decision_focused_action_shadow_stateful_panelgate_edge0005_7win_20260714.json`
- triple-pass: `7/7`
- `covid_2020`: no deviations, no metric change
- `inflation_2022`: no deviations, no metric change
- `live_2024_2026`: final value delta `+4,479`, Sharpe delta `+0.0044`, max drawdown delta `0.0000`
- `active_2025_2026`: no deviations, no metric change
- `2018_correction`: final value delta `+4,378`, Sharpe delta `+0.0246`, max drawdown delta `+0.0051`

Effective actions for edge `0.0005`:

- `live_2024_2026`
  - `2025-01-13`: `CAP10`, predicted regret `0.000721`
  - `2025-01-15`: `CAP10`, predicted regret `0.000770`
  - `2025-02-21`: `CAP10`, predicted regret `0.000585`
- `2018_correction`
  - `2018-07-27`: `CAP10`, predicted regret `0.000540`
  - `2018-10-01`: `CAP10`, predicted regret `0.000783`
  - `2018-10-02`: `CAP10`, predicted regret `0.000594`
  - `2018-10-04`: `CAP10`, predicted regret `0.000791`

Interpretation:

- `--require-panel-signal` is mandatory for any future promotion path.
- The panel-gated edge `0.0005` run is the best current research candidate.
- It is still not live-ready because `active_2025_2026` has no effective improvement and the live-window gain is small.
- The correct next research step is not live integration; it is broader panel coverage plus a sweep with panel gating enabled.

## 2026-07-14 Update: Panel-Gated Parameter Sweep

All runs below use:

- `--stateful-actions`
- `--require-panel-signal`
- `--min-train-days 60`
- `--regret-clip 0.02`
- `--reenter-edge-threshold -0.0005`
- 7-window promotion-style set

Sweep summary:

| output | edge | adjustment | turnover cap | pass | sum final delta | sum Sharpe delta | non-KEEP | conclusion |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `a2118_decision_focused_action_shadow_stateful_panelgate_edge001_7win_20260714.json` | 0.001 | 0.25 | 0.05 | 7/7 | 0 | 0.0000 | 0 | too conservative |
| `a2118_decision_focused_action_shadow_stateful_panelgate_edge0005_7win_20260714.json` | 0.0005 | 0.25 | 0.05 | 7/7 | +8,857 | +0.0290 | 7 | valid but small |
| `a2118_decision_focused_action_shadow_stateful_panelgate_edge00025_7win_20260714.json` | 0.00025 | 0.25 | 0.05 | 4/7 | -55,752 | +0.0567 | 19 | rejected, overtrades |
| `a2118_decision_focused_action_shadow_stateful_panelgate_edge0005_adj40_7win_20260714.json` | 0.0005 | 0.40 | 0.05 | 7/7 | +11,807 | +0.0325 | 7 | valid |
| `a2118_decision_focused_action_shadow_stateful_panelgate_edge0005_adj60_7win_20260714.json` | 0.0005 | 0.60 | 0.05 | 7/7 | +13,699 | +0.0346 | 7 | conservative candidate |
| `a2118_decision_focused_action_shadow_stateful_panelgate_edge0005_adj75_7win_20260714.json` | 0.0005 | 0.75 | 0.05 | 7/7 | +14,142 | +0.0350 | 7 | current balanced candidate |
| `a2118_decision_focused_action_shadow_stateful_panelgate_edge0005_adj40_turn10_7win_20260714.json` | 0.0005 | 0.40 | 0.10 | 7/7 | +11,807 | +0.0325 | 7 | same as cap 0.05 |
| `a2118_decision_focused_action_shadow_stateful_panelgate_edge0005_adj100_7win_20260714.json` | 0.0005 | 1.00 | 0.05 | 7/7 | +14,503 | +0.0413 | 4 | aggressive candidate |

Rejected:

- `edge=0.00025`
- reason: fails `live_2024_2026`, `active_2025_2026`, and `2019_recovery`; this matches the paper's warning that weaker decision thresholds can create unstable turnover.

Too conservative:

- `edge=0.001`
- reason: 7/7 pass but no effective action; useful as a safety bound only.

Current candidates:

- balanced research candidate: `edge=0.0005`, `adjustment_fraction=0.75`, `turnover_cap=0.05`
  - output: `results/a2118_decision_focused_action_shadow_stateful_panelgate_edge0005_adj75_7win_20260714.json`
  - 7/7 pass
  - sum final delta: `+14,142`
  - sum Sharpe delta: `+0.0350`
  - no negative windows
  - effective actions: 7 CAP10 days
- conservative research candidate: `edge=0.0005`, `adjustment_fraction=0.60`, `turnover_cap=0.05`
  - output: `results/a2118_decision_focused_action_shadow_stateful_panelgate_edge0005_adj60_7win_20260714.json`
  - 7/7 pass
  - sum final delta: `+13,699`
  - sum Sharpe delta: `+0.0346`
  - no negative windows
- aggressive research candidate: `edge=0.0005`, `adjustment_fraction=1.00`, `turnover_cap=0.05`
  - output: `results/a2118_decision_focused_action_shadow_stateful_panelgate_edge0005_adj100_7win_20260714.json`
  - 7/7 pass
  - sum final delta: `+14,503`
  - sum Sharpe delta: `+0.0413`
  - no negative windows

Interpretation:

- The action threshold is the dominant control.
- `turnover_cap=0.05` is not binding for the valid runs; increasing it to `0.10` changed nothing.
- Larger adjustment improves this sweep, but the signal remains sparse.
- `adjustment_fraction=0.75` is the current best compromise: it improves over 0.60 while avoiding the more concentrated action pattern of 1.00.
- Even the best candidate remains too small and inactive in `active_2025_2026`, so it should stay shadow-only.

## 2026-07-14 Update: CAP12 Action Trial

Added configurable action set support:

- CLI flag: `--actions`
- default remains `KEEP,NO_ADD,CAP10,REENTER`
- generic `CAPxx` actions are supported, for example `CAP12`

Reason for test:

- `CAP10` may be too abrupt when current A21.18 00631L baseline is around `12.6%`
- `CAP12` is a gentler cap and might improve execution smoothness if it can pass the decision-focused regret threshold

Test 1: add `CAP12` alongside `CAP10`

```bash
python3 scripts/evaluate/evaluate_a2118_decision_focused_action_shadow.py \
  --actions KEEP,NO_ADD,CAP12,CAP10,REENTER \
  --stateful-actions \
  --require-panel-signal \
  --min-train-days 60 \
  --edge-threshold 0.0005 \
  --reenter-edge-threshold -0.0005 \
  --regret-clip 0.02 \
  --adjustment-fraction 0.75 \
  --turnover-cap 0.05 \
  --windows <7-window-set> \
  --output results/a2118_decision_focused_action_shadow_stateful_panelgate_cap12_edge0005_adj75_7win_20260714.json
```

Result:

- output: `results/a2118_decision_focused_action_shadow_stateful_panelgate_cap12_edge0005_adj75_7win_20260714.json`
- identical to the existing `CAP10` run
- selected actions: `CAP10` only
- `CAP12` was never selected
- total final delta: `+14,142`
- sum Sharpe delta: `+0.0350`

Test 2: `CAP12` only, without `CAP10`

```bash
python3 scripts/evaluate/evaluate_a2118_decision_focused_action_shadow.py \
  --actions KEEP,NO_ADD,CAP12,REENTER \
  --stateful-actions \
  --require-panel-signal \
  --min-train-days 60 \
  --edge-threshold 0.0005 \
  --reenter-edge-threshold -0.0005 \
  --regret-clip 0.02 \
  --adjustment-fraction 0.75 \
  --turnover-cap 0.05 \
  --windows <7-window-set> \
  --output results/a2118_decision_focused_action_shadow_stateful_panelgate_cap12only_edge0005_adj75_7win_20260714.json
```

Result:

- output: `results/a2118_decision_focused_action_shadow_stateful_panelgate_cap12only_edge0005_adj75_7win_20260714.json`
- 7/7 pass
- no effective action
- all windows unchanged

Interpretation:

- `CAP12` does not currently add usable decision capacity.
- The model either prefers `CAP10`, or `CAP12` alone does not clear the regret threshold.
- Keep `CAP12` support in the evaluator for future tests, but do not include it in the current best candidate.

## 2026-07-14 Update: Existing Guard Overlap Check

Added overlap evaluator:

- `scripts/evaluate/evaluate_a2118_decision_focused_overlap.py`

Purpose:

- check whether DFL non-KEEP dates are already covered by existing volatility high-vol gate
- check whether DFL non-KEEP dates are already covered by A21.18 extreme-warning proxy

Commands:

```bash
python3 scripts/evaluate/evaluate_a2118_decision_focused_overlap.py \
  --input results/a2118_decision_focused_action_shadow_stateful_panelgate_edge0005_adj60_7win_20260714.json \
  --output results/a2118_decision_focused_action_overlap_edge0005_adj60_20260714.json
```

```bash
python3 scripts/evaluate/evaluate_a2118_decision_focused_overlap.py \
  --input results/a2118_decision_focused_action_shadow_stateful_panelgate_edge0005_adj100_7win_20260714.json \
  --output results/a2118_decision_focused_action_overlap_edge0005_adj100_20260714.json
```

Results:

- adj `0.60` candidate:
  - total non-KEEP days: `7`
  - covered by existing guard: `0`
  - coverage rate: `0%`
- adj `1.00` candidate:
  - total non-KEEP days: `4`
  - covered by existing guard: `0`
  - coverage rate: `0%`
- adj `0.75` candidate:
  - total non-KEEP days: `7`
  - covered by existing guard: `0`
  - coverage rate: `0%`

Effective DFL CAP10 dates occurred under low/neutral volatility, not high-vol:

- `2025-01-13`: `low_vol_participation`
- `2025-01-15`: `neutral_vol`
- `2025-02-21`: `low_vol_participation`
- `2018-07-27`: `low_vol_participation`
- `2018-10-01`: `low_vol_participation`
- `2018-10-02`: `low_vol_participation`
- `2018-10-04`: `low_vol_participation`

Interpretation:

- DFL action shadow is not merely duplicating the existing high-volatility pre-trade guard.
- It is also not duplicating the A21.18 extreme-warning proxy.
- The signal is independent, but still too sparse and too small to promote.

## Verification

```bash
pytest -q tests/test_evaluate_a2118_decision_focused_action_shadow.py
```

Result:

- `8 passed`

```bash
python3 -m py_compile scripts/evaluate/evaluate_a2118_decision_focused_action_shadow.py
```

Result:

- passed
