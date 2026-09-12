# 2608.09089 Extreme Value Alpha and Crash Risk — Group A+ 適用性審查

**日期**：2026-08-14
**論文**：Zhang & Yang (2026), *"Extreme Value Alpha and Crash Risk: Separating Structural Tails from Lottery Tails with LLM-Extracted Disclosure Networks"*, arXiv:2608.09089v1
**結論**：**不導入 Group A+ / a2118（最新策略）**，判定 research_only，無需回測驗證即可關閉。

## 論文方法論摘要

- **問題**：股票的heavy upper tail（尾部熱度）是模糊訊號——可能是「樂透尾巴」（transient jump risk，投資人overpay，即MAX anomaly的折價對象）或「結構性尾巴」（economic reconfiguration的統計影子，如NVIDIA歷次大漲前的模式）。單看報酬序列無法區分兩者。
- **判別器**：用LLM從公司10-K財報（Item 1/1A/7）抽取一個directed、span-grounded的「揭露經濟網絡」（供應商/客戶/授權/雲端/平台依存關係），逐年vintage比對rewiring，精確分解成edge-birth mass B、edge-death mass D、continuing drift C。
- **核心訊號**（sign pattern）：
  - `尾部熱度(ξ+) × 死亡質量(D)` → 顯著負向未來報酬，即**危險旗標/crash-side**（pilot: firm-vintage collapsed regression t≈-3.9, wild-cluster bootstrap p=0.04，兩次NVIDIA暴跌2018/2022前都是D-dominated rewiring）。
  - `尾部熱度(ξ+) × 誕生質量(B)` → 理論上該有正向「結構性溢價」/alpha-side，但**pilot中不顯著**（t≈+0.7~1.9），僅方向正確。
- **證據強度**：24檔美國科技股pilot（2014-2025）支持crash-side；但**pre-registered replication在50檔隨機S&P500股票上完全失敗**（interaction係數-0.001, t=-0.07, p=0.49）——因為判別器需要的disclosure graph在非科技生態系幾乎消失（83%的firm-vintage死亡質量為零，對比pilot的27%）。作者因此把整個機制的適用範圍限縮在「揭露密集的coherent ecosystem」（科技供應鏈、電信基礎設施、國防航太），並凍結一套confirmatory design（含density gate前置條件），**目前狀態是on hold，尚未confirm**。

## 為何不適用 Group A+

查`config/group_a_plus_watchlist.json`，Group A+/a2118 實際可交易標的是：
```
0050.TW（元大台灣50）、00631L.TW（正2）、00632R.TW（反1）、00679B.TWO（美債20年）
```
全部是**指數型ETF**，2330.TW（台積電）僅作為新聞關鍵字監控標的存在，非可交易部位。

論文的判別器（disclosure-measured economic network）建立在**個股10-K揭露的供應商/客戶關係文本**上——這個概念對追蹤指數的ETF完全不存在對應物（0050/00631L沒有「供應商」，00679B是債券ETF），不是回測能解決的資料缺口，是資料型態的根本不匹配，同一類推論已見於 [[project_2604_09060_aegis_universe_mismatch_closed_20260813]]（AEGIS論文的大候選池 vs. Group A+的5檔小池不匹配）。

**逐項檢查**：
1. **交易標的錯位**：判別器需要單一公司的揭露文本網絡，Group A+全是ETF，無此對象。
2. **即使有個股也用不上**：論文本身在非科技生態系（隨機50檔S&P500）就已經replication失敗（disclosure graph幾乎消失），台股個股（若未來納入2330等）揭露格式（MOPS公開資訊觀測站）與美股10-K結構、密度都不同，適用性只會更差，不是簡單換語言就能移植。
3. **論文自己都還沒confirm**：pilot-only descriptive結果，confirmatory design標記on hold（等density gate通過），alpha-side（結構性溢價）本身在pilot中就不顯著，作者明確聲明alpha claim必須等confirmatory test通過才能用於capital allocation；即使是crash-side危險旗標，也只夠risk-monitoring pool的證據門檻，還沒到能單獨用的地步。

## Do Not Do
- 不要嘗試把「揭露經濟網絡」概念套用在ETF標的上（沒有對應的揭露文本可抽取）。
- 不要因為Group A+已有NCF個股模型基礎設施（ncf_2330）就假設可以無痛移植——論文機制在個股層級都還沒confirm，且需要LLM抽取pipeline、10-K/MOPS filing資料源，屬於全新的重型基礎建設投入，ROI在論文自己都未confirm的前提下不合理。

## Next Step
- 若使用者未來考慮讓Group A+納入個股（如2330台積電）作為可交易部位，且該論文完成confirmatory stage並confirm，可重新評估是否值得投入建置台股版揭露網絡抽取pipeline。在此之前維持research_only關閉。
