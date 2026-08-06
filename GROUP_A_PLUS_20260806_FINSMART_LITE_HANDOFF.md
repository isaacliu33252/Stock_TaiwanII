# Group A+ 2026-08-06 交接記錄：FinSMART論文分析與FinSMART-lite shadow導入邊界

Status: 完整記錄本次針對使用者提供 PDF `C:\Users\isaac\Downloads\2607.28127.pdf` 的分析、已落地的 GroupA+ shadow/readiness 產物、實測結果、驗證結果，以及後續若要導入最新策略時的安全邊界。本文只描述本次 FinSMART 工作；同日先前的每日資料下載、8/6 預測、持股調整問題僅在必要處補充背景。

## 目錄

1. 使用者需求與本次決策
2. 論文重點：arXiv 2607.28127 FinSMART
3. 對 GroupA+ 的可導入優點
4. 本次已完成的本地診斷
5. 本次新增/產出的檔案
6. Readiness review 結論與治理邊界
7. 驗證結果
8. 與 2026-08-06 groupA+ 最新策略/持股預測的關係
9. 下一步建議
10. 明確未做事項與風險

---

## 1. 使用者需求與本次決策

使用者要求：

> `C:\Users\isaac\Downloads\2607.28127.pdf 分析, 是否有優點可以導入groupA+，最新策略？`

分析後結論：

**有優點可以導入，但只能先導入 shadow / readiness 層，不應直接改 groupA+ latest strategy 或 golden1_0531 的 live target weights。**

原因：

- 論文核心是「金融文本情緒訊號要用實際市場報酬做 market-aligned reward 校準」，不是單純換一個情緒模型。
- GroupA+ 目前已有 `watchlist_news`、FinBERT proxy、LM/LLM sentiment features、`signal_alignment`、`llm_state_reward` governance 等模組，適合先接成可稽核的 shadow artifact。
- 論文使用 S&P 500 個股完整新聞、公司 NER、Yahoo Finance 日資料、LLM + GRPO/LoRA 訓練；GroupA+ 現場是台灣 ETF/台股/中文新聞，且多數新聞是 title/snippet 或 watchlist 匹配，不能直接照搬成 live 交易權重。
- 本地診斷顯示 ticker/entity-specific 新聞確實比泛市場新聞更有訊號，但 next-day alignment 還不夠強到能直接進 live。

本次採取的工程決策：

- 建立 **FinSMART-lite readiness review**。
- 允許下一步建立 `market_aligned_sentiment_shadow.json`。
- 明確禁止 LLM/GRPO 訓練、禁止輸出 target weights、禁止自動 rebalance、禁止改 golden1_0531 或 latest strategy 權重。

---

## 2. 論文重點：arXiv 2607.28127 FinSMART

PDF 路徑：

`/mnt/c/Users/isaac/Downloads/2607.28127.pdf`

PDF metadata：

- Title: `FinSMART: Financial Sentiment Analysis for Algorithmic Trading through Market-Aligned Reinforcement Learning`
- Authors: Giorgos Iacovides, Wuyang Zhou, Danilo Mandic
- arXiv/DOI: `2607.28127`, `https://doi.org/10.48550/arXiv.2607.28127`
- PDF creation date: 2026-07-31
- Pages: 8

核心方法：

1. **Article Gating & Market Alignment**
   - 先用 NER 確認新聞能可靠對應到公司/標的。
   - Paper 使用 BERT-base-NER，target company confidence > 98% 才保留。
   - 避免把不相關文章錯配到股票，污染 reward。

2. **Sentiment Gating**
   - reference policy 必須能明確產生 `Positive / Neutral / Negative`。
   - 不明確、無法穩定分類的文章丟掉。
   - 這點對 GroupA+ 很重要，因為台灣新聞常是宏觀、政策、產業、政治或泛市場消息，直接拿來打 ETF 情緒分數雜訊很高。

