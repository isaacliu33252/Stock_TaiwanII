# Production / Shadow Boundary

Status: phase-1 guardrail, no file moves yet.

This repository currently contains production runners, shadow research, handoff
notes, audits, and experiment artifacts in overlapping locations. The first
goal is to make the boundary explicit before moving files.

## Production Allowlist

Production means a file may directly affect live signal generation,
rebalance planning, dashboard status, or broker read-only holdings workflows.

Current production sources of truth:

- `report/group_a_plus/latest/strategy.json`
- `report/group_a_plus/latest/live_signal.json`
- `report/group_a_plus/latest/execution_plan.json`
- `report/group_a_plus/latest/ops_health.json`
- `group_a_plus/`
- `scripts/run/run_ncf_daily_pipeline.py`
- `scripts/run/run_group_a_combined_signal.py`
- `FinRL/data/stock_db.py`
- `FinRL/data/stock_data.db`
- `results/group_a_combined_live_latest.json`
- `results/group_a_combined_live_latest.csv`
- `results/group_a_combined_bundle_latest.json`

Compatibility production dependencies that must not be moved without a
dedicated migration:

- root GroupA+ backtest/policy helpers imported by active runners
- `FinRL/backtesting`
- `FinRL/v2/backtesting/performance_metrics.py`

## Shadow / Research Areas

Shadow and research outputs may inform future decisions, but must not change
live allocation unless a separate promotion record updates the active strategy
manifest and production tests.

Preferred locations for new work:

- `research/` for research notes, reviews, shadow-only reports, prototypes, and
  non-production observations.
- `experiments/` for sweeps, ablations, parameter searches, and one-off model
  trials.
- `handoff/` for session handoff notes and migration logs.
- `archive/` for code or documents explicitly removed from active use after
  guard tests pass.

Existing scattered files are legacy debt. Do not bulk-move them until call
sites, import sites, and report readers have been checked.

## Boundary Rules

1. Active production manifest fields must not point into `research/`,
   `experiments/`, `handoff/`, or `archive/`.
2. A shadow report must declare one of:
   - `active_allocation_impact: none`
   - `research_only: true`
   - a `policy` string containing `research_only` or `shadow`
3. Promotion from shadow to production requires:
   - a decision record
   - active manifest update
   - runner smoke test
   - production/shadow boundary guard test
4. New handoff documents should go under `handoff/YYYY-MM/` unless they are
   source-of-truth release documents.
5. New sweeps and ablations should write under `experiments/` or a clearly
   research-only report path, not root.
6. Existing production paths may continue to read legacy root files until a
   compatibility migration is explicitly implemented.

## Phase Plan

Phase 1:

- Add this boundary document.
- Add placeholder directories for `research/`, `experiments/`, `handoff/`, and
  `archive/`.
- Add a guard test that prevents the active production manifest from pointing
  into research-only directories.

Phase 2:

- Add an index of root handoff/research files and classify them.
- Move Markdown-only legacy handoff files in small batches.
- Keep compatibility links or update references when documents are moved.

Phase 3:

- Move shadow-only scripts only after `rg` import/call-site checks.
- Add CI checks for production import boundaries.
- Update daily pipeline outputs so shadow artifacts land in explicit shadow or
  research paths.

