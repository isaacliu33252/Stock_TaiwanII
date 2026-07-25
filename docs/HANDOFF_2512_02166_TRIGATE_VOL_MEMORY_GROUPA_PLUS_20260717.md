# Handoff: 2512.02166 Tri-Gate Volatility Memory for GroupA+（2026-07-17）

## Source

- PDF: `C:\Users\isaac\Downloads\2512.02166.pdf`
- Title: `The Three-Dimensional Decomposition of Volatility Memory`
- Active strategy: `a2118_a2111_ncf_late_bull_deleverage`

## Imported Benefit

Imported only as research / governance:

- volatility-memory level gate
- volatility-memory shape / long-memory proxy
- volatility-memory tempo / business-time proxy
- separation of persistent volatility from transient bursts
- leverage add should respect volatility memory, not just point forecast

Not imported:

- full TG-Vol QMLE estimator
- G-FIGARCH fractional-order estimation
- SPY / EURUSD empirical parameters
- automatic rebalance
- direct `00631L` add signal

## Artifacts

Review docs:

- `docs/2512_02166_TRIGATE_VOL_MEMORY_GROUPA_PLUS_REVIEW_20260717.md`
- `docs/GROUPA_PLUS_PDF_RESEARCH_DECISION_MATRIX_20260717.md`

Scripts:

- `scripts/evaluate/evaluate_group_a_plus_trigate_vol_memory_shadow.py`
- `scripts/run/run_ncf_daily_pipeline.py`

Tests:

- `tests/test_group_a_plus_trigate_vol_memory_shadow.py`
- `tests/test_run_ncf_daily_pipeline.py`

Reports:

- `results/group_a_plus_trigate_vol_memory_shadow_20260717.json`
- `report/group_a_plus/latest/trigate_vol_memory_shadow.json`

## Current Result

Latest date: `2026-07-17`

- `state = blocked_for_leverage_add`
- `stress_gate_count = 3`
- level gate active:
  - 00631L 20-day annualized volatility: `0.7395`
  - 252-day percentile: `0.9325`
- shape gate active:
  - memory shape score: `0.8211`
  - 252-day percentile: `0.9762`
- tempo gate active:
  - tempo score: `7.4887`
  - 252-day percentile: `1.0000`
- 60-day 0050/00631L return correlation: `0.9806`

Decision:

- `allow_00631l_add = false`
- `auto_rebalance_allowed = false`
- `target_weight_change_allowed = false`
- `keep_golden1_0531_unchanged = true`

## Daily Pipeline

Added best-effort step:

- `trigate_vol_memory_shadow`

This is diagnostic only. Failure does not block downstream live status, and
success never unlocks execution.

## Daily Status

Added:

- `scripts/misc/check_group_a_plus_daily_status.py` accepts
  `--trigate-vol-memory-shadow`.
- `scripts/run/run_ncf_daily_pipeline.py` passes
  `report/group_a_plus/latest/trigate_vol_memory_shadow.json` into daily status.
- Markdown daily status renders `## Tri-Gate Volatility Memory Shadow` when the
  snapshot exists.

Smoke output:

- `results/group_a_plus_daily_status_20260720_research_shadow_smoke.json`
- `results/group_a_plus_daily_status_20260720_research_shadow_smoke.md`
- `results/group_a_plus_daily_status_20260720_research_shadow_summary_smoke.json`
- `results/group_a_plus_daily_status_20260720_research_shadow_summary_smoke.md`
- `results/group_a_plus_daily_status_20260718_research_shadow_smoke.json`
- `results/group_a_plus_daily_status_20260718_research_shadow_smoke.md`

Smoke result:

- `overall_status = block`
- `Tri-Gate Volatility Memory Shadow` section is present
- `Research Shadow Decision Snapshot` section is present
- `state = blocked_for_leverage_add`
- `stress_gate_count = 3`
- `00631L add = blocked`
- 2026-07-18 smoke remains blocked; data freshness is `0` business days stale
  and `1` calendar day stale because 2026-07-18 is a Saturday.

## Research Shadow Summary

Added:

- `scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py`
- `tests/test_build_group_a_plus_research_shadow_decision_snapshot.py`
- `docs/RESEARCH_SHADOW_DECISION_SNAPSHOT_20260717.md`
- `report/group_a_plus/latest/research_shadow_decision_snapshot.json`

Current result:

- `status = blocked`
- blockers:
  - `finstressts_snapshot_blocked`
  - `trigate_vol_memory_blocks_leverage_add`
- `allow_00631l_add = false`

## Verification

Commands run:

- `.venv/bin/python -m py_compile scripts/evaluate/evaluate_group_a_plus_trigate_vol_memory_shadow.py scripts/run/run_ncf_daily_pipeline.py`
- `.venv/bin/python -m pytest tests/test_group_a_plus_trigate_vol_memory_shadow.py tests/test_run_ncf_daily_pipeline.py`
- `.venv/bin/python -m pytest tests/test_check_group_a_plus_daily_status.py tests/test_run_ncf_daily_pipeline.py tests/test_group_a_plus_trigate_vol_memory_shadow.py`
- `.venv/bin/python -m pytest tests/test_build_group_a_plus_research_shadow_decision_snapshot.py tests/test_check_group_a_plus_daily_status.py tests/test_run_ncf_daily_pipeline.py tests/test_group_a_plus_trigate_vol_memory_shadow.py`

Result:

- `17 passed`

## Final Decision

Keep unchanged:

- GroupA+ latest strategy
- `Golden1_0531`
- `2026-07-20` execution block

Do not:

- auto-rebalance
- add `00631L`
- promote tri-gate volatility memory to live alpha
