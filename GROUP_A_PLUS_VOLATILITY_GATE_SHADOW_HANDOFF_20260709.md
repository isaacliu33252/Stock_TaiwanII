# GroupA+ Volatility Gate Shadow Handoff - 2026-07-09

## 背景

本輪是依照使用者提供的論文 `C:\Users\isaac\Downloads\2606.09478v1.pdf`，評估是否把 volatility / regime 類訊號導入 GroupA+。

論文重點：

- 資料：CSI 300 Index 2005-2023 高頻資料。
- 方法：兩階段架構，先用 regime-augmented HARQ + Markov-switching GJR-GARCH 估 realized volatility / regime，再把 volatility forecast、regime indicators、return predictors 丟進 XGBoost 做 return prediction。
- 驗證：嚴格 walk-forward out-of-sample。
- 結論：波動與 regime 比報酬本身更可預測；單純 return prediction 扣成本後常失效；加入 volatility scaling、low-vol gating、threshold calibration、turnover control 後，防守型策略比較有價值。

對 GroupA+ 的解讀：

- 模型架構不是重點，不應為了仿論文而硬塞 XGBoost / Markov-switching。
- 可落地的重點是：用 volatility / regime 做防守與交易節制，不直接拿來預測報酬。
- 本輪導入為 shadow / advisory guard，不改 target weights。

## 本輪核心決策

目前沒有把 volatility gate 升級成 GroupA+ 自動調倉規則。

原因：

- 多個歷史區間測試顯示，自動砍 00631L exposure 會明顯降低 final value。
- Sharpe 有小幅改善，但 final value 損失與 turnover / cost 不划算。
- 最有價值的用法是高波動時限制加碼 00631L，而不是自動減碼既有部位。

目前採用：

- `shadow_only_no_weight_change`
- `advisory_no_auto_weight_change`
- 高波動時產生 alert，metadata 標示 `allow_00631l_add: false`
- 不修改 `target_weights`

## 已改檔案

### Volatility / regime shadow

- `group_a_plus/integrations/garch_regime_shadow.py`
  - 新增 volatility gate reference policy。
  - 新增常數：
    - `LOW_VOL_PERCENTILE_THRESHOLD = 0.40`
    - `LOW_VOL_RATIO_MAX = 1.00`
    - `HIGH_VOL_REFERENCE_SCALE = 0.50`
    - `NEUTRAL_VOL_REFERENCE_SCALE = 0.75`
    - `LOW_VOL_REFERENCE_SCALE = 1.00`
  - 新增 `volatility_gate_reference(high_vol, ratio, percentile, return_5d)`。
  - `compute_garch_regime_shadow()` 回傳 payload 內新增 `volatility_gate` metadata。
  - policy 仍為 `shadow_only_no_weight_change`。

### Shadow evaluation

- `scripts/evaluate/evaluate_group_a_plus_volatility_gate_shadow.py`
  - 以 A21.18 baseline 為基準。
  - 使用 `_garch_features` 建 GARCH-proxy volatility gate frame。
  - 輸出：
    - `results/group_a_plus_volatility_gate_shadow_latest.json`
    - `results/group_a_plus_volatility_gate_shadow_latest.csv`

評估 variants：

- `vol_gate_high_only`
  - high-vol 時將 00631L scale 參考值降至 0.5，差額轉 0050。
- `vol_gate_tiered`
  - neutral scale 0.75，high scale 0.5。
- `vol_gate_confirmed_high_no_trade`
  - 只在 high-vol + `total_risk_score >= 6` + NCF 00631L bearish/tail-risk 時動作，並加 no-trade band 5%。
- `vol_gate_high_no_add`
  - path-dependent no-add rule，只限制 high-vol 時增加 00631L，不自動砍既有部位。

### Daily signal alert

