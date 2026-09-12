# Readiness-Review Freshness Watchdog — 2026-08-09

**Status: shipped, wired into daily ops_health/alert_state chain. Detection-only, no execution/weight impact.**

## Motivation

The readiness-review `as_of` staleness fix earlier the same day
(see `docs/READINESS_REVIEW_AS_OF_STALENESS_AUDIT_20260808.md`) was found by
accident three separate times in one bug — a producer script's input+output
both pinned to a dated filename, plus two hardcoded date strings in its
payload, plus 6 of 9 consumers independently pinning their own separate
stale input. Nothing in the existing health-check infrastructure
(`ops_health.py`, `alert_state.py`, `check_ohlcv_freshness.py`) would have
caught this class of bug automatically, because every existing freshness
check compares **mtimes** (file A vs file B, or file vs now) — and these
files' mtimes were always fresh (`generated_at` updated every day). The bug
was invisible to mtime-based checks; only the JSON payload's own `as_of`
field was frozen.

## What was built

Extended `group_a_plus/operations/ops_health.py` (not a new parallel
mechanism — confirmed via research that this project already has
substantial per-artifact freshness infra bespoke-scoped to specific
tables/tickers/files, so a new generic sweep belongs alongside it, not next
to it):

- `collect_readiness_review_freshness()`: sweeps every
  `report/group_a_plus/latest/*.json`, extracts a self-reported "as of" date
  via `_extract_as_of()` (tries `as_of`, `dates.requested_as_of_date`,
  `dates.actual_data_date`, `requested_as_of_date`, `actual_data_date` in
  order — covers both flat and nested payload conventions seen across this
  project's ~30 `build_group_a_plus_*` scripts), and cross-references
  against which files `run_ncf_daily_pipeline.py` actually writes to
  (`_pipeline_wired_latest_basenames()`, found by regexing the pipeline
  script's source text for `"group_a_plus" / "latest" / "X.json"` /
  `report/group_a_plus/latest/X.json` patterns — deliberately does not
  import/execute the pipeline module, keeping this check cheap and
  side-effect-free).
- Two distinct failure modes surfaced, matching the two ways this class of
  bug actually occurs in this project:
  - **`stale_despite_wiring`** (error): file IS regenerated daily but
    `as_of` is stale beyond `max_lag_business_days` (default 3) — the exact
    bug class just fixed. Business-day lag computed via
    `daily_signal.py::_business_days_between`, already imported into
    `ops_health.py`.
  - **`orphaned_stale`** (warning): file is NOT referenced anywhere in the
    daily pipeline and its `as_of` is stale — either a legitimate one-off
    research snapshot (see `KNOWN_FROZEN_LATEST_ARTIFACTS` allowlist:
    `reduced_rank_correlation_readiness_review.json`,
    `rl_governance_readiness_review.json`,
    `heterogeneous_vol_regime_advisory.json` — all three previously
    confirmed-expected-frozen in the 2026-08-08 audit and this session — in
    which case it's reported as `frozen_expected` and produces no
    warning), or a script that quietly stopped being scheduled and nobody
    noticed. New one-off scripts don't silently join the allowlist; a human
    has to add them.
- Wired into `build_ops_health()`'s `sections` dict as
  `readiness_review_freshness`, so it participates in the existing
  top-level `errors`/`warnings`/`status` roll-up the same as every other
  section.
- Wired into `alert_state.py::_ops_health_error_alerts()` as a new
  `ops_health_readiness_review_stale` alert type (`level: medium` — these
  are all research/promotion-gate documents, not weight-affecting, matching
  this function's existing severity convention for detection-only,
  manual-follow-up issues), so it flows through the same
  emit/cooldown/push chain as every other signal alert instead of sitting
  unread in `ops_health.json`.

## Verification

12 new unit tests (6 in `tests/test_group_a_plus_ops_health.py` covering
`stale_despite_wiring`, `fresh`, `frozen_expected`, `orphaned_stale`,
`no_as_of_field`, and end-to-end wiring into `build_ops_health`; 2 in
`tests/test_group_a_plus_alert_state.py` covering the new alert type firing
and staying silent when the section is `ok`). Full `tests/test_group_a_plus_ops_health.py`
(35) and `tests/test_group_a_plus_alert_state.py` (27) suites pass.

Ran end-to-end against real production data
(`report/group_a_plus/latest/*.json`, 255 files swept): correctly
identified all 9 previously-known-stale rebalance-review-family consumers
(still showing stale in the real production files, as expected, since only
the code fix and scratch-redirected verification runs have happened so
far — the real daily pipeline hasn't regenerated them since the fix landed)
**plus 2 new, previously-undiscovered `stale_despite_wiring` findings**:
`broker_holdings_reconciliation_review.json` (as_of 2026-07-17, 15 business
days stale) and `synthetic_augmentation_validation_readiness_review.json`
(as_of 2026-07-20, 14 business days stale) — neither part of the
rebalance_review family, found purely by the new generic sweep. Ran
`update_alert_state_from_files()` against the real ops_health output and
confirmed the new alert fires with the correct combined reason text.

## Root-cause follow-up on the 2 new findings (same day)

Both investigated to completion; neither required a producer-script fix.

- **`synthetic_augmentation_validation_readiness_review.json`**: not an
  independent bug. `build_group_a_plus_synthetic_augmentation_validation_readiness_review.py:138-141`
  derives its own `as_of` as `dynamic_cvar.get("as_of") or hmm_wj.get("as_of")
  or _nested(finstressts, "summary", "as_of")` — and
  `dynamic_cvar_tail_cost_readiness_review.json` is one of the 9
  rebalance_review-family consumers already fixed earlier the same day.
  Confirmed both files show identical `as_of: 2026-07-20` at
  near-identical `generated_at` timestamps (03:02:49 / 03:02:54) — a direct
  cascade, not a separate defect. Will self-resolve automatically once the
  real daily pipeline reruns with the already-landed fix; no further code
  change needed.
- **`broker_holdings_reconciliation_review.json`**: genuinely not a code
  bug. Its `as_of` honestly reflects `coverage.last_transaction_date` from
  `broker_holdings_time_series_sample.json`, which is built
  (`build_group_a_plus_broker_holdings_time_series_sample.py:21`) from a
  hardcoded manual broker transaction export, `isaac_tra_20260718.xlsx`.
  Confirmed via filesystem search that no newer `isaac_tra_*.xlsx` exists
  anywhere in the repo — there's no silently-ignored newer file, the
  script is correctly reporting the last real transaction in the only
  ledger available. Same category as `execution_plan.json`'s
  manually-maintained portfolio workbook
  (`_execution_plan_freshness` docstring: "cannot be safely
  auto-regenerated... user must regenerate it manually"). **Requires the
  user to export fresh transaction data, not a code fix.**

**Watchdog refinement applied as a result**: the generic
`stale_despite_wiring` (error) classification was actively *wrong* for
`broker_holdings_reconciliation_review.json` — it IS regenerated daily, but
its content can never get fresher just by re-running the pipeline, so
flagging it at the same severity/tolerance as a real code-bug staleness
case would be permanent, uninformative noise. Added
`MANUALLY_SOURCED_LATEST_ARTIFACTS` (mirrors `KNOWN_FROZEN_LATEST_ARTIFACTS`'s
pattern but for "wired, daily-regenerated, yet content is manually-source-
bounded" rather than "never regenerated at all"): downgrades this specific
file to a new `manually_sourced_stale` status (warning, not error) with a
reason explaining what the user needs to do. 1 new test added (7 total for
this feature now). Re-verified against real data: `stale_despite_wiring`
count dropped from 9 to 8 (all 8 remaining are the rebalance_review family
+ its one cascade, both already fixed in code and pending only a real
pipeline rerun); `broker_holdings_reconciliation_review.json` now correctly
reports `manually_sourced_stale`.

## Design choices worth remembering

- **mtime checks and as_of-field checks catch different bug classes** —
  this project had extensive mtime-based freshness checks before this and
  they never would have caught the rebalance_review bug. Any future
  freshness work should check both, not assume mtime is a sufficient proxy
  for "is the content actually current."
- **No canonical daily-vs-frozen artifact list existed anywhere in the
  repo** before `KNOWN_FROZEN_LATEST_ARTIFACTS` — this is now the first
  and only such list. If future sessions confirm another artifact is
  intentionally never-automated, add it here rather than re-deriving from
  scratch or leaving it to keep generating warning noise.
- Deliberately did NOT try to auto-regenerate anything or auto-fix
  `orphaned_stale` findings — detection-only, matching every other
  `*_freshness` helper in `ops_health.py` and this module's own docstring
  ("must not start/stop services, mutate files, or influence active
  allocation").
