# FinRL Consolidation / Archive Candidate Handoff - 2026-07-29

## 結論

「移除重複模組、統一 FinRL 版本」這個方向合理，但目前不建議直接刪除 `FinRL/`、`FinRL/v2/`、`Stock_TaiwanII_FinRLX/` 任一整包。

原因是目前 production/live 策略不是單純由 FinRL v1/v2 其中一套驅動，而是由 `group_a_plus/` 的 Group A+ runner 驅動，並且仍大量依賴 `FinRL/data` 當資料層，也部分依賴 `FinRL/backtesting` 與 `FinRL/v2/backtesting/performance_metrics.py` 作為回測/指標相容層。

最安全的整理方式是：

1. 先選定「主線」：`group_a_plus/` + root Group A+ policy/backtest scripts + `FinRL/data`。
2. 將沒有 live import 的模組標成 archive candidate。
3. 先補 import/contract 檢查，再移動到 `archive/`。
4. 最後才考慮把 `FinRL/data` 遷到更中性的資料模組名稱。

## 目前最新/active 策略

來源檔：

- `report/group_a_plus/latest/strategy.json`
- `report/group_a_plus/latest/live_signal.json`
- `group_a_plus/runners/latest.py`
- `group_a_plus/runners/a2118.py`

目前 active strategy：

- strategy id: `a2118_a2111_ncf_late_bull_deleverage`
- runner: `group_a_plus.runners.a2118`
- runner function: `run_a2118`
- activated_at: `2026-06-29`
- latest live signal generated_at: `2026-07-28T07:13:10`
- latest live signal actual_data_date: `2026-07-27`

最新 live target weights：

- `0050.TW`: `0.50`
- `00631L.TW`: `0.20`
- `00632R.TW`: `0.00`
- `00679B.TWO`: `0.00`
- `cash`: `0.30`

策略演進脈絡：

- `Golden1_0531`
- `A20.7 / switch policy`
- `A21.3 recovery ramp`
- `A21.7 tight entry`
- `A21.4 bond30_cash30 defensive basket`
- `A21.11 tight_entry_bond30c30`
- `A21.18 = A21.11 + NCF late-bull de-leverage overlay + 2020 COVID switch-rule fix`

重要判斷：目前 live/active 策略不是從 `Stock_TaiwanII_FinRLX/` 改來，也不是直接從 `FinRL/v2` RL agent/environment 改來。它是 Group A+ policy runner 線的延伸；FinRL 主要扮演資料、回測與指標工具層。

## 目前不可直接歸檔的區塊

### `group_a_plus/`

這是目前 active strategy 的主線。`group_a_plus.runners.latest` 讀 `report/group_a_plus/latest/strategy.json`，再 dispatch 到 `group_a_plus.runners.a2118`。

不可歸檔。

### root Group A+ policy/backtest scripts

例如：

- `backtest_group_a_plus_switch_policy.py`
- `ncf_2330.py`
- `ncf_00632r.py`
- 部分 `scripts/run/*`
- 部分 `scripts/evaluate/*`
- 部分 `scripts/misc/*`

這些仍是策略、資料更新、shadow evaluation、報表、daily pipeline 的組成部分。

不可整批歸檔，只能逐支確認。

### `FinRL/data`

這是 production data layer，不只是舊 FinRL 研究碼。

已確認用途包括：

- `FinRL/data/stock_data.db`
- `FinRL/data/stock_db.py`
- `FinRL.data.stock_db.DB_PATH`
- `FinRL.data.stock_db.query_ohlcv`
- 籌碼、融資融券、集保、OHLCV refresh CLI
- `scripts/run/run_ncf_daily_pipeline.py` 直接執行 `FinRL/data/stock_db.py`
- 多個 Group A+ evaluate/run/misc script 直接引用 `FinRL.data.stock_db`

不可直接歸檔。若要統一命名，應另開 migration，把資料層搬到例如 `group_a_plus/data` 或 `project_data`，同時保留 compatibility shim。

### `FinRL/backtesting`

仍有測試與 bridge 使用，例如：

- `tests/test_group_a_finrlx_bridge.py`
- `tests/test_integration.py`
- `scripts/evaluate/evaluate_a2118_finrl_dual_engine_reconciliation.py`
- `FinRL/finrlx_group_a_backtest.py`

不可直接歸檔。可以先標記為 compatibility/research bridge，等使用者全部遷完後再處理。

### `FinRL/v2/backtesting/performance_metrics.py`

雖然 `FinRL/v2` 大部分看起來偏 RL/research，但這支目前仍被 Group A+ 指標比較使用：

- `backtest_group_a_plus_switch_policy.py` 匯入 `FinRL.v2.backtesting.performance_metrics`
- `tests/test_backtest_group_a_plus_metrics_finrl_comparable.py`

不可連同整個 `FinRL/v2` 直接歸檔。若要歸檔 `FinRL/v2`，需先把這個 metrics helper 搬到 live/shared metrics 模組，並保留 import 相容或修正所有引用。

## Archive candidates

### 強候選：`Stock_TaiwanII_FinRLX/`

目前搜尋結果顯示，除了自己的檔案與 `GROUP_A_FINRLX_GAP_CHECKLIST_2026-05-24.md` 的文字連結外，沒有看到 live pipeline 對它的 import。

目錄內容偏 standalone prototype：

- `src/backtest/backtest_engine.py`
- `src/config/settings.py`
- `src/data/data_loader.py`
- `src/main.py`
- `src/strategies/base_strategy.py`
- `src/strategies/rl_portfolio_strategy.py`
- `src/trading/alpaca_manager.py`
- `src/trading/trade_executor.py`
- `tests/smoke_test.py`

建議處置：

- 第一階段：新增 `Stock_TaiwanII_FinRLX/ARCHIVE_CANDIDATE.md`
- 第二階段：確認 `pytest` 與 daily pipeline smoke 不依賴它
- 第三階段：移到 `archive/Stock_TaiwanII_FinRLX_legacy_20260729/`

### 候選：`FinRL/v2/agents`, `FinRL/v2/environments`, `FinRL/v2/data`

這些區塊主要是 RL v2 agent/environment/data implementation。目前 active A21.18 live path 沒有直接使用 agent/environment。

但注意：

- `FinRL/v2/environments/reward_function.py` 目前有測試覆蓋，是 research/RL reward function。
- `FinRL/v2/backtesting/performance_metrics.py` 不能跟著整包丟掉。
- `FinRL/v2/backtesting/backtest_engine.py` 曾被交接文件註記為 single-instrument，不適合作為 A21.18 multi-asset live engine。

建議處置：

- 不要直接移動整個 `FinRL/v2`
- 先切出 retained 子集：`FinRL/v2/backtesting/performance_metrics.py`
- 再把 agent/environment/data 標為 research legacy candidate

### 候選：root-level duplicate `agents/`, `backtesting/`, `environments/`

repo root 也有 `agents/`, `backtesting/`, `environments/` 等與 `FinRL/` 內部相似的模組。

目前看到 root `backtesting/backtest.py` 是 compatibility wrapper：

- `backtesting/backtest.py` 轉向 `FinRL.backtesting.backtest`

這類 wrapper 不能在未確認 import contract 前刪除。建議先標示 ownership，再逐一清。

## 建議的清理順序

1. 文件化 ownership
   - 建立本文件。
   - 明確宣告 active strategy 主線是 `group_a_plus/`，不是 `Stock_TaiwanII_FinRLX/` 或 RL v2 agent。

2. 加 archive candidate marker
   - 先加文件，不移動檔案。
   - 第一個 marker 建議放在 `Stock_TaiwanII_FinRLX/ARCHIVE_CANDIDATE.md`。

3. 加 import guard 測試
   - 檢查 live runner 不 import `Stock_TaiwanII_FinRLX`
   - 檢查 daily pipeline 不 import `Stock_TaiwanII_FinRLX`
   - 檢查 `group_a_plus.runners.latest` 可以讀取 `strategy.json` 並 dispatch 到 `a2118`

4. 抽離 shared metrics
   - 將 `FinRL/v2/backtesting/performance_metrics.py` 的 Group A+ 需要部分搬到 shared metrics 模組。
   - 修改 `backtest_group_a_plus_switch_policy.py` 與 tests。
   - 保留 compatibility import 一段時間。

5. 資料層命名 migration
   - 長期可把 `FinRL/data/stock_db.py` 遷成更中性的資料層，例如 `group_a_plus/data/stock_db.py` 或 `project_data/stock_db.py`。
   - 初期必須保留 `FinRL.data.stock_db` shim，因為引用點很多。

6. 真正搬 archive
   - 只有在 marker、guard tests、smoke tests 都完成後，才移動檔案到 `archive/`。

## 這次確認過的 command/output 摘要

使用過的檢查：

```bash
rg "Stock_TaiwanII_FinRLX" -n .
find Stock_TaiwanII_FinRLX -maxdepth 3 -type f -print
find FinRL -maxdepth 2 -type d | sort
rg "from FinRL|import FinRL" -n group_a_plus scripts tests . --glob '!Stock_TaiwanII_FinRLX/**' --glob '!FinRL/.venv-backtest/**' --glob '!*__pycache__/**'
rg "FinRL\\.v2|FinRL/v2|v2/environments|v2/data|v2/backtesting" -n .
```

主要觀察：

- `Stock_TaiwanII_FinRLX/` 沒看到 live import，是目前最乾淨的 archive candidate。
- `FinRL/data` 被大量 production/data refresh/evaluate 腳本使用，不能刪。
- `FinRL/backtesting` 還是 bridge/test/reconciliation 用途，不能整批刪。
- `FinRL/v2/backtesting/performance_metrics.py` 被 Group A+ comparable metrics 使用，不能跟著 `FinRL/v2` 整包歸檔。
- `FinRL/v2/agents`、`FinRL/v2/environments`、`FinRL/v2/data` 比較像 research/RL legacy，但要先加 guard 再搬。

## 下一位接手者的 resume checklist

1. 先讀：
   - `FINRL_CONSOLIDATION_ARCHIVE_CANDIDATES_20260729.md`
   - `GROUP_A_PLUS_PROJECT_REVIEW_AND_REWARD_PIPELINE_FIX_HANDOFF_20260729.md`
   - `report/group_a_plus/latest/strategy.json`
   - `report/group_a_plus/latest/live_signal.json`

2. 若要繼續清理，先做文件/測試，不要先移動：
   - 新增 `Stock_TaiwanII_FinRLX/ARCHIVE_CANDIDATE.md`
   - 新增 live import guard tests

3. 歸檔前至少跑：
   - `pytest tests/test_run_ncf_daily_pipeline.py`
   - `pytest tests/test_backtest_group_a_plus_metrics_finrl_comparable.py`
   - `pytest tests/test_group_a_finrlx_bridge.py`
   - `pytest tests/test_finrl_v2_reward_function.py`
   - `python3 -m compileall group_a_plus scripts FinRL/v2 FinRL/data`

4. 不要歸檔：
   - `group_a_plus/`
   - `backtest_group_a_plus_switch_policy.py`
   - `FinRL/data`
   - `FinRL/backtesting`
   - `FinRL/v2/backtesting/performance_metrics.py`

5. 可以優先處理：
   - `Stock_TaiwanII_FinRLX/`
   - `FinRL/v2/agents`
   - `FinRL/v2/environments`
   - `FinRL/v2/data`

## 當前狀態

本文件建立後，另新增了一個低風險實作改善：

- `group_a_plus/portfolio/rebalance_plan.py`
- `tests/test_rebalance_plan.py`
- `group_a_plus/portfolio/rebalance_validation.py`
- `tests/test_rebalance_validation.py`
- `group_a_plus/portfolio/rebalance_audit.py`
- `tests/test_rebalance_audit.py`
- `group_a_plus/portfolio/holding_snapshot.py`
- `group_a_plus/portfolio/rebalance_cli.py`
- `group_a_plus/portfolio/fubon_snapshot.py`
- `tests/test_holding_snapshot.py`
- `tests/test_rebalance_cli.py`
- `tests/test_fubon_snapshot.py`

這不是從 `Stock_TaiwanII_FinRLX/` 搬移 executor，也沒有接券商 API。它只吸收 FinRLX 值得參考的「broker-neutral execution/result interface」概念，將 Group A+ live signal 已產出的 `target_weights` 轉成可稽核的調倉計畫：

- 使用 `daily_signal.py` 的 `target_weights` 與 `latest_prices`
- 接收目前持股張/股數與 cash
- 計算 current values、target values、BUY/SELL 差額
- 支援 `min_trade_value`
- 支援每檔 ticker 的 `lot_size` rounding
- 缺價格、負權重、權重總和超過 1.0 時 fail fast
- 不下單、不寫 report artifact、不修改 live signal

設計判斷：

- 不把 active strategy 搬進 `Stock_TaiwanII_FinRLX/`
- 不重用 `Stock_TaiwanII_FinRLX/src/trading/trade_executor.py`，因為它偏 Alpaca/美股假設，且 `_weights_to_orders()` 欄位假設與 `live_signal.json` 不一致
- 將 execution planning 放在 `group_a_plus/portfolio/`，讓它貼近目前 production strategy 主線

新增驗證：

```bash
pytest tests/test_rebalance_plan.py tests/test_signal_contract.py tests/test_run_ncf_daily_pipeline.py
python3 -m compileall group_a_plus/portfolio tests/test_rebalance_plan.py
```

結果：

- `34 passed`
- compile check passed

尚未移動、刪除或重命名任何 production/research 模組。

後續又新增第二層 pre-trade validation：

- `validate_rebalance_plan(plan, daily_signal=..., config=...)`
- `RebalanceRiskConfig`
- `RebalanceValidation`
- `RiskCheck`

這一層同樣不下單、不修改 live signal，只檢查 `RebalancePlan` 是否適合進入人工審核/券商 adapter。已覆蓋檢查：

- `execution_allowed`: live signal 若已被 guard block，調倉計畫不得 approved
- `max_order_value`: 單筆交易金額上限
- `max_total_buy_value`: 總買入金額上限
- `max_turnover_ratio`: 總交易額 / portfolio value 上限
- `max_leveraged_target_weight`: `00631L.TW` 目標權重上限
- `ncf_stale_no_new_risk_adds`: 有 `ncf_panel_stale` alert 時禁止新增 `0050.TW` / `00631L.TW` 風險曝險
- `ops_health_no_new_risk_adds`: 有 `ops_health_*` alert 時禁止新增風險曝險
- `cash_drift`: planned cash 與 target cash 差距過大時 warning，不直接 fail

API 已從 `group_a_plus/portfolio/__init__.py` 匯出：

- `build_rebalance_plan`
- `validate_rebalance_plan`
- `RebalanceConfig`
- `RebalanceRiskConfig`
- `RebalancePlan`
- `RebalanceValidation`

新增驗證：

```bash
pytest tests/test_rebalance_plan.py tests/test_rebalance_validation.py
pytest tests/test_signal_contract.py tests/test_run_ncf_daily_pipeline.py tests/test_rebalance_plan.py tests/test_rebalance_validation.py
python3 -m compileall group_a_plus/portfolio tests/test_rebalance_plan.py tests/test_rebalance_validation.py
```

結果：

- `11 passed`
- `40 passed`
- compile check passed

第三層 audit trail 也已新增：

- `build_rebalance_audit_report(...)`
- `write_rebalance_audit_report(...)`
- `dated_rebalance_audit_path(...)`

預設輸出設計：

- latest pointer: `report/group_a_plus/latest/rebalance_plan.json`
- dated copy: `results/rebalance_plan_YYYYMMDD.json`

audit report schema 重點：

- `signal`: 來自 `TargetWeightSignal` 的 strategy/date/model/data hash 資訊
- `portfolio_snapshot`: current shares、cash、current values、portfolio value
- `rebalance_plan`: `RebalancePlan.to_json_dict()`
- `validation`: `RebalanceValidation.to_json_dict()`
- `manual_approval`: 預設 `required=true`, `approved=false`
- `execution`: 預設 `broker_submitted=false`
- `audit_hash`: 對 report payload 的 deterministic SHA-256

重要安全邊界：

- `validation.approved=true` 只代表 pre-trade checks 通過
- `manual_approval.approved` 預設永遠是 `false`
- 這一層仍然不送單、不接 broker、不改 live signal

新增驗證：

```bash
pytest tests/test_rebalance_plan.py tests/test_rebalance_validation.py tests/test_rebalance_audit.py
pytest tests/test_signal_contract.py tests/test_run_ncf_daily_pipeline.py tests/test_rebalance_plan.py tests/test_rebalance_validation.py tests/test_rebalance_audit.py
python3 -m compileall group_a_plus/portfolio tests/test_rebalance_plan.py tests/test_rebalance_validation.py tests/test_rebalance_audit.py
```

