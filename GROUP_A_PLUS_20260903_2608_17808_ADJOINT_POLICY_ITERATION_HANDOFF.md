# GroupA+ Handoff: 2026-09-03 -- 2608.17808 Adjoint Policy Iteration Review + β=1/2 Half-Step Damping Backtest

- Recorded: 2026-09-03
- Scope: (1) full independent desk review of `2608.17808` (continuous-time
  PMP-adjoint policy iteration for constrained portfolio choice), and (2) a
  follow-up empirical backtest of the one execution-layer idea from that
  paper that looked concretely transferable -- a β=1/2 "half-step" damped
  regime transition -- run against the production `a2118` engine.
- Policy: no strategy change, no target-weight change, no order created, no
  daily pipeline or production code modified. The half-step variant was
  tested via `unittest.mock.patch` in a scratch script, never touching
  `group_a_plus/runners/a2118.py` or any other production file.

## Session flow

1. User provided
   `2608.17808_self_consistent_adjoint_policy_iteration_constrained_dynamic_portfolio_choice.pdf`
   and asked whether it had ideas worth importing into GroupA+'s latest
   strategy. Read the full 38-page PDF (main text + all appendices), not
   just the abstract.
2. Checked memory (`MEMORY.md` full-text search, per
   `feedback_verify_every_paper_independently` -- registry-check habit is
   deprecated per `feedback_research_semantic_registry_check_before_new_research`,
   not required) for prior reviews of adjoint/Pontryagin/HJB portfolio
   papers. Found the closest precedents were `2607.00475` (end-to-end policy
   framework, closed_negative) and `2605.28853` (differentiable deep
   portfolio, closed_negative) -- both closed for "needs cross-asset
   breadth GroupA+ doesn't have." This paper's disqualifying issue turned
   out to be different (see below), so it was reviewed fully rather than
   pattern-matched to the same reasoning.
3. Delivered a closed_negative desk-review verdict (Chinese, per
   `feedback_language`). Wrote
   `project_2608_17808_adjoint_policy_iteration_desk_review_20260903.md`
   and an index line in `MEMORY.md`.
4. User asked a terse follow-up: "β=1/2 half-step cap 回測?" -- i.e., don't
   just desk-review the damped-update idea, actually backtest it. Per
   `feedback_verify_every_paper_independently`, treated this as its own
   independent verification task rather than deferring to the paper's
   overall closed_negative verdict.
5. Investigated GroupA+'s actual execution code
   (`backtest_group_a_plus_defensive_basket.py::_simulate_costed_curve`,
   used by every current runner including production `a2118`) to confirm
   it does an **instantaneous full rebalance to the new regime's target
   weights on the same day the regime label changes**, charging
   commission+slippage+tax on the full turnover.
6. Wrote a scratch-only script
   (`/tmp/.../scratchpad/halfstep_damping_backtest.py`, not committed) that:
   - Defines `_simulate_costed_curve_halfstep(...)`: on a regime change, sets
     a *pending target* weight vector; each subsequent day, moves the
     portfolio `beta` of the remaining gap toward that target
     (`w_{t+1} = w_t + beta*(target - w_t)`), paying transaction cost on
     only that day's partial trade, until within a 0.3% L1 tolerance (then
     stops trading).
   - Calls `group_a_plus.runners.a2118.run_a2118(...)` with **identical**
     production inputs (same switch rule, same NCF late-bull overlay when
     enabled, same cost parameters from `report/group_a_plus/latest/strategy.json`'s
     `runner_params`), monkeypatching only `_simulate_costed_curve` via
     `unittest.mock.patch.object` for the "damped" run, so only the
     execution-smoothing mechanism differs between baseline and variant.
7. Ran three windows; two were structurally distinct, the third collapsed
   into the second because `00679B.TWO` (the bond ETF) only has price data
   from 2017-01-11 onward, so requesting an earlier start (2015-01-01,
   2009-06-01) both get trimmed to the same 2017-01-11 first date (a live
   instance of the "multi-year coverage trap" --
   `feedback_check_data_coverage_before_multiyear_framing` -- caught
   automatically because the script reports the actual trimmed window, not
   the requested one).
8. Appended the backtest result to the same memory file (extending, not
   replacing, the earlier desk-review verdict) and updated its `MEMORY.md`
   index line.

