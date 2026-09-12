# 新聞來源擴充：新增三立(SETN)+Yahoo、補齊自由時報(LTN)缺口、三者排進每日pipeline — 交接記錄

**日期**：2026-08-17
**觸發脈絡**：審查2603.11408論文(WTI原油LLM多維度情緒)並實測既有新聞情緒訊號線後，查詢「目前的新聞來源」，發現production實際運作的新聞來源存在真實缺口，使用者要求擴充。

## 1. 查詢發現：修正前的新聞來源現況

| 來源 | 修正前狀態 | 內容豐富度 |
|---|---|---|
| **LTN(自由時報)** | `watchlist_news.py`名義上的預設來源，但**從未被排進每日pipeline**，`news/ltn_mainstream_*.jsonl`最後一批完整資料是2026-06-09~06-29，之後只有2026-08-06的3個手動主題爬取(共約20篇)，中間有約5週的完全空白。程式碼裡本身就有註解記載這個已知問題(2026-07-07 Fable稽核：連續8天stale、article_count=0)。 | 有真實摘要文字(~145字/篇) |
| **FinMind TaiwanStockNews** | 唯一實際每天自動跑的來源(LTN抓不到東西時的fallback)。 | snippet完全是空字串(0字/篇，只有標題) |
| **GDELT** | 純研究一次性產物(`news_anomaly`系列，2026-06-19)，未接pipeline。 | — |
| **MOPS重大訊息公告** | 被WAF擋，從未成功實作。 | — |

**核心問題**：production實際依賴的來源(FinMind)是title-only，完全沒有內文；唯一有真實摘要內容的來源(LTN)反而沒有排程、長期stale。

## 2. 已完成的擴充

### 2.1 新增 Yahoo 原生RSS來源
`scripts/fetch/fetch_yahoo_news_rss.py` — 抓取兩個Yahoo原生RSS feed：
- `https://tw.stock.yahoo.com/rss?category=news`（Yahoo股市-最新新聞）
- `https://tw.news.yahoo.com/rss/finance`（財經新聞-Yahoo奇摩新聞）

實測**內容品質比LTN還好**——真實新聞導言摘要(~130+字/篇，非空字串)，單次抓取約50篇。輸出schema跟既有`date/source/title/url/category/snippet`格式相容。

### 2.2 新增 SETN(三立新聞) 來源
`scripts/fetch/fetch_setn_news_rss.py` — SETN自己的搜尋頁(`setn.com/search`)是前端JS渲染的SPA，直接fetch拿到空白HTML，LTN那種靜態HTML解析法完全不適用；SETN也沒有可用的RSS feed(所有嘗試路徑都導向首頁404)。改用**Google News RSS的`site:`限定查詢**(`site:setn.com {關鍵字} when:{N}d`)當作間接抓取管道——這是可靠、結構化的替代方案，取得真實日期/標題/連結。**限制**：Google News RSS的`<description>`欄位不含真實內文(只是標題重複+來源標籤)，所以`snippet`欄位刻意留空而非塞入假摘要，避免下游誤用。單次(3天lookback、6個關鍵字)抓到約317篇。

### 2.3 補齊 LTN 缺口
用既有`fetch_ltn_news_jsonl.py`(6個關鍵字：台股/股市/大盤/0050/00631L/台積電，分段避開600筆分頁上限)回補2026-06-30~08-16，合併去重後**2,397篇真實文章**，寫入`news/ltn_mainstream_2026-06-30_to_2026-08-16.jsonl`，填補了原本完全空白的5週缺口。

### 2.4 修正LTN爬蟲的真實bug
`fetch_ltn_news_jsonl.py`原本`fetch_search_results()`只容忍「第2頁以後」的HTTP 404(視為「沒有更多頁」)，**第1頁404會直接拋例外中斷整個呼叫**。這在寬日期範圍手動爬取時很少遇到(關鍵字通常有結果)，但排進每日3天滾動窗口後，某個關鍵字在短視窗內查無結果是常態而非例外——已修正成第1頁跟後續頁的404都統一視為「無結果」，不中斷。已用真實網路連線驗證修正後可正常運作。

### 2.5 三個來源排進每日pipeline
`scripts/run/run_ncf_daily_pipeline.py`的`[watchlist-news]`區塊新增三個non-fatal步驟(仿FinMind既有步驟的try/except模式，任何一個失敗都不會擋住其餘pipeline)：
- **LTN**：3天滾動窗口×5個關鍵字(台股/股市/0050/00631L/台積電)，寫入`news/ltn_mainstream_rolling.jsonl`。
- **Yahoo**：兩個RSS feed，寫入`news/yahoo_news_rss_rolling.jsonl`。
- **SETN**：3天lookback×6個關鍵字，寫入`news/setn_news_rss_rolling.jsonl`。

### 2.6 `watchlist_news.py`改成支援多來源
`DEFAULT_NEWS_GLOB`從單一字串(`"news/ltn_mainstream_*.jsonl"`)改成**三個glob的tuple**(LTN+Yahoo+SETN)，`_iter_news_records()`改成同時支援單一字串跟字串序列，向下相容既有呼叫端(CLI的`--news-glob`單一字串覆寫、既有測試傳入的`news/*.jsonl`都仍正常運作)。**刻意排除FinMind**——FinMind維持「三者都抓不到才用」的fallback語意，不是第四個無條件併入的來源，避免title-only的空摘要稀釋掉其他三個有真實內文的來源。

## 3. 驗證

- 6項新測試(Yahoo 3項+SETN 3項)全部離線用假XML樣本測試，不打真實網路，符合既有`test_fetch_ltn_news_jsonl.py`的慣例。
- 三個抓取器都用**真實網路連線**端對端測過：LTN 106篇(3天滾動窗)、Yahoo 53篇、SETN 317篇(3天lookback)。
- `watchlist_news.py`合併三來源後端對端測過：`build_watchlist_news_summary(signal_date='2026-08-17')`正確產出8篇文章，`fallback_used=False`(不再需要FinMind fallback)，內容包含Yahoo跟自由時報的真實新聞。
- 全部相關測試套件(45項：LTN 8項+Yahoo 3項+SETN 3項+watchlist_news 3項+finmind相關+daily pipeline 21項)全數通過。

## Do Not Do
- 不要把FinMind無條件併入`DEFAULT_NEWS_GLOB`——它是故意設計成fallback-only，混進去會用空摘要稀釋掉LTN/Yahoo/SETN的真實內文優勢。
- 不要假設SETN有RSS或可以直接HTML爬蟲——已確認官方RSS路徑全部404、搜尋頁是JS渲染SPA，唯一可靠管道是Google News RSS proxy，且snippet天生是空的(Google News限制，不是實作疏漏)。
- 不要把LTN`fetch_search_results()`的404容忍範圍改回「僅page>1」——這次排程後第1頁404是常態(短視窗查無結果)，不是應該拋例外的異常情況。
- 每日pipeline新增的三個步驟都是non-fatal(try/except包住)，個別來源掛掉不會影響其他步驟或擋住pipeline，這是刻意設計，不要改成fatal。

## Next Step
無強制後續行動。下次若想重新評估新聞情緒訊號線(呼應2603.11408 follow-up)，現在有了LTN/Yahoo兩個有真實內文的來源可用，比之前只有FinMind的title-only語料更有機會做出有意義的多維度情緒分析——但樣本仍會受限於「累積時間」，需要這些來源實際跑上一段時間後才有足夠樣本量重新測試。

詳細記錄完。