結果：

- `15 passed`
- `44 passed`
- compile check passed

第四層日常操作入口已新增：

- `HoldingSnapshot`
- `holding_snapshot_from_dict(...)`
- `load_holding_snapshot_json(...)`
- `python3 -m group_a_plus.portfolio.rebalance_cli`

支援的 holdings JSON 格式：

```json
{
  "account_id": "paper",
  "as_of": "2026-07-27",
  "cash": 300000,
  "holdings": {
    "0050.TW": 4000,
    "00631L.TW": 12000
  }
}
```

也接受 `current_shares` 或 `positions` 作為 `holdings` 的別名。

CLI 範例：

```bash
python3 -m group_a_plus.portfolio.rebalance_cli \
  --signal report/group_a_plus/latest/live_signal.json \
  --holdings holdings.json \
  --output report/group_a_plus/latest/rebalance_plan.json
```

CLI 行為：

- 讀取 live signal JSON
- 讀取 holdings JSON
- 建立 `RebalancePlan`
- 執行 `RebalanceValidation`
- 建立並寫出 audit report
- 預設寫出 latest + dated copy
- 不送單、不接 broker、不改 live signal

新增驗證：

```bash
pytest tests/test_holding_snapshot.py tests/test_rebalance_cli.py tests/test_rebalance_plan.py tests/test_rebalance_validation.py tests/test_rebalance_audit.py
pytest tests/test_signal_contract.py tests/test_run_ncf_daily_pipeline.py tests/test_holding_snapshot.py tests/test_rebalance_cli.py tests/test_rebalance_plan.py tests/test_rebalance_validation.py tests/test_rebalance_audit.py
python3 -m compileall group_a_plus/portfolio tests/test_holding_snapshot.py tests/test_rebalance_cli.py tests/test_rebalance_plan.py tests/test_rebalance_validation.py tests/test_rebalance_audit.py
```

結果：

- `22 passed`
- `51 passed`
- compile check passed

第五層 Fubon read-only snapshot adapter 已新增：

- `FubonCredentials`
- `load_fubon_credentials_from_env(...)`
- `fetch_fubon_holding_snapshot(...)`
- `parse_fubon_inventories(...)`
- `parse_fubon_cash(...)`
- `write_holding_snapshot(...)`
- CLI: `python3 -m group_a_plus.portfolio.fubon_snapshot`

安全邊界：

- 只呼叫 `sdk.login(...)`
- 只呼叫 `sdk.accounting.inventories(...)`
- 只呼叫 `sdk.accounting.bank_remain(...)`
- 不 import 或呼叫 `sdk.stock.place_order(...)`
- 不呼叫 `sdk.stock.batch_place_order(...)`
- 不自動交易

富邦 credential 目前已改成「非密碼欄位可從環境變數/local config 讀取，密碼必須手動輸入」。

目前只應保存：

```bash
export FUBON_ID="..."  # or FUBON_PERSONAL_ID for compatibility with config/fubon_sdk.env.example
export FUBON_CERT_PATH="/path/to/cert.pfx"
```

不要再保存 `FUBON_PASSWORD` 或 `FUBON_CERT_PASSWORD`。snapshot CLI 會在連 Fubon SDK 時用 `getpass()` 手動詢問登入密碼與憑證密碼。

只讀 snapshot CLI 範例：

```bash
python3 -m group_a_plus.portfolio.fubon_snapshot \
  --output data/private/holdings_fubon_latest.json \
  --as-of 2026-07-29
```

接 rebalance audit：

```bash
python3 -m group_a_plus.portfolio.rebalance_cli \
  --signal report/group_a_plus/latest/live_signal.json \
  --holdings data/private/holdings_fubon_latest.json \
  --output report/group_a_plus/latest/rebalance_plan.json
```

新增驗證：

```bash
pytest tests/test_fubon_snapshot.py tests/test_holding_snapshot.py tests/test_rebalance_cli.py tests/test_rebalance_plan.py tests/test_rebalance_validation.py tests/test_rebalance_audit.py
pytest tests/test_signal_contract.py tests/test_run_ncf_daily_pipeline.py tests/test_fubon_snapshot.py tests/test_holding_snapshot.py tests/test_rebalance_cli.py tests/test_rebalance_plan.py tests/test_rebalance_validation.py tests/test_rebalance_audit.py
python3 -m compileall group_a_plus/portfolio tests/test_fubon_snapshot.py tests/test_holding_snapshot.py tests/test_rebalance_cli.py tests/test_rebalance_plan.py tests/test_rebalance_validation.py tests/test_rebalance_audit.py
```

結果：

- `29 passed`
- `58 passed`
- compile check passed

Compatibility note:

- `FUBON_ID` and legacy `FUBON_PERSONAL_ID` are both accepted.
- `python_sample_code_2.ipynb` uses its own AES helper (`AES_Encryption.encrype_process.check_encrype`) with `d:/python/key/` and `d:/python/config/`.
- The checked WSL paths `/mnt/d/python/e01/AES-Encryption-main`, `/mnt/d/python/key`, `/mnt/d/python/config`, `/mnt/c/python/e01/AES-Encryption-main`, `/mnt/c/python/key`, and `/mnt/c/python/config` were not present, so that notebook credential loader is not directly usable in this environment unless those files are restored.
- Keep real credentials out of git; use `.fubon.env` or shell environment variables.

新增驗證：

```bash
pytest tests/test_fubon_snapshot.py tests/test_fubon_sdk_check.py
python3 -m compileall group_a_plus/portfolio tests/test_fubon_snapshot.py tests/test_fubon_sdk_check.py
```

結果：

- `12 passed`
- compile check passed

額外只讀安全確認：

- `tests/test_fubon_snapshot.py::test_fubon_snapshot_module_has_no_order_placement_calls`
- 以 Python AST 掃描 `group_a_plus/portfolio/fubon_snapshot.py`
- forbidden call list:
  - `place_order`
  - `batch_place_order`
  - `cancel_order`
  - `batch_cancel_order`
  - `modify_price`
  - `batch_modify_price`
  - `modify_quantity`
  - `batch_modify_quantity`
  - `make_modify_price_obj`
  - `make_modify_quantity_obj`

新增驗證：

```bash
pytest tests/test_fubon_snapshot.py
rg "place_order|batch_place_order|cancel_order|modify_price|modify_quantity|make_modify" -n group_a_plus/portfolio tests/test_fubon_snapshot.py
python3 -m compileall group_a_plus/portfolio tests/test_fubon_snapshot.py
```

結果：

- `8 passed`
- `rg` 只在 forbidden-list 測試與 `fubon_snapshot.py` docstring 找到下單 API 名稱，沒有實作呼叫
- compile check passed

Fubon SDK no-login smoke check 已新增：

- `group_a_plus/portfolio/fubon_sdk_check.py`
- CLI: `python3 -m group_a_plus.portfolio.fubon_sdk_check --json`
- 測試：`tests/test_fubon_sdk_check.py`

這個 check 只做：

- `import fubon_neo`
- `from fubon_neo.sdk import FubonSDK`
- 建立 `FubonSDK()`
- 回報 version、module path、sdk type

明確不做：

- 不登入：`login_attempted=false`
- 不查帳：`accounting_attempted=false`
- 不碰下單 API：`order_api_attempted=false`

目前實測輸出摘要：

```json
{
  "sdk_imported": true,
  "sdk_instantiated": true,
  "version": "2.2.8",
  "sdk_type": "fubon_neo.sdk.FubonSDK",
  "login_attempted": false,
  "accounting_attempted": false,
  "order_api_attempted": false
}
```

新增驗證：

```bash
python3 -m group_a_plus.portfolio.fubon_sdk_check --json
pytest tests/test_fubon_sdk_check.py tests/test_fubon_snapshot.py
pytest tests/test_fubon_sdk_check.py tests/test_fubon_snapshot.py tests/test_holding_snapshot.py tests/test_rebalance_cli.py tests/test_rebalance_plan.py tests/test_rebalance_validation.py tests/test_rebalance_audit.py
python3 -m compileall group_a_plus/portfolio tests/test_fubon_sdk_check.py tests/test_fubon_snapshot.py
```

結果：

- no-login SDK check succeeded
- `11 passed`
- `38 passed`
- compile check passed

第六層 Excel holdings loader 已新增：

- `load_holding_snapshot_excel(...)`
- `rebalance_cli --holdings-excel ... --cash ...`

支援兩種 Excel 格式：

1. 一般表格格式：

```text
ticker | shares
0050   | 4000
00631L | 12000
cash   | 300000
```

若 Excel 沒有 `cash` row，必須用 `--cash` 明確指定。

2. 既有 `taiwan_stock_*.xlsx` 橫向格式：

```text
Group A++ | ... | Group B
元大台灣50 0050 | 元大台灣50正2 00631L | ...
即時庫存 | 1342 | 0 | ...
```

補充：

- `00679B`、`00751B` 自動轉 `.TWO`
- 其他代號預設轉 `.TW`
- 兼容歷史 typo/短碼 `0063L -> 00631L`
- 橫向格式若沒有 cash，仍需 `--cash`

CLI 範例：

```bash
python3 -m group_a_plus.portfolio.rebalance_cli \
  --signal report/group_a_plus/latest/live_signal.json \
  --holdings-excel taiwan_stock_20260725.xlsx \
  --cash 300000 \
  --output report/group_a_plus/latest/rebalance_plan.json
```

新增驗證：

```bash
pytest tests/test_holding_snapshot.py tests/test_rebalance_cli.py
pytest tests/test_fubon_snapshot.py tests/test_holding_snapshot.py tests/test_rebalance_cli.py tests/test_rebalance_plan.py tests/test_rebalance_validation.py tests/test_rebalance_audit.py
pytest tests/test_signal_contract.py tests/test_run_ncf_daily_pipeline.py tests/test_fubon_snapshot.py tests/test_holding_snapshot.py tests/test_rebalance_cli.py tests/test_rebalance_plan.py tests/test_rebalance_validation.py tests/test_rebalance_audit.py
python3 -m compileall group_a_plus/portfolio tests/test_fubon_snapshot.py tests/test_holding_snapshot.py tests/test_rebalance_cli.py tests/test_rebalance_plan.py tests/test_rebalance_validation.py tests/test_rebalance_audit.py
```

結果：

- `12 passed`
- `35 passed`
- `64 passed`
- compile check passed

## Fubon snapshot segmentation fault investigation

日期：2026-07-29

背景：

- 已確認 `fubon_neo` 可匯入與建立 SDK，版本為 `2.2.8`
- 使用 `fubon/AES-Encryption-main` 讀取本機 AES config/key 成功
- 使用 `.p12` 憑證後，Fubon login、庫存、銀行餘額讀取都成功
- 目標仍是 read-only：只允許讀庫存與現金，不自動交易、不下單

現象：

- `python3 -m group_a_plus.portfolio.fubon_snapshot` 成功寫出：
  - `data/private/holdings_fubon_latest.json`
  - as_of `2026-07-29`
  - holdings count `8`
- 但一開始程序結束碼是 `-11`
- `-11` 是 segmentation fault，發生在資料已成功讀取與寫檔之後

定位結果：

```text
instantiate only       -> printed ok, then rc=-11
login only             -> rc=0
login + logout         -> rc=0
inventories only       -> rc=0
bank_remain only       -> rc=0
fetch snapshot only    -> read ok, then rc=-11
fetch + del + gc       -> rc=0
direct main() call     -> rc=0
python -m CLI          -> read ok, then rc=-11 before fix
python -m CLI after fix-> rc=0
```

判斷：

- 不是帳密錯誤
- 不是 `.p12` 憑證錯誤
- 不是庫存/現金 API 回傳失敗
- 不是下單 API 造成，因為 adapter 沒有呼叫 `sdk.stock` 或任何 order method
- 最可能原因是 Fubon Neo SDK 的 native/runtime component 在 WSL/Linux 的 Python interpreter shutdown 階段清理不穩

已修正：

- `.gitignore`
  - ignore `/data/private/`
  - ignore `/fubon/`
  - ignore `*.p12`、`*.pfx`
  - 避免 Fubon 本機 SDK 範例、AES key/config、憑證、庫存/現金 snapshot 被誤提交
- `group_a_plus/portfolio/fubon_snapshot.py`
  - read-only adapter 自己建立 SDK 時，在 `finally` 內嘗試 `sdk.logout()`
  - logout 後主動 `gc.collect()`
  - CLI 成功完成後 flush stdout/stderr，再用 `os._exit(0)` 避免 native SDK 在 interpreter shutdown 階段 segfault
- `group_a_plus/portfolio/__init__.py`
  - Fubon snapshot 相關匯出改為 lazy import
  - 移除 `python -m group_a_plus.portfolio.fubon_snapshot` 的 runpy warning
- `tests/test_fubon_snapshot.py`
  - 新增/調整測試，確認外部傳入 SDK 不會被 adapter 擅自 logout
  - 確認 adapter 自己建立 SDK 時會 logout

最終驗證：

```bash
.venv/bin/python -m pytest tests/test_fubon_snapshot.py tests/test_fubon_sdk_check.py
python3 -m py_compile group_a_plus/portfolio/fubon_snapshot.py group_a_plus/portfolio/__init__.py
python3 -m group_a_plus.portfolio.fubon_snapshot --help
python3 -m group_a_plus.portfolio.fubon_snapshot
```

結果：

- `13 passed`
- compile check passed
- `--help` 無 runpy warning
- 實際 Fubon snapshot 讀取成功，退出碼 `rc=0`
- 產生/更新 `data/private/holdings_fubon_latest.json`

## Group A+ local dashboard

日期：2026-07-29

目的：

- 將 latest strategy、Fubon/Excel 持倉、調倉審核、風控檢查、ops health、crash risk 集中到一個本地 read-only HTML 頁面
- 不登入 Fubon
- 不下單
- 不啟動自動交易
- 預設輸出到 `data/private/`，避免持倉、現金、調倉金額被誤提交

新增：

- `group_a_plus/dashboard/static_dashboard.py`
  - 讀取：
    - `report/group_a_plus/latest/live_signal.json`
    - `report/group_a_plus/latest/ops_health.json`
    - `report/group_a_plus/latest/crash_risk_alert.json`
    - `data/private/holdings_fubon_latest.json`
    - `data/private/rebalance_plan_latest.json`
  - 輸出：
    - `data/private/group_a_plus_dashboard.html`
- `tests/test_static_dashboard.py`
  - 驗證 HTML escape，避免 JSON 內容直接注入 HTML
  - 驗證 wrapped live signal 格式
  - 驗證缺 live signal 時會報錯

執行：

```bash
python3 -m group_a_plus.dashboard.static_dashboard --json
```

結果：

```text
output_path=data/private/group_a_plus_dashboard.html
ops_health_loaded=true
crash_risk_loaded=true
rebalance_loaded=true
holdings_loaded=true
```

使用方式：

- 直接用瀏覽器開：

```text
C:\Users\isaac\Downloads\Stock_taiwan2-main\Stock_taiwan2-main\data\private\group_a_plus_dashboard.html
```

## Local price loader for full-holding rebalance audit

問題：

- Fubon read-only snapshot 目前有 8 檔持倉
- latest signal 只內含策略目標相關的部分價格
- 產生完整 rebalance audit 時，非策略目標但仍持有的 ETF 也需要價格才能估值
- 不能用 0 或猜測價格，否則總資產與調倉金額會錯

新增：

- `group_a_plus/portfolio/price_loader.py`
  - `load_prices_json(...)`
  - `load_prices_from_ohlcv_freshness(...)`
- `tests/test_price_loader.py`

已接到：

- `group_a_plus/portfolio/rebalance_cli.py`
  - 新增 `--prices`
  - 新增 `--price-freshness`

執行：

```bash
python3 -m group_a_plus.portfolio.rebalance_cli \
  --signal report/group_a_plus/latest/live_signal.json \
  --holdings data/private/holdings_fubon_latest.json \
  --price-freshness results/ohlcv_freshness_20260727.json \
  --output data/private/rebalance_plan_latest.json \
  --dated-output data/private/rebalance_plan_20260727.json
```

結果：

- 私有 rebalance audit 產生成功
- validation result: not approved
- manual approval required: true
- 這是正確保守行為；dashboard 只顯示風控結果，不自動送單

新增驗證：

