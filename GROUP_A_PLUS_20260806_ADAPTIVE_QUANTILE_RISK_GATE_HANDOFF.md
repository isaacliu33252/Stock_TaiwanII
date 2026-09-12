# GroupA+ Adaptive Quantile Risk Gate Handoff - 2026-08-06

## Source

- Paper: `C:\Users\isaac\Downloads\2605.24345.pdf`
- Title: `Evolving Robustness-Exploration Trade-off in Online Reinforcement Learning via Quantile Bayesian Risk MDPs`
- arXiv: `2605.24345`

## Practical Mapping

The paper's useful idea for GroupA+ is adaptive risk posture under epistemic
uncertainty:

- Lower-tail quantile (`alpha < 0.5`) maps to robust / pessimistic execution posture.
- Neutral quantile (`alpha = 0.5`) maps to normal latest-strategy posture.
- Upper-tail quantile (`alpha > 0.5`) maps to controlled exploration only when data are fresh and diagnostics agree.

This implementation is shadow-only. It does not change:

- `target_weights`
- `target_shares`
- `execution_regime`
- `base_regime`
- auto-rebalance decisions

## Added Files

- `group_a_plus/integrations/adaptive_quantile_risk_gate.py`
  - Pure classification logic.
  - Produces `pessimistic_0.20`, `defensive_0.35`, `neutral_0.50`, or `controlled_exploration_0.65`.
  - Converts execution freshness, NCF overlay status, signal alignment, ops health, strategy trust, tail/garch guards, leverage suitability, regime analog count, and yesterday review into a quantile posture.

- `scripts/evaluate/build_group_a_plus_adaptive_quantile_risk_gate_shadow.py`
  - CLI wrapper.
  - Reads wrapped or unwrapped `live_signal` JSON.
  - Writes latest report, history snapshot, and idempotent JSONL shadow log.

- `tests/test_group_a_plus_adaptive_quantile_risk_gate.py`
  - Covers stale/blocked defensive behavior, clean/fresh controlled exploration, yesterday-forecast miss penalty, idempotent log writing, and wrapped signal input.

## Generated Artifacts

- `report/group_a_plus/latest/adaptive_quantile_risk_gate_shadow.json`
- `report/group_a_plus/adaptive_quantile_risk_gate/history/adaptive_quantile_risk_gate_shadow_20260806.json`
- `results/adaptive_quantile_risk_gate_shadow_log.jsonl`

## Current 2026-08-06 Result

Command used:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_adaptive_quantile_risk_gate_shadow.py \
  --live-signal report/group_a_plus/latest/live_signal_20260810_1m_latest_strategy_preview.json \
  --as-of 2026-08-06
```

Result:

- `risk_posture`: `pessimistic_0.20`
- `quantile_level`: `0.2`
- `uncertainty_score`: `0.78`
- `exploration_credit`: `0.04`

Reason codes:

- `execution_guard_not_satisfied`
- `business_stale_days=2`
- `ncf_live_overlay_stale`
- `ops_health_data_quality_problem`
- `strategy_trust_abstain`
- `leverage_suitability_tier=1`
- `signal_alignment=bullish_alignment`
- `yesterday_review_missing`

Recommended shadow limits:

- `max_00631l_weight`: `0.0`
- `min_cash_weight`: `0.45`
- `allow_new_leverage_long`: `false`
- `allow_00632r_hedge`: `true`
- `hedge_policy`: `manual_review_when_execution_guard_blocked`

Current 8/10 preview target had:

- `00631L.TW`: `0.0`
- `cash`: `0.42921266083869036`

So the shadow gate does not object to the zero 00631L exposure, but it flags
cash as slightly below the 45% pessimistic floor.

## Verification

```bash
.venv/bin/python -m pytest \
  tests/test_group_a_plus_adaptive_quantile_risk_gate.py \
  tests/test_group_a_plus_strategy_trust_gate.py
```

Result: `16 passed`.

## Initial Backtest Validation

Added:

- `scripts/evaluate/backtest_group_a_plus_adaptive_quantile_risk_gate_shadow.py`
- `tests/test_backtest_group_a_plus_adaptive_quantile_risk_gate_shadow.py`
- `scripts/evaluate/backtest_group_a_plus_adaptive_quantile_risk_gate_frame.py`
- `tests/test_backtest_group_a_plus_adaptive_quantile_risk_gate_frame.py`

Command:

```bash
.venv/bin/python scripts/evaluate/backtest_group_a_plus_adaptive_quantile_risk_gate_shadow.py \
  --start 2024-01-01 \
  --end 2026-08-06 \
  --min-samples 20
