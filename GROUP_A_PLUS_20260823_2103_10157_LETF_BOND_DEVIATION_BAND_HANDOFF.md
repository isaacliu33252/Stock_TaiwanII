# GroupA+ 2026-08-23 Handoff: arXiv:2103.10157 Leveraged ETF Investing Review

## Status

Final decision: `do_not_promote`. The paper's core mechanism was tested
directly on Taiwan data (not inferred by analogy from prior research) and
does not replicate. No production code was changed.

## User Request

User provided: `C:\Users\isaac\Downloads\2103.10157.pdf`

Question: Analyze whether the paper has useful advantages that can be
imported into GroupA+ and the latest strategy.

## Paper Summary

Paper: `arXiv:2103.10157v1 "Leveraged ETF Investing"` (Tal Miller, March
2021).

Core method: bootstrapped Monte-Carlo (BMC) simulation of leveraged and
unleveraged mixed stock/bond portfolios, using 1989-2020 daily US market
data (SP500, NDX100, the long-term treasury ETF VUSTX as the bond proxy).
5-day block bootstrap preserves short-term serial correlation; same-day
joint sampling across assets preserves the stock/bond anti-correlation.
Explicitly cites "Hedgefundie's Excellent Adventure" (Bogleheads forum) as
the origin of the 2x/3x-leveraged-stock + leveraged-bond idea.

Core claim: a **fixed-ratio** mix of a leveraged-stock ETF and a bond ETF,
rebalanced back to target whenever any component's weight drifts more than
20% from target (a continuous "deviation-band" rebalancing scheme -- both
legs are always held, this is not a regime switch), historically beat a
100% unleveraged-stock buy-and-hold portfolio on **both** risk (5th-
percentile final yield, 5th-percentile minimum yield during the period,
median max drawdown) **and** reward (median final yield / CAGR)
simultaneously. The mechanism is a "rebalancing bonus": because stocks and
bonds are anti-correlated, forced rebalances systematically buy the dip in
whichever leg just fell.

Paper's own best configurations: 3x leverage at 35-45% stock allocation, or
2x leverage at 40-60% stock allocation. Also finds that 1.8x margin-based
leverage slightly outperforms 2x leveraged-ETF leverage on both risk and
reward, because margin avoids the LETF's daily-reset volatility drag.
Results hold in both tax-free and taxed (Israeli 25% capital-gains)
account simulations. LETF price-evolution model: `dp = dp_index,TR * L -
ER/252 - LR*(L-1)/252` (expense ratio + LIBOR-based leverage borrowing
cost).

## Prior Context Checked (per feedback_research_semantic_registry_check_before_new_research)

`group_a_plus/research_semantic_registry.json` and memory had no direct
prior review of this paper. However, GroupA+ already tested and **removed**
00679B (a Taiwan-listed long-duration US treasury ETF) from a2118's
defensive basket
(`project_a2118_defensive_basket_00679b_removed_promoted_20260818`, arXiv:
2601.21447 extension) because it hurt performance specifically in 2022 and
2025-03.

That prior result does **not** automatically transfer to this paper's
claim, because the mechanisms are structurally different:
- The already-closed 00679B research used a **regime-switch** mechanism:
  the portfolio is either 100% golden1/growth exposure OR 100% defensive
  basket, never both simultaneously.
- This paper's mechanism is a **continuously-held, deviation-band-
  rebalanced fixed ratio**: both the leveraged-stock leg and the bond leg
  are always held, and the "rebalancing bonus" argument specifically
  depends on that continuous-holding structure, which the regime-switch
  tests never exercised.

Per `feedback_verify_every_paper_independently`, the paper's actual
mechanism was tested directly rather than assuming the prior (structurally
different) negative result applied.

**Gap identified before testing (not after)**: the paper's own backtest
window (1989-2020) does not include any period resembling 2022's
simultaneous stock-and-bond selloff -- the exact regime that broke bond
diversification in the already-closed 00679B research. This was flagged as
a specific, testable reason to expect the paper's claim might not survive
contact with a window that includes 2022, before any backtest was run.

## Implemented Files

Backtest script (research-only):

- `scripts/evaluate/backtest_letf_bond_deviation_band_rebalance_2103_10157.py`

Result artifact:

- `results/letf_bond_deviation_band_rebalance_2103_10157.json`

## Method

Standalone deviation-band rebalancing loop with real share-count tracking
(does not reuse `_simulate_costed_curve` from
`backtest_group_a_plus_defensive_basket.py`, since that function only
rebalances on regime-label change, a poor fit for a continuously-drifting
fixed-ratio portfolio). Uses dividend-adjusted total-return prices via
`_load_total_return_prices` (reused unmodified). Rebalances to target
whenever either leg's weight drifts beyond target +/-20% (relative,
matching the paper's own choice -- e.g. a 40% target triggers outside
[32%, 48%]). Standard cost assumptions used throughout this session's LETF
work: commission 0.1425%, slippage 0.05%, equity ETF sell tax 0.1%.

