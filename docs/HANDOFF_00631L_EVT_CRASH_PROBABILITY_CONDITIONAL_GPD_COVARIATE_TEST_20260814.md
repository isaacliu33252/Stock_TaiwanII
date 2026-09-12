# 00631L EVT Crash Probability — Covariate-Conditional GPD Scale Test (2506.17549 follow-up)

**日期**：2026-08-14
**背景**：審查論文2506.17549（Bayesian GPD Regression）後判定不直接導入（look-ahead疑慮+隨機切分瑕疵），但識別出一個真實立足點：`scripts/evaluate/evaluate_00631l_evt_crash_probability.py`——2026-07-12建的walk-forward EVT/POT crash機率估計器，docstring記錄是「這個session的EVT/tail-risk線裡最乾淨的校準結果」，但scale參數在每個504天窗口內是常數（unconditional）。論文的核心技巧（讓GPD scale隨covariate動態變化，Cauchy prior正則化）理論上有機會改善這個既有模型的校準。

**結論：測試後判定不採用，維持既有unconditional模型不變。**

## 測試設計

新增獨立測試腳本 `scripts/evaluate/evaluate_00631l_evt_crash_probability_conditional.py`（不接入production，純驗證用）：

- Covariate：00631L自身trailing 21日realized volatility，用`shift(1)`確保day t的covariate只用day t-1及之前的報酬，修正論文原本「用當天報酬算當天波動度去解釋當天crash」的同期性瑕疵。
- 標準化：用每次refit的training window自己的mean/std做z-score，凍結後套用到當下covariate，不會有未來資訊洩漏（修正論文「隨機80/20切分」的瑕疵，維持base script原本的walk-forward紀律：每21天refit、只用t-1以前資料）。
- 模型：`e_i ~ GPD(0, σ_i, ξ)`，`log(σ_i) = β0 + β1·vol_std_i`，MAP估計（scipy.optimize, Nelder-Mead，論文用BFGS但本例的hard support constraint在L-BFGS-B下數值不穩定，換成Nelder-Mead後才收斂到非退化解）。
- Prior：β0/β1用標準Cauchy(0,1)，ξ用truncated Cauchy(0,1)（論文Table 2裡表現最好的prior選擇）。
- 評估指標：跟既有unconditional模型完全一樣——corr(crash_prob, 未來20日最大跌幅)、以及p90/95/99/99.5門檻觸發時的實際後續跌幅 vs baseline。

## 結果

| | corr(crash_prob, fwd 20d min ret) | p99觸發時實際後續跌幅 vs baseline |
|---|---|---|
| unconditional（既有，不變） | **-0.081**（正確方向） | -0.124 vs -0.043（觸發時確實跌更深） |
| conditional（新測試） | **+0.076**（方向反了） | -0.022 vs -0.043（觸發時反而跌更淺） |

conditional版本不只沒有改善，**相關係數符號整個反過來**——標記為高風險的日子，後續20天實際跌幅反而比baseline更淺。已排除bug可能性（support constraint、causal covariate、window-scoped標準化都檢查過，優化收斂到合理非退化解，非degenerate輸出）。

## 為什麼會這樣
00631L自身的realized volatility本來就跟「即將出現大跌」高度共線（大跌前後波動度本就會被推高），covariate沒有帶來新資訊；而每個refit窗口只有約20-50個exceedance的小樣本下，多估一個β係數（3參數 vs 原本2參數：scale, ξ）純粹增加估計噪音，把原本乾淨的unconditional校準做壞。跟本專案已驗證過的教訓同源：[[project_gjr_garch_oos_rejected_20260801]]（小樣本下的波動度condition機制OOS不穩健）、adaptive lookback window的base-rate假象。

## Do Not Do
- 不要把conditional版本接到production或`00631l_evt_crash_gate_derisk`的de-risk gate上——corr符號已經反了，接上去只會讓既有（雖然也未promote但calibration乾淨的）unconditional訊號變差。
- 不要因為Cauchy prior在論文原始情境（印度Nifty50、大樣本）表現好，就假設同一套正則化在Group A+這種小樣本(每窗口20-50個exceedance)、少covariate的情境下也會有幫助——這次實測證明「先驗選得穩健」救不了「樣本量撐不起額外參數」的根本問題。

## Next Step
無。`evaluate_00631l_evt_crash_probability.py`（unconditional）維持現狀不動，新腳本純作記錄保留，不需要後續調參或重跑。若未來要重新處理00631L尾部風險校準，優先方向是改善既有unconditional模型的refit頻率/窗口長度，而非加covariate。