```bash
.venv/bin/python -m pytest tests/test_price_loader.py tests/test_rebalance_cli.py tests/test_static_dashboard.py tests/test_rebalance_plan.py tests/test_rebalance_validation.py tests/test_rebalance_audit.py
.venv/bin/python -m pytest tests/test_static_dashboard.py tests/test_fubon_snapshot.py tests/test_holding_snapshot.py tests/test_rebalance_cli.py
python3 -m py_compile group_a_plus/portfolio/price_loader.py group_a_plus/portfolio/rebalance_cli.py group_a_plus/dashboard/static_dashboard.py
python3 -m group_a_plus.dashboard.static_dashboard --json
```

結果：

- `24 passed`
- `25 passed`
- compile check passed
- dashboard build succeeded

## One-command dashboard refresh

日期：2026-07-29

目的：

- 把日常 dashboard 更新流程收斂成一個命令
- 預設不登入 Fubon，使用既有 `data/private/holdings_fubon_latest.json`
- 只有明確加 `--refresh-fubon` 時，才會先執行 Fubon read-only snapshot
- 全流程仍然不下單、不自動交易

新增：

- `group_a_plus/dashboard/update_dashboard.py`
  - 推斷 latest signal 的 `actual_data_date`
  - 自動使用對應的 `results/ohlcv_freshness_YYYYMMDD.json`
  - 產生/更新 `data/private/rebalance_plan_latest.json`
  - 產生/更新 `data/private/group_a_plus_dashboard.html`
  - 可選 `--refresh-fubon`
- `tests/test_update_dashboard.py`

安全預設：

```bash
python3 -m group_a_plus.dashboard.update_dashboard --json
```

實際結果：

```text
dashboard_path=data/private/group_a_plus_dashboard.html
holdings_path=data/private/holdings_fubon_latest.json
rebalance_path=data/private/rebalance_plan_latest.json
price_freshness_path=results/ohlcv_freshness_20260727.json
refresh_fubon=false
rebalance_validation_approved=false
manual_approval_required=true
```

若要同時刷新 Fubon read-only snapshot：

```bash
python3 -m group_a_plus.dashboard.update_dashboard --refresh-fubon --json
```

注意：

- `--refresh-fubon` 需要本機 Fubon SDK、憑證、環境變數已就緒
- 仍只呼叫 read-only snapshot，不呼叫任何 order API
- dashboard 顯示 validation/manual approval 結果，但不送單

新增驗證：

```bash
.venv/bin/python -m pytest tests/test_update_dashboard.py tests/test_static_dashboard.py tests/test_price_loader.py tests/test_rebalance_cli.py tests/test_rebalance_audit.py tests/test_rebalance_plan.py tests/test_rebalance_validation.py
python3 -m py_compile group_a_plus/dashboard/update_dashboard.py group_a_plus/dashboard/static_dashboard.py group_a_plus/portfolio/rebalance_cli.py group_a_plus/portfolio/price_loader.py
python3 -m group_a_plus.dashboard.update_dashboard --json
```

結果：

- `26 passed`
- compile check passed
- one-command dashboard refresh succeeded

## Final handoff summary - start here

日期：2026-07-29

目前主線判斷：

- 最新/active 策略主線是 `group_a_plus/`
- active runner 仍是 `a2118_a2111_ncf_late_bull_deleverage`
- `Stock_TaiwanII_FinRLX/` 已標示為 archive candidate
- 不建議把最新策略整包搬到 `Stock_TaiwanII_FinRLX/`
- 不建議直接使用 `Stock_TaiwanII_FinRLX/src/trading/trade_executor.py`，原因是 Alpaca/美股假設太重，且與目前 `live_signal.json` 欄位契約不一致
- 已吸收 FinRLX 值得保留的概念：broker-neutral target weights -> rebalance/audit workflow

已完成模組：

- `group_a_plus/portfolio/rebalance_plan.py`
  - 將 `live_signal.json` 的 `target_weights` 轉成 broker-neutral orders
  - 不下單
- `group_a_plus/portfolio/rebalance_validation.py`
  - 檢查單筆金額、總買入、週轉率、槓桿 ETF 權重等風控條件
- `group_a_plus/portfolio/rebalance_audit.py`
  - 產生可稽核 rebalance audit JSON
  - manual approval 預設 required/未核准
- `group_a_plus/portfolio/rebalance_cli.py`
  - CLI 入口
  - 支援 JSON holdings、Excel holdings、本地 price loader
- `group_a_plus/portfolio/holding_snapshot.py`
  - broker-neutral holdings snapshot schema
  - 支援 Fubon JSON 與 Excel loader
- `group_a_plus/portfolio/fubon_snapshot.py`
  - Fubon Neo read-only adapter
  - 只讀 inventories 與 bank_remain
  - 不呼叫任何 order API
- `group_a_plus/portfolio/fubon_sdk_check.py`
  - no-login SDK smoke check
- `group_a_plus/portfolio/price_loader.py`
  - 從 local `ohlcv_freshness_YYYYMMDD.json` 對應 parquet 補齊持倉價格
- `group_a_plus/dashboard/static_dashboard.py`
  - 產生本地 read-only HTML dashboard
- `group_a_plus/dashboard/update_dashboard.py`
  - 一鍵更新 rebalance audit + dashboard
  - 預設不刷新 Fubon
  - 加 `--refresh-fubon` 才會讀 Fubon

安全邊界：

- 沒有自動交易
- 沒有下單
- 沒有送出 broker orders
- Fubon adapter 只呼叫：
  - `sdk.login(...)`
  - `sdk.accounting.inventories(...)`
  - `sdk.accounting.bank_remain(...)`
  - `sdk.logout()`
- 測試用 AST 檢查禁止 order methods：
  - `place_order`
  - `batch_place_order`
  - `cancel_order`
  - `batch_cancel_order`
  - `modify_price`
  - `batch_modify_price`
  - `modify_quantity`
  - `batch_modify_quantity`
  - `make_modify_price_obj`
  - `make_modify_quantity_obj`

私有/敏感檔案：

- `data/private/holdings_fubon_latest.json`
  - Fubon read-only snapshot
  - 含持倉、現金、帳號欄位
- `data/private/rebalance_plan_latest.json`
  - 私有調倉審核
  - 含持倉估值與交易建議
- `data/private/group_a_plus_dashboard.html`
  - 本地 dashboard
  - 含持倉/現金/調倉摘要
- `fubon/`
  - 本機 Fubon SDK/sample/key/config 來源
- `.p12`、`.pfx`
  - 憑證

`.gitignore` 已保護：

```text
/data/private/
/fubon/
*.p12
*.pfx
```

日常操作命令：

1. 只重建 dashboard 與 rebalance audit，不登入 Fubon：

```bash
python3 -m group_a_plus.dashboard.update_dashboard --json
```

2. 讀取 Fubon 庫存/現金並更新 dashboard：

```bash
python3 -m group_a_plus.dashboard.update_dashboard --refresh-fubon --json
```

3. 只檢查 Fubon SDK，不登入：

```bash
python3 -m group_a_plus.portfolio.fubon_sdk_check --json
```

4. 只讀 Fubon holdings snapshot：

```bash
python3 -m group_a_plus.portfolio.fubon_snapshot
```

5. 手動產生 rebalance audit：

```bash
python3 -m group_a_plus.portfolio.rebalance_cli \
  --signal report/group_a_plus/latest/live_signal.json \
  --holdings data/private/holdings_fubon_latest.json \
  --price-freshness results/ohlcv_freshness_20260727.json \
  --output data/private/rebalance_plan_latest.json \
  --dated-output data/private/rebalance_plan_20260727.json
```

6. 開 dashboard：

```text
C:\Users\isaac\Downloads\Stock_taiwan2-main\Stock_taiwan2-main\data\private\group_a_plus_dashboard.html
```

目前已知狀態：

- `python3 -m group_a_plus.dashboard.update_dashboard --json` 成功
- dashboard loaded:
  - live signal: true
  - ops health: true
  - crash risk: true
  - holdings: true
  - rebalance: true
- rebalance validation 目前是 `approved=false`
- manual approval required 目前是 `true`
- 這是保守且正確的狀態；不應自動送單

Fubon SDK 注意事項：

- 本機 `fubon_neo` 版本曾確認為 `2.2.8`
- WSL/Linux 下曾遇到 Fubon native runtime 在 interpreter shutdown 觸發 `rc=-11`
- 已在 `fubon_snapshot.py` 內處理：
  - login/read/logout
  - 主動 GC
  - CLI 成功後 flush 並 `os._exit(0)`
- 修正後實際 read-only snapshot 已確認 `rc=0`

最新驗證：

```bash
.venv/bin/python -m pytest tests/test_update_dashboard.py tests/test_static_dashboard.py tests/test_price_loader.py tests/test_fubon_sdk_check.py tests/test_fubon_snapshot.py tests/test_holding_snapshot.py tests/test_rebalance_audit.py tests/test_rebalance_cli.py tests/test_rebalance_plan.py tests/test_rebalance_validation.py
python3 -m py_compile group_a_plus/dashboard/update_dashboard.py group_a_plus/dashboard/static_dashboard.py group_a_plus/portfolio/rebalance_cli.py group_a_plus/portfolio/price_loader.py
git check-ignore -v data/private/group_a_plus_dashboard.html data/private/rebalance_plan_latest.json data/private/holdings_fubon_latest.json
```

結果：

- `48 passed`
- compile check passed
- private dashboard/rebalance/holdings all ignored by `.gitignore`

目前未完成/可後續改善：

- holdings reconciliation：
  - 比對 Fubon snapshot、Excel holdings、target weights、rebalance audit 的差異
- dashboard usability:
  - 可加 last-updated badge
  - 可加 validation failure reason summary
  - 可加 one-click local open helper，但目前 HTML 已可直接開
- 完整 backtest dashboard：
  - 可將 strategy performance、drawdown、turnover、historical validation 放入第二頁
  - 不是目前安全操作主線的必要項

接手建議：

- 不要先重構 `Stock_TaiwanII_FinRLX/`
- 不要把 Fubon key/config/憑證提交
- 不要放寬 manual approval
- 若要繼續改善，優先做 holdings reconciliation，而不是改策略核心

## Giant script split - ncf_2330 phase 1

日期：2026-07-29

背景：

- `ncf_2330.py` 原本約 3,328 行
- 是 active daily pipeline 的一部分，不能直接搬移或重寫
- 外部測試/腳本仍會直接 import top-level `ncf_2330.py`
- 本階段目標是低風險拆分，不改 CLI、不改輸出、不改模型訓練流程

已完成：

- 新增 package：
  - `group_a_plus/ncf_2330/__init__.py`
  - `group_a_plus/ncf_2330/dates.py`
  - `group_a_plus/ncf_2330/leadership.py`
  - `group_a_plus/ncf_2330/market_state.py`
- 從 top-level `ncf_2330.py` 移出：
  - `resolve_end_date(...)`
  - `_add_tsmc_leadership_features(...)`
  - `_classify_tsmc_market_state(...)`
  - leadership 私有 helper `_rolling_zscore(...)`
  - leadership 私有 helper `_align_to_index(...)`
- `ncf_2330.py` 仍 re-export/import 同名函式，因此以下舊用法仍可用：

```python
from ncf_2330 import resolve_end_date
from ncf_2330 import _add_tsmc_leadership_features
from ncf_2330 import _classify_tsmc_market_state
```

拆分後大小：

```text
ncf_2330.py                         3048 lines
group_a_plus/ncf_2330/__init__.py      11 lines
group_a_plus/ncf_2330/dates.py         29 lines
group_a_plus/ncf_2330/leadership.py   104 lines
group_a_plus/ncf_2330/market_state.py 166 lines
```

驗證：

```bash
.venv/bin/python -m pytest tests/test_ncf_2330_market_state.py tests/test_resolve_end_date_zero_volume.py tests/test_ncf_2330_expanding_weights.py
.venv/bin/python -m pytest tests/test_run_ncf_daily_pipeline.py tests/test_group_a_plus_ncf_integration.py tests/test_group_a_plus_signal_alignment.py tests/test_ncf_2330_market_state.py
python3 -m py_compile ncf_2330.py group_a_plus/ncf_2330/__init__.py group_a_plus/ncf_2330/dates.py group_a_plus/ncf_2330/leadership.py group_a_plus/ncf_2330/market_state.py
python3 ncf_2330.py --help
```

結果：

- `18 passed`
- `127 passed`
- compile check passed
- `python3 ncf_2330.py --help` succeeded

注意：

- 這只是第一階段拆分
- 尚未拆 train/evaluate/predict 主流程
- 尚未處理 `train_dual_group_2024_2026.py`
- 後續若繼續，建議優先抽：
  - `group_a_plus/ncf_2330/features.py`
  - `group_a_plus/ncf_2330/labels.py`
  - `group_a_plus/ncf_2330/ensembles.py`
  - `group_a_plus/ncf_2330/outputs.py`
- 每次只抽低耦合函式，保持 `ncf_2330.py` 作為 CLI wrapper 與 backward-compatible import facade

## Fubon local path migration to C:\fubon

日期：2026-07-29

背景：

- 原先測試使用 repo 內的 `fubon/` 目錄作為 AES helper/key/config 來源
- 使用者指定改用 `C:\fubon`
- WSL 對應路徑為 `/mnt/c/fubon`
- `C:\fubon` 目前包含：
  - `AES-Encryption-main/`
  - `key/key.key`
  - `config/encrype.config`
  - Fubon Neo 2.2.8 wheel/sample

已完成：

- 新增 `group_a_plus/portfolio/fubon_local_config.py`
  - 預設 local Fubon dir 為 `C:\fubon` / `/mnt/c/fubon`
  - 支援 `FUBON_LOCAL_DIR` 覆蓋
  - 支援 `--local-config-dir` 覆蓋
  - 支援 Windows path 轉 WSL path：
    - `C:\fubon` -> `/mnt/c/fubon`
    - `C:/CAFubon/...` -> `/mnt/c/CAFubon/...`
  - 直接讀 AES key/config，不輸出解密值
  - 若 config 內舊 `.pfx` 路徑不存在，會保守搜尋同目錄或 `C:\fubon` 下唯一存在的 `.p12/.pfx`
- 更新 `group_a_plus/portfolio/fubon_snapshot.py`
  - 非密碼環境變數仍優先
  - 若 `FUBON_ID/FUBON_CERT_PATH` 不完整，會 fallback 到 `C:\fubon` 讀取非密碼 metadata
  - `FUBON_PASSWORD` 與 `FUBON_CERT_PASSWORD` 不再從 env 或 `C:\fubon` 自動使用，連線時必須手動輸入
  - 新增 CLI：

```bash
.venv/bin/python -m group_a_plus.portfolio.fubon_snapshot --local-config-dir C:\fubon
```

- 更新 `group_a_plus/dashboard/update_dashboard.py`
  - `--refresh-fubon` 預設使用 `.venv/bin/python`，因為目前 `.venv` 同時有 `fubon_neo` 與 `Crypto`
  - 新增 `--local-config-dir`

```bash
.venv/bin/python -m group_a_plus.dashboard.update_dashboard --refresh-fubon --local-config-dir C:\fubon --json
```

新增測試：

- `tests/test_fubon_local_config.py`
  - Windows path -> WSL path
  - AES fixture decrypt
  - single `.p12/.pfx` fallback
  - missing key error

驗證：

```bash
.venv/bin/python -m pytest tests/test_fubon_local_config.py tests/test_fubon_snapshot.py tests/test_update_dashboard.py tests/test_fubon_sdk_check.py
python3 -m py_compile group_a_plus/portfolio/fubon_local_config.py group_a_plus/portfolio/fubon_snapshot.py group_a_plus/dashboard/update_dashboard.py tests/test_fubon_local_config.py
python3 -m group_a_plus.portfolio.fubon_snapshot --help
.venv/bin/python -m group_a_plus.portfolio.fubon_snapshot --local-config-dir C:\fubon
.venv/bin/python -m group_a_plus.dashboard.update_dashboard --refresh-fubon --local-config-dir C:\fubon --json
```

結果：

- `19 passed`
- compile check passed
- `python3 ... fubon_snapshot --help` succeeded even though system `python3` lacks `Crypto`
- `C:\fubon` AES config decrypt check succeeded:
  - user id present
  - password present
  - cert password present
  - resolved cert path exists
- read-only Fubon snapshot succeeded:
  - `rc=0`
  - output `data/private/holdings_fubon_latest.json`
  - holdings count `8`
- one-command dashboard refresh with Fubon succeeded:
  - `rc=0`
  - `refresh_fubon=true`
  - `dashboard_loaded.holdings_loaded=true`
  - `dashboard_loaded.rebalance_loaded=true`

注意：

