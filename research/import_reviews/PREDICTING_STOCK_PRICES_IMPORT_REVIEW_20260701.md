# predicting_stock_prices 導入評估紀錄 - 2026-07-01

## 來源

- 來源路徑：`C:\Users\isaac\Downloads\predicting_stock_prices-master\predicting_stock_prices-master`
- 目標：評估是否有可導入 Group A+ 最新策略的優點。

## 專案摘要

此專案是早期 Sirajology 教學範例，只有兩個主要腳本：

- `demo.py`
  - 從 CSV 讀日期與價格。
  - 使用 `sklearn.svm.SVR` 的 linear/poly/RBF kernel。
  - 用日期欄位的簡化數字當唯一特徵。
  - 直接預測未來價格並畫圖。
- `challenge.py`
  - Twitter/Tweepy 搜尋公司推文。
  - TextBlob 做正負情緒。
  - 若多數推文正面，再用 Keras 建神經網路預測價格。
  - 但 `predict_prices` 沒有實作，是 coding challenge template。

## 不建議導入的原因

- 使用過時套件版本：`scikit-learn==0.18`、`numpy==1.11.2`、`matplotlib==1.5.3`。
- Google Finance / Twitter API 流程已不適合作為穩定資料源。
- `demo.py` 只用日期序號預測價格，沒有 OHLCV、報酬、風險、交易成本、walk-forward。
- SVR 預測價格線圖容易產生視覺錯覺，不代表可交易 edge。
- `challenge.py` 只是模板，模型函式未完成。
- TextBlob 泛用情緒不適合中文台股新聞，也不如目前 Group A+ 的 FinBERT proxy/model、LM dictionary 與 event attribution。

## 可取概念

只有一個概念可作研究參考：

- 情緒作為模型啟動 gate
  - 原專案建議「若推文多數正面，才跑價格模型」。
  - 這個概念在 Group A+ 中應該改成：情緒只作為 shadow attribution/gating 診斷，不直接下單。

但目前 repo 已經有更完整版本：

- `group_a_plus/integrations/finbert.py`
- `group_a_plus/integrations/lm_dictionary_sentiment.py`
- `scripts/evaluate/evaluate_event_sentiment_attribution_shadow.py`
- `scripts/evaluate/evaluate_direction_magnitude_shadow.py`

## 結論

不建議導入程式或模型。

```text
decision = reject_direct_import
useful_concept = sentiment_gate_reference_only
active_allocation_impact = none
```

目前不需要再為此專案新增策略邏輯。若要保留其概念，已由 event sentiment attribution shadow 覆蓋。
