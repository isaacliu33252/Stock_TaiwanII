# GroupA+ 2026-08-23 Handoff: TXO Deeper-OTM Revalidation + arXiv:2606.23492 CHMM Three-Angle Investigation

## Status

Four independent pieces of work, all closed with no production code changed.

1. **TXO put overlay deeper-OTM hedge-quality revalidation**: `shadow_track`. Real
   but not clean — crisis-specific protection restored, full-window Sharpe
   is a wash.
2. **arXiv:2606.23492, angle A (regime-detection trigger)**: `closed_negative`.
3. **arXiv:2606.23492, angle B (regime-conditional VaR)**: `shadow_track`. Real
   but narrow — works on 0050's 1% VaR, fails on 00631L (the actual traded
   instrument) and on 0050's 5% VaR.
4. **arXiv:2606.23492, angle C (synthetic-data stress test)**: `informative_no_action`.
   The most clean-positive result of the four — no evidence Group A+'s core
   switch-rule logic is overfit to the single realized 2020-2026 history.

---

## Part 1: TXO Put Overlay — Deeper-OTM Hedge-Quality Revalidation

### Background

`2607_00883_txo_put_overlay_affordable_subset_realism_check` (earlier this
session) established that the validated 10%-OTM TXO put overlay's
positive result is essentially eliminated at Group A+'s real NAV under
realistic integer-contract sizing, and that moving to 15-20%-OTM strikes
roughly doubles the affordable-roll fraction (35.1% -> 62.3%/83.1%) — but
explicitly flagged that only AFFORDABILITY had been checked, not the
deeper strike's own hedge quality.

### Method

New script:
`scripts/evaluate/build_txo_put_overlay_deeper_otm_revalidation_2607_00883.py`.
Reuses the affordable-subset script's realistic integer-contract-sizing
machinery unmodified. Tests 90% (validated baseline), 85%, and 80% of
spot, each under full-window / per-year / episode-level evaluation.

### Results

Full-window Sharpe improvement over `switch_alone` is noise-level at
every depth:

| depth | affordable rolls | full-window d_sharpe | full-window d_mdd |
|---|---|---|---|
| 90% (10% OTM, validated) | 35.1% | -0.009 | -0.004pp |
| 85% (15% OTM) | 62.3% | +0.003 | +1.023pp |
| 80% (20% OTM) | 83.1% | -0.015 | +0.574pp |

Deeper OTM does **not** turn this into a clean full-window alpha source —
carry drag in calm years (2021/2023/2024 all show slightly lower hybrid
Sharpe than `switch_alone` at every depth) roughly cancels the
crisis-window gains in the full-sample average.

However, **crisis-specific protection genuinely improves with depth**:

| episode | switch_alone MDD | 90% hybrid MDD | 85% hybrid MDD | 80% hybrid MDD |
|---|---|---|---|---|
| tariff_shock_2025_04 | -15.29% | -15.29% (zero contribution) | **-9.78%** | **-8.21%** |
| bear_2022_full_year | -31.08% | -31.08% | -30.05% | -30.50% |
| covid_crash_2020 | -26.55% | -26.35% | -26.44% | -26.49% |

The 2025 tariff-shock improvement (5.5-7pp MDD reduction) is real and
substantial, driven by affordability rising from 0/12 rolls (90%) to
5/12 (85%) / 10/12 (80%) that year. COVID shows almost no improvement at
any depth because 2020 already had 8-11/12 rolls affordable at 90%-OTM —
there wasn't much headroom to gain.

### Conclusion

`shadow_track`, not promote-ready (no full-window Sharpe improvement, per
`feedback_strategy_promotion_caution` — isolated crisis-window improvement
alone is not sufficient grounds). But this is a materially different,
more interesting finding than the flat closed_negative verdict at the
original 10%-OTM depth: the granularity fix does what it was hypothesized
to do for its target failure mode (fast shocks with low affordability),
it just isn't a free lunch across the whole sample.

### Files

- New: `scripts/evaluate/build_txo_put_overlay_deeper_otm_revalidation_2607_00883.py`
- Registry: `2607_00883_txo_put_overlay_deeper_otm_revalidation`
- Memory: `project_txo_put_overlay_deeper_otm_revalidation_20260823.md`

### Next steps if pursued further

Grid search over strike-depth x premium-budget combinations to find a
full-window-Sharpe-positive sweet spot, or a dynamic depth (deepen only
under elevated crisis-probability conditions rather than a fixed
year-round depth) to avoid the calm-year carry drag. Neither tested here.

---

## Part 2: arXiv:2606.23492 — Continuous HMM Three-Angle Investigation

### Paper

Alswaidan, Jin, Varner, "Continuous Hidden Markov Models for Equity
Returns: Heavy-Tail Emission Families and Regime-Conditional
Value-at-Risk" (2026-06-22). A risk-modeling / synthetic-data-generation
paper (not a strategy paper): a K-state continuous HMM with heavy-tailed
(Student-t/Laplace/GED) per-state emissions, fit by EM, separates the
temporal side (latent regime chain -> ACF of |returns|) from the
distributional side (per-state marginal -> kurtosis), and builds a
regime-conditional VaR from the model's own filtered state posterior.

