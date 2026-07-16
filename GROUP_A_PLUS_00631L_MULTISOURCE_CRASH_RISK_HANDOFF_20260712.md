# GroupA+ 00631L Multi-source Crash-risk Features - 2026-07-12

## One-line conclusion

Tested the proposed "new information source" direction: TXO/options tail
demand, liquidity/forced-selling stress, cross-market shock, all combined
ML, and a non-ML 2-of-3 ensemble veto. None is good enough to promote. The
best-looking isolated result is the ensemble veto's small 2018 OOS gain, but
it loses badly in 2020/2022/live/active windows, so it is not actionable.

## New file

`scripts/evaluate/evaluate_00631l_multisource_crash_risk.py`

Research-only. It does not touch live signal generation, target weights, or
daily execution.

## Feature families tested

### Options tail demand

From local DuckDB:

- `taifex_options_daily`: TXO market put/call volume and OI PCR z-scores.
- `derivative_institutional_data`: foreign TXO put-call net OI and 5d shock.
- `derivative_institutional_data`: foreign TX futures net OI and 5d shock.

### Liquidity / forced selling

From local DuckDB:

- `market_margin_data`: market margin flow/balance, short-margin ratio,
  forced repayment proxy.
- `margin_data`: ETF-level 0050/00631L margin flow.
- `securities_lending_data`: 0050 securities-lending volume z-score.

### Cross-market shock

From `external_market_ohlcv`:

- VIX level/change.
- SOXX, QQQ, TWII, TSM ADR 1d/5d moves.
- SOXX vs TWII 1d gap.
- USD/TWD 5d move.

### Methods

- `options_tail`: ML using only options features.
- `liquidity_forced_selling`: ML using only liquidity features.
- `cross_market_shock`: ML using only cross-market features.
- `all_multisource`: ML using all above features.
- `ensemble_veto_2of3`: no ML; de-risk only when at least two of options,
  liquidity, and cross-market stress flags are active.

All ML variants use the same no-look-ahead walk-forward discipline as the
prior crash-risk scripts: 504-day train window, 21-day refit cadence, and
label horizon purging.

## Result artifacts

Local only: `/results/` is gitignored in this repo.

- `results/00631l_multisource_crash_risk_10d_options_20260712.json`
- `results/00631l_multisource_crash_risk_10d_liquidity_20260712.json`
- `results/00631l_multisource_crash_risk_10d_cross_20260712.json`
- `results/00631l_multisource_crash_risk_10d_all_20260712.json`
- `results/00631l_multisource_crash_risk_10d_ensemble_20260712.json`
- `results/00631l_multisource_crash_risk_20d_allmethods_20260712.json`

Reproduce examples:

```bash
python3 -u scripts/evaluate/evaluate_00631l_multisource_crash_risk.py --label 10d_mdd_lt_5pct --methods options_tail --output results/00631l_multisource_crash_risk_10d_options_20260712.json
python3 -u scripts/evaluate/evaluate_00631l_multisource_crash_risk.py --label 20d_mdd_lt_8pct --methods options_tail,liquidity_forced_selling,cross_market_shock,all_multisource,ensemble_veto_2of3 --output results/00631l_multisource_crash_risk_20d_allmethods_20260712.json
```

## Key 10d label results

Label: future 10-trading-day 00631L max drawdown < -5%.

| Method | Main result |
|---|---|
| options_tail | 2018 OOS roughly flat (delta final +205, Sharpe -0.002), but 2019 OOS large negative (-42,395 final, -0.189 Sharpe). Tuning mixed and unstable. |
| liquidity_forced_selling | 2018 OOS AUC looked better (0.596) but trading delta still negative; 2019 over-triggered badly (105/241 golden1 days). |
| cross_market_shock | Live/active Sharpe sometimes positive, but 2018 and 2019 OOS both negative. |
| all_multisource | No improvement from combining sources; tuning and OOS mostly negative. |
| ensemble_veto_2of3 | 2018 OOS small positive (+8,256 final, +0.050 Sharpe), but 2020/2022/live/active all materially negative. |

