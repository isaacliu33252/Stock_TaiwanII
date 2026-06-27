# GroupA+ Architecture - 2026-06-19

## Purpose

This document is the concise architecture handoff for the GroupA+ research
pipeline. Detailed experiment history remains in:

- `report/group_a_plus/review/md/risk6_confirm_handoff_20260618.md`

The refactor follows a modular-monolith structure inspired by Fincept Terminal:
separate data, runner, governance, portfolio, and research-strategy contexts
while retaining root-level compatibility entry points.

## Package Layout

```text
group_a_plus/
  paths.py
  data/
    registry.py
    coverage.py
  runners/
    a207.py
  governance/
    catalog.py
    compare.py
  portfolio/
    cash_00751b.py
  strategies/
    news_anomaly.py
    options_overlay.py
    scaling_tail.py
    scaling_tail_ready.py
    abm_agents.py
    fingpt_sentiment_alignment.py
```

## Context Responsibilities

| Context | Responsibility | Must not do |
| --- | --- | --- |
| `data` | Inventory local datasets and validate requested-window coverage | Mutate or fetch market data |
| `runners` | Execute formal baseline strategies with standardized outputs | Promote a strategy automatically |
| `governance` | Catalog runners and evaluate promotion guardrails | Change the latest pointer |
| `portfolio` | Evaluate actual Excel holdings and replacement scenarios | Treat price-only returns as total returns |
| `strategies` | Expose research overlay module entry points | Imply smoke tests are formal promotion evidence |

## Compatibility Entry Points

| Root entry point | Module implementation |
| --- | --- |
| `group_a_plus_data_registry.py` | `group_a_plus.data.registry` |
| `group_a_plus_data_coverage_check.py` | `group_a_plus.data.coverage` |
| `group_a_plus_runner.py` | `group_a_plus.runners.a207` |
| `group_a_plus_runner_catalog.py` | `group_a_plus.governance.catalog` |
| `compare_group_a_plus_results.py` | `group_a_plus.governance.compare` |
| `evaluate_group_a_plus_plus_00751b_cash.py` | `group_a_plus.portfolio.cash_00751b` |

The strategy root scripts remain the implementation source. Their package
modules currently provide stable `python3 -m` entry points.

## Formal Promotion Guardrails

A candidate passes formal upgrade only when all conditions hold:

1. `candidate_final_value >= baseline_final_value`
2. `candidate_sharpe_ratio >= baseline_sharpe_ratio`
3. `candidate_max_drawdown >= baseline_max_drawdown`
4. `effective_override_days > 0`

Research watchlist allows final value down to 98% of baseline but keeps the
Sharpe, drawdown, and effective-override requirements.

No tool in this package changes:

- `report/group_a_plus/latest/switch_backtest.json`
- the formal latest pointer
- strategy weights in the source signal files

## Core Commands

```bash
python3 -m group_a_plus.data.registry \
  --output results/group_a_plus_data_registry_latest.json

python3 -m group_a_plus.data.coverage \
  --start 2025-01-02 --end 2026-06-18 \
  --output results/group_a_plus_data_coverage_latest.json

python3 -m group_a_plus.runners.a207 \
  --start 2025-01-02 --end 2026-06-18 \
  --output results/group_a_plus_runner_a207_latest.json \
  --frame-output results/group_a_plus_runner_a207_latest_frame.csv

python3 -m group_a_plus.governance.catalog \
  --start 2025-01-02 --end 2026-06-18 \
  --output results/group_a_plus_runner_catalog_latest.json

python3 -m group_a_plus.governance.compare \
  --baseline results/group_a_plus_runner_a207_latest.json \
  --candidates \
    results/group_a_plus_news_anomaly_2025_2026_20260619.json \
    results/group_a_plus_derivative_options_overlay_2025_2026_20260619.json \
    results/group_a_plus_scaling_tail_2025_2026_20260619.json \
    results/group_a_plus_abm_agents_2025_2026_focused_20260619.json \
  --output results/group_a_plus_compare_latest.json
```

## Refactor Status

| Step | Status | Scope |
| --- | --- | --- |
| 1 | Complete | Data registry and coverage |
| 2 | Complete | A20.7 runner |
| 3 | Complete | Catalog and comparator governance |
| 4 | Complete | Excel/portfolio 00751B versus cash |
| 5 | Complete | Strategy module entry points |
| 6 | Complete | Architecture and result report separation |

The runner catalog now contains fifteen entries. `scaling_tail_ready` is a
research-only candidate that:

- requires a positive Hill alpha;
- uses pre-window warmup data;
- can only override A20.7 while A20.7 is in `golden1`;
- does not change the formal latest pointer.

