# Project Review, DFL Pipeline Defaults, and FinRL v2 Reward Fix Handoff - 2026-07-29

## Status

Reviewed the current project state after the user asked whether the recent
updates were OK, then made two low-risk reliability fixes:

1. Fixed a real DFL daily-pipeline stale-input regression in
   `scripts/run/run_ncf_daily_pipeline.py`.
2. Fixed `FinRL/v2/environments/reward_function.py` so
   `RewardConfig.capital_reward_weight` is no longer a dead setting while
   preserving the newly intended daily-return reward scale by default.

Both changes are code/test-only and do not change Group A+'s live target
weights directly.

## Starting Point

The repo had a very large dirty worktree before this session began:

- Many modified `report/group_a_plus/latest/*` and history JSON/MD/HTML
  outputs.
- Several modified Group A+ scripts and tests.
- New untracked handoff files for 2026-07-26/2026-07-27 work.
- New untracked code under `group_a_plus/core/`.
- New untracked evaluation/backtest scripts and tests.

Important: this handoff documents only the review and fixes performed in
this session. It does not claim ownership of all pre-existing dirty files.

## Review Findings

Initial checks:

- `git status --short`: large dirty tree, including code and generated
  reports.
- `git log --oneline -n 8`: latest committed state was
  `d39063e Upload 2026-07-25 full project state: Group A+ latest, Fable audit, daily signal improvements`.
- `git diff --stat`: 101 tracked files changed, roughly 6181 insertions /
  3626 deletions at the time of the first review, before this session's
  additional edits.

Relevant test/compile checks run before making fixes:

- `pytest tests/test_signal_contract.py tests/test_point_in_time_store.py tests/test_group_a_plus_tail_conformal.py tests/test_run_ncf_daily_pipeline.py tests/test_check_group_a_plus_daily_status.py tests/test_evaluate_a2118_decision_focused_action_shadow.py tests/test_evaluate_ncf_panel_drift.py tests/test_ncf_00631l_paths.py`
  - Result: 103 passed, 1 third-party deprecation warning.
- `pytest tests/test_ncf_decision_calibration.py tests/test_evaluate_ncf_panel_drift.py tests/test_evaluate_a2118_decision_focused_action_shadow.py`
  - Result: 51 passed.
- `python3 -m compileall group_a_plus scripts FinRL/v2 FinRL/data`
  - Result: passed.
- A full bare `pytest` was attempted, but it ran for several minutes with no
  progress output while consuming CPU. It was interrupted to avoid leaving a
  long-running background session. No full-suite result is available from
  this session.

## Fix 1: DFL CLI Defaults Still Pointed at Dated Snapshots

### Problem

`build_commands()` in `scripts/run/run_ncf_daily_pipeline.py` had already
been updated by prior work to use stable DFL latest files:

- `results/a2118_decision_focused_action_shadow_dfl_main_latest.json`
- `results/a2118_decision_focused_action_shadow_dfl_selective_p50_latest.json`
- `results/a2118_decision_focused_action_shadow_dfl_selective_p70_latest.json`
- `results/a2118_decision_focused_action_overlap_dfl_latest.json`

However, `parse_args()` still used old dated defaults:

- `results/a2118_decision_focused_action_shadow_fixed_7win_20260714_rerun.json`
- `results/a2118_decision_focused_action_shadow_selective_p50_7win_20260714.json`
- `results/a2118_decision_focused_action_shadow_selective_p70_7win_20260714.json`
- `results/a2118_decision_focused_action_overlap_fixed_7win_20260714_rerun.json`

Because argparse populates those attributes before `build_commands()` runs,
the intended stable default in `getattr(args, ..., stable_default)` was not
actually used in normal CLI execution. In practice, running the daily
pipeline from the command line could still read stale July 14 DFL artifacts
even though `build_commands()` looked fixed.

### Change

Updated `parse_args()` defaults in:

- `scripts/run/run_ncf_daily_pipeline.py`

Now the CLI defaults match the stable latest filenames used by
`build_commands()`.

### Test Added

Added `test_parse_args_dfl_defaults_use_stable_latest_files` in:

- `tests/test_run_ncf_daily_pipeline.py`

The test monkeypatches `sys.argv` to simulate default CLI parsing and
asserts all DFL defaults use the stable latest files.

## Fix 2: FinRL v2 Reward Weight Was a Dead Setting

### Problem

Recent work changed `FinRL/v2/environments/reward_function.py` to compute
capital reward from daily portfolio return instead of cumulative return
relative to initial capital. That scale change is reasonable and reduces
large reward drift over a training episode.

But the change had also made `RewardConfig.capital_reward_weight` ineffective:

```python
capital_reward = portfolio_return
```

while `RewardConfig` still exposed:

```python
capital_reward_weight: float = 100.0
```