Tested 4 allocation configs: 00631L 40%/60% and 50%/50%, each against both
00679B (matching the paper's bond leg) and cash (matching GroupA+'s
already-adopted defensive-basket asset) as the second leg. Same 4 standard
windows used throughout this session's LETF guard work:

- `full_2020_2026`: 2020-01-02 to latest
- `rate_hike_2022_2023`: 2022-01-03 to 2023-12-29
- `live_2024_2026`: 2024-01-02 to latest
- `active_2025_2026`: 2025-01-02 to latest

Benchmarked against 100% 0050 buy-and-hold (the paper's own benchmark) and
100% 00631L buy-and-hold.

## Results

### full_2020_2026 (1612 rows)

| Portfolio | final_value | Sharpe | MDD |
|---|---|---|---|
| 0050 buy&hold (benchmark) | 5,265,954 | 1.245 | -0.3380 |
| 00631L buy&hold | 14,062,568 | 1.153 | -0.5514 |
| 00631L 40% / 00679B 60% | 3,233,068 | 1.034 | -0.3592 |
| 00631L 50% / 00679B 50% | 4,168,721 | 1.070 | -0.3923 |
| 00631L 40% / cash 60% | 3,902,535 | 1.272 | -0.2327 |
| 00631L 50% / cash 50% | 4,889,173 | 1.191 | -0.3054 |

No tested config beats 0050 buy-and-hold on final_value.

### rate_hike_2022_2023 (485 rows) -- the critical stress window

| Portfolio | final_value | Sharpe | MDD |
|---|---|---|---|
| 0050 buy&hold (benchmark) | 995,992 | 0.087 | -0.3380 |
| 00631L buy&hold | 1,029,745 | 0.221 | -0.5130 |
| 00631L 40% / 00679B 60% | 915,872 | **-0.183** | -0.3545 |
| 00631L 50% / 00679B 50% | 954,277 | **-0.032** | -0.3773 |
| 00631L 40% / cash 60% | 1,042,056 | 0.227 | -0.2295 |
| 00631L 50% / cash 50% | 1,065,417 | 0.278 | -0.2793 |

The bond-leg variants underperform 0050 on **both** Sharpe and MDD, with
Sharpe turning negative -- confirming the identified-before-testing
hypothesis. The cash-leg variants beat 0050 on all 3 metrics in this
window.

### live_2024_2026 (639 rows) and active_2025_2026 (397 rows)

Both bull-market windows: all 4 tested configs underperform 0050
buy-and-hold on both final_value and Sharpe (expected -- diluting a bull
run with any defensive leg costs upside). MDD is mixed/close to the
benchmark rather than clearly better.

## Conclusion

The paper's central claim -- that a fixed-ratio leveraged-stock + bond
portfolio, deviation-band rebalanced, beats 100% unleveraged stock on
**both** risk and reward simultaneously -- does not hold on Taiwan data:

1. The bond-leg (00679B) variant fails specifically in 2022, for the same
   underlying reason (stock-bond correlation breakdown) already documented
   in the closed 00679B regime-switch research -- this was hypothesized
   before testing, then confirmed, not discovered after the fact and
   rationalized.
2. The cash-leg variant does show a genuine 2022 improvement over 0050 on
   all 3 metrics, but loses clearly in both bull-market windows and in the
   full 2020-2026 window -- a standard risk/reward trade-off (protects
   downside, costs upside), not the paper's claimed "wins on both
   dimensions" result.
3. No tested configuration beats 0050 buy-and-hold on final_value across
   the full multi-year window.

## Production Impact

No production strategy files were changed.

Not changed:

- latest strategy manifest;
- `golden1_0531`;
- `a2118.py` or any runner;
- daily signal output;
- execution plan;
- target weights;
- order files.

All changes are a single new research/shadow script and its result
artifact.

## Final Recommendation

Do not promote any variant of this mechanism into GroupA+. The core
methodological lesson (already noted once from the 00679B research, now
independently reconfirmed via a structurally different mechanism on the
same underlying asset) is durable: **stock-bond anti-correlation cannot be
assumed stable across regimes for Taiwan's actual defensive-basket
candidates** -- any future paper proposing a bond-diversification mechanism
should first be checked against whether its own backtest window includes a
period resembling 2022's simultaneous stock-and-bond selloff, since that is
now the second time (once implicitly via 00679B, once explicitly via this
paper) that gap has been identified as the specific reason a plausible-
sounding mechanism failed on Taiwan data.

Not attempted / out of scope for this review:

- Margin-based leverage (the paper's own finding that 1.8x margin beats 2x
  LETF leverage) -- would require a structurally different execution
  mechanism (broker margin debt tracking) that does not exist anywhere in
  this codebase's infrastructure; not pursued given the scope of this
  single-paper review.
- Capital-gains-tax modeling -- the paper's tax treatment is Israeli-
  specific (25% flat CGT with FIFO/optimized-lot selection) and does not
  map onto Taiwan's actual securities-transaction-tax-based cost structure,
  which this codebase already models directly in its transaction-cost
  assumptions; not relevant to import.

No commit was made -- per standing instruction, commits are not suggested
or created unless the user explicitly asks.
