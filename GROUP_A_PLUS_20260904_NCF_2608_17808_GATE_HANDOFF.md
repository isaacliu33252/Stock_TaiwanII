# GroupA+ Handoff: 2026-09-04 -- NCF Refresh, 9/4 Prediction, and 2608.17808 Gate Integration

- Recorded: 2026-09-04 Asia/Taipei
- Workspace:
  `/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main`
- Scope:
  1. Refresh latest GroupA+/NCF data for 2026-09-03.
  2. Run NCF daily pipeline.
  3. Predict 2026-09-04 using `golden1_0531`, `golden2_0830`, and latest strategy with TWD 1,000,000.
  4. Re-check paper `2608.17808_self_consistent_adjoint_policy_iteration_constrained_dynamic_portfolio_choice.pdf`.
  5. Import only the paper's useful point as a research-only daily gate, not as a trading rule.

## Executive State

The 2026-09-04 prediction stays unchanged across all three requested strategies:

| strategy | 0050.TW | 00631L.TW | 00632R.TW | 00679B.TWO | cash |
|---|---:|---:|---:|---:|---:|
| `golden1_0531` | 52.9328% | 17.0672% | 0% | 0% | 30% |
| `golden2_0830` | 52.9328% | 17.0672% | 0% | 0% | 30% |
| latest strategy | 52.9328% | 17.0672% | 0% | 0% | 30% |

TWD 1,000,000 rounded allocation:

| strategy | 0050 shares/value | 00631L shares/value | cash after rounding |
|---|---:|---:|---:|
| `golden1_0531` | 4,984 / 529,300.78 | 4,820 / 170,676.20 | 300,023.02 |
| `golden2_0830` | 4,984 / 529,300.78 | 4,819 / 170,640.79 | 300,058.43 |
| latest strategy | 4,984 / 529,300.78 | 4,819 / 170,640.79 | 300,058.43 |

Price references from 2026-09-03 data:

- `0050.TW`: 106.20
- `00631L.TW`: 35.41
- `00632R.TW`: 10.00
- `00679B.TWO`: 25.77

Important conclusion: no `golden1_0531`, `golden2_0830`, latest strategy,
target-weight, execution-permission, or order-generation change was made.

## Commands Run

Data refresh:

```bash
.venv/bin/python scripts/run/run_ncf_daily_pipeline.py \
  --date-stamp 20260903 \
  --refresh-target-date 2026-09-03 \
  --ohlcv-target-date 2026-09-03 \
  --only-refresh \
  --force-refresh \
  --strict-refresh \
  --fail-on-ohlcv-warning
```

Result: exit 0. Nine ETF OHLCV rows updated to `2026-09-03`.

Full NCF daily pipeline:

```bash
.venv/bin/python scripts/run/run_ncf_daily_pipeline.py \
  --date-stamp 20260903 \
  --ohlcv-target-date 2026-09-03 \
  --skip-refresh \
  --refresh-external-cache
```

Result: exit 0, all 138/138 pipeline steps completed.

Golden1 9/4 prediction:

```bash
.venv/bin/python generate_dual_group_signal.py \
  --group group_a \
  --result-json results/last_ppo_group_a_backtest_20250101_20260531_20260609_214023.json \
  --history-start 2020-01-01 \
  --simulation-start 2025-01-01 \
  --download-end 2026-09-03 \
  --as-of-date 2026-09-04 \
  --live-start \
  --extra-cash 1000000 \
  --override-holdings-json results/holdings_zero_for_1m_predict_20260903.json \
  --group-a-0050-max-weight-step 0.03 \
  --group-a-0050-step-active-max-ma-ratio 1.05 \
  --group-a-0050-ma-brake-window 60 \
  --group-a-0050-ma-brake-max-weight 0.3 \
  --group-a-0050-ma-brake-00631l-max-weight 0.0
```

Golden2 9/4 prediction:

```bash
.venv/bin/python -m group_a_plus.operations.daily_signal \
  --as-of 2026-09-04 \
  --portfolio-value 1000000 \
  --manifest releases/golden2_0830/group_a_plus_strategy_golden2_0830.json \
  --output results/golden2_0830/group_a_plus_live_signal_v2_golden2_0830_predict_20260904_from_20260903_total_1m.json \
  --latest-pointer results/golden2_0830/group_a_plus_live_signal_v2_golden2_0830_predict_20260904_from_20260903_total_1m.pointer.json
```

