# 2607.09537《GatedLinear: Adaptive Routing of Complementary Linear Bases for Time Series Forecasting》審查 — 交接記錄

**日期**：2026-08-16
**論文**：*GatedLinear: Adaptive Routing of Complementary Linear Bases for Time Series Forecasting*
**結論**：**跟今天其他論文不同，這是通用時序預測架構，有具體可測的落地點（Group A+自己的regime決策特徵）。實測後判定：完整架構不值得導入（複雜度/可解釋性投資報酬率太低，一個普通ridge regression就能達到9成效果），但抽出其中一個具體訊號（`drawdown` 20天預測）有小而穩健的RMSE邊際，已接進daily pipeline做shadow diagnostic純觀察。⚠️ 經濟效益驗證(§3d)初版因look-ahead bug誤判forecast輸給naive，修正後(§3d-korrektur)forecast其實稍微優於naive(24組中16組)，但兩者都沒有穩健打贏buy&hold，維持不接production決策的最終建議不變，理由已更正。**

## 1. 論文核心

輕量級(~千到萬級參數)多變量時序預測框架，用三個互補的線性basis分工，而非硬塞單一backbone：
1. **Global Trend-Seasonal Basis**：移動平均分解+線性投影外推。
2. **Difference-Based Incremental Basis**：一階差分+線性投影+從最後觀測值累加重建。附錄C證明對ARIMA(0,1,0)/random-walk-with-drift過程是MMSE最優且平移不變，不像對原始水平值的全域basis需要學到的權重剛好加總為1才具平移不變性(SGD+weight decay很難剛好達到)。
3. **Phase-Aligned Recurrence Basis**：把最近K個完整週期平均成模板，往前平鋪，加線性殘差。

用「Tri-Factorized Fusion Gate」動態組合：`z_{h,c,k} = a_{c,k} + u_{h,c,k} + v_{φ_h,c,k}`(channel偏好+horizon偏移+未來相位索引三個獨立分量)，temperature-scaled softmax正規化。在8個標準benchmark(電力/交通/天氣/匯率/ETT)上打平或超越PatchTST、iTransformer等更複雜模型，訓練成本遠低。學出來的gate權重可解釋，跟論文定義的6個「temporal traits」(趨勢強度/季節性強度/相位一致性/均值偏移/尺度偏移/頻譜熵)有意義相關。

## 2. 為何跟今天其他論文不同

不是綁死在選擇權/保險/SOFR/財報這些Group A+沒有的資產類別上——這是通用時序預測工具，設計動機（同一份資料裡不同變數/不同預測窗口需要不同機制）跟Group A+的處境接近：`ma_gap`、`drawdown`是switch規則真正依賴的兩個決策變數，目前規則是對「當下值」設門檻，不是對「未來值」預測。

## 3. 實測

抽取論文精神（三basis+學出來的gate組合），用純numpy+ridge簡化實作（無PyTorch），目標套在0050.TW的`ma_gap`(20日均線比例)跟`drawdown`——跟同日稍早diffusion follow-up(2607.29220)用同樣資料/切分(2015-01起、L=20窗口、2218train/555test)方便比較。腳本：`<scratchpad>/gatedlinear_regime_feature_test.py`。

### 3a. H=1(次日預測)：全部退化成persistence

basis B(差分)幾乎跟persistence打平(ma_gap RMSE 0.0168 vs 0.0169，drawdown 0.0147 vs 0.0147)——正好驗證論文附錄C自己的理論(差分basis對random walk是MMSE最優)，但也代表這兩個特徵1天粒度下沒有可榨取訊號。gated組合反而因混入沒用的trend/phase basis變差(0.0209 vs persistence 0.0169)。

### 3b. H=5(一週後)：出現小幅改善，但只有一個特徵穩健

| | ma_gap RMSE | drawdown RMSE |
|---|---|---|
| persistence | 0.0357 | 0.0295 |
| ridge-raw-lags | 0.0334 | 0.0293 |
| GatedLinear-lite | 0.0338(-5.3%) | 0.0291(-1.4%) |

拆成3段獨立測試視窗(各185天)：**ma_gap全勝(3/3)**，**drawdown只贏1/3、輸2/3**——drawdown的「改善」是雜訊。

### 3c. H=10/H=20：改善隨H拉長變大變穩健，但多數是假象或跟ridge打平

追加測H=10、H=20，並補一個「只預測訓練集歷史平均值」的常數基準來檢驗改善是否真實：

