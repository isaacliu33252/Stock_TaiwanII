# 2608.10410 Objective-Oriented Quantitative Investment (OOQI) — Group A+ 適用性審查 + 研究史Search-Width Deflation回顧

**日期**：2026-08-16
**論文**：Zhang (2026), *"Objective-Oriented Quantitative Investment: A Specification-Driven Framework for Automated Synthesis of Trading Strategy Pipelines"*, Shanghai Liangbai Technology Co., Ltd.（獨立作者，揭露利益衝突：用自家生產策略做定性診斷）
**結論**：**核心哲學已經在Group A+實踐中，不導入重型自動化框架，但借用一個具體統計工具做了project自己的研究史回顧驗證。**

## 1. 論文核心

- 批評現有自動化量化研究（AutoML/NAS/RL選股/LLM-agent research loop）全部在優化單一純量指標（Sharpe/IR/IC），但專業投資人真正要的是「身份」（identity）——純選股alpha、不含style曝險、空頭時有韌性、換手率在預算內。
- 提出Objective-Oriented Quantitative Investment (OOQI)：把策略pipeline建模成~8.8×10⁸個候選組合的typed design space（9個stage×多個module），把投資人需求形式化成clause language（8大類、30+條款，hard/soft語意+優先序），用compiler在feasible set內搜尋並優化。
- 核心統計貢獻：**search-width deflation**——證明在N個候選組合裡搜尋時，即使真相是「沒有一個組合真的滿足要求」，隨著N增加，「看起來滿足」的機率會指數逼近1（Proposition 3），因此報告satisfaction rate時必須揭露搜尋寬度N並做deflation校正。
- 合成市場demo：32個pipeline組合，result-oriented選擇拿到最高in-sample IR但只滿足25%的規格；specification-driven選擇滿足100%規格但付出5.5% IR代價——證明兩種paradigm會選出不同策略。
- 80頁附錄含NP-hardness證明（3-SAT reduction）、Galois connection對偶、e-process anytime-valid certification、Hadamard well-posedness inverse-problem理論等。
- **論文自身限制（作者誠實揭露）**：只有合成資料demo，"no real-data alpha, no production validation"；作者是獨立顧問公司，用自家生產策略做定性診斷（利益衝突已揭露）。

## 2. 為何核心哲學不需要「導入」——已經在被真實事故驗證過的實踐中

論文最重要的主張（Proposition 1：result-oriented選擇會系統性挾帶style曝險而非真alpha）正是這個session稍早**AlphaZeroBeta factor attribution**（2607.18001，2026-08-11）直接驗證過的東西——golden1_0531的78%年化報酬幾乎全是MKT beta，沒有顯著殘差alpha。

Group A+既有的`GROUP_A_PLUS_SIGNAL_VALIDATION_CHECKLIST_20260723.md`（8-9項檢查清單：崩盤期條件式檢查、worst-case perturbation robustness、base-rate/mean-bias拆解、多年資料涵蓋率陷阱等）本質上就是這篇論文clause language想形式化的東西——而且是被golden1_0531漂移bug、A21.19假訊號等真實事故逼出來的，不是紙上談兵。

## 3. 為何不導入重型框架

論文的8.8×10⁸組合design space、NP-hardness證明、Bayesian compiler，是為**大規模自動化搜尋**設計（AutoML規模）。Group A+的機制篩選是**人工+AI逐一深度驗證**（這個session一天測了6-7篇論文），不是海量自動組合搜尋，套用整套compiler機械是殺雞用牛刀。且論文本身只有合成資料demo，無real-data驗證。

## 4. 借用的具體工具：把search-width deflation套用在Group A+自己的研究史

論文Proposition 3的公式：若每次搜尋在純雜訊下有q機率「看起來顯著」，N次獨立搜尋後，「至少一個看起來滿足」的機率 = 1-(1-q)^N，趨近1速度隨N指數上升。這剛好可以拿project自己累積的機制測試史來反向驗證：**我們的promotion門檻，是否比雜訊null還嚴格？**