### First-pass desk review (before hands-on testing)

An initial desk-review pass identified that the paper's own walk-forward
test shows every generator, including the best CHMM variant, gets
rejected specifically at regime-introduction events (COVID 2020, the 2022
rate-hike onset) — the same "reactive not predictive" failure mode
already found this session in `2607_27188_txo_svi_rnd_tail_risk_regime_trigger`.
An `AskUserQuestion` was used to check direction; the user selected
"verify then close" for that framing, but then sent a mid-turn message
proposing a **different, specific angle**: "CHMM separates temporal
dependence from marginal distribution, heavy-tailed emissions capture
real fat tails better than Gaussian — apply directly to 0050/00631L
regime detection, more rigorous than Group A+'s current switch_ma* rule."
Per `feedback_verify_every_paper_independently`, this was tested directly
rather than treated as covered by the earlier closure decision.

### Angle A: Regime-Detection Trigger — `closed_negative`

**Method**: `scripts/evaluate/build_chmm_regime_detector_2606_23492.py`.
From-scratch K=2 Student-t CHMM (Baum-Welch for T/pi, ECM-style weighted
location/scale update, shared-nu selected by grid search each refit —
matching the paper's own Table S9 "shared-nu" ablation, its cleanest
single-row heavy-tail fit) fit on 0050.TW daily log returns.

**Causality** (matching `feedback_lookahead_bug_same_day_signal_decision`):
expanding-window quarterly refit (63 trading days); regime classification
within each following quarter uses only a forward (filtered, not
smoothed) recursion with the already-fixed parameters; the resulting
state call is lagged one trading day before being applied to portfolio
composition. Reused `golden1_0531_1m` and `group_a_plus_defensive_1m`
from the existing switch-backtest curve CSV as the two legs — identical
legs to what `switch_risk_ma80_dd11_total6_hold5_eg015_xg015` blends
under its own rule, isolating the regime classifier as the only variable
under test.

**Result** (full window 2020-01-02 to 2026-08):

| | Sharpe | MDD |
|---|---|---|
| golden1 alone | 1.116 | -37.02% |
| switch_ma80_dd11 (rule) | **1.159** | **-31.08%** |
| CHMM regime switch | 1.066 | -36.20% |

CHMM underperforms the rule on both metrics, and is barely better than
not switching at all on MDD, despite being defensive 48.5% of days
(vs the rule's 22.0%). Day-by-day agreement between the two classifiers
is only 53.6%, correlation 0.067 — essentially uncorrelated.

**Episode breakdown**: CHMM slightly better in COVID 2020 (acute,
volatility-driven, exactly what a Student-t-state HMM should catch), but
clearly worse in the 2022 grinding bear market and the 2025 vol-free
tariff-shock trend. Interpretation: the CHMM's states are keyed only off
realized return magnitude/volatility, which the rule's richer feature set
(MA gap, drawdown depth, chip/derivatives positioning) captures and a
univariate-return HMM structurally cannot.

**Files**: `scripts/evaluate/build_chmm_regime_detector_2606_23492.py`.
Registry: `2606_23492_chmm_heavy_tail_regime_detector`. Memory:
`project_2606_23492_chmm_regime_detector_20260823.md`.

### Angle B: Regime-Conditional VaR — `shadow_track`

Tests the paper's other distinct core claim (not the trigger angle): does
the CHMM's regime-conditional VaR (one-step-ahead predictive mixture
quantile, filtered-state posterior propagated one transition step) pass
Kupiec/Christoffersen calibration on Group A+'s actual instruments,
replicated independently rather than trusting the paper's own US-SPY
result.

**Method**: `scripts/evaluate/build_chmm_regime_conditional_var_2606_23492.py`,
reusing the causal CHMM-fitting machinery from Angle A unmodified. VaR at
day t tested against day t+1's realized return (matching the paper's own
Table 3 design).

**First pass at K=2 failed cleanly on both 0050 and 00631L, both alpha
levels** (all Christoffersen joint-cc p<0.05), and was worse than a
trivial 252-day rolling-quantile historical-VaR baseline. **Caught before
finalizing**: K=2 is not the paper's own recommended state count (K=3,
chosen by the paper's own held-out CV on SPY) — re-ran at K=3 before
drawing any conclusion.

