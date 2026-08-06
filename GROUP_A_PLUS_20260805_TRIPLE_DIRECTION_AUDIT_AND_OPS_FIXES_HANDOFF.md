# Group A+ 2026-08-04/05 交接記錄：三方向研究稽核 + 兩個真實ops bug修復 + 執行計畫狀態

Status: 完整記錄，避免下次session誤判「還沒做過」或誤信舊的production狀態。

## 目錄

1. 三個研究方向稽核結論（全部「已做過」，附file:line證據）
2. 兩個真實production bug：發現與修復
3. `taiwan_stock_*.xlsx` workbook混亂與正確持股
4. 目前正式`execution_plan.json`狀態（未執行，等待人工複核）
5. 8/5雙策略($1M)預測結果（golden1_0531 vs a2118，未觸碰production）
6. 00632R決策機制根因（PVA/SJM panic-state，對應真實市場事件）
7. 今天的程式碼改動清單
8. 未完成/刻意不做的事項

---

## 1. 三個研究方向稽核結論

使用者原始提案分別叫`A21.19_MultiPeriod_Reentry_Shadow`、`A21.19_Action_Regret_Gate`、`A21.19_Trough_Reentry_Nowcast`——**三個命名都要避開`A21.19`**，這個代號已經是VIX-credit gate那條完全不同的線在用（見`GROUP_A_PLUS_A2119_CONTINUOUS_DEFENSIVE_TILT_SHADOW_HANDOFF_20260724.md`），不是空的。

### Direction 1：多期回補路徑最佳化 / MPC path shadow

**完整做過**。實作：`scripts/evaluate/evaluate_a2118_mpc_path_shadow.py`（2026-07-13建）。

- Docstring原話（line 2-10）：「Each day, the evaluator scores a handful of candidate 00631L exposure paths, executes only the first step, and recomputes on the next day, matching a simple model-predictive-control workflow.」跟使用者的MPC提案逐字對應。
- 路徑集`DEFAULT_PATHS`（line 58-66）：P0_hold ~ P6_half_then_quarter_reentry，另有`conservative`/`disaster`子集，概念對應使用者的P0~P4。
- Utility函式（line 188-220, 490-551）：`terminal_value_delta - lambda_drawdown*drawdown_risk - gamma_turnover*transaction_cost - eta_missed_rebound*missed_rebound`，已包含`transaction_cost`跟`missed_rebound`兩項使用者要求的指標。
- 主評估函式`_build_mpc_targets`/`evaluate_window`（line 1071-1142, 1388-1558）。

**07-13/14既有結論**（`report/group_a_plus/review/md/group_a_plus_20260714_1m_execution_decision_record_20260713.md:231-274`）：直接自動減碼00631L撐不過交易成本；path-value/oracle版本可改善部分風險指標但通常損失終值或過度交易。降為warning-only（`a2118_extreme_risk_warning`+`apply_risk_add_pre_trade_guard`，已在production），不進自動交易。

**2026-08-04用真實非oracle`path_value`模式在`live_2024_2026`/`active_2025_2026`重驗證**：仍虧損（-44,946/-33,348, edge015配置；-162,146/-120,306, 1日oracle前瞻配置）——即使給1日oracle前瞻資訊仍虧損，強化「transaction cost殺死自動交易」結論。

**2026-08-04用2021/2023/2024全新OOS窗口驗證**（結果檔`results/a2118_mpc_path_shadow_pathvalue_alwaysopen_pinned_new_oos_2021_2023_2024_20260804.json`）：gate完全打開（風險門檻放到形同虛設），184/190個golden1+panel日在2021/2023真的完全沒有偏離hold；2024觸發3次，終值虧$10,079（Sharpe+0.0238、MDD+0.0082小幅改善但賠本）。**結論在全新OOS上完整重現，不是7個窗口上調參的過擬合假象**。

**2026-08-05查execution pacing落差**（memory `project_mpc_path_shadow_execution_pacing_gap_20260805.md`）：`evaluate_a2118_mpc_path_shadow.py`的`_simulate_daily_target_weights`（line 599）每次target改變就當天全額rebalance，完全沒呼叫或匯入`group_a_plus/operations/execution_plan.py`。真實生產環境的`_apply_buy_staging`（execution_plan.py line 296）是完全獨立的另一層節流（買進第一天最多執行到缺口的`max_initial_buy_fraction`，預設0.4）。**兩層節流從沒被一起測過，若真接進生產會疊加而非取代，回補速度只會更慢，強化而非推翻既有負面結論**。

