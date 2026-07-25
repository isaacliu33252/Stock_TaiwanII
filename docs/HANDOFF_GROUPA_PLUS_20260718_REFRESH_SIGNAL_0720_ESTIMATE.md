# GroupA+ Handoff - 2026-07-18 Refresh / Signal / 2026-07-20 Estimate

## Scope

This handoff records the work completed on `2026-07-18` after the user asked
to download the latest data, continue the GroupA+ workflow, rebuild signals,
check execution guards, and estimate `2026-07-20`.

Timezone / date context:

- Current date: `2026-07-18`
- `2026-07-18` is Saturday
- Latest available Taiwan market trading date used by the workflow:
  `2026-07-17`
- Forward estimate requested by user: `2026-07-20`

## Data Refresh

Refresh completed and verified.

Main refreshed artifacts:

- `results/data_refresh_20260718.json`
- `results/cross_market_ohlcv_stale_external_20260718.json`
- `results/ohlcv_freshness_20260718.json`
- `report/group_a_plus/latest/ops_health.json`
- `docs/DATA_FRESHNESS_AUDIT_20260718.md`

Freshness result:

- `results/ohlcv_freshness_20260718.json`
- `target_date = 2026-07-17`
- `overall_status = warning`
- `error_tickers = []`
- `external_error_tickers = []`

Important table status after refresh:

| Source | Max date | Status |
| --- | ---: | --- |
| `ohlcv` | `2026-07-17` | refreshed |
| `institutional_data` | `2026-07-17` | refreshed |
| `margin_data` | `2026-07-17` | refreshed |
| `market_margin_data` | `2026-07-17` | refreshed |
| `securities_lending_data` | `2026-07-17` | refreshed |
| `foreign_shareholding_data` | `2026-07-17` | refreshed |
| `short_sale_balance_data` | `2026-07-17` | refreshed |
| `day_trading_data` | `2026-07-17` | refreshed |
| `derivative_institutional_data` | `2026-07-17` | refreshed |
| `dealer_futures_data` | `2026-07-17` | refreshed |
| `dealer_options_data` | `2026-07-17` | refreshed |
| `external_options_iv` | `2026-07-17` | refreshed |
| `taifex_futures_daily` | `2026-07-16` | latest fetched |
| `taifex_futures_institutional` | `2026-07-16` | latest fetched |
| `taifex_options_daily` | `2026-07-16` | latest fetched |
| `shareholding_distribution` | `2026-07-09` | lower-frequency source |

External market OHLCV after explicit补抓:

- `^GSPC`: `2026-07-17`
- `^IXIC`: `2026-07-17`
- `^IRX`: `2026-07-17`
- `^TNX`: `2026-07-17`
- `GC=F`: `2026-07-17`
- `2330.TW`: `2026-07-17`
- `TSM`: `2026-07-17`
- `^VIX`: `2026-07-17`
- `QQQ`: `2026-07-17`
- `SOXX`: `2026-07-17`
- `TWD=X`: `2026-07-17`
- `^TWII`: `2026-07-16`, accepted by freshness policy

Remaining data caveats:

- Taiwan raw parquet cache warnings remain for some ETF `close` fields on
  target date, but DB OHLCV is current.
- TAIFEX daily futures/options tables did not provide `2026-07-17` rows in the
  refresh source.
- TDCC shareholding distribution remains lower-frequency.

## NCF / Signal Rebuild

The full NCF stack was rebuilt after the data refresh. The initial full pipeline
was manually interrupted at `ncf_00632r` because stdout did not flush for a long
period. The interrupted state was not used as final output. `ncf_00632r.py` and
`ncf_2330.py` were then run directly with unbuffered output and completed
successfully.

Generated artifacts:

- `results/ncf_00631l_latest_20260718.json`
- `results/ncf_00631l_panel_latest_20260718.csv`
- `results/ncf_00632r_latest_20260718.json`
- `results/ncf_00632r_panel_latest_20260718.csv`
- `results/ncf_2330_latest_20260718.json`
- `results/ncf_2330_panel_latest_20260718.csv`
- `results/ncf_panel_manifest_20260718.json`
- `results/ncf_panel_coverage_20260718.json`
- `results/ncf_advisory_panel_latest_20260718.csv`
- `results/group_a_plus_factor_lens_20260718.json`
- `results/group_a_plus_live_signal_v2_20260718.json`
- `report/group_a_plus/latest/live_signal.json`

Panel coverage:

| Panel | Status | Panel end | Latest source date | Gap |
| --- | --- | ---: | ---: | ---: |
| `00631L.TW` | pass | `2026-07-17` | `2026-07-17` | `0` business days |
| `00632R.TW` | pass | `2026-07-17` | `2026-07-17` | `0` business days |
| `2330.TW` | pass | `2026-07-17` | `2026-07-17` | `0` business days |

NCF latest ensemble summary:

| Model | Date | Direction | Prob up | Calibrated prob up | Confidence | Weighted return |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| `00631L` | `2026-07-17` | `UP` | `0.5101` | `0.5055` | `0.3485` | `-0.6190%` |
| `00632R` | `2026-07-17` | `UP` | `0.5204` | `0.5122` | `0.4278` | `+2.0023%` |
| `2330` | `2026-07-17` | `UP` | `0.5321` | `0.5162` | `0.2923` | `-0.3351%` |

Interpretation:

- The NCF labels are not strong enough to justify a new leverage add.
- `00631L` and `2330` have low confidence and negative weighted return despite
  ensemble direction being `UP`.
- `00632R` has positive weighted return, but H1/H5 direction is `DOWN`; the
  ensemble is supported mainly by H20, so it is not a clean near-term hedge
  signal.

## Daily Status / Alignment / Risk

Generated / updated:

- `results/group_a_plus_daily_status_20260718.json`
- `report/group_a_plus/latest/daily_status.json`
- `report/group_a_plus/latest/signal_alignment.json`
- `report/group_a_plus/latest/crash_risk_alert.json`
- `report/group_a_plus/latest/alert_state.json`
- `report/group_a_plus/latest/deployment_consistency_review.json`
- `report/group_a_plus/latest/ops_health.json`

Daily status after rebuilding the live signal:

- `overall_status = warn`
- `execution_allowed = ok` at live-signal level
- `data_freshness = warn` because latest market date is `2026-07-17` and
  check date is Saturday `2026-07-18`
- `source_freshness = ok`
- `cash_constraint = ok`

Signal alignment:

- `alignment = wide_divergence`
- `dominant_direction = bullish`
- `confidence_penalty = 0.25`
- leverage suitability tier: `1`
- leverage suitability label: `只適合 0050`
- action: `0050_only`
- policy reason: risk is elevated / breadth is narrow; do not add leverage

Compounding regime:

- Source: `results/00631l_leveraged_compounding_regime_20260718.json`
- Latest date: `2026-07-17`
- `compounding_regime = MEAN_REVERTING`
- `recommended_policy = prohibit_new_leverage_or_reduce_rebalance_frequency`

Crash-risk alert:

- Source: `report/group_a_plus/latest/crash_risk_alert.json`
- `as_of = 2026-07-17`
- `watch_level = watch`
- `alert_active = false`
- `category_score = 1`
- manual recommendation: `watch_only_no_action`

DFL advisory:

- Source: `report/group_a_plus/latest/a2118_dfl_advisory.json`
- `action = KEEP`
- `advisory_active = false`
- shadow ensemble level: `none`

Ops health:

- `status = warning`
- `errors = []`
- warnings include system/artifact/external freshness warnings, but no hard
  external ticker error remains.

## Execution Plan Guard Check

The execution plan was rebuilt after the refreshed live signal.

Important caveat:

- Workbook: `taiwan_stock_20260619.xlsx`
- Parsed holdings:
  - `0050.TW = 1342`
  - `00631L.TW = 0`
  - `00632R.TW = 0`
  - `00679B.TWO = 5000`
- Cash input used: `0`
- This is a conservative guard-check only. The workbook has no cash field, so
  this should not be treated as a cash-accurate broker order plan without the
  real cash balance.

Generated / updated:

- `results/group_a_plus_execution_plan_v2_20260718_cash0_guard_check.json`
- `report/group_a_plus/latest/execution_plan.json`

Execution-plan result:

- `requested_as_of_date = 2026-07-18`
- `actual_data_date = 2026-07-17`
- `planning_status = manual_review_required`
- `execution_allowed = false`
- guard reason: turnover ratio `50.06%` exceeds automatic limit `50.00%`

Targets from conservative cash-0 guard-check:

| Field | Shares |
| --- | ---: |
| theoretical `00631L.TW` target | `1670` |
| staged `00631L.TW` target before guards | `668` |
| final `00631L.TW` target after guards | `0` |

Pre-trade guards:

- `volatility_gate_no_00631l_add = blocked`
- `compounding_regime_no_00631l_add = blocked`
- `risk_add_pre_trade_guard = inactive`
- blocked `00631L` buy: `668` shares
- estimated blocked notional: `21,489.56`

Post-plan daily status:

- `overall_status = warn`
- `execution_plan_pre_trade_guard = ok`
- detail: `pre_trade_guards=blocked,blocked`

Deployment consistency review:

- `status = manual_review_required`
- `broker_actionable = false`
- warning reasons:
  - `cash_balance_zero_with_nonzero_trades`
  - `execution_plan_not_allowed`
  - `manual_confirmation_required`
- this is diagnostic only and does not change target weights

Execution conclusion:

- Do not rebalance automatically.
- Do not buy `00631L`.
- A real cash balance is required before producing a broker-actionable
  execution plan.

## 2026-07-20 Estimate

The user requested an estimate for `2026-07-20`. This estimate uses the latest
rebuilt NCF outputs based on `2026-07-17` close.

Post-refresh final update:

- A later full pipeline run for `20260720` completed `52 / 52` steps.
- Final decision record:
  `docs/GROUPA_PLUS_20260720_FULL_PIPELINE_FINAL_DECISION_RECORD.md`