## Key 20d label results

Label: future 20-trading-day 00631L max drawdown < -8%.

| Method | Main result |
|---|---|
| options_tail | 2022 small positive, but COVID negative, 2018 OOS slightly negative, 2019 OOS large negative. |
| liquidity_forced_selling | Some windows near flat, but AUC poor; 2019 de-risked 241/241 golden1 days, a clear false-positive failure. |
| cross_market_shock | 2018 OOS failed hard (-29,408 final, -0.249 Sharpe). |
| all_multisource | 2018 OOS failed (-24,991 final, -0.211 Sharpe); no robust gain from feature combination. |
| ensemble_veto_2of3 | Again small positive in 2018 OOS (+8,256 final, +0.050 Sharpe), but 2020/2022/live/active all negative. |

## Interpretation

The new information sources are directionally sensible, but in the current
simple wiring they do not solve the core problem:

1. Options/cross-market/liquidity features often recognize stress after it
   is already visible.
2. Sparse triggers still fire on enough false positives to create large
   opportunity cost.
3. Combining sources does not automatically reduce false positives.
4. The only repeatable positive pocket is the 2-of-3 ensemble in 2018 OOS,
   but that same rule is much too damaging in the main tuning/live windows.

## Promotion decision

Do not promote.

Keep the script as a feature harness. Future work should focus on either
better event timing (intraday/overnight data alignment, option skew instead
of coarse PCR) or a different downstream action (alert-only / no-buy guard /
smaller leverage cap), not full 00631L de-risk on these raw scores.

## Alert-only implementation - 2026-07-12

Implemented the conservative alert-only version requested after the no-
promotion result.

New runtime builder:

- `scripts/run/build_00631l_crash_risk_alert.py`
- Output: `report/group_a_plus/latest/crash_risk_alert.json`

Rule:

- Uses the explainable non-ML `ensemble_veto_2of3` condition.
- The three source families are:
  - options tail demand
  - liquidity / forced-selling stress
  - cross-market shock
- Alert is active only when at least 2 of 3 source families are active.
- Policy is explicitly `alert_only_no_auto_weight_change`.
- Metadata explicitly sets `auto_deleverage=false`.

Pipeline / alert-state integration:

- `scripts/run/run_ncf_daily_pipeline.py` now builds
  `crash_risk_alert.json` before `[alert-state]`.
- `group_a_plus/operations/alert_state.py` reads the snapshot and surfaces
  an advisory alert if active.
- The snapshot tolerates a 1-calendar-day lag versus `live_signal` because
  options/liquidity data commonly arrives one day behind. Older snapshots
  are surfaced as stale advisory alerts.

Current latest run:

- as_of: `2026-07-09`
- watch_level: `none`
- category_score: `0`
- alert_active: `false`
- source dates: options `2026-07-09`, liquidity `2026-07-09`, cross-market
  `2026-07-10`

Validation:

- `python3 -m py_compile scripts/run/build_00631l_crash_risk_alert.py group_a_plus/operations/alert_state.py scripts/run/run_ncf_daily_pipeline.py`
- `pytest -q tests/test_group_a_plus_alert_state.py`

## Alert-only usability upgrades - 2026-07-12

Implemented the follow-up alert-only improvements:

1. Severity tiers:
   - `category_score=0` -> `watch_level=none`
   - `category_score=1` -> `watch_level=watch` only, no push/action
   - `category_score=2` -> `watch_level=medium`; active alert only if score
     was also >=2 in the previous saved snapshot
   - `category_score=3` -> `watch_level=high`; immediate active alert

2. Human-readable reasons:
   - Snapshot includes `active_reason_lines`, e.g. options/liquidity/cross-
     market reason text instead of only raw boolean flags.
   - Alert metadata includes the same active reason lines.

3. Manual-action language:
   - Snapshot includes `manual_review`.
   - Active alerts recommend `manual_review_consider_pause_new_00631l_adds`.
   - It explicitly sets `do_not_auto_sell=true` and
     `do_not_auto_deleverage=true`.

