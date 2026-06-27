# Group A Hold10 + Group B No-2884 Rerun

Date: 2026-06-05

## Scope

- Window: 2024-01-02 to 2026-06-04, 584 trading rows.
- Group A: `hold_limit_00632r_10d_to_0050`.
- Group B: latest no-2884 curve.
- No retraining. This rerun only recombines existing daily equity curves and tests top-level A/B allocation.

## Outputs

- Combined A+B curve: `results/group_ab_hold10_no2884_backtest_20240102_20260604_curve.csv`
- Research JSON: `results/group_ab_hold10_no2884_research_20240102_20260604.json`
- Research table: `results/group_ab_hold10_no2884_research_20240102_20260604.csv`
- Research curves: `results/group_ab_hold10_no2884_research_20240102_20260604_curve.csv`

## Key Results

| Variant | Final | Annual | Sharpe | Max DD | Events | Cost |
|---|---:|---:|---:|---:|---:|---:|
| Fixed 25A/75B | 4,924,788 | 45.11% | 2.7992 | -15.69% | 10 | 672 |
| Fixed 50A/50B | 5,478,577 | 51.64% | 2.6667 | -18.39% | 10 | 911 |
| Fixed 62.5A/37.5B | 5,764,015 | 54.86% | 2.5589 | -19.75% | 10 | 860 |
| Dynamic lb126 band0.080 | 5,887,110 | 56.22% | 2.5785 | -19.01% | 7 | 1,115 |
| Fixed 90A/10B | 6,408,003 | 61.79% | 2.3200 | -24.66% | 10 | 335 |
| Fixed 100A/0B | 6,646,421 | 64.25% | 2.2416 | -26.43% | 10 | 0 |

## Comparison Versus Previous A+B Best

Previous best dynamic A+B:

- Variant: `dynamic_lb126_band0.015`
- Final: 5,636,020
- Annual: 53.43%
- Sharpe: 2.5203
- Max DD: -19.01%

New best dynamic A+B:

- Variant: `dynamic_lb126_band0.080`
- Final: 5,887,110
- Annual: 56.22%
- Sharpe: 2.5785
- Max DD: -19.01%

## Conclusion

The Group A hold10 overlay improves the A+B stack versus the previous best dynamic A+B run.

- Best risk-adjusted fixed allocation: 25A/75B, but final value is much lower.
- Best balanced live candidate: dynamic `lb126 band0.080`.
- If prioritizing raw final value only, 90A/10B or 100A/0B wins, but drawdown rises to about -24.7% to -26.4% and Sharpe falls.

Current practical recommendation: use dynamic `lb126 band0.080` for A+B allocation, with Group A running the 00632R max-hold-10 overlay and Group B excluding 2884.