`fingpt_sentiment_alignment` adds a research-only text-risk layer that:

- aggregates 7/14/28-day financial sentiment and event concerns;
- uses news available through the prior calendar day;
- requires 0050 price confirmation and only overrides A20.7 in `golden1`;
- measures independent-source coverage over the actual trading window;
- blocks formal promotion unless at least two sources cover 50% of trading days.

`dynamic_exposure` adds a research-only position-sizing layer that:

- retains A20.7 full-defense signals as authoritative;
- blends Golden1 and defensive weights at 25%, 50%, 75%, and 100%;
- permits partial early defense only when price stress and risk score agree;
- restores exposure in steps, with faster recovery only under positive momentum
  and calm relative volatility;
- optionally requires a tail-risk score and consecutive warning days;
- records desired exposure and the daily exposure reason for auditability;
- uses the same close-to-close simulation convention as the A20.7 baseline.

`coverage_normalized` adds an A20.8 research candidate that:

- tracks per-feature source availability with maturity and staleness limits;
- divides observable risk flags by the number of observable features;
- falls back to the original A20.7 raw score when coverage is below a configured
  minimum;
- changes only entry risk confirmation; price entry, minimum hold, exit rules,
  and portfolio weights remain A20.7;
- emits available feature count, observable risk count, normalized ratio, and
  entry mode for every backtest day.

`warmup_consistency` adds an A20.9 methodology candidate that:

- computes A20.7 features and switch state before the requested evaluation
  start;
- trims prices, regimes, events, and performance only after feature generation;
- audits 180/365/540-calendar-day warmups for event stability;
- prevents the evaluation start date from changing MA75 and rolling-risk state.

Core source hygiene now bounds daily forward-fill to five trading days and
weekly TDCC forward-fill to ten trading days. TDCC changes are reset to zero
when consecutive observations are more than 21 calendar days apart, preventing
multi-year gaps from being interpreted as weekly changes.

`defensive_basket` adds an A21 execution-realism candidate that:

- freezes A20.7 warmup-aware regimes and changes only defensive weights;
- constructs ETF total returns from local close and dividend fields;
- charges configurable commission, slippage, and sell-side ETF tax;
- applies the statutory bond-ETF transaction-tax exemption to 00679B during the
  tested period;
- evaluates base cost, doubled execution cost, and one/three-day signal delay;
- disables external formal eligibility because old price-only baselines are not
  comparable to dividend- and cost-aware results.

The A21.1 refinement adds training-only stress-episode selection. Price stress
uses the unchanged A20.7 MA-gap/drawdown entry and price-recovery exit, without
the raw risk-score gate, to obtain more defensive-basket observations. Baskets
are ranked by worst episode return delta first, then median return delta, joint
wins, and median MDD delta. Validation data is never used for selection.

A21.2 adds a complete execution-latency matrix. Entry and exit delays are varied
independently from zero through three trading days. Validation and long-window
runs accept an explicit `--latency-basket` so the training-selected basket is
locked instead of being reselected on later data.

A21.3 adds a one-shot recovery ramp and a dedicated standardized runner. While
the A20.7 base regime remains defensive, the candidate returns from `cash30` to
the existing A20.7 defensive weights after MA75 gap reaches zero and five-day
momentum turns positive. It still waits for the unchanged A20.7 rule before
returning to Golden1. The runner is `group_a_plus.runners.a213`.

Schema-v2 activation uses `report/group_a_plus/latest/strategy.json` and the
allowlisted dispatcher `group_a_plus.runners.latest`. It activates A21.3 for
new consumers. `report/group_a_plus/latest/switch_backtest.json` remains
unchanged as an A20.7 compatibility pointer for legacy two-regime consumers.

`group_a_plus.operations.daily_signal` converts the active strategy into an
execution-guarded daily target. It validates aligned OHLCV, strategy-specific
source freshness, target weights, reference whole-share quantities, transition
date, and current features. The theoretical target remains visible when stale,
but `execution_allowed` is false. Its managed pointer is
`report/group_a_plus/latest/live_signal.json`.

`group_a_plus.operations.execution_plan` parses only the `Group A++` workbook
section, values current holdings, calculates cost-aware trade deltas, treats
00679B/00751B as bond ETFs for sell-tax purposes, and blocks automatic execution
for missing prices, stale signals, negative cash, or turnover above 50%. Its
pointer is `report/group_a_plus/latest/execution_plan.json`.

## Next Technical Work

The next code refactor should be small and test-driven:

1. Add `group_a_plus/strategies/common.py` only for genuinely shared loading,
   output-path, and report-writing behavior.
2. Keep strategy-specific feature construction and regime rules in their
   original modules.
3. Compare output JSON and best-frame curves before and after each extraction.
