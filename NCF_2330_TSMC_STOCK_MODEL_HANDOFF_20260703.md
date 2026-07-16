# NCF_2330 — TSMC Single-Stock NCF Model Handoff - 2026-07-03

## Executive Summary

Built `ncf_2330.py`, a new standalone Next Close Forecast (NCF) model for 2330.TW (TSMC
common shares), modeled on the existing `ncf_00632r.py` / `scripts/misc/ncf_00631l.py`
architecture. This follows up on the same-day TSMC relative-strength research (2330.TW vs
0050 / TSM ADR lead-lag / vs SOXX-Nasdaq-NVDA-ASML / vs 0050-ex-TSMC).

**This is a standalone, shadow-only artifact. It is not wired into `a2118`, `daily_signal.py`,
`group_a_plus_config.json`, or any production decision path.** No existing production file
was modified.

**Decision: do not integrate into any production path yet.** H1/H5 signal is near-noise and
H20's headline AUC has a meaningful single-split optimism bias once purged cross-validation is
applied. The most promising lead (monthly revenue YoY) is worth isolating and validating on its
own before any further integration work.

## Files Produced

- `ncf_2330.py` (new file, ~3,100 lines, mirrors `ncf_00632r.py` / `ncf_00631l.py` structure)
- `results/ncf_2330_20260703.json` (full model output: predictions, validation metrics, feature
  importances, feature-stability report)
- `results/ncf_2330_panel_latest_20260703.csv` (340-row daily prediction panel over the
  validation period, same column convention as `ncf_00631l_panel_latest_*.csv`)
- `results/finmind_2330_monthly_revenue_cache.csv` (198 rows, FinMind `TaiwanStockMonthRevenue`,
  2010 ~ present; cached locally, not written to the production DB)

## Key Data-Source Finding (Important, Unexpected)

**2330.TW has zero per-stock chip/institutional data in the local DB.** `institutional_data`,
`margin_data`, `foreign_shareholding_data`, `short_sale_balance_data`, and
`securities_lending_data` all return `COUNT(*) = 0` for `ticker = '2330.TW'` — these tables are
only populated for the ETF tickers used elsewhere in GroupA+ (0050.TW, 00631L.TW, 00632R.TW,
etc.), not for individual stocks. This was assumed to be the opposite going in (TSMC usually has
the deepest, best-tracked chip data in the market) — the local pipeline simply never ingested it
at the individual-stock level.

Consequence: `ncf_2330.py` has no chip/institutional features at all. It relies on OHLCV
technicals (from `external_market_ohlcv`, not the `ohlcv` table — 2330.TW is not in `ohlcv`),
macro/cross-market features (TWII, SOXX, Nasdaq, KOSPI, Nikkei, HSI, VIX, USD/TWD, USD/JPY),
TSM ADR features, and the newly added monthly revenue features.

## Individual-Stock-Specific Checks (requested mid-run)

