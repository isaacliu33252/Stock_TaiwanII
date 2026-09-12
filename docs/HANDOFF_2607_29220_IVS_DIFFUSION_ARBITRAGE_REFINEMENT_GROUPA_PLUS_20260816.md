# 2607.29220《Decoupled Probabilistic Forecasting and Arbitrage-Aware Refinement of Implied Volatility Surfaces》審查 — 交接記錄

**日期**：2026-08-16
**論文**：Hao & Ji (Zhongtai Securities Institute, Shandong University), *"Decoupled Probabilistic Forecasting and Arbitrage-Aware Refinement of Implied Volatility Surfaces"*
**結論**：**不適用，跟同日稍早審查的2608.12493（選擇權曲面transport幾何）是同一類架構不匹配問題，不需要回測即可判定。**

## 1. 論文核心

對CSI 300指數選擇權的隱含波動率曲面(IVS)做兩階段預測框架：

1. **Stage I（conditional diffusion）**：用conditional diffusion model學習未來IVS狀態的條件分布，生成B=100個情境集合，取pointwise ensemble median當代表性預測曲面。相對LSTM-Direct基線，RMSE在daily頻率降8.7%、minute-level頻率降36.0%，且能提供隨moneyness/maturity/取樣頻率變化的預測區間（不是單點預測）。
2. **Stage II（SAAM, Surface Aware Attention Module）**：用cross-sectional attention把Stage I的代表曲面修正到更貼近市場觀察值，同時降低static no-arbitrage殘差（calendar spread單調性、butterfly spread凸性admissibility、tail asymptotics邊界曲率）。兩個變體（Spatial Separation SAAM純用座標路由、Volatility Fusion SAAM額外融入全域波動度水準訊號）都優於MLP-based逐點修正基線，在minute-level（雜訊更大、觀察點更稀疏）優勢更明顯。

方法論本身嚴謹：Proposition 1明確列出6條static no-arbitrage充分條件（positivity、zero-maturity limit、differentiability、monotonicity/calendar spread、Durrleman's butterfly condition、tail asymptotics），且誠實承認Stage II的殘差懲罰只在有限diagnostic grid上生效，不是連續域上的正式證明（"small residual values should be interpreted as numerical evidence...rather than as a formal proof of global static arbitrage freedom"）。

## 2. 為何不適用

論文整套方法論——log-forward moneyness參數化、Black-76定價公式、SVI族、calendar/butterfly no-arbitrage條件、隱含波動率曲面本身——**全部是選擇權特有的概念，沒有選擇權部位就沒有東西可以套用**。

Group A+的可交易資產是0050.TW/00631L.TW/00632R.TW/00679B.TWO，2330.TW僅news-only。同日稍早審查2608.12493（選擇權曲面transport幾何論文）時已經用WebSearch查證：**00631L/00632R是台指期貨為主的槓桿/反向ETF，不是選擇權部位**（來源：pocket.tw、元大投信官網、gugu.fund，詳見`docs/HANDOFF_2608_12493_VARIANCE_SURFACE_TRANSPORT_GROUPA_PLUS_20260816.md`）。這個事實查證直接排除了任何以「Group A+持有選擇權」為前提的論文，這篇也不例外。

跟2608.12493的差異只在切入角度——2608.12493是選擇權定價曲面的幾何transport理論，這篇是diffusion生成式預測+attention式no-arbitrage修正——但對沒有選擇權部位的Group A+，兩篇的判定邏輯完全相同：**架構層級不匹配，不需要回測驗證即可判定不適用**。

## 3. 有沒有可抽取的通用方法論？（簡短評估）

考慮過是否有跳脫選擇權脈絡、可抽象套用的通用元件，結論是沒有值得單獨移植的部分：

- **Diffusion-based機率情境生成**（Stage I的核心手法）本質上是一般的條件式生成模型，理論上可以用在任何時序預測問題。但Group A+目前的預測需求（regime分類、switch訊號）都是低維度、可解釋性優先的問題，用diffusion model生成高維度情境集合是為了解決IVS這種255維(15×17 grid)空間結構問題而設計的，套用在Group A+的低維特徵上沒有對應的複雜度需求，殺雞用牛刀。
- **SAAM的cross-sectional attention修正**明確依賴「calendar spread」「butterfly spread」這類選擇權特有的幾何admissibility條件當訓練目標的正則化項，沒有選擇權曲面就沒有這些殘差可以懲罰，機制本身無法脫離選擇權脈絡改造。