- `group_a_plus/operations/daily_signal.py`
  - `_build_signal_alerts()` 新增 optional `garch_regime_shadow` 參數。
  - `build_daily_signal()` 傳入 `garch_regime_shadow`。
  - 若 `garch_regime_shadow["volatility_gate"]["high_vol_gate"] is True`，新增 alert：
    - `type`: `volatility_gate_high_vol`
    - `level`: `medium`
    - title: `Volatility gate high-vol manual review`
    - metadata:

```json
{
  "allow_00631l_add": false,
  "trade_policy": "advisory_no_auto_weight_change",
  "reference_00631l_scale": 0.5,
  "volatility_gate": "high_vol_defensive",
  "signal_reliability": "suppress_return_prediction",
  "inputs": {}
}
```

### Alert state

- `group_a_plus/operations/alert_state.py`
  - `update_alert_state()` 現在會保留 raw alert 的 `metadata` 到 emitted / suppressed alert summary。
  - full raw alert 原本就會保存在 alerts entry，這次是補 summary metadata。

### Push notification

- `group_a_plus/operations/push_notifications.py`
  - `_format_alert_message()` 若看到 `metadata.allow_00631l_add is False`，會加上：

```text
00631L add: blocked (advisory, no auto weight change)
```

## 2026-07-09 live 狀態

今日資料已更新：

```bash
.venv/bin/python scripts/run/run_ncf_daily_pipeline.py --date-stamp 20260709 --refresh-target-date 2026-07-09 --ohlcv-target-date 2026-07-09 --only-refresh --force-refresh --strict-refresh --fail-on-ohlcv-warning
```

結果：

- OHLCV freshness OK for 2026-07-09。
- pipeline 成功。
- ops health 有 disk free below 2% 警告，屬環境容量問題，不是資料更新失敗。

2026-07-09 volatility gate smoke：

- vol ratio: `1.3247`
- percentile: `0.7024`
- 0050 5d return: `-0.0276`
- alert 包含 `volatility_gate_high_vol`
- metadata 有 `allow_00631l_add: false`

Push message smoke：

```text
<b>GroupA+ alert</b> (a2118_a2111_ncf_late_bull_deleverage, 2026-07-09)
- Volatility gate high-vol manual review: High-volatility gate is active; advisory-only review of 00631L exposure.
  00631L add: blocked (advisory, no auto weight change)
```

## Shadow evaluation 結論

主要結果：

| Window | Variant | delta_final | delta_sharpe | delta_mdd | extra_cost | changed_days |
|---|---:|---:|---:|---:|---:|---:|
| live_2024_2026 | vol_gate_high_only | -178,364 | +0.0687 | +2.37% | 19,872 | 84 |
| live_2024_2026 | vol_gate_tiered | -230,521 | +0.0622 | +2.41% | n/a | 353 |
| active_2025_2026 | vol_gate_confirmed_high_no_trade | -109,690 | +0.0515 | no improvement | n/a | 22 |
| all windows | vol_gate_high_no_add | 0 | 0 | 0 | 0 | 0 |

解讀：

- 自動 trim 00631L 的 variants 大多犧牲 final value。
- Sharpe 小幅改善不足以支持升級。
- `vol_gate_high_no_add` 沒傷害，但歷史樣本沒有遇到 high-vol 同時策略正在加碼 00631L 的場景，所以目前只能當 advisory guard，不能宣稱有效提升績效。

## 測試

最新相關測試：

```bash
.venv/bin/python -m pytest tests/test_group_a_plus_push_notifications.py tests/test_group_a_plus_alert_state.py tests/test_group_a_plus_daily_signal_v2.py tests/test_evaluate_group_a_plus_volatility_gate_shadow.py tests/test_group_a_plus_garch_regime_shadow.py
```

結果：

```text
82 passed, 3 warnings
```

warnings 來自 `backtest_group_a_plus_switch_policy.py:530` pandas FutureWarning，與本輪邏輯無關。

### 2026-07-09 後續：pre-trade guard + report display

已把 volatility gate 從 alert metadata 接到 execution plan 的 pre-trade guard，但仍不改
`target_weights`。

新增：

