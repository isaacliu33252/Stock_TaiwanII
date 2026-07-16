# GroupA+ Volatility Pre-Trade Guard Handoff - 2026-07-10

## 一句話

已把 volatility / regime 研究導入 GroupA+ 的 live safety rail：高波動時提醒並阻擋新增 `00631L.TW`，但不自動減碼、不改 `target_weights`，目前不能宣稱提升績效。

## 導入狀態

已導入：

- Daily signal alert
  - `volatility_gate_high_vol`
  - `metadata.allow_00631l_add=false`
  - `trade_policy=advisory_no_auto_weight_change`
- Execution plan
  - `group_a_plus/operations/execution_guard.py`
  - `pre_trade_guard`
  - 只阻擋 `00631L.TW` 新增部位
  - 不阻擋持有、不阻擋減碼、不阻擋其他 ticker
- Daily status / report
  - HTML / Markdown 顯示 `Pre-Trade Guard`
  - 顯示 `00631L Add: blocked/allowed`
- Ops health
  - `artifact_health.volatility_gate_execution_guard`
  - high-vol active 時檢查 execution plan 是否對齊且 guard 是否生效
- Push notification
  - high-vol alert 會顯示 `00631L add: blocked`

未導入：

- 沒有把 high-vol gate 變成自動減碼
- 沒有套用 `reference_00631l_scale=0.5` 到實際權重
- 沒有 promotion 成績效提升策略

## 主要檔案

Core:

- `group_a_plus/integrations/garch_regime_shadow.py`
- `group_a_plus/operations/daily_signal.py`
- `group_a_plus/operations/execution_guard.py`
- `group_a_plus/operations/execution_plan.py`
- `group_a_plus/operations/ops_health.py`
- `group_a_plus_report_manager.py`
- `scripts/misc/check_group_a_plus_daily_status.py`
- `scripts/run/run_ncf_daily_pipeline.py`

Evaluation:

- `scripts/evaluate/evaluate_group_a_plus_volatility_gate_shadow.py`
- `scripts/evaluate/evaluate_group_a_plus_volatility_pretrade_guard.py`
- `scripts/evaluate/evaluate_group_a_plus_volatility_pretrade_guard_sweep.py`
- `scripts/evaluate/evaluate_group_a_plus_volatility_guard_holdings_scenarios.py`

Tests:

- `tests/test_group_a_plus_garch_regime_shadow.py`
- `tests/test_evaluate_group_a_plus_volatility_gate_shadow.py`
- `tests/test_evaluate_group_a_plus_volatility_pretrade_guard.py`
- `tests/test_evaluate_group_a_plus_volatility_pretrade_guard_sweep.py`
- `tests/test_evaluate_group_a_plus_volatility_guard_holdings_scenarios.py`
- `tests/test_group_a_plus_execution_guard.py`
- `tests/test_group_a_plus_execution_plan_v2.py`
- `tests/test_group_a_plus_report_manager.py`
- `tests/test_check_group_a_plus_daily_status.py`
- `tests/test_group_a_plus_ops_health.py`

## 回測與 replay 結論

### 自動調倉 variants

不建議 promotion。

代表結果：

| Window | Variant | Delta final value | Delta Sharpe | 判斷 |
|---|---:|---:|---:|---|
| live_2024_2026 | vol_gate_high_only | -178,364 | +0.0687 | 不採用 |
| live_2024_2026 | vol_gate_tiered | -230,521 | +0.0622 | 不採用 |
| live_2024_2026 | vol_gate_confirmed_high_no_trade | -152,904 | +0.0074 | 不採用 |
| active_2025_2026 | vol_gate_high_only | -117,809 | +0.0548 | 不採用 |
| active_2025_2026 | vol_gate_tiered | -152,727 | +0.0400 | 不採用 |
| active_2025_2026 | vol_gate_confirmed_high_no_trade | -109,690 | +0.0515 | 不採用 |

結論：Sharpe 偶爾小幅改善，但 final value 損失太大，不能升級為自動減碼/調倉。

### Pre-trade no-add guard replay

輸出：

- `results/group_a_plus_volatility_pretrade_guard_shadow_20260709.json`
- `results/group_a_plus_volatility_pretrade_guard_shadow_20260709.csv`

