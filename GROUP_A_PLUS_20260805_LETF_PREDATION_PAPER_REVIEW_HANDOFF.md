# Group A+ 2026-08-05 交接記錄：LETF掠奪論文審查與實測 + 發現execution_plan.json再次踩過期持股雷

Status: 完整記錄本次對話的工作內容，並記錄一個在準備交接時新發現、與本次對話工作無關但重要的production狀態問題。與同一天稍早的
`GROUP_A_PLUS_20260805_TRIPLE_DIRECTION_AUDIT_AND_OPS_FIXES_HANDOFF.md`（三方向研究稽核+兩個真實bug修復+workbook混亂）是**不同session**，本文件不重複那份的內容，只在必要處引用。

## 目錄

1. 論文審查：arXiv:2608.03703《Preying on Leveraged ETFs》
2. 實測：00631L/00632R是否對TSMC(2330)造成同樣的收盤拍賣掠奪效應
3. 執行面討論：兩次成交平均參考價的概念套用在使用者自己手動下單
4. **新發現的production問題**：execution_plan.json在本次對話期間被重新產生，用的是過期預設workbook持股
5. 本次session的檔案異動清單
6. 對應memory索引
7. 未完成/刻意不做的事項

---

## 1. 論文審查：arXiv:2608.03703《Preying on Leveraged ETFs》

使用者提供PDF：`C:\Users\isaac\Downloads\2608.03703.pdf`（Yinhong Zhao, Princeton, 2026-08-04, 131頁）。

**核心論點**：槓桿型ETF(LETF)每日收盤前必須依當日報酬率方向、以`L²−L`倍資產規模在收盤拍賣中交易，而「當日報酬率」正是用收盤價本身衡量——LETF提交給收盤拍賣的需求曲線隨價格上升而增加。這種「在自我參照價格上執行的向上傾斜需求」會讓收盤價系統性過度反映公開消息、隔日折返，且**不需要任何操縱者存在**，唯一門檻是`loop gain ℓ = Λc × K`（收盤拍賣價格衝擊 × 全球追蹤同一標的的槓桿資金規模）夠大。

**韓國案例**：2026/5/27上市三星電子、SK海力士單股2倍LETF後，SK海力士「預先可算出的收盤訂單/實際收盤拍賣成交值」中位數達1.02（訂單常常大過整個拍賣）。結果：多增加47個年化波動百分點，8週內從持有人(92%散戶)手中轉移約韓元4兆(US$26億)。

**三種政策槓桿排名**：(1)降槓桿倍數/容量目標制——效果最強最乾淨；(2)分散執行時段(韓國實際採用的方案)——**可能適得其反**，訂單移出流動性最深的收盤拍賣，除非切成夠多份否則淨效果惡化；(3)改變參考價(兩日均價或雙收盤價平均)——論文最推薦，用算術方式讓套利者「拉動一個收盤價只影響一半的參照值」，不依賴場所深度。

完整摘要已寫入對話記錄，未另存獨立檔案（本文件即為書面記錄）。

---

## 2. 實測：00631L/00632R vs TSMC(2330)

**動機**：00631L追蹤台灣50指數(50檔成分股)而非單一個股，理論上稀釋了機械性再平衡壓力；但台積電(2330)長期佔台灣50指數權重35–50%，是壓倒性最大成分股，00631L的再平衡訂單實際上大部分打在2330的收盤拍賣上——結構上比論文所說「指數型LETF天然良性」更接近韓國單股集中案例，值得實測而非直接套用論文對美國指數複合體的良性結論。

**資料限制**：本專案DB（`FinRL/data/stock_data.db`, DuckDB）**沒有**00631L/00632R的AUM/NAV資料，也**沒有**TWSE收盤拍賣層級的細節資料（只有全日OHLCV）。因此無法直接複製論文的saturation ratio，只能做reduced-form代理測試。

**方法**：仿照論文的識別策略，用隔夜美股科技/半導體指數報酬(SOXX/QQQ/^IXIC，本專案DB的`external_market_ohlcv`已有現成資料)當公開消息工具變數，檢驗2330當日收盤是否對此過度反映、隔日是否折返；用2317(鴻海)、2454(聯發科)、2412(中華電，透過yfinance額外抓取，快取在`research/shadow/_cache/`)當低權重對照組；用00631L+00632R合計成交值當「劑量」代理變數。

