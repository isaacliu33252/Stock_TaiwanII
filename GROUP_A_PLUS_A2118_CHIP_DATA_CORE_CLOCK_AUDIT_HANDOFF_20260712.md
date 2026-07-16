# GroupA+ a2118 chip-data-outage core clock audit - 2026-07-12

## One-line conclusion

Applied the same freshness-masking audit used on the 00631L crash-risk
alert-only layer (see `GROUP_A_PLUS_00631L_MULTISOURCE_CRASH_RISK_HANDOFF_20260712.md`)
to the actually-live a2118 chip-data-outage fallback. Found and fixed a
real, unscheduled data-refresh gap (`dealer_futures_data`/
`dealer_options_data`, 9 days stale). Found, prototyped, and **reverted** a
worst-case fix to the union-based staleness clock itself, because it would
have silently corrupted ~70% of a2118's 2022-2026 historical backtest range.

## Motivation

After closing out the crash-risk alert-only freshness work, the user asked
whether the same class of bug ("a diagnostic clock exists, but its
aggregation lets one fresh source mask others going stale") could exist
somewhere with real production consequences, not just in the research/
alert-only layer. It does: `group_a_plus/runners/a2118.py`'s
`CHIP_DATA_FALLBACK_MAX_STALE_DAYS = 10` mechanism (added 2026-07-04, see
`GROUP_A_PLUS_FABLE_AUDIT_MARKET_STATE_ARBITRATION_HANDOFF_20260704.md`)
depends on exactly this kind of clock.

## Background: what the clock is for

a2118's `SwitchRule` requires `total_risk_score >= 6` (built from
`chip_score` + `derivative_score`) to enter `group_a_plus_defensive`. If the
underlying chip/derivative source tables go missing, those scores silently
default to 0 -- indistinguishable from "genuinely calm market" -- and the
defensive entry condition becomes permanently unsatisfiable regardless of
price action. `chip_data_fallback_max_stale_days=10` is the fix: when
`chip_data_core_days_since_source_update >= 10`, the chip/derivative/
total-risk gates are bypassed so entry can still fire on price action
alone.

`chip_data_core_days_since_source_update` (computed in
`backtest_group_a_plus_switch_policy.py::_load_chip_features`) is built from
a **union** of coverage dates across 10 "core" table queries:
`institutional_data`, `margin_data`, `shareholding_distribution`,
`foreign_shareholding_data`, `short_sale_balance_data`,
`securities_lending_data`, `day_trading_data`, `dealer_futures_data`,
`dealer_options_data`, and `derivative_institutional_data` (queried twice,
for futures and options rows).

## Bug found: the union masks a genuine per-table outage

Live DB check on 2026-07-12: `dealer_futures_data` and `dealer_options_data`
had not updated since `2026-07-03` (9 real trading days), while
`institutional_data`/`securities_lending_data`/`derivative_institutional_data`
were current through `2026-07-09`. Because `chip_data_core_days_since_source_update`
is a union, it reported 0-1 days stale throughout -- the exact scenario the
2026-07-04 fallback fix exists to catch, undermined one level up by its own
staleness clock.

Root cause: `fetch_finmind_chip_data.py --datasets dealer_futures,dealer_options`
already existed but was never called by `scripts/run/run_ncf_daily_pipeline.py`
-- same class of gap as `taifex_options_daily`/`securities_lending_data`
found earlier the same day in the crash-risk alert work.

## Fix applied: dealer_futures_data/dealer_options_data scheduling

- Added `dealer_start = _resolve_chip_start(db_path, ["dealer_futures_data", "dealer_options_data"], chip_start)`
  and a new `refresh_dealer_positions` best-effort pipeline step in
  `scripts/run/run_ncf_daily_pipeline.py`, calling
  `fetch_finmind_chip_data.py --datasets dealer_futures,dealer_options --futures-ids TX --option-ids TXO`.
- Manually backfilled: `python3 scripts/fetch/fetch_finmind_chip_data.py --datasets dealer_futures,dealer_options --futures-ids TX --option-ids TXO --start 2026-07-03 --end 2026-07-12`
  -- both tables jumped from `2026-07-03` to `2026-07-09`.
- Updated `tests/test_run_ncf_daily_pipeline.py`'s expected step-list assertion.

