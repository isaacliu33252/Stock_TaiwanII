# 2604.09060v2 (Chakraborty & Singh) — AEGIS: Momentum-Gated Hierarchical Optimisation Framework — Group A+ Handoff

**Status: clean close, no code written, no shadow line opened.**

Source file reviewed: `C:\Users\isaac\Downloads\2604.09060v2.pdf` (arXiv:2604.09060v2 [cs.CE], 18 May 2026, 18 pages). Text extracted locally via `pypdf` (no poppler-utils installed in this environment; `pdftoppm` unavailable) to
`/tmp/claude-1000/.../scratchpad/2604.09060v2.txt`.

## What the paper does

Proposes **AEGIS** (Adaptive Equity Generation and Immunisation System), a
three-layer momentum-gated portfolio construction pipeline for U.S. equities,
backtested 2006-2025 (20-year walk-forward):

1. **Signal Generation Module** — investment universe = union of S&P 500,
   S&P MidCap 400, S&P SmallCap 600, NASDAQ-100, and DJIA constituents
   (thousands of names, reconstructed with survivorship-bias correction via
   manual dead-stock injection). For each GICS sector, picks the single
   highest-12-month-cumulative-return leader, then scores each leader by
   **VAM** (Volatility-Adjusted Momentum, `S_i = R_i / σ_i` — a
   skip-month cumulative log-return divided by realized annualized
   volatility, i.e. a localized Sharpe ratio). Top-3 VAM leaders become the
   **anchor triad**.
2. **Immunisation Layer** — fills the remaining 47 slots (target basket size
   N=50) via a **minimax correlation** greedy algorithm: candidates must
   first pass a positive-momentum gate (`R_i > 0`), then the algorithm
   iteratively adds whichever remaining candidate has the *lowest maximum
   pairwise correlation* against all current basket members
   (`min_c max_{b∈B} |corr(r_c, r_b)|`), repeated until the basket is full.
   This is a combinatorial diversification search over a large low-
   correlation candidate pool, not a covariance-shrinkage or risk-parity
   step.
3. **Allocation Engine** — SLSQP (scipy) solves a non-convex optimization
   maximizing the Sortino ratio (`(w^T μ - R_f) / DD_ann(w)`, downside
   deviation as the LPM-2 lower partial moment vs. a 4% annual hurdle),
   monthly rolling reoptimization on a 3-month training lookback, subject to
   fully-invested / long-only / 5%-per-asset-cap constraints. 10bps
   proportional friction per unit turnover.

Headline results (Table III): CAGR 15.41%, annualized vol 16.44%, MaxDD
-28.89%, Sharpe 0.72, average Sortino 6.47 (outlier-adjusted 1.72 excluding
2013/2017), 18/20 profitable years, monthly win rate 68.8%. Beats S&P 500
(8.88% CAGR) and DJIA (7.79%) outright; matches NASDAQ-100's terminal wealth
(15.41% vs 15.44% CAGR) with far shallower drawdowns (2008: -20.94% vs
NASDAQ -41.73%; 2022: -5.10% vs NASDAQ -32.58%). Head-to-head vs standard
cross-sectional momentum (CSM) and stock/bond risk parity baselines
(Table V): AEGIS beats CSM in 2008 (-20.94% vs -42.58%) and beats risk
parity in 2022 (-5.10% vs -26.72%) — i.e. it survives both a deflationary
liquidity shock and an inflationary rate-hike shock, which the two
baselines each fail one of. A parameter robustness sweep (Table VI, N=25/
50/75 basket sizes × 3/6/12-month allocation lookback) shows 47-diversifier/
3-month is the empirical optimum; 3-month lookback is deliberately chosen
over the higher-CAGR 12-month lookback (18.39% CAGR but -37.94% MaxDD,
23.61% vol) to suppress variance instead of maximizing raw return.

## Why it doesn't transfer to Group A+

