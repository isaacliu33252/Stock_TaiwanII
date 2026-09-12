# 2608.10711《Optimal Pricing and Hedging of SOFR Derivatives》審查 — 交接記錄

**日期**：2026-08-16
**論文**：Pennanen, Taoum (King's College London)，*"Optimal Pricing and Hedging of SOFR Derivatives"*
**結論**：**論文本身不適用（Group A+無SOFR/利率衍生品曝險），但使用者要求實測其通用手法（用convex risk measure做少數資產的凸優化配置）能否取代Group A+既有的離散switch規則——實測全面更差，在四組風險趨避參數下沒有一組打贏現有switch規則的Sharpe/MDD。**

## 1. 論文核心

美國SOFR(隔夜擔保融資利率)衍生品市場的**indifference pricing**框架。CME掛牌的SOFR期貨/選擇權流動性好，但OTC的SOFR交換(OIS)、交換選擇權(swaption)、利率上限/下限(caplet/floorlet)無法完美複製避險。論文用convex risk measure(entropic risk measure，`V(u)=(1/ρ)ln E[exp(-ρu)]`)定義一個最適投資問題：在數百個交易所商品(有bid-ask價差跟數量限制)裡找一個稀疏避險組合去逼近OTC商品的payoff，同時明確量化避險誤差跟對應的indifference買賣價。用真實CME報價實測，一分鐘內用MOSEK凸優化solver算完，避險組合通常稀疏(數百個裡只用十幾個)但已能不錯地逼近目標payoff。

## 2. 為何論文本身不適用

Group A+完全沒有SOFR曝險——不交易美國利率期貨/選擇權/交換/交換選擇權/利率上限這些商品。這篇論文整套機制(payout functions、bid-ask優化、稀疏避險組合、indifference swap rate)是為了「用有限流動性的交易所商品去逼近無法複製的OTC利率商品payoff」這個特定問題設計的，沒有這類商品就沒有東西可以定價或避險。跟同日稍早的2607.21687(保險精算HJB)是同一類問題：通用的凸優化/風險測度金融工程框架，但沒有對應的資產類別可以套用。

## 3. 追加實測：用convex risk measure取代既有離散switch規則

使用者對「論文本身不適用」提出「不能參考?」，要求抽取論文的通用手法實際測試。抽取的核心技巧：**用entropic risk measure對少數可用資產做凸優化，找最適權重並明確量化風險**——這是論文式(17)跟Section 4最適投資問題的精神，去掉CME訂單簿/bid-ask機制，簡化成Group A+的4檔ETF權重單純形(simplex)配置問題。

**設計**：
- 資產：0050.TW/00631L.TW/00632R.TW/00679B.TWO(Group A+可交易宇宙)。
- 情境集合：每個交易日t，用過去H=60個交易日的真實已實現報酬當作「明天報酬可能長什麼樣」的情境集合(historical simulation，跟論文的Monte Carlo情境集合同精神但大幅簡化)。
- 目標函數：`minimize (1/ρ)·log(mean_s[exp(-ρ·w'r_s)])`，w在long-only單純形(`sum(w)=1, w≥0`)——這是convex的(w的線性函數的log-sum-exp是convex)，對應論文式(17)。
- 每日重新求解權重(用scipy.optimize SLSQP)，跑滿391天真實交易日回測(2025-01-02~2026-08-14)。
- 測試4組風險趨避參數ρ∈{5,15,40,100}，涵蓋從積極到保守的完整範圍。

腳本：`<scratchpad>/entropic_convex_allocation_test.py`。

**結果——四組風險趨避參數全部沒有打贏既有switch規則**：

| | Sharpe | MDD | 總報酬 | 平均權重 |
|---|---|---|---|---|
| **golden1_0531(production基準)** | 2.658 | -19.62% | 158.56% | — |
| **a2118 switch規則(production)** | **2.916(最佳)** | **-15.29%(最佳)** | 148.11% | — |
| entropic ρ=5(低風險趨避) | 1.890 | -23.92%(更差) | 134.66% | 00631L 67.9% |
| entropic ρ=15 | 1.698 | -17.72% | 55.04% | 0050 48.3%/00631L 25.5% |
| entropic ρ=40 | 1.868 | -9.13%(最保守) | 24.90% | 0050 49.7%/00632R 25.4% |
| entropic ρ=100(高風險趨避) | 1.769 | -4.36%(極保守) | 10.63% | 0050 41.0%/00632R 39.2% |

**判讀**：低ρ承擔更多風險卻沒換到對應報酬(還比golden1回撤更深)；高ρ雖然把回撤壓得很低，但犧牲的報酬遠超過風險降低的比例，Sharpe仍然全部不如既有switch規則。

**根本原因**：這個凸優化用的情境集合是「過去60天真實報酬」——**純粹回顧性**，只能反映「剛剛發生過的波動」，沒有任何前瞻性。Group A+既有switch規則用的是`ma_gap`、`drawdown`、籌碼/衍生品訊號這些**領先指標**，能在regime真正轉換之前就先行反應。這說明Group A+的優勢來自訊號設計本身(領先指標)，不是配置演算法的精密程度——套用更「原理正確」的凸優化風控機制，如果餵進去的只是純粹回顧性的歷史報酬分布，反而不如一個簡單但用對領先訊號的規則。

## Do Not Do
- 不要因為論文標題有"optimal pricing and hedging"這類聽起來通用的詞彙就假設可以套用——核心機制(SOFR衍生品payout結構、CME訂單簿)綁死在利率衍生品市場上。
- 不要把entropic risk measure凸優化(用純回顧性歷史報酬當情境集合)當成switch規則的替代品——已用四組風險趨避參數實測全面更差，不是單一參數選錯的問題。
- 若未來想重啟這條線，情境集合必須換成有前瞻性的東西(例如既有regime分類機率、tail_conformal分位數預測)，而不是單純trailing window的歷史報酬resampling——這是本次實測揭示的根本瓶頸，不是凸優化框架本身的問題。

## Next Step
無強制後續行動。若使用者想進一步驗證「凸優化+前瞻性情境集合」是否能打贏switch規則，需要先把既有regime診斷特徵轉換成一個機率化的情境生成器，這是比今天的最小可行測試大得多的工程量，這次沒有做。

詳細記錄完。
