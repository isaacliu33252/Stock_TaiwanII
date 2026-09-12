# 1706.10059 Deep Portfolio Management - Group A+ Review

**Current status (2026-08-09, read this first):** shadow-only, not
promoted, script default changed. The initial 2026-08-08 review below found
a `cost_recovery` PVM gate that passed at `lookback_days=5` (then the
default) on 3 windows. Follow-up work the same/next day added tests, then
progressively widened the OOS set to 8 windows spanning 2017-2026 (2017-19,
2020 COVID crash, 2021 May correction, 2022 rate-hike bear, 2024 Aug
carry-unwind crash, plus the original 3) and ran a parameter sensitivity
sweep -- see the "2026-08-09 Follow-Up" sections below for all of it.
**Result: `lookback_days=5` (the old default) regresses on two independent
sharp-reversal windows (2020 COVID, 2021 May correction);
`lookback_days=3` survives all 8 windows tested so far.** The script's own
`--lookback-days` default and `DEFAULT_WINDOWS` were updated accordingly
(now 3 and 8 windows respectively), and `report/group_a_plus/latest/pvm_cost_shadow_1706_10059.json`
was regenerated to match. Still shadow-only, still not promoted -- the
evidence for `lookback_days=3` specifically is now reasonably solid across
three independent crash/correction events, but promotion still requires
workbook-aware holdings state and a longer observation period per this
project's standing promotion discipline. **All four of the original
review's "next required validation" items are now done** (OOS windows,
parameter sensitivity, workbook-aware state, live-plan interaction check).
Read the "2026-08-09 Follow-Up" sections (there are 9 of them) before
treating anything above them as current.

Date: 2026-08-08

Source: `/mnt/c/Users/isaac/Downloads/1706.10059.pdf`

Paper: Jiang, Xu, Liang, "Deep Portfolio Management: A Deep Reinforcement Learning Framework for the Financial Portfolio Management Problem"

## Scope

Review whether the paper has useful ideas for Group A+ latest strategy. `golden1_0531` is fixed and must not be modified.

## Paper Summary

The paper proposes a model-free deep reinforcement learning portfolio allocator. The agent directly outputs portfolio weights instead of predicting prices first. Its main components are:

- EIIE: Ensemble of Identical Independent Evaluators. Each asset is evaluated by a shared network block, then weights are produced through a softmax layer with a cash bias.
- PVM: Portfolio-Vector Memory. Previous portfolio weights are fed back into the policy so transaction costs and turnover are part of the decision state.
- OSBL: Online Stochastic Batch Learning. Training samples are drawn in a way that supports pre-trade training and ongoing online learning.
- Explicit reward: portfolio log-growth after transaction costs.

The experiments are on intraday cryptocurrency data, not Taiwan ETFs. Reported returns are therefore not directly transferable to Group A+.

## Fit To Group A+

Useful, but only as research/shadow first.

Group A+ already has daily ETF allocation, NCF overlays, execution plans, turnover controls, and PPO-style research environments. The paper's strongest contribution is not the crypto result; it is the architecture discipline:

- use previous target weights as part of state;
- optimize portfolio weights directly;
- include transaction costs in reward rather than adding them after model output;
- keep a cash asset in the action vector;
- validate by walk-forward/online-style batches instead of a single static split.

## Candidate Imports

### 1. PVM-style previous-weight state

Add a shadow feature block that feeds prior target weights and realized holdings into latest-strategy evaluation:

- previous target weights: `0050`, `00631L`, `00632R`, `00679B`, `cash`;
- actual holdings weights from workbook/execution plan;
- turnover required to move from current state to proposed target;
- staged-buy remainder from execution plan.

Expected value: reduce unnecessary flips between 00631L and 00632R, and make the model aware that moving from current holdings to target weights is costly.

Import status: recommended as shadow diagnostic.

### 2. Cost-aware reward for latest-strategy backtests

Current Group A+ already accounts for trading costs in several evaluators, but the paper supports making this mandatory in every promotion review:

`reward = log(portfolio value after market move and transaction cost)`.

For Group A+, this should include:

- commission;
- ETF sell tax where applicable;
- slippage;
- staged execution penalty;
- turnover cap penalty;
- missed-trade/cash drag from pre-trade guards.

Expected value: prevents strategies that look good before costs but lose after frequent rebalancing.

Import status: recommended for latest strategy promotion gate.

### 3. EIIE-style shared evaluator across ETFs

Group A+ tickers have different roles, especially `00631L` and `00632R`, so a pure shared-weight EIIE is risky. A safer adaptation is a shared backbone plus asset-role embeddings:

- equity core: `0050`;
- leveraged long: `00631L`;
- inverse hedge: `00632R`;
- bond/cash stabilizer: `00679B` and `cash`.

Expected value: a more consistent allocator that compares assets under the same feature representation.

Import status: research-only; needs walk-forward validation before any latest-strategy use.

### 4. Cash bias as an explicit action

The paper treats cash as a first-class portfolio component. Group A+ already uses cash, but the import is to keep cash in every shadow allocator and scoring function, not as residual only.

Expected value: better defensive behavior when all risky ETF signals conflict.

Import status: already partially present; reinforce in future latest-strategy evaluators.

### 5. OSBL-style rolling training/evaluation

Use rolling windows and recent replay batches for strategy validation:

- train on older windows;
- validate on a recent rolling window;
- replay 2024-2026 out-of-sample;
- include current execution-plan state as the final replay point.

Expected value: less overfit than one static training split.

Import status: recommended as validation framework, not live online learning yet.

## Not Recommended

- Do not import the crypto-trained performance claims.
- Do not use intraday 30-minute crypto assumptions for Taiwan ETF daily execution.
- Do not let a neural allocator directly overwrite live weights without guardrails.
- Do not modify `golden1_0531`.

## Practical Group A+ Integration Plan

Phase 1: Shadow only

- Build `pvm_state_shadow`: previous target weights, current workbook weights, turnover-to-target, staged remainder, guard statuses.
- Add PVM state to latest strategy diagnostics.
- No live weight changes.

Phase 2: Backtest validation

- Evaluate whether PVM/cost-aware reward improves 2024-2026 replay versus current latest strategy.
- Required metrics: final value, Sharpe, max drawdown, turnover, transaction cost, number of 00631L/00632R flips.

Phase 3: Candidate latest-strategy overlay

- Only if Phase 2 improves net-of-cost performance and does not worsen drawdown.
- Use as a no-trade / reduce-turnover / staged-entry gate first, not as a full allocator.

## Decision

There are useful importable ideas, but the correct use for Group A+ is a PVM/cost-aware shadow framework and promotion gate. Direct deep RL allocation is not ready for latest strategy without a full Taiwan ETF walk-forward validation.

Recommended next action:

1. Implement PVM-style state/reward shadow evaluator.
2. Backtest 2024-2026 against current latest strategy.
3. If it improves net-of-cost behavior, consider adding it as a latest-strategy execution/turnover guard.

## 2026-08-08 Shadow Implementation Result

Implemented:

- `scripts/evaluate/evaluate_1706_10059_pvm_cost_shadow.py`

Generated:

- `report/group_a_plus/latest/pvm_cost_shadow_1706_10059.json`
- `report/group_a_plus/pvm_cost_shadow_1706_10059/history/pvm_cost_shadow_1706_10059_20260809_000029.json`

Tested windows:

- `live_2024_2026`: 2024-01-02 to 2026-08-07
- `active_2025_2026`: 2025-01-02 to 2026-08-07
- `stress_2026`: 2026-01-02 to 2026-08-07

Initial shadow rule tested:

- Use previous target weights as PVM state.
- When a large 00631L/00632R flip appears, delay the new target by one trading step.
- Compare current latest-strategy target replay versus PVM-delayed replay after costs.

Initial result:

- `triple_pass_windows = 3 / 3`
- `pvm_delay_event_count = 5`
- `total_transaction_cost_delta = +169.78`
- `total_turnover_delta = +62,561.36`
- `net_cost_pass = false`
- `decision = research_only_rule_refinement_needed_cost_or_turnover_increased`

Interpretation:

The delayed-flip PVM proxy improved final value, Sharpe, and drawdown in the tested windows, but it increased trading cost and turnover. That fails the paper-inspired cost-aware objective. The idea remains useful, but this exact rule is not ready to promote into the latest strategy.

Refined shadow rule:

- `policy = cost_recovery`
- `lookback_days = 5`
- `cost_multiplier = 3.0`
- `max_block_days = 20`
- A large 00631L/00632R flip is blocked unless the proposed target's trailing 5-session advantage over the previous target is at least 3x estimated transaction cost.
- This uses prior weights, proposed weights, trailing prices, and estimated trading cost only; it does not peek at future returns.

Refined result:

- `triple_pass_windows = 3 / 3`
- `pvm_policy_event_count = 55`
- `total_transaction_cost_delta = -8,944.33`
- `total_turnover_delta = -3,454,780.97`
- `net_cost_pass = true`
- `decision = candidate_for_latest_strategy_shadow_queue`

Window details:

- `live_2024_2026`: final value `+108,408.13`, cost `-4,722.38`, turnover `-1,820,532.43`, rebalance count `-1`
- `active_2025_2026`: final value `+48,443.07`, cost `-2,110.23`, turnover `-813,519.91`, rebalance count `-1`
- `stress_2026`: final value `+15,948.82`, cost `-2,111.72`, turnover `-820,728.63`, rebalance count `-1`

Updated recommendation:

- Keep PVM/cost-aware framework in shadow queue.
- Do not change live latest-strategy weights yet.
- Next required validation before any import into latest strategy:
  - add more OOS windows, including 2017-2019 if matching NCF inputs are available;
  - test parameter sensitivity around lookback 3/5/10 and cost multiplier 2/3/5;
  - add workbook-aware current holdings state;
  - confirm no degradation on the latest 8/10 execution-plan workflow.

## 2026-08-09 Follow-Up: 2017-2019 OOS Window Added

Extended `evaluate_1706_10059_pvm_cost_shadow.py` to accept an optional
per-window `ncf_panel_631l_path` (new `--window` field:
`label:start:end[:bucket[:ncf_panel_631l_path]]`) so a genuinely older,
independent OOS window can drive a2118's actual NCF-based hedge regime
instead of falling back to the latest live snapshot (which would give this
window no historical hedge behavior at all and defeat the point of testing
the PVM gate). Added `backfill_2017_2019` (2017-01-03 to 2019-12-31) using
the existing `results/ncf_00631l_panel_backfill_2017_2019_20260710.csv`.

Isolated result for this window alone (production defaults: policy
`cost_recovery`, lookback_days=5, cost_multiplier=3.0):

- `triple_pass_windows = 1 / 1` (final value, Sharpe, and max drawdown all
  improved or tied vs baseline)
- `total_transaction_cost_delta = +14.79`
- `total_turnover_delta = +5,590.61`
- `net_cost_pass = false` -- this window alone does NOT clear the net-cost
  bar; the cost_recovery gate slightly increased cost and turnover here,
  unlike the three live/recent windows.

Combined 4-window result (`live_2024_2026` + `active_2025_2026` +
`stress_2026` + `backfill_2017_2019`):

- `triple_pass_windows = 4 / 4`
- `pvm_policy_event_count = 63`
- `total_transaction_cost_delta = -8,929.53` (vs -8,944.33 for the original
  3-window result -- the 2017-2019 window's +14.79 cost is a rounding error
  against the aggregate, not a reversal)
- `total_turnover_delta = -3,449,190.36`
- `net_cost_pass = true`
- `decision = candidate_for_latest_strategy_shadow_queue` (unchanged)

