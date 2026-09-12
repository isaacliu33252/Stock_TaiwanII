# Group A+ 2026-08-16 Session 完整交接索引

**日期**：2026-08-16
**涵蓋範圍**：10篇新論文審查(含4次額外實測、1次意外的資料品質bug發現與修正、1次嚴重的回測look-ahead bug發現與修正)、每日資料更新pipeline、11個偏舊美股ticker補抓並正式排程、GatedLinear-lite shadow diagnostic接入production pipeline。

## 一句話摘要

今天審查了10篇論文（3篇選擇權定價、1篇保險精算HJB、1篇橫斷面選股alpha挖掘、1篇財報DCF預測、1篇歐盟碳權極值圖模型——皆判定架構不匹配不適用；1篇drawdown風控方法論判定可用並產出實際回撤警戒表；1篇SOFR利率衍生品不適用但追加實測entropic凸優化配置全面負面；1篇GatedLinear通用時序預測判定完整架構不導入，但抽出drawdown H=20預測訊號接進shadow diagnostic；1篇加密交易所ADL機制判定不適用但抽取「漸進vs二元切換」洞察實測出具體regime分野）。過程中意外在`FinRL/data/stock_data.db`的`ohlcv`表發現3個未回溯調整的真實公司行動價格斷點，追查影響範圍並修正了一個受污染最深的既有GJR-GARCH評估。GatedLinear的經濟效益驗證中還發現並修正了一個更嚴重的**回測look-ahead bug**(用當天收盤價算出的drawdown決定當天持倉、套用當天報酬率)，修正後結論完全反轉(見下方第9項)。session中出現多次自我修正，全部誠實記錄過程而非只留最終結論。另外執行了每日資料更新pipeline、補齊並正式排程11個先前只能手動補抓的美股ticker。

## 各主題個別記錄索引

### 論文審查（依序）

1. **[[project_2608_00127_drawdown_bootstrap_calibration_20260816]]** — 2608.00127《Drawdown Risk Beyond Brownian Motion》判定方法論可用。用golden1_0531/a2118真實391天日報酬跑stationary block bootstrap，產出回撤警戒表（目前MDD在15.5~21.2百分位，遠未到90/95警戒線）；追加用00631L完整12年真實歷史驗證方法論，過程中發現並修正了ohlcv資料斷點bug（見下）。完整記錄：`docs/HANDOFF_2608_00127_DRAWDOWN_RISK_BEYOND_BROWNIAN_MOTION_GROUPA_PLUS_20260816.md`。

2. **[[project_ohlcv_unadjusted_corporate_actions_and_gjr_garch_rerun_20260816]]** — 意外發現的資料品質bug。`ohlcv`表有3個未回溯調整的真實公司行動斷點（0050.TW 2014-01-02分割、00631L.TW 2015-01-05反向合併、00632R.TW 2024-12-02反向合併）。查證影響範圍：**production的switch policy跟5次危機回測都不受影響**；`gjr_garch_oos_forecast_quality_00631l.py`確認受污染，用修正後資料重跑，尾部顯著性從臨界值(p=0.056)變明確不顯著(p=0.768)，實務結論(不採用GJR做尾部風控)不變但更站得住。過程中兩次自我修正：(a) 一度誤判`evaluate_00631l_crash_risk_alert_quality.py`受污染，追查後推翻；(b) 一度誤判GJR-GARCH三篇既有記錄互相矛盾，追查後發現08-13記錄本身就已經記載過同樣的p值波動並得出「效果太脆弱不該採信」的結論，不是矛盾是自己沒讀完整。完整記錄：`docs/HANDOFF_00631L_OHLCV_UNADJUSTED_CORPORATE_ACTIONS_DATA_BUG_20260816.md`。

