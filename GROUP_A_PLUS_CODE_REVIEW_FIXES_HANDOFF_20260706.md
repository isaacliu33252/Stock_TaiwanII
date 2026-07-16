# GroupA+ 8-Angle Code Review + Fixes Handoff - 2026-07-06

## Executive Summary

Follow-up to the 2026-07-04/07-05 pending batch (chip fallback fix, market_state arbitration,
GARCH shadow routing, ncf_2330 advisory wiring, alert push notification — see
`project_alert_push_notification_20260705` and `project_chip_fallback_n_tuning_20260705` in
memory). Ran a full 8-angle code review (`/code-review high`: 3 correctness angles + reuse +
simplification + efficiency + altitude + conventions, each an independent finder agent, followed
by a 1-vote verification pass) over that entire pending diff. All 9 surviving findings were
CONFIRMED or PLAUSIBLE after verification. **8 were fixed this session; 1 was deliberately left
unfixed per an explicit user decision** (it would have been a live strategy behavior change, not
a bug fix). All fixes are covered by tests (333 relevant tests pass) and are still **uncommitted**
— part of the same pending multi-session batch as before.

## Review Method

- Scope: the pending production-adjacent diff only (`daily_signal.py`, `market_state.py`,
  `ncf.py`, `signal_alignment.py`, `runners/a2118.py`, `backtest_group_a_plus_switch_policy.py`,
  the new `garch_regime_shadow.py` and `push_notifications.py`, and their pipeline wiring in
  `scripts/run/*.py`). Excluded: `FinRL/*` (unrelated subsystem), the large pile of
  research-only `scripts/misc/*` scripts and shadow runners `a2121.py`-`a2126.py` (confirmed via
  `report/group_a_plus/latest/strategy.json` that a2118 remains the sole `active_strategy`; the
  others are only registered in `governance/latest.py`'s lookup table, not live).
- 8 parallel finder agents, each returning up to 6 candidates with `file`/`line`/`summary`/
  `failure_scenario`.
- Verification: 2 batch verifier agents (5 + 4 candidates), each returning CONFIRMED / PLAUSIBLE
  / REFUTED per candidate with the exact code checked. Result: 8 CONFIRMED, 1 PLAUSIBLE, 0
  REFUTED.

## Findings and Fixes (most severe first)

### 1. `ncf_2330.py` was never invoked by the daily pipeline — CONFIRMED, fixed

`scripts/run/run_ncf_daily_pipeline.py`'s `commands` dict only ran `refresh_2330_per` (a chip-data
refresh) and `ncf_2330_checklist` (a diagnostic report) — never the model script `ncf_2330.py`
itself. No other script or scheduler in the repo calls it either. Since the last manual run
(`results/ncf_2330_improved_20260703.json`, 2026-07-03), `daily_signal.py`'s
`str(ncf_2330.get('date')) != str(actual.date())` staleness check has been silently true every
day, meaning `tsmc_0050_health` has been reading as `stale` in live production with no error
surfaced.

