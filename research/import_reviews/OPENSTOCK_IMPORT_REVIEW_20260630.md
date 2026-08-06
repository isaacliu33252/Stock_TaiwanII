# OpenStock 導入分析記錄 - 2026-06-30

## 分析範圍

來源專案：

- Windows 路徑：`C:\Users\isaac\Downloads\OpenStock-main\OpenStock-main`
- WSL 路徑：`/mnt/c/Users/isaac/Downloads/OpenStock-main/OpenStock-main`

目標策略：

- 本 repo 最新 GroupA+ / A2118 策略
- 路徑：`C:\Users\isaac\Downloads\Stock_taiwan2-main\Stock_taiwan2-main`

分析目的：

- 判斷 OpenStock 是否有優點可以導入最新策略。
- 只導入適合本策略的工程概念，不直接搬程式碼。

## 授權限制

OpenStock 採用 `AGPL-3.0`。

結論：

- 不直接複製 OpenStock 原始碼。
- 可獨立重作其工程概念。
- 不導入 Next.js UI、MongoDB schema、Inngest runtime、Nodemailer/Kit 行銷流程。

## 總結

OpenStock 是股票資訊產品，不是量化策略或模型訓練專案。

主要功能：

- 股票搜尋
- Watchlist
- 價格提醒
- Finnhub / TradingView 整合
- AI 產生 email / 新聞摘要
- Inngest 背景排程
- MongoDB 持久化

因此，OpenStock 沒有可直接提升 A2118 報酬或 Sharpe 的交易 alpha。

真正可導入的是「策略運行層」：

1. 策略 alert state / cooldown。
2. Watchlist 式新聞與摘要。
3. 多來源 sentiment / signal alignment。
4. 外部資料 provider fallback 與 timeout。
5. 環境與流程健康檢查。
6. 台股 `.TW` / `.TWO` symbol normalization。

## 已檢視重點

### `README.md`

觀察：

- Next.js 15 / React 19 / TypeScript。
- MongoDB 保存 watchlist / alert。
- Finnhub 做行情與新聞。
- TradingView 做圖表。
- Inngest 做背景任務。
- AI provider 用於 email 與摘要。
- 授權為 AGPL-3.0。

可借鏡：

- 使用者介面、資料抓取、背景任務、通知輸出彼此分離。
- 對本策略而言，這表示 daily signal 應該和通知/監控狀態分離。

### `lib/actions/finnhub.actions.ts`

觀察：

- 即時 quote 不快取。
- 公司 profile 長時間快取。
- 新聞短時間快取。
- 有 symbol 時先抓個股新聞，沒有則 fallback 到 general market news。
- 多個 symbol 的新聞用 round-robin 方式挑選，避免單一標的壟斷摘要。
- API key 不存在時，搜尋流程回傳空結果而不是讓 UI 崩潰。

可導入：

- 策略 watchlist 新聞摘要：
  - `0050.TW`
  - `00631L.TW`
  - `00632R.TW`
  - `00679B.TWO`
- 新聞挑選要平衡，不讓單一 ETF 或單一來源壟斷 commentary。
- 外部資料抓取應該分清楚：
  - 即時資料：短快取或不快取。
  - 參考資料：長快取。
  - 新聞資料：短快取。

### `database/models/watchlist.model.ts`

觀察：

- Watchlist 以 user + symbol 做唯一索引。
- symbol 會 uppercase / trim。

可導入：

- 不需要 MongoDB。
- 可以建立簡單 JSON 設定，例如：

```json
{
  "group_a_plus": ["0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO"]
}
```

用途：

- daily commentary。
- 新聞摘要。
- 監控 dashboard。
- 外部圖表連結。

### `database/models/alert.model.ts`

觀察：

OpenStock alert 狀態包含：

- symbol
- target price
- condition: `ABOVE` / `BELOW`
- active
- triggered
- expiresAt
- createdAt

可導入：

- 本 repo 已經有 `signal_alerts`。
- 下一步應該把 `signal_alerts` 變成可持久化狀態：
  - 第一次看到。
  - 上次看到。
  - 上次發出。
  - 是否被 cooldown 壓掉。
  - 是否 resolved。

