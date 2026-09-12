# Handoff: 2604.08356 Minimum Regime Performance (MRP) Strategy-Decay Diagnostic for GroupA+ (2026-08-31)

## Scope

- Source PDF: `C:\Users\isaac\Downloads\2604.08356.pdf`
- Paper: "Measuring Strategy-Decay Risk: Minimum Regime Performance and the
  Durability of Systematic Investing" (Nolan Alexander & Frank J. Fabozzi)
- Target: GroupA+ production switch policy (`switch_ma80_dd11`,
  `switch_risk_ma80_dd11_total6_hold5_eg015_xg015`), 2026-08-31 review
- Import type: research diagnostic / governance monitor

Confirmed via full-text search across `docs/`, root `*.md`, the research
semantic registry, and every memory file that this paper had never been
reviewed before this session (see `project_2604_08356...` memory entry for
how it was found among 9 unreviewed PDFs in Downloads).

## What the Paper Proposes

- **MRP1** (Eq. 1-2): split a return series once at the point `t` that
  minimizes `min(Sharpe(x[0:t]), Sharpe(x[t:]))`, subject to both segments
  being at least `d` observations long. MRP1 is that minimum -- the
  strategy's worst realized risk-adjusted performance across the weakest
  historical regime.
- Framed as "expected shortfall of model efficacy": a lower bound on
  robustness, not a forecast.
- Diagnostic and governance use only: recompute periodically; a declining
  MRP trajectory is an early-warning signal for review. The paper explicitly
  says MRP is nonlinear and not suited as a formal portfolio-optimizer
  constraint -- heuristic/monitoring use only.
- **Appendix A caveat (important):** MRP1 is a biased, *inconsistent*
  estimator. As the number of valid split points `n_s` grows (i.e. `d`
  shrinks relative to sample length), MRP1 provably diverges toward `-inf`
  even for a stationary process -- an artifact of searching over more
  candidate splits, not real fragility. The paper's own mitigation is a
  sensitivity check across multiple `d` values and trusting the *ranking*,
  not one raw number.

## Why This Is a Different Import Class Than Prior Regime-Detection Papers

Unlike CHASM / CHMM / EMVRS / VLSTAR (all closed_negative as *switch
triggers* -- see memory), MRP1 is not proposed as a live signal. It is a
retrospective robustness statistic computed on an *existing* equity curve,
exactly the same category as `ops_health` / `strategy_trust_gate`. This
lines up with `feedback_strategy_promotion_caution` (high Sharpe != better)
and is, in effect, a formalized generalization of the ad hoc stress-window
audits already built today for 2606.26625
(`2606_26625_cvar_cost_window_split.json`) -- MRP1 replaces "pick 5 named
historical windows" with "exhaustively search for the single worst split."

## Implementation

- `scripts/evaluate/evaluate_group_a_plus_2604_08356_mrp_strategy_decay.py`
- `tests/test_evaluate_group_a_plus_2604_08356_mrp_strategy_decay.py`
- `report/group_a_plus/latest/2604_08356_mrp_strategy_decay.json`
- `report/group_a_plus/latest/2604_08356_mrp_strategy_decay.md`

Method: loads the production switch-policy equity curve
(`results/whatif_four_axis_switch_backtest_20260819_curve.csv`, 2020-01-02 to
2026-08-18, the same curve `report/group_a_plus/latest/switch_backtest.json`
already names as `recommended`), computes MRP1 at `d = 1` and `d = 2` years
for three series: the production switch policy, golden1_0531 alone, and the
defensive basket alone.

Validation: `.venv/bin/python -m pytest
tests/test_evaluate_group_a_plus_2604_08356_mrp_strategy_decay.py` -- `4
passed`. Tests cover: MRP1 correctly finds a worse-than-full-sample split on
a synthetic two-regime series; a short/coarse series stays close to
full-sample Sharpe; infeasible when the series is shorter than `2*d`; and a
direct reproduction of the Appendix A inconsistency claim (more valid splits
pushes MRP1 lower for the identical stationary process).

## Result (2026-08-31, `as_of = 2026-08-18`)

| strategy | full-sample Sharpe | MRP1 (d=1y) | MRP1 (d=2y) | MRP/Sharpe | worst-regime split |
|---|---:|---:|---:|---:|---|
| `switch_ma80_dd11` (production) | 1.159 | 0.307 | 0.307 | 0.265 | 2022-10-26 |
| `golden1_0531` (static baseline) | 1.115 | 0.217 | 0.217 | 0.195 | 2022-10-26 |
| defensive basket alone | 1.112 | 0.155 | 0.155 | 0.140 | 2022-10-26 |

All three series pick the same worst-regime split (2022-10-26, separating
the COVID-crash-through-2022-bear left segment from the 2023-2026 bull-run
right segment) -- expected, since golden1 and defensive share the same
underlying 0050/00631L/00632R price history that the switch policy overlays.

**The production switch policy strictly dominates both static baselines on
the paper's own decay-risk frontier: higher full-sample Sharpe AND higher
MRP1 than either golden1_0531 alone or the defensive basket alone.** This is
a genuinely positive, non-trivial confirmation using a different, principled
method than anything used to validate the switch policy before: it isn't
just delivering a better average Sharpe, it is also more robust in its own
worst historical regime than the assets it switches between.

`d=1y` and `d=2y` give identical results here because the 6.7-year curve is
short enough that both settings land on the same split point with enough
data on each side -- this dataset is too short to meaningfully exercise the
Appendix A inconsistency warning (would need a much finer `d`, e.g. quarters,
which was intentionally not tested to avoid manufacturing a spurious low
number, consistent with the paper's own guidance not to over-tune `d`).

## Side Finding (Not In Scope, Flagged For Future Cleanup)

While locating a longer equity curve to test wider `d` values, found that
`results/group_a_plus_switch_policy_backtest_longhist_rebalmonthly_20150401_20260810_curve.csv`
(2017-2026, 2325 rows) has a `switch_risk_ma80_dd11_total6_hold5_eg015_xg015`
column that is byte-identical to its `golden1_0531_1m` column for the entire
history (`max abs diff = 0.0`) -- i.e. the "switch" column in that specific
report file never actually switched, unlike the real production policy
(confirmed 14 real switch events since 2020 in
`report/group_a_plus/latest/switch_backtest.json`). This looks like a stale
or mis-generated artifact, not a live-strategy bug -- the real production
backtest (`whatif_four_axis_switch_backtest_20260819_curve.csv`, used above)
does switch correctly. Not investigated further this session; flagged so a
future session does not accidentally use that longhist file for a
switch-vs-golden1 comparison.

## Decision

- Adopt MRP1 as a **periodic shadow governance diagnostic**, not a live
  signal. It does not change target weights, create orders, or trigger
  rebalance.
- This run is a one-time confirmation, intentionally **not wired into the
  daily pipeline** yet -- unlike the 2606.26625 gates, there is no immediate
  actionable threshold here (no "block X" decision), just a robustness
  statistic. If it proves useful to track over time (e.g. recomputed monthly
  to watch for a declining MRP1 trend), wiring it into
  `research_shadow_decision_snapshot` alongside `ops_health` would be the
  natural next step -- deferred until there is a second data point to show a
  trend.
- Does not change `a2118_a2111_ncf_late_bull_deleverage`, target weights, or
  any live execution gate.