用memory索引檔`MEMORY.md`做粗略統計（關鍵字搜尋，非逐條人工分類，精確度有限）：
- 記憶庫總條目：145
- 廣義「否決/未採用/未promote」關鍵字命中：39（含維持不動/打平/不顯著/推翻等措辭）
- 明確「正式導入production」的**新機制**：僅1個（`project_ncf2330_leadership_score_promotion_20260707`，2026-07-07）

**用Proposition 3反算**：若每次機制測試在純雜訊下有q=0.05機率「看起來顯著」（標準p<0.05門檻），145次獨立測試下，雜訊本身預期產生約145×0.05≈7個假陽性promotion。實際整個可見研究史裡**只有1個機制被正式promote**，遠低於雜訊null預期。

**解讀**：這不代表完全沒有multiple-testing問題（39個明確關閉背後可能還有更多灰色地帶的shadow-only機制未被計入），而是**promotion門檻設得比雜訊null還嚴格**——跟既有的`feedback_strategy_promotion_caution`（策略切換要謹慎，高Sharpe不代表更好）、崩盤期條件式檢查、walk-forward驗證疊加起來的效果吻合：這套流程系統性地壓制假陽性，比論文Proposition 3警告的失敗模式（搜尋越多假陽性越多）還要保守。

**精確度提醒（初版）**：145條目不是每一條都是「機制候選測試」，有些是bug修復/流程改進/純基礎設施，真正的分母可能是80-100個候選機制而非145個；但即使用較小分母，1個promote對雜訊null的落差依然懸殊。這是一個order-of-magnitude的檢查，不是嚴謹統計檢定。

## 5. 修正版：逐條人工分類後的真實數字（同日追加）

初版用關鍵字搜尋粗算「145條僅1個promote」的結論**過度樂觀**，原因是關鍵字搜尋漏掉了真正的promotion案例（例如`2020 switch rule fix`未被抓到），且分母（145）遠大於真正的候選機制數。逐條人工分類146條記憶（排除header後line 3-148）後：

- **真正屬於「機制/論文候選測試」的條目**（排除bug修復、基礎設施、feedback、純參考索引、狀態摘要等）：約**69條**
  - 明確拒絕/未promote：約61條
  - Shadow-only（既非拒絕也非promote）：約5條
  - **正式promote到production**：**2條明確**（`project_ncf2330_leadership_score_promotion_20260707`、`project_2020_switch_rule_fix_promotion_ready_20260706`）+ 1條用詞模糊可能算（`project_ncf_2330_tsmc_stock_model_20260703`寫「尾部風險唯一有效」）

**用q=0.05對69次獨立測試反算Proposition 3**：雜訊null預期假陽性promotion數 ≈ 69×0.05 ≈ **3.45個**。實際promote數：**2-3個**——跟null預期在同一個數量級，**不是像初版關鍵字搜尋暗示的「遠低於雜訊null」**。

**修正後的誠實結論**：這個project的機制篩選紀律確實嚴格（拒絕率超過95%），但沒有初版粗算暗示的那麼「保守到雜訊都打不進來」。對於少數幾個真正promote的機制，仍然值得回頭用論文的margin/retention/deflation邏輯做二次檢查（現有的walk-forward+崩盤期條件式驗證某種程度上已經在做類似的事），不能單純因為「整體拒絕率很高」就假設通過的少數機制必然是真訊號——這正是初版分析本身犯的錯誤（過度樂觀地推論），修正過程本身就是一次活生生的「不要只憑拒絕率高就放心」示範。

## 6. 對已promote機制做margin/retention二次檢查：2020 switch rule fix（同日追加）

依第5節Next Step的建議，挑最容易驗證的`2020_switch_rule_fix_promotion_ready_20260706`（`momentum_fast_exit_ma_gap_min=-0.08`是2026-07-06三個新增opt-in參數之一）做margin檢查。

