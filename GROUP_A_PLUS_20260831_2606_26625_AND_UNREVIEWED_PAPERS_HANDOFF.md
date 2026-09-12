# GroupA+ 2026-08-31 Handoff: 2606.26625 Continued Work + Unreviewed-Papers Sweep (2604.08356, 2605.11423, 2606.09025, 2607.05291, 2512.11273, 2608.09641, 2608.05755, 2608.07690, 2608.10788)

## Status

Ten pieces of work across this continuous session (spanning 2026-08-31 into
2026-09-01), in order. No live strategy, target weight, order, or execution
gate was changed by any of them — everything is research/shadow governance
or desk-review closure. **All 9 of the originally-unreviewed Downloads
papers are now closed: 1 adopted as a diagnostic (`2604.08356`), 8
`closed_negative`.** The Downloads sweep from Part 2 is complete.

1. **2606.26625 (commodity ETF CVaR/tail-cost)**: continued from an earlier
   same-day session that had been cut short by context compaction before it
   was documented. Added a rolling no-add gate, then quantified whether a
   real dynamic CVaR optimizer is worth building — `closed_negative` on the
   optimizer, upper bound turned out to be an in-sample artifact.
2. **9-paper Downloads sweep**: full-text-searched every PDF in
   `C:\Users\isaac\Downloads\` against docs/registry/memory to find papers
   never reviewed. Found 9. **6 reviewed so far; 3 remain** (list at the end).
3. **arXiv:2604.08356 (MRP strategy-decay diagnostic)**: reviewed, tested
   hands-on against real production data. **Positive, adopted as a
   diagnostic** (not wired into daily pipeline yet).
4. **arXiv:2605.11423 (VVG intraday classifier, MNQ futures)** and
   **arXiv:2606.09025 (US growth-defensive cash overlay)**: both
   `closed_negative`, desk review.
5. **arXiv:2607.05291 (TSFM realized-volatility forecasting)**:
   `closed_negative`, desk review — the paper's own effect size is thin, and
   GroupA+ already has a documented, much larger negative result
   (2510.03236) from trying to upgrade its volatility forecast on Taiwan-only
   data.
6. **arXiv:2512.11273 (IPMO — end-to-end differentiable multi-period
   portfolio optimization)**: `closed_negative`, desk review — solves a
   scalability/alignment problem GroupA+ doesn't have; doesn't address the
   real blocker found in Part 1 (too-small, too-correlated asset universe).
7. **arXiv:2608.09641 (lower spectrum of correlation matrices / RMT)**:
   `closed_negative`, desk review — Marchenko-Pastur asymptotics require a
   large asset universe; GroupA+'s 4-ticker pool is mathematically too small,
   same closure logic as the already-closed `2608.20020`.
8. **arXiv:2608.05755 (LSTM with sector embeddings)**: `closed_negative`,
   desk review — the core contribution requires a broad, multi-sector cross-
   section (S&P 500 constituents) to embed; GroupA+ has no such
   cross-section.
9. **arXiv:2608.07690 (OTC market-making order imbalance/skew/width)**:
   `closed_negative`, desk review — pure dealer-quoting theory; GroupA+ never
   quotes bid/ask or takes on inventory risk from customer flow, the clearest
   domain mismatch of the 9 papers.
10. **arXiv:2608.10788 (Triadic Stress Index — correlation-network
    topology)**: `closed_negative`, but only after confirming it is a
    genuine, rigorous paper (its abstract's soil-microbial-network framing
    had raised a legitimate quality concern). Same "asset universe too
    small" closure logic as `2608.09641`/`2608.20020`.

Full detail for each piece already exists in per-paper handoff docs and
memory entries; this document is the consolidated index plus anything not
already written elsewhere (mainly the Downloads-sweep method and the
remaining-papers list).

---

## Part 1: 2606.26625 — Rolling No-Add Gate + CVaR-Optimizer Feasibility

Full detail: `docs/HANDOFF_2606_26625_COMMODITY_ETF_CVAR_TAIL_COST_GROUPA_PLUS_20260718.md`
(the 2026-08-31 sections at the bottom). Memory:
`project_2606_26625_commodity_etf_cvar_tail_cost_20260831`.

### 1a. Rolling tail no-add gate (recovered from an interrupted earlier session)

Before this session's visible start, an earlier same-day pass had already
built `scripts/evaluate/build_group_a_plus_2606_26625_rolling_tail_no_add_gate.py`
and wired it into the daily pipeline / `research_shadow_decision_snapshot` /
`check_group_a_plus_daily_status.py`, but the work was never written into the
handoff doc before context ran out. This session found the untracked files
via `git status`, verified all tests still pass (63 passed across the full
2606.26625 test set), and back-filled the handoff doc and the
`docs/GROUPA_PLUS_RECENT_PAPER_IMPORT_STATUS_20260807.md` index.

Result: rolling 63/126/252-day gate blocks new `00631L.TW` adds in `3/3`
windows, does not block `00632R.TW` opens (`0/3` windows).

**Lesson for future sessions**: when a user re-asks a question that looks
like it was already answered earlier the same day, check `git status` for
untracked scripts/tests matching the paper ID before redoing the work — the
harness's context compaction can silently drop work-in-progress that was
never committed to a doc.

### 1b. CVaR-optimizer feasibility (in-sample upper bound)

User asked directly whether a real dynamic CVaR optimizer (the paper's
actual proposal) is worth building. Rather than answer from priors, solved a
Rockafellar-Uryasev mean-CVaR LP
(`scripts/evaluate/evaluate_group_a_plus_2606_26625_cvar_optimizer_upper_bound.py`,
3 tests passed) as an in-sample look-ahead upper bound across the same 5
stress windows used in the earlier window-split audit.

Result: the optimizer "beats" the latest strategy's ES95/MDD in `5/5`
windows, but the optimal weights simultaneously hold large positions in both
`00631L.TW` (25-29%) and `00632R.TW` (58-65%) — a combination the production
switch-regime logic never takes, since it's a mutual-exclusivity regime
switch, not a continuous blend. The LP can only reach this "low risk, high
return" region because it has look-ahead knowledge of that window's realized
price path; it is exploiting in-sample noise in the 00631L/00632R
correlation, not a real forward-usable hedge — a textbook in-sample
overfitting artifact.

**Conclusion**: do not build a live dynamic CVaR optimizer. The reported
5/5 headroom is not real; building the real thing would need a mutual-
exclusivity or turnover-cost constraint plus walk-forward refitting before
the headroom estimate could be trusted, and there's no evidence yet that
doing so would clear a meaningful bar.

---

## Part 2: Downloads Sweep Method (9 unreviewed papers found)

User asked "還能做什麼" (what else can be done). Method used:

```bash
ls /mnt/c/Users/isaac/Downloads/*.pdf | grep -oE '[0-9]{4}\.[0-9]{4,5}' | sort -u
# for each id: grep -rl "$id" docs/ *.md group_a_plus/ scripts/ tests/ report/ <memory-dir>
```

133 total PDFs in Downloads; 9 had zero hits anywhere in the repo, the
research semantic registry, or every memory file:

| arXiv ID | Title (short) | Status after this session |
|---|---|---|
| `2604.08356` | MRP strategy-decay (Alexander & Fabozzi) | **Reviewed — adopted as diagnostic** |
| `2605.11423` | VVG intraday classifier (MNQ futures) | **Reviewed — closed_negative** |
| `2606.09025` | Growth-defensive cash overlay (Xiong) | **Reviewed — closed_negative** |
| `2607.05291` | Forecasting realized volatility with time-series foundation models | **Reviewed — closed_negative** |
| `2512.11273` | Integrated prediction + multi-period portfolio optimization (IPMO) | **Reviewed — closed_negative** |
| `2608.09641` | Lower spectrum of financial correlation matrices | **Reviewed — closed_negative** |
| `2608.05755` | Cross-Sectional Heterogeneity in LSTM Networks | **Reviewed — closed_negative** |
| `2608.07690` | Order imbalance/skew/width in OTC market making (Peter Cotton) | **Reviewed — closed_negative** |
| `2608.10788` | "The Triadic Stress Index in Financial Markets" | Not yet reviewed (abstract references soil-microbial-network literature — verify this is a genuine finance paper before investing time) |

Note: this sweep only checked file-path text search across docs/registry/
memory. It is a lower bound on "reviewed" (a paper discussed only in a
long-since-summarized conversation with no file trace would still show as
unreviewed) but a reasonable proxy given the project's practice of writing a
handoff doc or memory entry for every paper reviewed.

---

## Part 3: arXiv:2604.08356 — MRP Strategy-Decay Diagnostic (Adopted)

Full detail: `docs/HANDOFF_2604_08356_MRP_STRATEGY_DECAY_GROUPA_PLUS_20260831.md`.
Memory: `project_2604_08356_mrp_strategy_decay_20260831`.

MRP1 (Minimum Regime Performance — worst realized Sharpe across one
exhaustive-search split of a return series) computed on the production
switch-policy equity curve
(`results/whatif_four_axis_switch_backtest_20260819_curve.csv`,
2020-2026):

| strategy | full-sample Sharpe | MRP1 |
|---|---:|---:|
| production `switch_ma80_dd11` | **1.159** | **0.307** |
| golden1_0531 alone | 1.115 | 0.217 |
| defensive basket alone | 1.112 | 0.155 |

Production strictly dominates both static baselines on the paper's
decay-risk frontier — higher Sharpe AND higher worst-regime Sharpe. A
genuinely positive, independently-derived confirmation, in contrast to the
long run of negative results from prior regime-detection papers (CHASM,
CHMM, EMVRS, VLSTAR).

Implementation: `scripts/evaluate/evaluate_group_a_plus_2604_08356_mrp_strategy_decay.py`
+ `tests/test_evaluate_group_a_plus_2604_08356_mrp_strategy_decay.py` (4
passed, including a direct reproduction of the paper's own Appendix A
inconsistency claim). Intentionally **not wired into the daily pipeline**
yet — it's a one-time confirmation with no actionable threshold; revisit
once there's a second time point to show a trend.

**Side finding, not investigated further**: while locating a longer equity
curve for a `d`-sensitivity check, found
`results/group_a_plus_switch_policy_backtest_longhist_rebalmonthly_20150401_20260810_curve.csv`
has a `switch_risk_ma80_dd11_total6_hold5_eg015_xg015` column that is
byte-identical to `golden1_0531_1m` for its entire 2017-2026 history — a
stale/mis-generated report artifact (confirmed the real production backtest
curve does switch correctly, 14 real events). Flagged so a future session
doesn't accidentally use that file for a switch-vs-golden1 comparison.

---

## Part 4a: arXiv:2605.11423 — VVG Intraday Classifier (Closed, Desk Review)

Memory: `project_2605_11423_vvg_classifier_desk_review_20260831`.

"A Validated Volatility-Volume-Gap Classifier for Regime Identification in
MNQ Intraday Data" (Mathias Mesfin, independent researcher, non-peer-
reviewed). Full 15-page text read. Domain and frequency mismatch with
GroupA+: MNQ (Micro E-mini Nasdaq futures), 5-minute intraday bars, day-
classification for intraday fade/continuation trades. GroupA+ trades Taiwan
ETFs at daily frequency. Additionally, the paper's own conclusion is
negative — all 8 tested directional strategies failed (T-stat below 2.0 or
year-unstable); the author's own verdict is "valid but insufficient, not
wrong." No backtest run; closed via desk review.

## Part 4b: arXiv:2606.09025 — Growth-Defensive Cash Overlay (Closed, Desk Review)

Memory: `project_2606_09025_cash_overlay_desk_review_20260831`.

"Continuous Cash-Overlay Filters for a Static Growth-Defensive Risk Sleeve"
(Zheli Xiong, 32 pages, full text read). Architecture: two independent
continuous risk scores — a **slow-tail compensation filter** (targets
2022-style slow rate-hike drag) and a **V-shape crash brake** (targets fast
drawdowns like 2020/2025) — combined via `w_cash = max(w_slow, w_vshape)`
into a graduated (sigmoid-mapped) cash weight. Full-sample CAGR
16.62%→18.83%, MDD -33.59%→-18.05%, walk-forward validated.

Closed via desk review because both target problems are already solved in
GroupA+ by more precise, already-tested (and in one case already-live)
mechanisms:

- The slow-tail/2022 concept is what
  `docs/HANDOFF_20260814_GROUPA_PLUS_SLOW_BEAR_CASH_FLOOR_CLASSIFIER_SHADOW.md`
  already tested directly against the 2022 window: 8,640-configuration
  sweep, **0/8,640 passed** the formal gate (cash-flooring improved
  final-value/MDD but broke Sortino). The follow-up attribution
  (`docs/HANDOFF_20260814_GROUPA_PLUS_2022_DEFENSIVE_REGIME_ATTRIBUTION.md`)
  found the real 2022 culprit was `00679B` bond exposure in the defensive
  basket under a stock-bond selloff, not insufficient cash — and that fix
  (removing `00679B`) was already promoted to production on 2026-08-18
  (`project_a2118_defensive_basket_00679b_removed_promoted_20260818`).
- The V-shape/fast-crash concept functionally overlaps with the existing
  `switch_ma80_dd11` ma-gap/drawdown/risk-score-override triggers.
- The only architecturally novel piece — continuous sigmoid-mapped cash
  weight instead of a binary switch, combined via max-envelope — has no
  specific unsolved problem left to justify testing it on its own, and the
  paper itself flags unaddressed data-mining risk (no White's Reality
  Check / SPA test / Deflated Sharpe Ratio yet).

No new backtest code written; closure is based on citing the existing
2026-08-14/08-18 real-data evidence.

---

## Part 5: arXiv:2607.05291 — TSFM Realized-Volatility Forecasting (Closed, Desk Review)

Memory: `project_2607_05291_tsfm_volatility_desk_review_20260831`.

"Forecasting Realized Volatility with Time Series Foundation Models: A
Comparison with Econometric Benchmarks" (Alessio Brini, Duke, 41 pages, full
text read). Rigorous multi-model, multi-asset (50 US equities/FX/futures)
comparison of 9 zero-shot time-series foundation models (Chronos, Moirai,
TimesFM, TTM, etc.) against 8 econometric benchmarks (HAR family, ARFIMA,
ARMA, MEM), with formal Diebold-Mariano and Model Confidence Set testing.

Finding: TSFMs do not deliver a uniform gain. Only the smallest model (TTM,
<1M parameters) beats a well-specified Log-HAR, and only by 1.3-1.8%; a
Mincer-Zarnowitz recalibration shows most of that edge is a calibration
effect, not real informational gain (except at the monthly horizon).
Econometric benchmarks remain competitive throughout.

Closed via desk review: GroupA+ already has a documented, much larger
negative result from trying to upgrade its volatility forecast beyond the
existing HAR-RV/GARCH-proxy baseline —
`docs/REVIEW_2510_03236_REGIME_SWITCHING_VOL_FORECAST_GROUPA_PLUS_20260808.md`
found a regime-switching volatility model scored 42-258% *worse* QLIKE than
the existing HAR-RV forecast on real Taiwan OHLC data, because the paper's
original design needed SPX 5-minute data and VIX that Taiwan doesn't have.
Given this paper's own effect size is thin even on rich US/FX/futures data,
and GroupA+ already knows fancier volatility models can fail badly on
Taiwan's more limited data, running 9 large pretrained TSFM zero-shot
inferences for a 1-2% theoretical edge was judged not worth the engineering
cost. No new backtest code written.

## Part 6: arXiv:2512.11273 — IPMO End-to-End Differentiable Multi-Period Optimization (Closed, Desk Review)

Memory: `project_2512_11273_ipmo_desk_review_20260831`.

"Integrated Prediction and Multi-period Portfolio Optimization" (Linghu, Liu,
Deng — Shanghai Jiao Tong / U Chicago, 23 pages, read through the empirical
section). Proposes training a neural return forecaster jointly with a
downstream multi-period mean-variance optimizer (decision-focused learning),
using a new mirror-descent fixed-point (MDFP) scheme that keeps
differentiation cost nearly constant as the planning horizon grows (up to
21.8x faster than CvxpyLayer at horizon 100). Tested on 7 US ETFs, IPMO
consistently beats a two-stage (predict-then-optimize) baseline on Sharpe,
turnover, and weight-path stability.

Closed via desk review: the paper solves two problems GroupA+ doesn't
have — (1) aligning a neural forecaster's training loss with downstream
portfolio-decision quality, and (2) keeping differentiation cost from
exploding as the planning horizon grows. GroupA+ has no continuous
multi-period optimizer to attach this framework to in the first place — the
production switch policy is a discrete regime rule, not a continuous
weight-path optimizer, and building one is exactly what Part 1b of this
document already found not worth doing: with only 4 correlated tickers
(`00631L.TW`/`00632R.TW` are leveraged/inverse of the same underlying), even
a full-information in-sample optimizer produces an economically incoherent
solution. IPMO makes the optimizer's *training* more efficient; it does not
fix the asset-universe size/correlation problem that is the actual blocker.
No new backtest code written.

## Part 7: arXiv:2608.09641 — Lower Spectrum of Correlation Matrices / RMT (Closed, Desk Review)

Memory: `project_2608_09641_lower_spectrum_desk_review_20260831`.

"Lower spectrum of financial correlation matrices: a new perspective on
market synchronization" (Grassi, Pastorino, Uberti — U Milano-Bicocca).
Proposes a market-synchronization indicator (`m⁻`) counting correlation-matrix
eigenvalues below the Marchenko-Pastur lower bound, complementing the
standard PCA/RMT focus on the largest eigenvalues. Tested on S&P500 GICS
sector portfolios, S&P500 constituents, and Nikkei constituents, all
requiring a clustering step to reduce dimensionality first.

Closed via desk review, same logic as the already-closed `2608.20020`
(correlation-matrix rotation as a VRP factor, 2026-08-23): Marchenko-Pastur
asymptotic theory requires both the asset count and sample length to be
large with a meaningful ratio; GroupA+'s 4-ticker universe is mathematically
too small to define a meaningful eigenvalue spectrum at all. No backtest
needed to reach this conclusion.

## Part 8: arXiv:2608.05755 — LSTM with Sector Embeddings (Closed, Desk Review)

Memory: `project_2608_05755_lstm_sector_embedding_desk_review_20260831`.

"Cross-Sectional Heterogeneity in LSTM Networks for Financial Time Series"
(Julius Döbelt, TU Darmstadt, 32 pages, methodology + empirical setup read
in full). Extends the Fischer & Krauss (2018) single-layer LSTM
statistical-arbitrage design with (1) learnable TRBC sector embeddings, (2)
macro-financial covariates, (3) regularization (label smoothing, dropout,
gradient clipping). Strategy: daily binary classification (above/below
cross-sectional median return) across all S&P 500 constituents, long the top
k / short the bottom k. The sector-embedding LSTM beats a plain LSTM, random
forest, and buy-and-hold across all metrics; signal decomposition shows it's
driven by a short-term reversal factor plus an industry-momentum factor.
Also reconfirms (extended through 2024) that LSTM stat-arb profits have
deteriorated sharply since 2010.

Closed via desk review: the paper's core contribution — sector embeddings
capturing cross-sectional heterogeneity — is only meaningful with a broad,
multi-sector universe (S&P 500's 11 GICS sectors). GroupA+'s asset pool
(`0050.TW` tracking the broad index, its own `00631L.TW`/`00632R.TW`
leveraged/inverse derivatives, `00679B.TWO` bonds, and a single-stock model
for `2330.TW`) has no cross-sectional breadth to embed. The long-short
daily-rebalanced trading design is also structurally unlike GroupA+'s
regime-switch architecture. Weak corroborating evidence: GroupA+ has already
found recurrent (LSTM-family) architectures perform poorly on its own data —
RecurrentPPO collapsed to an observation-independent fixed point in both
single-env and multi-env designs (`2607.00475`,
`project_2607_00475_end_to_end_policy_and_seed_averaging_20260824`) — not
the same model family, but a relevant data point on recurrent-architecture
fit for this codebase's data regime. No new backtest code written.

## Part 9: arXiv:2608.07690 — OTC Market-Making Order Imbalance (Closed, Desk Review)

Memory: `project_2608_07690_otc_market_making_desk_review_20260831`.

"On a Simple Relationship Between Order Imbalance, Skew and Width in
Over-The-Counter Trading" (Peter Cotton, 9 pages, read in full). Pure
dealer-quoting theory for OTC/sealed-bid RFQ markets (bonds, physical
commodities): proves that order imbalance (skewed buy/sell customer flow) is
absorbed exactly by a translation of the dealer's skew, a widening of quotes,
and a multiplication of the effective cost of carry — an imbalanced
market-making problem compresses onto the balanced one via a closed-form
symmetry.

Closed via desk review with no further analysis needed — the clearest domain
mismatch of the 9 papers. GroupA+ is a directional buy/hold/regime-switch ETF
strategy; it never quotes a bid/ask spread, never makes markets against
customer request-for-quote flow, and never carries dealer inventory risk. The
paper's entire framework (dealer skew/width/inventory cost/win curve) has no
counterpart in GroupA+'s business model.

## Part 10: arXiv:2608.10788 — Triadic Stress Index (Closed, Desk Review — Confirmed Genuine First)

Memory: `project_2608_10788_tsi_triadic_stress_desk_review_20260831`.

"The Triadic Stress Index in Financial Markets" (Alberto Acedo, Biome Makers
Inc., 21 pages, read through the methodology and results sections). The
abstract's framing — the index descends from network-topology metrics
originally developed to detect "structural monopoly" in soil microbial
co-occurrence networks — raised a legitimate quality concern before reading.
After reading, confirmed this is a genuine, methodologically rigorous
systemic-risk paper: falsifiable pre-registered hypotheses (H1
detection/H2 attribution/H3 coincident-not-leading), block-bootstrap
confidence intervals, out-of-sample calibration, multiple-comparison
correction, and persistent-homology cross-checks, benchmarked against the
Absorption Ratio (the MSCI/central-bank industry standard), effective
rank/Vendi score, and Ollivier-Ricci curvature across equities (incl. banking
crises), crypto, commodities, FX, and sovereign debt, 2006-2026.

The index, TSI = C·D/(M·Coex) (clustering coefficient × density / modularity
× degree-variance of the asset correlation network), ties the best spectral
baselines on detection and beats the Absorption Ratio, but the authors are
explicit that it is a **coincident state index, not a leading indicator**
(zero-lag cross-correlation peak, confirmed by lead-lag analysis).

Closed via desk review, same logic as `2608.09641` and the already-closed
`2608.20020`: correlation-network topology measures need a reasonably sized
node set to be non-degenerate. The paper's own experiments show a related
rival index (the balance index) *saturates* on networks as small as 8 assets
(pinned at its maximum value on 26% of windows), which is why the paper
re-tests on a 464-asset universe to escape that regime. GroupA+'s asset pool
is 4 tickers, half of them (`00631L.TW`/`00632R.TW`) mechanically
±multiples of a third (`0050.TW`) and thus near-perfectly correlated by
construction — well below even the paper's own "too small" threshold, so
correlation-network clustering/modularity/degree-variance carry no
statistical content at that scale. Secondarily, even if computable, TSI is a
coincident stress confirmation, which is what GroupA+'s existing
`total_risk_score`/`tail_risk_score`/drawdown triggers already do. No new
backtest code written.

---

**This closes the 9-paper Downloads sweep from Part 2.** Final tally:
`2604.08356` adopted as a periodic shadow-governance diagnostic; the other 8
(`2605.11423`, `2606.09025`, `2607.05291`, `2512.11273`, `2608.09641`,
`2608.05755`, `2608.07690`, `2608.10788`) all `closed_negative` on desk
review or hands-on testing. No live strategy, target weight, or execution
gate changed across any of the 10 pieces of work documented in this file.

## Verification Summary

```bash
.venv/bin/python -m pytest tests/test_build_group_a_plus_2606_26625_rolling_tail_no_add_gate.py tests/test_evaluate_group_a_plus_2606_26625_cvar_cost_window_split.py tests/test_build_group_a_plus_dynamic_cvar_tail_cost_readiness_review.py tests/test_run_ncf_daily_pipeline.py tests/test_check_group_a_plus_daily_status.py tests/test_build_group_a_plus_research_shadow_decision_snapshot.py tests/test_group_a_plus_paper_convergence_review.py tests/test_build_group_a_plus_paper_convergence_review.py
# 63 passed
.venv/bin/python -m pytest tests/test_evaluate_group_a_plus_2606_26625_cvar_optimizer_upper_bound.py
# 3 passed
.venv/bin/python -m pytest tests/test_evaluate_group_a_plus_2604_08356_mrp_strategy_decay.py
# 4 passed
```

No production code path changed for any of the four pieces of work in this
document. Everything is additive: new research-only scripts, new report/
JSON+MD artifacts under `report/group_a_plus/latest/`, and doc/memory
updates.
