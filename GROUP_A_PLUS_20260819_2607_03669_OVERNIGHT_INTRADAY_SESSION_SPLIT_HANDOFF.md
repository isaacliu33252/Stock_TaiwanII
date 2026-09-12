# Group A+ 2026-08-19: arXiv:2607.03669 Overnight/Intraday Session-Split Review

**日期**：2026-08-19
**論文**：arXiv:2607.03669 — overnight vs intraday return should not be treated as the same
stochastic process; the two sessions have significantly different tail heaviness, and
mixing them distorts dynamic-correlation estimation. Method only needs daily open/close.
**使用者提案**：把「一天」拆成overnight（今天open/昨天close-1）與intraday（今天close/今天open-1）兩段，分別建regime，第一階段不用ML，先做4類事件表（GapDown+IntradayUp / GapDown+IntradayDown / GapUp+IntradayUp / GapUp+IntradayDown），測00631L/0050 next 1/3/5d跟future drawdown，「如果四類差異很大，再值得建正式模型」。
**結論**：**Phase 1 gate測試沒過，不建正式模型，closed research_only。**

## 1. Repo查證

搜尋`overnight_return`/`intraday_return`/`gap_down`/`gap_up`/`session_split`等關鍵字，全repo唯一相關命中是`group_a_plus_second_stage_execution.py`裡的`pause_open_gap_down`——這是純**執行層**的當日開盤跳空暫停下單機制（`open_gap_pct <= gap_down_threshold`時暫停執行，見該檔案56行、99-146行），跟這次提案的「overnight/intraday事件分類+forward return預測研究」是完全不同的東西，不衝突也不重複。確認是全新角度。

## 2. 資料可行性

`FinRL/data/stock_data.db`的`ohlcv`表本來就有`open`欄位（連同`high`/`low`/`close`/`volume`/`dividends`/`stock_splits`）：
- `0050.TW`：2009-01-02 ~ 2026-08-18，4,314筆
- `00631L.TW`：2014-10-23 ~ 2026-08-18，2,882筆
- 兩者`stock_splits`欄位全期間皆為0（無分割事件需要額外處理，不用擔心機械性缺口污染分類）

## 3. 方法

```python
overnight_ret = today_open / yesterday_close - 1   # 用0050自身的open/close，作為台灣市場代表
intraday_ret  = today_close / today_open - 1
```

事件分類用0050自身的overnight/intraday組合（不是TSM ADR/SOX/NVDA等外部代理——那些是"為什麼"會有gap的成因鏈，這次分類直接用結果端0050自己的open/close，跟使用者原始提案一致，先看有沒有可觀測的預測力，不先假設外部驅動因子）。

Forward return（00631L跟0050各自，用各自的close-to-close）：
- `fwd_ret_{1,3,5}d` = `close.shift(-h)/close - 1`
- `fwd_min_ret_5d` = 未來5天累積報酬路徑的最小值（近似forward drawdown代理）

用共同歷史區間（0050∩00631L，2014-10-23~2026-08-18，n=2,876天）。

## 4. 第一輪：全樣本、單純正負號分4類

```
event
GapDown+IntradayDown    784
GapUp+IntradayUp        780
GapUp+IntradayDown      678
GapDown+IntradayUp      634
```

| Event | n | mean_overnight | mean_intraday | mean_cc | fwd1_0050 | fwd3_0050 | fwd5_0050 | fwdmin5_0050 | fwd1_631L | fwd3_631L | fwd5_631L | fwdmin5_631L |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| GapDown+IntradayDown | 784 | -0.48% | -0.57% | -1.05% | 0.05% | 0.24% | 0.38% | -1.06% | 0.14% | 0.34% | 0.61% | -2.11% |
| GapDown+IntradayUp | 634 | -0.53% | 0.51% | -0.02% | -0.02% | 0.13% | 0.35% | -1.14% | -0.14% | 0.18% | 0.63% | -2.18% |
| GapUp+IntradayDown | 678 | 0.58% | -0.51% | 0.07% | 0.16% | 0.26% | 0.36% | -1.00% | 0.36% | 0.60% | 0.74% | -1.87% |
| GapUp+IntradayUp | 780 | 0.64% | 0.64% | 1.28% | 0.09% | 0.24% | 0.37% | -0.97% | 0.12% | 0.35% | 0.50% | -1.99% |

**ANOVA檢定（4類是否有顯著差異）**：
- 0050 fwd5: F=0.020, **p=0.9963**
- 0050 fwdmin5: F=0.897, p=0.4421
- 00631L fwd5: F=0.157, p=0.9251
- 00631L fwdmin5: F=0.381, p=0.7667