## Part 1: Desk review of `2608.17808`

Huh, Kim & Jeong (Sungkyunkwan University et al.), "Self-Consistent Adjoint
Policy Iteration for Constrained Dynamic Portfolio Choice" (2026-08-27,
math.OC). Proposes **I-PGDPO**: an algorithm using Pontryagin
adjoint processes (first/second-order BSDEs) plus open-loop
backprop-through-time (OL-BPTT) as an alternative to deep RL (PPO/actor-critic)
for continuous-time, multi-factor, convex-constrained (no-short, box) CRRA
portfolio choice. The core mechanism is *self-consistent re-evaluation*:
each outer iteration re-simulates and re-estimates the adjoint field **under
the currently-deployed policy**, rather than computing it once (one-shot)
from the initial policy.

Key results, all on **synthetic/simulated data**, not real markets:

- **Merton model (i.i.d. returns) is a designed negative control**: the
  policy-improvement operator is provably policy-independent here, so
  iterative re-evaluation adds zero value -- one-shot recovery is already
  optimal.
- **One-factor OU predictable-return model**: current-policy re-evaluation
  reduces policy RMSE from 2.67e-3 (one-shot) to 6.58e-4, vs 2.68e-3 for a
  matched-budget pooled initial-policy refinement. The operator here is
  genuinely policy-dependent, so iteration helps.
- **Three-factor, fifty-asset synthetic benchmark**: current-policy
  re-evaluation beats matched-cost pooled refinement in on-policy and broad
  evaluation laws across all three seeds; pooled refinement wins only under
  an enlarged tail-only law.
- Full convergence theory (adjoint-HJB Hamiltonian-gradient consistency,
  occupation-measure directional/norm-relative audits; 180 theorem-matched
  path banks all pass the 0.75 half-step sufficiency threshold with maximum
  95% upper endpoints of 0.066-0.074).

**Verdict: closed_negative**, for reasons distinct from the usual
"needs cross-asset breadth" pattern:

1. The entire method requires a **known parametric continuous-time SDE
   factor model** -- factors follow an Ornstein-Uhlenbeck process with known
   mean-reversion/volatility matrices, excess returns are affine in the
   factors, the return covariance and factor cross-covariance are known
   constant matrices, and CRRA utility has a fixed known risk-aversion γ.
   GroupA+'s signal generation is entirely model-free / empirical
   (technical indicators, institutional-flow features, NCF ensemble
   black-box features feeding PPO) -- there is no parametric diffusion
   model of Taiwan ETF returns, and building one would be an independent
   modeling-paradigm shift, not a feature addition.
2. The paper's headline insight -- "iterate under the deployed policy only
   when the improvement operator is genuinely policy-dependent; i.i.d.
   returns need no iteration" -- is conceptually already subsumed by PPO's
   own on-policy training loop (every epoch already re-evaluates under the
   currently-deployed policy). Adopting I-PGDPO would replace *how* the
   policy is computed (adjoint+QP vs neural net), not add a capability
   GroupA+ lacks.
3. The strongest empirical benchmark (three-factor, fifty-asset) is
   **synthetic Gaussian-OU simulated data**, not real market data (unlike
   e.g. `2605.28853`, which at least used real S&P 500 constituents) -- no
   evidence the demonstrated advantage survives contact with actual Taiwan
   ETF return dynamics.
4. GroupA+'s core sleeve is only 4-5 near-perfectly-(anti-)correlated
   leveraged ETFs. The paper's computational selling point (low-dimensional
   factor field + explicit QP replacing a high-dimensional neural policy)
   solves a "many assets, few factors" scaling problem GroupA+ does not
   have at this scale.

Memory: `project_2608_17808_adjoint_policy_iteration_desk_review_20260903.md`

## Part 2: β=1/2 half-step damping -- empirical backtest

The one piece of the paper that maps onto something concretely testable
without building a new SDE modeling stack is Proposition 3.8's damped
update `u_β = (1-β)u + β·T(u)`, reinterpreted at the execution layer as:
*don't jump straight to the new regime's target weights in one day --
spread the transition across days.* This is a different, more mundane claim
than the paper's (a conservative-interpolation optimization certificate in
continuous time) -- it's really "gradual rebalancing reduces whipsaw cost,"
a standard execution-smoothing heuristic, tested here on GroupA+'s own
golden1↔defensive switch.