- Fresh manifest:
  `results/ncf_daily_pipeline_20260720.json`
- Fresh live signal:
  `results/group_a_plus_live_signal_v2_20260720.json`
- Fresh daily status:
  `results/group_a_plus_daily_status_20260720.json`
- Data-layer state improved:
  - `execution_allowed = true`
  - `source_freshness = ok`
  - daily status `overall_status = warn`
- Governance state remained restrictive:
  - dynamic CVaR readiness `blocked`
  - research shadow snapshot `blocked`
  - deployment consistency `manual_review_required`
  - promotion gate `blocked_multi_window`

Therefore the post-refresh final decision remains: do not auto-rebalance, do not
add `00631L`, do not open a direct `00632R` hedge, and do not change
Golden1_0531.

H1 forecasts:

| Ticker | 2026-07-17 close | 2026-07-20 H1 predicted close | H1 direction | H1 probability up | H1 predicted return |
| --- | ---: | ---: | --- | ---: | ---: |
| `00631L.TW` | `32.17` | `32.1129` | `DOWN` | `0.4004` | `-0.1776%` |
| `00632R.TW` | `10.83` | `11.0307` | `DOWN` | `0.3944` | `+1.8528%` |
| `2330.TW` | `2290.00` | `2277.8396` | `DOWN` | `0.2128` | `-0.5310%` |

H1 confidence / quality notes:

- `00631L`: H1 points down and H20 also points down; ensemble `UP` is low
  confidence and not supported by weighted return.
- `00632R`: regression points higher, but classification direction is `DOWN`;
  signal is mixed.
- `2330`: H1 is clearly bearish, with better H1 AUC than ETF models. This does
  not support aggressive `0050/00631L` risk-on action for `2026-07-20`.

2026-07-20 decision:

- Bias: conservative / defensive.
- Do not add `00631L`.
- Do not auto-rebalance.
- Keep GroupA+ / Golden1_0531 unchanged unless the user provides real cash and
  explicitly requests a manual execution-plan recalculation.

## Commands Worth Reusing

Data freshness:

```bash
.venv/bin/python scripts/misc/check_ohlcv_freshness.py --target-date auto --max-db-lag-days 3 --output results/ohlcv_freshness_20260718.json
```

External stale ticker补抓:

```bash
.venv/bin/python scripts/fetch/fetch_cross_market_ohlcv.py --tickers '^GSPC,^IXIC,^IRX,^TNX,GC=F,^TWII,2330.TW' --start 2023-07-19 --end 2026-07-19 --output results/cross_market_ohlcv_stale_external_20260718.json
```

NCF direct reruns:

```bash
.venv/bin/python -u ncf_00632r.py --train-start 2015-01-01 --val-start 2025-01-02 --val-end latest --output results/ncf_00632r_latest_20260718.json --val-predictions-output results/ncf_00632r_panel_latest_20260718.csv --full-panel
.venv/bin/python -u ncf_2330.py --train-start 2015-01-01 --val-start 2025-01-02 --val-end latest --output results/ncf_2330_latest_20260718.json --val-predictions-output results/ncf_2330_panel_latest_20260718.csv --full-panel --feature-mode after_close
```

Execution guard-check:

```bash
.venv/bin/python -m group_a_plus.operations.execution_plan --workbook taiwan_stock_20260619.xlsx --as-of 2026-07-18 --cash-balance 0 --compounding-regime results/00631l_leveraged_compounding_regime_20260718.json --output results/group_a_plus_execution_plan_v2_20260718_cash0_guard_check.json --latest-pointer report/group_a_plus/latest/execution_plan.json
```

Daily status after guard-check:

```bash
.venv/bin/python scripts/misc/check_group_a_plus_daily_status.py --mode live --live-signal results/group_a_plus_live_signal_v2_20260718.json --execution-plan report/group_a_plus/latest/execution_plan.json --compounding-regime results/00631l_leveraged_compounding_regime_20260718.json --dfl-advisory report/group_a_plus/latest/a2118_dfl_advisory.json --dfl-shadow-ensemble report/group_a_plus/latest/a2118_dfl_shadow_ensemble.json --dfl-active-date-audit results/a2118_dfl_active_date_audit_20260718.json --finstressts-decision-snapshot report/group_a_plus/latest/finstressts_decision_snapshot.json --trigate-vol-memory-shadow report/group_a_plus/latest/trigate_vol_memory_shadow.json --research-shadow-decision-snapshot report/group_a_plus/latest/research_shadow_decision_snapshot.json --check-date 2026-07-18 --output-prefix results/group_a_plus_daily_status_20260718
```

## Final Decision State

As of this handoff:

- Latest data is refreshed enough for evaluation.
- NCF panels are aligned to `2026-07-17`.
- Live signal is rebuilt.
- Execution plan pre-trade guards are aligned and active.
- `00631L` buy is blocked.
- Automatic rebalance is not allowed.
- For `2026-07-20`, maintain defensive posture and do not add leverage.