4. History:
   - Latest snapshot still writes to
     `report/group_a_plus/latest/crash_risk_alert.json`.
   - Daily snapshots are also written to
     `report/group_a_plus/crash_risk_alert/history/YYYYMMDD.json`.

5. Freshness:
   - Snapshot includes per-family freshness under `freshness`.
   - `status=degraded` if any family is stale by more than one calendar day
     versus the selected `as_of`.

6. Quality monitor:
   - Added `scripts/evaluate/evaluate_00631l_crash_risk_alert_quality.py`.
   - Reads alert history and reports post-alert 00631L forward max drawdown
     over 5/10/20 trading days.
   - Output: `report/group_a_plus/crash_risk_alert/quality_latest.json`.
   - Current history has only one row (`2026-07-09`), so quality statistics
     are not yet meaningful.

Validation:

- `python3 -m py_compile scripts/run/build_00631l_crash_risk_alert.py scripts/evaluate/evaluate_00631l_crash_risk_alert_quality.py scripts/run/run_ncf_daily_pipeline.py group_a_plus/operations/alert_state.py`
- `pytest -q tests/test_build_00631l_crash_risk_alert.py tests/test_group_a_plus_alert_state.py`
- `python3 scripts/run/build_00631l_crash_risk_alert.py --output report/group_a_plus/latest/crash_risk_alert.json`
- `python3 scripts/evaluate/evaluate_00631l_crash_risk_alert_quality.py --output report/group_a_plus/crash_risk_alert/quality_latest.json`

## VIX / Global Risk-off enhancement - 2026-07-12

User pointed out that VIX-managed portfolios and implied-volatility style
signals should not be based on 00631L's own forecast volatility. They may
show global risk-off earlier through:

- VIX level
- VIX 5-day change
- SOXX implied/realized risk
- US overnight shock
- USD/TWD risk-off

Implemented this as an alert-only enhancement to the `cross_market_shock`
family. It still does not change target weights or execution.

Added cross-market features:

- `vix_level_z60`
- `vix_chg5_z60`
- `soxx_realized_vol20_z60`
- `soxx_downside_vol20_z60`
- `vix_soxx_realized_vol_gap_z60`
  - This is a VIX implied-risk proxy minus SOXX realized volatility, used
    because direct SOXX option-implied volatility is not currently in local
    DuckDB.
- `soxx_ret1`
- `qqq_ret1`
- `us_taiwan_gap1`
- `usdtwd_ret5_z60`

Latest snapshot after this enhancement:

- as_of: `2026-07-09`
- watch_level: `watch`
- category_score: `1`
- alert_active: `false`
- active family: `cross_market_shock`
- active reasons:
  - SOXX 20-day realized volatility is elevated
  - SOXX 20-day downside volatility is elevated
  - USD/TWD 5-day move indicates Taiwan FX risk-off

Interpretation: this is the desired alert-only behavior. Global risk-off is
visible enough to enter watch mode, but options/liquidity are not confirming,
so it does not escalate to a medium/high alert.

Validation:

- `python3 -m py_compile scripts/evaluate/evaluate_00631l_multisource_crash_risk.py scripts/run/build_00631l_crash_risk_alert.py`
- `pytest -q tests/test_build_00631l_crash_risk_alert.py tests/test_group_a_plus_alert_state.py`
- `python3 scripts/run/build_00631l_crash_risk_alert.py --output report/group_a_plus/latest/crash_risk_alert.json`
- `python3 scripts/evaluate/evaluate_00631l_crash_risk_alert_quality.py --output report/group_a_plus/crash_risk_alert/quality_latest.json`

## SOXX option-implied volatility integration - 2026-07-12 14:57 CST

User approved continuing with SOXX option-implied volatility because the
earlier VIX/SOXX realized-vol proxy was still not a direct SOXX options
market signal. Implemented this as alert-only data and feature plumbing.
No trading rule, target weight, execution gate, or live-signal decision is
changed by this work.

### New SOXX IV fetcher