```

Important limitation:

- Saved live-signal snapshots only covered `2026-06-18` to `2026-08-05`.
- This is not a full 2024-2026 walk-forward validation.
- It is a true saved-signal replay over the available snapshots.

Outputs:

- `results/group_a_plus_adaptive_quantile_risk_gate_backtest_latest.json`
- `results/group_a_plus_adaptive_quantile_risk_gate_backtest_latest.csv`

Replay result:

- rows: `21`
- raw total return: `-7.6319%`
- gated total return: `-7.1444%`
- total return delta: `+0.4876%`
- raw max drawdown: `-11.9829%`
- gated max drawdown: `-10.8692%`
- max drawdown delta: `+1.1138%`
- raw worst day: `-5.0736%`
- gated worst day: `-4.7343%`
- worst day delta: `+0.3393%`
- raw Sharpe: `-3.3327`
- gated Sharpe: `-3.7123`
- Sharpe delta: `-0.3797`

Gate activity:

- changed days: `17/21`
- 00631L cap days: `17`
- raise cash floor days: `0`
- avoided bad 00631L days: `10`
- posture counts: `defensive_0.35=7`, `neutral_0.50=14`

Interpretation:

- The gate improved total return, maximum drawdown, and worst day on the
  available saved signals.
- It worsened Sharpe because it also reduced exposure on some rebound days.
- Result is `shadow_pass_candidate`, not promotable. More history is required.

Verification:

```bash
.venv/bin/python -m pytest \
  tests/test_backtest_group_a_plus_adaptive_quantile_risk_gate_shadow.py \
  tests/test_group_a_plus_adaptive_quantile_risk_gate.py
```

Result: `7 passed`.

## Full Runner Frame Validation

Generated a full latest-runner frame first:

```bash
.venv/bin/python -m group_a_plus.runners.latest \
  --start 2024-01-01 \
  --end 2026-08-06 \
  --initial-value 1000000 \
  --output results/group_a_plus_runner_latest_20240101_20260806_for_aq_gate.json \
  --frame-output results/group_a_plus_runner_latest_20240101_20260806_for_aq_gate_frame.csv
```

Then ran frame-based gate replay:

```bash
.venv/bin/python scripts/evaluate/backtest_group_a_plus_adaptive_quantile_risk_gate_frame.py \
  --report results/group_a_plus_runner_latest_20240101_20260806_for_aq_gate.json \
  --frame results/group_a_plus_runner_latest_20240101_20260806_for_aq_gate_frame.csv \
  --output results/group_a_plus_adaptive_quantile_risk_gate_frame_backtest_latest.json
```

Outputs:

- `results/group_a_plus_adaptive_quantile_risk_gate_frame_backtest_latest.json`
- `results/group_a_plus_adaptive_quantile_risk_gate_frame_backtest_latest.csv`

Frame replay result:

- rows: `607`
- window: `2024-01-02` to `2026-08-05`
- raw total return: `+170.4971%`
- gated total return: `+170.4991%`
- total return delta: `+0.0020%`
- raw max drawdown: `-12.1091%`
- gated max drawdown: `-12.1091%`
- max drawdown delta: `0.0000%`
- raw Sharpe: `0.662894`
- gated Sharpe: `0.662896`

Gate activity:

- changed days: `2`
- 00631L cap days: `2`
- raise cash floor days: `0`
- avoided bad 00631L days: `1`
- posture counts: `neutral_0.50=605`, `defensive_0.35=2`
- regime counts: `golden1=533`, `group_a_plus_defensive=72`, `group_a_plus_recovery=2`

Interpretation:

- The full latest-runner frame is already mostly zero-00631L, so this gate has
  almost no opportunity to improve or harm performance.
- The 607-row frame validation does not support promotion; result is
  `do_not_promote`.
- The earlier 21-row saved-signal replay is useful as a stress observation,
  but the longer frame replay dominates the promotion decision.

Verification:

```bash
.venv/bin/python -m pytest \
  tests/test_backtest_group_a_plus_adaptive_quantile_risk_gate_frame.py \
  tests/test_backtest_group_a_plus_adaptive_quantile_risk_gate_shadow.py \
  tests/test_group_a_plus_adaptive_quantile_risk_gate.py
