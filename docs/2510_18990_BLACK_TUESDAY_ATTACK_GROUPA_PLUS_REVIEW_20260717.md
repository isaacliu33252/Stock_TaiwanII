# 2510.18990 GroupA+ Review

Source:

- `C:/Users/isaac/Downloads/2510.18990.pdf`
- Title: `The Black Tuesday Attack: How to Crash the Stock Market with Adversarial Examples to Financial Forecasting Models`
- arXiv version date in PDF: `2025-10-21`

## Paper Summary

The paper argues that financial forecasting models can be an attack surface:
small, sparse, coordinated perturbations in market inputs may cause ML models
trained on similar public data to make transferable, self-reinforcing bearish
forecasts. The paper discusses surrogate models, sparse targeted perturbations,
transferability, single-stock attacks, and imperfect defenses such as
adversarial training, detection, and smoothing.

## GroupA+ Decision

Do not import as a trading alpha or allocation rule.

Import only as adversarial-robustness governance:

- forecast model outputs must not directly trigger live target-weight changes;
- model outputs must be cross-checked against source freshness, option-state
  coverage, crash-risk state, signal alignment, and rebalance governance;
- small input perturbation / smoothing sensitivity should be tested only as
  future shadow research;
- any model-driven `00631L` add must remain blocked when robustness state is
  incomplete.

## Implemented Artifact

- `scripts/evaluate/build_group_a_plus_adversarial_market_integrity_review.py`
- `report/group_a_plus/latest/adversarial_market_integrity_review_20260720.json`
- `report/group_a_plus/latest/adversarial_market_integrity_review.json`
- `report/group_a_plus/adversarial_market_integrity/history/20260720.json`
- `tests/test_build_group_a_plus_adversarial_market_integrity_review.py`
- `scripts/run/run_ncf_daily_pipeline.py` now runs
  `adversarial_market_integrity_review` as a best-effort daily diagnostic.

Daily history:

- The review script writes both latest and dated history snapshots by default.
- History can be disabled with `--no-history` for one-off experiments.

Current result:

- status: `blocked`
- `target_weight_change_allowed = false`
- `allow_00631l_add = false`
- `keep_golden1_0531_unchanged = true`

Blocking reasons:

- `live_signal_execution_not_allowed`
- `option_state_gate_not_passed`
- `rebalance_review_disallows_target_weight_change`
- `adversarial_robustness_state_incomplete`

Warnings:

- `signal_alignment_wide_divergence`
- `market_risk_level_medium_high`

## Not Imported

- attack construction;
- surrogate adversarial attack model;
- adversarial training for live trading;
- any automatic target-weight change;
- any `00631L` auto-add override.

## Recommended Next Step

Keep this as a daily or pre-trade research diagnostic after enough evidence
accumulates. Future shadow tests can evaluate:

- sparse input perturbation sensitivity on NCF panels;
- raw-vs-smoothed feature prediction stability;
- cross-model direction consensus under small OHLCV/volume perturbations.

No live strategy change is justified by this paper.