Added:

- `scripts/fetch/fetch_soxx_options_iv.py`

Purpose:

- Fetch current `SOXX` option chain from Yahoo Finance through `yfinance`.
- Select the expiry closest to 30 DTE, ignoring expiries below 7 DTE.
- Store one compact daily implied-volatility snapshot in DuckDB.

New DuckDB table:

- `external_options_iv`

Schema written by the fetcher:

- `provider`
- `underlying`
- `dt`
- `spot`
- `expiry`
- `dte`
- `atm_iv`
- `atm_call_iv`
- `atm_put_iv`
- `otm_put_iv_95`
- `otm_call_iv_105`
- `put_call_iv_skew`
- `put_call_volume_ratio`
- `put_call_oi_ratio`
- `contract_count`
- `source`
- `fetched_at`

Important date behavior:

- The fetcher default is `--snapshot-date auto`.
- `auto` uses the latest SOXX trading date from `Ticker.history(period="5d")`.
- This avoids writing weekend/holiday rows such as `2026-07-12`, which would
  not align with alert trading dates.

Actual fetch performed after network approval:

```text
python3 scripts/fetch/fetch_soxx_options_iv.py
```

Latest stored SOXX snapshot:

```text
provider: yfinance
underlying: SOXX
dt: 2026-07-10
spot: 581.3400268554688
expiry: 2026-08-07
dte: 28
atm_iv: 0.6253699572753907
atm_call_iv: 0.63867548828125
atm_put_iv: 0.6120644262695314
otm_put_iv_95: 0.6404149728393554
otm_call_iv_105: 0.6181983981323244
put_call_iv_skew: 0.02221657470703109
put_call_volume_ratio: 5.394495412844036
put_call_oi_ratio: 5.099159663865546
contract_count: 124
```

Note:

- A first test fetch wrote `dt=2026-07-12`; this was manually deleted because
  it was a weekend row and should not be used for trading-date alignment.
- Current table check after cleanup showed only the `2026-07-10` SOXX row.

### Daily pipeline integration

Updated:

- `scripts/run/run_ncf_daily_pipeline.py`

Added best-effort step:

- `refresh_soxx_options_iv`

Command in pipeline:

```text
python3 scripts/fetch/fetch_soxx_options_iv.py
```

Behavior:

- Included in `BEST_EFFORT_STEP_NAMES`.
- If Yahoo/yfinance fails, the daily pipeline should continue.
- The alert builder then uses existing SOXX IV history if available.

### SOXX IV feature integration

Updated:

- `scripts/evaluate/evaluate_00631l_multisource_crash_risk.py`

Added raw SOXX IV loader:

- `_load_external_options_iv_raw`

Added transformed SOXX IV features:

- `soxx_atm_iv30_z252`
- `soxx_iv_rank_252`
- `soxx_iv_minus_rv20_z252`
- `soxx_put_call_iv_skew_z252`
- `soxx_put_call_volume_ratio_z60`
- `soxx_put_call_oi_ratio_z60`

Added raw fallback features:

- `soxx_atm_iv30_raw`
- `soxx_options_dte`
- `soxx_options_contract_count`
- `soxx_put_call_iv_skew_raw`
- `soxx_put_call_volume_ratio_raw`
- `soxx_put_call_oi_ratio_raw`

Raw fallback trigger thresholds:

- `soxx_atm_iv30_raw >= 0.55`
- `soxx_put_call_volume_ratio_raw >= 3.0`
- `soxx_put_call_oi_ratio_raw >= 3.0`

Rationale:

- zscore/rank features need 20/60/252 observations before becoming useful.
- The raw fallback makes the alert useful while SOXX IV history is still short.
- These raw triggers only contribute to the `cross_market_shock` source
  family; they do not create a standalone auto-deleverage rule.

### Alert builder changes

Updated:

- `scripts/run/build_00631l_crash_risk_alert.py`

Added SOXX IV fields to `FAMILY_COLUMNS["cross_market_shock"]`, including
both raw fallback and normalized/rank features.

