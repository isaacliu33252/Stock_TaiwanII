# Archive Candidate - Stock_TaiwanII_FinRLX

Date: 2026-07-29

## Status

`Stock_TaiwanII_FinRLX/` is marked as an archive candidate, not deleted.

Current active/live strategy is:

- strategy id: `a2118_a2111_ncf_late_bull_deleverage`
- runner: `group_a_plus.runners.a2118`
- dispatcher: `group_a_plus.runners.latest`
- config: `report/group_a_plus/latest/strategy.json`

This directory is not the current live strategy implementation.

## Why This Is A Candidate

Repository search found no live import dependency on `Stock_TaiwanII_FinRLX/` outside this directory and historical checklist references.

The directory appears to be a standalone FinRL-X style prototype containing:

- backtest engine
- settings/config
- data loader
- strategy base classes
- RL portfolio strategy
- Alpaca-style trading adapter
- smoke test

## Do Not Delete Yet

Before moving this directory to `archive/`, confirm:

1. `group_a_plus.runners.latest` still dispatches to `group_a_plus.runners.a2118`.
2. `scripts/run/run_ncf_daily_pipeline.py` does not import or execute this directory.
3. Group A+ tests and FinRL bridge tests still pass.
4. No external notebook, local scheduled task, or manual workflow depends on this directory.

Suggested checks:

```bash
rg "Stock_TaiwanII_FinRLX" -n .
pytest tests/test_run_ncf_daily_pipeline.py
pytest tests/test_group_a_finrlx_bridge.py
python3 -m compileall group_a_plus scripts FinRL/v2 FinRL/data
```

## Related Handoff

See `FINRL_CONSOLIDATION_ARCHIVE_CANDIDATES_20260729.md` for the full consolidation decision record.
