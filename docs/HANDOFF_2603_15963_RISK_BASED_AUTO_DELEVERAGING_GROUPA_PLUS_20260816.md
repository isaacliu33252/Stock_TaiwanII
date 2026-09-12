# 2603.15963《Risk-Based Auto-Deleveraging》審查 — 交接記錄

**日期**：2026-08-16
**論文**：Campbell, Hey, Moallemi, Nutz (Columbia University)，*"Risk-Based Auto-Deleveraging"*
**結論**：**論文本身不適用（Group A+不是交易所，沒有「多帳戶間分配強制減倉」這個問題結構）。但論文核心洞察（漸進式water-filling減倉優於一刀切全額平倉，已在Hyperliquid真實ADL事件實證）可以重新詮釋成「用漸進式防禦部位取代Group A+現有的二元switch硬切換」並實測。結果：漸進規則在緩慢累積型壓力(2018/2022/391天production)穩定勝出，但在2020 COVID閃崩中被binary硬切換完封——這是一個具體、通過參數穩健性檢查的區分準則。兩種switch機制都沒有穩定打贏單純buy&hold，不建議promote，但發現本身值得記錄。**

## 1. 論文核心

加密貨幣永續合約交易所的auto-deleveraging(ADL)機制設計。當某帳戶爆倉、保證金不足時，交易所必須強制平倉其他solvent帳戶的部位來吸收虧損。論文把這公式化成風險最小化問題：

1. **單一資產、隔離保證金**：期望損失最小化的最優政策是**minimax leverage water-filling**——先減最高槓桿帳戶的部位，逐步把槓桿壓到跟次高槓桿帳戶相等，直到達到目標減倉量。distribution-free、抗wash-trade、抗Sybil分身、path-independent，優於業界現行BitMEX式「依優先度排隊全額平倉」機制。
2. **多資產、跨保證金**：需要用**factor leverage**(考慮共同風險因子/避險效果後的槓桿)而非gross leverage做water-filling。
3. **實證(2025-10-10 Hyperliquid ADL事件)**：risk-optimal/water-filling分配的expected shortfall明顯優於交易所實際執行的分配——**核心差異是結構性的：實際政策幾乎不管槓桿、直接全額平倉受影響帳戶；risk-based政策則是漸進、部分減倉，依槓桿程度排序**。

## 2. 為何論文本身不適用

Group A+不是交易所，不需要在「多個其他交易者的帳戶」之間分配強制平倉——整套機制(多帳戶排隊、Sybil抵抗、跨帳戶損失分配)的前提在Group A+完全不存在，Group A+只管理自己單一投資組合。

## 3. 抽取通用洞察並實測：「漸進式減倉 vs. 二元硬切換」

論文最可轉移的發現不是water-filling公式本身(那需要多帳戶才有意義)，而是**「漸進式部分減倉優於一刀切全額平倉」這個經驗結論**——這正好對應Group A+現有switch規則的一個具體弱點：目前的switch規則是**二元硬切換**(100% golden1 ↔ 100% defensive)，觸發時直接跳到全額防禦，跟Hyperliquid案例裡被證明較差的「realized allocation」是同一種設計。

**實驗設計**：
- 成長資產：0050.TW；防禦資產：00679B.TWO（跟今天稍早所有實驗一致）。
- **binary規則**：`drawdown(t-1) < threshold` → 100%防禦，否則100%成長（現有switch規則的簡化代理）。
- **graduated規則(water-filling風格)**：防禦權重隨drawdown惡化程度線性爬升——`defensive_weight = clip((threshold - drawdown(t-1)) / stress_range, 0, 1)`，觸發點0%防禦、drawdown深過threshold再`stress_range`個百分點時到100%防禦，中間線性內插。搭配10%不動區間(no-trade band)避免頻繁瑣碎再平衡。
- **兩者都用`shift(1)`嚴格因果決策**(今天稍早GJR-GARCH/GatedLinear實驗發現look-ahead bug後建立的鐵律，這次一開始就正確實作，未重蹈覆轍)。
- 含真實交易成本(commission 0.1425%+slippage 0.05%+ETF賣出稅0.1%)。
- 測試視窗：391天production + 2018 + 2020 + 2022（今天已建立的4組標準對照視窗）。
- 門檻固定`threshold=-0.06`(今天稍早已用的值，非重調)；`stress_range`掃4組(0.05/0.10/0.15/0.20)做穩健性檢查，不挑最佳值報告。

