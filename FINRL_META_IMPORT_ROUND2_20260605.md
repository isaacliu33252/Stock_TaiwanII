# FinRL-Meta Import Round 2 2026-06-05

## Scope

Implemented requested items:

1. HTML strategy report
2. Extended metrics: Sortino, Calmar, rolling Sharpe, average daily cost
3. Validation-window A/B selector
4. Quantile-based stress gate

## Added / Modified

- Added `generate_strategy_html_report.py`
- Updated `finrl_meta_strategy_governance.py`
- Updated `backtest_group_ab_meta_governed.py`

## Outputs

- HTML report:
  - `results/group_ab_meta_governed_hold10_no2884_20240102_20260604.html`
- Updated summary:
  - `results/group_ab_meta_governed_hold10_no2884_20240102_20260604.json`
  - `results/group_ab_meta_governed_hold10_no2884_20240102_20260604.csv`
- Selector choices:
  - `results/group_ab_meta_governed_hold10_no2884_20240102_20260604_selector_choices.csv`

## Results

Window: 2024-01-02 to 2026-06-04.

| Variant | Final | Sharpe | Sortino | Calmar | Max DD | Cost |
|---|---:|---:|---:|---:|---:|---:|
| dynamic lb126 band0.08 no-stress | 5,885,722 | 2.5780 | 3.2795 | 2.9564 | -19.01% | 1,866 |
| validation selector 126D quarterly | 5,885,722 | 2.5780 | 3.2795 | 2.9564 | -19.01% | 1,866 |
| dynamic lb126 band0.08 quantile stress | 5,757,952 | 2.5626 | 3.2137 | 2.8822 | -19.01% | 3,792 |
| dynamic lb126 band0.08 fixed stress | 5,757,952 | 2.5626 | 3.2137 | 2.8822 | -19.01% | 3,792 |
| dynamic lb126 band0.03 fixed stress | 5,732,655 | 2.5573 | 3.2005 | 2.8674 | -19.01% | 4,226 |
| strict cost/stress | 5,667,924 | 2.5182 | 3.1315 | 2.8380 | -18.95% | 5,895 |

## Selector Behavior

The selector evaluates candidates every quarter using trailing 126-day Sharpe.

Choices:

| Date | Chosen |
|---|---|
| 2024-01-02 | quantile stress |
| 2024-04-01 | quantile stress |
| 2024-07-01 | quantile stress |
| 2024-10-01 | quantile stress |
| 2025-01-02 | quantile stress |
| 2025-04-01 | quantile stress |
| 2025-07-01 | quantile stress |
| 2025-10-01 | quantile stress |
| 2026-01-02 | band0.03 fixed stress |
| 2026-04-01 | no-stress |

Even though the selector changed candidates, the practical execution result matched the no-stress governed variant in this run.

## Interpretation

- The HTML report and extended metrics are clear improvements and should stay.
- Validation-window selector is useful for future regime changes, but it did not improve 2024-2026 beyond no-stress.
- Quantile stress gate behaved the same as fixed stress on this window.
- Current best remains:

`dynamic_lb126_band008_hold10_no2884_no_stress`

This is still the best live default among the tested governed variants.

Stress/quantile/selector should remain available as monitored alternatives, especially for 2008-like or future crash regimes.