This part is low-risk: it only adds a best-effort fetch step (failure logs
and is skipped, does not block the pipeline) and does not touch
`_load_chip_features`, `_switch_returns`, or any a2118 decision logic.

## Fix attempted and reverted: worst-case core clock

Also tried making `chip_data_core_days_since_source_update` a worst-case
(max per-table gap among tables that have started reporting) instead of a
union, mirroring the `RAW_FRESHNESS_SOURCES` fix applied to the crash-risk
alert the same day. Implemented as `core_coverage_dates_by_table` (per-table
sets) + a new `_worst_case_days_since_coverage` helper.

**This was reverted after validation, not shipped.** Recomputing
`chip_data_core_days_since_source_update` over 2022-01-01..2026-07-12 with
the worst-case version showed `>= 10` (the fallback-bypass threshold) on
**762 of 1094 trading days (70%)** -- because two of the ten core tables
have genuine, large historical voids that predate consistent data
collection, not outages:

- `margin_data`: `2022-08-26` -> `2023-10-06` (over a year with zero rows).
- `shareholding_distribution` (TDCC): `2022-05-13` -> `2025-06-06` (~3 years).

The worst-case design already excludes a table for dates *before* its
first-ever row (so a dataset onboarded later doesn't retroactively count as
an outage), but it cannot distinguish "this table went dark after already
reporting for a while" (a genuine multi-year collection gap, in this case)
from "this table is currently down" (today's dealer_futures_data scenario).
Applying it as a blanket fix would have silently bypassed a2118's
chip/derivative/total-risk entry gates across most of the strategy's
validated 2022-2026 backtest history -- a severe, unintended behavior
change to a core production risk mechanism.

Reverted `backtest_group_a_plus_switch_policy.py::_load_chip_features` back
to the exact original union-based `core_coverage_dates` computation, removed
`_worst_case_days_since_coverage`, and removed the test additions that
exercised it (`tests/test_group_a_plus_source_staleness.py` is back to its
original single test). The explanatory comment in `_load_chip_features`
documents this investigation and its outcome so it is not silently
attempted again the same way.

Confirmed the revert is behaviorally identical to pre-session state: as of
`2026-07-10`, both the "any" and "core" clocks read `1` (matching the
1-day OHLC lag), and all core-clock consumers
(`tests/test_backtest_group_a_plus_switch_policy_chip_fallback.py`,
`tests/test_backtest_group_a_plus_switch_policy_2020_fix.py`, and the
downstream `signal_alignment.py`/`daily_signal.py` imports of
`CHIP_DATA_FALLBACK_MAX_STALE_DAYS`) are unaffected.

## Interpretation / recommended future work

The scheduling gap (dealer positions) was a genuine, fixable bug and is
fixed. The clock's union-vs-worst-case tradeoff is a real, unresolved
limitation, not a bug with an obvious safe fix:

- A per-table worst-case is only safe once every core table's *own* history
  is either continuous from its first row, or the clock is date-bounded to
  only apply worst-case logic from some cutover date onward (e.g. only for
  `dt >= 2025-01-01`, after which all ten sources have continuous daily
  coverage in this DB).
- Alternatively, `margin_data`'s and `shareholding_distribution`'s
  historical voids could be backfilled first (if FinMind/TDCC's API allows
  it), which would remove the obstacle to a worst-case clock entirely.
- Do not re-attempt a blanket worst-case fix without first checking each
  core table's actual historical gap profile the way this session did
  (`SELECT dt FROM <table> ... ORDER BY dt` then `.diff().max()`), for
  exactly this class of surprise.

## Files touched (net, after the revert)

- `scripts/run/run_ncf_daily_pipeline.py` -- new `refresh_dealer_positions`
  best-effort step (kept).
- `tests/test_run_ncf_daily_pipeline.py` -- updated step-list assertion
  (kept).
- `backtest_group_a_plus_switch_policy.py` -- comment added explaining the
  investigation and revert; `_load_chip_features`'s actual computation is
  byte-for-byte the original union logic.
- `tests/test_group_a_plus_source_staleness.py` -- back to its original
  single test (worst-case tests added then removed).

## Validation

```bash
python3 scripts/fetch/fetch_finmind_chip_data.py --datasets dealer_futures,dealer_options --futures-ids TX --option-ids TXO --start 2026-07-03 --end 2026-07-12
python3 -m pytest -q tests/test_group_a_plus_source_staleness.py tests/test_backtest_group_a_plus_switch_policy_chip_fallback.py tests/test_backtest_group_a_plus_switch_policy_2020_fix.py tests/test_backtest_group_a_plus_metrics_finrl_comparable.py tests/test_group_a_plus_a2112.py tests/test_group_a_plus_a2128.py tests/test_group_a_plus_garch_regime_shadow.py tests/test_group_a_plus_latest_strategy.py tests/test_group_a_plus_ncf_integration.py tests/test_run_ncf_daily_pipeline.py
```

Result: 162 passed.

## Follow-up: closing the remaining execution_allowed gaps + a resolved false alarm

After the above, tried to produce an actual forward-looking target-weight
check ("what would tomorrow's allocation be"). This surfaced two more
things, one real fix and one false alarm that is worth recording so it is
not re-investigated from scratch later.

### Fix: 3 more unscheduled FinMind datasets, same pattern

`report/group_a_plus/latest/live_signal.json`'s `execution_guard_reasons`
listed `day_trading_0050`, `foreign_shareholding_0050`, `short_balance_0050`
as stale/missing, alongside the already-fixed `dealer_tx`/`dealer_txo`/
`institutional_0050`. Checked `run_ncf_daily_pipeline.py`: none of
`fetch_finmind_chip_data.py --datasets foreign_shareholding`,
`short_sale_balances`, or `day_trading` were ever called by the pipeline --
same unscheduled-fetch pattern as everything else found today. Added
`refresh_foreign_shareholding`, `refresh_short_sale_balances`,
`refresh_day_trading` best-effort steps and backfilled
(`python3 scripts/fetch/fetch_finmind_chip_data.py --datasets foreign_shareholding,short_sale_balances,day_trading --tickers 0050.TW --start 2026-07-08 --end 2026-07-12`).
All three now current (`day_trading_data` reached `2026-07-10`;
`foreign_shareholding_data`/`short_sale_balance_data` reached `2026-07-09`).
`tests/test_run_ncf_daily_pipeline.py` step-list assertion updated.

Remaining guard reason after this fix: `institutional_0050` only, because
`institutional_data` is at `2026-07-09` versus `actual_data_date`
`2026-07-10` and its tolerance in `daily_signal.py`'s `OPTIONAL_SOURCE_SPECS`
is 0 days. Re-fetching found no newer row -- TWSE's official 三大法人 data
for `2026-07-10` (Friday) genuinely was not yet published as of this
session (Sunday `2026-07-12`). Not a scheduling bug; expected to clear on
its own once TWSE publishes it or the next scheduled refresh runs.

### False alarm, fully resolved: golden1 base-weight "shift" was just a timing gap, not caused by anything in this session

Regenerating `live_signal.json` (`python3 group_a_plus/operations/daily_signal.py --as-of 2026-07-12`)
produced `target_weights` for `0050.TW`/`00631L.TW`/`cash` of
`57.4%/12.6%/30%`, materially different from the previously-deployed
`69.1%/10.9%/20%` -- despite `chip_score`/`derivative_score`/
`total_risk_score`/`market_state` being byte-identical between the two
runs. Traced this fully (not caused by any chip-data backfill above):

- `run_a2118()` resolves its golden1 base weights via
  `_resolve_golden_signal_path()` (`group_a_plus/runners/a2111.py`), which
  picks the most recently generated `results/signal_group_a_*.json` file --
  intentionally "drifts daily" (see the comment above `NCF_LB_MA_GAP_MIN` in
  `a2118.py`), independent of the `decision.json` pointer and independent
  of everything else touched today.
- The previously-deployed `live_signal.json` was generated `2026-07-11T23:27:37`,
  using `signal_group_a_20260708_010149.json` (`2026-07-08`, 3 days stale
  at the time -- the latest one that existed yet).
- `signal_group_a_20260711_234842.json` was written 21 minutes *later*
  (`2026-07-11T23:48:42`), after `daily_signal.py` had already run that
  night. Nobody re-ran `daily_signal.py` since, so the deployed signal
  stayed on the stale basis.
- Confirmed directly: loading each file through
  `_weights_from_group_a`/`_normalize` reproduces the old (`08-01`) and new
  (`07-11 23:48`) numbers exactly. This is a real, legitimate difference in
  Group A's own golden1 recommendation between `2026-07-08` and
  `2026-07-11`, not a bug and not related to any chip/derivative data
  backfilled in this session.
- Side finding, not investigated further: `results/signal_group_a_*.json`
  itself has an unexplained 3-day gap (`2026-07-08` -> `2026-07-11 23:48`)
  in its own generation cadence -- a separate pipeline from everything else
  in this document (Group A's own golden1 signal, not Group A+ chip data).
  Worth checking later whether it has the same "exists but isn't reliably
  scheduled" problem as everything found today, but out of scope here.

Net effect: `report/group_a_plus/latest/live_signal.json` now correctly
reflects the freshest available golden1 basis (`57.4%/12.6%/30%` cash) and
all chip/derivative sources except `institutional_0050`'s 1-day publication
lag. `execution_allowed` remains `false` pending that lag clearing.

### Additional files touched

- `scripts/run/run_ncf_daily_pipeline.py` -- 3 more best-effort steps:
  `refresh_foreign_shareholding`, `refresh_short_sale_balances`,
  `refresh_day_trading`.
- `tests/test_run_ncf_daily_pipeline.py` -- step-list assertion updated
  again.
- `report/group_a_plus/latest/live_signal.json` -- regenerated (live
  production file; this is the one production output actually changed by
  this session's work, and it changed because of the golden1 timing gap
  above, not because of any chip-data fix).

## Not done

- The worst-case core-clock fix itself was not shipped (see above).
- No other production runner (a2121-a2129) was individually re-audited for
  the same union-masking pattern; they all import
  `CHIP_DATA_FALLBACK_MAX_STALE_DAYS` from `a2118.py` and share the same
  `_load_chip_features` call path, so they inherit whatever
  `backtest_group_a_plus_switch_policy.py` does -- no separate action
  needed there.
- `results/signal_group_a_*.json`'s own 3-day generation gap (07-08 ->
  07-11) was found but not investigated -- separate pipeline from
  everything else in this document.

## Follow-up: phantom zero-volume OHLCV rows falsely blocking execution_allowed

Same day, later session. User pointed out directly: `2026-07-10` (Friday)
was a Taiwan market holiday. That single fact resolved the
`institutional_0050`-stale guard reason left over from the previous section
and led to a real, fixed bug plus a broader historical audit that,
correctly, concluded with **no further data changes**.

### Bug found: a holiday gets a phantom `ohlcv` row instead of being skipped

Checked the `ohlcv` table for `2026-07-10` across all 9 tracked tickers:
every one had `open=high=low=close=prior close, volume=0` -- a market-wide
flat/zero-volume row, not real trading data. `^TWII` (the separate
`external_market_ohlcv` index table) correctly has **no row at all** for
that date -- only the per-ticker `ohlcv` ingestion has this gap-filling
behavior.

`daily_signal.py`'s `build_daily_signal()` sets
`actual = pd.Timestamp(frame.index[-1]).normalize()` where `frame` comes
from `run_latest()` -> `run_a2118()` -> `_load_prices()`
(`backtest_group_a_plus_switch_policy.py`), which does not filter by
volume. The phantom `2026-07-10` row therefore became `actual_data_date`,
making every real chip/derivative source (all genuinely current through
`2026-07-09`, the real last trading day) look one day stale. This is what
was producing the `institutional_0050` guard reason in the previous
section -- not a genuine T+1 publication lag as first assumed there.

### Fix: opt-in `exclude_zero_volume` filter, live-signal only

- `_load_prices()` (`backtest_group_a_plus_switch_policy.py`): new
  `exclude_zero_volume: bool = False` parameter. When `True`, adds
  `AND volume > 0` to the `ohlcv` query. Default `False` = zero behavior
  change for every existing backtest/evaluation caller.
- `run_a2118()`: new `exclude_zero_volume_rows: bool = False` parameter,
  threaded straight into its own `_load_prices()` call.
- `report/group_a_plus/latest/strategy.json`'s `active_strategy.runner_params`:
  added `"exclude_zero_volume_rows": true` -- this is the *only* place that
  turns it on, because `run_latest()` (called by `daily_signal.py`) passes
  `runner_params` straight through as kwargs. Any direct/explicit call to
  `run_a2118()` elsewhere (backtests, evaluation scripts, promotion gates)
  keeps the old default and is completely unaffected.
- 3 new tests in `tests/test_group_a_plus_source_staleness.py`
  (`ExcludeZeroVolumeRowsTests`) using a small fixture DB reproducing the
  exact phantom-row scenario.

Verified against live data:

```
Before: actual_data_date=2026-07-10, execution_allowed=False,
        execution_guard_reasons=["required strategy sources are stale or missing: ['institutional_0050']"]
After:  actual_data_date=2026-07-09, execution_allowed=True,
        execution_guard_reasons=[]
target_weights unchanged (57.4% / 12.6% / 30% cash -- see previous section;
00631l_reduction was already 0.0, so nothing here depended on the wrong date).
```

One new, expected, non-blocking side effect: `execution_warning_reasons`
now shows `NCF live overlay skipped: date mismatch {'00631L.TW': '2026-07-10', ...}, actual 2026-07-09`.
The NCF panel files (`ncf_00631l_latest_20260711.json` etc.) are themselves
dated `2026-07-10` -- confirming `scripts/misc/ncf_00631l.py` has the exact
same unfiltered `SELECT dt, close FROM ohlcv WHERE ticker='0050.TW' ...`
pattern at line 314, and produced a panel entry for the phantom holiday
date. This is now caught defensively (the overlay skips itself rather than
applying a mismatched-date prediction) instead of silently misapplied, but
the underlying `ncf_00631l.py` date-resolution bug itself was not fixed --
see "Not done" below.

`python3 -m pytest -q tests/test_group_a_plus_source_staleness.py tests/test_backtest_group_a_plus_switch_policy_chip_fallback.py tests/test_backtest_group_a_plus_switch_policy_2020_fix.py tests/test_backtest_group_a_plus_metrics_finrl_comparable.py tests/test_group_a_plus_a2112.py tests/test_group_a_plus_a2128.py tests/test_group_a_plus_garch_regime_shadow.py tests/test_group_a_plus_latest_strategy.py tests/test_group_a_plus_ncf_integration.py` -> 150 passed.

### Historical audit ("回頭清查"): concluded with no data changes needed

Backed up `FinRL/data/stock_data.db` first (scratchpad copy,
`stock_data_backup_20260712_before_ohlcv_cleanup.db`) before investigating
further, in case a repair turned out to be warranted.

Inventoried every `volume=0` row across the whole `ohlcv` table
(2020-present) and grouped by date to see which tickers were affected
together. This split into four distinct patterns, not one bug repeating:

1. **`2026-07-10`, all 9 tickers simultaneously** -- the genuine market-wide
   holiday from above. This is the only one that was a logic bug on our
   side (misreading a real holiday as "the latest trading day"), and it is
   now fixed as described above.
2. **Single-ticker multi-day flat stretches**: `0050.TW` `2025-06-11~17`
   (5 days), `00631L.TW` `2026-03-25~30` (4 days), `00632R.TW`
   `2024-12-04~10` (5 days). Only the one ticker affected each time; price
   jumps to a genuinely different value immediately after each stretch
   (e.g. `0050.TW` `46.18` flat for 5 days -> `46.58` real move on
   `2025-06-18`).
3. **Pre-listing placeholder**: `00878.TW` `2020-07-10~17` (6 days), values
   drifting slowly (`10.04` -> `9.96`) instead of perfectly flat, volume=0
   throughout, real trading starting exactly on `2020-07-20` -- 00878's
   actual TWSE listing date.
4. **Single-day, subset-of-tickers**: `2024-01-15` -- `0050.TW`/`0056.TW`/
   `00646.TW`/`00713.TW`/`00878.TW` all flat/zero-volume, while
   `00631L.TW`/`00632R.TW`/`00679B.TWO`/`00751B.TWO` traded normally the
   same day (real market-open day, only these 5 tickers affected).

Initial hypothesis was that (2) and (4) were silent fetch failures worth
backfilling with a fresh yfinance pull. **Checked directly against a live
`yfinance.download()` call for every one of these date ranges, and
yfinance itself returns the exact same flat/zero-volume rows today as what
is already stored.** There is no better data available to backfill with --
these are not gaps in our ingestion, they are what the underlying data
source (yfinance) has always returned for these tickers on these dates,
most plausibly:

- (2): genuine ticker-specific TWSE trading halts, most likely regulatory
  (leveraged/inverse ETFs like `00631L.TW`/`00632R.TW` can be individually
  suspended for premium/size-control reasons independent of the broader
  market; less certain why `0050.TW` itself had one, but the pattern -- flat
  during, real jump immediately after -- is consistent with a real halt,
  not corrupted data).
- (3): yfinance provides an indicative-NAV-like placeholder before a fund's
  actual listing date rather than no row at all.
- (4): an unexplained single-day gap specific to yfinance's TW data for
  those 5 tickers; also not recoverable by re-fetching.

Conclusion: **no `ohlcv` rows were modified or deleted.** The DB backup
above was not needed for repair, but was kept as of this writing (not
committed; scratchpad only). The one and only actionable defect found in
this whole audit was the "logic misreads a flat/halted day as *the*
current day" pattern from `2026-07-10`, which is now fixed for the live
path. `_load_prices`'s new `exclude_zero_volume` parameter exists but is
deliberately **not** applied to historical backtests -- doing so would
silently change return series across (2)/(3)/(4) above, which is a
separate, considered decision, not an oversight.

### Additional files touched (this follow-up)

- `backtest_group_a_plus_switch_policy.py` -- `_load_prices()` gains
  `exclude_zero_volume`.
- `group_a_plus/runners/a2118.py` -- `run_a2118()` gains
  `exclude_zero_volume_rows`, threaded to its `_load_prices()` call.
- `report/group_a_plus/latest/strategy.json` -- `runner_params` now
  includes `"exclude_zero_volume_rows": true`.
- `report/group_a_plus/latest/live_signal.json` -- regenerated again;
  `execution_allowed` is now correctly `true`.
- `tests/test_group_a_plus_source_staleness.py` -- new
  `ExcludeZeroVolumeRowsTests` class (2 tests).

## Not done (updated)

- `scripts/misc/ncf_00631l.py` line 314 (`SELECT dt, close FROM ohlcv WHERE ticker='0050.TW' ...`)
  has the same unfiltered-volume pattern that produced the `2026-07-10`-dated
  NCF panel entry. Not fixed this session. The same opt-in
  `exclude_zero_volume`-style approach would apply, but this script also
  feeds historical panel generation used for backtesting/promotion-gate
  work (`ncf_00631l_panel_latest_*.csv`), so the same "opt-in, live-path-only"
  care taken with `run_a2118()` should be taken here too rather than a
  blanket change.
- `ncf_00632r.py`/`ncf_2330.py` were not checked for the same pattern; given
  `ncf_00631l.py` has it, they likely do too (same author/era of code) but
  this was not verified.
- No `ohlcv` data was modified -- see "Historical audit" above for why the
  three remaining zero-volume patterns are not fixable defects.

## Follow-up: ncf_00631l.py/ncf_00632r.py/ncf_2330.py resolve_end_date fix (2026-07-12/13)

Fixed the `ncf_00631l.py` line-314-class bug flagged above in all three
places it exists. `resolve_end_date(db, ticker, "latest")` in
`scripts/misc/ncf_00631l.py`, `ncf_00632r.py`, and `ncf_2330.py` all did a
plain `SELECT MAX(dt) FROM ohlcv/external_market_ohlcv WHERE ticker = ?`
with no volume filter -- the same phantom-holiday-row vulnerability as
`_load_prices`, but this one directly produced the mis-dated
`2026-07-10` NCF panel entries found in the earlier follow-up.

Fix: added `AND volume > 0` to all three. Unlike `_load_prices`/`run_a2118`,
**no opt-in flag was needed** -- `resolve_end_date`'s DB-lookup branch only
ever runs when `requested_end == "latest"`, which by definition is the
live/same-day case; no historical backtest or evaluation script passes
`"latest"` for a fixed historical window, so there is no existing-caller
behavior to preserve here.

New tests: `tests/test_resolve_end_date_zero_volume.py` (4 tests, one per
script plus a check that explicit dates never touch the DB).

Verified against production DB: all three now resolve `"latest"` to a real
trading day (`2026-07-09` for `00631L.TW`/`00632R.TW`; `2026-07-08` for
`2330.TW`, which is a separate, unrelated `external_market_ohlcv`
freshness lag, not a phantom row).

Then ran the actual scheduled fetch command (`run_fetch.bat`'s underlying
`run_ncf_daily_pipeline.py --only-refresh --force-refresh --strict-refresh --fail-on-ohlcv-warning`)
end-to-end for the first time since today's fixes, to validate them in the
real pipeline rather than just individually. All 7 new best-effort steps
from this document (`refresh_taifex_options`, `refresh_securities_lending`,
`refresh_dealer_positions`, `refresh_foreign_shareholding`,
`refresh_short_sale_balances`, `refresh_day_trading`,
`refresh_cross_market_ohlcv`) completed successfully. The only two failures
(`refresh_group_data`, `ohlcv_freshness`) were expected and unrelated to
this work: the run happened before market open on `2026-07-13`, so
`--strict`/`--fail-on-warning` correctly rejected "today" as not-yet-available
-- not a bug, resolves itself once run after market close as scheduled.

## Follow-up: golden1 / Group A+ decision-signal freshness now visible in ops_health (2026-07-13)

User asked whether Group A+ has the same "exists, not scheduled, no
freshness check" gap as Group A's golden1 signal (from the earlier
follow-up). It does, on a different input:
`report/group_a_plus/latest/decision.json` ->
`results/group_a_plus_policy_signal_*.json` -- last generated
`2026-06-27`, 16+ days stale as of this writing, and not referenced by
`run_daily.bat`/`run_fetch.bat`/`run_ncf_daily_pipeline.py` (only by
`scripts/run/run_group_a_plus_pipeline.py`, which is not scheduled either).