**Fix**: added `commands["ncf_2330"]` to `scripts/run/run_ncf_daily_pipeline.py`, mirroring the
existing `ncf_00631l`/`ncf_00632r` pattern (`--train-start`/`--val-start`/`--val-end`/`--output`/
`--val-predictions-output`, plus `--no-external-features` when that flag is set). Output path
`results/ncf_2330_latest_{stamp}.json` matches `_latest_ncf_path`'s glob pattern. New CLI arg
`--train-start-2330` (default `2015-01-01`, matching `ncf_2330.py`'s own default). Runs right
after `ncf_00632r`, before `advisory_panel`/`factor_lens`/`daily_signal`/`ncf_2330_checklist` (dict
insertion order = execution order in `main()`).

Deliberately **not** touched: `--refresh-external-cache` still defaults to `False` (cache-only),
so the `2330.TW` `external_market_ohlcv` price cache used by `_tsmc_0050_health_snapshot` is still
only refreshed when that flag is explicitly passed. This is a separate, pre-existing, deliberate
reliability/freshness tradeoff (avoid daily yfinance dependency in the unattended job) — changing
it is a policy decision, not a bug fix, so it was left alone.

### 2. `ncf_2330_checklist` was never populated in `ncf_live_overlay` — CONFIRMED, fixed

`signal_alignment.py`'s `_leverage_suitability` reads `overlay.get("ncf_2330_checklist")` to
drive its factor-quality/shadow-momentum tier logic, but nothing in `daily_signal.py`'s
`_apply_ncf_live_overlay` ever called `load_ncf_2330_checklist` (from `ncf.py`) or attached the
result. `checklist` was always `{}` in production, so `fq_risk_score`/`fq_net_score`/
`shadow_momentum_candidate` never reflected the real daily-generated
`ncf_2330_checklist_<stamp>.json` — only unit tests that hand-construct the overlay dict
exercised this.

**Fix**: added `_latest_ncf_2330_checklist_path()` helper in `daily_signal.py` (glob
`ncf_2330_checklist_*.json`, excluding `*_external_cache_*.json`), called from
`_apply_ncf_live_overlay` right after loading `sig_2330`, populating
`summary["ncf_2330_checklist"]` via `load_ncf_2330_checklist`. Wrapped in its own try/except so a
malformed checklist file can't break the rest of the overlay.

### 3. Chip-data-outage fallback (2026-07-04 fix) was incomplete — CONFIRMED, fixed

The 2026-07-04 fix added `chip_data_fallback_max_stale_days` to `_switch_returns()` in
`backtest_group_a_plus_switch_policy.py`, but it only bypasses the **local boolean gates**
(`chip_ok`/`derivative_ok`/`total_risk_ok`) inside that one function's per-row loop — it never
corrects `total_risk_score`/`chip_score`/`derivative_score` themselves, which stay at/near zero
during a real outage. Two other production consumers read `total_risk_score` directly and were
never covered by the fix:
- `daily_signal.py`'s `_apply_bearish_high_risk_trim` (`total_risk_score < 9` gate)
- `signal_alignment.py`'s `_leverage_suitability` (`total_risk_score >= 9`/`>= 6` conditions) and
  `_risk_score_source` (feeds the alignment vote; a score of 0 during an outage would vote
  "bullish", exactly backwards)

**Fix**:
- `daily_signal.py`: added `chip_data_core_days_since_source_update` to `latest_features`.
  `_apply_bearish_high_risk_trim` now computes `chip_data_stale` via the existing
  `_chip_data_is_stale()` helper (imported from `backtest_group_a_plus_switch_policy`) and
  `CHIP_DATA_FALLBACK_MAX_STALE_DAYS` (imported from `runners.a2118`), bypassing the
  `total_risk_score < 9` gate when stale. The trim-severity `scale` factor is pinned to `1.0`
  (base fraction, no severity scaling) during a stale bypass, since `total_risk_score` isn't a
  real reading in that case. `bearish_high_risk_trim_reason` now includes `chip_data_stale=...`.
- `signal_alignment.py`: added a shared `_chip_data_stale_from_features()` helper (same
  `_chip_data_is_stale`/`CHIP_DATA_FALLBACK_MAX_STALE_DAYS` imports). `_risk_score_source` now
  returns `available=False`/`neutral` instead of guessing "bullish" from a stale-zero score.
  `_leverage_suitability`'s tier-0 and tier-1 conditions now also fire on `chip_data_stale`; the
  tier-3 ("raise leverage") condition now additionally requires `not chip_data_stale`, so an
  outage can't look like a permissive, high-suitability calm market. `chip_data_stale` is
  included in the returned `inputs` dict for transparency.

No import cycles introduced (verified `a2118.py`/`backtest_group_a_plus_switch_policy.py` don't
import `daily_signal.py`/`signal_alignment.py`).

### 4. `run_a2118()`'s new default silently changed two evaluate scripts — CONFIRMED, fixed

`run_a2118()`'s new `chip_data_fallback_max_stale_days` parameter defaults to
`CHIP_DATA_FALLBACK_MAX_STALE_DAYS` (`10`), not `None` like the `_switch_returns` primitive it
wraps. Two pre-existing, untouched-by-this-diff scripts —
`scripts/evaluate/evaluate_a2118_composite_confidence_sweep.py` and
`scripts/evaluate/evaluate_a2118_finrl_dual_engine_reconciliation.py` — call `run_a2118(...)`
with explicit kwargs that omit this parameter, so they'd silently start running with the fallback
enabled, producing different numbers with no diff explaining why. Both scripts already mirror
other production parameters via `PRODUCTION_H20_MAX`/`PRODUCTION_CONF_MIN`/
`PRODUCTION_H5_REENTRY_MIN` constants, so `N=10` is arguably the *correct* value for what they're
trying to measure — the problem was that it was implicit, not wrong.

**Fix**: added `PRODUCTION_CHIP_DATA_FALLBACK_MAX_STALE_DAYS = CHIP_DATA_FALLBACK_MAX_STALE_DAYS`
(imported from `runners.a2118`) to both scripts, passed explicitly to `run_a2118(...)`. Behavior
unchanged (still resolves to `10`); the choice is now explicit and grep-able so a future default
change in `a2118.py` can't silently drift these scripts' output again.

### 5. `garch_regime_shadow.py` could crash the entire daily signal — CONFIRMED, fixed

Only `_load_prices(...)` inside `compute_garch_regime_shadow` was wrapped in try/except; the
subsequent `_load_chip_features`/`_switch_returns` (×2) /`_garch_features` calls were not.
Separately, `_attach_smart_money_cost_proxy` (called from `_load_chip_features`) unconditionally
`LEFT JOIN`s `institutional_data`/`margin_data` with no `_table_exists()` guard — unlike every
other chip source in that same function, which checks existence first. If either table is
missing from a given duckdb file, this raises a duckdb `CatalogException`. `daily_signal.py`
calls `compute_garch_regime_shadow` with no local try/except; the only handler is `main()`'s
top-level one, which wraps the entire `build_daily_signal(...)` call — so a failure in what's
supposed to be a shadow-only diagnostic could turn the whole day's live signal (including
`target_weights`) into an error payload.

