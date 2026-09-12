# Group A+ 2026-08-10 交接記錄：arXiv:2301.03186論文審查 + compounding_regime分類器controlled test

Status：單一session完整內容，本文件是最終版本，所有小節都已更新到跟現況一致。

## 目錄

1. 論文審查：arXiv:2301.03186《Long-Term Returns Estimation of Leveraged Indexes and ETFs》
2. 關鍵釐清：跟已採用的2504.20116是否矛盾（第一輪回答誤判，本節已更正）
3. 實作一：`letf_quadratic_bound.py`封閉式界限模組
4. 實作二：第一輪crosscheck（`evaluate_00631l_quadratic_bound_regime_crosscheck.py`）
5. 實作三：controlled test（`evaluate_00631l_regime_lift_vs_trend_baseline_20260810.py`）——推翻第一輪的表面結論
6. 最終判定
7. 本次session的檔案異動清單
8. 對應memory索引
9. 未完成/刻意不做的事項

---

## 1. 論文審查：arXiv:2301.03186《Long-Term Returns Estimation of Leveraged Indexes and ETFs》

使用者提供PDF：`C:\Users\isaac\Downloads\2301.03186.pdf`（Hayden Brown, University of Nevada Reno, 2023, 23頁）。

**核心論點**：給定標的指數日對數報酬的上下界`y0 ≤ Yi ≤ y1`，推導出槓桿ETF累積對數報酬的**二次型解析上下界**（Theorem 1-4，非統計近似，是嚴格數學界限），只用兩個聚合統計量表示：`m1`（日對數報酬平均）、`m2`（日對數報酬平方的平均，等價於`s²+m1²`，`s`是標準差）。

主要應用（Section 4）：
- 2x/3x正向槓桿ETF要贏過標的指數，`s`必須低於某門檻（S&P500年化log-return≥.0658、費用率.95%、日跌幅≥-20%時，2x的門檻約`s≤.0125`）。
- -3x反向槓桿ETF要贏過「放空標的」，同樣是`s`低於門檻的條件（標的跌10%+/63交易日、日漲幅≤15%、`s≤.015`時，-3x ETF報酬保證≥1.5倍放空報酬）。
- `0<L<1`（固定比例+現金再平衡）要輸給100%持有標的，需要`s`超過很高的門檻（日頻約`.02`）——用來論證「降低曝險去做再平衡」在正常波動度下不划算。

Remark 2給出一個關鍵簡化：把sup/inf運算裡的自由變數`y`直接取0（而非真正求解supremum），係數簡化成`a0 = (1/y0)(log(1+L(exp(y0)-1))/y0 - L)`、`b0 = L`、`c0 = 0`。論文自己在Section 4.3.1驗證過，真正的supremum數值上非常接近`y=0`，所以這個簡化是有依據的實務近似，不是隨便省略。

## 2. 關鍵釐清：跟已採用的2504.20116是否矛盾

**第一輪回答的錯誤**：一開始把這篇論文框成跟已經導入的2504.20116《Beyond the Volatility Drag Paradigm》（見`GROUP_A_PLUS_00631L_LEVERAGED_COMPOUNDING_REGIME_HANDOFF_20260713.md`、`docs/a2120_letf_compounding_regime_shadow_20260715.md`）互相矛盾的兩派，因此一開始建議直接關閉不採用。使用者追問「沒有值得參考的部份？」後重新檢查，發現這個框架是錯的。

**數學事實**：槓桿ETF累積對數報酬是`Σ log(1+L(exp(Yi)-1))`，對每日報酬`Yi`的**加總**——加法/乘法交換律保證這個總和只取決於`{Yi}`這個多重集合本身（也就是`m1`、`m2`這兩個聚合統計量），跟`Yi`的時間順序完全無關。也就是說，「趨勢持續」vs「均值回歸」這兩種路徑形狀，在數學上**不可能**透過重新排列同一組已實現報酬去改變終值。

**推論**：`leveraged_compounding_regime.py`裡的regime classifier（AR1/variance_ratio/trend_persistence等6個特徵）真正能提供價值的唯一途徑，是把它當成「**未來**窗口`(m1,m2)`會落在哪裡」的**領先指標**，而不是「路徑形狀本身直接影響終值」（這條路徑在數學上不成立）。2301.03186提供的正是「(未來m1,m2) → 保證的槓桿ETF表現區間」這個映射公式——兩篇論文是互補（一個給forecast、一個給後端映射），不是互斥。

這個釐清本身沒有改變任何production行為，但讓後續的驗證方向變得明確：**可以用2301.03186的公式直接測試regime classifier有沒有在做它宣稱在做的事**。

## 3. 實作一：`letf_quadratic_bound.py`封閉式界限模組