**腳本**：`scripts/evaluate/letf_close_auction_overshoot_reversal_test.py`（新增，read-only，不動production DB）
**報告**：`research/shadow/LETF_CLOSE_AUCTION_OVERSHOOT_REVERSAL_TEST_20260805.md`（新增）

**結果：乾淨的空結果，已收手**：
- 2330隔日報酬對隔夜消息的迴歸係數 β = −0.01 到 −0.03，t值−0.2到−1.3，三個工具變數下p值全部>0.17(n≈3060, HAC/Newey-West標準誤)——對比論文韓國受害股票的−1.85(t=−2.98)，完全不是同一量級。
- 依00631L/00632R成交值劑量分組：折返係數幾乎無差異(−0.011 vs −0.011)。
- 依2020年前後分組(00631L規模大幅成長分界)：折返點估計反而**變弱**，跟loop gain假說方向相反。
- 對照組也無折返訊號。
- **關鍵ceiling比較**：00631L+00632R合計日成交值即使在2026年高峰也只佔TSMC自身全日成交值的約10–15%（80.7億 vs 744.3億台幣/日）——這已是最寬鬆的上限估計，仍遠低於韓國SK海力士飽和度中位數1.02的門檻。

已寫入memory `project_preying_on_letfs_2608.03703_overshoot_reversal_test_20260805.md`，MEMORY.md索引已更新。**除非00631L規模相對TSMC流動性成長一個數量級以上，否則不建議重測**。

**追加：直接測0050**（同一session，使用者追問「00631L/00632R對映0050也沒有影響？」後追加）。00631L實務上主要用台灣50期貨複製槓桿，不是直接買賣0050持股或50檔成分股本身，所以0050只是間接代理，但仍是最直接可測的對映標的。用同一支腳本加入`0050.TW`（來自`ohlcv`表）當target，結果比2330更乾淨的空結果：隔日折返係數 β=+0.005到−0.010，|t|<0.6，三個工具變數下p值全部>0.6（n≈3060）。0050是台灣流動性最高的ETF，比TSMC更不可能被00631L/00632R的規模影響。

---

## 3. 執行面討論：兩次成交平均參考價套用在使用者自己手動下單

論文推薦的「兩次成交平均當參考價」是**基金NAV計價機制**層級的補救(Yuanta才有權限改)，不是使用者能動的東西。討論後確認使用者想套用的範圍是**自己手動下單執行00631L/00632R的方式**，而非策略內部訊號計算或程式碼修改。

**沒有修改任何程式碼**，純執行建議：針對第4節那筆待決交易(賣00631L、賣00679B、買00632R)，建議分兩個參考點執行（例如盤中連續交易時段一部分、接近收盤一部分，或跨兩個交易日），而非全部集中在13:25–13:30收盤集合競價那五分鐘。**明確跟使用者說清楚**：這是通用執行風險管理做法（該筆交易換手率80%+本身偏大，分批降低自己造成的市場衝擊），**不是**第2節驗證出的LETF-loop機制需要的防禦——今天的空結果代表目前沒有偵測到論文講的機械性收盤操縱現象存在於00631L/2330。論文明確警告「分散執行時段在loop gain夠大時反而會惡化」的前提是機構規模、自我指涉的強制性訂單，不適用於使用者這種對TWSE收盤拍賣毫無價格影響力的下單量。

---

## 4. 新發現的production問題：execution_plan.json再次用到過期預設持股

**這不是本次對話任何操作造成的**，是準備交接記錄時盤點repo現況才發現的，但因為牽涉真實交易決策，必須立刻記錄並告知使用者。

**現況**：`report/group_a_plus/latest/execution_plan.json`的`metadata.timestamp`顯示`2026-08-05T16:34:04`——即**本次對話進行期間**，這份檔案被重新產生過。但它的`data.current_holdings`是：

```
{'0050.TW': 1342, '00631L.TW': 0, '00632R.TW': 0, '00679B.TWO': 5000}
```

這**正是**前一個session（同一天稍早，見`GROUP_A_PLUS_20260805_TRIPLE_DIRECTION_AUDIT_AND_OPS_FIXES_HANDOFF.md`第3節）記錄過的、`execution_plan.py`的`DEFAULT_WORKBOOK`常數指向的過期workbook（`taiwan_stock_20260619.xlsx`，已過期一個多月）持股數字——**不是**真實持股。