Interpretation: adding a real independent older OOS window did NOT flip the
decision -- the aggregate net-cost bar still clears. This is a stronger
result than the original 3-window pass (all three original windows overlap
2024-2026, so they share a lot of the same regime history; 2017-2019 is
genuinely out-of-sample in a way the others weren't). Still outstanding
before any promotion: parameter sensitivity (see below), workbook-aware
holdings state, and confirming no interaction with the live 8/10
execution-plan run.

## 2026-08-09 Follow-Up: Parameter Sensitivity Sweep

Swept `lookback_days` in {3, 5, 10} x `cost_multiplier` in {2.0, 3.0, 5.0}
(the paper review's own "next required validation" ask), all 9 combinations
run across the full 4-window set (including the 2017-2019 backfill window
above).

| lookback | cost_mult | triple_pass | net_cost_pass | decision |
|---:|---:|---:|---|---|
| 3 | 2.0 | 4/4 | true | candidate_for_latest_strategy_shadow_queue |
| 3 | 3.0 | 4/4 | true | candidate_for_latest_strategy_shadow_queue |
| 3 | 5.0 | 3/4 | true | research_only_not_promoted |
| 5 | 2.0 | 4/4 | true | candidate_for_latest_strategy_shadow_queue |
| **5** | **3.0 (production default)** | **4/4** | **true** | **candidate_for_latest_strategy_shadow_queue** |
| 5 | 5.0 | 3/4 | true | research_only_not_promoted |
| 10 | 2.0 | 3/4 | false | research_only_not_promoted |
| 10 | 3.0 | 2/4 | false | research_only_not_promoted |
| 10 | 5.0 | 2/4 | false | research_only_not_promoted |

**Interpretation -- this is the most important finding of the follow-up
work.** Only 4 of 9 combinations (44%) reach
`candidate_for_latest_strategy_shadow_queue`. The current production
default (lookback=5, cost_multiplier=3.0) does clear the bar, but it sits
inside a narrow, not-particularly-robust region of the parameter space:

- Every `cost_multiplier=5.0` combination fails regardless of lookback --
  a stricter cost-recovery bar starts rejecting flips that the 2017-2019
  window's metrics actually needed, which regresses `triple_pass_windows`
  below 4/4.
- `lookback_days=10` fails at **every** cost_multiplier tested, and not
  just on the cost/turnover axis -- `triple_pass_windows` drops to 2-3/4,
  meaning the underlying final-value/Sharpe/drawdown metrics themselves
  regress on at least one window, not merely the cost accounting.
- Only the lookback in {3, 5} x cost_multiplier in {2, 3} quadrant (4 of 9
  cells) passes.

Per this project's own standing rule
([[feedback_overfitting_fixed_window_tuning]]: more than 2-3 rounds of
tuning on the same windows needs OOS validation before claiming
improvement) and its repeated pattern of shadow candidates that looked
promising at a single parameter setting but failed a wider sweep, this
narrows rather than strengthens the promotion case. **Do not read "the
default passes" as "this is robust."** Recommend keeping this in the
shadow queue at the current default, but do not treat it as
promotion-ready until either (a) the mechanism behind the lookback=10
failure is understood, or (b) a materially wider set of OOS windows shows
the {3,5}x{2,3} quadrant holding up beyond the 4 windows tested here.

## 2026-08-09 Follow-Up: Confirmed No Interaction With Live Execution-Plan Workflow

Grepped the whole repo: `evaluate_1706_10059_pvm_cost_shadow.py` is not
referenced anywhere in `scripts/run/run_ncf_daily_pipeline.py` or
`group_a_plus/operations/execution_plan.py` -- the only files mentioning
its module name are itself and its test file. It cannot be invoked as a
side effect of a real 8/10-style execution-plan run.

Also checked for accidental glob pickup: `execution_plan.py` and
`check_group_a_plus_daily_status.py` only glob `results/00631l_leveraged_compounding_regime_*.json`
and `results/group_a_plus_promotion_gate_*.json` -- neither pattern nor
directory (`results/`) overlaps with this shadow's output location
(`report/group_a_plus/latest/pvm_cost_shadow_1706_10059.json`) or filename
prefix. No path exists for this shadow's output to be silently picked up
by production tooling.

## 2026-08-09 Follow-Up: Mechanism Behind the lookback_days=10 Failure

Per-window breakdown at lookback_days=10, cost_multiplier=3.0 (production
cost_multiplier, isolating the lookback effect):

| window | final_value_delta | sharpe_delta | mdd_delta | cost_delta | events |
|---|---:|---:|---:|---:|---:|
| live_2024_2026 | +49,211.6 | +0.0107 | 0.0000 | +461.56 | 21 |
| active_2025_2026 | +21,990.6 | +0.1092 | 0.0000 | +206.25 | 21 |
| stress_2026 | -7,831.0 | -0.1646 | 0.0000 | -29.28 | 1 |
| backfill_2017_2019 | -4,130.2 | -0.1475 | -0.0046 | -10.08 | 19 |

This splits cleanly into two behaviors, not one uniform failure:

- `live_2024_2026` / `active_2025_2026` (smoothly trending, mostly one
  regime): metrics still *improve* at lookback=10, just at higher realized
  cost/turnover than lookback=5 -- the gate is simply less decisive, letting
  through more borderline flips.
- `stress_2026` / `backfill_2017_2019` (windows containing sharp
  regime-transition points -- the 2026 stress window and the 2018-2019
  correction/recovery cycle): final value, Sharpe, *and* drawdown all
  regress. This is a genuine strategy-quality failure, not just a cost
  artifact.

**Mechanism**: the cost-recovery gate's `prior_advantage` estimate is a
trailing N-day realized-return comparison between the proposed and current
weights (see `_pvm_cost_recovery_targets`'s `lookback_days` window). At
N=10 this estimate is staler than at N=3/5 -- it averages over twice the
history before deciding whether a flip has "already proven itself." In a
smoothly trending window that staleness barely matters (the trend keeps
pointing the same direction over 10 days as over 5). At a genuine regime
turning point, a 10-day trailing window is measuring the *previous* regime's
behavior right as it's ending, so the gate's block/allow decision is more
likely to be wrong exactly when it matters most -- either holding a stale
position too long, or (per the higher event counts on the two trending
windows) letting a since-reversed flip through because its now-outdated
trailing advantage still looked large.

This is a textbook lookback-length bias/staleness trade-off inherent to
using a trailing-return proxy for "was this flip justified," not a data bug
or an implementation error. It also means the {lookback=3,5} region that
currently passes should not be assumed safe against a *different* set of
regime-transition-heavy windows than the 4 tested here -- the same failure
mode that breaks lookback=10 on `stress_2026`/`backfill_2017_2019` could in
principle also break lookback=3/5 on a window with more/sharper transitions
than these four happen to contain. This reinforces rather than resolves the
"not robust, shadow-only" verdict above: understanding *why* lookback=10
fails does not make lookback=5 safe, it explains why lookback sensitivity
exists at all in this class of gate.

## 2026-08-09 Follow-Up: Widened OOS Set -- Production Default Now Fails

Tested the review's own condition (b) directly: widened the OOS set from 4
to 6 windows by adding two genuinely sharp regime-transition periods using
existing backfill panels --
`backfill_2020_covid` (2020-01-02 to 2020-12-31, the COVID crash) and
`backfill_2022_rate_hike` (2022-01-03 to 2022-10-31). Re-ran the
previously-passing quadrant (lookback in {3,5} x cost_multiplier in {2,3})
across all 6 windows.

| lookback | cost_mult | triple_pass | decision |
|---:|---:|---:|---|
| 3 | 2.0 | 6/6 | candidate_for_latest_strategy_shadow_queue |
| 3 | 3.0 | 6/6 | candidate_for_latest_strategy_shadow_queue |
| **5** | **2.0** | **5/6** | **research_only_not_promoted** |
| **5 (production default)** | **3.0 (production default)** | **5/6** | **research_only_not_promoted** |

**The production default (lookback=5, cost_multiplier=3.0) fails once the
2020 COVID-crash window is included.** Per-window detail for that cell:
`backfill_2020_covid` final_value_delta=-6,335.5, sharpe_delta=-0.0947 --
a genuine regression, not a cost artifact. This is exactly the mechanism
diagnosed in the previous section: COVID 2020 is about the sharpest,
fastest regime transition available in this project's data, and lookback=5
is stale enough at that speed of transition to make wrong block/allow
calls. lookback=3 (NOT the current production default) survives -- both
its cost_multiplier variants stay 6/6.

Caveat: `backfill_2022_rate_hike` contributed zero events and zero deltas
in every cell tested -- no large 00631L/00632R flip was ever proposed by
the base strategy during that window, so it added coverage without adding
signal. Not a data problem, just means this window doesn't test the gate at
all; don't read its "pass" as informative.

**Updated verdict**: this closes out condition (b) from the "not robust"
call above, and the answer is negative -- the passing quadrant does NOT
hold up under a materially wider, transition-heavy OOS set at the
*production* parameter default. If this shadow candidate is ever
reconsidered, `lookback_days` should default to 3, not 5, and even that
should be re-tested against further sharp-transition windows before
promotion. **Do not promote at the current lookback=5 default under any
circumstances based on prior results in this document** -- the
`candidate_for_latest_strategy_shadow_queue` decisions recorded above for
lookback=5 predate this test and are superseded by this section.

## 2026-08-09 Follow-Up: Why backfill_2022_rate_hike Contributed Zero Signal

Investigated the "zero events/zero deltas in every cell" caveat from the
widened-window section above -- confirmed it's a structural fact about
a2118, not a bug or a wiring problem. Ran `run_a2118()` directly over the
2022-01-03 to 2022-10-31 window with the backfill panel:

- `execution_regime` only ever takes values `golden1` (31 days) and
  `group_a_plus_defensive` (171 days) -- `ncf_late_bull_hedge` occurs 0
  times.
- `ma_gap` over the whole window: mean -0.058, max +0.083, min -0.163 --
  it never gets anywhere near the `ma_gap_min=0.1` (10%) threshold that
  gates a2118's NCF late-bull hedge trigger.

a2118's NCF late-bull deleverage mechanism (and therefore the PVM
cost-recovery gate that governs its 00631L<->00632R flips) is specifically
a **deep-late-bull-market** mechanism -- it only activates when price has
run up far enough above its 100-day MA. 2022 was a persistent decline
(rate-hike bear), so price never got anywhere near that condition; there
was simply no late-bull hedge for the base strategy to propose flipping
into or out of. This is not a defect in the window or the shadow script --
it's scope clarification: **this PVM gate's entire test surface only exists
within late-bull-to-hedge transitions.** Any future OOS window meant to
stress-test this specific gate should target late-stage bull runs followed
by a reversal (which is what made `backfill_2020_covid` and `stress_2026`
informative -- both contain a sharp transition *out of* an extended run),
not bear-market windows like 2022 which structurally never engage the
mechanism at all. `backfill_2022_rate_hike` is being kept in
`DEFAULT_WINDOWS` for general strategy-health coverage, but should not be
read as validating (or invalidating) this specific gate.

## 2026-08-09 Follow-Up: Two More Late-Bull-Reversal Windows (2021, 2024)

Per the previous section's guidance on what kind of window actually tests
this gate, picked two more candidates by checking 0050.TW's max intra-year
drawdown per year:

- `backfill_2021_may_correction` (2021-01-04 to 2021-12-30): +17.0% year
  return, -11.5% intra-year drawdown around 2021-05-17 (Taiwan's first
  major COVID community-outbreak market shock, mid an ongoing bull run).
- `backfill_2024_aug_unwind` (2024-01-02 to 2024-12-31): +45.1% year
  return, -21.7% intra-year drawdown around 2024-08-05 (the August 2024
  global carry-trade-unwind crash, after a strong AI/semiconductor H1 rally
  -- the sharpest drawdown of any window tested so far).

Added both to `DEFAULT_WINDOWS` (now 8 windows total) and re-ran the
{lookback=3,5}x{cost_multiplier=2,3} quadrant:

| lookback | cost_mult | triple_pass | decision |
|---:|---:|---:|---|
| 3 | 2.0 | 8/8 | candidate_for_latest_strategy_shadow_queue |
| 3 | 3.0 | 8/8 | candidate_for_latest_strategy_shadow_queue |
| 5 | 2.0 | 7/8 | research_only_not_promoted |
| 5 (old default) | 3.0 (old default) | 6/8 | research_only_not_promoted |

Two new results worth calling out:

- `backfill_2021_may_correction` produced real signal (29-33 events
  depending on cell) and, at lookback=5/cost_multiplier=3.0, its
  `sharpe_delta = -0.0704` -- a **second, independent** window (alongside
  `backfill_2020_covid`) where lookback=5 regresses. At lookback=3 the same
  window is the strongest performer in the whole set
  (final_value_delta=+18,283.8, sharpe_delta=+0.1587).
- `backfill_2024_aug_unwind` again contributed zero events, but for a
  **different reason** than `backfill_2022_rate_hike`: `execution_regime`
  was 100% `golden1` all year and `ma_gap` did exceed the 0.1 trigger
  threshold (max 0.237) -- unlike 2022, the market got hot enough. The
  late-bull trigger still never fired because it also requires the NCF
  panel's own `h20_prob_up < h20_max` and `confidence > conf_min`
  conditions to hold on the *same day* as the high ma_gap, and for this
  panel/year they never coincided. Not further diagnosed this pass; flagged
  as a different zero-signal mechanism, not a repeat of the 2022 case.

**This is now meaningfully stronger evidence than the prior 6-window
result**: `lookback_days=3` holds up across three independently-sourced
sharp-reversal events spanning 2020-2026 (COVID crash, May 2021 correction,
the built-in 2026 stress window), while `lookback_days=5` (the old default)
fails on two of those three. Still shadow-only per this project's
promotion discipline -- workbook-aware holdings state and the live-plan
interaction check (both already done above) plus a longer observation
period are still the bar for promotion, and `backfill_2024_aug_unwind`
being uninformative means the sharpest drawdown available in this dataset
still hasn't actually tested the gate. But the case for `lookback_days=3`
specifically (over the old default of 5) is now well-supported, not just
lucky on one window.

## 2026-08-09 Follow-Up: Test Coverage Added

`tests/test_evaluate_1706_10059_pvm_cost_shadow.py` (15 tests) now covers
`_weight_turnover`, `_pvm_delay_targets`, `_pvm_cost_recovery_targets`
(including the block/allow/max-block-days-forces-through edge cases), and
`_summarize`'s four decision branches. `evaluate_window()`/`build_report()`
remain integration-level, exercised by the real end-to-end runs recorded in
this document rather than by mocked unit tests.

## 2026-08-09 Follow-Up: Workbook-Aware Holdings State (Candidate Import #1)

Implemented the one item from the original review's "Candidate Imports"
section that had never actually been built: real workbook/execution-plan
holdings state, not just the backtest's simulated target-weight series.
Added `build_workbook_aware_snapshot()` and a `--workbook-snapshot
<execution_plan.json>` CLI flag. Diagnostic-only -- reads
`current_holdings`/`current_prices`/`current_total_assets`/`target_weights`/
`staged_target_shares_before_guards` from an execution_plan.json payload and
real trailing closes, and reports whether *today's actual* holdings-to-
target transition would trip the cost-recovery gate. Never writes to
execution_plan.json or changes any live weight/trade. Result attached as a
new top-level `workbook_aware_snapshot` report key (`null` unless the flag
is passed).

Ran against the real production `report/group_a_plus/latest/execution_plan.json`
(2026-08-07 data): current real holdings are 0050=41.1%/00632R=2.1%/
00679B=7.9%/cash=48.9% (no 00631L position at all); target wants
0050=30%/00632R=27.1%/cash=42.9%. Turnover is 50% -- a large real
rebalance -- but `large_flip_detected: false`. This is correct, not a
missed detection: the gate is scoped specifically to 00631L<->00632R
flips, and there is currently no 00631L position to flip out of. The
current staged 00632R accumulation is a fresh entry funded from cash, a
different trade pattern this gate was never meant to police.

Added 3 tests (`TestBuildWorkbookAwareSnapshot`, now 18 total in the test
file): missing-fields early-return, a synthetic no-631L-position case
(confirms high turnover alone doesn't false-trigger the gate), and a
synthetic real 00631L->00632R flip case (confirms the gate does engage and
resolves to either block or allow, not silently do nothing, when the
actual pattern it's scoped for is present).

This closes out the last of the original review's four "next required
validation" items (OOS windows, parameter sensitivity, workbook-aware
state, live-plan interaction check -- all now done). Verdict is unchanged:
shadow-only, not promoted.
