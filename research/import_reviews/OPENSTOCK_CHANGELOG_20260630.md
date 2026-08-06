# OpenStock 導入變更記錄 - 2026-06-30

## 目標

依據 `C:\Users\isaac\Downloads\OpenStock-main\OpenStock-main` 的分析結果，先導入最適合最新 GroupA+ / A2118 策略的工程優點：

- 策略 alert state / cooldown。

本次不導入 OpenStock 原始碼，因為 OpenStock 是 AGPL-3.0。

## 新增檔案

### `group_a_plus/operations/alert_state.py`

新增策略 alert 狀態管理模組。

功能：

- 讀取 daily signal 的 `signal_alerts`。
- 合併上一輪 alert state。
- 輸出：
  - `emitted_alerts`
  - `suppressed_alerts`
  - `resolved_alerts`
  - 每個 alert 的持久狀態。

狀態欄位：

- `state_key`
- `condition_key`
- `active`
- `resolved`
- `first_seen_at`
- `last_seen_at`
- `last_emitted_at`
- `seen_count`
- `suppressed_count`
- `cooldown_minutes`

設計說明：

- `state_key` 使用現有 `cooldown_key`，用來判斷同一 alert 是否仍在 cooldown。
- `condition_key` 使用 `strategy_id:type`，用來追蹤同類 alert 是否 active 或 resolved。
- 不改變現有 daily signal schema。
- 不改變交易決策、權重、NCF 訊號。

### `scripts/run/update_group_a_plus_alert_state.py`

新增 CLI。

使用方式：

```bash
.venv/bin/python scripts/run/update_group_a_plus_alert_state.py
```

預設輸入：

- `report/group_a_plus/latest/live_signal.json`

預設輸出：

- `report/group_a_plus/latest/alert_state.json`

### `tests/test_group_a_plus_alert_state.py`

新增測試。

覆蓋：

- 第一次看到 alert 會 emitted。
- cooldown 內重複 alert 會 suppressed。
- cooldown 後重複 alert 會再次 emitted。
- 當 live signal 不再出現該 alert，舊 active alert 會變 resolved。

## 修改檔案

### `scripts/run/run_ncf_daily_pipeline.py`

在 daily pipeline 結尾新增非致命 alert-state 更新：

- 成功時印出 emitted / suppressed / resolved 數量。
- 寫入 `report/group_a_plus/latest/alert_state.json`。
- 失敗時只印 warning，不讓 NCF pipeline 整體失敗。

### `OPENSTOCK_IMPORT_REVIEW_20260630.md`

改成繁中分析記錄。

內容包含：

- OpenStock 授權限制。
- 可導入優點。
- 不建議導入項目。
- 優先順序。
- 本次已開始實作項目。

## 實際輸出

已用目前 live signal 產生：

- `report/group_a_plus/latest/alert_state.json`

目前摘要：

```text
current_alert_count = 2
emitted_count = 2
suppressed_count = 0
resolved_count = 0
active_state_count = 2
```

目前 active alerts：

- `regime_transition`
- `total_risk_score`

## 驗證

已執行：

```bash
.venv/bin/python -m pytest tests/test_group_a_plus_alert_state.py -q
```

結果：

```text
4 passed
```

已執行：

```bash
.venv/bin/python -m pytest tests/test_run_ncf_daily_pipeline.py -q
```

結果：

```text
2 passed
```

已執行：

```bash
.venv/bin/python scripts/run/update_group_a_plus_alert_state.py
```

結果：

- 成功輸出 alert state JSON。
- 寫入 `report/group_a_plus/latest/alert_state.json`。

## 後續建議

### 2026-06-30 續作：導入優先 2

已新增策略 watchlist 新聞摘要。

新增檔案：

- `config/group_a_plus_watchlist.json`
- `group_a_plus/integrations/watchlist_news.py`
- `scripts/run/build_group_a_plus_watchlist_news.py`
- `tests/test_group_a_plus_watchlist_news.py`