- 不輸出 key/password/cert password
- 不呼叫任何 order API
- `data/private/` 仍由 `.gitignore` 保護
- `C:\fubon` 在 repo 外，不會被此 repo 的 git 追蹤
## Data refresh - 2026-07-29

### Request

User asked: `下載最新資料.`

### Commands run

Primary refresh command:

```bash
.venv/bin/python scripts/run/run_ncf_daily_pipeline.py --only-refresh --force-refresh --strict-refresh --fail-on-ohlcv-warning
```

Result:

- Process exit code: `0`
- Mode: refresh-only; NCF signal generation was intentionally skipped.
- Manifest written:
  - `results/ncf_daily_pipeline_20260729.json`
- Data refresh report written:
  - `results/data_refresh_20260729.json`
- OHLCV freshness report written:
  - `results/ohlcv_freshness_20260729.json`
- Env health refreshed:
  - `report/group_a_plus/latest/strategy_env_health.json`
- Ops health refreshed by the pipeline first, then rebuilt after the external-market fix:
  - `report/group_a_plus/latest/ops_health.json`

The 18-step refresh pipeline completed the first 17 refresh steps successfully. The final `ohlcv_freshness` step initially produced a non-fatal warning/error because some external-market yfinance tickers were stale.

### Primary pipeline steps observed

Completed:

- `refresh_group_data`
- `refresh_taifex`
- `refresh_taifex_options`
- `refresh_institutional`
- `refresh_margin`
- `refresh_market_margin`
- `refresh_derivative_institutional`
- `refresh_securities_lending`
- `securities_lending_0050_source_status`
- `refresh_dealer_positions`
- `refresh_foreign_shareholding`
- `refresh_short_sale_balances`
- `refresh_day_trading`
- `refresh_soxx_options_iv`
- `refresh_cross_market_ohlcv`
- `refresh_2330_per`
- `refresh_shareholding`

Final check:

- `ohlcv_freshness` initially failed under strict `--fail-on-warning`, but the pipeline treats this as a non-fatal best-effort refresh step and still completed refresh-only mode.

### External-market stale fix

Initial freshness errors were only in external-market OHLCV:

- `^GSPC`
- `^TNX`
- `^IRX`
- `GC=F`

Reason found:

- `scripts/misc/check_ohlcv_freshness.py` checks those tickers.
- `scripts/fetch/fetch_cross_market_ohlcv.py` default ticker set does not include all four of them.

Manual補抓 command:

```bash
.venv/bin/python scripts/fetch/fetch_cross_market_ohlcv.py --tickers ^GSPC,^TNX,^IRX,GC=F
```

Result:

- `^GSPC`: available, last date `2026-07-28`
- `^TNX`: available, last date `2026-07-28`
- `^IRX`: available, last date `2026-07-28`
- `GC=F`: available, last date `2026-07-29`

Then reran freshness check:

```bash
.venv/bin/python scripts/misc/check_ohlcv_freshness.py --target-date auto --max-db-lag-days 3 --output results/ohlcv_freshness_20260729.json --fail-on-warning
```

Result:

- Exit code: `1`, expected under `--fail-on-warning` because台股 raw cache still has warning.
- `overall_status`: `warning`
- `target_date`: `2026-07-29`
- `external_error_tickers`: empty
- Taiwan ETF DB max date: `2026-07-28`, lag 1 day, within max DB lag 3 days.
- Remaining warnings are `raw_cache_missing` for Taiwan ETF raw cache against target date `2026-07-29`.

Interpretation:

- Data download is usable.
- Core DB is not stale beyond policy.
- The remaining warning is not an external-data failure and not a DB-lag failure.
- Because live signal was not regenerated in refresh-only mode, signal date remains older than the newly refreshed data.

### Ops health after fix

Rebuilt ops health with:

```bash
.venv/bin/python -m group_a_plus.operations.ops_health
```

Final summary:

- `ops_health.status`: `warning`
- `ops_health.errors`: none
- `ops_health.warnings`:
  - `system_resources`
  - `artifact_health`
  - `module_health`
  - `external_data_freshness`

Important notes:

- `system_resources` warning includes low disk free ratio under the existing policy.
- `artifact_health` includes known old/frozen artifacts, not a new refresh failure.
- `external_data_freshness` is now warning-level, not error-level.

### Dashboard note

Dashboard was regenerated successfully once with:

```bash
.venv/bin/python -m group_a_plus.dashboard.update_dashboard --json
```

Output:

- `data/private/group_a_plus_dashboard.html`
- `data/private/rebalance_plan_latest.json`

Important behavior:

- `update_dashboard.py` infers freshness report from the active live signal's `actual_data_date`.
- Because this run was refresh-only and did not regenerate live signal, the dashboard auto-selected the older signal-date freshness report, not necessarily `results/ohlcv_freshness_20260729.json`.
- A later attempt to force `--price-freshness results/ohlcv_freshness_20260729.json` did not return output within the expected time and was interrupted to avoid leaving a hanging command.
- The data refresh itself is complete; the dashboard freshness selection behavior is a separate UX/runner issue.

Recommended follow-up:

- Add an option or default behavior in `group_a_plus.dashboard.update_dashboard` to use the newest available `results/ohlcv_freshness_*.json` when the user is refreshing data only, while preserving signal-date inference for strict signal/rebalance audits.
- Add the four freshness-required external tickers (`^GSPC`, `^TNX`, `^IRX`, `GC=F`) to the default cross-market refresh ticker set, or create a named `--freshness-required` mode.

## GroupA+ 2026-07-30 prediction - 1,000,000 TWD

### Request

User asked: `在groupA+,使用golden1_0531 及最新策略,以1百萬, 預測7/30`

### Scope and assumptions

- Prediction date requested: `2026-07-30`
- Capital: `1,000,000`
- No broker login, no real holdings, no order submission.
- Golden1 was run with empty holdings override and `--extra-cash 1000000`.
- Available Taiwan ETF DB data at run time was through `2026-07-28`.
- Therefore the 7/30 prediction is based on `actual_data_date=2026-07-28`, stale 2 calendar days, within the Golden1 runner's `--max-stale-days 3` policy.

### Golden1_0531 command

```bash
.venv/bin/python scripts/run/run_group_a_combined_signal.py \
  --as-of-date 2026-07-30 \
  --download-end 2026-07-29 \
  --extra-cash 1000000 \
  --override-holdings-json '{"0050":0,"00631L":0,"00632R":0}' \
  --max-stale-days 3
```

Result:

- Signal generated successfully.
- Stable files overwritten by the official runner:
  - `results/group_a_combined_live_latest.json`
  - `results/group_a_combined_live_latest.csv`
  - `results/group_a_combined_bundle_latest.json`
- Generated dated signal:
  - `results/signal_group_a_20260729_141612.json`
  - `results/signal_group_a_20260729_141612.csv`

Golden1 signal summary:

- `requested_as_of_date`: `2026-07-30`
- `actual_data_date`: `2026-07-28`
- `signal_status`: `rebalance`
- `signal_reason`: `pva_overlay_m; limited_0050_target_weight_step;ma_brake_capped_0050;ma_brake_capped_00631l`
- latest prices used:
  - `0050.TW`: `97.1500015258789`
  - `00631L.TW`: `30.600000381469727`
  - `00632R.TW`: `11.079999923706055`
  - `00679B.TWO`: `26.90999984741211`

Golden1 executable target weights for 1,000,000:

- `0050.TW`: `30.0000%`, runner target shares `3088`
- `00631L.TW`: `0.0000%`, runner target shares `0`
- `00632R.TW`: `25.8939%`, runner target shares `23370`
- `00679B.TWO`: `0.0000%`, runner target shares `0`
- `cash`: `44.1061%`

Note:

- The runner also reported a planned/pre-overlay candidate of `0050 37.1% / 00631L 7.0% / 00632R 25.9% / cash 30.0%`.
- The executable target after MA brake and step limits became `0050 30.0% / 00632R 25.9% / cash 44.1%`.

### Latest active strategy command

Initial attempt:

```bash
.venv/bin/python -m group_a_plus.runners.latest --start 2025-01-02 --end latest --initial-value 1000000 ...
```

Result:

- Failed because `group_a_plus.runners.latest` passes `"latest"` through to the active runner without resolving it.
- Error JSON was overwritten by the successful rerun below.

Successful command:

```bash
.venv/bin/python -m group_a_plus.runners.latest \
  --start 2025-01-02 \
  --end 2026-07-28 \
  --initial-value 1000000 \
  --output results/group_a_plus_latest_predict_20260730_1m.json \
  --frame-output results/group_a_plus_latest_predict_20260730_1m_frame.csv
```

Result files:

- `results/group_a_plus_latest_predict_20260730_1m.json`
- `results/group_a_plus_latest_predict_20260730_1m_frame.csv`

Latest active strategy summary:

- `active_strategy_id`: `a2118_a2111_ncf_late_bull_deleverage`
- `status`: `active`
- backtest/prediction window: `2025-01-02` to `2026-07-28`
- rows: `369`
- `today_regime`: `group_a_plus_defensive`

Latest active strategy live weights for 1,000,000:

- `0050.TW`: `40.0000%`
- `00631L.TW`: `0.0000%`
- `00632R.TW`: `0.0000%`
- `00679B.TWO`: `30.0000%`
- `cash`: `30.0000%`

Approximate floor-share conversion using Golden1 latest prices:

- `0050.TW`: 4,117 shares, about `399,966.56`
- `00679B.TWO`: 11,148 shares, about `299,992.68`
- cash after floor-share conversion: about `300,040.77`

Latest active strategy metrics over the runner window:

- final value from 1,000,000 initial value: `1,150,520.59`
- total return: `15.0521%`
- annual return: `9.3664%`
- Sharpe: `0.9769`
- Sortino: `0.9923`
- max drawdown: `-11.5125%`

### NCF limitation

Initial latest strategy run reported:

- `ncf_live_signal.status`: `stale`
- reason: `ncf_date_mismatch`
- NCF file: `results/ncf_00631l_latest_20260727.json`
- NCF signal date: `2026-07-27`
- frame data date: `2026-07-28`
- late-bull trigger: `false`
- effective hedge active: `false`

Attempted to repair this by running:

```bash
.venv/bin/python scripts/run/run_ncf_daily_pipeline.py --skip-refresh --skip-commentary --ohlcv-target-date 2026-07-28
```

Result:

- Pipeline started and passed `ohlcv_freshness`.
- It remained in `[2/74] ncf_00631l` for longer than expected.
- The session was interrupted with Ctrl-C before `ncf_00631l` completed.
- Follow-up diagnosis found that this was not a data/load failure: the script had already loaded DB data, external features, and completed the H=1 model before reaching the slower H=5/H=20 classifier training.

Interpretation:

- The first interruption was premature. `ncf_00631l.py` was slow, not broken.
- `.venv/bin/python` loads `sklearn 1.8.0` from user-site (`/home/isaacliu33252/.local/lib/python3.12/site-packages`) because `.venv/pyvenv.cfg` has `include-system-site-packages = true` and `.venv` itself does not contain sklearn.
- `ncf_00631l.py --help` also takes several seconds because the giant script imports ML/matplotlib dependencies before argparse returns.
- Matplotlib warns that `/home/isaacliu33252/.config/matplotlib` is not writable; setting `MPLCONFIGDIR=/tmp/matplotlib-ncf` avoids that warning for this run.

Successful standalone repair command:

```bash
MPLCONFIGDIR=/tmp/matplotlib-ncf .venv/bin/python scripts/misc/ncf_00631l.py \
  --train-start 2020-01-01 \
  --val-start 2025-01-02 \
  --val-end latest \
  --output results/ncf_00631l_latest_20260729.json \
  --val-predictions-output results/ncf_00631l_panel_latest_20260729.csv \
  --full-panel \
  --no-tabnet
```

Successful repair result:

- `results/ncf_00631l_latest_20260729.json`
- `results/ncf_00631l_panel_latest_20260729.csv`
- NCF summary date: `2026-07-28`
- horizon ensemble: `UP`
- combined prob: `0.540`
- confidence: `0.359`
- H=20 direction: `DOWN`, probability `0.288`
- forward 20d MDD > 5% probability: `0.184`
- forward 20d max gain > 5% probability: `0.923`

After rerunning latest strategy:

- `ncf_live_signal.status`: `ok`
- `ncf_live_signal.signal_date`: `2026-07-28`
- `ncf_live_signal.frame_data_date`: `2026-07-28`
- `late_bull_triggered`: `false`
- `today_regime`: `group_a_plus_defensive`
- live weights unchanged: `0050 40% / 00679B 30% / cash 30%`

Recommended follow-up:

- Add `MPLCONFIGDIR=/tmp/matplotlib-ncf` or similar env handling in the daily NCF runner to avoid Matplotlib cache warnings.
- Consider installing/pinning sklearn and related ML deps inside `.venv`, or set an explicit policy that the project intentionally uses user-site ML packages. The current mixed environment is reproducible only if `/home/isaacliu33252/.local` remains unchanged.
- Add progress flushing or timestamps around each horizon/model fit in `ncf_00631l.py`; otherwise slow HGB/LGB/XGB/CatBoost fits look like a hang.

### Comparison artifact

Machine-readable comparison written:

- `results/group_a_plus_predict_20260730_1m_comparison.json`

Short comparison:

- Golden1_0531: defensive/inverse-hedge-like executable target, `0050 30.0% / 00632R 25.8939% / cash 44.1061%`.
- Latest active A21.18: defensive basket, `0050 40.0% / 00679B 30.0% / cash 30.0%`.
- Both are defensive for the 7/30 prediction. Golden1 uses inverse ETF exposure (`00632R`), while latest active strategy uses bond ETF (`00679B`) instead.

## Production / shadow boundary phase 1 - 2026-07-29

### Request

User asked whether this recommendation is reasonable and then approved continuing:

> 建立 production / shadow 分離機制；大量 shadow、handoff 實驗檔散落根目錄；建議統一進 experiments/ 或 research/ 目錄，不汙染根目錄

### Decision

The recommendation is reasonable, but moving files immediately is risky because
production runners still read several legacy root files and report artifacts.

Implemented phase 1 only:

- define the boundary
- create target directories
- add guard tests
- do not move existing legacy scripts or handoff files yet

### Files added

- `docs/PRODUCTION_SHADOW_BOUNDARY.md`
- `research/README.md`
- `experiments/README.md`
- `handoff/README.md`
- `archive/README.md`
- `tests/test_production_shadow_boundary.py`

### Boundary rules added

- Active production manifest must not point into:
  - `research/`
  - `experiments/`
  - `handoff/`
  - `archive/`
- New shadow/research reports should declare one of:
  - `active_allocation_impact: none`
  - `research_only: true`
  - a `policy` string containing `research_only` or `shadow`
- New handoff documents should go under `handoff/YYYY-MM/` unless they are release/source-of-truth documents.
- New sweeps and ablations should go under `experiments/`.
- Existing scattered root files are legacy debt and should be moved only in small verified batches.

### Validation

Command:

```bash
.venv/bin/python -m pytest -q tests/test_production_shadow_boundary.py tests/test_group_a_plus_latest_strategy.py
```

Result:

- `27 passed`

### Follow-up

Recommended next phase:

- Build a root-level Markdown inventory and classify files as:
  - production source-of-truth
  - handoff
  - research/import review
  - archive candidate
- Move Markdown-only handoff/research files first.
- Do not move Python scripts until `rg` confirms imports/call sites and guard tests cover the active path.

## Production / shadow boundary phase 2a - root Markdown inventory

### Scope

Implemented the next low-risk cleanup step:

- generate a root-level Markdown inventory
- classify root Markdown files before moving them
- move only a small safe batch of external import-review documents
- keep production source-of-truth and active manifest references in root

### Files added

- `scripts/report/build_root_markdown_inventory.py`
- `handoff/root_markdown_inventory_20260729.md`
- `research/import_reviews/README.md`

### Inventory output

Generated:

```bash
.venv/bin/python scripts/report/build_root_markdown_inventory.py
```

Output:

- `handoff/root_markdown_inventory_20260729.md`

Current summary after the first move batch:

- `production_source`: 4
- `active_manifest_reference`: 4
- `research_import_review`: 9
- `handoff`: 94
- `experiment`: 10
- `research_shadow`: 6
- `possible_source_of_truth`: 1
- `unclassified_review_required`: 39

Active manifest Markdown references detected:

- `GROUP_A_PLUS_2020_COVID_SWITCH_RULE_FIX_HANDOFF_20260706.md`
- `GROUP_A_PLUS_A2118_HANDOFF_20260628.md`
- `STOCK_PREDICTION_MODELS_IMPORT_REVIEW_20260630.md`
- `STOCK_RNN_IMPORT_REVIEW_20260630.md`