**第一次嘗試（自行重現）產生誤導結果，已捨棄**：手動拼湊`_switch_returns`+`FOLDS["2020_covid"]`+`_simulate_regime_curve`寫了一個獨立sweep腳本，結果顯示「有無此guard」在整個-0.05~-0.15範圍內數字一致但**方向與原始promotion紀錄相反**（重現版Sharpe 1.478 < None的1.664，原始紀錄卻是fix讓Sharpe從1.253升到1.512）。判斷是重現腳本的`momentum_fast_exit_ma_gap_min=None`分支處理有bug（可能是`weights_by_regime`重建方式或參數傳遞有誤），**未進一步除錯，直接捨棄，不採用此結果**。

**改用原始研究者(2026-07-06)當時已產出的權威sweep結果**：`results/group_a_plus_momentum_fast_exit_ma_gap_guard_sweep_20260706.json`（腳本`scripts/misc/evaluate_momentum_fast_exit_ma_gap_guard_sweep_20260706.py`），掃過`momentum_fast_exit_ma_gap_min ∈ {none, -0.05, -0.08, -0.10, -0.15}`，涵蓋2008/2011/2015/2018/2020五個歷史危機窗口+live 2025-2026：

- **2020窗口**：`none`與`-0.05`到`-0.15`全部**bit-identical**（Sharpe=1.5123, final_value=1,986,790, fast_exit_dates=["2020-03-26"]全部相同）——guard從未擋下2020-03-26的真訊號，不管門檻多緊多鬆。
- **2008窗口**：`none`允許2008-11-03死貓跳誤觸發(Sharpe=0.402)；`-0.05`到`-0.15`**全部bit-identical**且都正確擋下(Sharpe=0.418)——guard正確發揮保護作用，且在整個測試範圍內結果不變。
- **2011/2015/2018窗口**：guard從未觸發，`none`與所有guard值結果一致（無假訊號可擋）。
- **live 2025-2026**：`-0.05`到`-0.10`一致(final=2,086,287)，`-0.15`才變回跟`none`一樣(final=2,089,815)——差異僅約0.17%，是六個測試窗口中唯一出現門檻敏感度的地方，且差異極小。

**結論**：生產值`-0.08`落在-0.05至-0.15這個**10個百分點寬的穩健區間**正中央，六個窗口的outcome在這個區間內幾乎完全不變（僅live窗口在區間邊緣-0.15處有0.17%的微小鬆動）。用論文Proposition 9的語言：這是一個**deep margin**的promotion，不是踩在刀口上的過擬合選擇。**且這個sweep本身就是原始研究者在2026-07-06 promote前主動做的**（`evaluate_momentum_fast_exit_ma_gap_guard_sweep_20260706.py`），不是這次審查論文才想到要做——再次印證第2節「核心哲學已在實踐」的判斷，這次連論文倡導的margin/retention具體檢查方法，Group A+的既有流程都已經在踐行。

## Do Not Do
- 不要嘗試導入論文的完整OOQI compiler/typed design space機械——規模不匹配（Group A+是人工深度驗證，不是海量自動搜尋）。
- 不要引用初版「145條僅1個promote，遠低於雜訊null」的結論——已被修正版推翻，正確數字是約69個候選機制中2-3個promote，跟null預期同量級。
- 不要把修正版的69/2-3數字當成嚴謹統計檢定——分類仍是人工判讀單行摘要，非逐一重讀完整memory檔案內容，仍有誤差。
- **不要引用本次自行重現2020 fix margin的第一次嘗試結果**（Sharpe方向與原始紀錄相反）——腳本有未除錯的bug，已捨棄；正確的margin結論來自原始2026-07-06權威sweep檔案，見第6節。

## Next Step
無強制後續行動。若未來想對另外1-2個已promote機制（`ncf_2330 leadership score`、`ncf_2330 TSMC stock model`）也做margin/retention二次檢查，先查是否已有類似的原始sweep產出（如本次2020 fix的案例），優先用既有資料而非重新拼湊重現腳本。
