# GroupA+ Handoff: 2026-09-02 Prediction Run + 2608.20179 Status Confirmation

- Recorded: 2026-09-02
- Scope: three-variant 9/2 prediction (golden1_0531 / golden2_0830 / latest strategy) +
  re-confirmation that arXiv 2608.20179's review is fully complete.
- Policy: no strategy change, no target-weight change, no production pointer
  overwrite, no order created.

## 1. Data Freshness Check (asked: "已是最新資料?")

Checked at system time `2026-09-01 23:37` (before the date rolled to 09-02):

| table | max(dt) |
| --- | --- |
| `ohlcv` (`0050.TW`) | `2026-08-31` |
| `institutional_data` (`0050.TW`) | `2026-08-31` |
| `taifex_options_daily` (incl. TXO) | `2026-08-31` |

All current through the most recently published trading day. 09-01/09-02's
own data had not yet been published by the external source at check time --
this is the expected T+1 publication lag already established earlier in the
week, not a pipeline problem. Note: the correct options table name is
`taifex_options_daily`, not `taifex_options_data` (a typo caught mid-query).

## 2. 9/2 Prediction, NT$1,000,000, Three Variants

Request: "在groupA+,使用golden1_0531 ,golden2_0830 及最新策略,以1百萬, 預測9/2"

All three runs used the same underlying market data (`actual_data_date =
2026-08-31`, since 09-01/09-02 data was not yet published) with
`requested_as_of_date = 2026-09-02`. All outputs were written to session
scratch files only -- **no production pointer, execution plan, or holdings
file was touched**.

### Commands used

**golden1_0531** (independent Group A signal generator, bypassing the
`run_group_a_combined_signal.py` wrapper to avoid its hardcoded overwrite of
`results/group_a_combined_live_latest.json`; called
`generate_dual_group_signal.py` directly with the wrapper's exact default
parameters):

```
python generate_dual_group_signal.py --group group_a \
  --result-json results/last_ppo_group_a_backtest_20250101_20260531_20260609_214023.json \
  --holdings-row-label 即時庫存 --as-of-date 2026-09-02 --extra-cash 1000000.000000 \
  --action-threshold 0.01 --max-stale-days 3 --max-strategy-drawdown 0.27 \
  --max-underperformance-vs-0050 0.10 --group-a-0050-max-weight-step 0.03 \
  --group-a-0050-step-active-max-ma-ratio 1.05 --group-a-0050-ma-brake-window 60 \
  --group-a-0050-ma-brake-ratio 1.0 --group-a-0050-ma-brake-max-weight 0.30 \
  --group-a-0050-ma-brake-00631l-max-weight 0.0 --live-start
```
Output: `results/signal_group_a_20260901_234803.json` (independently named,
not the `group_a_combined_live_latest.json` pointer).

**golden2_0830** (frozen strategy config, refreshed market data -- per the
2026-08-31 correction that golden2_0830 is a frozen *model/config* snapshot,
not frozen output numbers):

```
python -m group_a_plus.operations.daily_signal --as-of 2026-09-02 \
  --portfolio-value 1000000 \
  --manifest releases/golden2_0830/group_a_plus_strategy_golden2_0830.json \
  --output <scratch>/golden2_0830_predict_20260902.json \
  --latest-pointer <scratch>/golden2_0830_predict_20260902_pointer.json
```

**latest strategy** (current production `strategy.json` manifest, default):

```
python -m group_a_plus.operations.daily_signal --as-of 2026-09-02 \
  --portfolio-value 1000000 \
  --output <scratch>/latest_strategy_predict_20260902.json \
  --latest-pointer <scratch>/latest_strategy_predict_20260902_pointer.json
```

`<scratch>` = session-local scratchpad directory; both `--output` and
`--latest-pointer` were redirected away from
`report/group_a_plus/latest/live_signal.json` (the real production pointer)
to avoid the exact class of accidental-overwrite mistake flagged in prior
session feedback (`feedback_execution_plan_latest_pointer_default_overwrite`).