3. **Dual-Filter Trading Reward**
   - sentiment direction `d ∈ {-1, 0, +1}`。
   - market label `y ∈ {-1, 0, +1}` 不是只看 raw return，而是同時要求：
     - stock raw return 方向正確；
     - stock alpha return 超過門檻。
   - Paper 使用 alpha threshold `tau = 0.5%`。
   - Reward:
     - correct direction: `+2.0`
     - correct neutral: `+0.1`
     - opposite direction: `-1.5`
     - missed trade / false long-short signal: `-1.0`

4. **GRPO + KL + LoRA**
   - 以 GRPO 做 group-relative reward optimization。
   - `G=8` completions，KL beta `0.1`。
   - LoRA rank `16`，alpha `32`，dropout `0.05`。
   - Paper 稱單張 NVIDIA A6000 48GB 可完成。

5. **Periodic Market-Aligned Retraining**
   - 每 6 個月 expanding-window retrain。
   - 新文章 + 後續實際市場結果自動形成新的訓練資料，不需人工標籤。

實驗結果摘要：

- FinSMART vs FinDPO：
  - cumulative return: `264.9%` vs `109.8%`
  - annualized return: `91.5%` vs `45.0%`
  - Sharpe: `1.97` vs `1.12`
  - RankIC: `0.061` vs `0.053`
- Periodic retraining：
  - static FinSMART cumulative return: `264.9%`
  - retrained FinSMART cumulative return: `406.2%`
  - Sharpe: `1.97` -> `2.41`

重要 caveat：

- Paper 訓練 reward 使用 same-day raw/alpha return，是為了提高 supervision signal-to-noise。
- Paper 的 trading evaluation 使用 next-day open-to-open return，避免 look-ahead bias。
- 因此 GroupA+ 不可把 same-day return 當 live signal 直接使用。

---

## 3. 對 GroupA+ 的可導入優點

最值得導入的是 **FinSMART-lite**，不是完整 FinSMART。

可導入設計：

1. **嚴格新聞/標的對應**
   - 目前 `watchlist_news.py` 主要靠 keyword matching。
   - FinSMART 啟示：應把新聞先分類到 0050、00631L、00632R、2330、TWII proxy、semiconductor basket 等 entity/basket。
   - 沒有明確對應的新聞不要進 reward/trust。

2. **Sentiment gate**
   - 只有能明確判斷 bullish / neutral / bearish 的新聞才進 shadow reward。
   - 目前 rule-based FinBERT proxy / LLM sentiment 可能對中文新聞或泛市場新聞產生低品質分數。
   - 應加入 `unclear_or_unmapped -> discard / low confidence`。

3. **Market-aligned reward**
   - 把新聞當天的 sentiment 與後續 1/3/5 trading-day 報酬對照。
   - 報酬需扣掉 ETF/market/basket benchmark 或至少用 0050/TWII proxy 做 alpha。
   - 加入成本/滑價門檻，避免把雜訊小漲跌當 reward。

4. **每日預估檢討回填**
   - 使用者已要求：「將預估完，要加上檢論昨天預估。」
   - 這剛好可成為 FinSMART-lite 的 rolling reward dataset：
     - 昨天新聞/情緒/策略結論
     - 今天實際報酬
     - 是否方向正確
     - 是否扣成本後仍有 edge
     - 是否該調整 sentiment source trust

5. **只做 trust/gate，不做 direct weight**
   - 初期只影響 `signal_alignment` 或 `strategy_trust_gate` 的 diagnostic/trust score。
   - 不直接輸出 target weights。

不建議立即導入：

- 完整 GRPO/LoRA/LLM 訓練。
- same-day return 作為 live signal。
- 讓新聞情緒直接推翻 NCF/golden1/latest strategy。
- 讓 FinSMART-lite 直接開 00631L 或 00632R 部位。

---

## 4. 本次已完成的本地診斷

本 repo 已存在一個未追蹤腳本：

`scripts/evaluate/finsmart_reward_alignment_diagnostic.py`

我沒有覆蓋它，直接執行：

```bash
.venv/bin/python scripts/evaluate/finsmart_reward_alignment_diagnostic.py
```