```

Result: `8 passed`.

## Improvement Candidate: Defensive Cash Floor

Why this was needed:

- The full-frame validation showed the original quantile gate changed only `2`
  days because latest GroupA+ already carries almost no `00631L`.
- The largest losses happened mostly inside `group_a_plus_defensive`, where
  the raw basket is approximately `0050=40%`, `00679B=30%`, `cash=30%`,
  `00631L=0%`.
- Therefore capping `00631L` alone cannot reduce those losses. The useful next
  shadow improvement is to raise cash only during high-risk defensive states.

Added:

- `scripts/evaluate/sweep_group_a_plus_adaptive_quantile_defensive_cash_floor.py`
- `tests/test_sweep_group_a_plus_adaptive_quantile_defensive_cash_floor.py`

Command:

```bash
.venv/bin/python scripts/evaluate/sweep_group_a_plus_adaptive_quantile_defensive_cash_floor.py \
  --report results/group_a_plus_runner_latest_20240101_20260806_for_aq_gate.json \
  --frame results/group_a_plus_runner_latest_20240101_20260806_for_aq_gate_frame.csv
```

Outputs:

- `results/group_a_plus_adaptive_quantile_defensive_cash_floor_sweep_latest.json`
- `results/group_a_plus_adaptive_quantile_defensive_cash_floor_sweep_latest.csv`

Best variant:

- `cash55_risk7_tail1`
- Rule: inside `group_a_plus_defensive`, raise cash floor to `55%` when
  `total_risk_score >= 7` or `tail_risk_score >= 1`.
- Active days: `27`
- Changed days: `27`

Result versus raw latest runner frame:

- raw total return: `+170.4971%`
- variant total return: `+175.7000%`
- total return delta: `+5.2029%`
- raw max drawdown: `-12.1091%`
- variant max drawdown: `-9.2299%`
- max drawdown delta: `+2.8792%`
- raw worst day: `-3.4578%`
- variant worst day: `-2.5033%`
- worst day delta: `+0.9545%`
- Sharpe delta: `+0.0074`

Interpretation:

- This is a real improvement candidate because it acts where losses occurred:
  high-risk defensive periods, not 00631L exposure.
- It still stays shadow-only. It should not be promoted without deeper
  walk-forward / crisis-window validation and a signed promotion review.

## Defensive Cash Floor Window Validation

Added:

- `scripts/evaluate/validate_group_a_plus_adaptive_quantile_defensive_cash_floor.py`
- `tests/test_validate_group_a_plus_adaptive_quantile_defensive_cash_floor.py`

Command:

```bash
.venv/bin/python scripts/evaluate/validate_group_a_plus_adaptive_quantile_defensive_cash_floor.py \
  --sweep results/group_a_plus_adaptive_quantile_defensive_cash_floor_sweep_latest.json \
  --output results/group_a_plus_adaptive_quantile_defensive_cash_floor_validation_latest.json
```

Output:

- `results/group_a_plus_adaptive_quantile_defensive_cash_floor_validation_latest.json`

Validation result:

- Variant: `cash55_risk7_tail1`
- Decision: `shadow_candidate_for_fold_ablation`
- Evaluable changed windows: `5`
- Passed changed windows: `5`
- Failed changed windows: `0`
- Formal target-weight change allowed: `false`
- Auto rebalance allowed: `false`

Window details:

| Window | Rows | Changed Days | Pass | Total Delta | MDD Delta | Worst-Day Delta |
|---|---:|---:|---|---:|---:|---:|
| full | 607 | 27 | true | `+5.2029%` | `+2.8792%` | `+0.9545%` |
| year_2024 | 232 | 0 | false/no trigger | `0.0000%` | `0.0000%` | `0.0000%` |
| year_2025 | 238 | 25 | true | `+1.1933%` | `+2.8792%` | `+0.9545%` |
| year_2026 | 137 | 2 | true | `+0.7123%` | `+0.7082%` | `+0.3727%` |
| 2024_q3_ai_selloff | 63 | 0 | false/no trigger | `0.0000%` | `0.0000%` | `0.0000%` |
| 2025_tariff_shock | 51 | 24 | true | `+1.3426%` | `+2.8951%` | `+0.9545%` |
| 2026_summer_drawdown | 46 | 2 | true | `+0.6953%` | `+0.7082%` | `+0.3727%` |

Interpretation:

- All windows where the rule actually triggered passed the validation checks.
- 2024 windows had no trigger days, so they are evidence-neutral, not positive
  validation.
- This is stronger than the initial sweep and supports the next research step:
  fold ablation / overfit checks. It still does not authorize live target-weight
  changes.

Verification:

```bash
.venv/bin/python -m pytest \
  tests/test_validate_group_a_plus_adaptive_quantile_defensive_cash_floor.py \
  tests/test_sweep_group_a_plus_adaptive_quantile_defensive_cash_floor.py
