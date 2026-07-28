# arXiv:2601.04062v3 (SPO Portfolio Optimization) Review Handoff - 2026-07-26

**This is one of two documents from the 2026-07-26 session.** See
`GROUP_A_PLUS_20260726_SESSION_HANDOFF_INDEX.md` for the full session index
(this doc plus the separate `TargetWeightSignal`/point-in-time-store
implementation) if picking up later work -- read that first if you only
read one file.

## Final status (read this first)

**Group A+ (a2118) is unchanged and remains the only production strategy.**
This session went through the paper review, the gate-robustness diagnostic
(checklist item 7), the turnover-penalty rejection, and then a long detour
into whether an "optimization layer" should be added across the user's
*full* real holdings (not just Group A+'s 4-ticker tactical universe) --
that detour is documented in full in the "groupFull exploration and
abandonment" section near the end of this file, and ends with the user
saying "算了, 還是做groupA+" (never mind, stick with Group A+). No
production file was changed anywhere in this session. One new dormant
research script exists (`scripts/backtest/backtest_group_full.py`) --
functional, not wired to anything, not deleted, status "abandoned, kept as
reference" (see that section for why it wasn't torn back out).

## Trigger

User provided `C:\Users\isaac\Downloads\2601.04062v3.pdf` ("Smart
Predict-then-Optimize Paradigm for Portfolio Optimization in Real
Markets", Wang & Hasuike, Waseda) and asked whether it has anything worth
importing into Group A+ / the latest strategy. This is the same kind of
task as the 2605.20636v2 (RGRR/continuous-timing-signal) and 2607.06117v1
reviews already in this repo (see
`GROUP_A_PLUS_SIGNAL_VALIDATION_CHECKLIST_20260723.md`'s origin section and
`docs/2607_06117_RGRR_QQQ_DIA_GROUPA_PLUS_REVIEW_20260725.md`) -- read a
paper, decide what (if anything) transfers to this specific codebase, and
be honest about what doesn't.

**Bottom line up front: nothing about the paper's actual mechanism (SPO+/
PyEPO end-to-end differentiable training through a convex portfolio
optimizer) transfers.** Group A+ has no optimization-solve decision layer
to embed it into. Exactly one diagnostic *idea* from the paper (RobustSPO's
worst-case-perturbation training philosophy) was judged worth adapting as
a read-only validation tool, and one other idea (soft turnover penalty
replacing a hard cap) was investigated and explicitly rejected with
concrete evidence. No production code was changed. No `execution_plan.json`
generation, gate threshold, or live signal was touched at any point in this
session.

## Paper summary (for context)

- **Core idea**: Smart Predict-then-Optimize (SPO) trains a return
  predictor using a decision-focused surrogate loss (SPO+, a convex upper
  bound on decision regret) that embeds the downstream portfolio
  optimization problem into the training loop, instead of the
  conventional predict-then-optimize (PtO) approach of minimizing MSE and
  treating predictions as fixed optimizer inputs. Implemented via PyEPO
  (differentiable optimization layer, gradients backpropagated through an
  LP solve).
- **Three portfolio formulations tested**: MaxReturn, MaxReturn+transaction
  fee (`γ‖w−w_{t-1}‖₁` penalty in the objective), MaxReturn+ℓ2 weight
  regularization.
- **RobustSPO**: trains against worst-case multiplicative perturbations of
  the predicted return vector within an uncertainty set `‖ζ‖∞ ≤ ρ`, via
  Monte Carlo sampling of the inner max, rather than trusting the point
  prediction.
- **SoftmaxDFL baseline**: a fully differentiable neural allocator that
  skips the explicit optimization layer entirely (softmax weights direct
  from a DNN). Included as a contrast case.
- **Data/setup**: US ETFs, 2015-2025, monthly rebalancing, rolling-window
  backtest, linear predictors only (deliberate simplicity, "Occam's
  razor").
- **Headline results** (full backtest 2016-2024): SPO+ beat PtO Markowitz
  on Sharpe (0.785 vs 0.659) and return (14.05% vs 9.00%). During COVID-19
  2020, RobustSPO(ρ=0.1) and SPO+-with-fee both cut MaxDD to ~-9.6% vs
  PtO's -30.2%, while SPO+ alone (no fee/robustness) still beat PtO on
  return. SoftmaxDFL underperformed everything, especially in the crisis
  window, attributed to instability from skipping the explicit
  optimization structure. In the 2024 bull market, PtO Markowitz
  outperformed the more conservative decision-focused variants -- explicit
  trade-off the paper names between aggressiveness (PtO) and robustness
  (DFL).

## Why the core mechanism doesn't transfer

Confirmed via code exploration (not assumption) before drawing this
conclusion: `report/group_a_plus/latest/execution_plan.json` is generated
by `group_a_plus/operations/execution_plan.py::build_execution_plan()`
(around line 573), which calls `daily_signal.py::build_daily_signal()` for
`target_weights`. This is **purely rule-based/threshold logic** -- a
regime-classification lookup table (e.g. `LATE_BULL_HEDGE` weights in
`group_a_plus/runners/a2118.py:23`) combined with discrete NCF-model-driven
trims (`_apply_bearish_high_risk_trim`, `_apply_tsmc_weakness_trim` in
`daily_signal.py`), each a fixed fraction gated by a hand-tuned threshold.
There is no LP/QP solve anywhere in this path, so there is no
differentiable optimization layer for an SPO+ loss to backpropagate
through. Rebuilding one (a real cvxpylayers/PyEPO-style optimizer over
target weights) to make the paper's actual method applicable would be a
large, separate architectural undertaking, and Group A+'s asset universe
(effectively 2-4 tickers, mostly binary 0050/00631L allocation decisions)
is a poor match for the paper's multi-asset continuous-weight setting
regardless.

Also confirmed: the paper's SoftmaxDFL-underperforms-explicit-structure
finding is an independent literature data point supporting this project's
existing caution against replacing rule-based gates/overlays with a
black-box end-to-end policy -- not a new conclusion, just corroboration of
[[feedback_strategy_promotion_caution]] and
[[feedback_automation_first_design_principle]].

## What was adopted: checklist item 7 + a reusable diagnostic script

Added item 7 to `GROUP_A_PLUS_SIGNAL_VALIDATION_CHECKLIST_20260723.md`:
a worst-case-perturbation robustness check for any hard-threshold gate
built on a composite score assembled from independent sub-indicators.
`total_risk_score` (used across `daily_signal.py`, `market_state.py`,
`specialist_router.py`, `trough_nowcast.py`, and a2110/a218/a219) is the
concrete example -- it is a sum of 14 independent binary sub-indicators (12
chip + 2 derivative; see `_regime_features` in
`backtest_group_a_plus_switch_policy.py:766-881`), so its natural
"prediction noise" is discrete: one sub-indicator flipping moves the score
by exactly ±1. This is a direct discrete analogue of the paper's `ζ`
uncertainty set.

Built `scripts/evaluate/evaluate_total_risk_score_gate_robustness.py`
(new file, read-only, does not touch any production gate). For a given
threshold it reports:
1. **Margin-to-boundary**: of historical fires, what fraction sat exactly
   at the threshold (one flip from not firing)?
2. **Monte-Carlo decision-flip probability**: flip each of the 14
   sub-indicators independently with probability `--flip-prob` (default
   0.15) across `--n-trials` (default 1000) trials, grouped by the day's
   original margin-to-threshold.
3. **Forward-return regret proxy**: mean forward 5d/20d 0050 return for
   marginal (score==threshold) vs. clear (score>=threshold+2) vs.
   never-fired days.
4. **`--persistence-days N`**: optional -- require the threshold to be met
   for N consecutive days before "firing," to test whether a temporal
   confirmation requirement reduces boundary fragility.
5. **Yearly score-ceiling table** (`_yearly_score_ceiling_report`,added
   after the mistake described below): prints max/mean/count of
   `total_risk_score` per year as a standing data-coverage sanity check.

## Finding 1: the `total_risk_score >= 9` gate (`_apply_bearish_high_risk_trim`)

First run flagged this gate (the one that actually trims live 00631L
exposure in `daily_signal.py`) as fragile: of 13 historical firing
episodes (21 days), 81% sat exactly at the threshold, with a simulated 51%
decision-flip probability under plausible sub-indicator noise at margin=0.
The forward-return regret proxy showed **no separation** between marginal
fires and non-fires (marginal fwd_20d ≈ +1.6%, never-fired ≈ +1.3-1.7%
depending on window) -- i.e. the gate's rare marginal triggers don't carry
an obviously protective forward-return signal in isolation.

A follow-up test with `--persistence-days 2` and `3` (requiring 2-3
consecutive days above threshold before firing) reduced the flip rate away
from the boundary (margin=-1 flip rate 27%→4%→1%) but did **not** fix the
core ambiguity, and cut the already-rare episode count further (13→5→3
episodes across the usable window) -- concluded not worth adopting;
persistence trades one kind of fragility (boundary noise) for another
(near-total loss of statistical power on an already-rare gate).

**Not acted on.** n=17 marginal-fire days is too small a sample to justify
a threshold or persistence change in either direction -- doing so would be
tuning to noise, the trap already named in
[[feedback_overfitting_fixed_window_tuning]]. Logged as a tracked red flag
(unproven, not disproven), not a promotion/rejection verdict.

## Correction: the "10 years of history" framing was wrong (data-coverage bug in the analysis, not the code)

Mid-session the user asked "回測所有年份?" (backtest all years?), which
prompted verifying the DB's actual source-table coverage
(`SELECT min(dt) FROM <table>` on all 12 chip + 2 derivative source
tables). Finding: `total_risk_score`'s sub-indicators were onboarded in
phases as their source tables came online --
`dealer_futures_data`/`dealer_options_data`/`day_trading_data`/
`securities_lending_data`/`foreign_shareholding_data` only exist from
**2025-01-02**; `institutional_data`/`margin_data` from **2020-01-02**;
`derivative_institutional_data` from **2018-06-05**; `shareholding_
distribution` from 2015-04-30; `market_margin_data` from 2007-07-02 (the
only long-history source). `_load_chip_features` silently fills missing
columns with 0.0 for any date before a table existed, so the score's
*practical ceiling* rose over time even when nothing about the market
changed.

Re-running with 0050.TW price history extended to its full 2009-01-02
start (the original run's loader had also been unintentionally floored at
2017 -- it reused the production switch-policy backtest's 4-ticker join
via `_load_prices`, which requires all of `0050.TW`/`00631L.TW`/
`00632R.TW`/`00679B.TWO` to have data via `dropna(subset=tickers)`, and
`00679B.TWO` didn't IPO until 2017-01-11; fixed by loading `0050.TW` alone
in `_load_history()` since `_regime_features` only reads that column)
confirmed: yearly max `total_risk_score` was 1 from 2009-2017, 2 in
2018-2019, 7-8 in 2020-2022, 5 in 2023-2024, 10-11 in 2025-2026. **All 21
historical fires of the `>=9` gate fall in 2025-2026 regardless of how far
back the price history goes** -- the gate was structurally unfireable
before then, not "rare in a calm market." The genuinely usable evaluation
window for this specific threshold is ~1.5 years, not 10.

This did not change the "don't act on it" conclusion (if anything it
reinforces caution -- an even shorter usable window), but it materially
changes how the finding should be described to a future reader, and the
mistake pattern itself was written up separately as
[[feedback_check_data_coverage_before_multiyear_framing]] since it is a
general risk for any composite-score analysis in this repo, not specific
to this gate. The script now prints the yearly ceiling table by default so
this surfaces automatically on every future run.

## Finding 2: full sweep across all four production `total_risk_score` thresholds

Ran the corrected script against all four thresholds actually used in
production (`--thresholds 9 8 7 6`, full available history):

| threshold | production use | days/episodes fired | % at exact threshold | flip rate @ margin=0 | marginal-fire fwd_20d vs. never-fired baseline |
|---|---|---|---|---|---|
| 9 | `_apply_bearish_high_risk_trim`, `specialist_router.py` (defensive) | 21 days / 13 episodes | 81.0% | 51.3% | +1.63% vs. +1.33-1.73% (flat) |
| 8 | `trough_nowcast.py` (bottom-detection / reversal) | 47 days / 28 episodes | 55.3% | 43.1% | **+6.02% vs. +1.30% (clearly higher)** |
| 7 | `market_state.py` `bear_breakdown` (defensive) | 87 days / 38 episodes | 46.0% | 34.5% | -0.41% (5d) / +1.05% (20d) vs. +1.30-1.70% (flat/mixed) |
| 6 | `market_state.py`, a2110/a218/a219 entry gates (defensive) | 173 days / 63 episodes | 49.7% | 26.6% | +2.00% vs. +1.33-1.69% (flat, wrong direction if meant as protective) |

**Pattern**: all four gates show substantial same-day decision-flip risk
at the boundary (27-51%) -- fragility at margin=0 is not unique to the
`>=9` gate. But the forward-return regret proxy splits cleanly by
direction: the one bottom-detection/bullish-reversal threshold (8) shows a
real, large signal even at its marginal fires, consistent with its
designed purpose. The three defensive/bearish-oriented thresholds (6, 7,
9) all show the same pattern -- marginal fires carry no meaningfully worse
forward return than non-fires. This is **one pattern independently
confirmed three times**, not three isolated findings, which raises its
weight somewhat above a single-gate curiosity.

**Still not acted on.** Same small-sample caveat as Finding 1, plus this
diagnostic tests `total_risk_score` in isolation without the other
co-conditions production actually combines it with (`drawdown`, `ma_gap`,
`signal_alignment` direction) -- it cannot distinguish "this score alone is
weak evidence" from "this score plus its usual co-conditions is fine." A
proper resolution would require a multi-factor-controlled version of the
same analysis; user was offered this as an option and explicitly chose
*not* to pursue it this session (see "What was NOT pursued" below).
Logged as a pattern to revisit once more real crisis events accumulate
data, not a code-side task.

## Finding 3 (idea investigated and rejected): soft turnover penalty vs. hard cap

The paper's transaction-fee formulation (`argmax_w [r̂ᵀw − γ‖w−w_{t-1}‖₁]`)
bakes turnover cost into the optimization objective as a smooth penalty,
always producing *some* decision. Group A+'s actual turnover control
(confirmed via code read, `group_a_plus/operations/execution_plan.py`) is
structurally different: `max_turnover_ratio` (default 0.5) is a **hard
block**, checked at line 746 --
`if turnover_ratio > max_turnover_ratio: guard_reasons.append(...)`,
which flips `execution_allowed = False` and
`planning_status = "manual_review_required"` for the *entire* day's plan
(not a partial/discounted execution). `min_trade_notional`/
`min_weight_deviation` (`_apply_execution_controls`, line 226) and staged
buys (`_apply_buy_staging`, line 275) are separate, smaller-scale controls
that already behave more like soft suppression, but the headline turnover
cap does not.

Checked whether this hard block has ever actually fired in real production
history: `grep -rl "exceeds automatic limit" report/group_a_plus/` found
one real trigger,
`report/group_a_plus/latest/execution_plan_20260628.json`
(`actual_data_date: 2026-06-26`, `turnover ratio 65.57%` vs. the 50% cap).
Inspecting that plan's `current_holdings` vs. `target_shares`: it was a
full exit from `00679B.TWO` (bond ETF, 5000 shares held → 0 target) paired
with building `00631L.TW` from 10 → 896 shares -- i.e. a genuine
structural asset-class reallocation, not noise. The one real historical
trigger of this hard cap is exactly the kind of event (large, structural,
worth a human look before executing) the mechanism appears designed to
catch.

**Rejected.** The paper's soft-penalty formulation assumes a fully
automated pipeline with no human-in-the-loop option, where a hard block
simply isn't available -- the system must produce *a* decision every
period. Group A+ deliberately keeps a manual-review escape valve for large
structural rebalances (consistent with
[[feedback_automation_first_design_principle]] and
[[feedback_strategy_promotion_caution]]), and the one real historical
trigger validates that the valve fired on exactly the kind of event it
should. Replacing it with a smooth cost-penalty that always auto-executes
(possibly discounted) would remove that checkpoint for a marginal
"smoother execution" benefit -- assessed as a net safety downgrade, not an
improvement. No code changed.

## What was NOT pursued (explicit choice points, in case revisited later)

- **Multi-factor-controlled version of the Finding-2 analysis** (control
  for `drawdown`/`ma_gap`/`signal_alignment` alongside `total_risk_score`
  before judging whether the defensive gates are "really" weak at the
  margin) -- offered via `AskUserQuestion` after Finding 2, user chose to
  look at the paper's remaining low-priority idea (Finding 3) instead.
  This remains the most promising unexplored follow-up if the
  `total_risk_score`-margin fragility pattern is worth resolving properly
  rather than just tracking.
- **Distributionally robust optimization / VaR-type constraints** and
  **tree-based predictors within a DFL framework** -- both named
  explicitly as the paper's own future-work section, not evaluated here at
  all since they inherit the same "no optimization layer to embed into"
  blocker as the core method.
- **ℓ2 weight-regularization / diversification-promoting mechanism** --
  not evaluated for import; judged low-relevance up front given Group A+'s
  small (2-4 ticker) universe versus the paper's genuinely multi-asset
  setting, so this was not investigated in depth this session.

## groupFull exploration and abandonment (same session, continued)

After Finding 3 (turnover-penalty rejection) closed out the paper-derived
ideas, the user asked a genuinely different follow-up question: "optimization
solve 層, 應該加?" (should we add an optimization-solve layer?) -- i.e., not
"does the paper's idea fit," but "should Group A+ get a real optimizer at
all, now that we know it doesn't have one." This section documents that
whole thread, which ended in "算了, 還是做groupA+" (never mind, stick with
Group A+) -- recorded in full since a meaningful amount of real
investigation happened before landing back where it started.

**Step 1 -- initial recommendation: no.** Assessed against Group A+'s
narrow decision universe (`TICKERS = ('0050.TW', '00631L.TW', '00632R.TW',
'00679B.TWO')`, effectively a 2-3-way tactical allocation) an optimization
layer looked like poor ROI: too few assets for optimization to matter much,
would require rebuilding NCF model training around continuous return
targets instead of the classification/tail-risk outputs it already has, and
would reduce interpretability against this project's stated preference for
inspectable rule-based gates ([[feedback_automation_first_design_principle]],
[[feedback_strategy_promotion_caution]]).

**Step 2 -- user pushed back: "若是所有持股?"** (what if it's the full
holdings?). This was the right challenge -- checking the actual workbook
(`taiwan_stock_20260619.xlsx` at the time) showed the user's real holdings
span **9 tickers across two labeled groups**, not the 4 Group A+ actually
manages: "Group A++" (0050/00631L/00632R/00679B/**00751B**) and "Group B"
(0056/00646/00713/00878). Notably, **00751B was sitting in the workbook
under Group A++ but is not in Group A+'s `TICKERS` constant at all** -- the
decision system has never managed it.

**Step 3 -- clarifying question, user answered "group full 可以用?"**
(asking, in effect, whether it's feasible/sensible to use the full
combined group). Investigated further and found real prior infrastructure:
`GROUP_AB_FINAL_HANDOFF_20260605.md` documents a fully parameter-optimized
(768 candidates) two-block "Group A + Group B" governance system
(`backtest_group_ab_meta_governed.py`, `finrl_meta_strategy_governance.py`)
with a documented recommendation (Sharpe 2.60, MaxDD -18.9% over
2024-2026) -- but last touched in the single 2026-06-27 snapshot commit and
not referenced by any current production/pipeline script.

**Step 4 -- user asked to see prior records ("看之前的記錄?")** to find out
*why* that system went dormant. A fork (agent id not recorded here per
tool-use convention, see conversation) traced ~30 handoff docs from
2026-06-05 through 2026-06-28 and found:
- The GroupAB combined governance system was **research/backtest-only,
  never deployed live** -- not "abandoned production," just never went
  live in the first place.
- **"GroupA+" never meant "Group A + Group B combined."** Its first
  definition (`GROUP_A_PLUS_DEFINITION_20260606.md`, 2026-06-06) was
  already "Group A tactical + 00679B defensive sleeve" -- GroupAB and
  GroupA+ were two separate concurrent research tracks from day one, not
  a lineage. My earlier assumption that GroupA+ "superseded" GroupAB was
  wrong.
- **00751B has an explicit, documented rejection**:
  `GROUP_A_PLUS_PLUS_00751B_CASH_20260619.md` (2026-06-19) backtested it
  against cash in GroupA++ across two windows and found it strictly worse
  on both return and MaxDD (e.g. 2020-2026: -13.33pp return, MaxDD -41% vs
  -25% for cash). This -- not neglect -- is why it's absent from
  `TICKERS` today.
- **Group B (0056/00646/00713/00878) has a real, working, bug-fixed RL
  policy** (`GROUP_B_TICKERS` in `refresh_group_data.py:32`, note this
  6-ticker constant also includes 00679B/00751B -- overlapping with Group
  A++'s universe) that produced real signals through 2026-06-28 and then
  simply stopped being invoked, with **no documented decision found**
  explaining why -- reads as attention drifting to a2118, not a considered
  call, unlike 00751B's clear-cut rejection.

**Step 5 -- user said "做一個groupAB(full)的"** (build a groupAB(full)).
Attempted to scope this with an `AskUserQuestion` about Group B's signal
source (revive the dormant RL policy vs. treat Group B as static/passive
vs. build a fresh classical mean-variance model) -- **the user rejected the
question and said to just proceed**, renaming the target to "groupFull"
and pointing at an updated, simplified holdings workbook,
`taiwan_stock_20260725.xlsx`, which no longer even labels a Group A++/
Group B split -- just one flat row of 8 real positions: 0050, 0056,
00631L, 00646, 00679B, 00713, 00751B, 00878 (00632R dropped, 0 shares).

**Step 6 -- built `scripts/backtest/backtest_group_full.py`.** Since
further clarifying questions were explicitly rejected, made and disclosed
(rather than asked) the remaining design calls: classical Max-Sharpe /
PtO-Markowitz baseline (the paper's own Section 3.3.1 formula,
`argmax w^T r_bar / sqrt(w^T Sigma w)`, long-only, fully invested, 252-day
trailing lookback, ~monthly rebalance), over all 8 real tickers jointly
using their full common price history (2020-07-10 onward -- 00878's IPO,
the latest start date of the 8), with production-matching cost assumptions
(`commission_rate=0.001425`, `slippage_rate=0.0005`,
`equity_etf_sell_tax=0.001`, bond ETFs exempt from the sell tax). 00751B
was deliberately left in the optimization universe rather than
hard-excluded, to see whether a real optimizer would independently arrive
at the same "worse than nothing" conclusion the 06-19 backtest found.

**Result**: 2021-07-23 to 2026-07-24 backtest -- annual return 22.62%, vol
18.52%, Sharpe 1.2214, Sortino 1.6432, MaxDD -20.10%, 39 rebalances, total
cost ~$59,938 on a $1M start. Current-day (2026-07-24) recommendation vs.
actual holdings showed large deltas: recommended dropping 0056 (37.6% of
current real value) to 0%, 00713 (13.2%) to 0%, and 00751B (5.4%) to 0% --
**00751B's recommended weight independently landing at 0% matches the
06-19 finding without having been told to**, some evidence the optimizer
is behaving sensibly rather than randomly -- while pushing 0050/00646/
00679B much higher.

**Two caveats surfaced and disclosed before the user closed the thread**:
1. This build never actually integrated a2118's tactical signal for the
   0050/00631L leg as originally stated it would -- it fell back to the
   paper's pure classical baseline (all 8 tickers treated symmetrically by
   trailing historical mean/covariance), not a hybrid "tactical sub-slice +
   passive optimizer" design. This was flagged as a real gap, not hidden.
2. The knife-edge 0% recommendations (0056/00713/00751B all exactly 0%)
   are a textbook symptom of naive mean-variance optimization's
   sensitivity to estimation error in trailing sample means -- exactly the
   failure mode the paper itself motivates its ℓ2-regularization extension
   to address (Section 3.1.3, "may yield highly concentrated portfolios").
   This output was explicitly flagged as *not* an executable
   recommendation as-is.

**Step 7 -- user ended the thread**: "算了, 還是做groupA+ ,留下詳細記錄"
(never mind, stick with Group A+, leave a detailed record) -- this section
is that record. `scripts/backtest/backtest_group_full.py` is left in the
repo (functional, read-only research script, does not touch any production
path) rather than deleted, since it's a real working reference for "what
would a naive full-portfolio optimizer say" if this thread is ever picked
back up -- but it is **not** production code, **not** promoted, and should
not be treated as a live recommendation source. If this is revisited later,
the two open design questions are exactly the two caveats above: (a)
whether/how to actually blend a2118's tactical signal in rather than
treating all 8 tickers symmetrically, and (b) whether to add
regularization/position caps to avoid the knife-edge all-or-nothing
allocations. The Group B RL policy (dormant since 2026-06-28) and the old
GroupAB governance system (`backtest_group_ab_meta_governed.py`, dormant
since research-only 2026-06-05) both remain untouched, unrevived
alternatives if the classical-optimizer approach taken here isn't the
direction a future session wants.

## Companion paper reviewed (arXiv:2605.01176v4) -- also closed, no action

After the groupFull thread closed, user asked to analyze a second paper by
the same authors: `2605.01176v4`, "Decision-Induced Ranking Explains
Prediction Inflation and Excessive Turnover in SPO-Based Portfolio
Optimization" (Wang & Hasuike). Read in full (8 pages).

**Paper summary**: a self-critique of the SPO+ framework from the first
paper. Uses a KKT-based proof that SPO-optimized portfolio decisions
reduce to a ranking over risk- and transaction-cost-adjusted marginal
scores (`r̂_i - κs_i` for return-max+fee, `r̂_i - 2λ(Σw)_i - κs_i` for
mean-variance+fee), not a direct use of predicted-return magnitudes.
Empirically shows SPO+-trained predictors exhibit "prediction inflation"
(predicted monthly returns far exceed realistic/realized scale -- e.g.
Table 1: ~85-96% monthly turnover across DOW/ETF_A/ETF_B datasets,
unmoved by raising the risk-aversion parameter λ from 0.1 to 50) because
the SPO+ objective rewards exaggerating cross-sectional score gaps to
force a clear downstream ranking, not calibrated forecasting. Proposes and
tests three stabilizers: prediction clipping (`clip(r̂, -γ, γ)`), min-max
rescaling to a realistic range (preserves ranking, changes scale), and
partial portfolio adjustment (`w_t = w_{t-1} + δ(w*_t - w_{t-1})`, δ=0.1 --
move only partway toward the target each rebalance instead of jumping
fully). Finding: partial adjustment is what actually controls turnover
(Clip+Adj most conservative/stable, Rescale+Adj best returns/Sharpe);
clipping/rescaling alone barely help turnover since they don't touch the
ranking signal the optimizer reacts to.

**Verdict: does not transfer, and unlike the first paper, not even
partially.** The paper diagnoses a specific pathology (SPO+-trained
predictors self-inflating to force decisive rankings) that has no
counterpart anywhere in Group A+ -- confirmed by design, not by omission:
Group A+ has no SPO+-trained (or any DFL-trained) predictor at all. NCF
models are trained on AUC/Brier (bounded [0,1] classification outputs, not
unbounded continuous "predicted returns" that could inflate), and
`target_weights` come from a hand-tuned regime lookup table plus bounded
discrete `trim_fraction` adjustments -- there is no continuous predicted-
return vector anywhere in the live pipeline that clipping or rescaling
could even apply to. The paper's diagnosis has no target here.

The one superficially transferable idea, partial portfolio adjustment
(gradual δ-interpolation toward target weights every rebalance), was
checked against this project's own prior evidence rather than assumed
novel: it is mechanistically the same category of intervention (delay/
smooth the speed of reacting to a target signal) as two things already
tested and rejected on the A21.19 shadow candidate for the identical
reason --
[[project_a2119_no_trade_band_sweep_fp_bug_20260725]] (wider no-trade
band, delays execution of an already-computed target) and
[[project_a2119_tilt_update_freq_sweep_20260725]] (lower tilt-update
frequency, delays recomputing the target itself). Both were rejected
because slowing reaction to the target made crisis-window performance
(2020 COVID specifically) meaningfully worse -- turnover/cost dropped a
lot, but so did the protective response exactly when it mattered. No new
evidence in this paper overrides that prior finding, so partial adjustment
was not tested again from scratch; it was closed by citing the existing
result rather than re-running it.

**No code was written or changed for this paper.** Pure read-and-assess;
closed in the same conversation turn it was opened, no diagnostic script
built (unlike the first paper, where checklist item 7 came out of a
genuinely applicable idea -- this paper had none).

## Files touched this session

- `GROUP_A_PLUS_SIGNAL_VALIDATION_CHECKLIST_20260723.md` -- added item 7
  and its 2026-07-26 follow-up addendum (full 4-threshold sweep results).
- `scripts/evaluate/evaluate_total_risk_score_gate_robustness.py` -- new
  file, read-only diagnostic, no production dependency changes.
- `scripts/backtest/backtest_group_full.py` -- new file, read-only research
  script (classical Max-Sharpe over the full 8-ticker real holdings),
  abandoned per the user's final decision but left in the repo as a
  reference; not wired to any production path.
- This handoff document.
- Memory: [[project_spo_paper_robustness_checklist_item7_20260726]],
  [[feedback_check_data_coverage_before_multiyear_framing]],
  [[project_groupfull_explored_and_abandoned_20260726]].

**No production file was modified.** `execution_plan.py`, `daily_signal.py`,
`market_state.py`, `specialist_router.py`, `trough_nowcast.py`, and every
gate threshold discussed above are unchanged from before this session.
Group A+ (a2118) remains the sole production strategy at the end of this
session, exactly as it was at the start.