輸出：

`research/shadow/FINSMART_REWARD_ALIGNMENT_DIAGNOSTIC_20260805.md`

此腳本做的事：

- 讀取 `FinRL/data/stock_data.db` 的 `0050.TW` close return。
- 比較現有 sentiment feature 與 0050 realized return 的同日/隔日相關。
- 用 paper 的 `tau = 0.5%` 概念做 gated return 診斷。
- 純 research/shadow，不寫 production DB，不改 live report。

診斷結果：

| Series | n | same-day corr | next-day corr | gated same-day | gated next-day |
|---|---:|---:|---:|---:|---:|
| production finbert_sentiment LTN market-wide vs 0050 | 1555 | 0.1148 | 0.0052 | 0.1379 | -0.0500 |
| FinMind 0050-tagged headlines vs 0050 | 354 | 0.2355 | 0.0884 | 0.2638 | 0.1033 |
| production llm_sentiment_score LTN market-wide vs 0050 | 1555 | -0.0203 | -0.0252 | -0.0255 | -0.0269 |

解讀：

- FinMind 0050-tagged headlines 明顯優於 LTN 泛市場新聞。
- ticker/entity gating 是最重要的第一步。
- same-day alignment > next-day alignment，方向與 paper 一致。
- next-day alignment 仍偏弱，尚不足以 live promotion。
- production LLM market-wide sentiment 目前沒有明顯正向 alignment。

---

## 5. 本次新增/產出的檔案

### 新增程式

`scripts/evaluate/build_group_a_plus_finsmart_lite_readiness_review.py`

用途：

- 把 FinSMART paper 的可用設計轉成 GroupA+ readiness review。
- 讀取本地 PDF 與 reward-alignment diagnostic。
- 產生 latest + history JSON。
- 明確禁止 training/live/target weights。

### 新增測試

`tests/test_build_group_a_plus_finsmart_lite_readiness_review.py`

測試內容：

- PDF 存在且 diagnostic 存在時，允許 shadow design。
- 即使允許 shadow design，也必須禁止：
  - `llm_training_allowed`
  - `grpo_training_allowed`
  - `outputs_target_weights`
  - `target_weight_change_allowed`
- PDF 缺失時 blocked。
- `write_review()` 正確寫 latest 與 history。

### 產出 report

`report/group_a_plus/latest/finsmart_lite_readiness_review.json`

history：

`report/group_a_plus/finsmart_lite_readiness/history/finsmart_lite_readiness_review_20260806.json`

### 產出 research note

`research/shadow/FINSMART_REWARD_ALIGNMENT_DIAGNOSTIC_20260805.md`

### 已存在但仍未追蹤的診斷腳本

`scripts/evaluate/finsmart_reward_alignment_diagnostic.py`

注意：這支腳本在本次開始前已是 untracked 狀態。本次只執行它，沒有修改。

---

## 6. Readiness review 結論與治理邊界

