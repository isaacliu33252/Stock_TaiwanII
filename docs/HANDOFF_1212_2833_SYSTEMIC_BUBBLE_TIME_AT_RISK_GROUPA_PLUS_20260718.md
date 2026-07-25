# Handoff: 1212.2833 Systemic Bubble Time-At-Risk For GroupA+（2026-07-18）

## Objective

Analyze `C:\Users\isaac\Downloads\1212.2833.pdf` and decide whether its useful
ideas can be introduced into the latest GroupA+ strategy and Golden1_0531.

PDF:

- Title: `The Illusion of the Perpetual Money Machine`
- Authors: Didier Sornette and Peter Cauwels
- Paper date: 2012-10-27
- Local file: `C:\Users\isaac\Downloads\1212.2833.pdf`

## Final Decision

Do not change live target weights.

Do not auto-rebalance for `2026-07-20`.

Do not auto-add `00631L`.

Keep `Golden1_0531` unchanged.

The paper contributes useful governance ideas, not a live trading alpha model.
It is now imported as a research-only systemic-risk diagnostic:

- `time_at_risk`
- ETF coupling / network fragility
- market reflexivity proxy
- scenario discipline and ex-post review

## What Was Not Imported

Not imported into live strategy:

- LPPL / bubble model as live trading signal
- macro-debt market timing
- commodity or real-asset allocation shift
- direct `00631L` add
- direct `00632R` hedge
- any 2012 global macro parameter copied into Taiwan ETF weights

Reason: the paper is a macro/systemic-risk white paper. It does not provide a
validated Taiwan ETF allocation rule, transaction-cost model, or local 2026
calibration.

## Implemented Artifact

New research-only evaluator:

- `scripts/evaluate/evaluate_group_a_plus_systemic_bubble_time_at_risk_review.py`

Main outputs:

- `results/group_a_plus_systemic_bubble_time_at_risk_review_20260718.json`
- `report/group_a_plus/latest/systemic_bubble_time_at_risk_review.json`
- `report/group_a_plus/systemic_bubble_time_at_risk/history/20260717.json`

Policy:

- `research_only_systemic_bubble_time_at_risk_no_weight_change`

Hard rule:

- The diagnostic may support manual review or add-blocking evidence.
- It never unlocks execution.
- It never changes target weights.

## Data Inputs

Local DB:

- `FinRL/data/stock_data.db`

Tables used:

- `ohlcv`
  - `0050.TW`
  - `00631L.TW`
  - `00632R.TW`
- `external_market_ohlcv`
  - `2330.TW`, `provider = yfinance`

Important fix completed:

- `2330.TW` is not in the main `ohlcv` table.
- It is available in `external_market_ohlcv`.
- The evaluator now merges both tables and uses `external_market_ohlcv` as
  fallback, so `2330_0050_corr_60d` is populated.

Confirmed local coverage:

- `0050.TW`: `2009-01-02` to `2026-07-17`
- `00631L.TW`: `2015-01-05` to `2026-07-17`
- `00632R.TW`: `2015-01-05` to `2026-07-17`
- `2330.TW`: `2014-01-02` to `2026-07-17` from `external_market_ohlcv`

## Latest Result

Latest diagnostic file:

- `report/group_a_plus/latest/systemic_bubble_time_at_risk_review.json`

As of:

- price data end: `2026-07-17`
- target execution context: `2026-07-20`

Key values:

- `00631l_vol20_ann = 0.7395145955984148`
- `00631l_vol20_percentile_252d = 0.9325396825396826`
- `00631l_vol20_vs_vol60_ratio = 1.127032566628849`
- `0050_return_60d = 0.1598147457511958`
- `0050_ma120_gap = 0.1268318937920867`
- `time_at_risk_days_60 = 42`
- `0050_00631l_corr_60d = 0.9806113566378623`
- `0050_00632r_corr_60d = -0.9779260056912817`
- `2330_0050_corr_60d = 0.8733215293681316`
- `etf_coupling_score = 0.9439529638992444`
- `00631l_volume_z_60d = 4.096768507831392`
- `00631l_abs_return_z_60d = 3.7661828269151503`
- `reflexivity_proxy_score = 2.954317111582181`
- `reflexivity_proxy_percentile_252d = 0.9920634920634921`