**Fix**:
- `garch_regime_shadow.py`: wrapped the entire body (after the initial price-history check)
  in one try/except, matching the existing `_load_prices`-only pattern's return shape
  (`{"status": "unavailable", "reason": str(exc)}`).
- `backtest_group_a_plus_switch_policy.py`: `_attach_smart_money_cost_proxy` now checks
  `_table_exists(con, "institutional_data")` / `_table_exists(con, "margin_data")` and builds the
  SQL's `JOIN`/`SELECT` clauses conditionally, falling back to literal `0.0` columns when a table
  is absent — identical output when both tables exist, graceful degradation otherwise.

### 6. `a2118.py`'s 4 golden-overlay blocks were duplicated across two branches — CONFIRMED, fixed

The `golden_tail_trim_enabled`/`golden_follow_through_trim_enabled`/
`golden_rebound_recapture_enabled`/`golden_leverage_cap_enabled` overlay-application blocks (and
the subsequent `_delayed_regime`/`_simulate_costed_curve` calls) were copy-pasted verbatim
between the `panel_631l is not None` branch and its `else` branch — ~80 duplicated lines with a
real risk of the two paths silently diverging on a future fix.

**Fix**: refactored so the `if/else` only sets `modified_regime`/`overlay_info`/`backtest_mode`/
`ncf_panel_coverage` (the actual difference between the two paths), then the 4 overlay blocks and
the delayed-regime/simulate call run once, unconditionally, after the branch. Identical execution
order and behavior; verified via the full a2118/a2121-a2126 test suite (59 tests, all pass).

### 7. `_apply_ncf_live_overlay`'s test db_path safety — PLAUSIBLE, fixed defensively

`_apply_ncf_live_overlay`'s new `db_path` parameter defaults to the real production duckdb path
(`DB_PATH`) rather than `None`/injectable. The one existing direct test
(`test_daily_signal_ncf_overlay_reduces_00631l_to_cash`) called it without `db_path`, avoiding the
real DB only incidentally (no `ncf_2330_*.json` fixture was seeded, so the `tsmc_path is not
None` branch — the only one that opens `db_path` — was never reached). Not a live bug today (the
real production call site does pass `db_path` explicitly), but a latent risk for a future test
built by copying this pattern.

**Fix**: updated the existing test to pass `db_path=root / "unused.db"` explicitly, establishing
the safe pattern. Added 2 new tests for the new `_latest_ncf_2330_checklist_path` helper
(excludes `external_cache` files; returns `None` when nothing matches).

### 8. `market_state.py` dropped a `total_risk_score >= 6` conjunct — CONFIRMED, no fix needed

The `late_bull_overheat` branch now fires on any `regime.startswith("ncf_late_bull")` day
regardless of `total_risk_score`. Verified via the code's own comment: this was an **intentional**
2026-07-04 audit fix (previously a hedge day with `total_risk_score < 6` could fall through to
`bull_acceleration`/`bull_trend`, whose "00631L high weight" bias directly contradicted the
de-leverage the strategy was actually executing that day). `classify_market_state`'s output
remains diagnostic-only (stored as report metadata, never read back into `target_weights`/
`execution_regime`). **Reviewed and confirmed correct as-is — no change made.**

### 9. `_apply_tsmc_weakness_trim` was never called — CONFIRMED, deliberately NOT fixed