### Direction 2：Decision-focused Action Regret / DFL action shadow

**完整做過**。實作：`scripts/evaluate/evaluate_a2118_decision_focused_action_shadow.py`。

- 動作集`DEFAULT_ACTIONS`（line 56）：`KEEP, NO_ADD, CAP10, REENTER, REENTER_00631L_5, REENTER_00631L_10`——`REENTER_00631L_5/10`就是使用者的`REENTER_5/10`；`CAP10`（把00631L超額部位轉移進0050）等同`ROTATE_10_TO_0050`。
- Target（line 247-284, 566-596）：`action_regret = Utility(action) - Utility(KEEP)`，`Utility = log final wealth - MDD penalty - turnover - missed rebound`。用expanding ridge per action預測regret。
- 約束（line 732-805, 880-1049）：`turnover_cap`、`edge_threshold`/`reliability_percentiles`（預測收益要超過門檻才觸發，對應使用者要求的「不確定性緩衝」）、`regret_clip`、KEEP永遠是fallback。

**三分類現狀（2026-08-05核對）**：
- **default_latest**（`results/a2118_decision_focused_action_shadow_dfl_main_latest.json`）：`total_candidate_non_keep_days=0`，完全abstain。
- **best_candidate**（07-14 sweep，`edge0005_adj75`配置，`report/group_a_plus/review/md/a2118_dfl_best_candidate_handoff_20260714.md`）：7個有效非KEEP日（主要是CAP10），觸發`2018-07-27/10-01/10-02/10-04`跟`2025-01-13/01-15/02-21`。但這條延伸線（relief-gate，07-26）後來用**2021真實OOS backfill**驗證，純CAP10反而贏relief-gate版本（ΔSharpe+0.2016 vs +0.1586），判定過擬合收手（`project_spo_dfl_action_value_already_closed_20260727.md`）。
- **production_candidate**：空集合，這整條線從沒被promote，`w7`類權重維持0.0。

**根因（`project_dfl_cross_asset_ablation_reenter_label_degenerate_20260801.md`）**：REENTER在one-step `_apply_action`下的realized-regret恆為0——label本身簡併，不是調參能救的。如果要繼續，第一步是重寫成path-dependent label，不是重新開一套新框架。

### Direction 3：市場低點／Capitulation回補Nowcast / trough_nowcast

**完整做過**。實作：`group_a_plus/integrations/trough_nowcast.py`（07-14建，迭代到v7）。

- 狀態機`TROUGH_STATES`（line 23）：`NO_TROUGH/CAPITULATION_WARNING/PARTIAL_REENTRY/FULL_REENTRY`——比使用者的三態多一個更早期警戒態。
- 特徵清單（TXO put/call、skew、IV期限結構、台指期basis、外資期貨籌碼、漲跌家數、跌停占比、量縮、USD/TWD反轉、TSM ADR/SOX反轉、2330相對強弱）**幾乎全部已有對應計算好的版本**，只缺TXO自己的IV期限結構跟台指期basis兩項。

**重要澄清：trough_nowcast實際上是兩個獨立機制，不要混為一談**：
1. `_trough_nowcast_buy_fraction`（`group_a_plus/operations/execution_plan.py:433, 651`）——**真的是live的**，PARTIAL_REENTRY/FULL_REENTRY時會把買進分批比例(`effective_max_initial_buy_fraction`)從預設0.4拉到最高0.7，真的影響實際下單節奏（**不改變target weight，只改變多快買到target**）。
2. `trough_override_eligibility_shadow.json`（`report/group_a_plus/latest/`）——**這個才是`research_only: true, production_effect: "none"`**，對應`_trough_high_vol_override_watch`函式，docstring明寫「does not alter target shares, trades, or guard decisions」。這是完全不同、範圍更窄的shadow機制。

