# 2607.23068 (Bongiorno, Manolakis & Mantegna) — Neural Network-Driven Volatility Drag Mitigation under Aggressive Leverage — Group A+ Review

**Status: clean close, no code written.**

## What the paper does

Compresses an earlier end-to-end neural network for global minimum-variance
(GMV) portfolio optimization ([4], Bongiorno et al. 2025, arXiv:2507.01918)
from ~40,000 learnable parameters down to ~2,175, decoupling model
complexity from both look-back window length and asset-universe size:

- **Lag-transformation module**: replaces a 2,400-parameter layer with a
  5-scalar hyperbolic weighted moving average (`α_t = θ1·t^-θ2`) combined
  with a saturating-exponential clipping threshold (`β_t = θ3 - θ4·e^-θ5·t`).
- **Correlation-cleaning module**: a bidirectional GRU (16 units/direction,
  replacing the original BiLSTM) performs learned, rotation-invariant
  eigenvalue shrinkage on the sample correlation matrix — an implicit,
  end-to-end-trained alternative to classical Non-Linear Shrinkage (NLS).
- **Marginal-volatility module**: small per-asset MLP converting empirical
  std to an inverse volatility scale, no cross-asset information.
- The three combine into an approximate inverse covariance matrix; GMV
  weights are the closed-form `Σ⁻¹1/(1ᵀΣ⁻¹1)`, solved long-only via QP.
- Trained by minimizing realized out-of-sample portfolio variance directly
  (no expected-return term), on the top n=1,000 US common
  equities/ADRs by market cap, n∈[50,350] sampled per training batch,
  Δt_in∈[250,1200] days, 24 yearly retrained models (2000-2024).
- Validated in a high-fidelity Interactive-Brokers-account simulator with
  realistic commissions/fees, tiered margin interest, and worst-case
  intraday margin-call liquidation (maintenance margin floor at
  `max(low, 0.85·min(open,close))`, forced deleveraging back to 27% ratio).
- Headline result: across a ~400-point leverage grid (ℓ∈[0.01,3.99]), the
  compact NN beats EW/MCW/ERB/ERC/HRP/MLE/QIS/Average-Oracle on realized
  volatility, incremental efficiency ratio (`b/a`, mean-return slope over
  volatility slope, >1 only for this model), first-liquidation leverage
  threshold (2.77 vs 2.61-2.73 for rivals), and at ℓ=3: Sharpe 1.12 vs 0.99
  (AO, next best), MDD −0.77 vs −0.83. Model Confidence Set test (5%,
  stationary block bootstrap, 100k resamples) confirms the NN is the sole
  member of the superior set at ℓ=3 among all rivals except the original,
  larger [4] network (indistinguishable from it).

## Why it doesn't transfer to Group A+

**The core architecture solves a problem Group A+ doesn't have.** The
BiGRU eigencleaning module exists to denoise a high-dimensional sample
correlation matrix (n up to 350, aspect ratio q=n/Δt_in comparable to 1)
against Marchenko-Pastur-type estimation noise. Checked
`config/group_a_plus_watchlist.json`: Group A+'s actual tradable universe
is **5 symbols** (0050, 00631L, 00632R, 00679B, 2330) plus cash. At n=5,
the sample covariance matrix has no meaningful high-dimensional noise
problem to clean — same category of mismatch as
`2310_02084_ROBUST_LETF_GROWTH_RATE_GROUPA_PLUS_REVIEW_20260809.md`
(decision variable/infrastructure the paper assumes doesn't exist here).

**The portfolio-construction paradigm is different in kind, not degree.**
The paper solves a continuous QP for GMV weights over a large, rotating
cross-section, retrained yearly on 25 years of US equity history. Group
A+ allocates fixed nominal weights (e.g. 60/20/20 in golden1_0531) across
a small, static instrument set via discrete regime-switching rules
(`switch_ma*`, market-state classifiers). There's no natural grafting
point — adopting this architecture would mean replacing Group A+'s entire
allocation paradigm, not adding a module to it.

**The volatility-drag/leverage framing is the same well-trodden ground
already closed twice.** Eq. 2-3 (`drag ≈ ½ℓ²σ²` under compounding) is the
identical LETF decay identity already reviewed via `2301_03186`
(quadratic LETF bound, crosschecked and rejected as pseudo-replication
2026-08-10) and `2310_02084` (robust LETF growth rate, closed
2026-08-09 — no β decision variable exists in this project). This paper's
version is about portfolio-level leverage reconstructed via margin
borrowing on a rebalanced weight vector w, not 00631L's own
issuer-embedded daily-reset 2x — a related but distinct leverage
mechanism, and not a new formula.

## One point worth recording (not a code change)

Section 2's framing treats "rebalanced back to a fixed weight vector w and
target leverage ℓ at each day's close" as the *precondition* for the
drag formula to hold at its designed rate — i.e., daily rebalance-to-target
is baked in as the standard assumption for leverage-aware portfolios in
this literature. This is an independent, external data point (US
large-cap GMV context, unrelated codebase) landing on the same conclusion
just reached empirically in
`GROUP_A_PLUS_20260811_ALPHAZEROBETA_FACTOR_ATTRIBUTION_AND_CRASH_PROTECTION_HANDOFF.md`
§13: `_simulate_regime_curve`'s lack of any periodic rebalance (only
regime-change-triggered) let golden1_0531's realized weights drift until
MKT beta reached 1.337 against a nominal ~1.0, and crash-window
performance flipped from 4/12 to 10/12 hit rate once a monthly
(`rebalance_every_days=21`) rebalance was applied. Not a new finding —
corroboration of one already acted on, opt-in, non-default (see that
handoff's §14 for why the default wasn't changed).

No new checklist item, shadow mechanism, or code opened from this paper.

## Verdict

Clean close, no code written, no shadow line opened. Architecture/universe-
size mismatch (same category as 2310.02084, 2301.03186, DeepPocket,
low-risk DQN) — not a rejected-on-the-merits finding, the paper's own
results look sound for its stated problem (large-N US equity GMV under
margin leverage), that problem just isn't Group A+'s.