```

Result: `3 passed`.

## Defensive Cash Floor Fold Ablation

Added:

- `scripts/evaluate/ablate_group_a_plus_adaptive_quantile_defensive_cash_floor.py`
- `tests/test_ablate_group_a_plus_adaptive_quantile_defensive_cash_floor.py`

Command:

```bash
.venv/bin/python scripts/evaluate/ablate_group_a_plus_adaptive_quantile_defensive_cash_floor.py \
  --report results/group_a_plus_runner_latest_20240101_20260806_for_aq_gate.json \
  --frame results/group_a_plus_runner_latest_20240101_20260806_for_aq_gate_frame.csv \
  --output results/group_a_plus_adaptive_quantile_defensive_cash_floor_ablation_latest.json
```

Output:

- `results/group_a_plus_adaptive_quantile_defensive_cash_floor_ablation_latest.json`

Method:

- Leave one period out.
- Re-sweep the remaining frame.
- Test both the fixed candidate `cash55_risk7_tail1` and the train-selected
  best variant on the holdout period.
- Treat 2024 zero-trigger folds as evidence-neutral.

Result:

- Candidate: `cash55_risk7_tail1`
- Decision: `shadow_candidate_for_signed_review`
- Evaluable changed folds: `4`
- Candidate passed folds: `4`
- Train-selected same-family folds: `4`
- Failed folds: `0`
- Formal target-weight change allowed: `false`
- Auto rebalance allowed: `false`

Fold details:

| Holdout | Rows | Changed Days | Candidate Pass | Train-Selected Variant | Same Family | Total Delta | MDD Delta | Worst-Day Delta |
|---|---:|---:|---|---|---|---:|---:|---:|
| year_2024 | 232 | 0 | false/no trigger | `cash55_risk6_tail2` | true | `0.0000%` | `0.0000%` | `0.0000%` |
| year_2025 | 238 | 25 | true | `cash55_risk7_tail1` | true | `+1.1933%` | `+2.8792%` | `+0.9545%` |
| year_2026 | 138 | 2 | true | `cash55_risk6_tail2` | true | `+0.7123%` | `+0.7082%` | `+0.3727%` |
| 2025_tariff_shock | 51 | 24 | true | `cash55_risk7_tail2` | true | `+1.3426%` | `+2.8951%` | `+0.9545%` |
| 2026_summer_drawdown | 46 | 2 | true | `cash55_risk6_tail2` | true | `+0.6953%` | `+0.7082%` | `+0.3727%` |

Interpretation:

- The rule direction survived leave-one-period-out validation.
- Re-sweeping without each holdout still selected variants in the same
  high-cash defensive family: `cash55_risk7_tail1`,
  `cash55_risk6_tail2`, or `cash55_risk7_tail2`.
- This reduces, but does not eliminate, overfit risk. The main limitation is
  still sparse evidence: only `27` changed days in the 607-row frame, and
  2024 has no trigger days.

Verification:

```bash
.venv/bin/python -m pytest \
  tests/test_ablate_group_a_plus_adaptive_quantile_defensive_cash_floor.py \
  tests/test_validate_group_a_plus_adaptive_quantile_defensive_cash_floor.py \
  tests/test_sweep_group_a_plus_adaptive_quantile_defensive_cash_floor.py