**FULL_REENTRY狀態**：`trough_nowcast.py:381`有`full_reentry_disabled_reason: "shadow_audit_false_reentry_rate_too_high"`標記，但不是硬kill-switch，是判定條件本身設計得極難同時滿足（今天2026-08-04真實訊號卡在`risk_unwind_confirm: false`）。

**經濟價值**：原始9窗口研究（`project_trough_reentry_2509_05922_review_20260727.md`）：+1527.6元/9年/100萬本金，接近雜訊，不建議建新模組。

**2026-08-05追加：breadth_min門檻sweep真實金額驗證**（見memory `project_trough_nowcast_breadth_threshold_dollar_value_20260805.md`）：
- 既有216組param sweep（`results/group_a_plus_trough_nowcast_param_sweep_20260714.json`）發現`breadth_min`(市場參與度門檻)是影響力最大的參數：`breadth_min=0.5`(現行v6)平均false-reentry rate 50.1%，`breadth_min=0.6`只有27.9%。
- 用2021/2023/2024全新OOS重跑216組驗證（`results/group_a_plus_trough_nowcast_param_sweep_with_2021_2023_2024_oos_20260805.json`）：優勢沒有消失（0.5組51.8% vs 0.6組35.5%），甜蜜點候選在三個新年份**一次都沒觸發**，不是過擬合假象。
- **但換算成真實金額後結論反轉**：新增`--sweep-params`選項到`evaluate_group_a_plus_trough_nowcast_buy_attempt_alignment.py`後，同一組7窗口apples-to-apples比較——現行`breadth_min=0.5`：6次`allowed_fast_reentry`事件，+$857.9；`breadth_min=0.6`：2次事件，+$441.2（腰斬）。根因：收緊門檻沒有精準濾掉「假的」事件，是把好壞事件按比例一起濾掉（covid_2020+$334.1、inflation_2022一次+$68.0都被濾掉，只濾掉一次-$3.5的壞事件）。
- **結論：`breadth_min=0.6`不建議採用**，false-reentry rate跟真實金額效益是兩件不完全相關的事。Direction 3到此稽核完整收尾，不建議繼續投入。

---

## 2. 兩個真實production bug：發現與修復

### Bug A：golden1訊號解析被what-if快照污染

**根因**：`group_a_plus/runners/a2111.py:66 _resolve_golden_signal_path()`把curated的`results/group_a_combined_live_latest.json`跟所有`results/signal_group_a_*.json`（含what-if情境輸出）一起丟進候選池，**單純取mtime最新的那個**，不分辨真訊號還是what-if產物。這是2026-07-02 Fable5 audit記錄過的已知「H3」限制（docstring裡有記載，刻意保留、只做稽核可見）。

**具體踩雷**：`results/signal_group_a_20260803_200029.json`（一次what-if run，`override_holdings_source: override_holdings_json`）的mtime比curated pointer新，導致2026-08-04當天任何呼叫`run_a2118()`的評估器（MPC/DFL/trough_nowcast相關）都誤讀到這份快照的00631L=0%基準，跟回測的是哪一年完全無關。

**修復**：
1. `generate_dual_group_signal.py`：`override_holdings_json`不為None時，輸出檔名前綴從`signal_{group}_{timestamp}`改成`whatif_signal_{group}_{timestamp}`，不再匹配`_resolve_golden_signal_path()`的glob pattern。真實(非override)呼叫檔名完全不變。
2. 現有的`results/signal_group_a_20260803_200029.json`(+`.csv`)已重新命名為`whatif_signal_group_a_20260803_200029.*`。
3. `group_a_plus/runners/a2118.py`：`run_a2118()`新增`golden_signal_path_override`參數（additive，預設None不變更任何現有行為），讓研究用途可以釘住特定歷史golden1快照。已串進`evaluate_a2118_mpc_path_shadow.py`的`--golden-signal-path`。

**已驗證**：真實production的`execution_plan.json`（08-02產生的，00631L=10.3%正在買進）**沒有受這個污染影響**——這是研究/回測工具鏈的問題，不是live風險。用修好的工具鏈重跑OOS驗證得到本文件第1節Direction 1的最終結論。

### Bug B：五個外部cross-market ticker靜默漂移6-8天