Impact is narrower than golden1's: this file only feeds `current_defensive`
in `a2118.py`, which is only used by the `group_a_plus_recovery` regime --
not `golden1` (the current regime) and not `group_a_plus_defensive` (which
uses the fixed `bond30_cash30` basket instead, unaffected). So there is no
current live impact, but the same blind spot exists: if/when a crash
triggers a recovery-regime transition, it would silently use a stale
defensive-basket definition with nothing flagging it.

Added two new checks to `group_a_plus/operations/ops_health.py`'s
`collect_artifact_health()`, following the exact pattern of the existing
`_execution_plan_freshness()`:

- `_golden_signal_freshness()`: resolves the same file a2118 actually uses
  (via `group_a_plus.runners.a2111._resolve_golden_signal_path()`) and
  reports `stale` if its mtime lag exceeds 3 days. Surfaces as
  `golden_signal_stale` in `artifact_health.missing_optional`.
- `_group_a_plus_decision_signal_freshness()`: same pattern for
  `decision.json`'s referenced policy_signal file, 14-day tolerance
  (narrower blast radius than golden1 justifies a longer default).
  Surfaces as `group_a_plus_decision_signal_stale`.

Both are detection-only, matching `_execution_plan_freshness`'s existing
rationale: none of these three files can be safely auto-regenerated by an
unattended pipeline (golden1 depends on `generate_dual_group_signal.py`'s
holdings input; the Group A+ decision signal's generation process wasn't
investigated further this session) -- the fix is making staleness visible,
not automating generation.

Verified against live data: `golden_signal_freshness` currently reports
`fresh` (1.32 days); `group_a_plus_decision_signal_freshness` correctly
reports `stale` (15.43 days, exceeding the 14-day tolerance) and appears in
`missing_optional`. Regenerated `report/group_a_plus/latest/ops_health.json`
to confirm.

4 new tests in `tests/test_group_a_plus_ops_health.py` (stale/fresh cases
for both checks). All 18 tests in that file pass (15 existing + 3 new --
one golden1 case was folded into an existing assertion path, see the test
file for the exact count).

### Not done (this follow-up)

- `generate_dual_group_signal.py` (golden1) and whatever generates
  `group_a_plus_policy_signal_*.json` (the Group A+ decision signal) were
  not wired into the scheduled pipeline -- only their *staleness* is now
  visible, not fixed. Whether to automate either (and how to handle
  `--override-holdings-json`/real portfolio holdings input safely in an
  unattended run) is an open decision for the user, not attempted here.