| Check | Result |
|---|---|
| Dividend adjustment | `external_market_ohlcv` for 2330.TW was fetched via `yfinance` with `auto_adjust=True`; close is already dividend/split-adjusted. No ex-dividend gap artifact. No fix needed. |
| Monthly revenue feature | No local DB table. Added via FinMind `TaiwanStockMonthRevenue` API (198 rows). Added `revenue_yoy`, `revenue_mom`, `revenue_yoy_accel`, `revenue_ytd_yoy`. |
| ADR share ratio | Confirmed 1 ADR = 5 common shares (TSMC's 1997 ADR program). Not actually load-bearing for the model: all ADR features are return-based, so a ratio error would not have affected them (scale-invariant). Side finding: reverse-engineered ADR premium/discount vs spot is real and time-varying, roughly 11-26% — noted, not turned into a feature this round. |
| Leveraged/inverse-ETF-specific features (NAV tracking error, daily decay) | Confirmed the `00631L`/`00632R` templates don't actually have these either — nothing to exclude. |

### Data quality bug found and fixed

FinMind's `create_time` field was missing for 194/198 rows and had duplicate timestamps on the
remaining 4 — using it directly for revenue "as-of" alignment caused a reindex crash. Fixed by
using a conservative proxy publish date (disclosure month + 21 calendar days), which does not
look ahead. Verified coverage at 99.9% of trading days in the sample window.

## Validation Results

Labeling: H1/H20 use simple forward-return direction; H5 uses triple-barrier labeling.
Probability calibration: isotonic regression, applied to 4 of the classification models.

### Single-split validation vs purged K-fold (5-fold, with embargo)

| Horizon | Single-split AUC | Purged-CV AUC | Δ | Ensemble Brier | Feature-stability grade |
|---|---:|---:|---:|---:|---|
| H1 | 0.5375 | 0.5408 | +0.003 | 0.2486 | C |
| H5 | 0.5662 | 0.5242 | **-0.042** | 0.2357 | C |
| H20 | 0.6314 | 0.5612 | **-0.070** | 0.1756 | A |

H20's headline single-split AUC (0.63) looks strong on its own, but the purged-CV estimate
(which accounts for label overlap and applies an embargo) is a more honest 0.56 — there is a
meaningful single-split optimism bias, not the strength the raw number suggests. H1 is close to
noise on both measures.

Walk-forward (5-window) average directional accuracy, best model per horizon:

| Horizon | Best WF model | Avg accuracy |
|---|---|---:|
| H1 | rf | 0.5161 |
| H5 | et | 0.5663 |
| H20 | gb | 0.5705 |

Forward tail-risk auxiliary models (H20, 5% threshold): drawdown-risk AUC 0.626 / Brier 0.185;
upside-reward AUC 0.603 / Brier 0.246 — both mildly informative, not strong.

### ADR-leads-spot hypothesis: partially confirmed

Same-day research found `corr(ADR return t-1, 2330.TW return t) = 0.50` vs `corr(t-0) = 0.21`.
In the trained model, ADR-derived features rank:

| Horizon | Best ADR feature | Rank (of 141) |
|---|---|---:|
| H1 | `adr_vs_nasdaq_excess` | 31 |
| H5 | `us_tsm_adr_10d_ret` | **16** |
| H20 | `us_tsm_adr_10d_ret` | 69 |

The effect shows up with moderate-to-high importance at H1/H5 and fades by H20 — consistent
with "overnight information decays over longer holding periods," but ADR features are not the
single strongest predictor at any horizon; macro/cross-market features (VIX interactions, SOXX
returns, MA ratios) and revenue features dominate.

### Surprise finding: monthly revenue is the single strongest H20 feature

`revenue_ytd_yoy` is the **#1 of 141 features** at H20 (importance 0.038, ~3x the #2 feature),
with `revenue_yoy` at #5 and `revenue_yoy_accel` at #6, all appearing in 4-5 of 5
feature-stability folds. At H5, `revenue_yoy_accel` is #14 (top10_freq 3/5). This was not
anticipated when the model was scoped — it was added as a nice-to-have individual-stock feature,
not expected to dominate.

`earnings_window_flag` (the coarse quarter-end+N-day calendar proxy added as a stand-in for real
earnings-call dates) ranks 129-131/141 across horizons — essentially useless. It should be
replaced with actual earnings/investor-conference dates if this line of work continues, not kept
as-is.

## Recommendation

- **Do not integrate into `a2118` or any production decision path now.** H1/H5 are too weak;
  H20's raw AUC has a demonstrated optimism bias under purged-CV, matching the same
  single-window-overfitting pattern already flagged in
  [[feedback_strategy_promotion_caution]] and in today's separate 2008-shadow-candidate
  rejection ([[project_2008_stress_shadow_candidate_20260703]]).
- **Keep as an independent shadow artifact.** Re-running it periodically to track whether H20 +
  revenue-driven signal holds up out of sample is reasonable; it should not gate any trade.
- **Next step, if pursued further:** isolate and validate the monthly-revenue signal on its own
  (e.g., a dedicated backtest of a "post-monthly-revenue-release 20-day window" effect) rather
  than promoting the whole bundled model. Also replace `earnings_window_flag` with real
  earnings/investor-conference dates before relying on any event-window feature.

## No Production Changes

`group_a_plus/governance/latest.py`, `group_a_plus/runners/a2118.py`,
`group_a_plus/operations/daily_signal.py`, `group_a_plus_config.json`, and
`report/group_a_plus/latest/*` were not modified. `ncf_2330.py` and its outputs are net-new,
standalone files.
