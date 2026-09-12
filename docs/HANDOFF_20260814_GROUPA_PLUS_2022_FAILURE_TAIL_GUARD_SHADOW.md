# HANDOFF - GroupA+ 2022 failure attribution and tail no-00631L proxy shadow

Date: 2026-08-14  
Owner note: Codex 2026-08-14

## Scope

Follow-up after the 2026-08-14 prediction safety audit. The weak core latest-strategy backtest window was 2022:

- Final value: `846,876.29`
- Total return: `-15.31%`
- Max drawdown: `-21.73%`

This handoff documents a targeted failure attribution and a research-only proxy test of a hard no-new-00631L tail guard. No production strategy, golden1_0531, live signal, execution plan, or order file was changed.

## New files

- `scripts/evaluate/evaluate_group_a_plus_2022_failure_and_tail_guard_shadow.py`
- `tests/test_evaluate_group_a_plus_2022_failure_tail_guard_shadow.py`
- `results/group_a_plus_2022_failure_tail_guard_shadow_2022_rate_hike.json`
- `results/group_a_plus_2022_failure_tail_guard_shadow_2022_rate_hike_curve.csv`
- `report/group_a_plus/latest/2022_failure_tail_guard_shadow.md`

Additional multi-window outputs:

- `results/group_a_plus_2022_failure_tail_guard_shadow_2020_covid.json`
- `results/group_a_plus_2022_failure_tail_guard_shadow_2024_2026.json`
- `results/group_a_plus_2022_failure_tail_guard_shadow_2025_2026.json`
- matching curve CSV and Markdown files under `results/` and `report/group_a_plus/latest/`

## Method

The proxy shadow uses the active latest strategy runner and the same costed simulator used by the active runner. It creates a shadow regime only when:

- current execution regime is `golden1`
- `tail_risk_score >= 1`

On those days it maps golden1 to:

- `00631L.TW = 0`
- original 00631L weight shifted into `0050.TW`
- cash unchanged

Codex 2026-08-14: this is a proxy for hard no-new-00631L / tail trim behavior. It is not equivalent to full live `tail_conformal` history and must not be promoted without a stronger walk-forward implementation.

## 2022 failure attribution

2022 regime counts:

| Regime | Days |
|---|---:|
| golden1 | 67 |
| group_a_plus_defensive | 179 |

Worst drawdown episode:

| Start | Trough | End | Max drawdown |
|---|---:|---:|---:|
| 2022-01-18 | 2022-10-25 | 2022-12-30 | -21.73% |

Top loss days:

| Date | Portfolio return | Regime | Tail score | Total risk score | 0050 return |
|---|---:|---|---:|---:|---:|
| 2022-10-11 | -2.47% | group_a_plus_defensive | 2 | 1 | -5.18% |
| 2022-02-24 | -1.79% | group_a_plus_defensive | 1 | 4 | -2.43% |
| 2022-09-28 | -1.47% | group_a_plus_defensive | 0 | 3 | -2.09% |
| 2022-01-21 | -1.47% | golden1 | 2 | 5 | -4.33% |
| 2022-11-28 | -1.32% | golden1 | 1 | 0 | -2.01% |

Interpretation:

- 2022 losses were not mainly caused by late 00631L adds.
- The strategy spent most of the year in defensive mode.
- The largest loss days were mostly defensive-mode equity exposure losses, not pure golden1 leverage exposure.
- Therefore, a no-new-00631L guard alone is not the correct fix for the 2022 failure.

## Tail no-00631L proxy results

Command for 2022:

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_2022_failure_and_tail_guard_shadow.py --start 2022-01-03 --end 2022-12-30 --initial-value 1000000 --tail-risk-score-min 1 --output-json results/group_a_plus_2022_failure_tail_guard_shadow_2022_rate_hike.json --output-csv results/group_a_plus_2022_failure_tail_guard_shadow_2022_rate_hike_curve.csv --output-md report/group_a_plus/latest/2022_failure_tail_guard_shadow.md
```

2022 result:

| Metric | Baseline latest | Tail no-00631L proxy | Delta |
|---|---:|---:|---:|
| final_value | 846,876.29 | 842,393.06 | -4,483.23 |
| annual_return | -15.48% | -15.93% | -0.45pp |
| sharpe_ratio | -1.5541 | -1.6256 | -0.0715 |
| sortino_ratio | -1.5007 | -1.5675 | -0.0667 |
| max_drawdown | -21.73% | -22.07% | -0.34pp |

Multi-window results:

| Scenario | Guard days | Final value delta | Sortino delta | Max drawdown delta | Promotion ready |
|---|---:|---:|---:|---:|---:|
| 2020 COVID | 14 | -31,699.66 | -0.1597 | -0.0009 | false |
| 2022 rate hike | 14 | -4,483.23 | -0.0667 | -0.0034 | false |
| 2024-2026 | 70 | -201,558.73 | +0.1166 | +0.0308 | false |
| 2025-2026 | 40 | -125,828.72 | +0.0994 | +0.0045 | false |

Interpretation:

- The proxy guard improves recent risk-adjusted metrics in some windows but sacrifices too much final value.
- It worsens 2020 and 2022, including the exact weak window it was meant to fix.
- It is not promotable.

## Decision

Do not upgrade a simple tail no-new-00631L hard guard.

Recommended next research target:

1. Analyze defensive-mode composition in 2022, because 179/246 days were defensive.
2. Test a 2022-specific defensive basket improvement, likely lower 0050 beta or higher cash/bond during persistent downtrends.
3. Keep 8/14 manual caution: current live `tail_conformal=TAIL_RISK_HIGH`, so a new 00631L buy should still be manually reviewed even though this simple historical proxy is not promotable.

## Tests

Passed:

```bash
.venv/bin/python -m pytest tests/test_evaluate_group_a_plus_2022_failure_tail_guard_shadow.py -q
```

Output:

```text
3 passed in 5.44s
```

Passed:

```bash
.venv/bin/python -m py_compile scripts/evaluate/evaluate_group_a_plus_2022_failure_and_tail_guard_shadow.py tests/test_evaluate_group_a_plus_2022_failure_tail_guard_shadow.py
```