真實持股（確認來源：`taiwan_stock_20260804.xlsx`，mtime `Aug 4 17:04`，目前仍是最新一份，本次盤點已重新核對）：

```
{'0050.TW': 3834, '00631L.TW': 800, '00679B.TWO': 3000, '00632R.TW': 0}
```

前一個session已經用`--holdings-json results/group_a_plus_holdings_20260804.json`帶入正確數字修復過（見`feedback_execution_plan_workbook_default_stale.md`），但某次之後的`execution_plan.py`重跑（16:34，很可能是使用者自己或`run_daily.bat`觸發，不是自動化管線的一部分——`execution_plan.py`本來就不在`run_ncf_daily_pipeline.py`裡，見前一份handoff第4節）**沒有帶`--holdings-json`**，於是又落回過期預設值。

**目前這份`execution_plan.json`的建議交易(`target_weights`: 0050=30%、00632R=27.08%、其餘0%、cash=42.92%)是基於錯誤的持股基礎算出來的，數量不能拿來對照真實持股執行**（因為它以為你持有0050=1342股/00631L=0股/00632R=0股/00679B=5000股，跟你實際持有的完全不同）。另外這次guard多了一個新原因：`required strategy sources are stale or missing: ['institutional_0050']`——查了一下，`institutional_data`表裡`0050.TW`最新日期是2026-08-04，比對到2026-08-05執行時差一天，屬於盤後資料延遲的正常時間差，不是新bug。

**我沒有自己重新產生這份檔案**（這是會改變「正式建議」的動作，留給使用者決定要不要做）。如果要修正，做法跟前一個session一樣：

```
python group_a_plus/operations/execution_plan.py --holdings-json results/group_a_plus_holdings_20260804.json ...(其餘既有參數)
```

前提是要先確認`taiwan_stock_20260804.xlsx`仍是目前最新（本文件寫成當下確認是），如果之後有更新的workbook要換成對應的holdings-json。

---

## 5. 本次session的檔案異動清單

| 檔案 | 性質 |
|---|---|
| `scripts/evaluate/letf_close_auction_overshoot_reversal_test.py` | 新增，研究用，read-only查DB+yfinance抓對照組，不寫production DB |
| `research/shadow/LETF_CLOSE_AUCTION_OVERSHOOT_REVERSAL_TEST_20260805.md` | 新增，實測報告 |
| `research/shadow/_cache/*.csv` | 新增，2317/2412/2454/QQQ/IXIC控制組價格快取，純本地快取檔 |
| 本檔案 | 新增，交接記錄 |

**沒有修改任何production程式碼或既有report/latest/下的檔案**。第4節提到的`execution_plan.json`異動不是本次對話造成的（時間點在對話期間但不是我執行的操作）。

repo working tree裡還有大量**跟本次對話無關**的既有未commit異動（前幾天/今天其他session、每日自動化管線產生的report快照等），本文件不逐一盤點，沿用之前handoff的既有記錄。

---

## 6. 對應memory索引

- `project_preying_on_letfs_2608.03703_overshoot_reversal_test_20260805.md`（本次新增，第2節對應）

---

## 7. 未完成/刻意不做的事項

- **execution_plan.json過期持股問題（第4節）**：發現但沒有修復，留給使用者決定是否要重新產生正確版本，以及要不要進一步查是什麼觸發了16:34那次沒帶`--holdings-json`的重跑（避免下次再犯）。
- **execution_plan.json原本那筆待決交易本身**（08-04用正確持股產生的版本：賣800股00631L、賣3000股00679B、買5002股00632R避險，因換手率80.84%卡在manual_review_required）：交易與否仍是使用者的決定，沒有被本次對話觸碰或推翻——但**現在這份檔案已經被錯誤持股的版本覆蓋掉了**，如果要參考08-04那個正確版本的建議，需要重新用正確holdings-json產生，或從git歷史/前一份handoff文件裡找回原始數字。
- **前一session未commit的5個bug修復檔案**：仍未commit，本次對話沒有要求commit。
- **`institutional_0050`一天延遲的guard新增原因**：只做了初步查證（盤後資料時間差），沒有深入追蹤是否該調整guard的容忍窗口。