3. **[[project_2607_29220_ivs_diffusion_arbitrage_refinement_closed_20260816]]** — 2607.29220《IVS diffusion+SAAM refinement》判定不適用（選擇權，Group A+無選擇權部位）。但使用者要求實測「diffusion情境生成」這個手法能否脫離選擇權套用在Group A+自己的regime特徵（0050的ma_gap/drawdown）——**實測結果全面更差**：RMSE/MAE、CRPS(分布預測品質)、90%預測區間校準涵蓋率(僅35~43%，目標90%)三個指標全部輸給persistence/ridge/Gaussian-AR等簡單基準，證實了「殺雞用牛刀」的先驗判斷。完整記錄：`docs/HANDOFF_2607_29220_IVS_DIFFUSION_ARBITRAGE_REFINEMENT_GROUPA_PLUS_20260816.md`。

4. **[[project_2607_26642_alphaschema_llm_alpha_mining_closed_20260816]]** — 2607.26642《AlphaSchema》判定不適用。核心機制需要橫斷面選股宇宙（CSI300~300檔排名）才能定義IC/RankIC，Group A+只有4檔可交易ETF，是問題形狀不同構。次要評估過schema搜尋meta方法論套用在switch規則設計上是否划算——判斷不划算，未做實測。完整記錄：`docs/HANDOFF_2607_26642_ALPHASCHEMA_LLM_ALPHA_MINING_GROUPA_PLUS_20260816.md`。

5. **[[project_2607_21687_insurer_surplus_hjb_closed_20260816]]** — 2607.21687《保險公司盈餘管理HJB最優控制》判定不適用。Group A+無保險負債，是離散regime-switching框架非連續時間隨機控制，問題結構不同構；論文自己也聲明數值範例未校準真實資料。完整記錄：`docs/HANDOFF_2607_21687_INSURER_SURPLUS_MANAGEMENT_HJB_GROUPA_PLUS_20260816.md`。

6. **[[project_2607_19030_gasoil_illiquid_options_closed_20260816]]** — 2607.19030《用流動布蘭特選擇權市場推算非流動柴油選擇權曲面》判定不適用（選擇權）。今天第三篇選擇權論文，直接重用已查證的「Group A+無選擇權部位」事實快速排除。完整記錄：`docs/HANDOFF_2607_19030_GASOIL_ILLIQUID_OPTIONS_BRENT_BENCHMARK_GROUPA_PLUS_20260816.md`。

（2606.31251 GAMLSS/ZAGA：使用者今天問起，確認是昨天(08-15)已完成的審查，只做確認未重新分析，詳見[[project_2606_31251_gamlss_zaga_regime_comparison_20260815]]。）

7. **[[project_2608_10711_sofr_indifference_pricing_and_convex_allocation_test_20260816]]** — 2608.10711《SOFR衍生品indifference pricing》判定不適用（無SOFR曝險）。追加實測抽取entropic risk measure凸優化配置手法取代switch規則，四組風險趨避參數ρ=5/15/40/100全面輸給既有Sharpe/MDD，根因是情境集合純回顧性缺前瞻性。完整記錄：`docs/HANDOFF_2608_10711_SOFR_INDIFFERENCE_PRICING_GROUPA_PLUS_20260816.md`。

8. **2608.11327《Long-Horizon Forecasting of Complete Financial Statements》** — 判定不適用（DCF估值/財報預測，Group A+全ETF無對應決策變數），沒有可抽取的通用手法可測試，未留獨立memory。

9. **[[project_2606_17723_eu_carbon_tail_dependence_closed_20260816]]** — 2606.17723《Tail Dependence in EU Carbon Markets》判定不適用（Group A+無歐盟碳權/歐洲能源曝險）。核心技巧(Hüsler-Reiss極值圖模型，尾部依賴網路vs平均依賴網路結構反轉)理論上可轉用到Group A+跨市場訊號panel找危機時真正核心的外部訊號，但Python無現成套件、需從零刻懲罰概似求解器，成本評估後判定不划算，未實測（跟GatedLinear不同，這次是先估算成本再決定不測，不是架構不匹配）。完整記錄：`docs/HANDOFF_2606_17723_EU_CARBON_TAIL_DEPENDENCE_GROUPA_PLUS_20260816.md`。

