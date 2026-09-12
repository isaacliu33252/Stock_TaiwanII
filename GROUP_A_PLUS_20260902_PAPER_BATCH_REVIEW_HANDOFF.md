# GroupA+ Handoff: 2026-09-02 Paper Batch Review (4 papers, all closed_negative)

- Recorded: 2026-09-02
- Scope: independent desk review of four arXiv papers downloaded 2026-09-01
  13:01 (`2605.28853`, `2605.02326`, `2608.04987`, `2608.13748`), plus a
  quick re-confirmation that `2608.26115` was already fully reviewed
  2026-09-01.
- Policy: no strategy change, no target-weight change, no order created, no
  daily pipeline or production code modified.

## Session flow

1. User asked whether `2608.26115` had already been analyzed. Checked
   memory (`project_2608_26115_option_crash_risk_desk_review_20260901.md`) --
   already closed_negative from the "5 return-improvement candidate papers"
   review on 2026-09-01. No new work needed; answered from existing record.
2. User provided `2605.28853.pdf` for review.
3. After the verdict, user said "繼續" (continue). Checked the Downloads
   folder for other PDFs with the same download timestamp
   (`2026-09-01 13:01`, matching `2605.28853` and the already-reviewed
   `2608.20179`) that had not yet been reviewed anywhere in the repo or
   memory. Found three: `2605.02326`, `2608.04987`, `2608.13748`. Reviewed
   all three in sequence within the same turn (all straightforward
   desk-review closures, no need for user confirmation between each).

## 1. `2605.28853` -- Financially Guided Deep Portfolio Optimization

Fernandes & Desell (RIT). End-to-end differentiable-loss training
(Sharpe/Omega/CVaR/Risk-Parity surrogates, softplus + Rockafellar-Uryasev)
for a neural network that outputs portfolio weights directly, tested on 50
S&P 500 constituents, 2007-2023, quarterly rebalance. Best combination
(AttentionLSTM + Omega-CVaR-RiskParity loss): OOS (2022-2023) Sharpe 0.29 vs
S&P 500's -0.02.

**Verdict: closed_negative.**

- Risk Parity regularization requires genuinely diversifiable cross-asset
  structure (N=50 weakly-correlated large-caps). GroupA+'s core sleeve
  (`0050.TW`/`00631L.TW`/`00632R.TW`) is the same index family's
  leveraged/inverse instruments -- near-perfectly (anti-)correlated by
  construction, so risk parity degenerates (forces near-all-cash or
  long/short-offsetting solutions) rather than producing real
  diversification.
- The edge is largely "didn't lose as much in the 2022 bear year" (CVaR
  nearly tied with S&P 500, Omega barely above 1.0) -- overlaps with what
  GroupA+'s existing golden1/defensive regime switch already targets, not
  an additive alpha source.
- 8 of 14 model-loss combinations tested in the paper underperformed the
  benchmarks (some with negative Sharpe), showing high architecture
  sensitivity -- higher overfitting risk on GroupA+'s smaller, sparser
  feature set.
- One theoretically transferable but not-worth-pursuing idea: the
  differentiable CVaR/Omega loss formulas themselves (as a training
  methodology, backprop instead of RL) are not inherently tied to N=50.
  GroupA+ already achieves similar ends via PPO reward optimization plus an
  independent CVaR tail-cost overlay (`2606.26625` line); swapping the
  entire training paradigm carries architecture-level risk far exceeding any
  plausible marginal benefit.

Memory: `project_2605_28853_financially_guided_deep_portfolio_desk_review_20260902.md`

## 2. `2605.02326` -- Large-Scale Asset Selection via Metric Dependence (MDS)

Chen, He & Chen. Screens a large candidate universe (tested: 2938 Chinese
A-share stocks, 2023-07 to 2025-12) down to a manageable subset using a
Fréchet-variation dependence score over point-curve objects that combine
daily return with an intraday risk-state curve, then applies standard
mean-variance/min-variance allocation to the screened subset.

**Verdict: closed_negative** (two independent, either sufficient):