Added explainable conditions:

- `soxx_atm_iv30_raw_ge_55pct`
- `soxx_put_call_volume_ratio_raw_ge_3`
- `soxx_put_call_oi_ratio_raw_ge_3`
- `soxx_atm_iv30_z252_ge_1`
- `soxx_iv_rank_252_ge_80pct`
- `soxx_iv_minus_rv20_z252_ge_1`
- `soxx_put_call_iv_skew_z252_ge_1`
- `soxx_put_call_volume_ratio_z60_ge_1`
- `soxx_put_call_oi_ratio_z60_ge_1`

Human-readable labels added to `CONDITION_LABELS`, for example:

- `SOXX 30-day ATM implied volatility is above 55%`
- `SOXX options put/call volume ratio is above 3`
- `SOXX options put/call open-interest ratio is above 3`

### SOXX IV quality monitor

Added inside:

- `scripts/run/build_00631l_crash_risk_alert.py`

Function:

- `_soxx_iv_health(db_path, as_of_dt)`

Included in alert payload under:

- `soxx_iv_health`

Checks:

- `external_options_iv` table exists.
- Latest SOXX IV snapshot exists.
- Latest snapshot lag is not more than 3 calendar days.
- DTE is between 7 and 60.
- ATM IV is between 5% and 200%.
- Contract count is at least 20.
- Put/call volume ratio is not above 20.
- Put/call OI ratio is not above 20.
- A SOXX IV snapshot exists at or before the alert `as_of`.

Current health output:

```text
status: warning
warnings:
  - no_snapshot_at_or_before_alert_as_of
latest_snapshot:
  date: 2026-07-10
  lag_days_vs_generated_date: 2
  spot: 581.3400268554688
  expiry: 2026-08-07
  dte: 28.0
  atm_iv: 0.6253699572753907
  put_call_iv_skew: 0.02221657470703109
  put_call_volume_ratio: 5.394495412844036
  put_call_oi_ratio: 5.099159663865546
  contract_count: 124.0
as_of_snapshot: null
```

Interpretation:

- This warning is expected and correct right now.
- Alert `as_of` is `2026-07-09`.
- First valid SOXX IV snapshot is `2026-07-10`.
- The alert builder must not use future SOXX IV data for a `2026-07-09`
  snapshot, so raw fallback is not active in the current alert.

### Current alert snapshot after SOXX IV changes

Generated by:

```text
python3 scripts/run/build_00631l_crash_risk_alert.py --output report/group_a_plus/latest/crash_risk_alert.json
```

Current state:

```text
as_of: 2026-07-09
watch_level: watch
alert_active: false
category_score: 1
active family: cross_market_shock
```

Active reasons:

- SOXX 20-day realized volatility is elevated.
- SOXX 20-day downside volatility is elevated.
- USD/TWD 5-day move indicates Taiwan FX risk-off.

SOXX IV raw fallback values in the alert are currently null because no SOXX IV
snapshot exists on or before the `2026-07-09` alert date:

```text
soxx_atm_iv30_raw: null
soxx_options_dte: null
soxx_options_contract_count: null
soxx_put_call_iv_skew_raw: null
soxx_put_call_volume_ratio_raw: null
soxx_put_call_oi_ratio_raw: null
```

This is intentional no-lookahead behavior.

### Tests added / updated

Added:

- `tests/test_fetch_soxx_options_iv.py`

Coverage:

- Fake yfinance-like option chain.
- Confirms nearest 30-DTE expiry selection.
- Confirms ATM IV, put-call skew, and put/call volume ratio calculation.
- Confirms DuckDB `external_options_iv` history can feed SOXX IV features.

Updated:

- `tests/test_build_00631l_crash_risk_alert.py`

Added coverage:

- SOXX implied-vol normalized/rank conditions trigger cross-market family.
- SOXX raw fallback conditions trigger cross-market family.
- SOXX IV health flags bad snapshots:
  - DTE outside range
  - ATM IV outside range
  - low contract count
  - no snapshot at or before alert as-of