### Method

- Baseline: production `_simulate_costed_curve` (regime change → full
  rebalance same day, costed by `_trade_cost`: commission 0.1425% +
  slippage 0.05% (+ 0.1% equity-ETF sell tax on the sell leg, 0% on
  `00679B.TWO`)).
- Variant: `_simulate_costed_curve_halfstep`, β=0.5, 0.3% L1 convergence
  tolerance, otherwise identical cost model. Monkeypatched into
  `group_a_plus.runners.a2118.run_a2118()` for a like-for-like comparison
  -- same switch rule, same NCF overlay config, same cost parameters.
- Two effective windows (a third request collapsed into the second because
  `00679B.TWO` has no price data before 2017-01-11):
  - **A**: 2025-01-02 to latest (2026-09-02), full production config
    including the NCF late-bull-hedge panel (`ncf_panel_631l_path`,
    `h20_max=0.33`, etc., matching `report/group_a_plus/latest/strategy.json`).
  - **B**: 2017-01-11 to latest, base switch-only config (no NCF panel), a
    longer window with more regime transitions.

### Results

| Window | Variant | Sharpe | Sortino | Max DD | Txn cost | Turnover | Rebalances |
|---|---|---|---|---|---|---|---|
| A (2025-01~latest) | baseline (instant) | 1.8934 | 1.9525 | -14.04% | $9,287 | $3.94M | 7 |
| A | half-step β=0.5 | 1.8343 | 1.8899 | **-14.62%** | $7,199 | $3.08M | 68 |
| B (2017-01~latest) | baseline (instant) | 1.0175 | 1.3569 | -20.72% | $51,545 | $21.19M | 29 |
| B | half-step β=0.5 | 0.9744 | 1.3733 | **-20.80%** | $43,095 | $17.71M | 232 |

### Verdict: negative in both windows -- do not adopt

Half-step damping reliably cuts transaction cost and turnover by
16-22%, but Sharpe worsens in both windows and max drawdown does **not**
improve -- it is slightly *worse* in the shorter, more production-relevant
window. This is the expected mechanism, not a fluke: the golden1→defensive
switch exists specifically to de-risk *quickly* once a threat is detected;
half-step trades that speed for lower cost, and the cost saved does not
compensate for the slower de-risking during genuine (non-whipsaw) regime
persistence. This is consistent with the paper's own scope -- its damping
guarantee is a continuous-time HJB value-improvement certificate under
specific curvature assumptions, not a general "slower execution is safer"
claim.

Caveat noted in the memory record: the half-step variant traded 68-232
times vs. the baseline's 7-29, and the linear-in-turnover cost model used
here has no fixed per-trade friction (minimum commission tiers, odd-lot
spread, execution/monitoring overhead) -- real-world cost of that many tiny
daily rebalances is likely understated here, meaning the reported cost
savings for half-step are probably an upper bound, not a lower bound, on
its actual advantage.

Memory: appended to `project_2608_17808_adjoint_policy_iteration_desk_review_20260903.md`
(same file as Part 1, not a separate entry, since it's a follow-up
verification of the same paper's one transferable idea).

## Files touched

- New: this handoff document.
- New (memory): `project_2608_17808_adjoint_policy_iteration_desk_review_20260903.md`.
- Updated (memory): `MEMORY.md` index line for the above, and a minor
  correction to the long-stale index line for
  `feedback_research_semantic_registry_check_before_new_research.md` (the
  underlying memory file already recorded this rule as downgraded/deprecated
  back on 2026-08-19-20, but the one-line index entry still described it as
  an active step -- corrected to match).
- Scratch-only (not committed, not production): `/tmp/claude-1000/.../scratchpad/halfstep_damping_backtest.py`.
- No production code, strategy weights, orders, or reports touched.

## Validation

Part 1 was a read-only desk review (full PDF read, cross-checked against
`MEMORY.md`). Part 2 was an actual backtest against the real `a2118`
production runner and real Taiwan OHLCV/total-return data (2017-2026 and
2025-2026 windows), using `unittest.mock.patch` to swap only the execution
mechanism -- no production file was edited, no test suite was run (none
needed changing), no commit was made.