These four should not be moved until a dedicated migration updates
`report/group_a_plus/latest/strategy.json` and any related decision records.

### First safe move batch

Moved to `research/import_reviews/`:

- `AJENTI_IMPORT_REVIEW_20260701.md`
- `OPENSTOCK_IMPORT_REVIEW_20260630.md`
- `OPENSTOCK_CHANGELOG_20260630.md`
- `STOCKFISH_IMPORT_REVIEW_20260630.md`
- `STOCKFISH_CHANGELOG_20260630.md`
- `STOCKSPROJECT_IMPORT_REVIEW_20260701.md`

Pre-move reference check:

```bash
rg "AJENTI_IMPORT_REVIEW_20260701|OPENSTOCK_(IMPORT_REVIEW|CHANGELOG)_20260630|STOCKFISH_(IMPORT_REVIEW|CHANGELOG)_20260630|STOCKSPROJECT_IMPORT_REVIEW_20260701" -n . --glob '!research/import_reviews/**'
```

Findings:

- Only same-batch changelog/import-review internal references were found.
- No active runner, daily pipeline, or active manifest reference was found.

Post-move reference check:

- No references outside `research/import_reviews/` were found.

### Validation

Command:

```bash
.venv/bin/python -m pytest -q tests/test_production_shadow_boundary.py tests/test_group_a_plus_latest_strategy.py
.venv/bin/python -m py_compile scripts/report/build_root_markdown_inventory.py
```

Result:

- `27 passed`
- `py_compile` returned success.

## Production / shadow boundary phase 2g - root Markdown classification and safe research/report batches

### Scope

Improved `scripts/report/build_root_markdown_inventory.py` so root Markdown cleanup has more useful categories before moving more files.

Before this phase, the inventory still had `39` files in `unclassified_review_required`. That was too broad and made the next cleanup step risky because reports, checks, governance records, and current-session handoff records were all mixed together.

### Classification changes

Added explicit categories/markers:

- `current_session_record`
  - keeps `FINRL_CONSOLIDATION_ARCHIVE_CANDIDATES_20260729.md` in root as the active consolidation record.
- `governance_record`
  - for pipeline, ops, retention, signal contract, and stale-input fix records.
- `review_report`
  - for audit/check/checklist/evaluation/memo/report/review/summary/validation records.
- `improvement_research`
  - for backtest/branch/calibration/cash/conformal/gate/improvement/next-step/overlay/preliminary/proxy/ranking records.
- `research_import_review`
  - expanded to include `FINRL_META_*IMPORT*` documents.

Also updated the inventory recommended move order:

- Move `experiment`, `research_shadow`, `improvement_research`, and `review_report` only after reference checks.
- Keep `production_source`, `active_manifest_reference`, `current_session_record`, `governance_record`, and `possible_source_of_truth` in root until a dedicated migration updates references.

### Files added

- `research/improvement_notes/README.md`
- `research/review_reports/README.md`

### Files moved to `research/improvement_notes/`

Reference check found no external references for these files, excluding the generated inventory:

- `GROUP_AB_ALLOCATION_IMPROVEMENT_20260605.md`
- `GROUP_AB_META_ALLOCATION_PRELIMINARY_20260531.md`
- `GROUP_AB_NO2884_BACKTEST_20260605.md`
- `GROUP_A_00679B_90_10_IMPROVEMENT_20260604.md`
- `GROUP_A_HOLD10_NEXT_STEP_20260605.md`
- `GROUP_A_IMPROVEMENT_PACK_20260605.md`
- `GROUP_A_REGIME_AWARE_00632R_RANKING_20260605.md`
- `GROUP_A_SELECTOR_OVERLAY_20260605.md`
- `GROUP_A_TDCC_IMPROVEMENT_BRANCH.md`
- `GROUP_A_PLUS_A20_IMPROVEMENT_20260618.md`
- `GROUP_A_PLUS_IMPROVEMENT_20260609.md`
- `IMPROVEMENTS_v2.md`
- `IMPROVEMENTS_v3.md`

### Files moved to `research/review_reports/`

Reference check found no external references for these files, excluding the generated inventory:

- `GROUP_A_2008_00632R_CHECK_20260605.md`
- `GROUP_A_2008_CONDITIONAL_00632R_CHECK_20260606.md`
- `TWII_PROXY_2008_STRESS_REPORT_2026-05-24.md`
- `GROUP_A_PLUS_FORMAL_REPORT_20260613.md`
- `GROUP_A_PLUS_RISKLAB_EVALUATION_20260622.md`

### Files intentionally kept in root

Kept because they are referenced by active manifest, production code, root handoff/index files, or current consolidation notes:

- `GROUP_A_FINRLX_GAP_CHECKLIST_2026-05-24.md`
  - referenced by this consolidation handoff.
- `GROUP_A_LEVERAGE_CAP_DUAL_OBJECTIVE_REPORT_2026-05-24.md`
  - referenced by `GROUP_A_DEFENSIVE_CAP20_HANDOFF_2026-05-24.md`.
- `GROUP_A_PLUS_00631L_CAP_CHECK_20260618.md`
  - referenced by `handoff/2026-06/WORK_LOG_20260617_20260618.md`.
- `GROUP_A_PLUS_DFL_ACTION_VALUE_CALIBRATION_PHASE2_20260727.md`
  - referenced by `group_a_plus/integrations/ncf_decision_calibration.py`, `scripts/evaluate/evaluate_ncf_decision_calibration.py`, and July handoff/index docs.
- `GROUP_A_PLUS_MULTI_WINDOW_GATE_20260706.md`
  - referenced by governance and final decision handoffs.
- `GROUP_A_PLUS_PLUS_00751B_CASH_20260619.md`
  - referenced by `scripts/backtest/backtest_group_full.py` and July handoff docs.
- `GROUP_A_PLUS_SMART_MONEY_COST_PROXY_20260618.md`
  - referenced by `RESULTS_RETENTION_CANDIDATES_20260708.md`.
- `GROUP_A_PLUS_TAIL_CONFORMAL_ACI_20260727.md`
  - referenced by `group_a_plus/integrations/tail_conformal.py` and July handoff/index docs.
- `GROUP_A_PLUS_FINAL_DECISION_MEMO_20260706.md`
  - referenced by active strategy handoff and governance/fix docs.
- `GROUP_A_PLUS_NCF_PANEL_DRIFT_AUDIT_20260706.md`
  - referenced by `report/group_a_plus/latest/strategy.json`, tests, NCF scripts, and governance docs.
- `GROUP_A_PLUS_PROMOTION_GATE_SUMMARY_20260706.md`
  - referenced by governance docs.
- `GROUP_A_PLUS_SIGNAL_VALIDATION_CHECKLIST_20260723.md`
  - referenced by `report/group_a_plus/latest/strategy.json`, `group_a_plus/core/signal_contract.py`, evaluation scripts, docs, and July handoffs.
- `GROUP_A_PLUS_TROUGH_REENTRY_2509_05922_REVIEW_AND_SAMPLE_EXPANSION_20260727.md`
  - referenced by `GROUP_A_PLUS_TAIL_CONFORMAL_ACI_20260727.md` and July handoff/index docs.

### Inventory update

Regenerated:

```bash
.venv/bin/python scripts/report/build_root_markdown_inventory.py
```

Updated `handoff/root_markdown_inventory_20260729.md` summary:

- `unclassified_review_required`: `39` -> `0`
- `improvement_research`: `18` after classification, then `5` after safe moves
- `review_report`: `13` after classification, then `8` after safe moves
- active manifest references remain `4`

### Validation

Commands:

```bash
.venv/bin/python -m py_compile scripts/report/build_root_markdown_inventory.py
.venv/bin/python -m pytest -q tests/test_production_shadow_boundary.py tests/test_group_a_plus_latest_strategy.py
```

Result:

- `27 passed`
- `py_compile` returned success.

### Next safe cleanup candidates

The remaining root Markdown files are not all safe to move by category alone. Suggested next steps:

1. For files referenced only by moved/old handoff docs, move the target and update relative links in the referencing docs in the same patch.
2. Keep `GROUP_A_PLUS_SIGNAL_VALIDATION_CHECKLIST_20260723.md`, `GROUP_A_PLUS_NCF_PANEL_DRIFT_AUDIT_20260706.md`, and `GROUP_A_PLUS_TAIL_CONFORMAL_ACI_20260727.md` in root unless code references are migrated.
3. Keep `GROUP_A_PLUS_DFL_ACTION_VALUE_CALIBRATION_PHASE2_20260727.md` in root unless `group_a_plus/integrations/ncf_decision_calibration.py` and evaluate script comments are updated.
4. Keep `GROUP_A_PLUS_DEFINITION_20260606.md` in root until a production-source decision says whether it is still authoritative.

### Next recommended batch

Do not move Python scripts yet.

Suggested next Markdown-only target:

- older root handoff files into `handoff/YYYY-MM/`

Before moving, run `rg` for each batch and keep active manifest references in root unless the manifest is migrated at the same time.

## Production / shadow boundary phase 2b - 2026-06 handoff batch

### Scope

Moved a small batch of generic June 2026 GroupA+ handoff files from root to
`handoff/2026-06/`.

Did not move:

- active manifest references
- release/source-of-truth documents
- Python scripts
- NCF handoff files referenced by `GROUP_A_PLUS_A2118_HANDOFF_20260628.md`

### Files moved

Moved to `handoff/2026-06/`:

- `GROUP_A_PLUS_HANDOFF_20260606.md`
- `GROUP_A_PLUS_HANDOFF_20260609.md`
- `GROUP_A_PLUS_HANDOFF_20260609_FINAL.md`
- `GROUP_A_PLUS_HANDOFF_20260619.md`
- `GROUP_A_PLUS_HANDOFF_20260621.md`
- `GROUP_A_PLUS_HANDOFF_20260623.md`
- `GROUP_A_PLUS_HANDOFF_20260625.md`
- `GROUP_A_PLUS_HANDOFF_20260625_IMPROVEMENTS.md`
- `GROUP_A_PLUS_HANDOFF_20260626.md`

### Reference check

Pre-move command:

```bash
rg "GROUP_A_PLUS_HANDOFF_20260606|GROUP_A_PLUS_HANDOFF_20260609|GROUP_A_PLUS_HANDOFF_20260609_FINAL|GROUP_A_PLUS_HANDOFF_20260619|GROUP_A_PLUS_HANDOFF_20260621|GROUP_A_PLUS_HANDOFF_20260623|GROUP_A_PLUS_HANDOFF_20260625|GROUP_A_PLUS_HANDOFF_20260625_IMPROVEMENTS|GROUP_A_PLUS_HANDOFF_20260626" -n . --glob '!handoff/2026-06/**'
```

Finding:

- No production runner or active manifest reference to this generic handoff batch.
- The apparent nearby hit in `GROUP_A_PLUS_A2118_HANDOFF_20260628.md` is for `NCF_GROUP_A_PLUS_HANDOFF_20260626.md`, not the moved `GROUP_A_PLUS_HANDOFF_20260626.md`.

Post-move check:

- No outside references to the moved generic handoff files.

### Inventory update

Regenerated:

```bash
.venv/bin/python scripts/report/build_root_markdown_inventory.py
```

Updated `handoff/root_markdown_inventory_20260729.md` summary:

- `handoff`: `94` -> `85`
- active manifest references remain `4`

### Validation

Command:

```bash
.venv/bin/python -m pytest -q tests/test_production_shadow_boundary.py tests/test_group_a_plus_latest_strategy.py
.venv/bin/python -m py_compile scripts/report/build_root_markdown_inventory.py
```

Result:

- `27 passed`
- `py_compile` returned success.

## Production / shadow boundary phase 2c - 2026-06 handoff batch 2

### Scope

Moved a second small batch of June 2026 handoff files that had no outside
references after `rg` checks.

Kept in root because they still have outside references:

- `Three_Direction_Handoff_20260620.md` - mentioned by active strategy manifest note and July revert handoff.
- `GOLDEN_00631L_HANDOFF_20260620.md` - mentioned by code/commentary context in `group_a_plus/core/signal_contract.py`.
- `GROUP_AB_FINAL_HANDOFF_20260605.md` - mentioned by a July SPO paper review handoff.
- `GROUP_A_PLUS_FEATURE_SWEEP_HANDOFF_20260630.md` - mentioned by July handoff files.

### Files moved

Moved to `handoff/2026-06/`:

- `ALPHALENS_FACTOR_LENS_GROUP_A_PLUS_HANDOFF_20260629.md`
- `GROUP_A_PLUS_A213_HANDOFF_20260620.md`
- `GROUP_A_PLUS_BB_FEATURES_HANDOFF_20260630.md`
- `TBRAIN_FEATURES_GROUP_A_PLUS_HANDOFF_20260629.md`
- `WORK_LOG_20260617_20260618.md`

### Inventory update

Regenerated:

```bash
.venv/bin/python scripts/report/build_root_markdown_inventory.py
```

Updated `handoff/root_markdown_inventory_20260729.md` summary:

- `handoff`: `85` -> `80`
- active manifest references remain `4`

### Validation

Command:

```bash
.venv/bin/python -m pytest -q tests/test_production_shadow_boundary.py tests/test_group_a_plus_latest_strategy.py
.venv/bin/python -m py_compile scripts/report/build_root_markdown_inventory.py
```

Result:

- `27 passed`
- `py_compile` returned success.

## Production / shadow boundary phase 2d - import review batch 2

### Scope

Moved the remaining safe root-level import-review Markdown files to
`research/import_reviews/`.

Kept in root:

- `STOCK_PREDICTION_MODELS_IMPORT_REVIEW_20260630.md` - active manifest reference.
- `STOCK_RNN_IMPORT_REVIEW_20260630.md` - active manifest reference.
- `ALPHAGEN_IMPORT_REVIEW_20260701.md` - referenced by `ALPHAGEN_LITE_HANDOFF_20260701.md` and `scripts/evaluate/evaluate_alphagen_lite_feature_pool.py`.
- `WEIGHTWATCHER_IMPORT_REVIEW_20260701.md` - referenced by `GROUP_A_PLUS_MODEL_WEIGHT_HEALTH_HANDOFF_20260701.md`.

### Files moved

Moved to `research/import_reviews/`:

- `EVENT_DRIVEN_SENTIMENT_IMPORT_REVIEW_20260701.md`
- `FINRL_META_FINAL_SHADOW_IMPORT_20260605.md`
- `PREDICTING_STOCK_PRICES_IMPORT_REVIEW_20260701.md`
- `STOCKMIXER_ATFNET_IMPORT_REVIEW_20260702.md`
- `STOCKPREDICTIONAI_IMPORT_REVIEW_20260630.md`
- `STOCK_PREDICTION_DEEP_NEURAL_LEARNING_IMPORT_REVIEW_20260701.md`
- `STOCK_PREDICT_LSTM_IMPORT_REVIEW_20260701.md`

### Inventory update

Regenerated:

```bash
.venv/bin/python scripts/report/build_root_markdown_inventory.py
```

Updated `handoff/root_markdown_inventory_20260729.md` summary:

- `research_import_review`: `9` -> `2`
- active manifest references remain `4`

### Validation

Command:

```bash
.venv/bin/python -m pytest -q tests/test_production_shadow_boundary.py tests/test_group_a_plus_latest_strategy.py
.venv/bin/python -m py_compile scripts/report/build_root_markdown_inventory.py
```

Result:

- `27 passed`
- `py_compile` returned success.

## Production / shadow boundary phase 2e - research shadow batch

### Scope

Moved safe root-level `research_shadow` Markdown files to `research/shadow/`.

Kept in root:

- `GROUP_A_00679B_CONTINUOUS_SHADOW_20260605.md`
- `GROUP_A_00679B_OVERLAY_SHADOW_20260604.md`
- `GROUP_A_00679B_REBALANCE_FEE_SHADOW_20260604.md`

Reason:

- These three are referenced by `GROUP_A_HANDOFF_2026-06-05.md`, so moving them
  would require either updating that handoff or accepting broken relative
  references. Deferred to a dedicated batch.

### Files added

- `research/shadow/README.md`

### Files moved

Moved to `research/shadow/`:

- `GROUP_AB_GROUP_A_IMPROVEMENT_RESEARCH_20260605.md`
- `GROUP_AB_HOLD10_NO2884_RESEARCH_20260605.md`
- `GROUP_A_SHAREHOLDING_SHADOW_BRANCH.md`

### Inventory update

Regenerated:

```bash
.venv/bin/python scripts/report/build_root_markdown_inventory.py
```

Updated `handoff/root_markdown_inventory_20260729.md` summary:

- `research_shadow`: `6` -> `3`
- active manifest references remain `4`

### Validation

Command:

```bash
.venv/bin/python -m pytest -q tests/test_production_shadow_boundary.py tests/test_group_a_plus_latest_strategy.py
.venv/bin/python -m py_compile scripts/report/build_root_markdown_inventory.py
```

Result:

- `27 passed`
- `py_compile` returned success.

## Production / shadow boundary phase 2f - experiment Markdown batch

### Scope

Moved safe root-level experiment/sweep Markdown files to `experiments/markdown/`.

Kept in root:

- `EXPERIMENT_RESULTS_2026-05-22.md` - referenced by `GROUP_A_LATEST_HANDOFF_2026-05-22.md` and paired with `GROUP_A_OPTIMIZATION_2026-05-22.md`.
- `GROUP_A_OPTIMIZATION_2026-05-22.md` - referenced by `EXPERIMENT_RESULTS_2026-05-22.md` and `GROUP_A_LATEST_HANDOFF_2026-05-22.md`.
- `GROUP_A_GOLDEN1_0531_IMPROVEMENT_EXPERIMENT.md` - referenced by `GROUP_A_GOLDEN1_0531_RELEASE.md`, `EXPERIMENT_HANDOFF_2026-06-03.md`, and July staleness handoff.
- `GROUP_AB_PARAMETER_OPTIMIZATION_20260605.md` - referenced by `GROUP_AB_FINAL_HANDOFF_20260605.md`.
- `OPTIMIZATION_LOG.md` - historical root optimization log; self-referenced and not moved in this batch.

### Files added

- `experiments/markdown/README.md`

### Files moved

Moved to `experiments/markdown/`:

- `GROUP_AB_ALLOCATION_SWEEP_20260605.md`
- `GROUP_A_00632R_CONDITIONAL_SWEEP_20260606.md`
- `GROUP_A_00632R_DCA_SWEEP_20260605.md`
- `GROUP_A_EXPERIMENT_LOG_2026-05-26.md`
- `GROUP_A_TDCC_IMPROVEMENT_SWEEP_20260605.md`

### Inventory update

Regenerated:

```bash
.venv/bin/python scripts/report/build_root_markdown_inventory.py
```

Updated `handoff/root_markdown_inventory_20260729.md` summary:

- `experiment`: `10` -> `5`
- active manifest references remain `4`

### Validation

Command:

```bash
.venv/bin/python -m pytest -q tests/test_production_shadow_boundary.py tests/test_group_a_plus_latest_strategy.py
.venv/bin/python -m py_compile scripts/report/build_root_markdown_inventory.py
```

Result:

- `27 passed`
- `py_compile` returned success.

## 2026-07-29 latest handoff recommendation

### Current state

This cleanup is in a good checkpoint state:

- Production/shadow boundary structure exists:
  - `docs/PRODUCTION_SHADOW_BOUNDARY.md`
  - `research/`
  - `experiments/`
  - `handoff/`
  - `archive/`
- Root Markdown inventory exists and is reproducible:
  - `scripts/report/build_root_markdown_inventory.py`
  - `handoff/root_markdown_inventory_20260729.md`
- Root Markdown `unclassified_review_required` is now `0`.
- Active strategy manifest references remain unchanged at `4`.
- Guard tests confirm active strategy does not point into shadow-only directories.

### Recommended next sequence

1. Commit the current cleanup before doing more strategy work.
   - Reason: the diff is already large and includes file moves, new boundary docs, dashboard/portfolio modules, Fubon read-only helpers, and partial NCF split.
   - A commit now gives a clean rollback point before touching high-risk strategy code.

2. Continue splitting giant scripts, especially `ncf_2330.py`.
   - Phase 1 already moved some helpers into `group_a_plus/ncf_2330/`.
   - Recommended next modules:
     - `features.py`
     - `training.py`
     - `prediction.py`
     - `reporting.py`
   - Keep exports/import compatibility during each phase.

3. Keep `Stock_TaiwanII_FinRLX/` as archive candidate, not the new main project root.
   - Current active line is `group_a_plus/`.
   - `Stock_TaiwanII_FinRLX/` did not show live imports.
   - Its useful idea was already absorbed in a safer form: broker-neutral rebalance plan, validation, audit, holding snapshot, Fubon read-only snapshot, and dashboard.

4. Keep Fubon read-only for now.
   - Do not connect order placement or automatic trading.
   - Safe next additions:
     - read-only config validation report
     - snapshot audit export
     - dashboard panels for cash, holdings, target weights, and gap-to-target
   - Do not print account IDs, cash amounts, holdings, or certificate paths in public handoff/final summaries.

5. Pause aggressive Markdown moves.
   - The easy no-reference batches are done.
   - Remaining root Markdown files are mostly referenced by code, manifest, handoff indexes, or governance docs.
   - Any further moves should update all relative references in the same patch.

### Do not do next

- Do not move the latest strategy into `Stock_TaiwanII_FinRLX/`.
- Do not archive `FinRL/data`.
- Do not archive `FinRL/backtesting` as a whole.
- Do not archive `FinRL/v2/backtesting/performance_metrics.py` until comparable metrics imports are migrated.
- Do not move root files only because the inventory category says `review_report` or `improvement_research`; run `rg` reference checks first.
- Do not add Fubon order submission or automatic trading in this phase.

### Suggested verification before and after next edits

```bash
.venv/bin/python -m pytest -q tests/test_production_shadow_boundary.py tests/test_group_a_plus_latest_strategy.py
.venv/bin/python -m py_compile scripts/report/build_root_markdown_inventory.py
```

For NCF split work, also run the focused NCF tests touched by the moved helpers. Earlier safe subset was:

```bash
.venv/bin/python -m pytest -q tests/test_ncf_00631l_paths.py tests/test_ncf_panel_manifest.py tests/test_ncf_panel_validation.py
```

### High-level status for next agent

The best next engineering task is not more document moving. It is to checkpoint this cleanup, then reduce strategy-maintenance risk by continuing the `ncf_2330.py` split in small compatibility-preserving phases.

## 2026-07-29 Fubon manual-password security update

### Scope

Changed Fubon/Fuban SDK login handling so broker login cannot use a saved password automatically.

The read-only Fubon snapshot path still supports SDK login for holdings/cash reads, but the user must manually enter:

- Fubon login password
- Fubon certificate password

at runtime.

### Code changes

- `group_a_plus/portfolio/fubon_local_config.py`
  - still reads local `C:\fubon` AES config for non-password metadata.
  - returns `FUBON_ID`, `FUBON_CERT_PATH`, and local dir metadata only.
  - no longer returns `FUBON_PASSWORD` or `FUBON_CERT_PASSWORD`.
  - marks passwords as manual-required with:
    - `FUBON_PASSWORD_MANUAL_REQUIRED`
    - `FUBON_CERT_PASSWORD_MANUAL_REQUIRED`

- `group_a_plus/portfolio/fubon_snapshot.py`
  - `load_fubon_credentials_from_env()` now ignores any `FUBON_PASSWORD` / `FUBON_CERT_PASSWORD` values in env.
  - prompts with `getpass()` for both passwords.
  - keeps a test-only `password_provider` injection point so automated tests do not need real credentials.
  - read-only behavior is unchanged: login, accounting inventories, accounting bank remain, logout if SDK is owned.

- `scripts/misc/fubon_sdk_bridge.py`
  - `login-check` no longer accepts `--password` or `--cert-password`.
  - `login-check` no longer reads password env vars.
  - login password and certificate password are prompted manually.
  - `check --require-credentials` now checks only non-password readiness: personal ID and certificate path.

- `config/fubon_sdk.env.example`
  - removed password fields.

- `FUBON_SDK_SETUP.md`
  - updated to document non-password env setup and manual password prompts.

### Local credential cleanup

The local AES config under `C:\fubon` was updated outside the repo:

- cleared `password` field for `fubon_stock`
- cleared `password` field for `fubon_pfx`
- backup created before rewriting the config

Verification only printed boolean status, not secret values:

- `fubon_stock.password_is_empty`: `true`
- `fubon_pfx.password_is_empty`: `true`

### Validation

Commands:

```bash
.venv/bin/python -m py_compile group_a_plus/portfolio/fubon_snapshot.py group_a_plus/portfolio/fubon_local_config.py scripts/misc/fubon_sdk_bridge.py
.venv/bin/python -m pytest -q tests/test_fubon_snapshot.py tests/test_fubon_local_config.py tests/test_fubon_sdk_check.py tests/test_update_dashboard.py tests/test_production_shadow_boundary.py
```

Result:

- `21 passed`
- `py_compile` returned success.

### Next usage note

To refresh Fubon holdings now, run the normal snapshot/dashboard command from an interactive terminal. It will ask for both passwords manually. Non-interactive dashboard refresh will fail unless a controlled test-only password provider is explicitly wired in; this is intentional.

### Execution probe follow-up

After the first execution probe, `fubon_snapshot` still instantiated `FubonSDK()` before prompting for passwords. On WSL this could fail during SDK runtime/DNS initialization before the manual password gate.

Fixed ordering in `group_a_plus/portfolio/fubon_snapshot.py`:

1. load non-password metadata
2. prompt for login password and certificate password
3. reject blank passwords
4. instantiate `FubonSDK()`
5. call `sdk.login(...)`

Probe command with blank password input:

```bash
printf '\n\n' | .venv/bin/python -m group_a_plus.portfolio.fubon_snapshot --local-config-dir 'C:\fubon' --output /tmp/fubon_manual_password_probe.json --as-of 2026-07-29
```

Result:

- prompted for both passwords
- rejected blank login password with `Fubon login password is required`
- did not instantiate SDK before the password gate

Validation after the ordering fix:

```bash
.venv/bin/python -m pytest -q tests/test_fubon_snapshot.py tests/test_fubon_local_config.py tests/test_fubon_sdk_check.py tests/test_update_dashboard.py
.venv/bin/python -m py_compile group_a_plus/portfolio/fubon_snapshot.py
```

Result:

- `19 passed`
- `py_compile` returned success.

### Interactive terminal requirement

Codex/non-interactive command execution cannot provide a secure user password prompt to the operator. The snapshot command now detects this and fails before SDK initialization with:

```text
Fubon password prompt requires an interactive terminal
```

Run the snapshot from the user's own Windows/WSL terminal when an actual login is needed:

```bash
cd /mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main
.venv/bin/python -m group_a_plus.portfolio.fubon_snapshot --local-config-dir 'C:\fubon' --output data/private/holdings_fubon_latest.json --as-of 2026-07-29
```

Expected behavior:

- terminal prompts for Fubon login password
- terminal prompts for Fubon certificate password
- blank passwords are rejected
- SDK is initialized only after both password prompts pass

### Interactive dashboard refresh command

`group_a_plus.dashboard.update_dashboard --refresh-fubon` now supports a true interactive Fubon refresh when launched from the user's own terminal.

Change:

- interactive mode inherits terminal stdin/stdout/stderr for the Fubon snapshot subprocess.
- non-interactive mode still captures stderr and fails cleanly.
- dashboard CLI catches expected refresh/input errors and prints one clear line instead of a traceback.

Use this for the normal manual-login dashboard workflow:

```bash
cd /mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main
.venv/bin/python -m group_a_plus.dashboard.update_dashboard --refresh-fubon --local-config-dir 'C:\fubon' --json
```

Expected terminal flow:

1. Fubon snapshot asks for login password.
2. Fubon snapshot asks for certificate password.
3. Snapshot reads inventories/cash only.
4. Rebalance audit is regenerated.
5. `data/private/group_a_plus_dashboard.html` is regenerated.

Non-interactive probe result after this change:

```text
Dashboard update error: Fubon snapshot refresh failed with rc=2: Fubon snapshot input error: Fubon password prompt requires an interactive terminal
```

Validation:

```bash
.venv/bin/python -m pytest -q tests/test_update_dashboard.py tests/test_fubon_snapshot.py tests/test_fubon_local_config.py tests/test_fubon_sdk_check.py
.venv/bin/python -m py_compile group_a_plus/dashboard/update_dashboard.py group_a_plus/portfolio/fubon_snapshot.py
```

Result:

- `21 passed`
- `py_compile` returned success.

### Password failure handling update

Observed user-side failure:

```text
RuntimeError: Fubon login failed: Result {
  is_success: False,
  message: certificate password wrong,
  data: None
}
Dashboard update error: Fubon snapshot refresh failed with rc=-11
```

Diagnosis:

- Fubon SDK returned `certificate password wrong`.
- That means the second prompt, `Fubon certificate password (.p12/.pfx)`, was wrong.
- It is not the same as the first prompt, `Fubon account login password`.
- The Fubon SDK can segfault after a failed login in this runtime, so the CLI must avoid traceback unwinding.

Fixes:

- `group_a_plus/portfolio/fubon_snapshot.py`
  - catches `RuntimeError` in CLI `main()`.
  - prints one-line `Fubon snapshot error: ...`.
  - exits through `os._exit(exit_code)` to avoid SDK shutdown segfault after a failed login.
  - supports up to 3 manual password attempts when credentials are prompted.
  - prompt text is explicit:
    - `Fubon account login password:`
    - `Fubon certificate password (.p12/.pfx):`

- `tests/test_fubon_snapshot.py`
  - added retry coverage: first login fails, second manual password pair succeeds.

Validation:

```bash
.venv/bin/python -m pytest -q tests/test_fubon_snapshot.py tests/test_update_dashboard.py tests/test_fubon_local_config.py tests/test_fubon_sdk_check.py
.venv/bin/python -m py_compile group_a_plus/portfolio/fubon_snapshot.py group_a_plus/dashboard/update_dashboard.py
```

Result:

- `22 passed`
- `py_compile` returned success.

## 2026-07-29 NCF data validation gate

### Decision

The recommendation is reasonable and was implemented:

> Before each NCF training run, force a data validation step covering schema checks and price-history gap detection.

Important nuance:

- Schema and target price-history gaps are blocking.
- Freshness metadata is reported, but not blocking by default in this new gate.
- Reason: `ncf_data_freshness()` intentionally tracks broad external-market coverage. Some non-core external tickers can lag without invalidating the target ticker's training price series. Existing `ohlcv_freshness` remains the stricter dedicated freshness gate when `--fail-on-ohlcv-warning` is used.

### Code changes

- `ncf_data_quality.py`
  - expanded from freshness helper into a CLI-capable data validation module.
  - added `validate_ncf_training_data(...)`.
  - checks required DuckDB tables/columns:
    - `ohlcv`
    - `institutional_data`
    - `margin_data`
    - `market_margin_data`
    - `taifex_futures_daily`
    - `taifex_futures_institutional`
    - `shareholding_distribution`
    - `external_market_ohlcv`
  - checks target price-history gaps with `--max-ohlcv-gap-days`.
  - supports `2330.TW` correctly:
    - `00631L.TW` and `00632R.TW` use local `ohlcv`.
    - `2330.TW` uses `external_market_ohlcv` with `provider='yfinance'`.

- `scripts/run/run_ncf_daily_pipeline.py`
  - added critical step `ncf_data_validation`.
  - placement:
    - after `ohlcv_freshness`
    - before `ncf_00631l`, `ncf_00632r`, and `ncf_2330`
  - not in `BEST_EFFORT_STEP_NAMES`, so a failure blocks NCF training.
  - added emergency bypass:
    - `--skip-ncf-data-validation`
  - added threshold:
    - `--ncf-max-ohlcv-gap-days`, default `14`

### CLI

Manual validation:

```bash
.venv/bin/python ncf_data_quality.py \
  --db FinRL/data/stock_data.db \
  --tickers 00631L.TW,00632R.TW,2330.TW \
  --reference-date latest \
  --max-ohlcv-gap-days 14 \
  --output results/ncf_data_validation_manual.json
```

Pipeline-generated output path:

```text
results/ncf_data_validation_<date_stamp>.json
```

### Real DB probe

Command:

```bash
.venv/bin/python ncf_data_quality.py --db FinRL/data/stock_data.db --tickers 00631L.TW,00632R.TW,2330.TW --reference-date latest --max-ohlcv-gap-days 14 --output /tmp/ncf_data_validation_probe.json
```

Result:

- `status`: `ok`
- `missing_tables`: `[]`
- `missing_columns`: `{}`
- `blocking_reasons`: `[]`
- `00631L.TW`
  - `price_source`: `ohlcv`
  - latest price date: `2026-07-28`
  - gap count: `0`
- `00632R.TW`
  - `price_source`: `ohlcv`
  - latest price date: `2026-07-28`
  - gap count: `0`
- `2330.TW`
  - `price_source`: `external_market_ohlcv:yfinance`
  - latest price date: `2026-07-27`
  - gap count: `0`