這是本次最值得先做的項目。

### `lib/inngest/functions.ts`

觀察：

- 背景任務分成清楚 step。
- 價格 alert 會先把 alert 按 symbol 分組，再抓價格。
- alert 觸發後會標成 inactive / triggered。
- 週報和 email 是背景任務，不塞進核心查詢邏輯。

可導入：

- 不需要導入 Inngest。
- 本 repo 可用 Python CLI + Windows Task Scheduler 做同樣概念。
- daily pipeline 結尾可更新 alert state，產生：
  - emitted alerts
  - suppressed alerts
  - resolved alerts

### `lib/ai-provider.ts`

觀察：

- AI provider 抽象層。
- Gemini / MiniMax / Siray。
- primary 失敗後 fallback。
- 有測試覆蓋 provider fallback。

本 repo 現況：

- `group_a_plus/integrations/llm_commentary.py` 已有：
  - `auto`
  - `minimax`
  - `anthropic`
  - `template`
- provider 失敗時會 fallback 到 template。

可改善：

- commentary output 可再加入 provider health：
  - 嘗試哪個 provider。
  - 是否 fallback。
  - 最後使用哪個 mode。
  - 錯誤原因需 redacted。

### `lib/actions/adanos.actions.ts` 與 `adanos.helpers.ts`

觀察：

- 多來源 sentiment：
  - Reddit
  - X.com
  - News
  - Polymarket
- 每個來源獨立容錯。
- 有 timeout。
- 各來源資料先 normalize，再聚合。
- 聚合結果包含：
  - average buzz
  - bullish average
  - source alignment
  - available source count
- 全部來源失敗時回傳 null，不硬湊錯資料。

可導入：

- 建立策略 signal alignment：
  - NCF 00631L
  - NCF 00632R
  - FinBERT
  - factor lens
  - chip / derivative score
  - TDCC / shareholding
- 輸出：
  - bullish / bearish / mixed / wide_divergence
  - available_sources
  - divergent_sources
  - confidence_penalty

這適合 A2118，因為 A2118 已經依賴多個訊號，但目前比較像分散欄位，還不是集中 alignment 摘要。

### `lib/utils.ts`

觀察：

- Finnhub symbol 可轉成 TradingView symbol。
- 台股：
  - `.TW` -> `TWSE`
  - `.TWO` -> `TPEX`
- 較長 suffix 先比對，避免 `.TWO` 被誤判成 `.TW`。

可導入：

- 建立台股 symbol normalization utility：
  - `0050.TW` -> `TWSE:0050`
  - `00631L.TW` -> `TWSE:00631L`
  - `00679B.TWO` -> `TPEX:00679B`

這對報表/dashboard 有用，但不影響交易決策。

### `scripts/check-env.mjs`

觀察：

- 檢查 required / optional / deprecated env。
- 敏感值會遮罩。
- 缺少必要項目時明確失敗。

可導入：

- 增加 Python preflight：
  - `.venv` 是否存在。
  - DB 檔是否存在。
  - 必要 results/report 檔是否存在。
  - commentary/news 需要的 API key 是否存在。
  - 輸出路徑是否可寫。

## 導入優先順序

### 優先 1：策略 Alert State / Cooldown

原因：

- 本 repo 已經有 `signal_alerts`。
- 導入成本低。
- 不改交易決策。
- 可避免 daily run 重複發出同一個警報。
- 最符合 OpenStock alert 模型的可移植價值。

本次已開始實作：

- 新增 `group_a_plus/operations/alert_state.py`
- 新增 `scripts/run/update_group_a_plus_alert_state.py`
- 新增 `tests/test_group_a_plus_alert_state.py`
- daily pipeline 已接上 alert-state 更新。

目前輸出：

- `report/group_a_plus/latest/alert_state.json`

目前 active alerts：

- `regime_transition`
- `total_risk_score`

### 優先 2：策略 Watchlist 新聞摘要

原因：

- 可改善 commentary 內容。
- 可把新聞來源與目前持倉/監控標的對齊。

建議：

