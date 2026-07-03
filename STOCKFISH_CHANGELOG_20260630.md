# Stockfish-Inspired Change Log - 2026-06-30

## Objective

Analyze `C:\Users\isaac\Downloads\Stockfish-master\Stockfish-master` and test whether any useful ideas can be imported into the latest GroupA+ / A2118 strategy.

Final decision:

- Do not import Stockfish trading logic because Stockfish is a chess engine, not a financial model.
- Do not copy Stockfish source code because Stockfish is GPL-licensed.
- Import only the engineering idea of deterministic bench/signature verification.

## Files Added

### `scripts/evaluate/group_a_plus_strategy_signature.py`

New deterministic strategy bench/signature tool.

Default command:

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

Main behavior:

- Builds a stable strategy-critical payload.
- Excludes volatile fields such as timestamps, generated time, execution time, request date, and file paths.
- Produces a SHA-256 signature.
- Writes a standard wrapped JSON output through `tw_output_standard.OutputStandardizer`.
- Prints the same JSON to stdout for immediate inspection.

Current generated signature:

```text
6118f59437e8d0ad0ac115154292faefbc059d3361a47cf2e6247d887328bd86
```

### `tests/test_group_a_plus_strategy_signature.py`

New focused regression tests.

Test command:

```bash
.venv/bin/python -m pytest tests/test_group_a_plus_strategy_signature.py -q
```

Result:

```text
2 passed
```

Tests added:

- Signature remains stable when only volatile timestamps change.
- Signature changes when strategy-critical target weight changes.

### `results/group_a_plus_strategy_bench_signature.json`

Generated current strategy bench signature output.

Important summary values:

- Strategy: `a2118_a2111_ncf_late_bull_deleverage`
- Actual data date: `2026-06-29`
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

### `STOCKFISH_IMPORT_REVIEW_20260630.md`

Detailed review record.

Includes:

- Reviewed Stockfish files and transferable concepts.
- Why no direct alpha/code import was made.
- Implemented signature tool.
- Validation result.
- Current signature and recommended future workflow.

### `STOCKFISH_CHANGELOG_20260630.md`

This file.

Purpose:

- Keep a concise implementation-level record of the actual repository changes.

## Implementation Notes

### Stable Payload Design

The signature payload includes:

- Active strategy manifest and runner parameters.
- Daily live signal fields:
  - strategy id
  - actual data date
  - execution permission
  - base/execution regime
  - action
  - target weights
  - latest features
  - execution risk
  - NCF live overlay
  - factor lens gate
- Runner benchmark metrics and execution summary.
- NCF 00631L horizon probabilities, AUCs, ensemble confidence, and data freshness.
- Latest NCF panel row matched to `actual_data_date`.

The signature excludes:

- `generated_at`
- `timestamp`
- `execution_time_ms`
- `requested_as_of_date`
- `path`
- `files`

### Runtime Fixes During Implementation

Two issues were found and fixed while testing:

1. Direct script execution initially failed with:

   ```text
   ModuleNotFoundError: No module named 'group_a_plus'
   ```

   Fix:

   - Added repo-root bootstrap to `sys.path` inside `scripts/evaluate/group_a_plus_strategy_signature.py`.

2. Test execution initially failed because CSV-loaded boolean values were numpy scalar types and could not be JSON serialized:

   ```text
   TypeError: Object of type bool is not JSON serializable
   ```

   Fix:

   - Added scalar normalization through `.item()` inside the stable value converter.

## Validation Commands Run

```bash
.venv/bin/python -m pytest tests/test_group_a_plus_strategy_signature.py -q
```

Result:

```text
2 passed in 3.54s
```

```bash
.venv/bin/python scripts/evaluate/group_a_plus_strategy_signature.py
```

Result:

```text
success: true
signature: 6118f59437e8d0ad0ac115154292faefbc059d3361a47cf2e6247d887328bd86
```

## How To Use Going Forward

Before changing latest strategy:

```bash
.venv/bin/python scripts/evaluate/group_a_plus_strategy_signature.py --output results/group_a_plus_strategy_bench_signature_before.json
```

After changing latest strategy:

```bash
.venv/bin/python scripts/evaluate/group_a_plus_strategy_signature.py --output results/group_a_plus_strategy_bench_signature_after.json
```

Then compare:

- `summary.signature`
- `summary.execution_regime`
- `summary.target_weights`
- `summary.a2118_overlay`
- `summary.ncf`
- `summary.panel_latest`
- `summary.runner_metrics`

If the signature changed, inspect `signature_payload` to verify the changed fields are intended.

## Remaining Optional Improvements

Not implemented in this pass:

- `compare_strategy_signature.py` for field-level diff between two signature JSON files.
- Factor history table inspired by Stockfish history heuristic.
- Compute-budget planner for Optuna/retraining jobs inspired by Stockfish time management.

