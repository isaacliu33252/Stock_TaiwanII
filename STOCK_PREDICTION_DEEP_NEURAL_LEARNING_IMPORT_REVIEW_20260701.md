# stock-prediction-deep-neural-learning 導入評估紀錄 - 2026-07-01

## 來源

- 來源路徑：`C:\Users\isaac\Downloads\stock-prediction-deep-neural-learning-master\stock-prediction-deep-neural-learning-master`
- 目標：評估是否有可導入 Group A+ 最新策略的優點。

## 專案摘要

此專案是 TensorFlow/Keras LSTM 股價預測流程，主體包含：

- `stock_prediction_deep_learning.py`
  - 訓練 LSTM。
  - 支援 returns、deltas、trend residual 等目標模式。
  - 會輸出 `model_config.json`、scaler、模型檔、prediction CSV、圖表。
  - v7 模式把方向與幅度拆成兩個模型。
- `stock_prediction_lstm.py`
  - 多版 LSTM 架構。
  - 使用 EarlyStopping。
  - v4/v7 加入 ReduceLROnPlateau。
  - 幅度模型使用 Huber loss。
- `stock_prediction_numpy.py`
  - 下載 Yahoo Finance close price。
  - 依 validation_date 切訓練/測試。
  - 建立 log return、delta、trend residual、direction/magnitude label。
- `stock_prediction_deep_learning_inference.py`
  - 載入模型與 scaler/config。
  - 支援 business day forecast。
  - 支援 magnitude clipping。
  - 支援 stochastic paths，輸出 P10/P50/P90 forecast band。

## 可取概念

這個專案比一般教學 LSTM 範例多幾個值得吸收的工程概念：

1. 方向與幅度拆分
   - v7 用 direction model 預測漲跌機率。
   - magnitude model 預測價格變動幅度。
   - 這比直接預測價格 MSE 更接近 Group A+ / NCF 的方向與幅度治理。

2. Huber loss for magnitude
   - 幅度預測使用 Huber，比 MSE 對極端值更穩。
   - 可作為 NCF/序列 shadow model 的候選評估設定。

3. 推論 config 與 scaler 持久化
   - 每次訓練輸出 `model_config.json`、`min_max_scaler.pkl`、`input_scaler.pkl`。
   - 有助於避免 live inference 與 training preprocessing 不一致。

4. 預測幅度 clipping
   - 用近期絕對變動 percentile 限制預測幅度。
   - 對槓桿 ETF 或高波動環境有治理價值。

5. stochastic forecast band
   - 推論端可產生 P10/P50/P90。
   - 對 Group A+ 更適合轉成風險區間、alert band 或 opportunity/risk shadow，而不是單一路徑價格預測。

6. ReduceLROnPlateau + EarlyStopping
   - 訓練治理比單純 epoch 固定訓練好。

## 不建議直接導入的原因

- 資料來源是 yfinance，與本 repo 既有 DuckDB/台股資料流程不一致。
- 主流程仍偏單一標的價格/差分預測，不是 portfolio allocation。
- validation_date 是單次切分，不是多年度 walk-forward。
- 預測目標主要是 next close/delta，不直接對 H20 AUC、forward drawdown、Sharpe、turnover 或交易成本最佳化。
- 輸出大量圖表與 run folder，若直接導入會增加 repo 噪音。
- Group A+ 目前已有 NCF、TabNet/序列 shadow、signal alignment，不能因為 LSTM 圖表看起來貼合就升級到配置層。

## 與目前 Group A+ 的關係

目前已有：

- NCF 方向訊號與 horizon ensemble。
- 00631L/00632R cross-ticker consistency。
- stock-rnn relative-window shadow benchmark。
- OHLCV relative-window shadow benchmark。
- Monte Carlo stress / opportunity cost / factor lens。

本專案可以補的不是「再訓練一個 LSTM」，而是兩個治理概念：

- direction + magnitude split 的 shadow evaluator。
- stochastic P10/P50/P90 forecast band，轉成 live signal 的風險附註。

## 建議導入方式

建議做，但只做 shadow/evaluation，不進 active allocation。

優先級：

1. 建立 `direction_magnitude_shadow` 評估
   - 使用現有 DuckDB OHLCV，不用 yfinance。
   - 目標：
     - direction: forward return > 0。
     - magnitude: abs(forward return) 或 forward drawdown。
   - loss/metric：
     - direction: AUC/Brier。
     - magnitude: MAE/Huber loss。
   - benchmark：
     - NCF `prob_up_h20`。
     - 現有 OHLCV relative-window HGB。

2. 將 P10/P50/P90 概念導入 live signal 附註
   - 不預測價格。
   - 改成用現有 Monte Carlo 或 NCF 分布產生風險 band。
   - 顯示於 report，用於治理，不直接調倉。

3. 將 magnitude clipping 概念用在模型輸出治理
   - 若某個 advisory 模型的預測變動超過近期波動 percentile，先降權或標記 abnormal。

## 結論

不建議直接導入 LSTM 模型或 yfinance 訓練流程。

建議吸收以下概念到研究/治理層：

```text
direction_magnitude_split = useful_for_shadow
stochastic_forecast_band = useful_for_reporting
magnitude_clipping = useful_for_model_governance
active_allocation_impact = none
```

目前不應影響 Group A+ 實際配置。若要試導入，第一步應是新增 shadow evaluator，而不是加入 live trading overlay。

## 試導入結果

已完成 shadow/evaluation 層導入：

- 新增 `scripts/evaluate/evaluate_direction_magnitude_shadow.py`
  - 使用既有 DuckDB OHLCV 與 NCF panel。
  - 沿用 OHLCV relative-window 特徵。
  - direction model：`HistGradientBoostingClassifier`。
  - magnitude model：`GradientBoostingRegressor(loss="huber")`。
  - magnitude prediction 使用近期訓練 target percentile clipping。
  - 輸出 signed-return residual P10/P50/P90 作為 uncertainty band。
- 新增 `tests/test_evaluate_direction_magnitude_shadow.py`

測試：

```bash
.venv/bin/python -m pytest -q tests/test_evaluate_direction_magnitude_shadow.py tests/test_evaluate_stock_rnn_relative_window_shadow.py
```

結果：

```text
9 passed
```

實測輸出：

```text
results/direction_magnitude_shadow_latest_20260701.json
```

實測摘要：

```text
feature_rows                 310
feature_count                401
baseline prob_up_h20 AUC     0.9004
direction model AUC          0.5910
AUC delta vs baseline       -0.3094
baseline Brier               0.2614
direction model Brier        0.0824
magnitude MAE                0.0962
signed return MAE            0.1026
residual P10/P50/P90        -0.0238 / 0.0857 / 0.1911
promotion_decision           research_only
active_allocation_impact     none
```

判讀：

- direction/magnitude split 的方向排序仍遠低於現有 NCF `prob_up_h20`。
- Brier 改善代表它可能有機會作為校準/風險報告參考。
- 不足以進 active allocation，也不應影響目前 Group A+ 權重。