Observed but non-blocking:

- `ncf_data_freshness()` reports broad `external_market_ohlcv` as `degraded_stale` for ETF models because one or more tracked external tickers lag more than 3 days.
- This is preserved in the report for review, but not used as a default training blocker in the new schema/gap gate.

### Tests

Commands:

```bash
.venv/bin/python -m pytest -q tests/test_ncf_data_quality.py tests/test_run_ncf_daily_pipeline.py
.venv/bin/python -m py_compile ncf_data_quality.py scripts/run/run_ncf_daily_pipeline.py
```

Result:

- `28 passed`
- `py_compile` returned success.

### Next recommendation

If later desired, add a second strict mode that blocks only on explicitly-required external features per model, not the full broad external ticker set. Do not make all external-market freshness blocking globally unless each ticker is mapped to a model-required feature.

### Handoff quick resume

Status:

- Done.
- `ncf_data_quality.py` is now a real pre-training validation CLI.
- `scripts/run/run_ncf_daily_pipeline.py` now runs `ncf_data_validation` before NCF model commands.
- The new validation step is critical, not best-effort.

What blocks training:

- missing required DuckDB tables
- missing required columns
- missing target price history
- target price history calendar gap above `--ncf-max-ohlcv-gap-days`

What does not block by default:

- broad external-market freshness degradation from `ncf_data_freshness()`

Reason for not blocking on broad freshness by default:

- The current freshness helper checks a wide external ticker set.
- Some lagging external tickers are not necessarily required by every NCF model.
- Blocking on all broad external tickers would create false negatives.

How to verify quickly:

```bash
.venv/bin/python ncf_data_quality.py --db FinRL/data/stock_data.db --tickers 00631L.TW,00632R.TW,2330.TW --reference-date latest --max-ohlcv-gap-days 14 --output /tmp/ncf_data_validation_probe.json
.venv/bin/python -m pytest -q tests/test_ncf_data_quality.py tests/test_run_ncf_daily_pipeline.py
.venv/bin/python -m py_compile ncf_data_quality.py scripts/run/run_ncf_daily_pipeline.py
```

Expected current result:

- validation probe status: `ok`
- tests: `28 passed`
- compile: success

Pipeline placement contract:

```text
ohlcv_freshness
ncf_data_validation
ncf_00631l
ncf_00632r
ncf_signal_archive
ncf_2330
```

Emergency bypass:

```bash
--skip-ncf-data-validation
```

Use the bypass only when manually investigating a known false-positive validation failure; do not use it in normal daily runs.

## 2026-07-29 strategy logic test coverage

### Decision

The recommendation is reasonable:

> Add strategy-logic unit tests for signal generation, regime judgment, and weight calculation instead of relying mostly on smoke tests.

Existing context:

- The repo already has meaningful strategy tests, not just smoke tests.
- Useful existing coverage includes:
  - `tests/test_group_a_plus_ncf_integration.py`
  - `tests/test_group_a_plus_market_state.py`
  - `tests/test_group_a_plus_overlay_backtest.py`
  - `tests/test_group_a_plus_latest_strategy.py`
- Gap still existed around active A21.18 helper-level contracts: weight movement, normalization, late-bull regime override, and leverage-cap regime override.

### Implemented

Added:

- `tests/test_a2118_strategy_logic.py`

Coverage added:

- `_late_bull_hedge_weights(...)`
  - halves `00631L.TW` exposure into `0050.TW`
  - clamps intensity below 0 and above 1
  - preserves normalized full universe weights

- `_golden_rebound_recapture_weights(...)`
  - moves a controlled fraction from `0050.TW` into `00631L.TW`
  - preserves total weight

- `_recovery_boost_weights(...)`
  - moves recovery exposure from `0050.TW` into `00631L.TW`
  - preserves total weight

- `_golden_leverage_cap_weights(...)`
  - caps `00631L.TW`
  - moves excess to `0050.TW`
  - preserves total weight

- `_apply_late_bull_overlay(...)`
  - only changes `golden1` days
  - requires late-bull MA gap, low H20 up probability, and sufficient confidence
  - does not modify defensive days
  - reports missing required panel columns instead of silently changing regime

- `_apply_golden_leverage_cap_overlay(...)`
  - requires tail score, realized-vol ratio, and drawdown trigger
  - only modifies `golden1`
  - does not modify recovery regime

### Validation

Commands:

```bash
.venv/bin/python -m pytest -q tests/test_a2118_strategy_logic.py tests/test_group_a_plus_market_state.py tests/test_group_a_plus_latest_strategy.py
.venv/bin/python -m py_compile tests/test_a2118_strategy_logic.py group_a_plus/runners/a2118.py
```

Result:

- `40 passed`
- `py_compile` returned success.

### Handoff note

Do not replace these focused unit tests with full backtest smoke tests. Keep them small and deterministic. For future strategy changes, prefer adding one or two direct helper-level contract tests before broadening integration coverage.

## 2026-07-29 type hints rollout

### Decision

The recommendation is reasonable, but should be applied gradually:

> Add type hints to core modules first, especially `group_a_plus/core/`, and avoid a broad all-repo typing pass.

Rationale:

- Active production/shadow-sensitive code benefits most from typed interfaces.
- A global type-hint rewrite would create large diffs across legacy/research files and increase review risk.
- `FinRL/v2/` should not be typed wholesale until the retained production surface is narrowed; otherwise type hints may preserve code that should instead be archived.

### Implemented

Updated:

- `group_a_plus/core/point_in_time_store.py`

Type boundaries added:

- `PathInput`: accepts `str`, `PathLike[str]`, and `Path`.
- `SignalDate`: accepts `str` and `pd.Timestamp`.
- `_snapshot_dir(...)`
- `write_snapshot(...)`
- `read_snapshot(...)`
- `list_snapshots_for_date(...)`
- `latest_snapshot_for_date(...)`

No signal logic, snapshot filename logic, JSON schema, or output path behavior was changed.

### Validation

Commands:

```bash
.venv/bin/python -m pytest -q tests/test_signal_contract.py tests/test_point_in_time_store.py
.venv/bin/python -m py_compile group_a_plus/core/signal_contract.py group_a_plus/core/point_in_time_store.py
```

Result:

- `18 passed`
- `py_compile` returned success.

### Handoff note

Continue type hints in this order:

1. `group_a_plus/core/`
2. `group_a_plus/portfolio/` data contracts and pure calculation modules
3. `group_a_plus/dashboard/` public function boundaries
4. Narrow retained parts of `FinRL/v2/` only after the archive/consolidation decision is complete

Do not enable strict mypy/pyright globally yet. A safer next step is adding focused annotations and tests around modules that already have deterministic unit tests.

## 2026-07-29 outputs/report schema migration

### Decision

The recommendation is reasonable:

> Report artifacts should converge toward one canonical `outputs/` tree with a common JSON schema.

But this should not be implemented as a bulk move. Current paths are heavily referenced by active scripts, tests, dashboard code, and latest-strategy governance:

- `report/group_a_plus/latest/strategy.json`
- `report/group_a_plus/latest/*.json`
- `results/ncf_*`
- `FinRL/report/`
- `FinRL/results/`

Moving these paths all at once would be high risk and would likely break the daily pipeline, dashboard, and historical comparisons.

### Implemented

Added:

- `group_a_plus/outputs.py`
- `tests/test_group_a_plus_outputs.py`
- `docs/OUTPUTS_SCHEMA_MIGRATION.md`

The new helper defines:

- canonical root: `outputs/group_a_plus/`
- `output_path(...)`
- `report_envelope(...)`
- artifact kinds:
  - `backtest`
  - `signal`
  - `validation`
  - `dashboard`
  - `portfolio`
  - `research`
  - `pipeline`
- run modes:
  - `production`
  - `shadow`
  - `research`

Common JSON envelope:

```json
{
  "schema_version": 1,
  "artifact_name": "daily_status",
  "artifact_kind": "pipeline",
  "run_mode": "production",
  "generated_at": "2026-07-29T10:00:00+00:00",
  "payload": {}
}
```

No existing report/result files were moved. No existing writer was redirected yet. This is intentional: the first step is additive and compatibility-safe.

### Validation

Commands:

```bash
.venv/bin/python -m pytest -q tests/test_group_a_plus_outputs.py tests/test_group_a_plus_latest_strategy.py tests/test_run_ncf_daily_pipeline.py
.venv/bin/python -m py_compile group_a_plus/outputs.py tests/test_group_a_plus_outputs.py
```

Result:

- `52 passed`
- `py_compile` returned success.

### Handoff note

Next migration should be one writer at a time:

1. Keep legacy output path.
2. Add canonical `outputs/group_a_plus/...` write using `output_path(...)`.
3. Wrap the new JSON copy with `report_envelope(...)`.
4. Move readers/tests to `outputs/`.
5. Remove legacy compatibility copy only after no active reader remains.

Do not move `report/group_a_plus/latest/strategy.json` first. It is still the active latest-strategy pointer.

## 2026-07-29 outputs dual-write first writers

### Implemented

Extended:

- `group_a_plus/outputs.py`
- `tests/test_group_a_plus_outputs.py`
- `scripts/run/run_ncf_daily_pipeline.py`
- `docs/OUTPUTS_SCHEMA_MIGRATION.md`

Added helper:

- `write_json_report(...)`

First dual-write artifacts:

- legacy: `report/group_a_plus/latest/strategy_env_health.json`
- canonical: `outputs/group_a_plus/latest/strategy_env_health.json`
- legacy: `report/group_a_plus/latest/ops_health.json`
- canonical: `outputs/group_a_plus/latest/ops_health.json`

The legacy files remain unwrapped and unchanged for dashboard/pipeline compatibility. The canonical files use the new common envelope:

- `schema_version`
- `artifact_name`
- `artifact_kind`
- `run_mode`
- `generated_at`
- `payload`

### Validation

Commands:

```bash
.venv/bin/python -m pytest -q tests/test_group_a_plus_outputs.py tests/test_run_ncf_daily_pipeline.py
.venv/bin/python -m py_compile group_a_plus/outputs.py scripts/run/run_ncf_daily_pipeline.py tests/test_group_a_plus_outputs.py
```

Result:

- `28 passed`
- `py_compile` returned success.

### Handoff note

Next low-risk candidates for dual-write:

1. `signal_alignment`
2. `watchlist_news`
3. `daily_status` pointer copy

Do not migrate NCF panel CSVs or active `strategy.json` before the reader side is updated and covered by tests.

## 2026-07-29 outputs dual-write second writers

### Implemented

Extended:

- `group_a_plus/integrations/signal_alignment.py`
- `group_a_plus/integrations/watchlist_news.py`
- `scripts/misc/check_group_a_plus_daily_status.py`
- `tests/test_group_a_plus_signal_alignment.py`
- `tests/test_group_a_plus_watchlist_news.py`
- `tests/test_check_group_a_plus_daily_status.py`
- `docs/OUTPUTS_SCHEMA_MIGRATION.md`

New canonical dual-write artifacts:

- legacy: `report/group_a_plus/latest/signal_alignment.json`
- canonical: `outputs/group_a_plus/latest/signal_alignment.json`
- legacy: `report/group_a_plus/latest/watchlist_news.json`
- canonical: `outputs/group_a_plus/latest/watchlist_news.json`
- legacy: `results/group_a_plus_daily_status*.json` plus managed latest pointer
- canonical: `outputs/group_a_plus/latest/daily_status.json`

Daily status gained:

- `--canonical-output`
- default: `outputs/group_a_plus/latest/daily_status.json`
- pass an empty value to skip the canonical copy

All legacy output behavior is preserved.

### Validation

Commands:

```bash
.venv/bin/python -m pytest -q tests/test_check_group_a_plus_daily_status.py tests/test_group_a_plus_signal_alignment.py tests/test_group_a_plus_watchlist_news.py tests/test_group_a_plus_outputs.py tests/test_run_ncf_daily_pipeline.py
.venv/bin/python -m py_compile scripts/misc/check_group_a_plus_daily_status.py group_a_plus/integrations/signal_alignment.py group_a_plus/integrations/watchlist_news.py group_a_plus/outputs.py tests/test_check_group_a_plus_daily_status.py
```

Result:

- `86 passed`
- `py_compile` returned success.

### Handoff note

The next migration should shift selected readers to prefer canonical `outputs/` files with legacy fallback. Good candidates:

1. dashboard health panels for `daily_status`, `ops_health`, and `strategy_env_health`
2. alert-state readers for `ops_health`
3. final governance snapshot readers

Keep `report/group_a_plus/latest/strategy.json` unchanged until all latest-strategy consumers have a tested canonical fallback.

## 2026-07-29 model registry first pass

### Decision

The recommendation is reasonable:

> Every model checkpoint should have metadata: training date/range, data range, evaluation metrics, and lineage. These should be tracked in a model registry.

This should be done incrementally. `models/portfolio/` currently contains roughly 200 checkpoint files, and many old files do not have complete reconstructable training lineage. Do not invent lineage. Mark old entries as `partial` when details are unknown.

### Implemented

Added:

- `.gitignore` exception for `models/MODEL_REGISTRY.json` while keeping checkpoint files ignored
- `group_a_plus/model_registry.py`
- `models/MODEL_REGISTRY.json`
- `tests/test_model_registry.py`
- `docs/MODEL_REGISTRY.md`

Registry helper API:

- `file_sha256(...)`
- `relative_to_project(...)`
- `build_checkpoint_metadata(...)`
- `load_model_registry(...)`
- `validate_model_card(...)`
- `validate_model_registry(...)`

Seeded model cards:

- `group_a_oos_2020_2024_cap20_llm_pva_tripletv4_inst_localregime_20260526`
  - status: `frozen_release`
  - role: Golden1_0531 source-of-truth release checkpoint
  - metadata_status: `complete`

- `group_a_production_2020_2025_100k`
  - status: `legacy_runtime_reference`
  - role: referenced by many historical `results/signal_group_a*.json` files
  - metadata_status: `partial`

- `group_a_plus_4tickers_2020_2025`
  - status: `shadow_diagnostic_reference`
  - role: default target for read-only model weight health diagnostics
  - metadata_status: `partial`

All three entries include verified:

- `model_path`
- `sha256`
- `size_bytes`
- `modified_at`

### Validation

Commands:

```bash
.venv/bin/python -m pytest -q tests/test_model_registry.py
.venv/bin/python -m py_compile group_a_plus/model_registry.py tests/test_model_registry.py
```

Result:

- `4 passed`
- `py_compile` returned success.

### Handoff note

Next step should be integrating registry updates into future training scripts. Do not scan and auto-register every old model as `complete`; old model lineage must be reconstructed from result JSON, release docs, and handoff notes before being marked complete.

Recommended next candidates:

1. Add registry lookup to release/promotion checks.
2. Add a training-script helper that appends/updates a model card immediately after saving a checkpoint.
3. Add a CI-style test that all models cited by active release manifests exist in `models/MODEL_REGISTRY.json`.

## 2026-07-29 ops_health feature table synchronization

### Decision

The recommendation is reasonable and important:

> ops_health should not only check whether individual artifacts are fresh versus wall-clock time. It should also check whether feature/chip tables are synchronized with OHLCV.

Real failure class:

- OHLCV reached a newer trading date.
- A feature table such as `institutional_data` lagged one trading day behind.
- The strategy could build mixed-date features and silently fall into a defensive regime.

This is not caught by ordinary OHLCV freshness checks.

### Implemented

Updated:

- `group_a_plus/operations/ops_health.py`
- `tests/test_group_a_plus_ops_health.py`

Added:

- `collect_feature_table_sync(...)`
- `feature_table_sync` section in `build_ops_health(...)`

Reference date:

- latest common `ohlcv.dt` across:
  - `0050.TW`
  - `00631L.TW`
  - `00632R.TW`
- only rows with `volume > 0`

Monitored feature/chip tables:

- `institutional_data`, `ticker = '0050.TW'`
- `institutional_data`, `ticker = '00631L.TW'`
- `institutional_data`, `ticker = '00632R.TW'`
- `margin_data`, `ticker = '00631L.TW'`
- `margin_data`, `ticker = '00632R.TW'`
- `market_margin_data`
- `derivative_institutional_data`, `product_id IN ('TX', 'TXO') AND institutional_investors = '外資'`

Policy:

- `max_lag_days = 0`
- any monitored table lagging the OHLCV common date is `error`
- this remains detection-only; it does not place orders or mutate strategy output

### Validation

Commands:

```bash
.venv/bin/python -m pytest -q tests/test_group_a_plus_ops_health.py
.venv/bin/python -m py_compile group_a_plus/operations/ops_health.py tests/test_group_a_plus_ops_health.py
```