10. **[[project_2607_09537_gatedlinear_drawdown_forecast_shadow_20260816]]** — 2607.09537《GatedLinear》通用時序預測架構（tri-basis+gate）。判定完整架構不導入（H=1/5/10大多退化成persistence或跟普通ridge打平；H=20的ma_gap「改善」被證實是均值回歸假象，gate權重全為0）。drawdown在H=20視野下有真實且穩健的RMSE邊際（同時打贏persistence/常數均值/ridge三個基準，3/3子視窗全勝，gate權重非退化）——已接進daily pipeline做shadow diagnostic純觀察（`gatedlinear_drawdown_forecast_shadow_log`步驟）。**⚠️追加經濟效益驗證(把預測拿去做0050/00679B防禦切換決策)初版發現一個嚴重的look-ahead bug**：`defensive = drawdown.loc[dt] < threshold` 用當天收盤價算出的drawdown決定「當天」持倉、又套用「當天」報酬率，等於用未來(對交易當下而言)資訊回頭避開當天崩盤，真實交易不可能做到。初版(帶bug)誤判「naive當下值規則完封forecast規則」；用`signal.shift(1)`修正後在4個獨立視窗(391天production+2018+2020+2022)共24組threshold測試，**結論完全反轉：forecast贏16組(67%)，naive只贏8組**。但修正後兩者都沒有穩健打贏單純buy&hold 0050，所以「不接production決策、維持shadow純觀察」的最終建議不變，只是理由從「naive完封forecast」更正為「兩者都不夠穩健」。這個bug已寫成獨立可重用的feedback memory：[[feedback_lookahead_bug_same_day_signal_decision]]。完整記錄：`docs/HANDOFF_2607_09537_GATEDLINEAR_GROUPA_PLUS_20260816.md`（§3d保留原始錯誤結論、§3d-korrektur完整記錄修正過程，未覆蓋原文）。

11. **[[project_2603_15963_risk_based_auto_deleveraging_graduated_test_20260816]]** — 2603.15963《Risk-Based Auto-Deleveraging》判定不適用（Group A+不是交易所，無多帳戶分配強制減倉問題）。抽取核心洞察「漸進式water-filling減倉優於一刀切全額平倉」(已在Hyperliquid真實ADL事件實證)套用在Group A+現有二元switch規則——設計graduated(防禦權重隨drawdown線性爬升)vs binary(現有硬切換代理)對照，用嚴格因果決策(`shift(1)`，吸取稍早GatedLinear實驗的look-ahead bug教訓，這次一開始就正確實作)。**結果：緩慢累積型壓力(2018/2022/391天production)graduated穩定勝binary 3/4(跨stress_range 0.10~0.20參數穩健)，但2020 COVID閃崩binary在全部4組參數下完封graduated**——具體可解釋的regime分野：漸進式風控只在壓力漸進累積時有優勢，瞬間閃崩時binary硬切換更好。兩種機制都沒穩定打贏buy&hold，不建議promote，但這個regime分野發現本身值得記錄。完整記錄：`docs/HANDOFF_2603_15963_RISK_BASED_AUTO_DELEVERAGING_GROUPA_PLUS_20260816.md`。

### 資料維運

- **每日資料更新pipeline**：跑了`run_ncf_daily_pipeline.py --only-refresh`，18步驟全部成功，0個missing files。OHLCV已是最新（跑pipeline當天為週日非交易日，資料庫已有到最近交易日週五的資料，這是預期落差不是缺口）。
- **11個偏舊美股ticker手動補抓**：AMD/ASML/AVGO/DX-Y.NYB/EWT/HYG/NVDA/SHY/^HSI/^KS11/^N225全部更新到最新交易日。**已解決**：使用者確認後已正式加入`fetch_cross_market_ohlcv.py`的`DEFAULT_TICKERS`，往後每日排程自動更新，不再需要手動補抓。`tests/test_fetch_cross_market_ohlcv.py`用動態集合比對，加入後測試仍pass。
- **新增shadow diagnostic步驟**：`gatedlinear_drawdown_forecast_shadow_log`已接進`run_ncf_daily_pipeline.py`的`BEST_EFFORT_STEP_NAMES`，逐日記錄0050.TW drawdown的H=20預測值到`results/group_a_plus_gatedlinear_drawdown_forecast_shadow_log.jsonl`，純觀察不影響任何決策。新增`group_a_plus/integrations/gatedlinear_drawdown_forecast_shadow_log.py`+`scripts/run/build_group_a_plus_gatedlinear_drawdown_forecast_shadow_log.py`+對應測試(4項全過)，`tests/test_run_ncf_daily_pipeline.py`既有步驟清單斷言已同步更新(2項原失敗測試已修復，全部21項通過)。

