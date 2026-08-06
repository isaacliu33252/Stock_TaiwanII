# Stockfish Import Review - 2026-06-30

## Scope

Reviewed local source:

- `C:\Users\isaac\Downloads\Stockfish-master\Stockfish-master`
- WSL path: `/mnt/c/Users/isaac/Downloads/Stockfish-master/Stockfish-master`

Target strategy repo:

- `C:\Users\isaac\Downloads\Stock_taiwan2-main\Stock_taiwan2-main`

Purpose:

- Check whether Stockfish has useful ideas that can improve the latest GroupA+ / A2118 strategy.
- Avoid copying Stockfish code because Stockfish is GPL-licensed and the domain is chess, not finance.

## Conclusion

No direct trading alpha should be imported from Stockfish.

Useful transferable ideas are engineering patterns:

1. Deterministic bench signature.
2. Reproducibility checks for strategy outputs.
3. Explicit benchmark summary before/after strategy changes.
4. Staged decision discipline similar to iterative deepening.
5. History/ranking heuristics as a possible future research direction for factor candidates.
6. Compute-budget control as a possible future pipeline improvement.

Implemented in this repo:

- `scripts/evaluate/group_a_plus_strategy_signature.py`
- `tests/test_group_a_plus_strategy_signature.py`
- `results/group_a_plus_strategy_bench_signature.json`

## Stockfish Files Reviewed

Important files and concepts:

- `src/search.cpp`
  - Search orchestration, iterative deepening, pruning, and move ordering.
  - Transferable concept: staged evaluation and strict comparison of decision outputs.

- `src/history.h`
  - History tables for ranking moves based on prior search usefulness.
  - Transferable concept: maintain empirical usefulness statistics for factor/rule candidates.

- `src/tt.cpp`
  - Transposition table/cache for repeated position evaluation.
  - Transferable concept: cache expensive repeated evaluation states. Lower priority for current strategy because the existing bottleneck is data/model freshness and validation, not repeated tree search.

- `src/timeman.cpp`
  - Time allocation under a search budget.
  - Transferable concept: pipeline budget manager for Optuna/retraining/backtest jobs.

- `tests/reprosearch.sh`
  - Reproducibility test using fixed search node counts.
  - Direct inspiration for the new deterministic strategy signature.

- `tests/signature.sh`
  - Bench signature extraction.
  - Direct inspiration for the new GroupA+ bench signature output.

## What Was Implemented

Added a deterministic strategy signature script:

```bash
.venv/bin/python scripts/evaluate/group_a_plus_strategy_signature.py
```

Default inputs:

- `results/group_a_plus_live_signal_v2.json`
- `results/group_a_plus_runner_latest_20260620.json`
- `results/ncf_00631l_20260630.json`
- `results/ncf_00631l_v5_tabnet_panel.csv`
- `report/group_a_plus/latest/strategy.json`

Default output:

- `results/group_a_plus_strategy_bench_signature.json`

The script builds a stable payload from strategy-critical fields:

- Active strategy metadata and parameters.
- Daily live signal regime, execution permission, action, weights, features, risk, NCF overlay, factor lens gate.
- Runner benchmark metrics and execution summary.
- NCF 00631L horizon probabilities, AUCs, ensemble confidence, data freshness, drawdown/gain risk.
- Latest NCF panel row matched to `actual_data_date`.

Volatile fields are excluded from the signature:

- `generated_at`
- `timestamp`
- `execution_time_ms`
- `requested_as_of_date`
- file paths inside payloads

This means rerunning the tool without changing strategy state should produce the same signature.

## Current Signature

Generated on current latest artifacts:

```text
6118f59437e8d0ad0ac115154292faefbc059d3361a47cf2e6247d887328bd86
```

Current summary:

- Strategy: `a2118_a2111_ncf_late_bull_deleverage`
- Data date: `2026-06-29`
- Execution regime: `ncf_late_bull_hedge`
- Execution allowed: `true`
- A2118 overlay applied: `true`
- A2118 overlay reason: `panel_trigger`
- H20 probability up: `0.2703`
- H5 probability up: `0.3576`
- NCF confidence: `0.6621`
- Target weights:
  - `0050.TW`: `0.7473586978`
  - `00631L.TW`: `0.0526413022`
  - `00632R.TW`: `0.0`
  - `00679B.TWO`: `0.0`
  - `cash`: `0.2`

## Validation

Focused tests added:

```bash
.venv/bin/python -m pytest tests/test_group_a_plus_strategy_signature.py -q
```

Result:

```text
2 passed
```

Test coverage:

1. Signature is stable when only volatile timestamps change.
2. Signature changes when a strategy-critical target weight changes.

## Recommendation

Keep this as a regression guard before and after future strategy changes.

Suggested workflow:

1. Run latest strategy pipeline.
2. Run:

   ```bash
   .venv/bin/python scripts/evaluate/group_a_plus_strategy_signature.py
   ```

3. Compare `results/group_a_plus_strategy_bench_signature.json`.
4. If signature changed, inspect the included `summary` and `signature_payload` to confirm the change is intended.

Next possible Stockfish-inspired improvements, not yet implemented:

- A compact `compare_strategy_signature.py` that compares two signature files and prints only changed fields.
- A factor history table that tracks which gates/features had useful out-of-sample contribution across rolling windows.
- A compute budget planner for Optuna/retraining jobs.

