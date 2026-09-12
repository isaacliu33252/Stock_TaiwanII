# HANDOFF - 2603.01157v2 BAWS Extended Experiments for GroupA+

Date: 2026-08-14  
Scope: follow-up to user question "這篇論文的實驗都做完了? 繼續做完?"

## Status

Completed the remaining GroupA+-relevant BAWS experiments that can affect a
promotion decision.

No live strategy change was made.

- `golden1_0531`: unchanged
- GroupA+ latest strategy: unchanged
- `report/group_a_plus/latest/strategy.json`: unchanged
- `report/group_a_plus/latest/live_signal.json`: unchanged
- `report/group_a_plus/latest/execution_plan.json`: unchanged
- order/execution files: unchanged

Final decision: keep BAWS research-only. Do not promote to latest strategy or
execution guard.

## What was added

New extended evaluator:

- `scripts/evaluate/evaluate_group_a_plus_baws_extended_experiments.py`

Performance fix to existing BAWS-lite evaluator:

- `scripts/evaluate/evaluate_group_a_plus_baws_lite_var_es_shadow.py`
  - vectorized moving-block bootstrap threshold calculation
  - method logic unchanged
  - tests still pass

## Experiments Completed

The previous BAWS-lite work already tested VaR quantile-score performance
against fixed windows across GroupA+ ETFs.

This follow-up added:

1. Paper-grade bootstrap sample count
   - `B=1000`
   - `beta=0.90`

2. FZ-style joint VaR/ES score diagnostic
   - lower score is better
   - diagnostic only, not used for live trading

3. SAWS-like deterministic-threshold comparator
   - not exact paper SAWS, but a stability-style fixed-threshold comparator
   - labelled `saws_lite_deterministic_threshold`

4. Portfolio replay
   - previous-day BAWS warning shifts next-day golden1 `00631L` sleeve into
     `0050`
   - costed replay through existing GroupA+ backtest engine
   - research-only proxy, no live execution impact

## Commands Run

```bash
.venv/bin/python -m py_compile scripts/evaluate/evaluate_group_a_plus_baws_lite_var_es_shadow.py scripts/evaluate/evaluate_group_a_plus_baws_extended_experiments.py

.venv/bin/python -m pytest tests/test_evaluate_group_a_plus_baws_lite_var_es_shadow.py -q

.venv/bin/python scripts/evaluate/evaluate_group_a_plus_baws_extended_experiments.py \
  --start 2020-01-02 --end 2020-12-31 \
  --candidate-windows 20,40,63,126 \
  --evaluation-window 40 \
  --betas 0.90 --bootstrap-samples-grid 1000 \
  --output-json results/group_a_plus_baws_extended_experiments_2020_covid_b1000.json \
  --output-csv results/group_a_plus_baws_extended_portfolio_curve_2020_covid_b1000.csv \
  --output-md report/group_a_plus/latest/baws_extended_experiments_2020_covid_b1000.md

.venv/bin/python scripts/evaluate/evaluate_group_a_plus_baws_extended_experiments.py \
  --start 2022-01-03 --end 2022-12-30 \
  --candidate-windows 20,40,63,126,252 \
  --evaluation-window 40 \
  --betas 0.90 --bootstrap-samples-grid 1000 \
  --output-json results/group_a_plus_baws_extended_experiments_2022_rate_hike_b1000.json \
  --output-csv results/group_a_plus_baws_extended_portfolio_curve_2022_rate_hike_b1000.csv \
  --output-md report/group_a_plus/latest/baws_extended_experiments_2022_rate_hike_b1000.md

.venv/bin/python scripts/evaluate/evaluate_group_a_plus_baws_extended_experiments.py \
  --start 2024-01-02 --end 2026-08-13 \
  --candidate-windows 63,126,252,504 \
  --evaluation-window 63 \
  --betas 0.90 --bootstrap-samples-grid 1000 \
  --output-json results/group_a_plus_baws_extended_experiments_2024_2026_b1000.json \
  --output-csv results/group_a_plus_baws_extended_portfolio_curve_2024_2026_b1000.csv \
  --output-md report/group_a_plus/latest/baws_extended_experiments_2024_2026_b1000.md

.venv/bin/python scripts/evaluate/evaluate_group_a_plus_baws_extended_experiments.py \
  --start 2025-01-02 --end 2026-08-13 \
  --candidate-windows 63,126,252,504 \
  --evaluation-window 63 \
  --betas 0.90 --bootstrap-samples-grid 1000 \
  --output-json results/group_a_plus_baws_extended_experiments_2025_2026_b1000.json \
  --output-csv results/group_a_plus_baws_extended_portfolio_curve_2025_2026_b1000.csv \
  --output-md report/group_a_plus/latest/baws_extended_experiments_2025_2026_b1000.md
```

## Results

| Window | BAWS quantile wins | BAWS FZ-style wins | SAWS-like wins | Portfolio guard days | Portfolio final value delta | Promotion ready |
|---|---:|---:|---:|---:|---:|---:|
| 2020 COVID | 0/4 | 0/4 | 0/4 | 7 | -20,102 | false |
| 2022 rate hike | 0/4 | 0/4 | 1/4 | 2 | +2,160 | false |
| 2024-2026 | 0/4 | 0/4 | 1/4 | 34 | -199,776 | false |
| 2025-2026 latest | 0/4 | 0/4 | 0/4 | 20 | -125,421 | false |

Key interpretation:

- BAWS did not beat the best fixed window on VaR quantile score in any tested
  GroupA+ ETF/window.
- BAWS did not beat the best fixed window on FZ-style joint VaR/ES score in
  any tested GroupA+ ETF/window.
- The SAWS-like comparator occasionally beat fixed windows for one ticker, but
  this did not translate into a BAWS promotion case.
- Portfolio replay is not robust: one narrow 2022 window is mildly positive,
  while 2020, 2024-2026, and 2025-2026 are negative after costs.

## What Is Still Not a Full Paper Replication

The following are not needed for the GroupA+ promotion decision and were not
fully replicated:

- the paper's discrete structural-break simulation suite;
- the paper's GARCH/time-varying-volatility simulation suite;
- the paper's full S&P 500 empirical study;
- exact SAWS implementation from the cited SAWS paper;
- full theoretical asymptotic validation.

For GroupA+ decision-making, the relevant question is whether BAWS improves
GroupA+ ETF risk forecasts and portfolio outcomes. That question has now been
tested more directly than a generic paper replication would, and the answer is
negative.

## Decision

Do not import BAWS into GroupA+ latest strategy.

Keep only as research-only diagnostic:

- no target-weight effect;
- no live signal effect;
- no execution guard effect;
- no automatic `00631L` block.

Promotion gate would require all of the following, none of which is currently
true:

- BAWS beats best fixed windows on most GroupA+ ETFs;
- BAWS improves FZ-style VaR/ES score;
- BAWS warning/replay improves final value or drawdown robustly across
  multiple market windows after costs;
- no conflict with existing tail conformal / NCF / compounding guards.