**Result at K=3** (paper's own default):

| | 0050, alpha=0.05 | 0050, alpha=0.01 | 00631L, alpha=0.05 | 00631L, alpha=0.01 |
|---|---|---|---|---|
| CHMM VaR | fails (p_cc=0.007) | **passes (p_cc=0.382)** | fails (p_cc=0.000) | fails (p_cc=0.000) |
| historical VaR baseline | fails (p_cc=0.000) | fails (p_cc=0.000) | fails (p_cc=0.000) | fails (p_cc=0.000) |

On 0050's 1% tail, CHMM genuinely passes Christoffersen joint
conditional-coverage (17/1611 breaches, rate 1.06% vs nominal 1%) and
clearly beats the historical baseline (30/1611 breaches, rate 1.86%,
completely fails). This is a real, correctly-replicated instance of the
paper's own headline claim — not a fluke. But it does not transfer to
0050's 5% level, or to 00631L (the actual leveraged instrument Group A+
holds) at either level. Plausible explanation: 00631L's daily-rebalanced
2x leverage introduces volatility-of-volatility / negative-convexity
compounding effects a plain Student-t HMM on 00631L's own returns doesn't
structurally capture, unlike the cleaner single-volatility-regime
structure the paper's method was built and validated around.

**Conclusion**: `shadow_track`. Given Group A+'s practical need is
00631L risk-sizing, not 0050 in isolation, this doesn't clear an adoption
bar as-is, but the 0050/1%-tail result is a genuine positive worth
recording precisely.

**Files**: `scripts/evaluate/build_chmm_regime_conditional_var_2606_23492.py`.
Registry: `2606_23492_chmm_regime_conditional_var`. Memory:
`project_2606_23492_chmm_regime_conditional_var_20260823.md`.

### Angle C: Synthetic-Data Stress Test — `informative_no_action`

Tests the paper's actual originally-designed use case (not a
repurposing, unlike Angles A and B): use the fitted CHMM as a synthetic
generator to stress-test whether `switch_risk_ma80_dd11`'s apparent edge
over buy-and-hold on the single realized 2020-2026 history is a genuine,
generalizable property or an overfitting artifact
(`feedback_overfitting_fixed_window_tuning`).

**Method**: `scripts/evaluate/build_chmm_synthetic_stress_test_2606_23492.py`.
K=3 Student-t CHMM fit unconditionally on the full 0050.TW history
(n=4316 days — full-sample fit is appropriate here since this is
generation, not a live signal). Simulated N=300 independent synthetic
1611-day paths from the fitted stationary distribution (paper's own
Algorithm 2). Applied a simplified price-only proxy of the switch rule
(same MA-gap/drawdown/hold-day thresholds; chip/derivative gates dropped
as unavailable from a univariate price generator, disclosed as a real
simplification) to each synthetic path and to the real last-1611-day
history, comparing Sharpe/MDD edge over buy-and-hold.

**Result**: the real history's `edge_sharpe` (+0.275) falls almost
exactly at the median (44.7th percentile) of the 300-path synthetic
distribution (mean +0.323, [p5,p95]=[+0.031,+0.669]) — the rule's edge on
the actual realized history is statistically typical of what the
mechanism produces on any similar alternate history, not a lucky fit.
The real history's `edge_mdd` (+5.90pp) sits at only the 10th percentile
of the synthetic distribution (mean +16.55pp) — the real MDD improvement
actually *understates* the mechanism's typical benefit, the opposite of
what an overfitting concern would predict. 97.7% of synthetic paths show
the rule beating buy-and-hold on Sharpe, 99.0% on MDD.

**Limitations disclosed**: only the simplified price-only rule proxy was
tested, not the real chip/derivative-gated production rule; the CHMM was
fit on the full history *including* 2020-2026 (not a strict held-out
split) — a stricter version would fit on pre-2020 data only.

**Conclusion**: within these limits, a genuinely reassuring result — no
evidence Group A+'s core price-technical switch logic is overfit to the
single realized history. Doesn't promote anything (production has richer
gates not tested here) but is a useful robustness cross-check, distinct
in kind from the session's many closed_negative new-signal tests.

**Files**: `scripts/evaluate/build_chmm_synthetic_stress_test_2606_23492.py`.
Registry: `2606_23492_chmm_synthetic_stress_test_switch_rule_overfitting`.
Memory: `project_2606_23492_chmm_synthetic_stress_test_20260823.md`.

### Next steps if this line is pursued further

(a) Refit the Angle-B VaR construction directly on 00631L's own return
series with a richer state count or leverage/compounding-aware emission
structure, rather than assuming the 0050 result transfers. (b) Redo the
Angle-C stress test with the CHMM fit strictly on pre-2020 data only, for
a true held-out overfitting check. (c) Extend the Angle-C synthetic-path
infrastructure to stress-test other Group A+ parameter choices, not just
`switch_risk_ma80_dd11`.

---

## Cross-cutting summary

Across this segment (TXO deeper-OTM + all three 2606.23492 angles),
**nothing is ready for production adoption**. Two `shadow_track` results
(TXO deeper OTM, CHMM regime-conditional VaR on 0050) are real but too
narrow to clear the promotion bar; one `closed_negative` (CHMM
regime-detection trigger); one `informative_no_action` (CHMM synthetic
stress test — reassuring but not itself actionable). No production code
was touched in any of the four pieces of work.