### Validation performed

Compilation:

```text
python3 -m py_compile scripts/evaluate/evaluate_00631l_multisource_crash_risk.py scripts/run/build_00631l_crash_risk_alert.py scripts/fetch/fetch_soxx_options_iv.py
```

Tests:

```text
pytest -q tests/test_build_00631l_crash_risk_alert.py tests/test_fetch_soxx_options_iv.py tests/test_group_a_plus_alert_state.py
```

Result:

```text
31 passed
```

Alert rebuild:

```text
python3 scripts/run/build_00631l_crash_risk_alert.py --output report/group_a_plus/latest/crash_risk_alert.json
```

Quality monitor:

```text
python3 scripts/evaluate/evaluate_00631l_crash_risk_alert_quality.py --output report/group_a_plus/crash_risk_alert/quality_latest.json
```

Quality monitor current state:

- `status: ok`
- history rows: `1`
- date range: `2026-07-09` to `2026-07-09`
- forward MDD statistics are still null because only one alert-history row
  exists and not enough forward days have elapsed.

### Important limitations

1. Yahoo Finance option chain is current snapshot data, not historical IV.
   The system can only build SOXX IV history from the day the fetcher starts
   running.

2. Current raw SOXX IV fallback is unavailable for the current alert because
   the current alert `as_of` is `2026-07-09` and first SOXX IV snapshot is
   `2026-07-10`.

3. Raw thresholds are intentionally conservative and alert-only:
   - `ATM IV >= 55%`
   - `put/call volume ratio >= 3`
   - `put/call OI ratio >= 3`

4. SOXX IV only affects the `cross_market_shock` family. Medium/high alert
   still requires multi-family confirmation or persistence depending on the
   existing alert policy.

5. No live allocation or target weight is changed anywhere in this work.

### Recommended next steps

1. Add a daily coverage report that explicitly lists:
   - latest SOXX IV date
   - latest external market OHLCV date
   - latest options-tail date
   - latest liquidity date
   - the source family blocking alert `as_of` from advancing

2. Split cross-market reasons into subfamilies in the alert JSON:
   - `cross_market_price_fx`
   - `cross_market_implied_vol`

   This would make it easier to distinguish price/FX risk-off from options-
   market risk-off.

3. Once alert `as_of` advances to `2026-07-10` or later, verify that SOXX IV
   raw fallback enters `feature_values` and condition details when thresholds
   are met.

4. After enough SOXX IV history accumulates:
   - revisit raw thresholds
   - compare raw fallback against zscore/rank triggers
   - evaluate whether `soxx_iv_rank_252` needs a shorter interim window
     before 252 daily snapshots exist

## Freshness bugs, automation gaps, and diagnostics follow-up - 2026-07-12 (later session)

Follow-up session, same day. Triggered by a targeted code-review fork run
against the 5 files from the alert-only work above (both research scripts,
`build_00631l_crash_risk_alert.py`, `fetch_soxx_options_iv.py`,
`alert_state.py`, `run_ncf_daily_pipeline.py`), looking specifically for
look-ahead leakage, `as_of` alignment bugs, severity-tier logic errors, and
walk-forward purging correctness. Everything else checked out clean; one
confirmed, currently-live bug was found and is documented below along with
everything that came out of following its root cause.

Nothing in this section changes target weights, execution gates, or the
"do not promote" trading conclusion above. Everything here is either a bug
fix in the alert-only data-quality layer, or new best-effort data-refresh
automation.

### Bug found: `cross_market_shock` freshness always reported fresh

`_load_cross_market_features` in `evaluate_00631l_multisource_crash_risk.py`
forward-fills VIX/SOXX/QQQ/^TWII/TSM/TWD=X closes across the full date grid
before z-scoring (needed to bridge US/TW calendar gaps for the engineered
features themselves). `build_00631l_crash_risk_alert.py`'s
`_family_freshness` computed staleness from that already-ffilled frame, so
`cross_market_shock` always reported `lag_days_vs_as_of: 0, stale: false`
regardless of real staleness.