執行：

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_finsmart_lite_readiness_review.py --as-of 2026-08-06
```

輸出摘要：

```json
{
  "status": "available_for_shadow_design",
  "shadow_design_allowed": true,
  "llm_training_allowed": false,
  "target_weight_change_allowed": false,
  "warning_reasons": []
}
```

完整 review 中的重要 decision：

```json
{
  "finsmart_lite_shadow_design_allowed": true,
  "market_aligned_sentiment_shadow_allowed": true,
  "llm_training_allowed": false,
  "grpo_training_allowed": false,
  "outputs_target_weights": false,
  "promote_to_live": false,
  "target_weight_change_allowed": false,
  "auto_rebalance_allowed": false,
  "keep_golden1_0531_unchanged": true,
  "keep_latest_strategy_weights_unchanged": true
}
```

推薦的下一個 shadow artifact：

`report/group_a_plus/latest/market_aligned_sentiment_shadow.json`

建議 input sources：

- `report/group_a_plus/latest/watchlist_news.json`
- `report/group_a_plus/latest/watchlist_news_finmind.json`
- `FinRL/data/stock_data.db:ohlcv`
- `FinRL/data/sentiment/finbert_market_sentiment_daily.csv`
- `FinRL/data/sentiment/llm_market_sentiment_daily.csv`

建議 entity mapping targets：

- `0050.TW`
- `00631L.TW`
- `00632R.TW`
- `2330.TW`
- `TWII_proxy`
- `semiconductor_basket`

Reward spec：

- horizons: `[1, 3, 5]` trading days
- alpha threshold: `0.005`
- cost-aware: required
- labels:
  - bullish: `1`
  - neutral: `0`
  - bearish: `-1`
- reward:
  - correct direction: `2.0`
  - correct neutral: `0.1`
  - opposite direction: `-1.5`
  - missed/false signal: `-1.0`

建議 integration points：

- `group_a_plus/integrations/watchlist_news.py`
- `group_a_plus/integrations/signal_alignment.py`
- `group_a_plus/integrations/llm_sentiment_features.py`
- `group_a_plus/integrations/strategy_trust_gate.py`

Promotion requirements：

- point-in-time join，禁止 look-ahead。
- walk-forward 2024-2026 必須提升 next-day alignment。
- cost-adjusted shadow backtest 必須改善 Sharpe 或 drawdown，且 turnover 不惡化。
- 任何 training 或 live weight change 前必須人工 approval。

---

## 7. 驗證結果

執行：

```bash
.venv/bin/python -m pytest tests/test_build_group_a_plus_finsmart_lite_readiness_review.py
```

結果：

```text
3 passed in 1.99s
```

另有實際 builder run 通過：

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_finsmart_lite_readiness_review.py --as-of 2026-08-06
```

產生：

- `report/group_a_plus/latest/finsmart_lite_readiness_review.json`
- `report/group_a_plus/finsmart_lite_readiness/history/finsmart_lite_readiness_review_20260806.json`

---

## 8. 與 2026-08-06 groupA+ 最新策略/持股預測的關係

本次 FinSMART-lite 工作**沒有**改動 2026-08-06 的任何 target weights。

同日先前已完成的 8/6 資料與預測背景如下，供後續接續時避免混淆：

### 最新資料狀態

- 已下載/刷新最新資料並跑 daily pipeline。
- OHLCV provider 當時只回到 `2026-08-05`。
- NCF signals 對 `2026-08-06` 屬於 degraded/stale：
  - `00631L`: UP, prob_up `0.6526`, data date `2026-08-05`
  - `00632R`: DOWN, prob_up `0.2794`, data date `2026-08-05`
  - `0050`: UP, prob_up `0.5001`, data date `2026-08-05`
- `live_signal` requested date `2026-08-06`，actual data date `2026-08-05`，execution_allowed `True`。

### golden1_0531 strict release 1M preview

輸出：

`report/group_a_plus/latest/golden1_0531_signal_20260806_1m_after_refresh_preview.json`

狀態：

- source: `results/group_a_backtest_20250101_20260525_20260526_193252.json`
- actual_data_date: `2026-08-04`
- stale: 2 calendar/business-ish days from requested date
- target:
  - `0050`: 50%
  - `00631L`: 20%
  - cash: 30%
- shares:
  - `0050`: 4968
  - `00631L`: 6221
- prices:
  - `0050`: 100.65
  - `00631L`: 32.15

### latest strategy 1M preview

輸出：

`report/group_a_plus/latest/live_signal_20260806_1m_latest_strategy_after_refresh_preview.json`

狀態：

- actual_data_date: `2026-08-05`
- stale: 1 business day
- regime: `golden1`
- execution_allowed: `True`
- target:
  - `0050`: 30%
  - `00631L`: 0%
  - `00632R`: 27.0787%
  - cash: 42.9213%
- shares:
  - `0050`: 2890
  - `00632R`: 26290
- cash after rounding: `429230.99`

### 使用者要求的新日報格式

使用者已要求：

> 將預估完，要加上檢論昨天預估。

