# StocksProject 導入評估紀錄 - 2026-07-01

## 來源

- 來源路徑：`C:\Users\isaac\Downloads\StocksProject-master\StocksProject-master`
- 目標：評估是否有可導入 Group A+ 最新策略的優點，並先做低風險改善。

## 評估結論

StocksProject 的主體是較舊的 Python 2 股票分類/迴歸研究碼，依賴過時資料介面與硬編碼路徑，不適合直接導入模型或資料流程。

可吸收的部分是「文字情緒作為輔助市場風險訊號」概念，特別是 Loughran-McDonald 財務字典的正負面與風險詞統計。這比直接導入其模型安全，因為 Group A+ 目前已有 FinBERT、全球市場特徵與 signal alignment 架構，可以把字典情緒放在 shadow/輔助層做交叉驗證。

## 已導入改善

- 新增 `group_a_plus/integrations/lm_dictionary_sentiment.py`
  - 支援 Loughran-McDonald 字典載入。
  - 從 `report/group_a_plus/latest/watchlist_news.json` 擷取新聞標題與摘要。
  - 輸出 positive/negative/uncertainty/litigious 計數、`sentiment_score`、`risk_score`。
  - 固定標記 `active_allocation_impact: none`，不直接改配置。
- 更新 `group_a_plus/integrations/signal_alignment.py`
  - 新增 `lm_dictionary_sentiment` shadow source。
  - 只有 `status == "ok"` 才納入可用來源。
  - 強度上限壓低至 `0.5`，避免字典訊號蓋過 FinBERT 與既有市場訊號。
- 更新 `group_a_plus/operations/daily_signal.py`
  - daily signal 會附帶 `lm_dictionary_sentiment` snapshot。
  - signal alignment 會顯示該來源狀態。
- 新增測試
  - `tests/test_lm_dictionary_sentiment.py`
  - `tests/test_signal_alignment_lm_dictionary.py`
- 小幅更新 `tests/test_group_a_plus_daily_signal_v2.py`
  - 對齊現有高風險動態 trim 行為；不是 LM 字典造成的配置改變。

## 2026-07-01 實測結果

執行：

```bash
.venv/bin/python -m pytest -q tests/test_lm_dictionary_sentiment.py tests/test_signal_alignment_lm_dictionary.py tests/test_group_a_plus_daily_signal_v2.py tests/test_group_a_plus_latest_strategy.py
```

結果：

```text
39 passed
```

產生 daily signal：

```bash
PYTHONPATH=. .venv/bin/python group_a_plus/operations/daily_signal.py --as-of 2026-07-01 --output results/group_a_plus_live_signal_v2_20260701_lm_shadow.json
```

結果摘要：

- `lm_dictionary_sentiment.status`: `no_dictionary_hits`
- `lm_dictionary_sentiment.active_allocation_impact`: `none`
- `signal_alignment.sources` 已出現 `lm_dictionary_sentiment`
- 目前 watchlist news 主要是中文內容，英文 LM 字典命中不足，因此本次不產生方向訊號。
- 目標權重未因 LM 字典情緒改變。

2026-07-01 shadow output 目標權重：

```text
0050.TW   0.694717
00631L.TW 0.072139
CASH      0.233143
```

## 建議

保留此改善在 shadow 層。短期用途是監控英文財經新聞或外部摘要中的極端風險詞，作為 FinBERT 訊號的低權重交叉檢查。

不建議把 StocksProject 的舊模型、資料下載器或硬編碼流程直接導入 Group A+。