**根因**：`scripts/fetch/fetch_cross_market_ohlcv.py`的docstring自己寫明它**無條件**每天抓一組固定ticker（`^VIX, SOXX, QQQ, ^TWII, TSM, TWD=X`共6個），不像其他NCF模型內部抓取要靠`--refresh-external-cache`/`NCF_EXTERNAL_ALLOW_DOWNLOAD`環境變數才觸發。`^GSPC/^IXIC/^TNX/^IRX/GC=F`這5個不在這張無條件清單裡，只能靠`run_ncf_daily_pipeline.py`裡`name.startswith("ncf_")`的步驟順帶抓——這條路徑不可靠，導致靜默漂移6-8天（`run_daily.bat`確實每天都有帶`--refresh-external-cache`，不是排程沒觸發）。

**修復**：把這5個ticker加進`DEFAULT_TICKERS`，變成跟其餘6個一樣無條件每天抓。`tests/test_fetch_cross_market_ohlcv.py`用set比對常數，2/2測試依然過。

**已驗證**：真實重跑抓取（打yfinance、寫進真實production DB），5個ticker全部回到`last_date: 2026-08-04`；`check_ohlcv_freshness.py`的`overall_status`從error變成ok；正式的`results/ohlcv_freshness_20260804.json`已用真實結果覆蓋。

**下游治理鏈驗證**：手動重放`build_ops_health()`→`classify_risk_mechanism()`→`classify_strategy_trust()`（比照`run_ncf_daily_pipeline.py`同一段邏輯），寫回真實`report/group_a_plus/latest/ops_health.json`跟`strategy_trust.json`。結果：`external_data_freshness_status`從error轉回ok（修復生效），但`trust_level`依然是**ABSTAIN**——這是預期中、有憑有據的，不是殘留bug，因為：
- `ensemble_disagrees=True`：`signal_alignment`的`divergent_sources=['composite_risk_score']`，正是PVA避險層跟基礎多頭模型的真實方向分歧（見第6節）。
- `module_health`還有一個`finbert_sentiment`警告，未查（次要，不影響核心判斷）。
- `system_resources`那項error**沒有查也不會查**——見memory `feedback_no_disk_warning_topic`，使用者明確要求不要碰、不要提磁碟話題。

`report/group_a_plus/latest/deployment_consistency_review.json`/`daily_status.json`/`promotion_gate`等更下游的治理鏈**沒有**連帶重新產生，只有ops_health/risk_mechanism/strategy_trust三個被手動重放過。

---

## 3. `taiwan_stock_*.xlsx` workbook混亂與正確持股

**發現**：repo根目錄有多份`taiwan_stock_*.xlsx`，格式、持股數字都不一樣，不是同一份的版本演進：

| 檔案 | 格式 | 持股(0050/00631L/00679B) |
|---|---|---|
| `taiwan_stock_20260619.xlsx`（`execution_plan.py`的`DEFAULT_WORKBOOK`） | 有「Group A++」標籤區塊 | 1342/0/5000（已過期一個多月） |
| `taiwan_stock_20260804.xlsx` | **沒有**Group A++標籤，欄位是完全不同的8檔ETF組合(0050/0056/0063L/00646/00679B/00713/00751B/00878) | 3834/800/3000 |
| `taiwan_stock_20260516_group.xlsx` | 基礎Group A模型用的workbook | （5月16日的，另一組） |

**使用者裁決（2026-08-04）**：「日期最新的才是」——`taiwan_stock_20260804.xlsx`的持股（0050=3834、00631L=800、00679B=3000、00632R=0）才是真實當下持倉。

**處理方式**：因為`taiwan_stock_20260804.xlsx`結構跟`execution_plan.py`的`_parse_group_a_plus_holdings`解析器不相容（直接傳`--workbook`會ValueError），改用`--holdings-json results/group_a_plus_holdings_20260804.json`帶入正確數字，**沒有**修改使用者的workbook本身，也**沒有**動`execution_plan.py`的解析邏輯。

**過程中的意外**：曾經誤用`--workbook taiwan_stock_20260804.xlsx`直接呼叫，導致正式`execution_plan.json`短暫變成`success:false`的壞狀態，隨即用`--holdings-json`修復回正確狀態。**目前正式`execution_plan.json`是健康、有效的**，見第4節。