- `group_a_plus/operations/execution_guard.py`
  - `apply_volatility_gate_pre_trade_guard()`
  - high-vol gate active 且 `allow_00631l_add=false` 時，只阻擋 `00631L.TW` 目標股數高於目前持股的買入差額。
  - 持有不變、減碼 00631L、其他 ticker 交易都允許。
- `group_a_plus/operations/execution_plan.py`
  - 在 execution controls / buy staging 後、建立 trades 前套用 pre-trade guard。
  - 輸出新增 `pre_trade_guard`，`target_shares` 與 trades 使用 guard 後的股數。
- `group_a_plus_report_manager.py`
  - daily status HTML 若收到 `pre_trade_guard`，會顯示狀態、00631L add allowed/blocked、policy、blocked trade 明細。
- `scripts/misc/check_group_a_plus_daily_status.py`
  - 新增讀取 `--execution-plan`（預設 `report/group_a_plus/latest/execution_plan.json`）。
  - 只有當 execution plan 的 `actual_data_date` 與 `strategy_id` 和 live signal 對齊時，才把 `pre_trade_guard` 放進 daily status。
  - 若 execution plan 存在但不對齊，只產生 warning，不顯示舊 guard，避免誤讀。
- `scripts/run/run_ncf_daily_pipeline.py`
  - daily_status step 明確傳入 `--execution-plan report/group_a_plus/latest/execution_plan.json`。
  - pipeline 仍不自動生成 execution plan，因為 execution plan 需要人工 workbook/cash balance；daily status 只檢查 latest plan 是否對齊。
- `scripts/evaluate/evaluate_group_a_plus_volatility_pretrade_guard.py`
  - 新增 pre-trade no-add guard shadow audit。
  - 重播 A21.18 regime path，只檢查 high-vol gate 是否碰到 00631L 加碼 rebalance，不做策略 promotion、不改 target weights。
- `group_a_plus/operations/ops_health.py`
  - 新增 `artifact_health.volatility_gate_execution_guard`。
  - 若正式 latest live signal 有 high-vol volatility gate active，會檢查 execution plan 是否存在、日期/策略是否對齊、`pre_trade_guard.allow_00631l_add` 是否為 `false`。
  - 不 active 時不產生 warning。

新增測試：

- `tests/test_check_group_a_plus_daily_status.py`
- `tests/test_evaluate_group_a_plus_volatility_pretrade_guard.py`
- `tests/test_group_a_plus_execution_guard.py`
- `tests/test_group_a_plus_ops_health.py` 新增 volatility gate / execution guard 對齊檢查。
- `tests/test_group_a_plus_report_manager.py`
- `tests/test_group_a_plus_execution_plan_v2.py` 新增 guard-before-trades regression。

Pre-trade guard shadow audit：

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_volatility_pretrade_guard.py \
  --output results/group_a_plus_volatility_pretrade_guard_shadow_20260709.json
```

輸出：

- `results/group_a_plus_volatility_pretrade_guard_shadow_20260709.json`
- `results/group_a_plus_volatility_pretrade_guard_shadow_20260709.csv`

結果摘要：

| Window | all_high_vol_days | checked_rebalance_days | high_vol_rebalance_days | blocked_days | blocked_notional |
|---|---:|---:|---:|---:|---:|
| covid_2020 | 9 | 3 | 0 | 0 | 0 |
| inflation_2022 | 34 | 1 | 0 | 0 | 0 |
| live_2024_2026 | 97 | 6 | 0 | 0 | 0 |
| active_2025_2026 | 51 | 6 | 0 | 0 | 0 |

解讀：

- 歷史 high-vol days 不少，但沒有出現在 A21.18 的 rebalance day 上。
- 因此 no-add pre-trade guard 在這些窗口沒有實際阻擋交易，也沒有歷史績效副作用可量化。
- 這支持目前定位：guard 是 live safety rail，不是已證實能改善績效的策略因子。

Live execution dry-run（不更新正式 latest pointer）：

```bash
.venv/bin/python -m group_a_plus.operations.execution_plan \
  --as-of 2026-07-09 \
  --cash-balance 0 \
  --output results/group_a_plus_execution_plan_dry_run_20260709.json \
  --latest-pointer /tmp/group_a_plus_execution_plan_dry_run_20260709_latest.json