兩者都不建議進一步花時間評估。

## 4. 追加實測：把diffusion情境生成脫離選擇權脈絡，套用在Group A+自己的regime特徵上

使用者對第3節「殺雞用牛刀」的判斷提出「可以試試看?」，要求實際驗證而非只憑理論判斷。做了一次完整的對照實驗，結論是：**不只沒必要，實際上更差**。

**設計**：預測目標是production switch規則(`switch_deriv_ma20_dd5_score1_hold5`等)真正依賴的兩個決策變數——**下一天的`ma_gap`跟`drawdown`**（0050.TW）。用真實0050.TW價格歷史(2015-01-01起，避開稍早發現的2014-01-02未調整分割斷點)計算`ma_gap`/`drawdown`/`realized_vol_20d`/`mom_5d`四個特徵，用H=20天滾動窗口(展開成80維)當條件，訓練一個輕量版conditional diffusion model(K=50步、小型MLP score network，仿照論文Stage I的forward/reverse diffusion結構但去掉所有IVS/選擇權相關的no-arbitrage部分)，B=200次反向採樣生成情境集合。訓練樣本2218筆(2015-03~2024-04)，測試555筆(2024-04~2026-08)，時序切分。腳本：`<scratchpad>/diffusion_regime_scenario_test.py`。

**對照組**：(1) persistence(用前一天的值當預測)，(2) ridge迴歸(用同樣80維條件做線性點預測)，(3) Gaussian-AR基準(ridge殘差標準差當常態分布，算closed-form CRPS)。

**結果——三個指標全部輸給簡單基準**：

| 指標 | Persistence | Ridge | Diffusion |
|---|---|---|---|
| RMSE(ma_gap, drawdown) | 0.0240 / 0.0207 | 0.0232 / 0.0206 | **0.0281 / 0.0250(最差)** |
| MAE | 0.0177 / 0.0143 | 0.0170 / 0.0145 | **0.0209 / 0.0177(最差)** |
| CRPS(分布預測品質) | — | — | Gaussian-AR **0.01181** vs Diffusion **0.01655**(更差) |
| 90%預測區間實際涵蓋率 | — | — | **35.1% / 42.7%**(目標90%，嚴重校準不足) |

**判讀**：不只點預測輸給最簡單的persistence基準，連論文最核心的賣點——機率分布預測優於單點預測——都輸給一個最陽春的常態分布假設；90%區間實際涵蓋率只有35~43%，代表diffusion ensemble的樣本發散度嚴重不足，模型對自己的不確定性過度自信，沒有真正學到有意義的分布。**合理解釋**：diffusion model是為了255維(15×17 grid)、高度結構化的選擇權曲面設計的生成模型，訓練樣本量(~2200筆)對這種模型來說太少；而Group A+這裡的目標只有2維、訊噪比本來就不高，simple方法(persistence/ridge)已經逼近可預測的極限，複雜生成模型在小樣本低維度資料上學不出有意義的分布，反而全面更差。

**沒有做的事**：沒有進一步調參重試(更多epoch、更大網路、不同K)——三個指標(點準確度、CRPS、校準)方向完全一致，已是決定性的負面結果，在單一窗口上反覆調參試圖救回正面結果會撞上`feedback_overfitting_fixed_window_tuning`的紅線。

## Do Not Do
- 不要因為論文標題提到"probabilistic forecasting"或"attention"就誤以為有通用時序預測價值可挖——核心機制(no-arbitrage殘差正則化)綁死在選擇權曲面幾何上。
- 不要把diffusion-based情境生成套用在Group A+低維regime特徵上——第4節實測已證明點準確度、CRPS、校準三項指標全面輸給persistence/ridge/Gaussian-AR等簡單基準，不是理論猜測而是實測結果。
- 不要重複做這類選擇權論文的架構匹配判斷——本session今天已經對兩篇選擇權相關論文(2608.12493、這篇)做過同樣的排除，後續若再遇到選擇權曲面/定價類論文，可以直接引用「Group A+無選擇權部位」這個已查證事實快速判定，不需要每次重新分析論文內容細節。

## Next Step
無——選擇權曲面本身的排除跟diffusion情境生成的實測都已是決定性結論，沒有留下待辦事項。

詳細記錄完。
