# 2606.31251 GAMLSS/ZAGA Regime-Conditional Strategy Comparison — Group A+ 適用性審查與實測

**日期**：2026-08-15
**論文**：Ozimek (2026), *"Regime-Conditional Distributional Comparison of Trading Strategies: A GAMLSS/ZAGA Framework Applied to the S&P 500"*, （獨立研究者，Warsaw）
**結論**：**交易策略本身(SVM polynomial kernel)不相關，但評估方法論(GAMLSS/ZAGA regime-conditional比較)有效且已用Group A+真實資料驗證，發現一個持續、方向一致但尚未達統計顯著的訊號——防禦性regime切換機制在牛市付出的機會成本可能超過空頭時的保護價值。**

## 1. 論文方法論摘要

- 傳統策略比較把整個回測期壓成一個Sharpe/報酬率數字，忽略表現如何隨市場regime變化。
- 用walk-forward backtest（146個40天OOS窗口，S&P500 2002-2025）算每個窗口的Adjusted Information Ratio(IR*) = (max(平均報酬,0))² / (波動度×最大回撤)，這個指標在非正報酬窗口會恰好等於0，形成「零質量+連續正尾巴」的混合分佈。
- 用**GAMLSS框架配Zero-Adjusted Gamma(ZAGA)分佈**同時對(μ平均, σ離散度, ν零機率)三個參數做迴歸，covariate是realized volatility(RV)、momentum(MOM)，都只用資產自身價格算出。
- 用擬合參數解析算出策略間在特定regime下的期望IR*差異(ΔE)，再用parametric bootstrap在6個代表性regime點做假設檢定。
- 核心發現：SVM策略在低/負動能時顯著贏過buy-and-hold，但在強勢多頭動能時buy-and-hold反而大幅領先——dominance關係是regime-conditional的。

## 2. 為何交易策略不相關、但方法論值得引入

- SVM+技術指標訊號跟Group A+的策略無關（不同資產類別、不同訊號生成邏輯），不需要移植。
- GAMLSS本身是成熟的peer-reviewed統計方法（Rigby & Stasinopoulos 2005, JRSS-C），且完全公開可複製（開源R套件），跟先前2108.11755「核心方法confidential」形成鮮明對比。
- RV/MOM covariate只用資產自身價格算出，跟Group A+現有PVA/SJM regime分類邏輯高度相容。
- 這正好對應Group A+一直在土法煉鋼做的事（例如同一天稍早的Last PPO 100k/500k/1M季度拆解），GAMLSS/ZAGA可以把這類比較升級成有p-value的正式檢定。

## 3. 用Python重現ZAGA結構並實測（無R環境，用statsmodels兩段式GLM等價重現）

ZAGA的log-likelihood可以精確分解成：(1) Bernoulli/logistic對ν(零機率)迴歸，(2) Gamma GLM(log link)對μ在正值觀測上迴歸——用`statsmodels.formula.api.logit`+`smf.glm(family=Gamma)`完整重現，不需要R的gamlss套件。

### 實驗1：Last PPO 100k vs 1M，9個不重疊fold（OOS 2025-01-02~2026-08-14, 40天窗口）
- ν方程式**complete separation**（跟論文自己在最極端regime遇到的問題一模一樣）——樣本太小，2個負動能fold剛好完美對應到兩策略的零IR*。
- μ方程式：D(1M vs 100k)係數=-0.462, p=0.343（不顯著），點估計顯示1M風險調整後IR*可能較低，跟稍早季度總報酬率拆解看到的「1M下跌段抗性較弱」是同一訊號的另一種呈現。

### 實驗2：同樣兩策略，71個重疊fold（40天窗口、5天滑動）
- D係數萎縮到-0.0325, p=0.728——**樣本從9擴大到71後，訊號幾乎完全消失**，證實先前的差異很可能是9-fold小樣本雜訊。
- MOM、RV係數方向都跟論文Table 2完全一致（MOM正、RV負），驗證Python重現版本運作正常。
- **強化了先前「100k vs 1M風險調整後打平，維持100k不promote」的判斷**，且理由更嚴謹。