| H | 特徵 | persistence | 常數均值 | ridge-raw-lags | GatedLinear-lite | 3段視窗結果 |
|---|---|---|---|---|---|---|
| 10 | ma_gap | 0.0475 | — | 0.0400 | 0.0399 | 3/3勝，但**跟ridge幾乎打平**(0.0399 vs 0.0400) |
| 10 | drawdown | 0.0386 | — | 0.0376 | 0.0373 | 3/3勝，但**跟ridge幾乎打平**(0.0373 vs 0.0376) |
| 20 | ma_gap | 0.0550 | **0.0422** | 0.0426 | **0.0422** | 3/3勝，但**gate權重=[0,0,0]，跟常數均值完全相同** |
| 20 | drawdown | 0.0510 | 0.0652 | 0.0483 | **0.0476** | 3/3勝，且同時打贏persistence/常數/ridge三個基準 |

**關鍵發現：ma_gap在H=20的「23%改善」是假的**——GatedLinear-lite的RMSE(0.0422)跟「只預測訓練集歷史平均值」完全相同(0.0422)，gate權重確認`[0,0,0]`，代表它根本沒用任何一個basis，純粹退化成常數。這只是「ma_gap定義上是相對20日均線的比例、本身有界會均值回歸，20天後幾乎跟現在無關」這個平凡事實，不是學到任何時序結構。

**H=5/H=10的改善多半等於一個普通ridge regression**——ma_gap H=10：GatedLinear-lite 0.0399 vs 單純ridge-raw-lags 0.0400；drawdown H=10：0.0373 vs 0.0376。三basis+gate架構在這幾組沒有比一個原始滯後項的ridge多學到東西。

**唯一真正站得住的案例：drawdown H=20**——GatedLinear-lite(0.0476)同時打贏persistence(0.0510)、常數均值(0.0652)、ridge-raw-lags(0.0483)三個基準，且gate權重非退化(trend=0.12/diff=0.42/phase=0.30，三個basis都有用到)，3段獨立視窗全勝。這是唯一一個「架構本身確實比簡單基準多學到東西」的證據。

### 3d. 追加經濟效益驗證：初版有look-ahead bug，已發現並修正（見3d-korrektur）

前面3a~3c都是統計指標(RMSE)，沒有回答「這個訊號如果真的拿去做決策，有沒有用」。設計一個最小可行的2資產防禦切換回測：預設持有0050.TW，訊號跌破門檻時切到00679B.TWO(Group A+實際的防禦性資產)，在完整391天production視窗(2025-01-02~2026-08-14)上，掃6組門檻(-0.06~-0.20)。腳本：`<scratchpad>/gatedlinear_drawdown_early_warning_backtest.py`。

**初版(有bug)看起來是這樣**：forecast規則門檻-0.06/-0.08打贏golden1_0531/a2118；但加入naive當下drawdown對照後，naive在6組門檻中5組贏過forecast，上下半年切分4/4全勝；再測3個獨立年度(2018/2020/2022)18組中naive贏13組(72%)——**這個版本的結論是錯的，見下方3d-korrektur**。

### 3d-korrektur. ⚠️ 發現並修正look-ahead bug，上面3d的「naive完封forecast」結論被推翻

使用者問「參數可以微調?」時我拒絕在固定視窗上調參，改用3個獨立OOS年度驗證(正確做法)。但使用者接著問「沒有要做的實驗了?」，追問這個naive規則為何優勢大到不合理，要求「拆解報酬來源」——分解過程中發現原本的回測程式碼有**嚴重的look-ahead bug**：

```python
defensive = drawdown.loc[dt] < threshold   # 用「當天」收盤價算出的drawdown
r = rets.loc[dt, ticker]                    # 卻拿去套用「當天」的報酬率
```

`drawdown.loc[dt]`是用當天收盤價算出來的，代表已經知道當天股價的漲跌結果；用它來決定「當天」要不要切換、再套用「當天」報酬率，等於用未來(對交易當下而言)的資訊回頭避開當天的崩盤，這在真實交易中不可能做到(收盤前不會知道收盤價)。這個bug在forecast規則跟naive規則都存在，且對兩者的影響不對稱——naive訊號直接是當天drawdown本身(受益最大)，forecast訊號是H=20天預測(較平滑，受益較小)，所以bug放大了naive相對forecast的優勢，製造出「naive完封forecast」的假結論。

**修正**：訊號改用前一天(t-1)的值決定當天(t)的持倉(`signal.shift(1)`)，這才是真實交易可行的因果順序。用修正後版本在全部4個視窗(391天production + 2018 + 2020 + 2022)重跑，共24組threshold×視窗組合：