```

Result: `5 passed`.

## Defensive Cash Floor Signed Promotion Review Package

Added:

- `scripts/evaluate/build_group_a_plus_defensive_cash_floor_signed_promotion_review.py`
- `tests/test_build_group_a_plus_defensive_cash_floor_signed_promotion_review.py`

Command:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_defensive_cash_floor_signed_promotion_review.py \
  --sweep results/group_a_plus_adaptive_quantile_defensive_cash_floor_sweep_latest.json \
  --validation results/group_a_plus_adaptive_quantile_defensive_cash_floor_validation_latest.json \
  --ablation results/group_a_plus_adaptive_quantile_defensive_cash_floor_ablation_latest.json \
  --as-of 2026-08-06 \
  --output report/group_a_plus/latest/defensive_cash_floor_signed_promotion_review.json \
  --md-output report/group_a_plus/latest/defensive_cash_floor_signed_promotion_review.md
```

Outputs:

- `report/group_a_plus/latest/defensive_cash_floor_signed_promotion_review.json`
- `report/group_a_plus/latest/defensive_cash_floor_signed_promotion_review.md`

Review status:

- `status`: `manual_signature_pending`
- `signed_review_ready`: `true`
- `manual_signature_valid`: `false`
- `promote_to_live`: `false`
- `target_weight_change_allowed`: `false`
- `auto_rebalance_allowed`: `false`
- `allow_00631l_add`: `false`
- `allow_00632r_open`: `false`
- `keep_golden1_0531_unchanged`: `true`

Candidate rule recorded for manual review:

- Variant: `cash55_risk7_tail1`
- Scope: `group_a_plus_defensive_high_risk_cash_floor_only`
- Rule: inside `group_a_plus_defensive`, raise cash floor to `55%` when
  `total_risk_score >= 7` or `tail_risk_score >= 1`.
- Mechanism: reduce positive risky ETF weights pro-rata and add the released
  weight to cash.
- Does not add `00631L`.
- Does not open `00632R`.

Manual acknowledgements required before any integration:

- Sparse `27` changed-day evidence acknowledged.
- 2024 no-trigger limitation acknowledged.
- Shadow replay is not live broker execution acknowledged.
- No `00631L` add and no `00632R` open acknowledged.
- Separate execution review required before any order acknowledged.

Rollback monitor recorded:

- Disable candidate if first 10 trigger days underperform raw by more than
  `0.50%` cumulative.
- Disable candidate if trigger-window max drawdown becomes worse than raw by
  more than `0.25%`.
- Disable candidate if cash-floor trigger conflicts with execution guard or
  freshness blockers.
- Disable candidate if the manual reviewer revokes signed review.

Verification:

```bash
.venv/bin/python -m pytest \
  tests/test_build_group_a_plus_defensive_cash_floor_signed_promotion_review.py \
  tests/test_ablate_group_a_plus_adaptive_quantile_defensive_cash_floor.py
```

Result: `5 passed`.

## Guarded Formal Candidate Integration - Disabled by Default

Added:

- `group_a_plus/integrations/defensive_cash_floor_guard.py`
- `scripts/evaluate/build_group_a_plus_defensive_cash_floor_guarded_candidate.py`
- `tests/test_group_a_plus_defensive_cash_floor_guard.py`
- `tests/test_build_group_a_plus_defensive_cash_floor_guarded_candidate.py`

Integration shape:

- This does not modify `group_a_plus.runners.latest`.
- This does not modify `report/group_a_plus/latest/strategy.json` active
  strategy.
- It builds a formal candidate artifact from the latest live signal and the
  signed-promotion-review package.
- Default is `enabled=false`.
- Even if `--enable` is passed, formal target changes require
  `manual_signature_valid=true` in the signed review.
- `auto_rebalance_allowed` remains `false`.

Rule implemented:

- Variant: `cash55_risk7_tail1`
- Scope: only `execution_regime == group_a_plus_defensive`
- Trigger: `total_risk_score >= 7` or `tail_risk_score >= 1`
- Action: raise candidate cash to `55%` by reducing positive risky ETF weights
  pro-rata.
- No `00631L` add.
- No `00632R` open.

Command run on 2026-08-07:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_defensive_cash_floor_guarded_candidate.py \
  --live-signal report/group_a_plus/latest/live_signal_20260810_1m_latest_strategy_preview.json \
  --signed-review report/group_a_plus/latest/defensive_cash_floor_signed_promotion_review.json \
  --as-of 2026-08-07 \
  --output report/group_a_plus/latest/defensive_cash_floor_guarded_candidate.json \
  --history-dir report/group_a_plus/defensive_cash_floor_guarded_candidate/history \
  --log results/defensive_cash_floor_guarded_candidate_log.jsonl
