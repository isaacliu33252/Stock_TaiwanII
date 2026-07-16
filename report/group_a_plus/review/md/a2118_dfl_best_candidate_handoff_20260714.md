# A21.18 DFL Action Shadow Best Candidate Handoff

Date: 2026-07-14
Status: best research candidate selected; not promoted to live

## Best Candidate

Within the tested sweep, the best balanced research candidate is:

```text
actions = KEEP,NO_ADD,CAP10,REENTER
edge_threshold = 0.0005
adjustment_fraction = 0.75
turnover_cap = 0.05
stateful_actions = true
require_panel_signal = true
regret_clip = 0.02
min_train_days = 60
reenter_edge_threshold = -0.0005
```

Output:

- `results/a2118_decision_focused_action_shadow_stateful_panelgate_edge0005_adj75_7win_20260714.json`

Command:

```bash
python3 scripts/evaluate/evaluate_a2118_decision_focused_action_shadow.py \
  --stateful-actions \
  --require-panel-signal \
  --min-train-days 60 \
  --edge-threshold 0.0005 \
  --reenter-edge-threshold -0.0005 \
  --regret-clip 0.02 \
  --adjustment-fraction 0.75 \
  --turnover-cap 0.05 \
  --windows covid_2020:2020-01-02:2020-12-31:results/ncf_00631l_panel_latest_20260707.csv:tuning_window,inflation_2022:2022-01-03:2022-12-30:results/ncf_00631l_panel_latest_20260707.csv:tuning_window,live_2024_2026:2024-01-02:latest:results/ncf_00631l_panel_latest_20260707.csv:tuning_window,active_2025_2026:2025-01-02:latest:results/ncf_00631l_panel_latest_20260707.csv:tuning_window,2017_bull:2017-01-03:2017-12-29:results/ncf_00631l_panel_backfill_2017_2019_20260710.csv:out_of_sample,2018_correction:2018-01-02:2018-12-31:results/ncf_00631l_panel_backfill_2017_2019_20260710.csv:out_of_sample,2019_recovery:2019-01-02:2019-12-31:results/ncf_00631l_panel_backfill_2017_2019_20260710.csv:out_of_sample \
  --output results/a2118_decision_focused_action_shadow_stateful_panelgate_edge0005_adj75_7win_20260714.json
```

## Results

7-window promotion-style backtest:

- `covid_2020`
- `inflation_2022`
- `live_2024_2026`
- `active_2025_2026`
- `2017_bull`
- `2018_correction`
- `2019_recovery`

Result:

- triple-pass: `7/7`
- total final delta: `+14,142`
- total Sharpe delta: `+0.0350`
- total max drawdown delta: `+0.0061`
- non-KEEP days: `7`
- no negative windows

Window details:

- `live_2024_2026`: final delta `+8,829`, Sharpe delta `+0.0052`, MDD delta `0.0000`
- `2018_correction`: final delta `+5,313`, Sharpe delta `+0.0298`, MDD delta `+0.0061`
- all other windows: no effective deviations and no metric change

Effective actions:

- `2025-01-13`: `CAP10`
- `2025-01-15`: `CAP10`
- `2025-02-21`: `CAP10`
- `2018-07-27`: `CAP10`
- `2018-10-01`: `CAP10`
- `2018-10-02`: `CAP10`
- `2018-10-04`: `CAP10`

## Why This Candidate

Compared with nearby sweep points:

- `edge=0.001`: 7/7 pass but completely inactive
- `edge=0.00025`: rejected, overtrades and fails 3 windows
- `adjustment_fraction=0.60`: valid but lower total final delta, `+13,699`
- `adjustment_fraction=1.00`: higher total final delta, `+14,503`, but more concentrated/aggressive with only 4 active days
- `adjustment_fraction=0.75`: best balanced trade-off between improvement and action distribution

`turnover_cap=0.05` was not binding in the valid runs. Raising it to `0.10` did not change results.

## Existing Guard Overlap

Overlap report:

- `results/a2118_decision_focused_action_overlap_edge0005_adj75_20260714.json`

Result:

- total non-KEEP days: `7`
- covered by existing volatility high-vol gate: `0`
- covered by A21.18 extreme-warning proxy: `0`
- overlap rate: `0%`

Interpretation:

- This is not a duplicate of the existing volatility pre-trade guard.
- This is not a duplicate of the A21.18 extreme-warning guard.
- It is an independent shadow signal.

## Rejected Variants

CAP12:

- `results/a2118_decision_focused_action_shadow_stateful_panelgate_cap12_edge0005_adj75_7win_20260714.json`
- adding `CAP12` alongside `CAP10` produced identical results; model still selected only `CAP10`

CAP12 only:

- `results/a2118_decision_focused_action_shadow_stateful_panelgate_cap12only_edge0005_adj75_7win_20260714.json`
- no effective actions

Conclusion:

- keep `CAP12` support in the evaluator
- do not include `CAP12` in the current best candidate

## Do Not Promote Yet

Reason:

- `active_2025_2026` has no effective improvement
- overall gain is small
- no effective `REENTER` case has been demonstrated
- signal is sparse

Production decision:

- keep as shadow-only
- do not wire into live signal weights
- do not wire into execution plan guards yet

## Relevant Files

Implementation:

- `scripts/evaluate/evaluate_a2118_decision_focused_action_shadow.py`
- `scripts/evaluate/evaluate_a2118_decision_focused_overlap.py`

Tests:

- `tests/test_evaluate_a2118_decision_focused_action_shadow.py`
- `tests/test_evaluate_a2118_decision_focused_overlap.py`

Full detailed research log:

- `report/group_a_plus/review/md/a2118_decision_focused_action_shadow_handoff_20260713.md`

## Verification

Latest related verification:

```bash
pytest -q tests/test_evaluate_a2118_decision_focused_overlap.py tests/test_evaluate_a2118_decision_focused_action_shadow.py tests/test_evaluate_a2118_mpc_path_shadow.py tests/test_evaluate_a2118_warning_cashflow_guard.py
```

Result:

- `29 passed`

Compile check:

```bash
python3 -m py_compile scripts/evaluate/evaluate_a2118_decision_focused_action_shadow.py scripts/evaluate/evaluate_a2118_decision_focused_overlap.py
```

Result:

- passed