新增`group_a_plus/integrations/letf_quadratic_bound.py`：純函式模組，實作Theorem 1 + Remark 2（`y=0`近似）。

- `remark2_lower_bound_coeffs(leverage, y0)`：回傳`(a0, b0=leverage, c0=0)`，要求`leverage>1`且`log(1-1/leverage) < y0 < 0`。
- `quadratic_lower_bound_log_return(m1, m2, n, coeffs)`：回傳`n*(a0*m2+b0*m1+c0)`——`n`日累積對數報酬的下界估計。函式docstring明確標註：只有當窗口內每日報酬都`≥y0`時，這才是**嚴格保證**；否則是可用的連續評分函式，不是保證。

新增`tests/test_letf_quadratic_bound.py`（4個測試，全過）：
- 用論文自己的S&P500範例（`L=2, y0=log(0.8)`）手算驗證`a0≈-1.29614`、`b0=2`、`c0=0`。
- 驗證domain檢查（`y0`超出`(log(1-1/L), 0)`範圍要raise ValueError）。
- 驗證`m1=m2=0`時下界為0、下界對`n`線性縮放。

## 4. 實作二：第一輪crosscheck

新增`scripts/evaluate/evaluate_00631l_quadratic_bound_regime_crosscheck.py`（研究用，不動production DB、不接daily pipeline）。

**方法**：對`leveraged_compounding_regime.py`用**預設（未調參，跟目前live daily pipeline餵給`execution_guard`的是同一套）**閾值分類出來的每一個日期`t`，取**未來**`--horizon`（預設20）個交易日的0050實際對數報酬，算出`forward m1, m2`；用`letf_quadratic_bound`算出`L=2`的下界`paper_lb_cum`，跟`L0×forward_cum_0050`（`L0=1`）比較得到`paper_margin`；同時算出00631L實際forward累積對數報酬跟同樣基準比較的`actual_margin`。`y0`用台股漲跌停±10%當日跌幅下限（TW daily limit，比論文原例的-20%更貼近實際市場）。

**資料**：2015-01-05至2026-08-07，`n=2774`個「有完整forward window」的分類日期。`certified_bound_windows_frac=99.3%`——幾乎所有forward window都沒有觸及-10%跌停下限，代表這個下界在這個樣本裡幾乎都是嚴格保證，不只是啟發式分數。

**結果**（`results/00631l_quadratic_bound_regime_crosscheck_20260810.json`+`.csv`）：
- `corr_paper_vs_actual_margin = 0.81`（整體）——公式本身在真實台股資料上準確追蹤實際表現，數學面站得住腳。
- 表面上regime label方向正確但差距小：TREND_PERSISTENT `actual_favorable_rate=0.671`、`hit_rate=0.862`；MEAN_REVERTING `actual_favorable_rate=0.650`、`hit_rate=0.844`。整體不分regime的基準勝率`0.656`——當時判讀成「大部分favorable結果是base rate」。

## 5. 實作三：controlled test——推翻第一輪的表面結論

使用者要求不要只是標注base rate疑慮，直接做controlled test。新增`scripts/evaluate/evaluate_00631l_regime_lift_vs_trend_baseline_20260810.py`。

**方法**：
1. 用一個**獨立的、簡單的**backward-looking趨勢代理（0050收盤價 vs 自己的200日均線）把第4節的crosscheck資料分層，在「多頭層」跟「空頭層」內部分別比較TREND_PERSISTENT vs MEAN_REVERTING，檢驗regime classifier的優勢是否在控制掉這個簡單濾網後還存在。
2. **修正pseudo-replication**：原始2774筆樣本是逐日滾動20日forward window，相鄰兩筆樣本共用19/20天的forward window，統計上嚴重虛增樣本數（真正的獨立資訊量遠小於2774）。額外用`stride=20`取樣（每20天取一筆），得到`n=139`個真正互相獨立的區塊，作為穩健性檢查。
3. 用`scipy.stats`做two-proportion z-test（勝率）跟`ttest_ind`（連續margin），並在報告裡明確警告重疊樣本的p值低估了真實不確定性。

**結果**（`results/00631l_regime_lift_vs_trend_baseline_20260810.json`）：

| 檢驗 | favorable rate差(TREND−REVERT) | p值 |
|---|---|---|
| 不分層(全樣本，n=2233) | +0.0209 | 0.371（本來就不顯著） |
| 多頭層(n=1638) | +0.0236 | 0.363 |
| 空頭層(n=595) | **-0.0239**（反號） | 0.658 |
| 非重疊獨立樣本(n=139) | **-0.0208**（反號） | 0.829 |

