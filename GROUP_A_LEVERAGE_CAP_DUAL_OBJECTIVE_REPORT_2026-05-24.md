# Group A Leverage Cap Dual-Objective Report

Date: 2026-05-24

## Scope

This comparison tests the current `Group A` model and runtime payload under three `00631L` exposure caps:

- `leverage_cap = 0.20`
- `leverage_cap = 0.25`
- `leverage_cap = 0.30` (current canonical baseline)

Two evaluation windows were used:

- Recent real window: `2024-01-02` to `2026-05-20`
- Crash proxy window: `2007-07-02` to `2010-12-31` using the `TWII` synthetic 2008 stress path

Artifacts:

- Raw comparison JSON:
  `results/group_a_leverage_cap_dual_objective_20260524.json`
- 2008 proxy sweep context:
  `results/group_a_twii_proxy_2008_runtime_sweep_20260524.json`

## Headline Conclusion

- If the primary objective is `recent production return`, keep `leverage_cap = 0.30`.
- If the primary objective is `2008-style crash defense`, `leverage_cap = 0.20` is clearly better.
- `0.25` is not compelling. It is basically dominated by the other two choices.

The tradeoff is real:

- `0.30` wins on recent final value and recent contribution return.
- `0.20` wins on crash drawdown, crash return, crash Sharpe, and also slightly improves recent Sharpe and recent max drawdown.
- The cost of `0.20` is a meaningful drop in recent final value.

## Summary Table

| Cap | Recent Final Value | Recent Contribution Return | Recent Sharpe | Recent Max DD | Crash Final Value | Crash Contribution Return | Crash Sharpe | Crash Max DD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `0.20` | `3,554,678.12` | `2.1045` | `2.3914` | `-20.32%` | `1,521,037.15` | `0.2571` | `0.5359` | `-50.66%` |
| `0.25` | `3,618,299.64` | `2.1601` | `2.3324` | `-22.02%` | `1,426,392.48` | `0.1788` | `0.4464` | `-53.89%` |
| `0.30` | `3,736,958.18` | `2.2637` | `2.3571` | `-22.04%` | `1,439,564.66` | `0.1897` | `0.4538` | `-54.18%` |

## Delta Vs Current Baseline `0.30`

### Cap `0.20`

Recent real window:

- Final value: `-182,280.06`
- Contribution return: `-0.1592`
- Sharpe: `+0.0343`
- Max drawdown: improved by `1.72pp`

Crash proxy window:

- Final value: `+81,472.50`
- Contribution return: `+0.0673`
- Sharpe: `+0.0822`
- Max drawdown: improved by `3.52pp`

Interpretation:

- `0.20` is the strongest crash-defense choice.
- It is also cleaner on recent risk-adjusted metrics than `0.30`.
- But the recent return sacrifice is large enough that it should not automatically replace the canonical production cap.

### Cap `0.25`

Recent real window:

- Final value: `-118,658.54`
- Contribution return: `-0.1036`
- Sharpe: `-0.0247`
- Max drawdown: improved by only `0.02pp`

Crash proxy window:

- Final value: `-13,172.17`
- Contribution return: `-0.0109`
- Sharpe: `-0.0074`
- Max drawdown: improved by only `0.29pp`

Interpretation:

- `0.25` gives up recent return without meaningful crash improvement.
- It is weaker than `0.20` for defense and weaker than `0.30` for production.
- This is the least attractive middle point.

## Ranking By Objective

### Objective A: Maximize Recent Production Performance

1. `0.30`
2. `0.25`
3. `0.20`

Reason:

- `0.30` has the highest recent final value and highest recent contribution return.

### Objective B: Reduce 2008-Style Crash Damage

1. `0.20`
2. `0.25`
3. `0.30`

Reason:

- `0.20` has the best crash max drawdown, best crash contribution return, and best crash Sharpe.

### Objective C: Balanced Risk/Return Read

If you care about both windows at once:

- `0.20` is the better `defensive profile`
- `0.30` is the better `production growth profile`
- `0.25` should be discarded

## Practical Recommendation

Use two profiles instead of forcing one compromise:

- `Production profile`: keep `leverage_cap = 0.30`
- `Crash profile`: add a separate payload with `leverage_cap = 0.20`

This is the cleanest result from the data. The windows disagree enough that a single universal cap is not justified.

## Bottom Line

To answer the original question directly:

- Yes, `Group A RL` can reduce `2008`-style drawdown further.
- The most effective tested change is:
  `leverage_cap 0.30 -> 0.20`
- But that same change materially lowers recent real-window return, so it is better treated as a `defensive alternate profile`, not an immediate replacement for the current canonical payload.