A best-effort, additive point-in-time snapshot was still written under
`results/ncf_snapshots/2026/08/31/...` by `daily_signal.py`'s normal
snapshotting side effect -- this is expected, non-production, and does not
affect any pointer or strategy file.

### Results

Common to all three: `base_regime`/`execution_regime` = `golden1`
(bull), `action` = `hold_or_align_to_target` /
`rebalance_to_0050_50_00631L_20_cash_30`.

| Asset | golden1_0531 | golden2_0830 | latest strategy |
| --- | ---: | ---: | ---: |
| `0050.TW` | 47.0000% (470,000) | 47.0000% (470,000) | 47.0000% (470,000) |
| `00631L.TW` | 9.8813% (98,813) | 9.8714% (98,714) | 9.8714% (98,714) |
| `00632R.TW` | 16.7139% (167,139) | 16.7139% (167,139) | 16.7139% (167,139) |
| `00679B.TWO` | 0% (0) | 0% (0) | 0% (0) |
| cash | 26.4048% (264,048) | 26.4147% (264,147) | 26.4147% (264,147) |

### Interpretation

- `golden2_0830` and `latest strategy` produced **identical** target weights
  for this date. This is consistent with the governance finding from the
  golden2 promotion review completed 2026-09-01
  (`project_golden2_promotion_review_wiring_fixed_20260901` memory): the two
  only diverge in extended multi-month backtests (`-10.45%` final value gap
  in the `live_2024_2026` / `active_2025_2026` windows); a same-day snapshot
  this close to the 08-30 freeze point shows no divergence yet.
- `golden1_0531`'s small difference from the other two (`00631L` 9.88% vs
  9.87%) is the pre-existing, expected structural gap between golden1's
  independent Group A overlay logic and GroupA+'s (`a2118`) overlay logic --
  not a new finding.
- No target-weight change, no auto-rebalance, no order was created by this
  exercise. All three predictions are read-only what-if snapshots.

## 3. 2608.20179 (Dynamic CVaR Constraint) -- Re-confirmed Fully Complete

Question: "OK,這個論文實驗都做完了?" -- re-verified rather than re-run, per
prior session feedback about checking existing state before redoing work.

Checked live artifacts (both regenerated 2026-08-31, unchanged since):

- `report/group_a_plus/latest/2608_20179_dynamic_cvar_constraint_shadow.json`
  -- `decision.review_complete: true`,
  `decision.best_import: cvar_constraint_residual_and_state_dependent_pacing_shadow`,
  `status: blocked_for_live_promotion`.
- `report/group_a_plus/latest/2608_20179_dynamic_cvar_forward_validation.json`
  -- `decision.review_complete: true`,
  `decision.best_import: forward_validation_for_cvar_residual_shadow_only`,
  `status: blocked_for_live_promotion`.

Both reports agree: `promote_to_live: false`, `target_weight_change_allowed:
false`, `auto_rebalance_allowed: false`, `keep_latest_strategy_unchanged:
true`. The paper contributes a useful shadow-only diagnostic (CVaR residual +
state-dependent 00631L add-pacing multiplier) but does not clear the bar for
live promotion. No further experiments are pending for this paper.

## Still-Open Thread (not started, not requested this session)

Carried over from the 2026-09-01 five-paper review: arXiv 2508.16598
(SPXW put-writing sizing) was left `likely closed_negative` but with one
unverified caveat -- existing TXO liquidity evidence covers option **buying**
(premium-budget constrained) only; option **selling** (margin-constrained)
liquidity was never separately checked. Next step, if picked up: query TXO's
actual bid/ask depth (not just trade volume) at near-month, near-the-money
strikes. Not executed in this session; no action taken.

## Validation

Read-only verification only in this session (data freshness queries, JSON
report inspection, three prediction runs to scratch paths). No test suite
changes; no production files modified. No commit made.