修改檔案：

- `group_a_plus/integrations/llm_commentary.py`
- `scripts/run/run_ncf_daily_pipeline.py`

功能：

- 使用本地 LTN JSONL 新聞，不呼叫外部 API。
- 依策略 watchlist 平衡挑選新聞。
- 預設 watchlist：
  - `0050.TW`
  - `00631L.TW`
  - `00632R.TW`
  - `00679B.TWO`
- 每個 symbol 預設最多 2 則。
- 若 symbol 新聞不足，使用 market fallback keywords 補足。
- commentary output 會附上 `watchlist_news`。
- daily pipeline 會另外寫出 `report/group_a_plus/latest/watchlist_news.json`。

手動執行：

```bash
.venv/bin/python scripts/run/build_group_a_plus_watchlist_news.py --date 2026-06-29
```

實際輸出：

- `report/group_a_plus/latest/watchlist_news.json`
- `article_count = 8`
- `fallback_used = false`
- 每個策略標的各 2 則。

已重跑 commentary：

```bash
.venv/bin/python scripts/run/run_llm_commentary.py --ncf results/ncf_00631l_20260630.json --date 2026-06-29 --provider template
```

輸出：

- `report/group_a_plus/latest/commentary_20260629.json`
- 已包含 `watchlist_news` 欄位。

驗證：

```bash
.venv/bin/python -m pytest tests/test_group_a_plus_watchlist_news.py tests/test_group_a_plus_alert_state.py tests/test_run_ncf_daily_pipeline.py -q
```

結果：

```text
8 passed
```

下一步可做 OpenStock 導入優先 3：

- 多來源 Signal Alignment。

### 2026-06-30 續作：導入優先 3

已新增多來源 Signal Alignment。

新增檔案：

- `group_a_plus/integrations/signal_alignment.py`
- `scripts/run/build_group_a_plus_signal_alignment.py`
- `tests/test_group_a_plus_signal_alignment.py`

修改檔案：

- `group_a_plus/operations/daily_signal.py`
- `group_a_plus/integrations/llm_commentary.py`
- `scripts/run/run_ncf_daily_pipeline.py`
- `scripts/evaluate/group_a_plus_strategy_signature.py`

功能：

- 從現有 live signal 擷取多個來源：
  - `ncf_00631l`
  - `ncf_00632r_inverse`
  - `ncf_cross_ticker`
  - `finbert_sentiment`
  - `composite_risk_score`
  - `factor_lens`
  - `execution_regime`
- 每個來源轉成：
  - `bullish`
  - `bearish`
  - `neutral`
  - `strength`
  - `reason`
- 輸出整體：
  - `alignment`
  - `dominant_direction`
  - `direction_counts`
  - `weighted_share`
  - `divergent_sources`
  - `confidence_penalty`

手動執行：

```bash
.venv/bin/python scripts/run/build_group_a_plus_signal_alignment.py
```

實際輸出：

- `report/group_a_plus/latest/signal_alignment.json`

目前結果：

```text
alignment = mixed
dominant_direction = bearish
direction_counts = bullish 1 / bearish 5 / neutral 1
weighted_share.bearish = 0.7951
divergent_sources = ["factor_lens"]
confidence_penalty = 0.1
```

解讀：

- 多數來源偏防守，包括 NCF 00631L、00632R inverse、cross ticker、composite risk、execution regime。
- `factor_lens` 是目前主要分歧來源，代表模型因子近期有效性仍過關，但方向訊號/風險層偏防守。

已重產：

- `results/group_a_plus_live_signal_v2.json`
- `report/group_a_plus/latest/live_signal.json`
- `report/group_a_plus/latest/signal_alignment.json`
- `report/group_a_plus/latest/commentary_20260629.json`
- `results/group_a_plus_strategy_bench_signature.json`
- `report/group_a_plus/latest/alert_state.json`

