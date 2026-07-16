# Group A+ Paper Import Session Handoff — 2026-07-11

Consolidated record of a single session evaluating two academic papers for
import into Group A+. Both lines of work are **research-only**: nothing in
this session changed any production trading weight, decision rule, or alert
threshold. Detailed per-topic handoffs and raw results are linked throughout;
this document is the narrative index tying them together.

## Session shape

Two independent papers were analyzed, each following the same discipline:
(1) read the full paper, (2) map its claims onto concrete Group A+ code, (3)
build the smallest testable version of the claim, (4) test it with a rigorous
statistical method (not just eyeballing a backtest number), (5) report the
result honestly — including negative/null results — and stop rather than
keep tuning until something looks good.

| Paper | Core claim | Outcome |
|---|---|---|
| arXiv:2606.03828 (Boetti & Nunes) — GNHAR network volatility forecasting | Pooling cross-asset volatility info with *shared* (global-α) network coefficients beats per-asset (individual-α) estimation and beats univariate HAR | Built a real GNHAR-RV forecast; **no significant edge** over existing univariate HAR-RV for 0050.TW (DM test, all p≥0.29). Applied the "shared > individually-estimated" principle elsewhere instead — built NCF signal archive infra to eventually test `ncf.py`'s `blend_live_auc`. |
| Wang & Yan (2021, JBF) — downside-volatility-managed portfolios | Scaling positions by *downside* volatility beats scaling by *total* volatility because downside vol reliably predicts (negatively) future returns, while total vol does not | Built a downside GARCH-proxy variant and tested return-timing power on 0050.TW **and** 00631L.TW; **null on both** (all p>0.25). Not built into any regime gate. |

---

## Part 1: arXiv:2606.03828 — Network Time Series Models for Multivariate Volatility Forecasting

### 1a. Prior art found (same day, earlier session)

Before this session's deep read, a shallow import already existed:
`group_a_plus/integrations/network_volatility_spillover_shadow.py` — a
lagged-correlation cross-asset volatility network (7 ETFs: 0050, 00631L,
00632R, 00679B, 00646, 00713, 00878) used only as a risk **alert**
(`network_spillover_high` in `alert_state.py`), not a forecast. See
`report/group_a_plus/review/md/2606_03828_network_vol_spillover_shadow_handoff_20260711.md`.
This session's paper read went deeper (full Table 2-4 methodology: HAR daily/
weekly/monthly aggregation, GNHAR network-AR specification, global-α vs
individual-α, Model Confidence Set, Diebold-Mariano tests) and found this
shallow version never actually built the forecasting model the paper proposes.

### 1b. GNHAR-RV forecast prototype (this session)

