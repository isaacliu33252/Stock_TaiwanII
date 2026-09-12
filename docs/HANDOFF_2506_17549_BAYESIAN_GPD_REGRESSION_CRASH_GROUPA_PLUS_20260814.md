# 2506.17549 Predicting Stock Market Crash with Bayesian GPR — Group A+ 適用性審查

**日期**：2026-08-14
**論文**：Das (2025), *"Predicting Stock Market Crash with Bayesian Generalised Pareto Regression"*, arXiv:2506.17549v1
**結論**：**不導入 Group A+ / a2118（最新策略）**，判定 research_only。

## 論文方法論摘要

- 對印度Nifty50指數的極端負報酬樣本（跌幅>2%，佔全樣本4.6%，其中11.6%跌幅>5%）建立Bayesian Generalised Pareto Regression：GPD的scale參數σ設為當日波動度covariate的log-linear函數 `log(σ_i) = x_i^T β`，shape參數ξ在所有樣本間共用。
- 波動度covariate來源：Nifty自身empirical volatility（EWMA, k=21, α=0.9）、Garman-Klass intraday volatility、S&P500與黃金的volatility，用來捕捉本地與全球風險驅動因子（spillover/flight-to-safety）。
- 比較4種Bayesian regularization prior（Cauchy、Lasso/Laplace、Ridge/Gaussian、Zellner's g-prior），MAP估計。模擬與實證都顯示Cauchy prior在RMSE/AIC/BIC上表現最好。
- 實證結論：`P(跌幅>5% | 已跌>2%)`隨波動度呈非線性上升，波動度10th percentile時crash機率<5%，90th percentile時>65%；S&P500與黃金波動度都顯著提升印度市場的crash機率（全球溢出效應）。

## 為何不適用 Group A+

### 1. 方法論本身有瑕疵
- **同期性/look-ahead疑慮**：論文的EWMA波動度公式 `σ²_t = α·s²_{t-1} + (1-α)·r²_t` 把**當天報酬r_t**直接放進當天波動度估計，再用這個波動度去解釋當天的極端跌幅`y_t=|r_t|`——這是同期關係（contemporaneous），不是真正可在盤前取得的預測變數。開盤前無法拿到這個已經包含當天已實現報酬的波動度數字。
- **隨機train/test切分**：時間序列資料卻用「隨機80/20分割」（非walk-forward），訓練集可能混入測試期之後的觀測值，Table 2的RMSE 1.58等OOS指標有資訊洩漏風險，可信度打折。

### 2. 跟既有機制方向重複、且既有機制更嚴謹
`group_a_plus/integrations/tail_conformal.py` 已經是production等級的「用當前市況估計極端下檔機率」機制——用Adaptive Conformal Inference（`_walk_forward_aci_alpha`，Gibbs & Candes 2021 single-rate ACI，scoped precursor to arXiv:2606.18199 DtACI）搭配252天walk-forward calibration window，估計`00631L.TW`的forward lower-tail bound與`P(MDD<-8%)`，正是論文想做的同一件事（"用當前波動狀態condition尾部風險機率"），但方法論更嚴謹（線上自適應校準、明確coverage保證），且已實際接入a2118的pre-trade guard運作中（見`results/group_a_plus_a2118_predict_20260817`一類輸出的`tail_conformal`欄位）。

### 3. 同類機制已測試否決過
[[project_gjr_garch_oos_rejected_20260801]]——GJR-GARCH做「波動度→尾部風險」預測，正規OOS驗證後判定「in-sample顯著≠預測有用」而否決，[[project_gjr_garch_oos_forecast_quality_00631l_20260813]]重驗後再次確認結論不穩健。本論文本質上是同一類「波動度condition尾部風險」模型，且方法論嚴謹度（隨機切分、同期變數）還不如已被否決的GJR-GARCH線。

### 4. 市場不同（次要）
印度Nifty50 vs. 台股TAIEX，波動結構與極端事件驅動因子不同，論文參數無法直接套用，但這點是次要問題，前3點已足夠關閉。

## 唯一可能有參考價值的細節
Cauchy prior在heavy-tail regression中比Lasso/Ridge/g-prior更穩健的統計工具選擇——若未來重做任何Bayesian尾部模型可參考，但不構成"導入"理由，屬於工具箱筆記而非策略優點。

## Do Not Do
- 不要為了驗證這篇論文重新用台股資料跑一次GPD regression——既有`tail_conformal.py`已經做得更好，且論文自身方法論有look-ahead疑慮，不值得投入驗證成本。

## Next Step
無。此論文已收手，不需要後續行動。若未來要重新設計Bayesian尾部風險模型，可回頭參考Cauchy prior的regularization選擇作為技術筆記。