| 視窗 | forecast勝 | naive勝 |
|---|---|---|
| 391天production | 5 | 1 |
| 2018 | 5 | 1 |
| 2020 | 2 | 4 |
| 2022 | 4 | 2 |
| **總計** | **16(67%)** | **8(33%)** |

**結論完全反轉**：修正bug後，forecast規則在24組中贏16組，naive只贏8組——跟修正前回報的「naive贏18組中13組(72%)」方向相反。GatedLinear-lite的H=20預測在真正因果一致的回測下，其實**傾向於比naive當下值規則更好**，不是更差。

**但也要誠實地說**：修正後不管forecast還是naive，都沒有穩定、一致地打贏單純buy&hold 0050(391天視窗buy&hold Sharpe=1.93，forecast/naive兩者在多數門檻都低於這個數字)。所以「不要接進production決策」的最終建議維持不變，但理由要更正：不是因為「naive完封forecast、forecast沒用」，而是「forecast雖然稍微優於naive，但兩者都沒有穩健地打贏最簡單的buy&hold基準，證據強度都不夠支撐production決策」。

**Why記錄這個**：這是本session、也是本次GatedLinear調查裡最嚴重的一次自我發現的方法論錯誤——不是資料污染或參數選錯，而是回測邏輯本身的look-ahead bug，且已經在稍早的回報中把錯誤結論(「naive完封forecast」)明確告知使用者。修正後在此完整記錄推翻過程，不隱藏、不覆蓋原始錯誤描述(見上方3d保留原文)，符合本session一貫的「每次自我修正都完整保留，不覆蓋原結論」慣例。

**How to apply**：任何「用當天已知特徵值決定當天持倉、套用當天報酬率」的回測寫法都要立刻檢查look-ahead——正確作法是訊號必須用嚴格早於決策生效日的資訊(至少shift(1))。未來重跑任何早期預警/switch規則回測，第一步就要驗證這個時序關係，不要等到結果好到不合理才回頭查。

**附帶：股債相關性分解(用戶選「拆解報酬來源」後做的分析)也是用帶bug版本算的**——腳本`<scratchpad>/naive_drawdown_return_decomposition.py`把naive規則優勢拆成「單純避開下跌(用CASH取代0050)」跟「00679B自身正報酬(flight-to-quality)」兩部分，發現00679B在2018/2020跟0050負相關(-0.38/-0.14，flight-to-quality真實存在)、但2022年bond variant反而拖累(股債同跌)、391天production視窗兩者幾乎零相關(0.028，沒有避險效果)。**這個「不同年度股債相關性regime不同」的定性結論不受look-ahead bug影響**(相關係數本身跟同日/前一日決策無關)，可以保留參考；但拆解出的絕對報酬數字(如「00679B貢獻+13.32%」)是用帶bug版本算的，不可信，需要有人重跑修正版才能拿到可信數字，本次未做。

### 3e. Out-of-sample驗證方法論仍然正確，但結論隨3d-korrektur一併修正

使用者問「參數可以微調?」後，正確回應是不在同一391天視窗上調`L`/`P`/alpha/門檻，改用3個從未用來調參/選門檻的獨立歷史年度(2018/2020/2022)做out-of-sample驗證，方法論本身沒有問題。門檻/模型參數維持原樣不變。腳本：`<scratchpad>/gatedlinear_drawdown_oos_windows.py`。但**這3個年度的回測數字也用了帶bug的同日決策版本**，已在3d-korrektur用修正後版本重跑並取代原本「naive贏18組中13組」的結論——正確結果是上表所示的forecast贏16/24。

00679B是20年期以上長天期債券ETF，2022年升息時本身也重挫，是「切防禦資產」邏輯本身可能失效的年度，跟其他兩年質地不同，是此次OOS窗口選擇特意涵蓋的壓力測試regime，這個設計考量仍然成立，不受bug修正影響。

### 3f.（附帶發現，數字受3d bug影響需保留但降級為「方向性參考」）今天稍早SOFR/entropic實驗的視窗跟本次不可直接比較