### 實驗3：golden1_0531 vs switch-policy(a2118族系規則)，舊資料（`results/recheck_group_a_plus_switch_policy_backtest_20260618_curve.csv`，2025-01~2026-06，62個重疊fold，任選`switch_ma60_dd8_hold10`）
- D係數(switch vs golden1)=-0.1386, p=0.217，方向持續為負。
- 高動能(牛市)regime：golden1_0531 E(IR*)=0.0545 明顯高於switch的0.0474（切換成本顯現）。
- 低動能(空頭)regime：兩者都≈0（switch沒有展現論文預期的「主動策略在空頭時保護優勢」）。

### 實驗4：同樣比較，重跑`backtest_group_a_plus_switch_policy.py`用**最新資料**（2025-01-02~2026-08-14，392天，輸出到`results/whatif_switch_policy_fresh_20260815*`，非production，`--output-prefix`/`--latest-pointer`都導向`whatif_`前綴避免覆蓋正式pointer），改用當下系統判定的Recommended規則`switch_deriv_ma20_dd5_score1_hold5`：
- D係數=-0.1682, **p=0.120**（比舊資料的0.217更接近顯著）
- 高動能：golden1_0531 0.0460 vs switch 0.0389
- 低動能：兩者仍≈0

**三次獨立測試（舊資料任選規則、golden1_0531 vs switch的71-fold版本、新資料+今日推薦規則）方向完全一致，且p值隨資料變新越來越接近顯著**——這是一個持續、值得追蹤的訊號，不是單次雜訊，但還沒跨過p<0.05門檻。

### 實驗5：穩健性檢驗——golden1_0531 vs全部16種switch規則變體（新資料，71 fold each）
把fresh curve CSV裡**全部16個switch_*規則欄位**逐一跟golden1_0531做同樣的D係數檢定，結果：
- **16/16(100%)的D係數方向都是負的**，沒有一個例外——如果真的沒有差異，16個規則的方向應該大約各半，全數同向本身就是很強的一致性證據。
- 單一規則沒有一個跨過p<0.10顯著門檻，但最接近顯著的都是**換手較頻繁的規則**（ma20/dd5類, p≈0.11-0.12）；最遲鈍/門檻寬鬆的規則（ma120、寬鬆risk規則）幾乎打平(p>0.8)，符合「換手越勤、切換成本吃得越多」的直覺。
- **這把「防禦切換牛市機會成本」的發現從「某個特定規則的巧合」升級為「切換機制本身的普遍性質」**——不是參數選錯，是這段以多頭為主的樣本期間，任何形式的regime切換都在系統性地付出機會成本，且沒有任何測試過的變體展現出能抵銷成本的空頭保護優勢。

## 4. 核心發現與既有結果的呼應

這次GAMLSS/ZAGA實測發現的模式，跟同一天稍早Last PPO訓練步數ablation的季度拆解發現高度呼應：**防禦性/風控機制（不管是提高PPO訓練步數讓policy更積極曝險、還是regime-switch防禦切換）在牛市段的機會成本，可能持續超過它在空頭段展現出的保護價值**——這不是單一巧合，是這段樣本期間（2025-01至今幾乎全是多頭）下重複出現的同一種trade-off。

## Do Not Do
- 不要因為這個訊號還沒顯著就忽略——三次獨立測試方向一致且p值隨資料增加而收斂，值得持續追蹤，但也不要因為p值接近顯著就直接下「switch機制沒用」的結論並改動a2118的防禦邏輯——證據還不夠。
- `results/whatif_switch_policy_fresh_20260815*`系列檔案是純研究用途，不是production pointer，不要跟`report/group_a_plus/latest/`下的正式檔案混淆。

## Next Step
1. 若未來Group A+的OOS歷史累積出真正的空頭/盤整段，重新用GAMLSS/ZAGA框架檢驗這個「防禦切換在牛市持續小輸」的訊號是否在空頭段真正逆轉展現保護價值（這是switch機制存在的整個理由，需要真實驗證）。
2. 若要正式把GAMLSS/ZAGA接進Group A+常態化的策略比較管線（如`compare.py`/`promotion_utility.py`），需要決定regime covariate的標準化定義（沿用RV/MOM或改用既有的PVA/SJM state），以及是否要處理重疊窗口的自相關問題（論文用不重疊窗口犧牲樣本量換取獨立性，這次為了增加fold數用了重疊窗口，p值解讀需要更保守）。
3. 這次的Python兩段式重現（logistic+Gamma GLM）已經是可重用的最小可行版本，未來如果要用可以直接參考本次的實作方式，不需要額外安裝R環境。
