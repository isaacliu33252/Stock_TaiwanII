# GroupA+ GARCH-Proxy Specialist-Routing Research Handoff - 2026-07-05

## Motivation

User asked about "specialist routing / 多模型路由" for GroupA+: don't trust one
model in every regime -- use momentum/trend/GRU/LightGBM in low volatility,
switch to GARCH/drawdown-risk/volatility models in high volatility, and go to
pure risk control (no return forecasting) in extreme volatility. Referenced a
2026 ETF-volatility-forecasting study where regime-dependent specialist
routing cut high-volatility-regime forecast loss ~24% and underprediction
loss ~22% versus a single always-on model.

This repo already had a relevant, never-promoted 2026-06-19 research script
(`scripts/backtest/backtest_group_a_plus_financial_econometrics.py`) that uses
a fixed-parameter GARCH(1,1)-style recursion as a local volatility-state
proxy and picks the best-Sharpe threshold by optimizing over the *entire*
backtest window (i.e. the parameter choice itself sees the future -- not a
valid walk-forward test). This session re-validated that script's core idea
properly, found real gaps in local historical data along the way, filled
them, and built a shadow-only diagnostic overlay. **No production weight
logic was changed.**

## Summary Of The Decision

- Walk-forward tested on **four** windows: 2022-2026 (six folds, real data),
  2008 (TWII proxy), 2011 (TWII proxy, newly built this session), 2020 (real
  data, newly tested this session).
- 2022-2026: no edge (coin-flip, 3/6 folds).
- 2008: strong, threshold-robust edge (24/24 grid variants).
- 2011: same direction, much weaker (14/24, marginal magnitude, all-negative
  Sharpe regime).
- 2020 (V-shaped COVID crash): same direction for selector but weak (13/24,
  differences look like noise); guard actually **loses** here (6/27).
- **Consolidated verdict: the 2008 result looks like a favorable outlier, not
  a general property.** Direction is inconsistent across guard, magnitude is
  mostly small, only one of three real crises showed a strong effect.
  De-risking on a vol spike has a real cost in V-shaped recoveries that a
  longer/harsher crash doesn't have.
- **Decision: do not promote anything to production.** Built a shadow-only
  diagnostic (`group_a_plus/integrations/garch_regime_shadow.py`) that logs,
  once per real trading day, what a frozen GARCH-vol selector rule would have
  picked, so future forward days accumulate real (non-backtest) evidence.
  Revisit only once that log has enough real forward days to say something
  new -- not from re-running more backtests on the same three historical
  crises.

## Methodology (Applies To All Folds)

Expanding-window walk-forward: pick the best-Sharpe grid variant using ONLY
the train-segment equity curve, freeze it, evaluate out-of-sample on the
following test segment. Grids:

- **Selector** (switch which switching-rule "book" to trust -- a207 vs ma20 --
  based on GARCH-proxy vol): `ratio_threshold in {1.05,1.10,1.20,1.30} x
  percentile_threshold in {0.70,0.80,0.90} x require_negative_5d in
  {True,False}` = 24 combos.
- **Guard** (binary defensive override layered on top of a207's own regime,
  triggered by GARCH vol + negative momentum + an optional total_risk_score
  gate): `ratio_threshold in {1.05,1.10,1.20} x percentile_threshold in
  {0.70,0.80,0.90} x require_total_risk_score in {0,4,6}` = 27 combos.

Benchmark for "beats": `static_best_frozen` = whichever of a207/ma20 had the
better Sharpe on the train segment (a cheaper baseline that answers "does
GARCH routing add anything beyond just picking the better simple rule?").

Robustness check added after the 2008 fold: don't just report whether the
*frozen-chosen* variant won -- evaluate the *entire grid* directly on the
test segment and report the win count. A single frozen variant winning could
be luck; the whole grid winning cannot.

## Per-Fold Results

### 2022-2026 (real ETF data, 6 folds)

Script: `scripts/misc/garch_specialist_routing_walkforward_20260705.py`
Output: `results/garch_specialist_routing_walkforward_20260705.json`

6 expanding-window folds (2022H1, 2022H2, 2023, 2024, 2025, 2026H1).
garch_selector_frozen and garch_guard_frozen each beat static_best_frozen in
only 3/6 folds -- coin-flip. Guard's chosen parameter was also unstable (3
different picks across 6 folds). Even the cheaper question -- "does train-
Sharpe predict which of a207/ma20 wins OOS" -- only got it right 3/6 times.
Conclusion at the time: no edge in calm/moderate years.