```

結果：

- `success=True`
- `actual_data_date=2026-07-09`
- `execution_regime=golden1`
- `planning_status=manual_review_required`
- `pre_trade_guard.status=blocked`
- `current_00631L=0`
- 原 requested target: `476` 股
- guarded target: `0` 股
- `trades` 中沒有 00631L 買單
- manual review reasons：
  - required strategy sources stale/missing: `day_trading_0050`, `dealer_tx`, `dealer_txo`
  - turnover ratio `78.14%` exceeds automatic limit `50.00%`

注意：這次 dry-run 使用 `--cash-balance 0`，僅驗證管線與 guard 落地，不代表實際下單現金假設。

Ops health guard check：

```bash
.venv/bin/python -m group_a_plus.operations.ops_health \
  --output results/group_a_plus_ops_health_guard_check_20260709.json
```

結果：

- 正式 latest live signal 目前仍是 `actual_data_date=2026-07-08`，且沒有 garch volatility gate payload。
- 因此 `artifact_health.volatility_gate_execution_guard.status=ok` / inactive。
- 整體 ops health 仍為 `error`，原因是環境 `system_resources`（磁碟空間）問題，不是 guard 邏輯。

Threshold sweep（2026-07-10）：

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_volatility_pretrade_guard_sweep.py \
  --output results/group_a_plus_volatility_pretrade_guard_threshold_sweep_20260710.json
```

輸出：

- `results/group_a_plus_volatility_pretrade_guard_threshold_sweep_20260710.json`
- `results/group_a_plus_volatility_pretrade_guard_threshold_sweep_20260710.csv`

掃描：

- ratio threshold: `1.05, 1.10, 1.15, 1.20, 1.25, 1.30`
- percentile threshold: `0.55, 0.60, 0.65, 0.70, 0.75, 0.80`
- require negative 5d: `true / false`
- total combinations: `72`

結果：

- max blocked days: `0`
- max high-vol rebalance days: `2`
- best overlap setting:
  - ratio `1.05`
  - percentile `0.70`
  - require negative 5d `false`
  - high-vol days `536`
  - high-vol rebalance days `2`
  - blocked days `0`

結論：

- 不建議調鬆 production volatility gate threshold。
- 即使大幅放寬到 ratio `1.05` 且不要求 0050 5d 下跌，也沒有產生任何歷史 blocked case。
- 放寬只會大幅增加 high-vol alert burden（500+ days），沒有增加 no-add guard 的可驗證效益。
- 目前參數保守保留，guard 維持 live safety rail 定位。

Current holdings scenario grid（2026-07-10）：

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_volatility_guard_holdings_scenarios.py \
  --plan results/group_a_plus_execution_plan_dry_run_20260709.json \
  --output results/group_a_plus_volatility_guard_holdings_scenarios_20260710.json
