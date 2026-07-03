# Event-Driven Sentiment 導入評估紀錄 - 2026-07-01

## 來源

- 來源路徑：`C:\Users\isaac\Downloads\Sentiment-Analysis-in-Event-Driven-Stock-Price-Movement-Prediction-master\Sentiment-Analysis-in-Event-Driven-Stock-Price-Movement-Prediction-master`
- 目標：評估是否有可導入 Group A+ 最新策略的優點。

## 專案摘要

此專案用 Reuters 公司新聞標題/內容預測股票後續漲跌，主要流程是：

- 爬 Reuters 公司新聞與 Yahoo 股價。
- 只取 `topStory` 類新聞，避免普通新聞噪音過高。
- 用公司/日期把新聞與股價報酬對齊。
- 產生 short/mid/long 三種 label：
  - short：約當日 open 到 adjClose。
  - mid：約 7 日。
  - long：約 28 日。
- label 使用個股相對 S&P 500 的 normalized/relative return。
- 文本做 tokenize、lemmatize、stopword removal、固定長度 padding。
- 模型是 PyTorch CNN text classifier，訓練方式包含 SGLD/thinning 多模型平均。

## 可取概念

可導入 Group A+ 的概念不是模型，而是事件資料治理與標籤設計：

1. 事件新聞與未來報酬對齊
   - 目前 Group A+ 已有 watchlist news、FinBERT、LM dictionary sentiment。
   - 但這些主要是日級情緒 snapshot，還沒有完整記錄「新聞發生日後 1/5/20 日相對報酬是否真的支持該情緒」。

2. 相對大盤/benchmark return label
   - 該專案用個股報酬減 S&P 500 報酬，避免把大盤漲跌誤判成公司事件效果。
   - Group A+ 可改成 ETF/標的相對 `0050.TW`、`TWII` 或策略 benchmark。

3. 多 horizon 評估
   - short/mid/long label 概念可對應 Group A+ 的 1D/5D/20D。
   - 這能檢查新聞情緒是短線噪音，還是對 H20 方向/回撤有用。

4. topStory / event priority
   - 只取事件重要新聞，避免把一般新聞量當作有效訊號。
   - Group A+ 目前 watchlist selection 是 keyword round-robin，可再加事件重要度/來源權重。

5. 重複新聞治理
   - 原專案有 `del_repeat.py`，處理同公司多 ticker 重複新聞。
   - Group A+ 已用 URL 去重，但可再補 title/content hash 去重，避免不同 URL 的同稿重複放大情緒。

6. 高信心 bucket 評估
   - 原專案不只看整體 accuracy，也看距離 0.5 較遠的高信心樣本。
   - Group A+ 可用於 FinBERT/LM/signal alignment：只在高信心 bucket 做 promotion 判斷。

## 不建議直接導入的原因

- Reuters/Yahoo crawler 舊且與台股資料源不匹配。
- 模型是舊式 CNN text classifier；目前 Group A+ 已有 FinBERT proxy/model 與 LM dictionary shadow，直接搬模型價值低。
- 原專案測試集用最近 90 天切分，沒有嚴格 walk-forward 與交易成本驗證。
- 原專案主要是公司個股新聞，不是台股 ETF 組合/槓桿 ETF 配置。
- SGLD/thinning 多模型平均有研究價值，但導入成本高，且目前缺少台灣新聞標註資料支撐。

## 與目前 Group A+ 的關係

目前已存在：

- `group_a_plus/integrations/watchlist_news.py`
  - 本地新聞 keyword selection。
  - URL 去重。
  - symbol round-robin。
- `group_a_plus/integrations/finbert.py`
  - daily FinBERT sentiment snapshot。
  - freshness decay。
  - risk score。
- `group_a_plus/integrations/lm_dictionary_sentiment.py`
  - LM dictionary shadow source。
  - `active_allocation_impact: none`。
- `group_a_plus/integrations/signal_alignment.py`
  - 多訊號方向一致性檢查。

缺口：

- 沒有針對 watchlist news 建立 forward return attribution。
- 沒有檢查新聞情緒分數和 1D/5D/20D 相對報酬的一致性。
- 沒有 title/content hash 去重。
- 沒有事件重要度或 topStory 類似欄位。

## 建議導入方式

建議做，但只放在 shadow/evaluation 層，不進 active allocation。

優先順序：

1. 新增 event sentiment attribution evaluator
   - 輸入：`report/group_a_plus/latest/watchlist_news.json`、FinBERT/LM snapshot、DuckDB OHLCV。
   - 輸出：新聞日期後 1D/5D/20D 的相對報酬。
   - benchmark：`0050.TW` 或 TWII。
   - 目的：評估新聞情緒是否真的對 Group A+ 的 H20 方向或風險有解釋力。

2. 補強 watchlist news 去重
   - 在 URL 去重之外，加 title/snippet 正規化 hash。
   - 避免同稿不同 URL 或不同來源重複放大。

3. 新增 confidence bucket report
   - 只看高 negative/high positive 情緒樣本的 forward return。
   - 若高信心樣本沒有明顯 edge，不得升級到 advisory。

## 結論

不建議直接導入 CNN/SGLD 模型。

建議導入事件驅動標籤與評估框架，狀態如下：

```text
decision = import_evaluation_concepts_only
recommended_next_step = event_sentiment_attribution_shadow
active_allocation_impact = none
```

此改善若導入，應先作為研究/治理輸出，只有多年度 OOS 或足夠事件樣本證明有效後，才考慮影響 signal alignment 權重。

## 試導入結果

已完成 shadow/evaluation 層導入：

- 新增 `scripts/evaluate/evaluate_event_sentiment_attribution_shadow.py`
  - 讀取 `report/group_a_plus/latest/watchlist_news.json`。
  - 對每篇新聞計算 FinBERT proxy sentiment。
  - 若 LM 字典可用，補 LM dictionary per-article score。
  - 以 title/snippet 正規化 hash 標記重複內容。
  - 用 DuckDB OHLCV 計算 1D/5D/20D forward return。
  - 輸出相對 benchmark return，預設 benchmark 為 `0050.TW`。
  - 固定 `active_allocation_impact: none`。
- 新增 `tests/test_evaluate_event_sentiment_attribution_shadow.py`

測試：

```bash
.venv/bin/python -m pytest -q tests/test_evaluate_event_sentiment_attribution_shadow.py
```

結果：

```text
3 passed
```

實測輸出：

```text
results/event_sentiment_attribution_shadow_latest_20260701.json
```

以 2026-06-30 最新資料實測摘要：

```text
article_count                   8
duplicate_content_hash_count    0
h1 matured_count                8
h1 mean_relative_return        -0.0184
h1 median_relative_return      -0.0162
h1 positive_relative_rate       0.25
h1 sentiment_direction_match    0.3333
h5 matured_count                0
h20 matured_count               0
active_allocation_impact        none
```

判讀：

- 目前資料庫只到 2026-06-30，watchlist 新聞多為 2026-06-29，因此只有 1D attribution 成熟。
- 1D 結果偏弱：平均相對報酬為負、正相對報酬比例 25%、情緒方向命中率約 33%。
- 這支持「新聞情緒先留在 attribution/governance，不進配置」的決策。
- 等資料更新後，5D/20D 會自動成熟，屆時再看是否有穩定 edge。
