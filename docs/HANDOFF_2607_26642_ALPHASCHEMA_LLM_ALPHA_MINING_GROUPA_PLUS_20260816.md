# 2607.26642《AlphaSchema: Exploring the Space of Trading Semantics for LLM-Based Alpha Mining》審查 — 交接記錄

**日期**：2026-08-16
**論文**：Yi, Yang, Jin, Li, Li (X-Tech / Xtech-PandaAI-Waton Joint Lab / Monash / Tsinghua)，*"AlphaSchema: Exploring the Space of Trading Semantics for LLM-Based Alpha Mining"*
**結論**：**不適用，核心機制需要橫斷面選股宇宙（cross-sectional stock ranking），Group A+只有4檔可交易ETF沒有這個問題；即使抽取「結構化schema搜尋」這個meta方法論，投入成本也遠超過Group A+既有規則空間的需求，不建議投入。**

## 1. 論文核心

LLM驅動的自動化alpha因子挖掘框架。核心貢獻是把「要搜尋什麼」跟「怎麼實作」解耦：

1. **結構化語意plan**：每個候選因子表示成`p=(e,c,Q,d,o)`——Event(市場現象，如breakout/volume expansion)、Context(解讀事件的市場狀態，如VWAP區域/波動regime)、Qualities(0~3個確認/過濾條件)、Direction(預期跟未來報酬的關係，continuation/reversal/oscillation)、Output(訊號的可交易形式，連續分數/event decay/cross-sectional rank)。
2. **搜尋機制**：維護一個累積的plan-reward buffer，用LightGBM對schema特徵(one-hot、類別/範疇計數、pairwise交互作用)訓練一個reward surrogate model。每輪從140個schema元件的組合空間隨機抽樣大量候選，用quota scheduler在「結構探索(novelty)」「surrogate導向利用」「局部突變(從高reward plan改一個維度)」三者間動態配置預算。
3. **Plan-to-code實作**：LLM(預設DeepSeek-V4-Flash)把選中的schema plan翻譯成可執行factor函式，經過execution guard(合約檢查、數值有效性、look-ahead洩漏篩查)才能進入回測。
4. **Reward定義**：`r = α·RankIC + β·RankICIR - λ·Δlag`(懲罰單期delay後IC下降過多的因子，避免依賴不可執行的即時資訊)。

**實證結果**：CSI300宇宙，2016-2020訓練/2021-2022驗證/2023-2025測試，OHLCV設定挖出120檔因子池，組合後IC(0.0382)/ICIR(0.2374)超過MLP/XGBoost/Transformer/GRU/LSTM/Alpha158/Alpha360/RD-Agent/QuantaAlpha等基線；加上財報欄位的+Fundamental版本(150檔)進一步把IR推到1.0877、年化超額報酬11.94%。附錄額外驗證：(a) 五個schema維度都有貢獻，拿掉任一個維度Rank IC下降21~31%；(b) 語意搜尋過程確實從探索逐漸收斂到高reward區域(用PCA+K-means視覺化)；(c) 同一個schema plan給不同LLM(GPT-5.4/Claude 4.6/DeepSeek/Qwen等)實作，Pass率差很多但成功實作的Rank IC品質差不多——代表因子品質主要由schema決定，不是特定LLM能力。

## 2. 為何不適用——關鍵是橫斷面選股宇宙不存在，不是選擇權問題

跟今天稍早排除的兩篇選擇權論文(2608.12493、2607.29220)不同，這篇的問題不在於選擇權——這篇的核心評估對象是**跨資產排名**：

- IC/RankIC衡量的是「今天的預測分數」在CSI300(~300檔股票)裡的排名跟「未來報酬」排名的相關性。
- Top50/Drop5策略是每天從300檔裡選50檔持有，換手率受限每次最多換5檔。
- 論文附錄的Reward Predictability(Table 7)、Semantic Navigation(Figure 4)等分析全部建立在「每輪16個plan、80輪、跨越大量股票橫斷面」這個規模上。

Group A+的可交易宇宙只有**0050.TW/00631L.TW/00632R.TW/00679B.TWO四檔ETF**（2330.TW是news-only，不交易）。**不是「宇宙太小所以效果會打折」，是問題形狀根本不同構**——AlphaSchema要解決「300選50」的橫斷面排名問題，Group A+要解決的是「4檔裡面切換到哪個regime配置」的時序決策問題。沒有橫斷面可以排名，就沒有IC/RankIC這個核心評估指標可以定義，論文整套reward學習跟搜尋機制都是為橫斷面問題設計的。

## 3. 次要考量：抽取「結構化schema搜尋」這個meta方法論本身，值不值得？

論文的schema元件裡有`scope="time_series"`的選項(單一標的的時序訊號，如breakout/range-shock/gap-fill，不需要橫斷面比較)，理論上可以脫離CSI300脈絡，套用在「怎麼系統化搜尋switch規則設計」這個問題上，取代目前`backtest_group_a_plus_switch_policy.py`裡`RULES`清單(手動列出約18組ma_gap/drawdown/hold-period/chip-score/deriv-score參數組合)的人工設計方式。

**評估後判斷不值得投入**，理由：

1. **規模不匹配**：AlphaSchema的搜尋規模是140個schema元件、16 plans/round×80 rounds=1280次LLM程式碼生成+回測，外加LightGBM reward model訓練、execution/leakage guard、embedding+clustering診斷等一整套基礎建設——這是為了應付CSI300那種因子空間量級設計的重型系統。
2. **既有規則空間已經很小且有實證支撐**：Group A+目前的~18條switch規則不是暴力搜尋堆出來的，是這個session(以及更早的session)反覆用真實5次危機回測(2008/2011/2015/2018/2020)驗證過、有經濟直覺支撐(ma_gap/drawdown/籌碼/衍生品訊號)的規則。用LLM生成式搜尋去覆蓋一個已經被人工domain expertise跟大量真實回測覆蓋過的小空間，價值有限。
3. **投入成本比今天稍早否決的diffusion情境生成實驗更高**：那次只需要一個訓練腳本(PyTorch現成環境)就能測試假說；這次需要一整套LLM code-gen pipeline(prompt engineering、execution驗證、leakage screening)才能做出哪怕是最小可行的驗證，沒有一個低成本、可以脫離橫斷面選股脈絡的子問題可以直接測試。

## Do Not Do
- 不要因為論文標題有"LLM-based"或提到"structured semantic search"就假設可以脫離CSI300橫斷面選股脈絡套用——核心reward定義(RankIC/RankICIR)跟評估協定(Top50/Drop5)都需要一個有意義的橫斷面。
- 不要嘗試用這篇的schema搜尋機制去自動化Group A+的switch規則設計——既有~18條規則的規模跟這篇論文的搜尋預算量級差太多，投入產出比不合理，這個判斷已經足夠清楚，不需要用實測驗證（不像2607.29220那次的diffusion情境生成，這次沒有一個低成本、明確的子問題可以拿來試）。

## Next Step
無——架構層級的問題形狀不匹配(橫斷面vs時序決策)，加上次要的meta方法論投入產出比評估都指向同一個結論，沒有留下待辦事項。

詳細記錄完。
