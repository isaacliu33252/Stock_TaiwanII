# stock_predict_with_LSTM 導入評估紀錄 - 2026-07-01

## 來源

- 來源路徑：`C:\Users\isaac\Downloads\stock_predict_with_LSTM-master\stock_predict_with_LSTM-master`
- 目標：評估是否有可導入 Group A+ 最新策略的優點。

## 專案摘要

此專案是教學型股票 LSTM 預測範例，核心檔案很少：

- `main.py`
  - 固定 CSV 輸入。
  - 使用 `time_step=20` 的滑動序列。
  - 預測未來 `predict_day=1`。
  - 可同時預測多個 label，預設為 low/high。
  - 使用均值/標準差標準化。
  - 支援 train/valid split、early stopping、checkpoint、簡單 log/plot。
- `model/model_pytorch.py`
  - LSTM + Linear regression head。
  - MSE loss。
  - validation loss early stopping。
- `model/model_keras.py`
  - Keras LSTM + Dense。
- `model/model_tensorflow.py`
  - TensorFlow 1.x LSTM。

## 可取概念

可吸收的概念：

- 固定長度序列窗口。
- 多目標 high/low 同時預測。
- early stopping 與 checkpoint。
- 訓練過程記錄。
- 避免單一 close 價格，把 OHLCV 也納入序列。

## 不建議直接導入的原因

- 主目標是價格 MSE，不是 Group A+ 關心的 H20 方向、drawdown、Sharpe、turnover、交易成本或配置穩定性。
- 使用單一 CSV 範例，沒有台股 ETF walk-forward 驗證。
- TensorFlow 版本固定在 `tensorflow==1.15`，不適合現在專案。
- 預設 `train_data_rate=0.95` 且 validation 從訓練資料切出，缺少嚴格 walk-forward 防洩漏設計。
- 直接預測 high/low 容易產生視覺上貼合、但交易上不可用的結果。
- 這類序列窗口概念已在本專案先前的 stock-rnn 匯入評估中以更安全方式測過。

## 與現有 Group A+ 的重疊

本 repo 已有：

- `scripts/evaluate/evaluate_stock_rnn_relative_window_shadow.py`
  - close relative-window shadow benchmark。
  - OHLCV relative-window shadow benchmark。
  - TimeSeriesSplit + gap。
  - 與 NCF `prob_up_h20` baseline 比較。
- `STOCK_RNN_IMPORT_REVIEW_20260630.md`
  - 已記錄 relative-window 與 OHLCV window 評估結果。

既有 OHLCV relative-window 測試結果：

```text
baseline prob_up_h20 AUC      0.9004
OHLCV relative-window HGB AUC 0.5910
promotion_decision            research_only
active_allocation_impact      none
```

這代表 LSTM 類序列窗口目前還沒有足夠證據勝過現有 NCF 方向訊號。

## 結論

不建議直接導入 `stock_predict_with_LSTM` 的模型、訓練流程或 TensorFlow/Keras/PyTorch 實作。

建議保留為研究參考，不進 active strategy：

```text
status = research_reference_only
active_allocation_impact = none
```

若未來要延伸，較合理方向不是搬 LSTM，而是新增一個更嚴格的 shadow 評估：

- 以目前 DuckDB OHLCV 為資料源。
- 使用 walk-forward。
- 目標改為 forward drawdown / forward gain / H20 direction。
- 與 NCF、signal alignment、現有 OHLCV relative-window baseline 比較。
- 只有在多年度 OOS 明顯提升後，才考慮導入 advisory 層。

## 本次處置

本次只做評估與紀錄，沒有修改 Group A+ active allocation。