States:

- `time_at_risk_state = elevated`
- `etf_coupling_state = watch`
- `reflexivity_proxy_state = elevated`
- `systemic_score = 2`
- `overall_state = blocked_for_leverage_add`

Decision:

- `promote_to_live = false`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `allow_00631l_add = false`
- `keep_golden1_0531_unchanged = true`

## Research Snapshot Integration

Updated:

- `scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py`

Latest output:

- `report/group_a_plus/latest/research_shadow_decision_snapshot.json`

Current snapshot:

- `status = blocked`
- `finstressts_status = blocked`
- `trigate_state = blocked_for_leverage_add`
- `trigate_stress_gate_count = 3`
- `systemic_bubble_state = blocked_for_leverage_add`
- `systemic_bubble_score = 2`
- `allow_00631l_add = false`

Blocking reasons:

- `finstressts_snapshot_blocked`
- `trigate_vol_memory_blocks_leverage_add`
- `systemic_bubble_time_at_risk_blocks_leverage_add`

## Daily Pipeline Integration

Updated:

- `scripts/run/run_ncf_daily_pipeline.py`

New best-effort step:

- `systemic_bubble_time_at_risk_review`

Command output:

- `results/group_a_plus_systemic_bubble_time_at_risk_review_<stamp>.json`
- `report/group_a_plus/latest/systemic_bubble_time_at_risk_review.json`

Placement:

- after `trigate_vol_memory_shadow`
- before `research_shadow_decision_snapshot`

Reason:

- systemic bubble review is a research-only diagnostic that should be available
  before the consolidated research snapshot is built.

## Daily Status Integration

Updated:

- `scripts/misc/check_group_a_plus_daily_status.py`

New CLI argument:

- `--systemic-bubble-time-at-risk-review`

New JSON path:

- `group_a_plus.systemic_bubble_time_at_risk_review`

New Markdown section:

- `## Systemic Bubble Time-At-Risk Review`

Latest generated daily status:

- `results/group_a_plus_daily_status_20260720_systemic_bubble.json`
- `results/group_a_plus_daily_status_20260720_systemic_bubble.md`
- `report/group_a_plus/latest/daily_status.json`

Latest managed reports:

- `report/group_a_plus/daily/html/daily_status_a2118_a2111_ncf_late_bull_deleverage_20260720_20260718_091011.html`
- `report/group_a_plus/daily/json/daily_status_a2118_a2111_ncf_late_bull_deleverage_20260720_20260718_091011.json`
- `report/group_a_plus/daily/md/daily_status_a2118_a2111_ncf_late_bull_deleverage_20260720_20260718_091011.md`
- `report/group_a_plus/daily/meta/daily_status_a2118_a2111_ncf_late_bull_deleverage_20260720_20260718_091011.meta.json`

Daily status now shows:

- `State = blocked_for_leverage_add`
- `00631L add = blocked`
- `Systemic score = 2`
- `Time-at-risk / ETF coupling / reflexivity = elevated / watch / elevated`
- `2330/0050 corr 60d = 0.8733215293681316`
- `ETF coupling score = 0.9439529638992444`

Daily status overall:

- `overall_status = warn`

Reason:

- `data_freshness = warn`
- `2026-07-20` check date vs `2026-07-17` actual data:
  - `1` business day stale
  - `3` calendar days stale

This warning does not unlock or change execution.

## Tests

Added / updated:

- `tests/test_group_a_plus_systemic_bubble_time_at_risk_review.py`
- `tests/test_build_group_a_plus_research_shadow_decision_snapshot.py`
- `tests/test_check_group_a_plus_daily_status.py`
- `tests/test_run_ncf_daily_pipeline.py`

Verified:

- `31 passed`
- `20 passed` in earlier full related run after 2330 fallback
- `py_compile` passed for:
  - `scripts/evaluate/evaluate_group_a_plus_systemic_bubble_time_at_risk_review.py`
  - `scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py`
  - `scripts/misc/check_group_a_plus_daily_status.py`
  - `scripts/run/run_ncf_daily_pipeline.py`

Most recent targeted command:

```bash
.venv/bin/python -m pytest tests/test_check_group_a_plus_daily_status.py tests/test_run_ncf_daily_pipeline.py tests/test_group_a_plus_systemic_bubble_time_at_risk_review.py
```

Result:

- `31 passed`

## Current Strategy Implication For 2026-07-20

Strategy:

- `a2118_a2111_ncf_late_bull_deleverage`

Reference target:

- `0050.TW = 50%`
- `00631L.TW = 20%`
- `00632R.TW = 0%`
- `00679B.TWO = 0%`
- cash = `30%`

Execution conclusion:

- no auto-rebalance
- no new `00631L` add
- no direct `00632R` hedge
- keep `Golden1_0531` unchanged
- keep manual review requirement

The new systemic bubble review strengthens the existing no-add conclusion
because both `time_at_risk_state` and `reflexivity_proxy_state` are elevated.

## Files Changed In This Workstream

Core:

- `scripts/evaluate/evaluate_group_a_plus_systemic_bubble_time_at_risk_review.py`
- `scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py`
- `scripts/run/run_ncf_daily_pipeline.py`
- `scripts/misc/check_group_a_plus_daily_status.py`

Tests:

- `tests/test_group_a_plus_systemic_bubble_time_at_risk_review.py`
- `tests/test_build_group_a_plus_research_shadow_decision_snapshot.py`
- `tests/test_check_group_a_plus_daily_status.py`
- `tests/test_run_ncf_daily_pipeline.py`

Docs:

- `docs/1212_2833_PERPETUAL_MONEY_MACHINE_GROUPA_PLUS_REVIEW_20260718.md`
- `docs/GROUPA_PLUS_PDF_RESEARCH_DECISION_MATRIX_20260717.md`
- `docs/HANDOFF_1212_2833_SYSTEMIC_BUBBLE_TIME_AT_RISK_GROUPA_PLUS_20260718.md`

Generated reports:

- `results/group_a_plus_systemic_bubble_time_at_risk_review_20260718.json`
- `report/group_a_plus/latest/systemic_bubble_time_at_risk_review.json`
- `report/group_a_plus/systemic_bubble_time_at_risk/history/20260717.json`
- `report/group_a_plus/latest/research_shadow_decision_snapshot.json`
- `results/group_a_plus_daily_status_20260720_systemic_bubble.json`
- `results/group_a_plus_daily_status_20260720_systemic_bubble.md`
- `report/group_a_plus/latest/daily_status.json`

## Maintenance Notes

The diagnostic intentionally uses transparent thresholds. It should remain
research-only until enough out-of-sample daily observations exist to evaluate:

- whether it improves crash-window decisions;
- whether it reduces false-positive 00631L add blocks;
- whether it adds information beyond tri-gate volatility memory and FinStressTS.

Potential follow-ups:

- add history scorecard for systemic bubble review;
- compare `systemic_score` with next 1/5/20-day `00631L` drawdown;
- include SOXX / QQQ / TSM / VIX / USD/TWD coupling if a broader cross-market
  panel is desired;
- keep `2330.TW` fallback from `external_market_ohlcv` unless `ohlcv` later
  gains native 2330 rows.

Do not promote this diagnostic to a live weight-changing guard without a
separate walk-forward validation and explicit approval.
