# HANDOFF - 2510.14985v1 DeepAries Adaptive Interval for GroupA+

Date: 2026-08-14  
PDF: `C:\Users\isaac\Downloads\2510.14985v1.pdf`  
Paper: `DeepAries: Adaptive Rebalancing Interval Selection for Enhanced Portfolio Selection`  
Venue: CIKM 2025  
arXiv: `2510.14985v1`  

## Status

Reviewed and shadow-tested for GroupA+ latest strategy relevance.

No live strategy change was made.

- `golden1_0531`: unchanged
- GroupA+ latest strategy: unchanged
- A21.18/a2118 decision rule: unchanged
- live signal: unchanged
- execution plan: unchanged
- orders: unchanged

Decision: do not import into GroupA+ latest strategy yet. Keep as
research-only / shadow candidate.

## Paper Summary

DeepAries is a deep reinforcement learning portfolio-management framework
that jointly decides:

- when to rebalance, as a discrete interval action;
- how to allocate, as a continuous portfolio-weight action.

Core model:

- Transformer/iTransformer-style state encoder;
- PPO policy optimization;
- interval action space such as `{1, 5, 20}` days;
- continuous long-only portfolio allocation;
- transaction costs based on turnover from current evolved weights to target
  weights;
- reward shaping that gives a bonus when the selected interval matches the
  ex-post best interval.

The paper's strongest importable idea for GroupA+ is not the full PPO model.
It is the operational idea that the strategy should not necessarily act on
every daily target update when the market state is stable.

Paper experimental highlights:

- DeepAries outperforms baselines across DJ 30, FTSE 100, KOSPI, and CSI 300
  in most reported metrics.
- Adaptive interval selection beats fixed daily rebalancing across the tested
  markets.
- Fixed monthly rebalancing is a surprisingly strong baseline in several
  markets.
- Higher transaction costs hurt fixed daily rebalancing more than adaptive
  rebalancing.

## GroupA+ Applicability

High-risk parts not imported:

- no PPO training;
- no iTransformer model;
- no continuous allocation head;
- no reward shaping using ex-post best interval;
- no replacement of golden1/a2118 target weights.

Lower-risk idea tested:

- keep a2118's own daily target weights unchanged;
- decide how often to act on those daily outputs;
- compare daily review against fixed 5-day, fixed 20-day, and adaptive
  `{1,5,20}` review intervals;
- freeze last-reviewed target weights between review dates.

This directly matches the paper's practical cost-control thesis while avoiding
a new opaque live RL model.

## What Was Added

New research-only evaluator:

- `scripts/evaluate/evaluate_2510_14985_deeparies_interval_shadow.py`

It imports existing GroupA+/a2118 simulation utilities and tests:

- `fixed_5d`;
- `fixed_20d`;
- `deeparies_lite_adaptive_1_5_20`.

DeepAries-lite adaptive rule:

- daily review (`1d`) when risk is crash-like, near a switch threshold, in
  recovery, or total risk is high;
- weekly review (`5d`) when already defensive but not at a daily-action
  threshold;
- monthly review (`20d`) when stable golden1.

This is a causal heuristic, not trained PPO.

## Commands Run

Syntax check:

```bash
.venv/bin/python -m py_compile \
  scripts/evaluate/evaluate_2510_14985_deeparies_interval_shadow.py
```

Default multi-window shadow:

```bash
.venv/bin/python scripts/evaluate/evaluate_2510_14985_deeparies_interval_shadow.py \
  --output-json results/2510_14985_deeparies_interval_shadow_default.json \
  --output-md report/group_a_plus/latest/2510_14985_deeparies_interval_shadow_default.md
```

Output files:

- `results/2510_14985_deeparies_interval_shadow_default.json`
- `report/group_a_plus/latest/2510_14985_deeparies_interval_shadow_default.md`

## Results

Summary by method:

| Method | Pass windows | Total final delta | Total cost delta | Total turnover delta |
|---|---:|---:|---:|---:|
| `deeparies_lite_adaptive_1_5_20` | 4/6 | +189,913 | -20,444 | -9,135,817 |
| `fixed_20d` | 2/6 | -126,578 | -24,841 | -11,138,097 |
| `fixed_5d` | 2/6 | -93,579 | -7,280 | -3,014,792 |

Window detail for adaptive `{1,5,20}`:

| Window | Final delta | Sharpe delta | MDD delta | Cost delta | Turnover delta | Pass |
|---|---:|---:|---:|---:|---:|---:|
| live 2024-2026 | +104,146 | +0.0298 | +0.0000 | -7,893 | -3,444,570 | true |
| active 2025-2026 | +39,581 | -0.0350 | -0.0160 | -6,270 | -2,737,164 | false |
| 2020 COVID | +17,469 | +0.0954 | +0.0076 | -1,984 | -934,025 | true |
| 2021 May correction | +33,199 | +0.2673 | +0.0067 | -4,252 | -2,002,565 | true |
| 2022 rate hike | -4,482 | +0.0999 | -0.0044 | -45 | -17,493 | false |
| 2024 Aug unwind | +0 | +0.0000 | +0.0000 | +0 | +0 | true |

Interpretation:

- The interval idea is useful: adaptive `{1,5,20}` reduced both cost and
  turnover materially and improved aggregate final value.
- It is not production-ready because it fails `active_2025_2026` on Sharpe
  and drawdown, and fails `2022_rate_hike` on final value and drawdown.
- Fixed weekly/monthly intervals reduce costs but hurt total performance more
  often than the adaptive rule.
- The result is stronger than the older 1/3/5 adaptive-review shadow, but not
  enough for automatic promotion.

## Import Decision

Do not import into GroupA+ latest strategy now.

Reasons:

- multi-window gate is mixed (`4/6`, not all windows);
- 2022 rate-hike window still shows downside from stale/frozen weights;
- active 2025-2026 has better final value but worse Sharpe and drawdown;
- full DeepAries would require training/validating a new PPO+iTransformer
  stack, which is a larger model-risk surface than justified by current
  evidence;
- GroupA+ already has execution guards, turnover caps, staged buys, and
  adaptive review shadow logging, so live integration must prove incremental
  benefit over those controls.

Recommended use:

- keep as research-only candidate;
- continue daily shadow logging of `NEXT_REVIEW_1D/5D/20D`;
- evaluate whether a 2022-specific choppy-market detector can prevent stale
  weights before any promotion;
- do not change target weights or orders.

## What Can Be Borrowed

Safe concepts:

- expose review interval as an explicit action/diagnostic;
- compare daily vs weekly vs monthly review before accepting new strategy
  changes;
- report turnover and transaction-cost deltas next to final value and Sharpe;
- treat monthly review as a serious baseline in stable regimes;
- require daily review near regime-switch thresholds.

Not recommended:

- importing PPO/iTransformer allocation head directly;
- using ex-post best interval reward shaping in live production;
- replacing a2118/golden1 weights;
- freezing targets for up to 20 days without a choppy-market fail-safe;
- using aggregate positive final delta alone as promotion evidence.

## Current State

Files produced:

- `scripts/evaluate/evaluate_2510_14985_deeparies_interval_shadow.py`
- `results/2510_14985_deeparies_interval_shadow_default.json`
- `report/group_a_plus/latest/2510_14985_deeparies_interval_shadow_default.md`
- `results/2510_14985_deeparies_interval_shadow_choppy.json`
- `report/group_a_plus/latest/2510_14985_deeparies_interval_shadow_choppy.md`

## Continued Choppy Fail-Safe Test

Follow-up after the first DeepAries-lite result: tested whether a simple
choppy-market fail-safe can fix stale-weight losses.

Implementation:

- added `deeparies_lite_adaptive_choppy_1_5_20` to
  `scripts/evaluate/evaluate_2510_14985_deeparies_interval_shadow.py`;
- if recent regime flips in a 20-trading-day window exceed the threshold, the
  interval is forced back to daily review;
- original `deeparies_lite_adaptive_1_5_20` is left unchanged for comparison.

Command:

```bash
.venv/bin/python scripts/evaluate/evaluate_2510_14985_deeparies_interval_shadow.py \
  --output-json results/2510_14985_deeparies_interval_shadow_choppy.json \
  --output-md report/group_a_plus/latest/2510_14985_deeparies_interval_shadow_choppy.md
```

New outputs:

- `results/2510_14985_deeparies_interval_shadow_choppy.json`
- `report/group_a_plus/latest/2510_14985_deeparies_interval_shadow_choppy.md`

Choppy fail-safe result:

| Method | Pass windows | Total final delta | Total cost delta | Total turnover delta |
|---|---:|---:|---:|---:|
| original adaptive `{1,5,20}` | 4/6 | +189,913 | -20,444 | -9,135,817 |
| choppy fail-safe adaptive `{1,5,20}` | 3/6 | -27,273 | -2,396 | -1,111,863 |
| fixed 20d | 2/6 | -126,578 | -24,841 | -11,138,097 |
| fixed 5d | 2/6 | -93,579 | -7,280 | -3,014,792 |

Interpretation:

- the simple choppy fail-safe is not an improvement;
- it overreacts in `2021_may_correction` and `active_2025_2026`, pulling too
  many days back toward daily review and losing the original adaptive edge;