Confirmed live, not hypothetical: at the time of the review, the DB had
^VIX/SOXX/QQQ/TSM/TWD=X stuck at `2026-07-07` while the alert (`as_of`
`2026-07-09`) reported `cross_market_shock` as fresh. `options_tail` and
`liquidity_forced_selling` did not have this specific ffill bug (their
loaders use plain `.reindex()`); the separate `_soxx_iv_health` check was
independently correct about SOXX IV's own staleness. No test exercised
`_family_freshness` at all before this session.

### Fix 1: freshness reads raw source dates, worst-case, not engineered/ffilled columns

- Added `_cross_market_raw_latest_date` (queries `external_market_ohlcv`
  directly, pre-ffill) for `cross_market_shock`. Takes the **worst-case
  (oldest)** date across tickers, not the newest: `^TWII` updates on the
  Taiwan calendar while VIX/SOXX/QQQ/TSM/TWD=X update on the US calendar, so
  picking the newest ticker (typically `^TWII`) would keep hiding US-side
  staleness.
- Generalized the same worst-case pattern to `options_tail` and
  `liquidity_forced_selling` via `RAW_FRESHNESS_SOURCES` +
  `_raw_sources_worst_case_date`, because each of these families also mixes
  columns from more than one raw table with independent refresh cadences:
  - `options_tail`: `taifex_options_daily` (TXO market-wide) +
    `derivative_institutional_data` (foreign TXO/TX positioning).
  - `liquidity_forced_selling`: `market_margin_data` + `securities_lending_data`.
  - Using the engineered columns' freshest date (the pre-existing behavior)
    let whichever table was still updating mask the other one going stale.
- Regression tests added for both the cross-market ffill case and the
  generic two-table case (`tests/test_build_00631l_crash_risk_alert.py`).

### Fix 2: `freshness.status == "degraded"` is now wired into a visible advisory

`alert_state.py::_crash_risk_alerts` previously only compared the overall
snapshot `as_of` against the live-signal date; it never read the per-family
`freshness` field, so a correctly-flagged degraded family produced no
visible alert anywhere -- the diagnostic was accurate but unread.

Added a new alert type `00631l_crash_risk_family_degraded` (level `watch`,
`auto_deleverage=false`) that fires when `freshness.status == "degraded"`,
listing the specific stale family/families. It coexists with the existing
`00631l_multisource_crash_risk` active alert (both can appear together). 3
new tests added; verified end-to-end against the live snapshot before and
after the fix.

### Root cause found: 3 data sources were never scheduled in the daily pipeline at all

Distinct from the freshness-detection bug above -- these sources were
simply never being refreshed by automation, so a correct freshness check
would have (rightly) kept reporting them stale indefinitely:

1. **Cross-market OHLCV** (VIX/SOXX/QQQ/^TWII/TSM/TWD=X): only refreshed via
   `NCF_EXTERNAL_ALLOW_DOWNLOAD=1`, which the pipeline only sets on `ncf_*`
   steps when `--refresh-external-cache` is passed (off by default). Added
   `scripts/fetch/fetch_cross_market_ohlcv.py` (always `allow_download=True`,
   unconditional, best-effort) and wired it in as the
   `refresh_cross_market_ohlcv` pipeline step.
2. **`taifex_options_daily`** (TXO market-wide put/call volume and OI): the
   pipeline's `refresh_taifex` step only ever called `taifex_futures_data.py`
   (the futures table); the separate `taifex_options_data.py --refresh-latest`
   script was never wired into the pipeline at all. Added the
   `refresh_taifex_options` step. One manual `--refresh-latest` call jumped
   the table from `2026-07-03` to `2026-07-09` -- TAIFEX's OpenAPI serves
   "latest published business day" on every call, not a date range, so
   the 6-day gap was purely "nobody had called this in 6 days," not a
   deeper backfill problem.
