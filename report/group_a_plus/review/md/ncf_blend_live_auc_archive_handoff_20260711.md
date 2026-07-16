# NCF blend_live_auc Verification Archive Handoff

Date: 2026-07-11

## Why

Follow-up to the GNHAR-RV investigation (`2606_03828_gnhar_forecast_prototype_handoff_20260711.md`).
Applying that paper's "pooled/global parameter beats independently-estimated
per-entity parameter" lesson elsewhere in this project surfaced
`group_a_plus/integrations/ncf.py`'s `ncf_dynamic_horizon_signal`: it blends a
stable multi-year OOS AUC prior (`DEFAULT_HORIZON_AUC_PRIORS`) with the
current run's live single-point validation AUC via `blend_live_auc=0.35`.
That default is a judgement call, never backtested against realized outcomes
-- and there was no archive of daily NCF signal snapshots long enough to
check it.

Do not change `ncf.py`'s `blend_live_auc` default based on this session's
work. This only builds the infrastructure to check it later.

## What was built

- `group_a_plus/integrations/ncf_signal_archive.py` -- pure module:
  `build_archive_row` (records raw per-horizon probability/AUC plus what
  `ncf_dynamic_horizon_signal` would output under several `blend_live_auc`
  candidates: 0.0/0.35/0.65/1.0), `append_archive_rows` (JSONL, dedup by
  ticker+date, including within a single batch -- caught a real duplicate,
  see below), `load_archive`, `evaluate_archive_against_realized` (joins
  against realized forward price direction, reports per-horizon hit rate per
  blend candidate, or `insufficient_data` with the current count).
- `scripts/evaluate/append_ncf_signal_archive.py` -- CLI. `--backfill` scans
  all existing `results/ncf_{00631l,00632r}_latest_YYYYMMDD.json` files;
  default (no flags) appends just today's stamp. Logging only, changes no
  decision.
- **Wired into `scripts/run/run_ncf_daily_pipeline.py`** as a new
  `ncf_signal_archive` step, added to `BEST_EFFORT_STEP_NAMES` (same
  non-blocking-failure treatment as `ohlcv_freshness`/`refresh_*`): runs
  right after `ncf_00632r` (so both 00631L/00632R JSON outputs already
  exist) and before `ncf_2330`. Verified with `--dry-run` that it lands at
  the correct position (step 12/22, `--date-stamp 20260711`), and updated
  `tests/test_run_ncf_daily_pipeline.py`'s two step-order assertions to
  include it (14/14 pass). A failure here is logged and skipped, same as any
  other best-effort step -- it can never block `ncf_2330`, `daily_signal`,
  `alert_state`, or the push notification below it.
- `scripts/evaluate/evaluate_ncf_blend_live_auc_archive.py` -- CLI. Joins the
  archive against `FinRL/data/stock_data.db` close prices and reports hit
  rate per horizon per blend candidate once `min_samples` (default 30) exist.
- `tests/test_group_a_plus_ncf_signal_archive.py` -- 9 tests, including a
  regression test for the within-batch dedup bug found and fixed below.

## Bug found and fixed during backfill

`ncf_00631l_latest_20260703.json` and `ncf_00631l_latest_20260702.json` both
report `last_close_date: 2026-07-02` (the 07-03 snapshot appears stale/stuck
on the prior trading day's data). `append_archive_rows` originally only
deduplicated new rows against rows already persisted to disk, not against
each other within the same call -- so backfilling both files in one run wrote
two rows for the same (ticker, date). Fixed to also dedupe within the batch;
re-backfilled cleanly (22 source files -> 20 archive rows, was 22).

## Current state (2026-07-11)

Archive backfilled from all 11 existing daily snapshots (2026-06-25 to
2026-07-09, both tickers): 20 rows.

Running the evaluation today:

- h=1: insufficient_data (n=18, need >=30)
- h=5: insufficient_data (n=12, need >=30)
- h=20: insufficient_data (n=0, need >=30)

This is expected, not a bug. h=20 needs 20 trading days to elapse after each
archived date before a realized outcome exists -- the archive doesn't span
that yet. At roughly one new snapshot per trading day, `min_samples=30` for
h=1 needs ~6 more weeks of accumulation from today; h=5 needs a bit longer;
h=20 needs roughly 4-5 months minimum (30 independent windows x ~20 trading
days, though windows overlap so the wall-clock time is shorter than that
naive multiplication -- realistically 2-3 months once daily appends resume).

## Decision

Do not promote or change `ncf.py`'s `blend_live_auc`. Infrastructure only.

- Yes: archive module, CLI scripts, tests exist and pass.
- Yes: backfilled with all currently-available historical snapshots (20
  rows).
- Yes: wired into the daily pipeline as a best-effort step -- the archive
  will now grow by up to 2 rows (00631L + 00632R) each day the pipeline runs,
  with no ability to affect any trading decision if it fails.
- No: any conclusion about blend_live_auc -- current sample sizes are far
  below `min_samples=30` at every horizon.
- Next actual test (not before the archive has enough rows): re-run
  `evaluate_ncf_blend_live_auc_archive.py` in a few months and compare
  candidates the same way the GNHAR-RV work did -- hit rate plus a
  Diebold-Mariano-style significance check before trusting any apparent edge.

## Verification

- `.venv/bin/python -m pytest tests/test_group_a_plus_ncf_signal_archive.py` -- 9 passed.
- `.venv/bin/python -m py_compile group_a_plus/integrations/ncf_signal_archive.py scripts/evaluate/append_ncf_signal_archive.py scripts/evaluate/evaluate_ncf_blend_live_auc_archive.py scripts/run/run_ncf_daily_pipeline.py` -- passed.
- `.venv/bin/python scripts/evaluate/append_ncf_signal_archive.py --backfill` -- 20 rows written to `results/ncf_signal_archive.jsonl`.
- `.venv/bin/python scripts/evaluate/evaluate_ncf_blend_live_auc_archive.py` -- correctly reports `insufficient_data` at all horizons; output saved to `results/ncf_blend_live_auc_archive_evaluation_latest.json`.
- `.venv/bin/python scripts/run/run_ncf_daily_pipeline.py --dry-run` -- confirms `ncf_signal_archive` lands at step 12/22, right after `ncf_00632r` and before `ncf_2330`.
- `.venv/bin/python -m pytest tests/test_run_ncf_daily_pipeline.py` -- 14 passed (2 step-order assertions updated to include the new step).