### 2008 (TWII proxy, prolonged 18-month crash)

Real data gap found: `FinRL/data/portfolio_cache/TWII_20030101_20110101_1d_market_v2.parquet`
covers real TAIEX returns 2003-01-02..2010-12-31 -- genuine index data, just
pre-dating real 0050.TW/00631L.TW histories (00631L/00632R didn't exist as
listed products before 2015; 0050.TW real OHLCV only starts 2009-01-02).

- `scripts/misc/prepare_2008_twii_proxy_data_20260705.py`: converts that real
  TWII history into leveraged-ETF-equivalent proxy prices (0050=1x,
  00631L=2x, 00632R=-1x, 00679B.TWO=0.45x/vol_scale=0.70, matching
  `twii_proxy_utils`' existing conventions). Outputs:
  `results/twii_proxy_2008_prepared_20260705_{prices,chip_features,manifest}.{csv,json}`.
  Crash sanity check (2007-10..2008-11): 0050 proxy MDD -58.31% (real TAIEX
  2007 peak 9309 -> 2008 low 3955 is about -57%, matches).
- `scripts/misc/garch_specialist_routing_2008_fold_20260705.py`:
  train=2003-01-02..2007-06-30, test=2007-07-01..2009-12-31.
  Output: `results/garch_specialist_routing_2008_fold_20260705.json`.

Result:

| | Test Sharpe | MDD | Total return |
|---|---:|---:|---:|
| a207 (chip-gated, never fires -- see caveat below) | -0.054 | -62.25% | -15.27% |
| ma20 / static_best_frozen | 0.084 | -55.51% | -3.59% |
| **garch_selector_frozen** | **0.151** | -56.74% | **+0.53%** |
| garch_guard_frozen | 0.104 | -54.92% | -1.88% |

Robustness check: **24/24** selector grid variants beat ma20 OOS (Sharpe
range 0.107-0.162) -- not one lucky threshold, the whole grid works. Guard
only 9/27, but the 18 losses are exactly the `require_total_risk_score in
{4,6}` subset that structurally cannot fire (see caveat) -- guard is
*untested* there, not falsified.

**Caveat (applies to every proxy fold, and to 2020 partially):** a207
requires `total_risk_score >= 6` to enter defensive.
`institutional_data`/`margin_data`/etc. only start 2020 in `stock_data.db`,
so `total_risk_score` never reaches 6 on 2008/2011 proxy data --
a207 literally never leaves `golden1` regardless of price action. a207's
numbers here reflect "a chip-gated rule with zero chip signal available,"
not a claim about how real a207 (with real 2008 chip data, which does not
exist locally) would have performed.

### 2011 (TWII proxy, European debt crisis -- grinding decline)

Real data gap found (and fixed): `stock_data.db`'s `ohlcv` table had a **clean
four-year hole** for 0050.TW: last row `2010-12-30`, next row `2015-01-05`,
zero rows in between. `external_market_ohlcv`'s `^TWII` only started
2014-01-02. The old TWII proxy parquet cache stops 2010-12-31. So 2011-2014,
including the real Aug-Oct 2011 selloff, had **no usable data locally in any
form**.

- Fetched real `^TWII` via yfinance (`ncf_external_cache.fetch_yf_close_cached`,
  the same caching pattern already used for every other external ticker in
  this repo) for `2008-06-02..2014-01-10`, written into `external_market_ohlcv`
  (provider='yfinance'). Verified continuous afterward (max gap 13 calendar
  days = normal holidays) and consistent with the pre-existing 2014-01-02+
  rows at the overlap (same source).
- `scripts/misc/prepare_2011_2014_twii_proxy_data_20260705.py`: builds the
  same style of leveraged proxy prices from this now-real `^TWII` series (via
  `twii_proxy_utils.build_twii_proxy_ohlcv`/`_build_group_b_single_proxy`,
  constructing a minimal compatible "market" frame -- only
  `twse_index_return_raw` carries real values; the volume/vol columns used
  purely for synthetic OHLC cosmetics are zero-filled since this research
  never reads them). Outputs:
  `results/twii_proxy_2011_2014_prepared_20260705_{prices,chip_features,manifest}.{csv,json}`.
  Crash sanity check (2011-07..2011-12): 0050 proxy MDD -24.83% (real TAIEX
  2011 decline was ~-21%, matches). ma20 correctly entered defensive on
  2011-08-04 -- the exact week of the US debt-ceiling/S&P-downgrade panic.
- `scripts/misc/garch_specialist_routing_2011_fold_20260705.py`:
  train=2008-06-02..2010-12-31 (includes the tail of the 2008-2009 recovery
  -- realistic, since by 2011 you would already have lived through 2008),
  test=2011-01-01..2012-12-31.
  Output: `results/garch_specialist_routing_2011_fold_20260705.json`.

Result:

| | Test Sharpe | MDD | Total return |
|---|---:|---:|---:|
| a207 (never fires, same caveat) | -0.393 | -26.08% | -14.90% |
| ma20 / static_best_frozen | -0.382 | -26.95% | -15.11% |
| garch_selector_frozen | -0.369 | -26.76% | -14.94% |
| garch_guard_frozen | -0.353 | -25.63% | -13.96% |

Same *direction* (selector/guard both nominally beat static_best), but much
weaker: robustness check found only **14/24** selector variants win (vs
24/24 in 2008), 9/27 guard (same subset-limitation as 2008). All five
candidates post *negative* Sharpe and lose 14-15% total return -- routing
does not rescue a bad two-year stretch, it only marginally reduces the
damage (selector -14.94% vs static_best's -15.11%, a small gap versus 2008's
much clearer +0.53% vs -3.59%).

### 2020 (real data, COVID V-shaped crash+recovery)

No proxy needed -- highest-quality fold. 0050.TW/00631L.TW/00632R.TW have
continuous real OHLCV from 2015-01-05. `institutional_data`/`margin_data`
start exactly 2020-01-02 (the fold's test-window start), so total_risk_score
is less chip-thin than 2008/2011 but still limited (foreign_shareholding/
short_sale_balance/securities_lending/day_trading/derivative_institutional
tables only start 2025-01-02). `00679B.TWO` (real data starts 2020-01-02
too) was back-filled flat for the pre-2020 train window -- negligible given
its ~0-0.05% weight in both books.

Script: `scripts/misc/garch_specialist_routing_2020_fold_20260705.py`
(custom loader `_load_real_prices_with_00679b_backfill`, no synthetic proxy
module needed). train=2015-01-05..2019-12-31, test=2020-01-01..2020-12-31.
Output: `results/garch_specialist_routing_2020_fold_20260705.json`.

Result:

| | Test Sharpe | MDD | Total return |
|---|---:|---:|---:|
| a207 (0 events, stayed golden1 the whole crash) | 1.299 | -34.32% | **+36.02%** (highest) |
| ma20 / static_best_frozen | 1.364 | -28.13% | +31.60% |
| garch_selector_frozen | 1.391 | -28.49% | +32.92% |
| garch_guard_frozen | 1.337 | -26.73% | +28.66% |

Notable reversal: a207, by never de-risking, captured the *entire* V-shaped
rebound and posted the highest total return of all four candidates -- in a
fast V-shaped crash, "don't cut exposure just because volatility spiked" was
the right call, unlike the prolonged 2008/2011 declines.

Robustness check: selector only **13/24** (near coin-flip, tight range
1.355-1.399 -- looks like noise, not signal). Guard actually **loses** to
static_best this time (1.337 vs 1.364, only 6/27 grid variants win) --
weaker than either prior fold.

## Consolidated 3-Real-Crisis Table

| Crisis | Shape | Selector full-grid win rate | Guard full-grid win rate | Magnitude |
|---|---|---:|---:|---|
| 2008 | Prolonged (18mo) | 24/24 | 9/27 | Large, clearly positive |
| 2011 | Grinding decline | 14/24 | 9/27 | Small, all-negative regime |
| 2020 | V-shaped | 13/24 | 6/27 (guard loses) | Small, noise-level |

**Reading all three together: 2008 looks like the favorable outlier, not a
general property of GARCH-proxy vol-based routing.** Guard is never robust
across any of the three (best case 9/27 = one-third), and even selector's
edge collapses to near-coin-flip outside the one prolonged-crash sample.
De-risking on a vol spike has a real, demonstrated cost in fast V-shaped
recoveries. **Do not describe this research as "routing works" -- describe it
as "direction is occasionally consistent, magnitude is mostly small, one out
of three real crises showed a strong effect."**

## Shadow Overlay Implementation (Only Production-Adjacent Change)

Given the mixed evidence, the only thing wired into the live pipeline is a
diagnostic-only shadow observer -- it cannot affect any weight decision.

- `group_a_plus/integrations/garch_regime_shadow.py`:
  `compute_garch_regime_shadow(db_path, as_of_date)` computes, for one day,
  what the frozen selector rule (`ratio_threshold=1.05, percentile_threshold=0.70,
  require_negative_5d=True` -- the only combo stable across all six 2022-2026
  folds, and part of the 24/24 winning grid in 2008) would pick: `a207` vs
  `ma20`, and each rule's current regime. `append_garch_regime_shadow_log(...)`
  appends one JSON-lines row per real trading day to
  `results/garch_regime_shadow_log.jsonl`, replacing any existing row for the
  same date (idempotent under same-day re-runs).
- Wired into `group_a_plus/operations/daily_signal.py`: new `garch_regime_shadow`
  field in the live-signal output (next to `market_state`, same "diagnostic
  only, never feeds target_weights/execution_regime" contract), plus the log
  append call. Runs automatically every night via the existing scheduled
  `daily_signal.py` invocation in `scripts/run/run_ncf_daily_pipeline.py` --
  no further wiring needed; the log accumulates real forward observations on
  its own from now on.
- Tests: `tests/test_group_a_plus_garch_regime_shadow.py` (6 tests: calm
  market -> a207/no high-vol-flag; injected late crash -> ma20/high-vol-flag
  with negative 5d return; insufficient/out-of-range history -> `unavailable`
  status without raising; log append + idempotent per-date replace; missing
  shadow status is not logged).
- One pre-existing latent gap found while writing the test fixture:
  `_load_chip_features`'s `_attach_smart_money_cost_proxy` unconditionally
  LEFT JOINs `institutional_data`/`margin_data` (unlike every other optional
  chip source, which is gated behind `_table_exists`) -- a minimal test DB
  needs those two tables present (even empty) or the query raises
  `CatalogException`. Not fixed (pre-existing behavior, not part of this
  session's scope), just documented in the test file so it isn't
  re-discovered as a surprise later.

## Verification

```bash
.venv/bin/python -m pytest tests/test_group_a_plus_garch_regime_shadow.py -q
# 6 passed

.venv/bin/python -m pytest tests/test_group_a_plus_daily_signal_v2.py \
  tests/test_group_a_plus_latest_strategy.py tests/test_group_a_plus_market_state.py \
  tests/test_group_a_plus_ncf_integration.py tests/test_group_a_plus_signal_alignment.py \
  tests/test_run_ncf_daily_pipeline.py tests/test_backtest_group_a_plus_switch_policy_chip_fallback.py \
  tests/test_ncf_2330_checklist.py tests/test_ncf_2330_checklist_factor_quality.py \
  tests/test_ncf_2330_factor_quality_tier_overlay_shadow.py tests/test_ncf_2330_market_state.py \
  tests/test_group_a_plus_garch_regime_shadow.py -q
# 181 passed

.venv/bin/python -m pytest tests/ -q -k "group_a_plus or ncf or daily_signal or market_state"
# 319 passed, 268 deselected -- no regressions across the wider surface
```

End-to-end smoke test against the real DB (`build_daily_signal('2026-07-03', ...)`)
confirmed `garch_regime_shadow` renders correctly (2026-07-03: vol_ratio=1.57,
percentile=0.87 -- elevated -- but return_5d=+5.09% positive, so
`require_negative_5d` keeps `high_vol_flag=False`, selects `a207`; both
`a207_regime`/`ma20_regime` were `golden1` that day anyway) and that
`results/garch_regime_shadow_log.jsonl` got the first row written.

## Files Added This Session

Research scripts (read-only w.r.t. production code):

- `scripts/misc/garch_specialist_routing_walkforward_20260705.py`
- `scripts/misc/prepare_2008_twii_proxy_data_20260705.py`
- `scripts/misc/garch_specialist_routing_2008_fold_20260705.py`
- `scripts/misc/prepare_2011_2014_twii_proxy_data_20260705.py`
- `scripts/misc/garch_specialist_routing_2011_fold_20260705.py`
- `scripts/misc/garch_specialist_routing_2020_fold_20260705.py`

New production-adjacent files:

- `group_a_plus/integrations/garch_regime_shadow.py`
- `tests/test_group_a_plus_garch_regime_shadow.py`

Modified:

- `group_a_plus/operations/daily_signal.py` (new import, `GARCH_REGIME_SHADOW_LOG`
  constant, `garch_regime_shadow` computation + log-append call, new
  `garch_regime_shadow` field in the returned dict)

Result/data files (all in `results/`, all research artifacts not read by
production code except the shadow log):

- `garch_specialist_routing_walkforward_20260705.json`
- `twii_proxy_2008_prepared_20260705_{prices,chip_features}.csv`,
  `twii_proxy_2008_prepared_20260705_manifest.json`
- `garch_specialist_routing_2008_fold_20260705.json`
- `twii_proxy_2011_2014_prepared_20260705_{prices,chip_features}.csv`,
  `twii_proxy_2011_2014_prepared_20260705_manifest.json`
- `garch_specialist_routing_2011_fold_20260705.json`
- `garch_specialist_routing_2020_fold_20260705.json`
- `garch_regime_shadow_log.jsonl` (grows daily via the production pipeline
  from now on)

## DB Changes (Real, Not Reversible Without Explicit Cleanup)

`FinRL/data/stock_data.db`'s `external_market_ohlcv` table (provider=
'yfinance', ticker='^TWII') was extended backward from 2014-01-02 to
2008-06-02 via a live yfinance fetch this session (`purpose` tags
`2011_2014_gap_fill_research` in the `external_data_version` audit table).
This is the same table/provider/caching function already used for every
other external ticker in this repo (`2330.TW`, `SOXX`, `NVDA`, etc.) --
low-risk, well-precedented, and reversible by deleting rows for that ticker/
date-range/provider if ever needed. No other table was modified.

## Known Remaining Data Gaps (Not Addressed This Session)

- `0050.TW`/`00631L.TW`/`00632R.TW` real `ohlcv` data still has no rows
  2011-01-01..2014-12-31 (only `^TWII` was backfilled; the ETF-level gap is
  still proxy-only, matching the 2008 fold's same limitation).
- Real chip/derivative data (`foreign_shareholding_data`,
  `short_sale_balance_data`, `securities_lending_data`, `day_trading_data`,
  `derivative_institutional_data`) only starts 2025-01-02. `institutional_data`/
  `margin_data` start 2020-01-02. `market_margin_data` is the only chip-ish
  source with real coverage back to 2007-07-02. This means **no historical
  fold before 2025 can properly test a207-style chip-gated logic** -- every
  a207 result in this document (2008/2011/2020) reflects "chip gate
  structurally cannot fire," not a real historical evaluation of a207's own
  design.

## Recommended Next Steps

1. Do not promote GARCH-proxy volatility routing (selector or guard) to
   production from this backtest evidence -- the 2008 result does not
   generalize cleanly across 2011/2020.
2. Let `results/garch_regime_shadow_log.jsonl` accumulate real forward days.
   Revisit only once there is a real future high-vol episode to check
   `high_vol_flag`/`selected_rule` against actual outcomes -- not by
   re-running more backtests on the same three historical crises.
3. If a fourth historical crisis is ever wanted for more evidence, the 2011
   gap-fill pattern (fetch real `^TWII` via `ncf_external_cache.fetch_yf_close_cached`,
   build proxy ETF prices via `twii_proxy_utils`) is reusable for any other
   TWII-covered period; real per-ETF `ohlcv` gaps (2011-2014) would need the
   same treatment if a non-TWII-proxy fold is ever wanted for that window.
4. This session's uncommitted work adds to the existing pending-commit batch
   from 2026-07-04/07-05 (chip fallback, market_state arbitration, ncf_2330
   advisory wiring) -- per explicit user instruction this session, git
   status/commit was left untouched.