Latest-strategy 9/4 prediction:

```bash
.venv/bin/python -m group_a_plus.operations.daily_signal \
  --as-of 2026-09-04 \
  --portfolio-value 1000000 \
  --manifest report/group_a_plus/latest/strategy.json \
  --output results/group_a_plus_live_signal_v2_predict_20260904_from_20260903_total1000000_latest_strategy.json \
  --latest-pointer results/group_a_plus_live_signal_v2_predict_20260904_from_20260903_total1000000_latest_strategy.pointer.json
```

New 2608.17808 gate:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_current_policy_re_evaluation_gate.py
```

Paper convergence rebuild:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_paper_convergence_review.py --as-of 2026-09-03
```

## NCF Snapshot

Pipeline manifest:

- `results/ncf_daily_pipeline_20260903.json`

Pipeline signal summary:

| ticker | last close date | close | direction | prob up | calibrated prob up | confidence | freshness |
|---|---|---:|---|---:|---:|---:|---|
| `00631L.TW` | 2026-09-03 | 35.41 | UP | 0.5941 | 0.5722 | 0.6670 | `degraded_stale` |
| `00632R.TW` | 2026-09-03 | 10.00 | DOWN | 0.2818 | 0.3222 | 0.7352 | `degraded_stale` |
| `0050.TW` | 2026-09-03 | 106.20 | UP | 0.5519 | 0.5327 | 0.4709 | `degraded_stale` |

Freshness note:

- ETF NCF freshness is `degraded_stale` because `external_market_ohlcv`
  is stale at `2026-08-28`.
- Core ETF OHLCV and institutional data are at `2026-09-03`.
- Margin/market-margin and TAIFEX sources are at `2026-09-02`.
- TDCC shareholding is at `2026-08-28`.

Additional NCF horizon details reported during the session:

| ticker | horizon | target date | direction | prob up | pred ret | pred close | val AUC | best model |
|---|---:|---|---|---:|---:|---:|---:|---|
| `00631L.TW` | 1d | 2026-09-04 | UP | 0.6058 | -0.00059 | 35.3891 | 0.5719 | cat |
| `00631L.TW` | 5d | 2026-09-10 | UP | 0.5816 | -0.00434 | 35.2563 | 0.6170 | cat |
| `00631L.TW` | 20d | 2026-10-01 | UP | 0.6005 | 0.029324 | 36.4484 | 0.6823 | et |
| `00632R.TW` | 1d | 2026-09-04 | DOWN | 0.2756 | 0.009079 | 10.0908 | 0.5182 | rf |
| `00632R.TW` | 5d | 2026-09-10 | DOWN | 0.3577 | 0.045224 | 10.4522 | 0.6302 | hgb |
| `00632R.TW` | 20d | 2026-10-01 | DOWN | 0.2402 | 0.150000 | 11.5000 | 0.7390 | stable_rf |
| `0050.TW` | 1d | 2026-09-04 | NEUTRAL | 0.5414 | -0.001148 | 106.0781 | 0.5644 | et |
| `0050.TW` | 5d | 2026-09-10 | NEUTRAL | 0.4730 | -0.002860 | 105.8963 | 0.5807 | rf |
| `0050.TW` | 20d | 2026-10-01 | UP | 0.5864 | 0.006643 | 106.9055 | 0.6622 | et |
| `2330.TW` | 1d | 2026-09-04 | DOWN | 0.4807 | 0.001809 | 2394.3247 | 0.7351 | gb |
| `2330.TW` | 5d | 2026-09-10 | UP | 0.5585 | 0.006984 | 2406.6908 | 0.6452 | et |
| `2330.TW` | 20d | 2026-10-01 | UP | 0.7067 | 0.027294 | 2455.2333 | 0.6777 | et |

## 2608.17808 Review State

The paper:

`C:\Users\isaac\Downloads\2608.17808_self_consistent_adjoint_policy_iteration_constrained_dynamic_portfolio_choice.pdf`

Repository copy:

- `research/papers/2608.17808_self_consistent_adjoint_policy_iteration_constrained_dynamic_portfolio_choice.pdf`

Prior detailed review handoff:

- `GROUP_A_PLUS_20260903_2608_17808_ADJOINT_POLICY_ITERATION_HANDOFF.md`