- 新增 `config/group_a_plus_watchlist.json`。
- commentary 讀取 watchlist。
- 若個股/ETF 新聞不足，fallback 到市場新聞。

本次續作已實作：

- 新增 `config/group_a_plus_watchlist.json`
- 新增 `group_a_plus/integrations/watchlist_news.py`
- 新增 `scripts/run/build_group_a_plus_watchlist_news.py`
- 新增 `tests/test_group_a_plus_watchlist_news.py`
- commentary output 已附上 `watchlist_news`
- daily pipeline 已接上 `report/group_a_plus/latest/watchlist_news.json`

目前輸出：

- `article_count = 8`
- `fallback_used = false`
- `0050.TW` / `00631L.TW` / `00632R.TW` / `00679B.TWO` 各 2 則。

### 優先 3：多來源 Signal Alignment

原因：

- A2118 多訊號已經存在，但缺集中一致性判斷。
- 可降低單一訊號過度主導的風險。

建議：

- 建立 alignment report。
- 接入 daily signal warning / commentary / signature payload。

本次續作已實作：

- 新增 `group_a_plus/integrations/signal_alignment.py`
- 新增 `scripts/run/build_group_a_plus_signal_alignment.py`
- 新增 `tests/test_group_a_plus_signal_alignment.py`
- daily signal 已新增 `signal_alignment`
- commentary 已附上 `signal_alignment`
- signature payload 已納入 `signal_alignment`
- daily pipeline 已接上 `report/group_a_plus/latest/signal_alignment.json`

目前結果：

- `alignment = mixed`
- `dominant_direction = bearish`
- `direction_counts = bullish 1 / bearish 5 / neutral 1`
- `divergent_sources = ["factor_lens"]`
- `confidence_penalty = 0.1`

解讀：

- 多數來源支持防守/去槓桿。
- `factor_lens` 顯示因子有效性仍可用，是目前主要分歧來源。
- 這是監控與 commentary 輔助，不改交易決策。

### 優先 4：環境與 Pipeline Health Check

原因：

- daily pipeline 依賴多個資料檔與外部來源。
- scheduled run 失敗時需要更明確原因。

建議：

- 新增 `scripts/run/check_strategy_env.py`。

本次續作已實作：

- 新增 `group_a_plus/operations/strategy_env.py`
- 新增 `scripts/run/check_strategy_env.py`
- 新增 `tests/test_group_a_plus_strategy_env.py`
- daily pipeline 已接上 `report/group_a_plus/latest/strategy_env_health.json`

目前結果：

- `status = ok`
- `missing_files = []`
- `bad_dirs = []`
- `warnings = []`
- 目前使用 `.venv/bin/python` 執行。

### 優先 5：Symbol Normalization

原因：

- 對報表與 dashboard 有用。
- 低風險。
- 不影響策略本體。

本次續作已實作：

- 新增 `group_a_plus/utils/symbols.py`
- 新增 `tests/test_group_a_plus_symbol_utils.py`
- daily signal 已新增 `symbol_metadata`

目前轉換：

- `0050.TW` -> `TWSE:0050`
- `00631L.TW` -> `TWSE:00631L`
- `00679B.TWO` -> `TPEX:00679B`

說明：

- 只用於報表/dashboard/外部圖表連結。
- 不參與策略決策。
- 不改權重。
- 不納入 strategy signature。

## 不建議導入

不建議導入：

- Next.js UI 元件。
- Better Auth。
- MongoDB schema。
- Inngest runtime。
- Nodemailer / Kit email 行銷流程。
- TradingView widget 到策略核心。
- OpenStock 原始碼。

## 本次結論

OpenStock 沒有可直接提高 A2118 績效的 alpha。

最有價值的導入方向是把策略變成更可靠的日常運行系統：

- 可追蹤 alert。
- 可 cooldown。
- 可 resolved。
- 可輸出每日監控狀態。

本次已完成 OpenStock 可導入的五項工程優點：

1. 策略 alert state / cooldown。
2. 策略 watchlist 新聞摘要。
3. 多來源 signal alignment。
4. 環境與 pipeline health check。
5. Symbol normalization。

這些都是運行監控與報表層改進，不改 A2118 的交易決策。