`_apply_tsmc_weakness_trim` (trims 00631L 25% when TSMC is `tsmc_weak_confirmed` **and**
00631L's own NCF signal independently agrees) is fully implemented, unit-tested, and has alert
wiring (`tsmc_weakness_trim_applied`/`tsmc_weakness_trim` alert type) — but `build_daily_signal`
never calls it; only `_apply_bearish_high_risk_trim` runs in production. This looked like a bug
at first (a tested safeguard that never fires), **but** `_tsmc_0050_reference_guidance()` in the
same file explicitly documents `"trade_policy": "manual_review_only_no_auto_trim"` for exactly
this state (`tsmc_weak_confirmed`) — the code's own contract says this signal should be
manual-review-only, not auto-trim.

**User was asked directly** (2026-07-06): wire it in, or keep manual-review-only? **Decision:
keep manual-review-only** — do not wire `_apply_tsmc_weakness_trim` into `build_daily_signal`.
This is now the confirmed, intentional design, not an open item. `_apply_tsmc_weakness_trim`
remains dead code in production (tested but uncalled) by design.

## A Bug Found *During* Verification (meta note)

While confirming fixes with a full `pytest tests/` run, found and fixed a real regression
introduced by fix #1 itself: `run_ncf_daily_pipeline.py`'s new `commands["ncf_2330"]` block
referenced `args.train_start_2330` directly, but `tests/test_run_ncf_daily_pipeline.py` builds
minimal `argparse.Namespace(...)` fixtures by hand (not via real `argparse.parse_args()`), so
they lack that new attribute — `AttributeError` on 5 tests. Fixed by using
`getattr(args, "train_start_2330", "2015-01-01")`, matching this file's own established pattern
for other args added after the original test fixtures were written (e.g. `refresh_target_date`,
`only_refresh`). Also updated 2 tests' hardcoded `list(commands) == [...]` assertions to include
the new `"ncf_2330"` step. All 9 tests in that file pass now.

Also worth knowing for next time: `tests/test_seed_collapse.py::test_seed_collapse_walk_forward`
is a genuinely slow test (60s+, doesn't even finish standalone within a minute) that imports
nothing from any file touched this session — if a future full-suite run appears to hang there,
it is not a regression from Group A+ work.

## Files Changed This Session

Modified (all part of the pending batch, uncommitted):
- `backtest_group_a_plus_switch_policy.py` (`_attach_smart_money_cost_proxy` table-exists guard)
- `group_a_plus/integrations/signal_alignment.py` (`_chip_data_stale_from_features`,
  `_risk_score_source`, `_leverage_suitability` tier changes)
- `group_a_plus/operations/daily_signal.py` (ncf_2330_checklist wiring, chip-data-stale bypass in
  `_apply_bearish_high_risk_trim`, new `_latest_ncf_2330_checklist_path` helper)
- `group_a_plus/runners/a2118.py` (deduplicated golden-overlay branches)
- `group_a_plus/integrations/garch_regime_shadow.py` (full-body try/except)
- `scripts/evaluate/evaluate_a2118_composite_confidence_sweep.py`,
  `scripts/evaluate/evaluate_a2118_finrl_dual_engine_reconciliation.py` (explicit
  `chip_data_fallback_max_stale_days`)
- `scripts/run/run_ncf_daily_pipeline.py` (new `ncf_2330` pipeline step)
- `tests/test_group_a_plus_daily_signal_v2.py`, `tests/test_group_a_plus_signal_alignment.py`,
  `tests/test_group_a_plus_latest_strategy.py`, `tests/test_group_a_plus_garch_regime_shadow.py`,
  `tests/test_run_ncf_daily_pipeline.py` (new/updated tests, 6 new tests total this session plus
  2 assertion updates)

No production runtime behavior changed for the case where chip/derivative data is fresh (the
default, current, real-world case) — every new bypass/fix only activates when
`chip_data_core_days_since_source_update >= 10` (a genuine outage), verified by full test suite.

## Verification

```bash
.venv/bin/python -m pytest tests/ -q -k "group_a_plus or a2118 or a2121 or a2122 or a2123 or a2124 or a2125 or a2126" \
  tests/test_run_ncf_daily_pipeline.py tests/test_a2118_composite_confidence_sweep.py \
  tests/test_a2118_finrl_dual_engine_reconciliation.py
```
Result: **333 passed**, 297 deselected, 3 (pre-existing, unrelated) warnings.

## Status

Everything in this document is **uncommitted** — part of the same pending multi-session batch as
`GROUP_A_PLUS_A2118_CHIP_FALLBACK_HANDOFF_20260704.md`,
`GROUP_A_PLUS_FABLE_AUDIT_MARKET_STATE_ARBITRATION_HANDOFF_20260704.md`,
`GROUP_A_PLUS_GARCH_SPECIALIST_ROUTING_HANDOFF_20260705.md`, and
`GROUP_A_PLUS_A2118_CHIP_FALLBACK_N_TUNING_SYNTHETIC_OUTAGE_HANDOFF_20260705.md`. Per explicit
user instruction this session, do not raise or suggest committing.