**教訓**（memory `feedback_execution_plan_workbook_default_stale.md`）：以後任何要重跑`execution_plan.py`產生真實計畫的場合，先跑`ls -la taiwan_stock_*.xlsx`看哪份mtime最新，不要相信`DEFAULT_WORKBOOK`常數。

---

## 4. 目前正式`execution_plan.json`狀態

`report/group_a_plus/latest/execution_plan.json`（最後一次於2026-08-04用正確真實持股產生，`holdings_source: results/group_a_plus_holdings_20260804.json`）：

- `execution_regime: golden1`
- `current_holdings: {0050.TW: 3834, 00631L.TW: 800, 00632R.TW: 0, 00679B.TWO: 3000}`
- `target_weights: {0050: 30%, 00631L: 0%, 00632R: 27.08%, 00679B: 0%, cash: 42.92%}`
- **建議交易**：賣2371股0050、**全部賣光800股00631L**、全部賣光3000股00679B、買進5002股00632R
- `execution_allowed: False`, `manual_confirmation_required: True`, `planning_status: manual_review_required`
- 原因：`execution_guard_reasons: ["turnover ratio 80.84% exceeds automatic limit 50.00%"]`

**這份計畫完全沒有被執行**，交易決定留給使用者。如果之後這份計畫被重新produce（例如今晚自動化管線跑execution_plan.py——但目前它**不是**自動化管線的一部分，見下方），數字會不一樣，要重新核對。

**重要**：`group_a_plus/operations/execution_plan.py`**不是**`run_ncf_daily_pipeline.py`(104步自動化管線)的一部分——整份`logs/daily.log`裡完全沒有呼叫它的紀錄。它是需要手動另外執行的一步，自動化管線只會讀取現有的`execution_plan.json`當輸入，並正確地每天標記`execution_plan_date_mismatch`直到有人手動重跑。**這不是bug，是設計上的兩步驟分離**，但代表如果放著不管，`execution_plan.json`會持續過期，`daily_status`會持續是`block`狀態。

---

## 5. 8/5雙策略($1M)預測結果（未觸碰production）

使用者的固定請求模式：「使用golden1_0531及最新策略，以1百萬，預測X日」。這次確認「1百萬」= 真實持股之外**另加**$1,000,000現金（總規模$1,490,962 = 真實持股市值~$49萬 + $100萬現金）。

**golden1_0531**（`generate_dual_group_signal.py --group group_a --result-json results/group_a_backtest_20250101_20260531_20260609_214023.json --live-start --extra-cash 1000000 --override-holdings-json '{"0050":3834,"00631L":800,"00679B":3000}' --as-of-date 2026-08-05`，輸出`results/whatif_signal_group_a_20260804_233152.json`）：

- PVA疊加層判定進入M(panic)狀態
- 目標：0050 35.5%(5251股，買1417股)、**00631L 7.0%(3246股，加碼2446股)**、00679B 0%(全賣3000股)、00632R 27.5%(38640股，避險)

**最新策略/a2118**（`execution_plan.py --holdings-json ... --cash-balance 1000000 --as-of 2026-08-05`，output/latest-pointer導向scratch，**沒有**動production，輸出`results/group_a_plus_a2118_predict_20260805_1m_scratch.json`）：

- 目標：0050 30%(4078股，買244股)、**00631L 0%(全賣800股)**、00679B 0%(全賣3000股)、00632R 27.1%(15192股，避險)
- `execution_allowed: True`（加了$1M現金稀釋換手率，跟第4節真實production那份不同，這份不需要人工複核）

**分歧**：兩邊在00631L方向完全相反（golden1_0531加碼 vs a2118全出清），其餘方向一致（賣00679B、買00632R避險）。**這不是需要「解決」的問題**——a2118（Group A+）才是正式生效的主動策略（`project_a2118_upgrade.md`，06-28/29正式升級），golden1_0531是參考基準，不是實際部署的東西。分歧只是提醒00631L這部分共識較弱，不需要調和兩個模型。

---

## 6. 00632R決策機制根因

真實生效訊號裡00632R(反向ETF)出現27%配置，查證結果：

