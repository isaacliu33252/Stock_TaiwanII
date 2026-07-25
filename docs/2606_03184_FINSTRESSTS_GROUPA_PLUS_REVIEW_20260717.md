# 2606.03184 FinStressTS Review for GroupA+

## Source

- File: `C:\Users\isaac\Downloads\2606.03184.pdf`
- Title: `FinStressTS: A Parametric Synthetic Benchmark for Time-Series Forecasting in Finance`
- Reviewed on: `2026-07-17`
- Strategy context: `a2118_a2111_ncf_late_bull_deleverage`
- Reference date under review: `2026-07-20`

## Paper Takeaway

FinStressTS is a diagnostic benchmark, not a trading strategy. It builds
controlled synthetic financial time-series environments so a forecaster's
failure can be attributed to a specific mechanism instead of a mixed historical
sample.

The paper's six useful mechanism families are:

- volatility clustering
- multi-scale persistence
- heavy-tailed shocks
- regime switching
- self-exciting clustered jumps
- zero-inflated sparse jumps

The paper also reports that larger neural models do not automatically dominate:
simple autoregressive or linear/econometric baselines can outperform
Transformers in mechanism-specific financial settings, and probabilistic
models must be judged by calibration, not only point error.

## Useful Ideas Imported

Imported as GroupA+ research/governance only:

- mechanism-specific stress-test checklist before model promotion
- counterfactual synthetic scenarios for failure attribution
- probabilistic calibration review under known data-generating mechanisms
- data-efficiency / learning-curve requirement before trusting larger models
- simple baseline requirement before Transformer or density-head promotion
- no single model should unlock execution without multi-window and mechanism
  evidence

## Not Imported

Not imported:

- synthetic returns as live alpha
- KDD benchmark rankings as Taiwan ETF evidence
- automatic architecture replacement
- automatic rebalance or target-weight change
- any direct `00631L` add signal

## GroupA+ Mapping

The paper supports adding a `FinStressTS` readiness review that checks whether
current GroupA+ evidence covers the main failure mechanisms:

- volatility clustering: partially covered by heterogeneous volatility and
  CVaR/tail diagnostics
- multi-scale persistence: partially covered by rolling windows and promotion
  gates, but no HAR-style synthetic benchmark is live
- heavy tails: partially covered by CVaR/density-head reviews, but option-state
  coverage is still blocked
- regime switching: partially covered by market-state and compounding-regime
  labels
- self-exciting jumps: only indirectly covered by crash/adversarial/impact
  checks; no Hawkes-style stress harness is live
- zero-inflated sparse jumps: only indirectly covered by adversarial sparse
  perturbation governance and option-state checks

## Current Output

Produced:

- `scripts/evaluate/build_group_a_plus_finstressts_readiness_review.py`
- `report/group_a_plus/latest/finstressts_readiness_review_20260720.json`
- `report/group_a_plus/latest/finstressts_readiness_review.json`
- `report/group_a_plus/finstressts_readiness/history/20260720.json`

Current result:

- `status = blocked`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `allow_00631l_add = false`
- `keep_golden1_0531_unchanged = true`

Blocking reasons:

- `live_signal_execution_not_allowed`
- `rebalance_review_disallows_target_weight_change`
- `option_state_gate_not_passed`
- `adversarial_market_integrity_not_passed`
- `market_impact_readiness_not_passed`
- `optimizer_readiness_not_passed`
- `mechanism_stress_coverage_blocked`

## Decision

This PDF has useful validation ideas, but no live allocation advantage that can
be imported directly.

Decision:

- keep GroupA+ latest strategy unchanged
- keep `Golden1_0531` unchanged
- do not auto-rebalance for `2026-07-20`
- do not auto-add `00631L`
- use FinStressTS only as a research-only model validation readiness gate

Best next research step:

- build a small Taiwan ETF counterfactual stress harness covering heavy-tail,
  regime-switch, and jump-cluster scenarios, then compare current NCF,
  density-head, and simple linear baselines before any model promotion claim.

## Next Step Completed

Added a first fixed-weight counterfactual stress harness:

- `scripts/evaluate/evaluate_group_a_plus_finstressts_counterfactual_shadow.py`
- `results/group_a_plus_finstressts_counterfactual_shadow_20260717.json`
- `report/group_a_plus/latest/finstressts_counterfactual_shadow.json`
- `docs/FINSTRESSTS_COUNTERFACTUAL_SHADOW_20260717.md`

Result:

- `reference_loses_to_no_00631l_scenarios = 5`
- `reference_tail_failure_scenarios = 4`
- `allow_00631l_add = false`

Conclusion:

- The `2026-07-20` reference allocation does not pass this stress harness.
- Keep GroupA+ latest strategy and `Golden1_0531` unchanged.
