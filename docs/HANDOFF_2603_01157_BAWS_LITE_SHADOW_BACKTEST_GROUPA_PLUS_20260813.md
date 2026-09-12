# HANDOFF - 2603.01157v2 BAWS-lite adaptive window VaR/ES for GroupA+

Date: 2026-08-13  
Owner note: Codex 2026-08-13  
Paper: arXiv:2603.01157v2, "Adaptive Window Selection for Financial Risk Forecasting"

## Scope

User asked whether `C:\Users\isaac\Downloads\2603.01157v2.pdf` has benefits that can be introduced into GroupA+ latest strategy.

Decision: implement only a research-only shadow diagnostic. Do not change GroupA+ latest strategy, golden1_0531, live signal, execution plan, or any order file.

## What was implemented

New code:

- `scripts/evaluate/evaluate_group_a_plus_baws_lite_var_es_shadow.py`
- `tests/test_evaluate_group_a_plus_baws_lite_var_es_shadow.py`

Generated artifacts:

- `results/group_a_plus_baws_lite_var_es_shadow_latest.json`
- `results/group_a_plus_baws_lite_var_es_shadow_forecasts_latest.csv`
- `report/group_a_plus/latest/baws_lite_var_es_shadow.md`

The evaluator tests a BAWS-lite adaptive historical window for one-day loss VaR/ES forecasts over the GroupA+ ETF universe:

- `0050.TW`
- `00631L.TW`
- `00632R.TW`
- `00679B.TWO`

Candidate windows:

- 63 trading days
- 126 trading days
- 252 trading days
- 504 trading days

Method summary:

- Forecast one-day loss VaR and ES using historical windows.
- Score VaR forecasts with quantile/check loss at alpha 0.95.
- Compare longer candidate windows with the shortest reference window over a rolling evaluation window.
- Use a deterministic moving-block bootstrap threshold with beta 0.90.
- Select the largest admissible window.

Codex 2026-08-13: this is intentionally shadow-only and does not write to any production pointer.

## Backtest run

Primary command:

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_baws_lite_var_es_shadow.py --start 2025-01-02 --end 2026-08-13 --candidate-windows 63,126,252,504 --evaluation-window 63 --bootstrap-samples 200
```

Result:

```json
{
  "promotion_ready": false,
  "baws_beats_best_fixed_count": 0,
  "tickers_evaluated": 4,
  "average_baws_minus_best_fixed_score": 0.00003646363478175763
}
```

Ticker-level comparison:

| Ticker | Best fixed window | BAWS minus best fixed score | BAWS beats best fixed |
|---|---:|---:|---:|
| 0050.TW | fixed_504 | 0.0000000000 | false |
| 00631L.TW | fixed_252 | 0.0000008349 | false |
| 00632R.TW | fixed_63 | 0.0001406849 | false |
| 00679B.TWO | fixed_252 | 0.0000043347 | false |

## All-window backtest sweep

User asked whether all relevant windows were backtested. After the primary 2025-2026 run, Codex 2026-08-13 added three additional checks:

| Scenario | Start | End | Candidate windows | Forecast rows | BAWS beats best fixed | Avg BAWS-best score delta | Promotion ready |
|---|---:|---:|---|---:|---:|---:|---:|
| 2020 COVID | 2020-01-02 | 2020-12-31 | 20,40,63,126 | 980 | 0/4 | 0.0002837931 | false |
| 2022 rate hike | 2022-01-03 | 2022-12-30 | 20,40,63,126,252 | 984 | 0/4 | 0.0000102095 | false |
| 2024-2026 recent long | 2024-01-02 | 2026-08-13 | 63,126,252,504 | 2532 | 0/4 | 0.0000222090 | false |
| 2025-2026 latest | 2025-01-02 | 2026-08-13 | 63,126,252,504 | 1564 | 0/4 | 0.0000364636 | false |

Additional commands:

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_baws_lite_var_es_shadow.py --start 2020-01-02 --end 2020-12-31 --candidate-windows 20,40,63,126 --evaluation-window 40 --bootstrap-samples 200 --output-json results/group_a_plus_baws_lite_var_es_shadow_2020_covid.json --output-csv results/group_a_plus_baws_lite_var_es_shadow_2020_covid_forecasts.csv --output-md report/group_a_plus/latest/baws_lite_var_es_shadow_2020_covid.md

.venv/bin/python scripts/evaluate/evaluate_group_a_plus_baws_lite_var_es_shadow.py --start 2022-01-03 --end 2022-12-30 --candidate-windows 20,40,63,126,252 --evaluation-window 40 --bootstrap-samples 200 --output-json results/group_a_plus_baws_lite_var_es_shadow_2022_rate_hike.json --output-csv results/group_a_plus_baws_lite_var_es_shadow_2022_rate_hike_forecasts.csv --output-md report/group_a_plus/latest/baws_lite_var_es_shadow_2022_rate_hike.md

.venv/bin/python scripts/evaluate/evaluate_group_a_plus_baws_lite_var_es_shadow.py --start 2024-01-02 --end 2026-08-13 --candidate-windows 63,126,252,504 --evaluation-window 63 --bootstrap-samples 200 --output-json results/group_a_plus_baws_lite_var_es_shadow_2024_2026.json --output-csv results/group_a_plus_baws_lite_var_es_shadow_2024_2026_forecasts.csv --output-md report/group_a_plus/latest/baws_lite_var_es_shadow_2024_2026.md
```