**The core mechanism (minimax correlation basket construction) needs a
large, genuinely low-correlation candidate pool — Group A+ doesn't have
one.** Checked `config/group_a_plus_watchlist.json`: the tradable universe
is **5 symbols** — `0050.TW`, `00631L.TW`, `00632R.TW`, `00679B.TWO`,
`2330.TW`. Three of the five (`0050`, `00631L`, `2330`) are structurally the
same underlying exposure (TWII / TSMC-heavy weighted index and its 2x
leveraged / issuer-derivative forms); their pairwise correlations sit near
1, not spread across a diversifiable spectrum. AEGIS's diversification edge
comes from having *thousands* of sector-spanning candidates to greedily pick
the least-correlated 47 from; at n=5 with near-collinear names there is no
combinatorial search to run and no diversification gain available. Same
category of universe-size mismatch previously closed for
`2607_23068_COMPACT_GMV_NEURAL_NETWORK_LEVERAGE_GROUPA_PLUS_REVIEW_20260812.md`
(BiGRU eigenvalue-cleaning module needs n up to 350 with a meaningful
Marchenko-Pastur noise floor; Group A+'s n=5 has none).

**The portfolio-construction paradigm is different in kind.** AEGIS is a
cross-sectional stock-picking engine choosing *which* equities to hold out
of a large rotating universe. Group A+'s `golden1_0531` / `a2118` operate as
discrete regime-switching rules over a fixed, small instrument set (e.g.
0050/00631L/00632R weight tilts via `switch_ma*`, market-state
classifiers) — there is no "candidate pool" to run a minimax-correlation
search over in the first place. Grafting this module in would mean
replacing the allocation paradigm, not adding a component to it.

**Individually-checked sub-components, none add new value here:**

- **VAM signal** (`cumret / realized_vol`, a localized Sharpe ratio) — this
  metric class (`sortino`, `sharpe`) is already used throughout
  `group_a_plus/governance/compare.py`, `governance/significance.py`,
  `governance/catalog.py`, and multiple runners/integrations (grepped
  `group_a_plus/`, `environments/`, `FinRL/` for `sharpe|sortino`, dozens of
  hits). Not a new signal family.
- **Positive-momentum gate** (`R_i > 0` pre-filter before further
  processing) — structurally the same "sign of trailing return/MA" logic
  already embedded in `switch_ma*` and golden1_0531's regime rules.
- **SLSQP + Sortino-maximizing allocation, 3-month lookback beating
  12-month** — this is a parameter-sweep conclusion specific to optimizing
  weights across a 50-asset combinatorial space; on a 2-3-instrument
  allocation problem, a numerical solver over that few free variables adds
  no meaningful degrees of freedom over the existing discrete rules.
- **Dead-stock survivorship-bias injection** — a backtest-data-hygiene
  technique for a universe with real delisting/bankruptcy risk (individual
  U.S. equities). Group A+'s core instruments (`0050`, `00631L`, `2330`)
  are a continuously-tracked broad-market ETF, its issuer-maintained 2x
  leveraged derivative, and Taiwan's largest, most liquid blue-chip — none
  carry realistic delisting risk over the backtest horizons in use. Not
  applicable.

## What was and wasn't done this session

Done:
- Extracted and read the full 18-page paper text (methodology, all tables,
  results, robustness sweep, conclusion, references).
- Checked `config/group_a_plus_watchlist.json` to confirm actual tradable
  universe size (5 symbols).
- Grepped `group_a_plus/`, `environments/`, `FinRL/` for existing
  sharpe/sortino usage to confirm VAM/Sortino-style metrics aren't a new
  addition.
- Saved memory entry
  `project_2604_09060_aegis_universe_mismatch_closed_20260813` and updated
  `MEMORY.md` index.

Not done (and not warranted given the universe-mismatch finding):
- No backtest, shadow module, or evaluation script was written.
- No attempt to graft VAM signal or Sortino-SLSQP allocation onto
  `golden1_0531` / `a2118` — the mismatch is structural (n=5 near-collinear
  instruments), not a parameter or implementation gap that more engineering
  would fix.

## Do Not Do

- Do not implement a minimax-correlation candidate-selection module for
  Group A+ — there is no candidate pool of sufficient size/diversity for it
  to operate on.
- Do not treat AEGIS's 15.41% CAGR / -28.89% MaxDD backtest as evidence
  transferable to Group A+ — it was produced on a fundamentally different
  asset universe (thousands of diversifiable U.S. equities) under a
  fundamentally different construction paradigm (cross-sectional stock
  selection vs. fixed-instrument regime switching).
- Do not modify `golden1_0531`.
- Do not modify `a2118` / latest-strategy weights from this review.

## Next Step

Only worth revisiting if the Group A+ tradable universe is deliberately
expanded to include a genuinely larger, lower-correlation candidate set
(e.g. multiple uncorrelated sector ETFs or a broader Taiwan-stock basket
beyond the current 5-symbol watchlist) — at that point the VAM signal +
minimax-correlation construction pattern would become mechanically
applicable and worth a real shadow backtest. Until then, leave closed.

## Verdict

Clean close, no code written, no shadow line opened. Universe-size /
paradigm mismatch (same category as `2310_02084`, `2301_03186`,
`2607_23068`, DeepPocket/low-risk-DQN) — not a rejected-on-the-merits
finding; the paper's own U.S.-equity results look methodologically sound
(proper walk-forward, survivorship-bias correction, parameter robustness
sweep, crisis-regime stress comparison against CSM and risk-parity
baselines) for its stated problem. That problem — diversified cross-
sectional momentum stock-picking over a large universe — just isn't Group
A+'s problem.
