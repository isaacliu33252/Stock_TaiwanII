# Readiness-Review `as_of` Staleness Audit - 2026-08-08

Investigation of 4 papers' readiness-review JSONs flagged during the
2026-08-05/06 Fable paper audit as all showing `as_of=2026-07-20`, to
determine whether that is expected (one-off research artifact, never
rerun) or an active bug (should update but silently isn't).

## Finding: two different situations, not one

**2107.09048 (reduced_rank_correlation) and 2512.10913 (rl_governance) -- expected, not a bug.**

- `report/group_a_plus/latest/reduced_rank_correlation_readiness_review.json`
  (generated_at 2026-07-19T23:56, unchanged since)
- `report/group_a_plus/latest/rl_governance_readiness_review.json`
  (generated_at 2026-07-20T00:19, unchanged since)
- Neither `build_group_a_plus_reduced_rank_correlation_readiness_review.py`
  nor `build_group_a_plus_rl_governance_readiness_review.py` is referenced in
  `scripts/run/run_ncf_daily_pipeline.py` or
  `scripts/misc/check_group_a_plus_daily_status.py`. These were one-off
  manual research runs and were never wired into any automation. A frozen
  `as_of` on a file nothing ever reruns is correct, not a bug. No action
  needed.

**2511.12476 (asian_etf_tail_analytics) and 2606.26625 (dynamic_cvar_tail_cost) -- real active bug.**

- Both scripts ARE in the daily pipeline
  (`run_ncf_daily_pipeline.py` lines ~232, ~257/1248/1374) and DO regenerate
  daily -- confirmed `generated_at: 2026-08-06T03:0x` on both files, newer
  than the other two above.
- But both still report `as_of: "2026-07-20"` despite the fresh
  `generated_at`. Root cause: both scripts derive `as_of` from
  `_nested(rebalance, "dates", "requested_as_of_date")`, where `rebalance` is
  loaded from `DEFAULT_REBALANCE = report/group_a_plus/latest/rebalance_review_20260720.json`
  -- a **permanently pinned, date-stamped filename**, not a "latest"
  undated pointer.
- That file's producer, `build_group_a_plus_rebalance_review.py`, hardcodes
  its own `DEFAULT_OUTPUT` to that exact same dated filename
  (`.../rebalance_review_20260720.json`) rather than an undated `latest`
  path. And that builder itself is **not called anywhere in
  `run_ncf_daily_pipeline.py`** -- it was run manually once
  (file mtime 2026-07-17T18:06) and never again.
- Net effect: every day the two downstream readiness reviews regenerate with
  fresh CVaR / market-impact / systemic-bubble inputs, but their `as_of`
  label (and the `dates.execution_plan_stale_vs_live` framing they inherit
  from the pinned rebalance snapshot) has been silently frozen at
  2026-07-20 since day one. As of today that label is over two weeks wrong,
  and it will keep drifting indefinitely -- nothing will ever correct it on
  its own.

## Blast radius (not yet fully mapped)

`grep -rl "rebalance_review_20260720"` under `scripts/` turns up at least
10 builder scripts referencing this same pinned filename as their
`DEFAULT_REBALANCE` (asian_etf_tail_analytics and dynamic_cvar_tail_cost
confirmed above as pipeline-wired; `build_group_a_plus_deep_hedging_overlay_review.py`,
`build_group_a_plus_adversarial_market_integrity_review.py`,
`build_group_a_plus_sciphyrl_readiness_review.py`,
`build_group_a_plus_finpilot_lite_planning_review.py`,
`build_group_a_plus_intervention_fatigue_risk_budget_readiness_review.py`,
`build_group_a_plus_finstressts_readiness_review.py`, and
`build_group_a_plus_market_impact_readiness_review.py` also reference it but
were not individually checked for daily-pipeline membership in this pass).
Any of these that are pipeline-wired likely have the same frozen-`as_of`
symptom. This was not fully swept -- scope was limited to the 4 papers on
the original punch list.

## Impact assessment

- No production trading impact: every affected readiness review is a
  research-only / promotion-gate document (`status: blocked`,
  `promote_to_live: false` pattern throughout this project). None feed
  target weights directly.
- Real impact is on trust in the metadata: anyone reading
  `asian_etf_tail_analytics_readiness_review.json` or
  `dynamic_cvar_tail_cost_readiness_review.json` and checking `as_of` to
  judge "is this current" would be misled into thinking the review reflects
  2026-07-20, when the substantive diagnostics inside were actually computed
  today. It also means the `execution_plan_stale_vs_live` framing these
  reviews inherit from the pinned rebalance snapshot is itself 3+ weeks
  stale and uninformative.

## Fixed 2026-08-09

Full blast radius confirmed at 10 files (1 producer + 9 consumers), plus one
extra layer discovered only while verifying the fix (see below): 12 files
touched total.

**Producer** (`scripts/evaluate/build_group_a_plus_rebalance_review.py`):
- `DEFAULT_LIVE_SIGNAL` (its own input) was *also* pinned to a dated
  snapshot, `live_signal_20260720_estimate.json` -- not just `DEFAULT_OUTPUT`.
  Both renamed to the undated `latest/live_signal.json` and
  `latest/rebalance_review.json` pointers.
- Two more hardcoded `2026-07-20` strings inside `build_review()`'s payload,
  missed in the original audit because they're data values, not path
  constants: the dict key `current_weights_reliable_for_20260720` (renamed
  to `current_weights_reliable`, value now computed from
  `execution_plan_stale`) and the `decision.summary` text (now built from
  `actual_date`/`requested_date` and `auto_rebalance_allowed`, so it reads
  correctly whether or not auto-rebalance is currently allowed).
- Wired into `run_ncf_daily_pipeline.py` as `commands["rebalance_review"]`,
  placed immediately after `commands["daily_signal"]` so it always reads a
  same-run-fresh `live_signal.json` (dict insertion order = execution order
  in this pipeline, confirmed via `for step, cmd in commands.items()`).

**9 consumers**: `DEFAULT_REBALANCE`/`DEFAULT_REBALANCE_REVIEW` repointed
from `rebalance_review_20260720.json` to `rebalance_review.json` in all 9
(`adversarial_market_integrity`, `asian_etf_tail_analytics`,
`deep_hedging_overlay`, `dynamic_cvar_tail_cost`, `finpilot_lite_planning`,
`finstressts_readiness`, `intervention_fatigue_risk_budget`,
`market_impact_readiness`, `sciphyrl_readiness`).

**Extra layer found during verification, same bug class, fixed same pass**:
re-running the adversarial-market-integrity consumer after the above fixes
still showed `as_of: "2026-07-20"` -- turned out 6 of the 9 consumers
*also* carry their own independent `DEFAULT_LIVE_SIGNAL` pinned to
`live_signal_20260720_estimate.json` (a real frozen Jul-19 snapshot, not
just a naming leftover -- confirmed via `ls -la`, vs `live_signal.json`
which daily_signal.py refreshes every run). Fixed all 6
(`adversarial_market_integrity`, `deep_hedging_overlay`,
`finpilot_lite_planning`, `finstressts_readiness`, `market_impact_readiness`,
`sciphyrl_readiness`) to point at the undated `live_signal.json` pointer.
The other 3 consumers (`asian_etf_tail_analytics`, `dynamic_cvar_tail_cost`,
`intervention_fatigue_risk_budget`) don't take a live-signal input at all,
so were unaffected by this second layer.

**Verification**: producer run directly now shows
`requested_as_of_date: 2026-08-09`, `actual_data_date: 2026-08-07` (was
frozen `2026-07-20`); `current_weights_reliable: true`; `decision.summary`
now reads "Do not auto-rebalance for 2026-08-07..." dynamically. Re-ran
`adversarial_market_integrity` and `sciphyrl_readiness` end-to-end after
both fix layers -- both now show `as_of: "2026-08-09"`. Existing test
suites for the 4 consumers with dedicated tests
(`adversarial_market_integrity`, `market_impact_readiness`,
`finstressts_readiness`, `sciphyrl_readiness`) all pass unchanged (8 tests).
Smoke-ran the 2 consumers without dedicated tests
(`deep_hedging_overlay`, `finpilot_lite_planning`) directly; both produce
valid output with fresh dates (or, for `deep_hedging_overlay`, no `as_of`
field at all -- it only ever surfaced `generated_at`, which was already
correct, so it never had the symptom despite carrying the same pinned
default).

Full 1909-test suite (`pytest -q`, 1:19:07) run after all fixes: 3 failures,
all diagnosed. 2 (`test_run_ncf_daily_pipeline.py::test_build_commands_*`)
were an expected consequence of adding the new `rebalance_review` pipeline
step -- fixed by inserting `"rebalance_review"` into the test's expected
step-order list right after `"daily_signal"` in both places it's asserted.
1 (`test_evaluate_00631l_0050_relative_reentry_opportunity.py::test_cli_writes_latest_output`)
is unrelated to this fix (own isolated `tmp_path` output, untouched file) and
passed cleanly on isolated re-run -- flaky under full-suite resource
contention, not a regression. All 3 confirmed passing together afterward.

Not touched: `reduced_rank_correlation`/`rl_governance` readiness reviews
(confirmed above as genuinely never-automated one-off files -- still true,
still correct as-is, deferred to the Task #20 data-freshness watchdog to
catch systematically rather than fixed ad hoc here) and
`heterogeneous_vol_regime_advisory.json` (a separate input this producer
reads, also stale at 22 days and also never wired into the daily pipeline --
same "never automated" class as the two above, same deferral).