Additional generated artifacts:

- `results/group_a_plus_baws_lite_var_es_shadow_2020_covid.json`
- `results/group_a_plus_baws_lite_var_es_shadow_2020_covid_forecasts.csv`
- `report/group_a_plus/latest/baws_lite_var_es_shadow_2020_covid.md`
- `results/group_a_plus_baws_lite_var_es_shadow_2022_rate_hike.json`
- `results/group_a_plus_baws_lite_var_es_shadow_2022_rate_hike_forecasts.csv`
- `report/group_a_plus/latest/baws_lite_var_es_shadow_2022_rate_hike.md`
- `results/group_a_plus_baws_lite_var_es_shadow_2024_2026.json`
- `results/group_a_plus_baws_lite_var_es_shadow_2024_2026_forecasts.csv`
- `report/group_a_plus/latest/baws_lite_var_es_shadow_2024_2026.md`

Sweep interpretation: across COVID stress, 2022 drawdown, and recent long samples, BAWS-lite never beat the best fixed-window method for any GroupA+ ETF. This strengthens the decision to keep it research-only.

Selected-window behavior:

| Ticker | Selected windows |
|---|---|
| 0050.TW | 504: 391 days |
| 00631L.TW | 504: 391 days |
| 00632R.TW | 504: 391 days |
| 00679B.TWO | 252: 1 day, 504: 390 days |

Interpretation: BAWS-lite mostly chose the longest 504-day window. In this 2025-01-02 to 2026-08-13 GroupA+ sample, adaptive-window selection did not improve VaR forecast score against the best fixed windows.

## Latest 2026-08-13 snapshot

| Ticker | Selected window | VaR loss | ES loss | Latest realized loss | Breach |
|---|---:|---:|---:|---:|---:|
| 0050.TW | 504 | 0.02313337 | 0.04022806 | -0.01425856 | false |
| 00631L.TW | 504 | 0.04740771 | 0.08475859 | -0.02369535 | false |
| 00632R.TW | 504 | 0.02771580 | 0.04105309 | 0.01093445 | false |
| 00679B.TWO | 504 | 0.01220124 | 0.02079279 | 0.00151569 | false |

The latest day does not show a BAWS VaR breach for any GroupA+ ETF.

## Why this should not enter latest strategy yet

1. It did not beat the best fixed-window forecast for any of the four GroupA+ ETFs.
2. It does not produce allocation weights; it is a risk forecast method.
3. The adaptive rule mostly selected 504 days, so the current evidence does not justify replacing existing fixed-window tail diagnostics.
4. Promotion would add complexity without measured benefit.

Recommended status:

- Keep as research-only.
- Do not add to `group_a_plus/operations/daily_signal.py`.
- Do not add to `group_a_plus/operations/execution_guard.py`.
- Do not use it to block or force 00631L trades.

## Tests

Passed:

```bash
.venv/bin/python -m pytest tests/test_evaluate_group_a_plus_baws_lite_var_es_shadow.py -q
```

Output:

```text
3 passed in 6.12s
```

Passed:

```bash
.venv/bin/python -m py_compile scripts/evaluate/evaluate_group_a_plus_baws_lite_var_es_shadow.py tests/test_evaluate_group_a_plus_baws_lite_var_es_shadow.py
```

## Follow-up options

If revisited later, test BAWS-lite on explicit stress windows before considering promotion:

- 2020 COVID
- 2022 rate-hike drawdown
- 2024-2026 recent regime
- Windows around known 00631L drawdowns

Promotion gate should require:

- BAWS beats best fixed windows on most tickers.
- 00631L breach calibration improves without too many false positives.
- At least one drawdown-sensitive portfolio replay improves Sortino or max drawdown after costs.