1. Its entire purpose is selecting from a large candidate pool (thousands of
   stocks) -- GroupA+'s universe is a fixed 4-5 ETFs; there is no selection
   problem to solve. Same pattern already confirmed closed multiple times
   (`2608.05755`, `2608.09641`, `2512.11273` -- "the real bottleneck is a
   too-small asset pool, not screening/optimizer efficiency").
2. Requires intraday high-frequency data to build the risk-state curve.
   GroupA+'s data is Taiwan EOD daily bars only -- no intraday/tick data
   available (consistent with the data gap already established across the
   options-liquidity paper line).

Memory: `project_2605_02326_metric_dependence_screening_desk_review_20260902.md`

## 3. `2608.04987` -- Portfolio Allocation under Heterogeneous Scales and Multifractality (mean-MFCCA)

Kakinaka & Umeno. Replaces the covariance matrix in mean-variance
optimization with a sign-preserving Multifractal Cross-Correlation Analysis
(MFCCA) risk criterion, indexed by time scale `s` and fluctuation order `q`.
Empirical test uses only **4 assets** -- Nikkei index, S&P 500 index, WTI
crude futures, gold (XAU/USD), 2011-2023 daily data -- which is structurally
much closer to GroupA+'s scale than the other three papers reviewed this
session, so this one received a full read of the empirical section (not an
abstract-only close).

**Verdict: closed_negative**, for two independent reasons:

1. The method's value depends on the assets having genuinely heterogeneous,
   scale-varying dependence (the paper's own Figure 4 shows DCCA
   coefficients shifting systematically across scale `s` and order `q`
   between Nikkei/S&P500/WTI/Gold -- four different economic drivers).
   GroupA+'s core sleeve is mechanically (anti-)correlated at every scale by
   construction (`00631L.TW` ≈ 2× `0050.TW`, `00632R.TW` ≈ -1× `0050.TW`) --
   there is no scale-dependent structure to exploit. `00679B.TWO` is the one
   genuinely heterogeneous asset, already handled by the existing switch
   policy, leaving too few non-trivial asset pairs for this method's premise
   to apply.
2. Even under its own best-case setup (four genuinely diverse asset
   classes), the paper explicitly states its out-of-sample improvement over
   the plain mean-variance benchmark "remain[s] within the resolution of the
   out-of-sample period... the sample may be too short to establish uniform
   statistical dominance." The only *statistically* clean result is MMFC's
   drawdown advantage over the alternative (absolute-value) MFDCCA
   construction, not over conventional mean-variance.

Memory: `project_2608_04987_mfcca_multifractal_portfolio_desk_review_20260902.md`

## 4. `2608.13748` -- Multi-period VaR-Constrained Portfolio Optimization via DC Programming

Nguyen. Pure numerical-optimization contribution: a projected inertial
Boosted Difference-of-Convex Algorithm (iBDCA) for a nonconvex multi-period
finite-scenario VaR-constrained portfolio problem, with full convergence
proofs. Numerical experiments use n=30 stocks (NASDAQ / S&P 500 samples),
S=500 bootstrap scenario paths, T=10 periods, comparing solver quality/speed
against classical DCA and BDCA.

**Verdict: closed_negative**, for two independent reasons:

1. The solver-efficiency contribution only matters at the scale tested
   (n=30, 500 scenario paths). At GroupA+'s n=4-5 scale, any off-the-shelf
   convex/DC solver is already fast enough -- the computational bottleneck
   this paper solves does not exist for GroupA+.
2. More fundamentally, GroupA+ does not currently allocate via a formal
   per-period optimization solve at all (it uses PPO/RL plus a rule-based
   regime switch). Adopting this paper's contribution would require
   re-architecting GroupA+ around solving a formal multi-period VaR-
   constrained optimization each rebalance -- and that specific path (a
   real-time CVaR optimizer) was already investigated and falsified in
   `2606.26625`'s in-sample LP feasibility study: the "optimizer wins 5/5
   stress windows" result there turned out to be a textbook in-sample
   overfitting artifact (the LP solution exploited look-ahead knowledge to
   simultaneously overweight `00631L.TW` long-leverage and `00632R.TW`
   inverse-leverage as a hedge, something the mutually-exclusive production
   switch logic can never do). A better *solver* does not address that
   already-falsified premise.

Memory: `project_2608_13748_dc_programming_var_solver_desk_review_20260902.md`

## Addendum: re-confirmation, not re-review

Immediately after this handoff was first written, the user asked again
whether `2605.02326.pdf` had been analyzed and whether it had anything worth
importing into GroupA+'s latest strategy. This was **not** a new review --
the answer was retrieved from the record above (and its memory file) and
reported back verbatim (closed_negative, same two reasons: no
large-candidate-pool selection problem exists in GroupA+'s fixed 4-5 asset
universe, and no intraday data is available). No new analysis, no new file
changes, no new memory entry beyond this note. Recorded here only so the
session timeline is complete if this handoff is read later.

A second re-confirmation followed for `2608.04987.pdf` (same pattern: user
re-asked whether it had been analyzed and had anything to import; answered
from the record above, no new analysis, no new file changes).

## Downloads folder status

As of this session, every arXiv PDF in `~/Downloads` has a corresponding
review record (memory file and/or existing repo doc). No unreviewed papers
remain pending.

## Validation

Read-only desk review only (PDF text extraction via `pypdf`, cross-checks
against `group_a_plus/research_semantic_registry.json` and existing memory).
No backtests run, no code changed, no tests run, no production files
touched, no commit made.
