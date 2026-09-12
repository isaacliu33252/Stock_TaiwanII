# 2310.02084 (Leung, Park & Yeo) — Robust Long-Term Growth Rate for LETFs — Group A+ Review

**Status: clean close, no code written.**

## What the paper does

Derives, via the comparison principle for SDEs and a martingale extraction
method, closed-form expressions for the **worst-case long-term growth rate**
of an investor's expected utility from holding a leveraged ETF (LETF) at a
chosen constant leverage ratio β, when the reference asset's drift/
volatility/correlation/short-rate parameters are only known to lie within
an uncertainty interval, not at a point estimate. Covers GBM, CIR, 3/2, and
Heston/3-2 stochastic-volatility reference models, plus Vasicek and inverse
GARCH stochastic short-rate extensions. Also derives the **optimal leverage
ratio β\*** that maximizes this worst-case growth rate under each model,
via numerical search when no closed form exists (Heston, Vasicek, inverse
GARCH cases). Core qualitative finding, consistent across every model:
don't hold the LETF (β\* = 0) unless the worst-case expected return of the
reference asset clearly exceeds (long) or falls clearly below (short) the
risk-free rate — volatility-decay-adjusted, not a naive point estimate.

## Why it doesn't transfer to Group A+

**The paper's decision variable doesn't exist in this project.** β is a
continuously-chosen leverage ratio the investor picks when *constructing*
a synthetic LETF position (the paper's numerical examples find optimal β
values like 1.25, 1.7). Group A+ doesn't construct synthetic leverage — it
allocates weight among a small fixed set of pre-existing retail ETF
products (00631L at its issuer-fixed 2x, 00632R at its issuer-fixed -1x,
0050 unleveraged) via a discrete regime table. There is no β to solve for;
the leverage ratios are fixed by the products themselves, and the actual
decision variable is regime-conditional portfolio weight, not leverage
choice.

**No infrastructure exists to calibrate the required uncertainty sets.**
Reproducing even one of the paper's closed-form results requires
calibrated drift/volatility/correlation/short-rate uncertainty *intervals*
for GBM/CIR/Heston/3-2 model parameters (e.g. `[µ, µ̄]`, `[ρ, ρ̄]`,
`[σ, σ̄]`). Group A+'s market-state features are entirely empirical and
regime-discrete (chip flow, drawdown, MA gap, tail-risk sub-indicator
counts) — there is no existing pipeline that fits or bounds continuous-time
SDE parameters against Taiwan market data, and building one from scratch
just to exercise this paper's formulas would be new infrastructure
disproportionate to what the paper would deliver (a leverage-ratio
recommendation for a choice this project doesn't make).

**The underlying "when is holding an LETF worth the volatility drag" question
this project already answers empirically, in production, from a different
paper.** `GROUP_A_PLUS_00631L_LEVERAGED_COMPOUNDING_REGIME_HANDOFF_20260713.md`
(arXiv:2504.20116, "Compounding Effects in Leveraged ETFs: Beyond the
Volatility Drag Paradigm") built a no-lookahead trend/mean-reversion
regime classifier for exactly this question — and unlike this review, that
mechanism is now **live and enforcing** in
`group_a_plus/operations/execution_guard.py::apply_compounding_regime_pre_trade_guard()`
(caps new 00631L buy-side additions when the regime reads
MEAN_REVERTING). That solution is empirical/regime-classification-based
and fits this project's existing data and architecture; 2310.02084's
closed-form parametric-uncertainty approach solves a related but distinct
problem (optimal leverage *choice* under model uncertainty, not
trend-vs-mean-reversion timing of a *fixed*-leverage product) and would
require an entirely separate, currently-nonexistent calibration
infrastructure to even attempt.

## Any piece worth extracting?

Checked against the same standard as every other paper reviewed this
session (is there one narrow, cheap, applicable idea even if the main
mechanism doesn't transfer — e.g. how the 2605.20636v2 validation checklist
was extracted from an otherwise-rejected paper). The paper's general
epistemic stance — evaluate a leverage/exposure decision against the
*worst case* within a plausible parameter range, not a point estimate — is
already independently present in this project's signal validation
checklist item 7 (worst-case-perturbation robustness check for hard
threshold gates on composite scores, adopted 2026-07-26,
`GROUP_A_PLUS_SIGNAL_VALIDATION_CHECKLIST_20260723.md`). Nothing new to
extract from this angle either.

## Verdict

Clean close, no code written, no shadow line opened. Architecture/data
mismatch, not a rejected-on-the-merits finding — same category as the
2105.08664 (DeepPocket) and 1909.03278 (low-risk DQN) reviews earlier the
same day.