驗證3d時發現：`docs/HANDOFF_2608_10711_SOFR_INDIFFERENCE_PRICING_GROUPA_PLUS_20260816.md`報告的golden1_0531 Sharpe=2.658、a2118 Sharpe=2.916，用的是同一份`whatif_drawdown_bootstrap_source_20260816_curve.csv`但因為那個實驗自己的H=60回顧窗口，**實際比較區間從2025-04-10才開始**(截掉了2025年初到4月這段，包含4月初的關稅拋售)。而本次3d跟今天稍早block bootstrap等其他實驗用的都是完整391天(2025-01-02起)，golden1/a2118的真實完整視窗Sharpe其實只有1.80/1.94。這不是bug（entropic實驗自己內部所有候選都用同一個截斷窗口比較，排序仍然公平），但**兩篇文件裡的「golden1_0531 Sharpe」數字不能跨文件直接引用比較**，未來遇到要小心核對窗口起點。

## 4. 已落地的行動

1. **不導入完整GatedLinear架構**——複雜度/可解釋性投資報酬率太低，一個ridge regression就能達到9成以上的效果，唯一的例外(drawdown H=20)相對ridge也只贏1.5%。
2. **`drawdown` H=20預測接入daily pipeline純觀察，不影響任何決策**：
   - `group_a_plus/integrations/gatedlinear_drawdown_forecast_shadow_log.py` — 核心`fit_and_forecast()`，用0050.TW全歷史walk-forward重fit(訓練pair只用target已知的歷史窗口，保持跟研究腳本一致的紀律)。
   - `scripts/run/build_group_a_plus_gatedlinear_drawdown_forecast_shadow_log.py` — CLI runner，寫入`results/group_a_plus_gatedlinear_drawdown_forecast_shadow_log.jsonl`(逐日累積，依日期去重)跟`report/group_a_plus/latest/gatedlinear_drawdown_forecast_shadow.json`(最新快照)。
   - 已接進`scripts/run/run_ncf_daily_pipeline.py`的`BEST_EFFORT_STEP_NAMES`(步驟名`gatedlinear_drawdown_forecast_shadow_log`)，失敗不會擋住其餘pipeline。
   - 測試：`tests/test_group_a_plus_gatedlinear_drawdown_forecast_shadow_log.py`(4項全過)，加上`tests/test_run_ncf_daily_pipeline.py`既有的完整步驟清單斷言已同步更新(2項原本失敗的測試已修復)。
   - 實際production資料驗證：2026-08-14當前drawdown -4.27%，預測20天後drawdown -5.40%，gate權重跟研究腳本的H=20 profile一致(trend=0.12/diff=0.42/phase=0.27)。

## Do Not Do
- 不要看到「改善隨H拉長變大」就直接下「模型學到更長期結構」的結論——H=20 ma_gap的改善被證實100%是均值回歸假象(gate權重全為0，等於常數預測)，必須用「常數基準」跟「拆分視窗」兩道檢查才能分辨真假。
- 不要把GatedLinear-lite的H=5/H=10結果當成架構優勢的證據——這兩組幾乎跟一個原始滯後項的ridge regression打平，不是tri-basis+gate機制本身的貢獻。
- 不要把這個shadow diagnostic的預測值接進switch規則或任何target weight邏輯——修正look-ahead bug後，forecast規則雖然稍微優於naive(24組中16組)，但兩者都沒有穩健打贏單純buy&hold 0050，證據強度都不足以支撐production決策(見§3d-korrektur)。
- 不要跨文件直接比較golden1_0531/a2118的Sharpe數字而不核對比較窗口起點——同一份curve CSV因為不同實驗的lookback需求，比較區間可能截斷不同，數字不可直接並列(見§3f)。
- **不要在寫「用當天特徵值決定當天持倉、套用當天報酬率」這種回測程式碼時漏掉時序檢查**——`signal.loc[dt]`若是用dt當天收盤價算出來的，卻拿去決定dt當天的持倉並套用dt當天報酬率，就是look-ahead bug。已在§3d-korrektur發現並修正，正確作法一律用`signal.shift(1)`(或更早)決定持倉。結果好到不合理時，第一步該查這個，不是急著寫結論。
- 不要在同一個固定歷史窗口上調`L`/`P`/alpha/門檻直到forecast規則贏過naive——方法論本身正確(見§3e)，但用3段獨立年度驗證前務必先確認回測邏輯本身無look-ahead，否則OOS驗證只是把同一個bug複製到更多視窗，不會發現問題。

## Next Step
無強制後續行動。shadow log會逐日累積`drawdown` H=20的真實預測值，未來(至少累積數十筆後)可以寫一個`evaluate_*.py`腳本，把預測值跟20個交易日後的實際drawdown對齊比較，驗證這個H=20邊際在真實線上資料是否持續存在，而不只是單一歷史切分的結果。

詳細記錄完。