Result:

- `29 passed`
- `py_compile` returned success.

Real DB probe:

```text
status= ok
reference latest_common_date=2026-07-28
institutional_0050 ok 2026-07-28 lag=0
institutional_00631l ok 2026-07-28 lag=0
institutional_00632r ok 2026-07-28 lag=0
margin_00631l ok 2026-07-28 lag=0
margin_00632r ok 2026-07-28 lag=0
market_margin ok 2026-07-28 lag=0
derivative_tx_txo_foreign ok 2026-07-28 lag=0
```

### Handoff note

If a future incident involves mixed-date features, inspect `ops_health.json` under:

```json
feature_table_sync
```

Possible future expansion:

- add `securities_lending_data`
- add `day_trading_data`
- add `short_sale_balance_data`
- add per-table trading-calendar grace rules if a source is documented to publish later than OHLCV

## 2026-07-29 panel drift regression-bound follow-up

### Decision

The concern is reasonable and should be tracked:

> The 2026-07-07 NCF panel drift fix documented a residual drift bound around `<=0.13`, but the 2026-07-27 pin-switch audit measured much larger drift (`h20_prob_up` around `0.196`, `confidence` around `0.270`). This cannot be closed as noise without root-cause isolation.

Existing governance already had configured gate limits, but those limits had later been calibrated separately:

- `h20_prob_up`: configured gate limit `0.15`
- `confidence`: configured gate limit `0.28`

That means `confidence=0.270` could pass the configured gate while still violating the earlier 2026-07-07 verification bound. The missing piece was a separate "historical bound regression" flag.

### Implemented

Updated:

- `scripts/evaluate/build_ncf_panel_drift_diagnosis.py`
- `tests/test_build_ncf_panel_drift_diagnosis.py`

Added:

- `HISTORICAL_VERIFICATION_BOUNDS`
  - `h20_prob_up: 0.13`
  - `confidence: 0.13`
- per-column fields:
  - `historical_verification_bound`
  - `exceeds_historical_verification_bound`
- top-level field:
  - `historical_verification_bound_exceeded`
- top-level follow-up section:
  - `root_cause_follow_up`

If any historical verification bound is exceeded, the report now says:

```json
"root_cause_follow_up": {
  "status": "unresolved_requires_diagnosis",
  "reason": "drift exceeds the 2026-07-07 historical verification bound; do not close as noise without root-cause isolation"
}
```

Required checks listed in the report:

- `same_method_baseline_vs_candidate`
- `model_set_isolation`
- `feature_schema_or_external_feature_delta`
- `training_window_or_label_availability_delta`
- `pin_and_baseline_path_verification`

### 2026-07-27 Pin Drift Re-Diagnosis

Generated:

- `results/ncf_panel_drift_regression_bound_diagnosis_20260729.json`

Command:

```bash
.venv/bin/python scripts/evaluate/build_ncf_panel_drift_diagnosis.py \
  --drift-audit results/ncf_panel_drift_0716_vs_0725_20260727.json \
  --output results/ncf_panel_drift_regression_bound_diagnosis_20260729.json
```

Key output:

```text
status=blocked
exceeded_columns=['h20_prob_up']
historical_bound_exceeded=['h20_prob_up', 'confidence']
h20_prob_up max_abs_delta=0.1963733280860215 configured_limit=0.15 historical_bound=0.13
confidence max_abs_delta=0.26995329827979453 configured_limit=0.28 historical_bound=0.13
root_cause_follow_up.status=unresolved_requires_diagnosis
```

Interpretation:

- `h20_prob_up` fails both current gate and historical bound.
- `confidence` passes the current configured gate but violates the 2026-07-07 historical bound.
- Therefore this is now explicitly unresolved and must not be closed as "noise" without source isolation.

### Validation

Commands:

```bash
.venv/bin/python -m pytest -q tests/test_build_ncf_panel_drift_diagnosis.py tests/test_build_ncf_panel_drift_model_set_isolation_report.py tests/test_evaluate_ncf_panel_drift.py
.venv/bin/python -m py_compile scripts/evaluate/build_ncf_panel_drift_diagnosis.py tests/test_build_ncf_panel_drift_diagnosis.py
```

Result:

- `7 passed`
- `py_compile` returned success.

### Handoff note

Next investigation should not change thresholds first. It should isolate why the historical bound was exceeded:

1. Compare same-method baseline versus candidate.
2. Verify exact baseline/candidate pin paths.
3. Compare feature schema and external feature availability.
4. Compare training window and label availability.
5. Decide whether the 2026-07-07 bound should be revised only after root cause is known.

### 2026-07-29 Root-Cause Narrowing

Follow-up question:

> Was the cause found?

Answer: partially found and narrowed, but not fully closed.

Generated:

- `results/ncf_panel_drift_root_cause_review_20260729.json`
- `results/ncf_panel_drift_0716_vs_0725_no_external_20260729.json`
- `results/ncf_panel_drift_0725_no_external_vs_external_20260729.json`

Commands:

```bash
.venv/bin/python scripts/evaluate/evaluate_ncf_panel_drift.py \
  --baseline-panel results/ncf_00631l_panel_latest_20260716.csv \
  --candidate-panel results/ncf_00631l_panel_latest_20260725_no_external.csv \
  --columns h20_prob_up confidence prob_fwd_mdd_gt5_h20 prob_fwd_gain_gt5_h20 \
  --outcome-aware \
  --top-n 10 \
  --output results/ncf_panel_drift_0716_vs_0725_no_external_20260729.json

.venv/bin/python scripts/evaluate/evaluate_ncf_panel_drift.py \
  --baseline-panel results/ncf_00631l_panel_latest_20260725_no_external.csv \
  --candidate-panel results/ncf_00631l_panel_latest_20260725.csv \
  --columns h20_prob_up confidence prob_fwd_mdd_gt5_h20 prob_fwd_gain_gt5_h20 \
  --outcome-aware \
  --top-n 10 \
  --output results/ncf_panel_drift_0725_no_external_vs_external_20260729.json

.venv/bin/python scripts/evaluate/build_ncf_panel_drift_diagnosis.py \
  --drift-audit results/ncf_panel_drift_0716_vs_0725_20260727.json \
  --baseline-signal results/ncf_00631l_latest_20260716.json \
  --candidate-signal results/ncf_00631l_latest_20260725.json \
  --baseline-no-external-panel results/ncf_00631l_panel_latest_20260716_no_external.csv \
  --candidate-no-external-panel results/ncf_00631l_panel_latest_20260725_no_external.csv \
  --sensitivity-audit results/ncf_panel_drift_0725_no_external_vs_external_20260729.json \
  --output results/ncf_panel_drift_root_cause_review_20260729.json
```

Key findings:

- There is no saved `results/ncf_00631l_panel_latest_20260716_no_external.csv`, so a perfectly controlled 2026-07-16 no-external comparison is not available from current artifacts.
- 2026-07-16 signal context:
  - `external_features=true`
  - `data_freshness.status=degraded_stale`
  - `external_market_ohlcv` only up to `2026-07-07`
  - classification model set includes `tabnet`
- 2026-07-25 signal context:
  - `external_features=true`
  - `data_freshness.status=ok`
  - `external_market_ohlcv` up to `2026-07-21`
  - classification model set no longer includes `tabnet`
- Existing model-set isolation report already showed `model_set_mismatch_isolated`:
  - `original_vs_today` failed `h20_prob_up`
  - `original_vs_no_tabnet` failed more strongly
  - `no_tabnet_vs_today` passed configured limits
  - conclusion: TabNet/model-set mismatch explains the primary configured-gate blocker for the active-vs-today path.
- New 2026-07-25 no-external versus external sensitivity audit shows external features can dominate the prediction panel:
  - `h20_prob_up max_abs_delta=0.5113554732054251`
  - `confidence max_abs_delta=0.6372621107070484`
  - `prob_fwd_mdd_gt5_h20 max_abs_delta=0.4929439578628999`
  - `prob_fwd_gain_gt5_h20 max_abs_delta=0.4391331183401779`
- These external-feature deltas are larger than the original 2026-07-16 to 2026-07-25 pin drift:
  - original `h20_prob_up max_abs_delta=0.1963733280860215`
  - original `confidence max_abs_delta=0.26995329827979453`
- `results/ncf_panel_drift_root_cause_review_20260729.json` now records the artifact contract:
  - `status=missing_provided_artifacts`
  - `missing_provided_artifacts=["baseline_no_external_panel"]`
  - `candidate_pair_available=true`
  - `baseline_pair_available=false`
  - `sensitivity_audit_available=true`
  - `full_attribution_required=true`
  - `full_attribution_possible=false`
  - reason: `baseline no-external pair is missing; exact attribution remains partial`

Interpretation:

- The oversized drift should no longer be treated as unexplained random noise.
- Two concrete contributors are now identified:
  1. model-set mismatch, especially TabNet removal from the candidate model set;
  2. external feature state/sensitivity, with 2026-07-16 using stale external data and 2026-07-25 using fresher external data.
- The exact percentage attribution cannot be proven from existing artifacts because the 2026-07-16 no-external panel was not saved.

Current governance state:

- keep `status=blocked` for the 2026-07-16 to 2026-07-25 historical-bound regression review;
- do not relax `HISTORICAL_VERIFICATION_BOUNDS`;
- do not promote, retrain, or change target weights based on this diagnosis alone;
- future reproductions should always save paired external/no-external panels and model-set manifests for both baseline and candidate pins.

### 2026-07-29 Pipeline Artifact Fix

Problem found during root-cause review:

- `ncf_panel_external_feature_sensitivity_governance` consumed `results/ncf_panel_drift_no_external_vs_external_{stamp}.json`.
- The daily command graph did not formally generate the paired same-day `00631L no_external` panel or that no-external versus external drift audit.
- This is why older investigations could end up missing the exact counterfactual panel needed for later root-cause isolation.

Implemented:

- `scripts/run/run_ncf_daily_pipeline.py`
  - Added best-effort `ncf_00631l_no_external_shadow`.
  - Added best-effort `ncf_panel_drift_no_external_vs_external`.
  - Moved the no-external versus external drift audit before `ncf_panel_drift_diagnosis`, so the diagnosis can ingest the same-run sensitivity audit.
  - Added inferred `--baseline-no-external-panel`, `--candidate-no-external-panel`, and `--sensitivity-audit` to `ncf_panel_drift_diagnosis` when the main run uses external features.
  - If the inferred active baseline no-external panel does not exist, the diagnosis report records it as a missing provided artifact instead of silently losing the attribution trail.
  - These run only when the main NCF run uses external features.
  - When `--no-external-features` is used for the main run, the paired sensitivity comparison is skipped because there is no external candidate to compare.
- `scripts/evaluate/build_ncf_panel_drift_diagnosis.py`
  - Added `artifact_contract` under `source_diagnosis`.
  - It records provided/missing artifacts and whether paired external/no-external attribution is possible.
- `tests/test_run_ncf_daily_pipeline.py`
  - Added assertions that the default command graph now saves:
    - `results/ncf_00631l_latest_{stamp}_no_external.json`
    - `results/ncf_00631l_panel_latest_{stamp}_no_external.csv`
    - `results/ncf_panel_drift_no_external_vs_external_{stamp}.json`
  - Added assertions that these diagnostic steps are best-effort.
  - Added assertions that no meaningless external-sensitivity pair is scheduled when the whole run is already `--no-external-features`.
- `tests/test_build_ncf_panel_drift_diagnosis.py`
  - Added coverage for complete and missing paired artifact contracts.

Governance interpretation:

- This does not change the active strategy, live target weights, or promotion permission.
- It fixes artifact retention so future panel-drift root-cause reviews have the paired external/no-external panels that were missing for 2026-07-16.
- If the shadow run fails, live signal generation can continue, but governance still records the missing sensitivity audit as blocked.

Validation:

```bash
.venv/bin/python -m pytest -q tests/test_build_ncf_panel_drift_diagnosis.py tests/test_run_ncf_daily_pipeline.py
.venv/bin/python -m pytest -q tests/test_run_ncf_daily_pipeline.py
.venv/bin/python -m py_compile scripts/evaluate/build_ncf_panel_drift_diagnosis.py scripts/run/run_ncf_daily_pipeline.py tests/test_build_ncf_panel_drift_diagnosis.py tests/test_run_ncf_daily_pipeline.py
```

Result:

- `25 passed`
- `24 passed`
- `20 passed`
- `py_compile` returned success.

## 2026-07-29 decision_confidence probability-calibration closure

### Decision

The concern is reasonable and should be closed explicitly:

> Phase 2 tried CAP10 empirical calibration and then `total_risk_score` regime-conditioned calibration. Both failed out-of-sample validation; the later attempt worsened error from `0.129` to `0.158`. `--use-calibration-model` is already default-off, so leaving it as a half-open path is misleading.

Decision:

- Keep `decision_confidence` only as `predicted_regret_percentile_rank_proxy`.
- Do not call it a calibrated probability.
- Mark empirical realized-regret probability calibration as `closed_failed_oos`.
- Keep calibration code only as an opt-in research reproduction path.
- Do not allow it to affect promotion, training, target weights, live gates, or auto-rebalance.

### Implemented

Updated:

- `group_a_plus/integrations/ncf_decision_calibration.py`
  - Added `CALIBRATION_MODEL_GOVERNANCE`.
  - Added `calibration_governance_summary()`.
  - `DecisionCalibrationSnapshot.to_json_dict()` now includes `governance`.
  - Empirical calibration basis text now states `closed_failed_oos research reproduction only`.
- `scripts/evaluate/evaluate_ncf_decision_calibration.py`
  - CLI help now says `--use-calibration-model` is closed failed OOS and kept only for research reproduction.
  - Output JSON now includes top-level `calibration_governance`.
- `scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py`
  - Added `--ncf-decision-calibration`.
  - Consolidated research snapshot summary now exposes:
    - `ncf_decision_calibration_governance_status`
    - `ncf_decision_confidence_contract`
    - `ncf_decision_calibration_model_default_enabled`
    - `ncf_decision_calibration_live_gate_allowed`
    - `ncf_decision_calibration_target_weight_change_allowed`
- `scripts/run/run_ncf_daily_pipeline.py`
  - Added best-effort `ncf_decision_calibration_shadow`.
  - The step writes `results/ncf_decision_calibration_shadow_{stamp}.json`.
  - `research_shadow_decision_snapshot` is moved after the DFL advisory/calibration step so it reads the same-day governance artifact.
- `tests/test_ncf_decision_calibration.py`
  - Added checks that the governance status is `closed_failed_oos`.
  - Added checks that promotion/live/target-weight permissions remain false.
  - Added checks that the OOS failure reason records `0.129 to 0.158`.
- `tests/test_build_group_a_plus_research_shadow_decision_snapshot.py`
  - Added checks that the consolidated research snapshot carries the closed calibration governance.
- `tests/test_run_ncf_daily_pipeline.py`
  - Added checks that daily command graph schedules `ncf_decision_calibration_shadow` as best-effort and passes it into `research_shadow_decision_snapshot`.

Governance payload:

```json
{
  "status": "closed_failed_oos",
  "decision_confidence_contract": "predicted_regret_percentile_rank_proxy_not_calibrated_probability",
  "calibration_model_default_enabled": false,
  "promotion_allowed": false,
  "training_allowed": false,
  "target_weight_change_allowed": false,
  "auto_rebalance_allowed": false,
  "live_gate_allowed": false
}
```

### Interpretation

- This does not remove the historical calibration functions because existing tests and research reproduction still use them.
- It does close the production/research-governance ambiguity.
- Future work should not continue tuning bins or `total_risk_score` buckets. If uncertainty quantification is revisited, use a different method class such as conformal abstention, ensemble disagreement, action-value margin stability, or rolling live-observation reliability.

### Validation

Commands:

```bash
.venv/bin/python -m pytest -q tests/test_ncf_decision_calibration.py tests/test_build_group_a_plus_research_shadow_decision_snapshot.py tests/test_run_ncf_daily_pipeline.py
.venv/bin/python -m pytest -q tests/test_ncf_decision_calibration.py
.venv/bin/python -m py_compile group_a_plus/integrations/ncf_decision_calibration.py scripts/evaluate/evaluate_ncf_decision_calibration.py scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py scripts/run/run_ncf_daily_pipeline.py tests/test_ncf_decision_calibration.py tests/test_build_group_a_plus_research_shadow_decision_snapshot.py tests/test_run_ncf_daily_pipeline.py
```

Result:

- `50 passed`
- `27 passed`
- `py_compile` returned success.