This was risky because a training configuration could appear to tune
`capital_reward_weight` while the value had no effect. Existing tests did
not cover this; `rg capital_reward_weight` showed no test usage and no
other real references besides the config and debug print.

### Change

Updated `FinRL/v2/environments/reward_function.py`:

- `capital_reward_weight` default changed from `100.0` to `1.0`.
- Capital reward calculation now applies the weight:

```python
capital_reward = portfolio_return * self.config.capital_reward_weight
```

The default was set to `1.0` deliberately to preserve the newly intended
daily-return reward scale. This avoids unexpectedly restoring the old
100x scale while making the config knob real again.

The daily-return logic remains:

- Use `(current - previous) / previous` when `prev_metrics.portfolio_value > 0`.
- Fall back to initial-capital return for first/invalid previous metrics.
- Clamp raw one-step return to +/-10% before applying the configured weight.

### Test Added

Created:

- `tests/test_finrl_v2_reward_function.py`

Coverage:

- Default daily-return reward stays at the unscaled daily-return value.
- Custom `RewardConfig(capital_reward_weight=2.5)` changes the reward.
- Clamp happens before weighting.

## Verification After Fixes

Targeted tests:

```bash
pytest tests/test_finrl_v2_reward_function.py tests/test_run_ncf_daily_pipeline.py
```

Result:

- 23 passed.

Compile check:

```bash
python3 -m compileall FinRL/v2/environments/reward_function.py tests/test_finrl_v2_reward_function.py scripts/run/run_ncf_daily_pipeline.py tests/test_run_ncf_daily_pipeline.py
```

Result:

- Passed.

No long-running shell sessions were left active.

## Files Touched by This Session

Primary files changed by this session:

- `FinRL/v2/environments/reward_function.py`
- `scripts/run/run_ncf_daily_pipeline.py`
- `tests/test_run_ncf_daily_pipeline.py`
- `tests/test_finrl_v2_reward_function.py` (new)

This session also created this handoff:

- `GROUP_A_PLUS_PROJECT_REVIEW_AND_REWARD_PIPELINE_FIX_HANDOFF_20260729.md`

Note: `scripts/run/run_ncf_daily_pipeline.py` and
`tests/test_run_ncf_daily_pipeline.py` already had substantial uncommitted
changes before this handoff, including prior DFL shadow refresh wiring and
same-method-baseline governance-chain tests. This session's incremental
change in those files is specifically the argparse DFL-default fix and the
new parse-args regression test.

## Important Remaining Risks

### 1. Full test suite was not completed

A full `pytest` run was attempted but interrupted after several minutes
with no progress output. Targeted tests passed, but there is no full-suite
green result from this session.

Recommended next step:

Run a full suite in a long-running shell or CI-like environment where heavy
tests are expected:

```bash
pytest
```

If it hangs, identify the slow test with:

```bash
pytest -vv
```

or split by directories.

### 2. Very large dirty worktree remains

The worktree still contains many modified and untracked generated reports,
handoff docs, scripts, and tests. Do not blindly commit everything.

Recommended next step:

Separate into at least three groups before commit:

- Code/test changes that should be versioned.
- Generated report/history outputs that are intentionally part of the
  project state.
- Accidental runtime artifacts such as `__pycache__` files.

### 3. `__pycache__` scan was noisy

An exploratory `find . -path '*/__pycache__/*' -print` found a huge number
of cache files, including under `.venv` and `.claude/worktrees`. That scan
was stopped and no cleanup was performed, because destructive cleanup across
the whole repo would be too broad for this session.

Recommended next step:

If cleanup is desired, scope it carefully and exclude `.venv`,
`.claude/worktrees`, and any user-managed worktrees unless explicitly
approved.

### 4. Reward-scale semantics still deserve training validation

The reward fix keeps default scale at daily-return magnitude and restores
config effectiveness. It does not prove the new scale is optimal for RL
training.

Recommended next step:

Before relying on this for a production training run, compare at least:

- `capital_reward_weight=1.0` (current default)
- `capital_reward_weight=10.0`
- `capital_reward_weight=100.0` (old nominal config value)

using the same seed/window and compare reward stability, turnover, final
portfolio value, and drawdown.

## Suggested Resume Checklist

1. Review `git diff -- FinRL/v2/environments/reward_function.py tests/test_finrl_v2_reward_function.py`.
2. Review `git diff -- scripts/run/run_ncf_daily_pipeline.py tests/test_run_ncf_daily_pipeline.py`.
3. Run targeted tests again if anything changed:

```bash
pytest tests/test_finrl_v2_reward_function.py tests/test_run_ncf_daily_pipeline.py
```

4. Decide whether to run full `pytest` or split it into smaller suites.
5. Stage only intended code/test/handoff files, not the entire dirty tree.