Desk-review verdict remains `closed_negative` for production strategy import:

- Full adjoint/HJB/SDE policy iteration is not suitable for GroupA+ production.
- The paper is synthetic/continuous-time/parametric-factor-model based.
- GroupA+ is empirical, ETF-constrained, and already uses on-policy PPO-style
  evaluation where appropriate.
- The tested half-step damping idea reduced turnover but worsened Sharpe and
  did not improve max drawdown.

The useful transferable point is narrower:

> Current-policy re-evaluation is useful only as a research-only validation
> and promotion gate: re-evaluate the existing policy under perturbed inputs,
> compare active-set stability, compare against frozen-policy matched-budget
> checks, and require tail-bank confirmation before considering promotion.

That point is now implemented.

## New Files Added

Script:

- `scripts/evaluate/build_group_a_plus_current_policy_re_evaluation_gate.py`

Test:

- `tests/test_build_group_a_plus_current_policy_re_evaluation_gate.py`

Latest outputs:

- `report/group_a_plus/latest/current_policy_re_evaluation_gate.json`
- `report/group_a_plus/latest/current_policy_re_evaluation_gate.md`

Paper convergence history output:

- `report/group_a_plus/paper_convergence_review/history/paper_convergence_review_20260903.json`

This handoff:

- `GROUP_A_PLUS_20260904_NCF_2608_17808_GATE_HANDOFF.md`

## Existing Files Updated

Pipeline:

- `scripts/run/run_ncf_daily_pipeline.py`
  - Added best-effort step `current_policy_re_evaluation_gate`.
  - Step is scheduled after `riccati_mv_shadow`.
  - Step writes only `report/group_a_plus/latest/current_policy_re_evaluation_gate.{json,md}`.
  - Manifest output map now includes both gate artifacts.
  - `paper_convergence_review` command now receives `--re-evaluation-gate`.

Paper convergence:

- `group_a_plus/integrations/paper_convergence_review.py`
  - Added candidate `current_policy_re_evaluation_gate_2608_17808`.
  - Candidate is scored as `review_context_only` while gate/tail-bank blockers remain.
  - It is ranked as paper-import review context, not as live alpha.

- `scripts/evaluate/build_group_a_plus_paper_convergence_review.py`
  - Added default input:
    `report/group_a_plus/latest/current_policy_re_evaluation_gate.json`.
  - Added CLI arg `--re-evaluation-gate`.
  - Added source tracking for `re_evaluation_gate`.

Tests:

- `tests/test_run_ncf_daily_pipeline.py`
  - Added pipeline order and best-effort assertions for `current_policy_re_evaluation_gate`.

- `tests/test_group_a_plus_paper_convergence_review.py`
  - Added assertion that 2608.17808 gate appears as shadow-only context.

- `tests/test_build_group_a_plus_paper_convergence_review.py`
  - Added wrapper/source-map coverage for `re_evaluation_gate`.

Latest reports regenerated:

- `report/group_a_plus/latest/current_policy_re_evaluation_gate.json`
- `report/group_a_plus/latest/current_policy_re_evaluation_gate.md`
- `report/group_a_plus/latest/paper_convergence_review.json`
- `report/group_a_plus/paper_convergence_review/history/paper_convergence_review_20260903.json`

## Current 2608.17808 Gate Output

From `report/group_a_plus/latest/current_policy_re_evaluation_gate.json`:

```json
{
  "decision": {
    "promotion_allowed": false,
    "decision": "keep_shadow_do_not_promote",
    "blockers": [
      "error_certificate_not_blocked",
      "stability_tuned_gate_active",
      "tail_bank_promotion_allowed"
    ]
  }
}
```

Checks:

| check | pass |
|---|---:|
| `shadow_report_ok` | true |
| `research_only_policy` | true |
| `two_pass_stable_within_grid_step` | true |
| `active_set_stable` | true |
| `matched_budget_supported` | true |
| `error_certificate_not_blocked` | false |
| `stability_tuned_gate_active` | false |
| `cap_only_reduces_volatility` | true |
| `tail_bank_available` | true |
| `tail_bank_promotion_allowed` | false |

Evidence:

- Two-pass L1 drift second-minus-first: `0.000000`
- Active-set verdict: `stable_active_set`
- Active-set stability ratio: `1.0`
- Matched-budget verdict: `current_policy_re_evaluation_supported`
- Error decomposition verdict: `diagnostic_blocked`
- Error decomposition blockers:
  - `expected_return_source_stale_or_missing`
  - `stability_tuned_gate_inactive`
- Cap-only annualized volatility reduction: `0.04508673986992667`
- Tail-bank decision: `do_not_promote_keep_shadow`
- Best tail-bank candidate: `cap631_tail2_dd10_vol125_beta05`

Interpretation:

The paper concept is useful as an audit layer, but the live promotion gate is
closed. It must remain shadow-only.

## Current Paper Convergence State

From `report/group_a_plus/latest/paper_convergence_review.json`:

- `top_candidate_id`: `defensive_cash_floor_high_risk_state`
- `top_candidate_decision`: `best_candidate_but_signed_review_blocked`
- `target_weight_change_allowed`: false
- `auto_rebalance_allowed`: false
- `allow_00631l_add`: false
- `allow_00632r_open`: false
- `promote_to_live`: false

2608.17808 candidate entry:

- `candidate_id`: `current_policy_re_evaluation_gate_2608_17808`
- `decision`: `review_context_only`
- `scores.total`: `0.547`
- blockers:
  - `research_only_no_weight_change`
  - `error_certificate_not_blocked`
  - `stability_tuned_gate_active`
  - `tail_bank_promotion_allowed`

This is intentional: 2608.17808 should be visible in the paper convergence
dashboard, but it should not compete as a live strategy candidate while the
tail-bank and error-certificate checks fail.

## Validation

First focused test run after adding the standalone gate:

```bash
.venv/bin/python -m pytest \
  tests/test_build_group_a_plus_current_policy_re_evaluation_gate.py \
  tests/test_build_group_a_plus_2608_17808_tail_bank_review.py \
  tests/test_group_a_plus_riccati_mv_shadow.py \
  tests/test_run_ncf_daily_pipeline.py \
  -q
```

Result:

- `42 passed in 54.98s`

Second focused test run after connecting the gate into paper convergence:

```bash
.venv/bin/python -m pytest \
  tests/test_build_group_a_plus_current_policy_re_evaluation_gate.py \
  tests/test_group_a_plus_paper_convergence_review.py \
  tests/test_build_group_a_plus_paper_convergence_review.py \
  tests/test_run_ncf_daily_pipeline.py \
  -q
```

Result:

- `31 passed in 51.70s`

One intermediate test failed because the first blocked-gate score still put
2608.17808 in `research_candidate_needs_validation`. The implementation was
made more conservative so a blocked tail-bank/current-policy gate is ranked
`review_context_only`; the re-run passed.

## Dirty Worktree Warning

The repository was already dirty before this handoff. Some files shown by
`git diff`/`git status` include unrelated prior work. Do not revert anything
unless the user explicitly asks.

Files directly touched by this session are listed above. In particular, there
are pre-existing large modifications in `scripts/run/run_ncf_daily_pipeline.py`
and `tests/test_run_ncf_daily_pipeline.py`; this session only added the
`current_policy_re_evaluation_gate` pieces around `riccati_mv_shadow` and
paper-convergence wiring.

## Do Not Do Next

- Do not promote 2608.17808 to production weights.
- Do not change `golden1_0531`.
- Do not change `golden2_0830`.
- Do not change latest strategy target weights based on this paper.
- Do not create execution orders from the current-policy gate.
- Do not treat `cap_only_reduces_volatility=true` as sufficient; it is blocked
  by the tail-bank and error-certificate checks.

## Reasonable Next Steps

1. Run the normal daily pipeline for 2026-09-04 after the market data is
   available, then confirm `current_policy_re_evaluation_gate` appears in the
   new pipeline manifest.
2. Accumulate daily gate history before considering any manual review.
3. If revisiting 2608.17808 later, require all of:
   - tail-bank `promotion_allowed=true`;
   - error decomposition not `diagnostic_blocked`;
   - stability-tuned gate active;
   - active-set stability still passing;
   - matched-budget comparator still supported;
   - independent OOS/stress windows not degrading Sharpe/drawdown.
4. Prefer defensive cash floor work over 2608.17808 for near-term improvement,
   because current paper convergence still ranks it as the closest candidate,
   although it remains signed-review blocked.