**Built:**
- `group_a_plus/integrations/network_volatility_forecast_shadow.py` — pooled
  GNHAR-RV: global-α (AR + network coefficients shared across all 7 tickers
  via one fixed-effects OLS, only the intercept is per-ticker), fully-connected
  unweighted 1-stage neighbour graph, network order (1,0,1) (daily + monthly
  network terms — the paper's most broadly robust configuration).
- `scripts/evaluate/evaluate_group_a_plus_network_volatility_forecast_quality.py`
  — QLIKE comparison against the existing, already-production-validated
  univariate HAR-RV forecast (`volatility_forecast.py`) for 0050.TW.
- `tests/test_group_a_plus_network_volatility_forecast_shadow.py` — 9 tests.

**Result (2018-01-02 to 2026-07-09, target 0050.TW):**

| h | GNHAR vs HAR-RV (QLIKE) | win rate | DM p-value |
|---|---|---|---|
| 5 | -7.56% (worse) | 0.517 | 0.29 |
| 10 | +3.58% (better) | 0.541 | 0.57 |
| 20 | +7.81% (better) | 0.546 | 0.38 |

Also tested network order (1,1,0): same pattern, still non-significant
(p=0.42/0.90/0.60). **None of the 6 horizon×order combinations are
significant at 5%.**

**Added `diebold_mariano_test` to `group_a_plus/integrations/risk_sensitive_loss.py`**
— Harvey et al. (1997) small-sample-corrected DM test, Bartlett-kernel HAC
variance, truncation lag = h-1. This is new reusable infrastructure (used
again in Part 2 below).

**Why the edge is smaller than the paper's:** the paper's network used 10
largely independent global stock indices; this project's 7-ticker panel is
mostly derivatives of the same underlying basket (0050/00631L/00632R are
index/leveraged/inverse variants of the same TAIEX-50 basket), so "neighbour"
volatility is closer to duplicate signal than genuine spillover.

**Decision:** Not promoted. Closed — this specific panel/order combination is
DM-tested, not just under-tested; do not re-run expecting a different answer.
Full detail: `report/group_a_plus/review/md/2606_03828_gnhar_forecast_prototype_handoff_20260711.md`.

### 1c. Applying "global-α > individual-α" elsewhere: NCF signal archive

Rather than keep fishing for a different ticker panel for GNHAR (which would
risk exactly the multi-round no-correction search this project has been
burned by before), the underlying *methodological* lesson — pool/share
parameters instead of estimating them independently per small-sample entity —
was applied to a different, already-live piece of code:
`group_a_plus/integrations/ncf.py`'s `ncf_dynamic_horizon_signal`, which
blends a stable multi-year OOS AUC prior with the current run's noisy live
single-point validation AUC via `blend_live_auc=0.35` — a judgement call
never checked against realized outcomes because no archive of daily NCF
signal snapshots existed long enough to check it.

**Built:**
- `group_a_plus/integrations/ncf_signal_archive.py` — records each day's raw
  per-horizon probability/AUC plus what `ncf_dynamic_horizon_signal` would
  output under blend candidates 0.0/0.35/0.65/1.0; JSONL append with dedup
  (including within a single batch — see bug below).
- `scripts/evaluate/append_ncf_signal_archive.py` (`--backfill` scans all
  existing dated snapshots) and
  `scripts/evaluate/evaluate_ncf_blend_live_auc_archive.py` (joins archive
  against realized forward price direction, reports hit rate per blend
  candidate once `min_samples` exist).
- **Wired into `scripts/run/run_ncf_daily_pipeline.py`** as a new
  `ncf_signal_archive` best-effort step (added to `BEST_EFFORT_STEP_NAMES`,
  runs right after `ncf_00632r`/before `ncf_2330`) — a failure here is logged
  and skipped, never blocks `ncf_2330`/`daily_signal`/`alert_state`. Verified
  with `--dry-run` (lands at step 12/22) and updated
  `tests/test_run_ncf_daily_pipeline.py`'s two step-order assertions.
- `tests/test_group_a_plus_ncf_signal_archive.py` — 9 tests.

**Bug found and fixed during backfill:** two dated snapshot files
(`ncf_00631l_latest_20260702.json` and `..._20260703.json`) both carry
`last_close_date: 2026-07-02` (the 07-03 snapshot is stale). The original
dedup only checked new rows against already-persisted rows, not against each
other within the same batch, so backfilling both files in one run wrote a
duplicate row. Fixed to dedupe within-batch too; regression test added.

**Current state:** backfilled from all 11 existing daily snapshots
(2026-06-25 to 2026-07-09) → 20 rows. Evaluation correctly reports
`insufficient_data` at every horizon (h=1: n=18, h=5: n=12, h=20: n=0, all
need ≥30) — expected, not a bug; h=20 needs 20 trading days to elapse per
sample. The archive now grows by ~2 rows/trading day automatically. Revisit
in ~2-3 months; use the DM test (not just hit rate) before trusting any
apparent edge. Full detail:
`report/group_a_plus/review/md/ncf_blend_live_auc_archive_handoff_20260711.md`.

---

## Part 2: Wang & Yan (2021, J. Banking & Finance) — Downside risk and the performance of volatility-managed portfolios

### Paper's core claims

1. Scaling position size by **downside volatility** (semivariance from
   negative-return days only) significantly outperforms scaling by **total
   volatility** — across spanning regressions, real-time (out-of-sample)
   strategies, and direct Sharpe comparisons, for 9 equity factors and 94
   anomalies (1926-2018 US data).
2. Decomposition: the outperformance is driven almost entirely by
   "return-timing" — downside vol reliably, negatively predicts future
   returns (positive in 71/94 anomalies), while total vol has near-zero
   return-timing power (positive in only 42/94 anomalies). Both have similar
   "volatility-timing" (persistence) power.
3. Independent lesson: in real-time combination strategies, **fixed weights**
   (e.g. 50/50) beat weights estimated to be "optimal" in real time, because
   of parameter instability/estimation risk.

### What was tested

Target: `group_a_plus/integrations/garch_regime_shadow.py`'s
`volatility_gate_reference` (shadow-only, not consumed by live allocation) is
gated by a **symmetric** GARCH(1,1) proxy
(`_garch_proxy_vol` in `scripts/backtest/backtest_group_a_plus_financial_econometrics.py`)
— exactly the "total volatility" the paper contrasts against downside vol.

**Built (before investing in the heavier walk-forward trading-curve
machinery, a cheap direct test of the mechanism first):**
- `_garch_proxy_vol_downside` added alongside `_garch_proxy_vol` — same
  GARCH(1,1)-style recursion, but the shock term only fires on
  negative-return days (asymmetric/GJR-style). `_garch_features` extended
  with 3 new columns, purely additive.
- `tests/test_backtest_group_a_plus_financial_econometrics_downside.py` — 3 tests.
- `scripts/evaluate/evaluate_downside_vol_return_timing.py` — regresses
  forward h-day return (h=5/10/20) on the lagged, causal 252d rolling
  percentile of each vol proxy, with Newey-West/Bartlett-HAC t-statistics
  (reusing the same rigor as `diebold_mariano_test` from Part 1).

**Result — null on both tickers tested:**

0050.TW (2013-01-01 to 2026-07-09):

| h | total_vol slope/t/p | downside_vol slope/t/p |
|---|---|---|
| 5 | +0.0018 / 0.59 / 0.557 | +0.0010 / 0.34 / 0.736 |
| 10 | +0.0028 / 0.45 / 0.650 | +0.0023 / 0.39 / 0.694 |
| 20 | +0.0062 / 0.51 / 0.609 | +0.0050 / 0.40 / 0.688 |

00631L.TW (2015-01-05 to 2026-07-09, the one ticker with an a-priori reason —
leverage/volatility-sensitivity — to show a stronger effect):

| h | total_vol slope/t/p | downside_vol slope/t/p |
|---|---|---|
| 5 | +0.0066 / 1.12 / 0.262 | +0.0047 / 0.79 / 0.430 |
| 10 | +0.0130 / 1.13 / 0.258 | +0.0103 / 0.90 / 0.366 |
| 20 | +0.0202 / 0.89 / 0.373 | +0.0192 / 0.85 / 0.395 |

All 12 combinations across both tickers: p>0.25. Both slopes are the wrong
sign (weakly positive; the paper's mechanism requires negative), and downside
vol is never more negative than total vol. **Not a contradiction of the
paper** — its own MKT-factor return-timing component (closest analog to a
broad-market ETF) was already the smallest of its 9 factors, estimated over
~90 years of monthly US data; 0050.TW/00631L.TW have only ~11-13 years of
daily history, far too little power to detect an effect that marginal even in
the paper's own best-matching case.

**Decision:** Closed. Do not build a downside-vol regime gate, do not touch
`garch_regime_shadow.py`'s gate/selector/guard, do not test further tickers
without a new specific reason (avoiding the multi-round no-correction search
pattern). `_garch_proxy_vol_downside` is kept as harmless, tested
infrastructure. The paper's "fixed weight beats optimized weight" lesson
needed no new action — already the existing pattern in `ncf.py`'s
`blend_live_auc` and `garch_regime_shadow.py`'s discrete reference-scale
buckets. Full detail:
`report/group_a_plus/review/md/downside_volatility_return_timing_handoff_20260711.md`.

---

## All files touched this session

**New modules:**
- `group_a_plus/integrations/network_volatility_forecast_shadow.py`
- `group_a_plus/integrations/ncf_signal_archive.py`

**Modified modules (additive only, no existing behavior changed):**
- `group_a_plus/integrations/risk_sensitive_loss.py` (+ `diebold_mariano_test`)
- `scripts/backtest/backtest_group_a_plus_financial_econometrics.py` (+ `_garch_proxy_vol_downside`, + 3 `_garch_features` columns)
- `scripts/run/run_ncf_daily_pipeline.py` (+ `ncf_signal_archive` best-effort step)

**New scripts:**
- `scripts/evaluate/evaluate_group_a_plus_network_volatility_forecast_quality.py`
- `scripts/evaluate/append_ncf_signal_archive.py`
- `scripts/evaluate/evaluate_ncf_blend_live_auc_archive.py`
- `scripts/evaluate/evaluate_downside_vol_return_timing.py`

**New tests (all passing):**
- `tests/test_group_a_plus_network_volatility_forecast_shadow.py` (9)
- `tests/test_group_a_plus_risk_sensitive_loss.py` (+4 DM-test cases, 9 total in file)
- `tests/test_group_a_plus_ncf_signal_archive.py` (9)
- `tests/test_backtest_group_a_plus_financial_econometrics_downside.py` (3)

**Modified tests:**
- `tests/test_run_ncf_daily_pipeline.py` (2 step-order assertions updated, 14 total pass)

**New result/report artifacts:**
- `results/group_a_plus_network_volatility_forecast_quality_latest.json`
- `results/group_a_plus_network_volatility_forecast_quality_order110.json`
- `results/ncf_signal_archive.jsonl` (20 rows as of 2026-07-11, grows daily)
- `results/ncf_blend_live_auc_archive_evaluation_latest.json`
- `results/downside_vol_return_timing_latest.json` (0050.TW)
- `results/downside_vol_return_timing_00631l_latest.json` (00631L.TW)
- `report/group_a_plus/review/md/2606_03828_gnhar_forecast_prototype_handoff_20260711.md`
- `report/group_a_plus/review/md/ncf_blend_live_auc_archive_handoff_20260711.md`
- `report/group_a_plus/review/md/downside_volatility_return_timing_handoff_20260711.md`

**Full regression check (last run this session):** 545 tests passed across
the group_a_plus/ncf test suite (3 pre-existing, unrelated FutureWarnings),
plus the daily-pipeline test file (14) and all new test files above.

## Production impact

**None.** No target weight, alert threshold, or trading decision changed.
The only thing now running automatically in production is the
`ncf_signal_archive` logging step in the daily pipeline (best-effort,
observation-only, cannot block or alter any other step).

## What's actually open for the future

1. NCF blend_live_auc archive needs ~2-3 months more daily accumulation
   before `evaluate_ncf_blend_live_auc_archive.py` has enough h=20 samples to
   say anything — re-run then, with a DM-style significance check.
2. Everything else in this session is closed, not paused: GNHAR on this
   7-ticker panel (tested, DM-null) and downside-vol return-timing on
   0050/00631L (tested, null on both) should not be re-run without a
   genuinely new reason (different ticker universe, different data, etc.),
   per this project's standing rule against unmonitored multi-round tuning.