後續每日預估應包含：

- 昨天預估權重。
- 今天實際市場報酬。
- 估算 P&L。
- 預估與實際差異原因。
- gate/freshness 狀態。
- 是否應調整持股或只觀察。

FinSMART-lite 的 market-aligned reward 正好可接這個檢討流程。

---

## 9. 下一步建議

### Step 1：建立真正的 market_aligned_sentiment_shadow

新增腳本建議：

`scripts/evaluate/build_group_a_plus_market_aligned_sentiment_shadow.py`

輸出：

`report/group_a_plus/latest/market_aligned_sentiment_shadow.json`

功能：

- 讀取 `watchlist_news` 與 FinMind 0050-tagged headlines。
- 將文章 mapping 到 ETF / 2330 / semiconductor / TWII proxy。
- 對每篇或每日聚合情緒產生 `bullish/neutral/bearish`。
- 用 1/3/5 日 forward returns 回填 reward。
- 計算 rolling hit rate、rolling reward、source reliability。
- 僅輸出 shadow diagnostics，不輸出 target weights。

### Step 2：加入每日預估檢討

將使用者要求的「檢論昨天預估」擴成每日固定欄位：

- yesterday_forecast_artifact
- yesterday_target_weights
- actual_return_by_asset
- realized_portfolio_pnl_estimate
- forecast_error_reason
- sentiment_reward_update
- trust_adjustment_shadow_only

### Step 3：接入 signal_alignment，但只做 diagnostic

可以在 `signal_alignment` 新增一個 source：

`market_aligned_sentiment_shadow`

初期僅：

- 顯示 available/unavailable。
- 顯示 direction/trust。
- 顯示與 NCF/golden/latest 是否一致。
- 不參與 final target weights。

### Step 4：做 2024-2026 walk-forward

promotion 前最低要求：

- 比現有 FinBERT/LLM sentiment 更高的 next-day RankIC 或 sign hit rate。
- 扣成本後不惡化 turnover。
- crash window 不增加 max drawdown。
- 至少通過 0050、00631L、00632R 三種不同 exposure 的 out-of-sample 分析。

### Step 5：若要訓練 LLM，需另開 governance approval

完整 FinSMART/GRPO 不應在目前步驟直接做。若之後要做：

- 先建立 frozen dataset manifest。
- 明確 GPU/環境/模型。
- 明確 LoRA/GRPO 參數。
- 明確 no-live promotion gate。
- 先 offline smoke，再 shadow backtest，再 manual approval。

---

## 10. 明確未做事項與風險

未做：

- 沒有修改 `group_a_plus/integrations/signal_alignment.py` 的 live 行為。
- 沒有修改 `watchlist_news.py`。
- 沒有修改 `daily_signal.py`。
- 沒有把 FinSMART-lite 接入任何 target weight 或 rebalance plan。
- 沒有訓練 LLM。
- 沒有跑 GRPO/LoRA。
- 沒有變更 golden1_0531 或 latest strategy。

風險/限制：

- 本地新聞資料多為 title/snippet，低於 paper 的 full article corpus 品質。
- 台灣 ETF 與 S&P 500 single-stock news 結構不同。
- 00631L/00632R 是槓桿/反向 ETF，新聞對它們的 mapping 應多數來自 0050/2330/TWII/semiconductor proxy，而不是 ETF 本身新聞。
- same-day alignment 不代表可交易；live evaluation 必須用 next-day 或下個可交易時點。
- 現有 production LLM sentiment market-wide feature 在本次診斷中 alignment 很弱，不能直接信任。
- repo working tree 已有大量既有未 commit 異動，本次只新增/產出本文件第 5 節列出的 FinSMART-lite 相關檔案；未嘗試整理其他無關變更。

本次最重要的交接結論：

**FinSMART 的優點應先轉成 GroupA+ 的 market-aligned sentiment shadow/trust system。當前 readiness 已通過 shadow design，但所有 live 權重、golden1_0531、latest strategy 均保持不變。**