- it does not repair `2022_rate_hike`;
- the best current shadow remains the original adaptive `{1,5,20}`, but it is
  still not production-ready.

Decision update:

- do not promote either adaptive interval variant;
- do not add the simple regime-flip fail-safe to live logic;
- future work should test a more specific stale-weight detector rather than
  treating raw regime flip count as sufficient.

Production pointer check to run after this handoff:

```bash
git diff -- \
  report/group_a_plus/latest/strategy.json \
  report/group_a_plus/latest/live_signal.json \
  report/group_a_plus/latest/execution_plan.json
```

Expected output: no diff.

## Parameter Tuning Follow-Up

Follow-up question: can the interval heuristic be lightly tuned?

Answer: yes, but only as a research/shadow parameter study. The tuned rule
must not be imported into latest/golden1 until it proves incremental benefit
without merely falling back to daily review in difficult windows.

The evaluator was parameterized with:

- `--crash-dd-buffer`
- `--tail-risk-score-min`
- `--total-risk-score-min`
- `--near-ma-gap-buffer`
- `--near-dd-buffer`
- `--defensive-interval`
- `--stable-golden-interval`

Syntax check after parameterization:

```bash
.venv/bin/python -m py_compile \
  scripts/evaluate/evaluate_2510_14985_deeparies_interval_shadow.py
```

Tuning runs:

```bash
.venv/bin/python scripts/evaluate/evaluate_2510_14985_deeparies_interval_shadow.py \
  --output-json results/2510_14985_deeparies_interval_shadow_tuned_original.json \
  --output-md report/group_a_plus/latest/2510_14985_deeparies_interval_shadow_tuned_original.md
```

```bash
.venv/bin/python scripts/evaluate/evaluate_2510_14985_deeparies_interval_shadow.py \
  --stable-golden-interval 10 \
  --output-json results/2510_14985_deeparies_interval_shadow_tuned_stable10.json \
  --output-md report/group_a_plus/latest/2510_14985_deeparies_interval_shadow_tuned_stable10.md
```

```bash
.venv/bin/python scripts/evaluate/evaluate_2510_14985_deeparies_interval_shadow.py \
  --crash-dd-buffer 0.05 \
  --tail-risk-score-min 4 \
  --total-risk-score-min 6 \
  --near-ma-gap-buffer 0.02 \
  --near-dd-buffer 0.07 \
  --output-json results/2510_14985_deeparies_interval_shadow_tuned_conservative_daily.json \
  --output-md report/group_a_plus/latest/2510_14985_deeparies_interval_shadow_tuned_conservative_daily.md
```

```bash
.venv/bin/python scripts/evaluate/evaluate_2510_14985_deeparies_interval_shadow.py \
  --crash-dd-buffer 0.05 \
  --tail-risk-score-min 4 \
  --total-risk-score-min 6 \
  --near-ma-gap-buffer 0.02 \
  --near-dd-buffer 0.07 \
  --window holdout_2023:2023-01-03:2023-12-29:holdout \
  --window holdout_2026:2026-01-02:latest:holdout \
  --window holdout_2022_full:2022-01-03:2022-12-30:holdout \
  --output-json results/2510_14985_deeparies_interval_shadow_tuned_conservative_holdout.json \
  --output-md report/group_a_plus/latest/2510_14985_deeparies_interval_shadow_tuned_conservative_holdout.md
```

Tuning summary:

| Run | Key params | Pass windows | Total final delta | Total cost delta | Total turnover delta | Interpretation |
|---|---|---:|---:|---:|---:|---|
| original defaults | crash `0.03`, tail `5`, total `8`, MA `0.015`, DD `0.05`, stable `20d` | 4/6 | +189,913 | -20,444 | -9,135,817 | highest aggregate gain, but fails 2025 and 2022 gates |
| stable 10d | stable golden interval `10d` | 5/6 | +20,292 | -1,944 | -915,915 | safer, but much less upside |
| conservative daily trigger | crash `0.05`, tail `4`, total `6`, MA `0.02`, DD `0.07`, stable `20d` | 6/6 | +38,234 | -8,236 | -3,763,781 | best constrained base pass, but partly by reverting to daily |
| conservative holdout | same conservative params, holdout only | 3/3 | +0 | +0 | +0 | passes by becoming equivalent to daily baseline in hard windows |

Conservative tuned parameter set:

```text
crash_dd_buffer = 0.05
tail_risk_score_min = 4.0
total_risk_score_min = 6.0
near_ma_gap_buffer = 0.02
near_dd_buffer = 0.07
defensive_interval = 5
stable_golden_interval = 20
```

Important caveat:

- the conservative version is safer than defaults under the current gates;
- however, several passed windows have exactly zero delta versus daily review;
- this means the rule often avoids harm by falling back to daily review rather
  than creating durable interval-selection edge;
- therefore it is not enough evidence for production import.

Updated decision:

- keep the conservative parameter set as the preferred shadow candidate;
- do not change GroupA+ latest strategy, golden1_0531, a2118 decision logic,
  live signal, execution plan, or orders;
- require a future incremental gate that separates "reduced cost with same
  outcome" from "identical to daily because the rule fired daily almost
  everywhere";
- if implemented later, it should first appear only as advisory metadata such
  as `suggested_review_interval_days`, not as a live execution throttle.

Additional files produced by tuning:

- `results/2510_14985_deeparies_interval_shadow_tuned_original.json`
- `report/group_a_plus/latest/2510_14985_deeparies_interval_shadow_tuned_original.md`
- `results/2510_14985_deeparies_interval_shadow_tuned_stable10.json`
- `report/group_a_plus/latest/2510_14985_deeparies_interval_shadow_tuned_stable10.md`
- `results/2510_14985_deeparies_interval_shadow_tuned_conservative_daily.json`
- `report/group_a_plus/latest/2510_14985_deeparies_interval_shadow_tuned_conservative_daily.md`
- `results/2510_14985_deeparies_interval_shadow_tuned_conservative_holdout.json`
- `report/group_a_plus/latest/2510_14985_deeparies_interval_shadow_tuned_conservative_holdout.md`

## Next-Step Strict Nontrivial Gate

The next step was to prevent a misleading pass when the adaptive interval is
effectively identical to daily review.

Evaluator update:

- added `legacy_gate_promotion_ready`;
- kept `promotion_ready` for a stricter nontrivial gate;
- added `nonzero_delta_windows` by method;
- added `strict_nontrivial_ready` by method;
- default strict thresholds:
  - total cost saving at least `1000`;
  - total turnover reduction at least `100000`;
  - at least `2` windows with nonzero deltas.

Strict-gate commands:

```bash
.venv/bin/python scripts/evaluate/evaluate_2510_14985_deeparies_interval_shadow.py \
  --crash-dd-buffer 0.05 \
  --tail-risk-score-min 4 \
  --total-risk-score-min 6 \
  --near-ma-gap-buffer 0.02 \
  --near-dd-buffer 0.07 \
  --output-json results/2510_14985_deeparies_interval_shadow_strict_gate_conservative_daily.json \
  --output-md report/group_a_plus/latest/2510_14985_deeparies_interval_shadow_strict_gate_conservative_daily.md
```

```bash
.venv/bin/python scripts/evaluate/evaluate_2510_14985_deeparies_interval_shadow.py \
  --crash-dd-buffer 0.05 \
  --tail-risk-score-min 4 \
  --total-risk-score-min 6 \
  --near-ma-gap-buffer 0.02 \
  --near-dd-buffer 0.07 \
  --window holdout_2023:2023-01-03:2023-12-29:holdout \
  --window holdout_2026:2026-01-02:latest:holdout \
  --window holdout_2022_full:2022-01-03:2022-12-30:holdout \
  --output-json results/2510_14985_deeparies_interval_shadow_strict_gate_conservative_holdout.json \
  --output-md report/group_a_plus/latest/2510_14985_deeparies_interval_shadow_strict_gate_conservative_holdout.md
```

Strict-gate results:

| Split | Legacy all-window no-worse gate | Strict promotion ready | Nonzero windows | Total final delta | Total cost delta | Total turnover delta |
|---|---:|---:|---:|---:|---:|---:|
| base conservative daily | true | true | 2/6 | +38,234 | -8,236 | -3,763,781 |
| conservative holdout | true | false | 0/3 | +0 | +0 | +0 |

Interpretation:

- the base split passes the stricter nontrivial gate;
- the holdout split fails because the adaptive method has zero nontrivial
  effect versus daily review;
- therefore the combined research decision remains not production-ready.

Updated final decision for this paper:

- do not import DeepAries interval throttling into GroupA+ latest strategy;
- keep only the strict-gate evaluator and reports for future monitoring;
- any future live change must pass both base and holdout strict gates, not just
  the legacy no-worse gate.

Additional strict-gate files:

- `results/2510_14985_deeparies_interval_shadow_strict_gate_conservative_daily.json`
- `report/group_a_plus/latest/2510_14985_deeparies_interval_shadow_strict_gate_conservative_daily.md`
- `results/2510_14985_deeparies_interval_shadow_strict_gate_conservative_holdout.json`
- `report/group_a_plus/latest/2510_14985_deeparies_interval_shadow_strict_gate_conservative_holdout.md`