3. **`securities_lending_data`** (0050 securities-lending volume):
   `fetch_finmind_chip_data.py --datasets securities_lending` already
   existed but was never called by the pipeline. Added the
   `refresh_securities_lending` step (mirrors `refresh_derivative_institutional`,
   using the existing `_resolve_chip_start` gap-aware backfill start date).
   Manually backfilled `2026-07-08` -> `2026-07-09`.

All three now (a) refresh automatically every pipeline run as best-effort
steps (a failure logs and is skipped, it does not block the run), and (b)
are covered by the worst-case freshness check from Fix 1, so a future
silent failure of any one of them will surface as `status: degraded` plus a
`watch`-level advisory instead of being invisible again.

Verified end state this session: all three crash-risk families report
`status: ok`, `lag_days_vs_as_of: 0` against the live production DB via
`python3 scripts/run/build_00631l_crash_risk_alert.py`.

### Recommended-next-step #1 and #2 from above, implemented

- **#1 (coverage/blocking diagnostic):** added an `as_of_advancement` field
  to the alert payload. For feature dates after the resolved `as_of` that
  already exist in the 00631L.TW OHLC index, it lists which family/families
  are still missing data there. Current live output shows `as_of` stuck at
  `2026-07-09` because `options_tail`/`liquidity_forced_selling` (official
  TWSE/TAIFEX chip data) had not posted `2026-07-10` yet at the time of this
  session -- expected T+1 official-data lag, not a bug, but now explicit
  instead of requiring a fresh DB investigation every time.
- **#2 (cross-market subfamily split):** `active_reason_lines` now splits
  `cross_market_shock` into `Cross-market price/FX` and `Cross-market implied
  volatility` labeled lines. Presentation-only -- `cross_market_shock` still
  casts exactly one vote in the 2-of-3 ensemble either way.

### Files touched

- `scripts/run/build_00631l_crash_risk_alert.py` -- freshness generalization
  (`_cross_market_raw_latest_date`, `RAW_FRESHNESS_SOURCES`,
  `_raw_sources_worst_case_date`), `as_of_advancement`
  (`_as_of_advancement_blocking`), cross-market subfamily split in
  `_active_reason_lines`.
- `group_a_plus/operations/alert_state.py` -- new
  `00631l_crash_risk_family_degraded` alert type in `_crash_risk_alerts`.
- `scripts/fetch/fetch_cross_market_ohlcv.py` -- new file.
- `scripts/run/run_ncf_daily_pipeline.py` -- 3 new best-effort steps:
  `refresh_cross_market_ohlcv`, `refresh_taifex_options`,
  `refresh_securities_lending`.
- Tests: `tests/test_build_00631l_crash_risk_alert.py`,
  `tests/test_group_a_plus_alert_state.py`,
  `tests/test_fetch_cross_market_ohlcv.py` (new file),
  `tests/test_run_ncf_daily_pipeline.py`.

### Validation

```bash
python3 -m pytest -q tests/test_build_00631l_crash_risk_alert.py tests/test_group_a_plus_alert_state.py tests/test_fetch_soxx_options_iv.py tests/test_fetch_cross_market_ohlcv.py tests/test_run_ncf_daily_pipeline.py
```

Result: 58 passed.

```bash
python3 scripts/run/build_00631l_crash_risk_alert.py --output report/group_a_plus/latest/crash_risk_alert.json
```

Rebuilt and inspected against live data after every fix in this section.

### Not done / deferred

- Recommended-next-steps #3 and #4 from above (verify SOXX IV raw fallback
  once `as_of` reaches `2026-07-10`+; revisit raw IV thresholds once more
  SOXX IV history accumulates) still require calendar time / data
  accumulation and were not attempted this session.
- No other latent freshness-masking pattern was found beyond the 3 families
  already covered by `RAW_FRESHNESS_SOURCES` + `_cross_market_raw_latest_date`.
- This session only touched the alert-only layer (`crash_risk_alert.json`,
  `alert_state.py` advisories, and the daily-pipeline refresh steps that
  feed it). No production target weight, execution gate, or live trading
  decision was changed. The "do not promote" research conclusion from the
  rest of this document is unchanged.
