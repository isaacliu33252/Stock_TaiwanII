# FinStressTS Counterfactual Shadow（2026-07-17）

## Purpose

This is the next research step after reviewing
`C:\Users\isaac\Downloads\2606.03184.pdf`.

The goal is not to create synthetic alpha. The goal is to test whether the
current `2026-07-20` GroupA+ reference allocation can survive a small set of
mechanism-specific stress scenarios inspired by FinStressTS.

## Portfolios Compared

- `reference_20260720`: `0050.TW 50% / 00631L.TW 20% / cash 30%`
- `no_00631l_reference_cash`: `0050.TW 50% / cash 50%`
- `0050_only_full`: `0050.TW 100%`
- `reduced_leverage`: `0050.TW 70% / 00631L.TW 10% / cash 20%`
- `cash`: `100% cash`

## Counterfactual Scenarios

- `historical_baseline`
- `heavy_tailed_shocks`
- `regime_switch_down`
- `self_exciting_jumps`
- `zero_inflated_sparse_jumps`

## Artifacts

- Script: `scripts/evaluate/evaluate_group_a_plus_finstressts_counterfactual_shadow.py`
- Output: `results/group_a_plus_finstressts_counterfactual_shadow_20260717.json`
- Latest pointer: `report/group_a_plus/latest/finstressts_counterfactual_shadow.json`
- Daily pipeline: `finstressts_counterfactual_shadow` runs as a best-effort
  diagnostic after `finstressts_readiness_review`.

## Decision Rule

The `2026-07-20` reference allocation fails this shadow review if it has higher
95% expected shortfall or larger absolute max drawdown than the no-`00631L`
reference in stress scenarios.

## Decision

This is a research-only shadow review.

- It does not change GroupA+ live target weights.
- It does not allow auto-rebalance.
- It does not allow adding `00631L`.
- It keeps `Golden1_0531` unchanged.

## 2026-07-17 Result

Input data:

- common `0050.TW` / `00631L.TW` close panel through `2026-07-17`
- scenario rows: `2809`

Summary:

- `reference_loses_to_no_00631l_scenarios = 5`
- `reference_tail_failure_scenarios = 4`
- `allow_00631l_add = false`

Scenario comparison:

| Scenario | Ref ES95 | No-00631L ES95 | Ref MDD | No-00631L MDD | Decision |
| --- | ---: | ---: | ---: | ---: | --- |
| `historical_baseline` | `0.0252` | `0.0140` | `-0.3032` | `-0.1986` | reference weaker |
| `heavy_tailed_shocks` | `0.0423` | `0.0232` | `-0.7290` | `-0.5326` | reference weaker |
| `regime_switch_down` | `0.0249` | `0.0140` | `-0.5511` | `-0.4346` | reference weaker |
| `self_exciting_jumps` | `0.0262` | `0.0146` | `-0.3656` | `-0.2376` | reference weaker |
| `zero_inflated_sparse_jumps` | `0.0113` | `0.0062` | `-0.1632` | `-0.1009` | reference weaker |

Conclusion:

- The `2026-07-20` reference allocation
  `0050.TW 50% / 00631L.TW 20% / cash 30%` does not pass this
  FinStressTS-style shadow review.
- The no-`00631L` reference has lower ES95 and lower drawdown in every tested
  scenario.
- This reinforces the current GroupA+ decision: no rebalance, no `00631L` add,
  and no live target-weight change.