連續margin的t檢定更明顯：全樣本(重疊)看起來「顯著」(`p=0.0074`)，但這正是pseudo-replication造成的假顯著——換到139個真正獨立區塊的樣本後，同一個檢定`p=0.661`，完全不顯著。

**結論**：第一輪crosscheck看到的「TREND_PERSISTENT比較好」的方向性，在(a)控制簡單趨勢濾網、(b)修正pseudo-replication之後，**都不穩定甚至反號**。這代表第一輪看到的0.02差距是雜訊，不是真訊號。

## 6. 最終判定

`compounding_regime`分類器（`leveraged_compounding_regime.py`，目前live但advisory-only，見`GROUP_A_PLUS_00631L_LEVERAGED_COMPOUNDING_REGIME_HANDOFF_20260713.md`、`docs/COMPOUNDING_REGIME_GUARD_REVERTED_TO_ADVISORY_20260809.md`）用arXiv:2301.03186的封閉式公式做交叉驗證後，**沒有找到穩健的預測力證據**——本次的controlled test**強化了**既有的`do_not_promote`判定，而不只是維持中立。這是同一個失敗模式的又一個實例：`feedback_overfitting_fixed_window_tuning.md`跟`project_adaptive_lookback_window_20260809.md`都記錄過類似的「表面訊號是base-rate/過擬合假象」情況，這次多了一個新的具體成因（daily overlapping window造成的pseudo-replication）。

**沒有修改任何production程式碼、沒有動`execution_guard.py`或`execution_plan.py`的既有邏輯，`compounding_regime`的advisory-only狀態不變。** 這條線本次到此收線，除非之後有新證據，不建議再投入。

## 7. 本次session的檔案異動清單

| 檔案 | 性質 |
|---|---|
| `group_a_plus/integrations/letf_quadratic_bound.py` | 新增，2301.03186 Theorem 1/Remark 2封閉式公式，純函式，無production依賴 |
| `tests/test_letf_quadratic_bound.py` | 新增，4個測試，全過 |
| `scripts/evaluate/evaluate_00631l_quadratic_bound_regime_crosscheck.py` | 新增，研究用診斷，read-only查DB |
| `results/00631l_quadratic_bound_regime_crosscheck_20260810.json` + `.csv` | 新增，第一輪crosscheck產物 |
| `scripts/evaluate/evaluate_00631l_regime_lift_vs_trend_baseline_20260810.py` | 新增，研究用controlled test，read-only查DB |
| `results/00631l_regime_lift_vs_trend_baseline_20260810.json` | 新增，controlled test產物 |
| 本檔案 | 新增，交接記錄 |

**本次對話對production的實質異動：無。** 所有新增檔案都是research-only診斷腳本、其輸出、跟對應測試，沒有修改任何既有production程式碼路徑，沒有覆蓋任何`report/group_a_plus/latest/`下的正式檔案。

## 8. 對應memory索引

- `project_2301_03186_quadratic_bound_regime_crosscheck_20260810.md`（涵蓋第1-6節全部內容，含兩輪驗證結果）
- 已連結既有：`project_compounding_regime_guard_reverted_to_advisory_20260809.md`、`project_adaptive_lookback_window_20260809.md`、`feedback_overfitting_fixed_window_tuning.md`、`project_signal_validation_checklist_adopted_20260723.md`

## 9. 未完成/刻意不做的事項

- **沒有把`letf_quadratic_bound.py`的下界公式接到`crash_risk_alert`或`tail_conformal`當worst-case stress test工具**——第一輪回答提過這是理論上可能的殘餘用途，但這次使用者的追問聚焦在「regime classifier到底有沒有用」這個問題上，沒有要求做這個。如果之後要做，公式本身（`remark2_lower_bound_coeffs`+`quadratic_lower_bound_log_return`）已經是現成、有測試的積木。
- **兩支研究腳本沒有pytest測試**（`evaluate_00631l_quadratic_bound_regime_crosscheck.py`、`evaluate_00631l_regime_lift_vs_trend_baseline_20260810.py`）——刻意維持一次性研究診斷腳本定位，只有底層公式模組`letf_quadratic_bound.py`有測試覆蓋。
- **沒有嘗試調整`compounding_regime`的閾值再重跑controlled test**——這次驗證的對象明確是「目前live的預設閾值分類器」，調參後重新尋找訊號屬於`feedback_overfitting_fixed_window_tuning.md`警告過的做法，沒有使用者要求，不主動做。
- **`0<L<1`（降曝險+現金再平衡）那段論文結果沒有實作驗證**——目前系統裡沒有對應的降曝險提案在跑，屬於備而不用的工具，本次沒有花時間做。
- **沒有commit**——使用者沒有要求commit，依既有慣例不主動提。