```

Outputs:

- `report/group_a_plus/latest/defensive_cash_floor_guarded_candidate.json`
- `report/group_a_plus/defensive_cash_floor_guarded_candidate/history/defensive_cash_floor_guarded_candidate_20260807.json`
- `results/defensive_cash_floor_guarded_candidate_log.jsonl`

2026-08-07 guarded candidate result:

- `enabled`: `false`
- `triggered`: `false`
- `changed`: `false`
- `target_weight_change_allowed`: `false`
- `auto_rebalance_allowed`: `false`
- `manual_signature_valid`: `false`
- reason codes:
  - `candidate_disabled_by_default`
  - `manual_signature_not_valid`
  - `execution_regime_not_defensive=golden1`

Current signal reference used:

- requested signal date: `2026-08-10`
- actual data date: `2026-08-06`
- execution regime: `golden1`
- total risk score: `2`
- tail risk score: `0`
- formal target weights unchanged:
  - `0050.TW`: `30.0000%`
  - `00631L.TW`: `0.0000%`
  - `00632R.TW`: `27.0787%`
  - `00679B.TWO`: `0.0000%`
  - cash: `42.9213%`

Verification:

```bash
.venv/bin/python -m pytest \
  tests/test_group_a_plus_defensive_cash_floor_guard.py \
  tests/test_build_group_a_plus_defensive_cash_floor_guarded_candidate.py \
  tests/test_build_group_a_plus_defensive_cash_floor_signed_promotion_review.py
```

Result: `10 passed`.

## Signed Approval Template And Validator

Added:

- `scripts/evaluate/build_group_a_plus_defensive_cash_floor_signed_approval_record_template.py`
- `scripts/evaluate/validate_group_a_plus_defensive_cash_floor_signed_approval_record.py`
- `tests/test_defensive_cash_floor_signed_approval_record.py`

Purpose:

- Convert a manual approval into a traceable JSON record.
- Do not rely on chat text as approval.
- Keep all broker/action permissions blocked unless the signed record is valid.
- Permit only guarded candidate target output, not auto rebalance or broker
  orders.

Template command:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_defensive_cash_floor_signed_approval_record_template.py \
  --promotion-review report/group_a_plus/latest/defensive_cash_floor_signed_promotion_review.json \
  --as-of 2026-08-07 \
  --output report/group_a_plus/latest/defensive_cash_floor_signed_approval_record_TEMPLATE.json \
  --history-dir report/group_a_plus/defensive_cash_floor_signed_approval_record_template/history
```

Template outputs:

- `report/group_a_plus/latest/defensive_cash_floor_signed_approval_record_TEMPLATE.json`
- `report/group_a_plus/defensive_cash_floor_signed_approval_record_template/history/defensive_cash_floor_signed_approval_record_template_20260807.json`

Template result:

- `status`: `unsigned_template_ready_for_manual_completion`
- `signed_approval_record_template_ready`: `true`
- `manual_signature_valid`: `false`
- `target_weight_change_allowed`: `false`
- `auto_rebalance_allowed`: `false`

Validation command:

```bash
.venv/bin/python scripts/evaluate/validate_group_a_plus_defensive_cash_floor_signed_approval_record.py \
  --template report/group_a_plus/latest/defensive_cash_floor_signed_approval_record_TEMPLATE.json \
  --signed-record report/group_a_plus/latest/defensive_cash_floor_signed_approval_record.json \
  --as-of 2026-08-07 \
  --output report/group_a_plus/latest/defensive_cash_floor_signed_approval_validation.json \
  --history-dir report/group_a_plus/defensive_cash_floor_signed_approval_validation/history
```

Validation outputs:

- `report/group_a_plus/latest/defensive_cash_floor_signed_approval_validation.json`
- `report/group_a_plus/defensive_cash_floor_signed_approval_validation/history/defensive_cash_floor_signed_approval_validation_20260807.json`

Initial validation result before manual approval:

- `status`: `blocked`
- `blocking_reasons`: `missing_signed_approval_record`
- `signed_approval_record_valid`: `false`
- `manual_signature_valid`: `false`
- `guarded_candidate_target_output_allowed`: `false`
- `target_weight_change_allowed`: `false`
- `auto_rebalance_allowed`: `false`
- `allow_00631l_add`: `false`
- `allow_00632r_open`: `false`

Required signed record target:

- `report/group_a_plus/latest/defensive_cash_floor_signed_approval_record.json`

Required true field in `approved_actions`:

- `allow_guarded_candidate_target_output`

Required false fields in `approved_actions`:

- `allow_auto_rebalance`
- `allow_live_strategy_change`
- `allow_00631l_add`
- `allow_00632r_open`
- `allow_broker_order_output`
- `allow_unreviewed_target_weight_output`

Required acknowledgements:

- `sparse_27_changed_day_evidence_acknowledged`
- `year_2024_no_trigger_limitation_acknowledged`
- `shadow_replay_not_live_execution_acknowledged`
- `no_00631l_add_and_no_00632r_open_acknowledged`
- `separate_execution_review_required_before_any_order_acknowledged`
- `auto_rebalance_remains_forbidden_acknowledged`
- `rollback_monitor_required_acknowledged`

Verification:

```bash
.venv/bin/python -m pytest \
  tests/test_defensive_cash_floor_signed_approval_record.py \
  tests/test_group_a_plus_defensive_cash_floor_guard.py \
  tests/test_build_group_a_plus_defensive_cash_floor_guarded_candidate.py
```

Result: `14 passed`.

## Signed Approval Activated And Guarded Candidate Enabled

User selected approval path on `2026-08-07`.

Created:

- `report/group_a_plus/latest/defensive_cash_floor_signed_approval_record.json`

Signed approval record:

- `record_id`: `defensive_cash_floor_guarded_candidate_20260807`
- `reviewer`: `isaac`
- `reviewer_role`: `owner_manual_reviewer`
- `approved_at`: `2026-08-07T08:20:37+08:00`
- `expires_at`: `2026-08-14T08:20:37+08:00`
- allowed true action:
  - `allow_guarded_candidate_target_output`
- required false actions remained false:
  - `allow_auto_rebalance`
  - `allow_live_strategy_change`
  - `allow_00631l_add`
  - `allow_00632r_open`
  - `allow_broker_order_output`
  - `allow_unreviewed_target_weight_output`
- all required acknowledgements were set true.
- `constraint_overrides`: `{}`

Validator fix:

- `validate_group_a_plus_defensive_cash_floor_signed_approval_record.py` now
  normalizes timezone-aware and timezone-naive datetimes before comparison.
- Added regression coverage for signed dates like
  `2026-08-07T09:00:00+08:00`.

Validation command:

```bash
.venv/bin/python scripts/evaluate/validate_group_a_plus_defensive_cash_floor_signed_approval_record.py \
  --template report/group_a_plus/latest/defensive_cash_floor_signed_approval_record_TEMPLATE.json \
  --signed-record report/group_a_plus/latest/defensive_cash_floor_signed_approval_record.json \
  --as-of 2026-08-07 \
  --output report/group_a_plus/latest/defensive_cash_floor_signed_approval_validation.json \
  --history-dir report/group_a_plus/defensive_cash_floor_signed_approval_validation/history
```

Validation result after approval:

- `status`: `valid_for_guarded_candidate_target_output`
- `signed_approval_record_valid`: `true`
- `manual_signature_valid`: `true`
- `guarded_candidate_target_output_allowed`: `true`
- `auto_rebalance_allowed`: `false`
- `promote_to_live`: `false`
- `allow_00631l_add`: `false`
- `allow_00632r_open`: `false`
- blockers: `[]`

Guarded candidate re-run with `--enable`:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_defensive_cash_floor_guarded_candidate.py \
  --live-signal report/group_a_plus/latest/live_signal_20260810_1m_latest_strategy_preview.json \
  --signed-review report/group_a_plus/latest/defensive_cash_floor_signed_approval_validation.json \
  --as-of 2026-08-07 \
  --enable \
  --output report/group_a_plus/latest/defensive_cash_floor_guarded_candidate.json \
  --history-dir report/group_a_plus/defensive_cash_floor_guarded_candidate/history \
  --log results/defensive_cash_floor_guarded_candidate_log.jsonl