腳本：`<scratchpad>/adl_waterfilling_graduated_switch.py`。

**結果——只要stress_range不設太窄，graduated穩定贏binary 3/4，但2020是決定性的反例**：

| stress_range | graduated勝場(4視窗中) |
|---|---|
| 0.05(近似binary，幾乎立刻滿倉防禦) | 2/4 |
| 0.10 | **3/4**（391天、2018、2022勝；2020輸） |
| 0.15 | **3/4**（同上） |
| 0.20 | **3/4**（同上） |

**2020年COVID崩盤在全部4組stress_range下binary都贏graduated**——這是決定性、跨參數一致的反例。COVID是幾天內急跌的閃崩，graduated規則要花時間慢慢爬升到滿倉防禦，跟不上崩盤速度；binary硬切換立即全額防禦反而更有效，MDD穩定壓在-16.82%(graduated在同視窗MDD介於-19%到-28%，隨stress_range加寬而惡化)。

**判讀**：這正好呼應論文自己框架的隱含前提——water-filling的最優性建立在**帳戶有足夠時間漸進調整**這個假設上。緩慢累積型壓力(2018修正、2022升息熊市、391天production視窗多數時間)符合這個前提，漸進式減倉確實比一刀切更好；但真正的瞬間衝擊(2020 COVID是幾天內閃崩，不是漸進累積的壓力)不符合這個前提，graduated規則反而因為反應太慢而變差。**這是一個具體、可解釋、通過4組參數穩健性檢查的區分準則：漸進式風控只在「壓力漸進累積」的regime裡有優勢，「瞬間閃崩」regime裡binary硬切換更好。**

**誠實的整體結論**：不管binary還是graduated，在4個視窗都沒有穩定打贏單純buy&hold 0050——這跟今天稍早的其他switch規則因果測試（GatedLinear forecast vs naive、entropic凸優化）結論一致：Group A+這種「用0050/00679B二資產切換」的簡化代理規則本身天花板不高，不建議把graduated或binary任何一種單獨拿去promote production。但**「漸進式減倉在緩慢累積壓力下有優勢、在瞬間閃崩下劣勢」這個發現本身是有價值的**，可以作為未來設計switch規則(或既有`golden1_tail_trim`overlay)時的判斷準則：不要用單一機制應付所有regime，考慮偵測「壓力累積速度」來決定用漸進式還是立即全額反應。

## Do Not Do
- 不要把graduated規則的「391天/2018/2022勝出」直接當成「漸進式優於二元」的普遍結論——2020 COVID是決定性反例，且跨4組stress_range參數一致，不是雜訊。
- 不要忽略這個發現的因果限制：graduated規則之所以在閃崩輸，是因為它的設計前提(有時間漸進調整)在瞬間衝擊下不成立，這是規則設計的根本限制，不是可以靠調參數解決的。
- 不要把這個實驗跟今天稍早GatedLinear的「naive vs forecast」搞混——這次比的是「防禦權重的變化速度(binary/graduated)」，不是「訊號本身(forecast/naive)」，是完全不同的兩條實驗線，只是剛好都用同一組0050/00679B/391天+2018+2020+2022的基礎設施。

## Next Step
無強制後續行動。若未來想真正落地「依壓力累積速度切換漸進/立即反應機制」的想法，需要先設計一個「壓力累積速度」的偵測指標(例如drawdown的變化率而非drawdown本身)，這次沒有做，只驗證了「兩種機制各有各的regime優勢」這個定性發現。

詳細記錄完。