```

輸出：

- `results/group_a_plus_volatility_guard_holdings_scenarios_20260710.json`
- `results/group_a_plus_volatility_guard_holdings_scenarios_20260710.csv`

設定：

- source plan: `results/group_a_plus_execution_plan_dry_run_20260709.json`
- execution-stage requested 00631L target: `476` 股
- theoretical 00631L target before execution controls: `1192` 股
- 00631L price: `36.78`

結果：

| current 00631L shares | requested target | guarded target | status | blocked shares | blocked notional |
|---:|---:|---:|---|---:|---:|
| 0 | 476 | 0 | blocked | 476 | 17,507 |
| 100 | 476 | 100 | blocked | 376 | 13,829 |
| 250 | 476 | 250 | blocked | 226 | 8,312 |
| 476 | 476 | 476 | active_allowed | 0 | 0 |
| 600 | 476 | 476 | active_allowed | 0 | 0 |
| 1000 | 476 | 476 | active_allowed | 0 | 0 |
| 1192 | 476 | 476 | active_allowed | 0 | 0 |

解讀：

- 如果目前 00631L 低於 execution-stage target `476` 股，guard 會把 target 壓回目前持股，只阻擋新增部位。
- 如果目前 00631L 已達或高於 `476` 股，guard 不阻擋；減碼到 476 股仍允許。
- 這驗證 guard 的 live 行為符合設計：禁止加碼，不禁止減碼。

較寬回歸：

```bash
.venv/bin/python -m pytest \
  tests/test_evaluate_group_a_plus_volatility_guard_holdings_scenarios.py \
  tests/test_evaluate_group_a_plus_volatility_pretrade_guard_sweep.py \
  tests/test_group_a_plus_ops_health.py \
  tests/test_evaluate_group_a_plus_volatility_pretrade_guard.py \
  tests/test_check_group_a_plus_daily_status.py \
  tests/test_group_a_plus_report_manager.py \
  tests/test_group_a_plus_execution_guard.py \
  tests/test_group_a_plus_execution_plan_v2.py \
  tests/test_group_a_plus_daily_signal_v2.py \
  tests/test_group_a_plus_alert_state.py \
  tests/test_group_a_plus_signal_alignment.py \
  tests/test_group_a_plus_market_state.py \
  tests/test_group_a_plus_ops_health.py \
  tests/test_run_ncf_daily_pipeline.py \
  tests/test_group_a_plus_garch_regime_shadow.py \
  tests/test_evaluate_group_a_plus_volatility_gate_shadow.py \
  tests/test_group_a_plus_push_notifications.py
```

結果：

```text
159 passed, 3 warnings
```

## Git / worktree 注意

本輪相關檔案中，有部分目前在 `git status --short` 顯示為 untracked。接手者不要假設已 commit。

已看到的相關狀態：

```text
 M group_a_plus/operations/alert_state.py
 M group_a_plus/operations/daily_signal.py
 M tests/test_group_a_plus_alert_state.py
 M tests/test_group_a_plus_daily_signal_v2.py
?? group_a_plus/integrations/garch_regime_shadow.py
?? group_a_plus/operations/execution_guard.py
?? group_a_plus/operations/push_notifications.py
?? scripts/evaluate/evaluate_group_a_plus_volatility_gate_shadow.py
?? scripts/evaluate/evaluate_group_a_plus_volatility_pretrade_guard.py
?? tests/test_check_group_a_plus_daily_status.py
?? tests/test_evaluate_group_a_plus_volatility_gate_shadow.py
?? tests/test_evaluate_group_a_plus_volatility_pretrade_guard.py
?? tests/test_group_a_plus_execution_guard.py
?? tests/test_group_a_plus_garch_regime_shadow.py
?? tests/test_group_a_plus_push_notifications.py
?? tests/test_group_a_plus_report_manager.py
```

repo 內還有很多既有 dirty / untracked files，未必與本輪有關，不要任意 revert。

## 後續建議

1. 保持 volatility gate 為 advisory / no-add guard。
2. 不要把 high-vol gate 改成自動 trim 00631L，除非新的 multi-window OOS 證據能同時證明 final value、MDD、turnover tradeoff 可接受。
3. `allow_00631l_add=false` 已接到 execution plan pre-trade guard；若之後接 broker，也沿用同一個「只禁止新增 00631L」檢查，不改 rebalance target。
4. 若要正式 promotion，需跑既有 promotion gate / multi-window gate，且成本、turnover、changed_days 必須列入決策。
5. 先處理磁碟空間警告，避免後續 daily pipeline 或 results 寫檔失敗。

## 一句話交接

這次已把論文中的 volatility / regime 思路轉成 GroupA+ 的 shadow advisory 與 execution pre-trade guard：高波動時提醒並阻擋新增 00631L，但不自動減碼、不改 target weights；歷史測試不支持把它升級為自動調倉策略。
