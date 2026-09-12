# Production Pointer Backup-Before-Overwrite Protection — 2026-08-09

**Status: shipped. Detection/recovery mechanism only — never blocks a write, never changes what gets written.**

## Motivation

Earlier this session, a verification run of `daily_signal.py` without
`--output` silently overwrote the live production pointer
`report/group_a_plus/latest/live_signal.json` (recorded as
`feedback_production_pointer_scripts_need_output_redirect_for_testing` in
project memory). The established fix at the time was purely procedural —
"redirect output explicitly before test/verification runs" — which relies
on remembering every time, forever, across every session and every script
with this shape of default. This adds an actual mechanism instead of
relying only on discipline: a one-step "undo" path if it happens again,
and evidence to detect that it happened at all.

## What was built

**`tw_output_standard.py::backup_latest_pointer_before_overwrite(target)`**
(public, newly exposed — was previously going to be a private
`write_standard_output`-only helper, renamed once it became clear other
call sites needed it too): before a file under
`report/group_a_plus/latest/` gets overwritten, copies its current
content to a sibling `<name>.json.bak` file. No-ops if the target doesn't
exist yet (first write) or isn't under that directory. Deliberately keeps
only **one rolling generation**, not a growing history — every call
replaces the previous `.bak` — to keep disk cost bounded and predictable
(see `feedback_no_disk_warning_topic` in project memory: the user has
explicitly asked not to raise disk-space topics, so an unbounded-growth
design would be the wrong tradeoff here regardless of its other merits).

Called automatically from `write_standard_output()` — the shared JSON
output helper used by the large majority of scripts across this project
(confirmed via a 2026-08-09 research pass: "used by all shadow evaluator
scripts"). This alone covers `live_signal.json` (the file from the
original incident), `execution_plan.json`, `alert_state.json`,
`ops_health.json` (when written via the standardizer path),
`rebalance_review.json`, and essentially every `report/group_a_plus/latest/*`
producer that follows the `OutputStandardizer`/`write_standard_output`
convention with zero changes needed to any individual script.

Also retrofitted the handful of high-value governance/diagnostic writers
found to bypass `write_standard_output` with their own raw
`Path.write_text()` calls, since they were already surfaced while auditing
this:
- `group_a_plus/integrations/watchlist_news.py::write_watchlist_news_summary()`
  (covers `watchlist_news.json`)
- `scripts/run/run_ncf_daily_pipeline.py`'s direct writes to
  `strategy_env_health.json`, `ops_health.json` (its own inline write
  path, separate from the module-level one above), `risk_mechanism.json`,
  `strategy_trust.json`, and the FinMind-fallback branch of
  `watchlist_news.json`.

## Explicitly NOT covered (scope boundary, not silently claimed complete)

A full project-wide grep-and-patch of every raw `Path.write_text()` call
targeting `report/group_a_plus/latest/*` was **not** performed — only
sites discovered incidentally while investigating this task were fixed.
Known-unpatched examples, all lower-stakes (diagnostic/advisory-only, not
weight-affecting, per their own docstrings):
- The 4 pure-logging shadow-log "latest" snapshot writers built earlier the
  same day (`recovery_boost_spillover_gate_shadow.json`,
  `trough_override_eligibility_shadow.json`, `add_0050_instead_shadow.json`,
  `adaptive_review_interval_shadow.json`).
- `evaluate_00631l_0050_relative_reentry_opportunity.py`'s `latest_output`.
- `build_group_a_plus_cvar_tail_risk_diagnostic_snapshot.py`'s `latest_output`.
- `group_a_plus/portfolio/rebalance_audit.py`'s `rebalance_plan.json` — not
  individually audited for whether anything downstream treats it as
  authoritative; flagged here rather than assumed safe.

If a future incident involves one of these files, or a systematic sweep is
wanted, the natural next step is either extending `collect_readiness_review_freshness()`'s
approach (Task #20, `docs/READINESS_REVIEW_FRESHNESS_WATCHDOG_20260809.md`)
into a similar generic "find every write site" static sweep, or a manual
grep audit the same way this task's own scope was discovered.

## What this does NOT do

- Does not block or refuse any write — purely a backup side-effect before
  the normal write proceeds unchanged.
- Does not distinguish "legitimate daily automated write" from "accidental
  test-script write" — every overwrite of a protected path gets backed up,
  by design, since there's no reliable signal at this layer to tell them
  apart.
- Does not restore anything automatically — the `.bak` file is left for a
  human (or a future script) to inspect/restore manually.
- Does not add any locking — under this project's known concurrent
  multi-session activity, a race between two near-simultaneous writes to
  the same path is still possible (read-old, then write-backup, then
  write-new is not atomic). Not addressed here; this is a bounded,
  intentionally simple mechanism, not a full write-transaction system.

## Verification

New `tests/test_tw_output_standard.py` (6 tests): backup created for
existing files under `latest/`, no backup for first-time writes, no backup
outside `latest/`, backup is single-rolling-generation (not accumulating),
and both direct-call and `write_standard_output()`-integration paths
verified. Existing `tests/test_run_ncf_daily_pipeline.py` (21 tests) and
`tests/test_build_finmind_watchlist_news.py` +
`tests/test_group_a_plus_watchlist_news.py` (5 tests) all pass unchanged
after the retrofit — confirms the backup side-effect doesn't alter any
existing write's actual output content.

Also added `*.bak` to `.gitignore` — these files under
`report/group_a_plus/latest/` are tracked by git in this repo (unusual but
this project's existing convention), so without this the new `.bak`
siblings would show up as untracked files in every `git status`.

Full 1938-test suite run afterward (67 min): 1 failure
(`relative_reentry_opportunity::test_cli_writes_latest_output`), the same
pre-existing flaky test identified earlier the same day during the
rebalance_review fix (own isolated `tmp_path` output, untouched file,
passes standalone) -- confirmed passing standalone again, not a
regression from this change.