- **不是bug，不是資料髒污**。基礎Group A PPO模型本身輸出純多頭action（0050 50%/00631L 20%/cash 30%）。
- 獨立的PVA(Price-Volume-Acceleration)/SJM風控覆蓋層（`train_dual_group_2024_2026.py`的`_sjm_state`/`_pva_risk_scaled_weights`）偵測到0050的63日動能加速度z-score(`a_z`)跌破-2.0門檻（2026-08-04讀數-3.70，07-30最深到-4.45），觸發「M」(panic)狀態，`hedge_signal=0.90`，疊加避險部位。
- **直接從DB拉0050真實價格驗證**：0050在2026-07-16到07-30之間真的下跌約12%（106.40→93.50），08-04僅反彈回100.65，還沒完全收復。PVA的panic訊號是對這次真實市場修正的正確反應。
- 這也是`strategy_trust.json`裡`ensemble_disagrees=True`（`divergent_sources=['composite_risk_score']`）的真正原因——PVA避險層跟基礎多頭模型方向不同調，是真實分歧不是雜訊。
- `^GSPC`等5個外部ticker(第2節Bug B)只餵NCF/2330層，**跟這個PVA/00632R機制完全獨立無關**——這是查證過程中一度誤判的因果關係，已在對話中更正。

---

## 7. 今天的程式碼改動清單

| 檔案 | 改動 | 性質 |
|---|---|---|
| `group_a_plus/runners/a2118.py` | `run_a2118()`新增`golden_signal_path_override`參數 | additive，預設None不變更行為 |
| `scripts/evaluate/evaluate_a2118_mpc_path_shadow.py` | 新增`--golden-signal-path` CLI flag | additive |
| `generate_dual_group_signal.py` | what-if輸出檔名加`whatif_`前綴 | 只影響`--override-holdings-json`不為空的呼叫 |
| `scripts/fetch/fetch_cross_market_ohlcv.py` | `DEFAULT_TICKERS`加5個ticker | 擴大每日無條件抓取範圍 |
| `scripts/evaluate/evaluate_group_a_plus_trough_nowcast_buy_attempt_alignment.py` | 新增`--sweep-params` CLI選項+`_build_trough_state_with_params`輔助函式 | additive，預設None不變更行為 |

所有改動都經過相關pytest驗證（`test_evaluate_a2118_mpc_path_shadow.py`、`test_group_a_plus_latest_strategy.py`、`test_fetch_cross_market_ohlcv.py`、`test_evaluate_group_a_plus_trough_nowcast_buy_attempt_alignment.py`皆通過），且用真實資料重跑驗證過效果（不只是compile-check）。

**未commit**——這些改動目前都是working tree裡的uncommitted修改，使用者沒有要求commit。

---

## 8. 未完成/刻意不做的事項

- **執行計畫決定**：第4節那份`manual_review_required`計畫，交易與否留給使用者，我沒有執行。
- **Direction 5（尚未做過的策略層研究）**：使用者提出的5個方向裡，第5個需要使用者提供具體研究來源/清單才能查，目前空著。
- **完整治理鏈重新產生**：`deployment_consistency_review.json`/`daily_status.json`/`promotion_gate`等比`ops_health`/`strategy_trust`更下游的環節，今天的兩個bug修復**沒有**連帶重新產生，下次完整跑`run_ncf_daily_pipeline.py`才會反映。
- **`finbert_sentiment`模組警告**：`ops_health.json`的`module_health`裡還有這個未查的警告，次要，未影響今天任何結論。
- **`system_resources`磁碟錯誤**：刻意不查、不提，見memory `feedback_no_disk_warning_topic`。
- **殘留檔案**：`results/whatif_signal_group_a_20260803_200029.json`(+`.csv`)只是重新命名，沒有刪除，還在`results/`底下。

---

## 對應的memory索引（同一批寫入，2026-08-04/05）

- `project_mpc_path_shadow_prior_art_20260713_20260804.md`
- `project_golden1_signal_resolution_whatif_pollution_20260804.md`
- `project_external_cross_market_ticker_staleness_fix_20260804.md`
- `feedback_execution_plan_workbook_default_stale.md`
- `project_mpc_path_shadow_execution_pacing_gap_20260805.md`
- `project_trough_nowcast_breadth_threshold_dollar_value_20260805.md`

（本文件是這一批的統一索引/完整版，個別memory檔案是精簡版，兩邊互相連結。）