結果：

| Window | High-vol days | High-vol rebalance days | Blocked days |
|---|---:|---:|---:|
| covid_2020 | 9 | 0 | 0 |
| inflation_2022 | 34 | 0 | 0 |
| live_2024_2026 | 97 | 0 | 0 |
| active_2025_2026 | 51 | 0 | 0 |

結論：歷史 high-vol days 不少，但沒有剛好落在 A21.18 rebalance day，所以 regime-level replay 無 blocked case。

### Threshold sweep

輸出：

- `results/group_a_plus_volatility_pretrade_guard_threshold_sweep_20260710.json`
- `results/group_a_plus_volatility_pretrade_guard_threshold_sweep_20260710.csv`

掃描：

- ratio threshold: `1.05, 1.10, 1.15, 1.20, 1.25, 1.30`
- percentile threshold: `0.55, 0.60, 0.65, 0.70, 0.75, 0.80`
- require negative 5d: `true / false`
- 72 組

最佳 overlap：

- ratio `1.05`
- percentile `0.70`
- require negative 5d `false`
- high-vol days `536`
- high-vol rebalance days `2`
- blocked days `0`

結論：不建議調鬆 production threshold；只會增加 alert burden，沒有增加可驗證 blocked case。

### Live dry-run

命令：

```bash
.venv/bin/python -m group_a_plus.operations.execution_plan \
  --as-of 2026-07-09 \
  --cash-balance 0 \
  --output results/group_a_plus_execution_plan_dry_run_20260709.json \
  --latest-pointer /tmp/group_a_plus_execution_plan_dry_run_20260709_latest.json
```

結果：

- `actual_data_date=2026-07-09`
- `execution_regime=golden1`
- `pre_trade_guard.status=blocked`
- current `00631L.TW = 0`
- requested target `00631L.TW = 476`
- guarded target `00631L.TW = 0`
- trades 中沒有 00631L 買單

注意：`--cash-balance 0` 只作管線驗證，不代表實際下單現金假設。

### Current holdings scenario grid

輸出：

- `results/group_a_plus_volatility_guard_holdings_scenarios_20260710.json`
- `results/group_a_plus_volatility_guard_holdings_scenarios_20260710.csv`

source plan:

- `results/group_a_plus_execution_plan_dry_run_20260709.json`

結果：

| Current 00631L | Requested target | Guarded target | Status | Blocked shares |
|---:|---:|---:|---|---:|
| 0 | 476 | 0 | blocked | 476 |
| 100 | 476 | 100 | blocked | 376 |
| 250 | 476 | 250 | blocked | 226 |
| 476 | 476 | 476 | active_allowed | 0 |
| 600 | 476 | 476 | active_allowed | 0 |
| 1000 | 476 | 476 | active_allowed | 0 |
| 1192 | 476 | 476 | active_allowed | 0 |

結論：guard 符合設計。低於 requested target 時禁止新增；已達或高於 target 時允許減碼。

## 最新測試

最近較寬回歸：

```text
159 passed, 3 warnings
```

較小套件：

```text
44 passed
43 passed
```

warnings 仍是 `backtest_group_a_plus_switch_policy.py:530` pandas `FutureWarning`，與本輪 guard 邏輯無關。

## 目前風險與注意事項

- 不能宣稱 volatility gate 改善績效。
- 它目前是 live safety rail，不是 alpha 模組。
- 正式 latest live signal 曾停在 `2026-07-08`，dry-run 是 `2026-07-09`；做正式 execution review 時要確認日期對齊。
- execution plan 需要人工 workbook / cash balance，daily pipeline 不自動生成正式 execution plan。
- ops health 仍會因磁碟空間等 system resource 問題報 error，這不是 guard 邏輯錯誤。

## 下一步建議

1. 保持現有 production threshold，不調鬆。
2. 每次正式下單前重跑 execution plan，使用正確 workbook 與 cash balance。
3. 若 high-vol gate active，確認 `pre_trade_guard.allow_00631l_add=false` 且 execution plan 日期/策略與 live signal 對齊。
4. 累積真實 blocked events，再評估是否有 promotion 證據。
5. 先處理磁碟空間與 stale/missing execution source warnings，這比繼續調 volatility gate 更實際。