新 signature：

```text
3b4d07022894c8c4291267fe818ceec1a31ec0bdd21b5849c7cc119994fb4460
```

簽章改變原因：

- signature payload 現在納入 `signal_alignment`，策略核心權重與 NCF 機率未因 alignment 改變。

驗證：

```bash
.venv/bin/python -m pytest tests/test_group_a_plus_daily_signal_v2.py tests/test_group_a_plus_signal_alignment.py tests/test_group_a_plus_strategy_signature.py -q
```

結果：

```text
17 passed
```

下一步可做 OpenStock 導入優先 4：

- 環境與 Pipeline Health Check。

### 2026-06-30 續作：導入優先 4

已新增環境與 Pipeline Health Check。

新增檔案：

- `group_a_plus/operations/strategy_env.py`
- `scripts/run/check_strategy_env.py`
- `tests/test_group_a_plus_strategy_env.py`

修改檔案：

- `scripts/run/run_ncf_daily_pipeline.py`

功能：

- 檢查必要檔案：
  - `report/group_a_plus/latest/strategy.json`
  - `report/group_a_plus/latest/live_signal.json`
  - `results/ncf_00631l_20260630.json`
  - `results/ncf_00631l_v5_tabnet_panel.csv`
  - `config/group_a_plus_watchlist.json`
- 檢查必要目錄：
  - `results`
  - `report/group_a_plus/latest`
  - `news`
- 檢查 `.venv/bin/python` 是否存在，以及目前是否用專案 venv 執行。
- 檢查 optional env，並遮罩敏感值：
  - `MINIMAX_API_KEY`
  - `ANTHROPIC_API_KEY`
  - `NCF_EXTERNAL_ALLOW_DOWNLOAD`
- daily pipeline 會寫出：
  - `report/group_a_plus/latest/strategy_env_health.json`

手動執行：

```bash
.venv/bin/python scripts/run/check_strategy_env.py
```

實際輸出：

```text
status = ok
missing_files = []
bad_dirs = []
warnings = []
running_inside_project_venv = true
```

驗證：

```bash
.venv/bin/python -m pytest tests/test_group_a_plus_strategy_env.py tests/test_run_ncf_daily_pipeline.py -q
```

結果：

```text
4 passed
```

下一步可做 OpenStock 導入優先 5：

- Symbol normalization for reports/dashboard。

### 2026-06-30 續作：導入優先 5

已新增報表用 Symbol Normalization。

新增檔案：

- `group_a_plus/utils/__init__.py`
- `group_a_plus/utils/symbols.py`
- `tests/test_group_a_plus_symbol_utils.py`

修改檔案：

- `group_a_plus/operations/daily_signal.py`

功能：

- 將 yfinance/Finnhub 風格 symbol 轉成 TradingView 風格。
- 支援較長 suffix 優先比對，避免 `.TWO` 被誤判成 `.TW`。
- daily signal 會輸出 `symbol_metadata`。

目前支援範例：

```text
0050.TW -> TWSE:0050
00631L.TW -> TWSE:00631L
00679B.TWO -> TPEX:00679B
```

用途：

- 報表。
- dashboard。
- 外部圖表連結。

不用途：

- 不參與交易決策。
- 不改 target weights。
- 不納入 strategy signature。

已重產：

- `results/group_a_plus_live_signal_v2.json`
- `report/group_a_plus/latest/live_signal.json`

驗證：

```bash
.venv/bin/python -m pytest tests/test_group_a_plus_symbol_utils.py tests/test_group_a_plus_daily_signal_v2.py tests/test_group_a_plus_strategy_env.py tests/test_run_ncf_daily_pipeline.py -q
```

結果：

```text
19 passed
```

目前 OpenStock 可導入的前五項已完成：

1. Alert state / cooldown。
2. Watchlist 新聞摘要。
3. 多來源 signal alignment。
4. 環境與 pipeline health check。
5. Symbol normalization。
