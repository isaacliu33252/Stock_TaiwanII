# Cross-Market Directed Graph Shadow Handoff - 2026-07-15

## Status

This module is retained as `NO_ADD_ONLY_SHADOW_FILTER`.

It must not be used as:

- an automatic execution guard
- a REENTER signal
- an automatic allocation or weight-change rule

Live policy:

```text
NO_ADD alert threshold = 0.65
Require NO_ADD probability > REENTER probability
Auto weight change = false
Execution guard promotion = false
Re-entry promotion = false
```

## Timing Rule

For each Taiwan trading date `d`, source-market features use only the latest
source close with `source_dt < d`.

This is intentional.  U.S. market information from calendar day `T` can only be
used for Taiwan `T+1` trading decisions.

## Nodes

Source nodes:

```text
TSM
SOXX
QQQ
TWD=X
NVDA
AMD
AVGO
ASML
^TNX
```

Target nodes:

```text
2330.TW
0050.TW
00631L.TW
2454.TW
2317.TW
2308.TW
2382.TW
```

`0050.TW` and `00631L.TW` are required because the labels use their forward
relative return and 00631L forward drawdown.

## Current Production-Like Parameters

```text
edge_window = 250
tstat_threshold = 2.0
stability_threshold = 0.20
min_windows = 3
walk_forward_edge_selection = true
min_train_days = 504
retrain_step = 252
use_composite_features = true
```

## Latest Report Pointer

The daily signal reads:

```text
results/cross_market_directed_graph_shadow_latest.json
```

Current pointer source:

```text
results/cross_market_directed_graph_shadow_full_conditional_20260715.json
```

## Main Backtest Result

Strict walk-forward, full target nodes:

```text
OOS rows = 1317
REENTER AUC = 0.485
REENTER balanced accuracy = 0.497
NO_ADD AUC = 0.532
NO_ADD balanced accuracy = 0.527
NO_ADD p@0.65 = 40.0%
```

Interpretation:

- NO_ADD has weak but repeatable signal.
- REENTER is unstable and should not be used.
- High-confidence alerts are intentionally sparse.

## Crash-Year Notes

Strict setting has no 2020 OOS because it requires two years of training data.
A short-training diagnostic version for 2020 showed only weak NO_ADD usefulness:

```text
2020 diagnostic:
NO_ADD AUC = 0.522
NO_ADD p@0.65 = 35.0%
REENTER AUC = 0.441
```

Best stress-year result was 2022 under the main `window=250` setting:

```text
2022:
NO_ADD AUC = 0.559
NO_ADD balanced accuracy = 0.541
NO_ADD p@0.65 = 44.4%
REENTER AUC = 0.449
```

## Conditional Evaluation

Risk-off conditioning did not materially improve reliability.

```text
All rows:
NO_ADD AUC = 0.532
NO_ADD p@0.65 = 40.0%

0050 5d <= -2%:
NO_ADD AUC = 0.477
NO_ADD p@0.65 = 38.9%

0050 10d <= -3%:
NO_ADD AUC = 0.467
NO_ADD p@0.65 = 35.3%

0050 60d drawdown <= -5%:
NO_ADD AUC = 0.520
NO_ADD p@0.65 = 40.9%

0050 abs 5d >= 2%:
NO_ADD AUC = 0.538
NO_ADD p@0.65 = 36.8%

00631L 5d <= -4%:
NO_ADD AUC = 0.524
NO_ADD p@0.65 = 38.9%
```

Do not gate Graph usage simply on recent 0050 selloff; it did not help.

## Ablation Summary

Full target nodes remain the default.

Single-node and pair ablations produced only small AUC changes, often with worse
high-confidence precision.

Best AUC candidate:

```text
minus 2330 + 2308:
NO_ADD AUC = 0.537
NO_ADD p@0.65 = 31.6%
```

This is not promoted because the live use case prioritizes alert quality over
small AUC gains.

## Live Integration

Daily signal includes:

```text
cross_market_graph_shadow
```

Execution plan includes:

```text
cross_market_graph_advisory
execution_summary.cross_market_graph_no_add_active
execution_summary.cross_market_graph_recommended_use
```

Both are advisory only.

## Regeneration Commands

Fetch source nodes:

```bash
.venv/bin/python scripts/fetch/fetch_cross_market_ohlcv.py \
  --start 2019-01-02 \
  --end 2026-07-16 \
  --tickers TSM,SOXX,QQQ,TWD=X,NVDA,AMD,ASML,AVGO,^TNX,2330.TW
```

Run main report:

```bash
.venv/bin/python scripts/evaluate/evaluate_cross_market_directed_graph_shadow.py \
  --start 2019-01-02 \
  --end 2026-07-15 \
  --edge-window 250 \
  --tstat-threshold 2.0 \
  --stability-threshold 0.20 \
  --min-windows 3 \
  --walk-forward-edge-selection \
  --min-train-days 504 \
  --retrain-step 252 \
  --output results/cross_market_directed_graph_shadow_latest.json
```

Validate integration:

```bash
.venv/bin/python -m pytest -q \
  tests/test_evaluate_cross_market_directed_graph_shadow.py \
  tests/test_group_a_plus_cross_market_graph_shadow.py \
  tests/test_group_a_plus_execution_plan_v2.py::ExecutionPlanV2Tests::test_execution_plan_reports_cross_market_graph_advisory_without_guarding_trades
```

## Final Decision

Keep the module, but keep it weakly scoped:

```text
Graph = NO_ADD_ONLY_SHADOW_FILTER
Alert threshold = 0.65
No automatic trade blocking
No REENTER usage
No target-node pruning for now
```