四類forward報酬/drawdown幾乎完全重疊，無統計證據支持任何差異。

## 5. 第二輪：使用者具體舉例的「shock」版本

原文例子：「Overnight shock down + Intraday strong reversal」vs「Overnight shock down + Intraday continued liquidation」，兩者close-to-close都可能是-3%但經濟意義應該不同。

用`overnight_ret <= -1%`篩選出gap-down shock（n=213天），再依intraday方向細分（`intraday_ret > +0.5%`=reversal, `< -0.5%`=continuation, 其餘=flat）：

```
GapDown shock (overnight<=-1%) days: 213
  flat (n=101) / IntradayUp_reversal (n=59) / IntradayDown_continuation (n=53)
```

| bucket | n | mean_overnight | mean_intraday | mean_cc | fwd1_0050 | fwd3_0050 | fwd5_0050 | fwdmin5_0050 | fwd1_631L | fwd3_631L | fwd5_631L | fwdmin5_631L |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| IntradayDown_continuation | 53 | -1.86% | -1.42% | -3.25% | 0.08% | 0.47% | 1.08% | -1.58% | -0.32% | 0.10% | 1.47% | -3.61% |
| IntradayUp_reversal | 59 | -2.12% | 1.23% | -0.92% | -0.07% | 0.29% | 0.61% | -1.66% | -0.08% | 0.58% | 1.53% | -3.12% |
| flat | 101 | -1.69% | -0.01% | -1.70% | 0.00% | 0.40% | 0.27% | -1.41% | -0.01% | 0.62% | 0.36% | -2.84% |

**t-test（continuation vs reversal，Welch's）**：
- 0050 fwd1: t=0.366, p=0.715
- 0050 fwd3: t=0.299, p=0.766
- 0050 fwd5: t=0.679, p=0.498
- 0050 fwdmin5: t=0.133, p=0.894
- 00631L fwd1: t=-0.233, p=0.817
- 00631L fwd3: t=-0.363, p=0.718
- 00631L fwd5: t=-0.038, p=0.970
- 00631L fwdmin5: t=-0.365, p=0.716

全部p>0.49，沒有一個接近0.05。方向上continuation組的fwd5/fwd3甚至略優於reversal組（跟直覺「繼續破底應該更差」相反），但差異在統計上完全無法跟雜訊區分（n=53 vs 59，標準誤遠大於組間差異）。

**GapUp shock對照組**（`overnight_ret >= +1%`，n=237，continuation n=78/reversal n=48）同樣做t-test：
- 0050 fwd5: t=1.108, p=0.271
- 0050 fwdmin5: t=0.517, p=0.607
- 00631L fwd5: t=0.608, p=0.545
- 00631L fwdmin5: t=0.271, p=0.787

同樣無顯著差異。

## 6. 結論

使用者自訂的phase 1 gate是「如果四類差異很大，再值得建正式模型」。這次無論用哪一種分類粒度（全樣本正負號 / shock門檻+reversal-continuation細分），0050跟00631L的forward 1/3/5天報酬、forward 5天drawdown代理，在4類事件之間都**沒有統計上可分辨的差異**（ANOVA p=0.44~0.996；t-test p=0.27~0.97）。

**不建議進入第二階段**（正式regime模型/動態相關性估計）——至少用「overnight/intraday組合預測未來報酬」這個具體應用方向，在GroupA+實際交易的0050/00631L上不成立。

**重要澄清（不是推翻論文本身）**：2607.03669論文的核心發現是「兩個session的tail heaviness/動態相關性估計不應該混在一起」，這是關於**報酬分布形狀**（厚尾程度、波動率動態）的統計性質，跟這次測的「session組合能否預測forward return」是不同問題。這次的null result只回答了使用者提出的具體應用（事件表預測未來報酬），沒有測試也沒有否定論文原本的「分開估計tail/波動率」主張——如果之後有人想從那個角度（例如VaR/ES計算是否該分session估計）重新評估，屬於不同的研究方向，不受這次結論約束。

## 7. 檔案與可重現性

分析未存成正式repo腳本（純exploratory one-off，符合使用者自己的「phase 1不用ML、先看值不值得」定位）。分析程式碼與中間結果CSV：`/tmp/overnight_intraday_events.csv`（session-scoped temp，非repo正式產出，未來session若要重跑需要重新執行本文件第3-5節的邏輯，資料來源为`FinRL/data/stock_data.db`的`ohlcv`表，query在本文件內完整記錄可直接複製重跑）。

沒有任何repo檔案被建立或修改，未影響任何production程式碼/訊號/執行計畫。