## 下次接手最容易誤判的幾件事

1. **`ohlcv`表本身沒有修正那3個公司行動斷點**——只在個別分析腳本(2608.00127的block bootstrap、GJR-GARCH重跑)做了本地修正，資料庫原始資料依然是斷點狀態。任何未來要對0050.TW/00631L.TW/00632R.TW算跨越2014-01-02/2015-01-05/2024-12-02的連續報酬率/波動度/回撤，都要先檢查回溯調整。
2. **不要用「單日報酬超過某個門檻」自動判定公司行動斷點**——今天測試過會誤傷2018-10-11/2020-03等真實崩盤日，必須人工核對（同日相關ticker反向對稱變動是好方法，例如00631L跟00632R同日方向相反的大幅波動通常是真實市場事件不是資料錯誤）。
3. **不要只憑「載入區間是否跨越斷點」判斷某腳本是否受污染**——要追到實際使用載入資料的函式邏輯（`evaluate_00631l_crash_risk_alert_quality.py`就是一個反例，寬鬆載入範圍不代表真的用到那段資料）。
4. ~~11個美股ticker(AMD/NVDA/ASML等)不在每日自動排程內~~ **已解決**（見上方資料維運段落）——已加入`DEFAULT_TICKERS`，往後自動更新。
5. **今天3篇「選擇權相關」論文的排除都重用同一個已查證事實**（Group A+無選擇權部位，00631L/00632R是台指期貨為主的槓桿/反向ETF）——來源是2608.12493審查時的WebSearch查證，未來遇到選擇權曲面/定價類論文可以直接引用，不需要重新查證。
6. **任何「用當天特徵值決定當天持倉、套用當天報酬率」的回測程式碼都要立刻檢查look-ahead**——這是今天最嚴重的方法論錯誤，已在GatedLinear經濟效益驗證中犯過一次並先把錯誤結論(「naive完封forecast」)回報給使用者好幾輪才被抓到。正確作法一律用`signal.shift(1)`(或更早)決定持倉。**結果好到不合理時，第一步該查這個，不是急著寫結論或加更多out-of-sample視窗**——OOS驗證只會把同一個bug複製到更多視窗，不會自動發現問題，因為bug是結構性的不是單一視窗雜訊。詳見[[feedback_lookahead_bug_same_day_signal_decision]]。
7. **跨文件比較golden1_0531/a2118 Sharpe數字前要先核對比較窗口起點**——今天發現SOFR/entropic實驗(H=60 lookback，比較窗口從2025-04-10才開始)跟GatedLinear實驗(完整391天2025-01-02起)報的golden1/a2118 Sharpe數字差很大(2.658/2.916 vs 1.80/1.94)，不是bug只是窗口不同，但不可直接並列引用。
8. **`switch_deriv_ma20_dd5_score1_hold5`(a2118正式規則)在2018/2020/2022完全等於golden1_0531**——因為衍生品籌碼資料在這幾年不存在、規則從未觸發，這代表a2118的正式規則在這些年度無法真正回測（若需要更早年度的a2118對照組，只能退而求其次用不需籌碼資料的`switch_ma20_dd5_hold5`純價格規則，且它在這幾年只比golden1好一點點，是「正常可信」量級的參考值）。