```

2026-08-07 enabled guarded candidate result:

- `enabled`: `true`
- `manual_signature_valid`: `true`
- `guarded_candidate_target_output_allowed`: `true`
- `triggered`: `false`
- `changed`: `false`
- `target_weight_change_allowed`: `false`
- `auto_rebalance_allowed`: `false`
- reason codes:
  - `execution_regime_not_defensive=golden1`

Important interpretation:

- The approval is now valid.
- The candidate is enabled as a guarded output path.
- Today it still does not change target weights because the latest signal is
  `golden1`, not `group_a_plus_defensive`, and risk scores are below trigger:
  `total_risk_score=2`, `tail_risk_score=0`.
- The code now distinguishes approval to output a guarded candidate from
  permission to change target weights. Target changes require a valid
  signature plus an actual triggered candidate weight change.

Verification:

```bash
.venv/bin/python -m pytest \
  tests/test_group_a_plus_defensive_cash_floor_guard.py \
  tests/test_build_group_a_plus_defensive_cash_floor_guarded_candidate.py \
  tests/test_defensive_cash_floor_signed_approval_record.py
```

Result: `16 passed`.

## Daily Pipeline Wiring

Added the signed approval validation and guarded candidate report to
`scripts/run/run_ncf_daily_pipeline.py`.

New best-effort steps:

- `defensive_cash_floor_signed_approval_validation`
- `defensive_cash_floor_guarded_candidate`

Execution order in the 2026-08-07 dry-run command list:

- step `65/89`: `defensive_cash_floor_signed_approval_validation`
- step `66/89`: `defensive_cash_floor_guarded_candidate`

Validation step command shape:

```bash
.venv/bin/python scripts/evaluate/validate_group_a_plus_defensive_cash_floor_signed_approval_record.py \
  --as-of 2026-08-07 \
  --output report/group_a_plus/latest/defensive_cash_floor_signed_approval_validation.json \
  --history-dir report/group_a_plus/defensive_cash_floor_signed_approval_validation/history
```

Guarded candidate step command shape:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_defensive_cash_floor_guarded_candidate.py \
  --live-signal results/group_a_plus_live_signal_v2_20260807.json \
  --signed-review report/group_a_plus/latest/defensive_cash_floor_signed_approval_validation.json \
  --as-of 2026-08-07 \
  --enable \
  --output report/group_a_plus/latest/defensive_cash_floor_guarded_candidate.json \
  --history-dir report/group_a_plus/defensive_cash_floor_guarded_candidate/history \
  --log results/defensive_cash_floor_guarded_candidate_log.jsonl
```

Important behavior:

- Both steps are best-effort, so failure does not block daily signal,
  deployment review, or daily status.
- The guarded candidate reads the date-stamped daily live signal from
  `results/group_a_plus_live_signal_v2_<date>.json`, not a stale fixed latest
  path.
- The guarded candidate is run with `--enable`, but target changes still
  require both valid manual signature and an actual defensive trigger.
- Auto rebalance and broker-order output remain blocked.

Verification:

```bash
.venv/bin/python -m pytest \
  tests/test_run_ncf_daily_pipeline.py \
  tests/test_group_a_plus_defensive_cash_floor_guard.py \
  tests/test_build_group_a_plus_defensive_cash_floor_guarded_candidate.py \
  tests/test_defensive_cash_floor_signed_approval_record.py
```

Result: `37 passed`.

Dry-run verification:

```bash
.venv/bin/python scripts/run/run_ncf_daily_pipeline.py \
  --date-stamp 20260807 \
  --skip-refresh \
  --dry-run
```

Result:

- completed dry-run command listing successfully.
- total steps: `89`.
- manifest would be written to `results/ncf_daily_pipeline_20260807.json`.

## Next Steps

1. Add yesterday forecast-vs-actual review JSON into the CLI once that report has a stable path/schema.
2. Keep the adaptive quantile output as a daily shadow diagnostic.
3. On the next real daily pipeline run, inspect
   `report/group_a_plus/latest/defensive_cash_floor_guarded_candidate.json`
   after `daily_signal` refreshes.
4. Continue to block auto rebalance and broker orders; current implementation
   status is `daily_pipeline_wired_enabled_waiting_for_defensive_trigger`.
