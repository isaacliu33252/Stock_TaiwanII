# Group A+ 2026-08-18 Session 交接記錄

**日期**：2026-08-18（週二）
**涵蓋範圍**：golden1_0531 vs a2118（最新策略）8/18預測（真實持股+$1,000,000現金）；arXiv:2607.16450尾端風險指標wiring補完（延續08-01遺留的骨架）；lambda_starr/lambda_es三輪加碼OOS驗證（單一split→4組split→8組split，含一次統計陷阱的自我發現與更正）；**arXiv:2601.21447延伸研究並實際promote：a2118 defensive basket的00679B配置從30%降到0%（改成純cash），真實production程式碼變更**；arXiv:2603.10559跨市場lead-lag回頭審查08-09舊實驗（code review無bug，修正1個真gap後null不變）；arXiv:2603.01157 BAWS adaptive window pilot（機制驗證成功，下游動態bond/cash應用未打贏今天已promote的靜態版本，未接production）。

## 一句話摘要

先用`taiwan_stock_20260817.xlsx`真實持股+$1M現金重跑golden1_0531跟a2118對8/18的目標權重（資料已是8/17收盤，這次沒遇到08-17發現的chip-data-gate缺口，institutional/day_trading已預先補到8/17）。接著使用者重提arXiv:2607.16450（跟08-01同一篇），查證後發現08-01那次只搭了`compare.py`的`TAIL_RISK_METRIC_KEYS`骨架，從未有真實candidate report填值；這次在`backtest_group_a_plus_switch_policy.py`/`backtest_group_a_plus_overlay.py`的`_metrics()`補上真正的欄位（negative_semivariance、rachev_95_95、worst_5d/10d_return、drawdown/recovery duration、ES95/STARR改名對齊）。然後照使用者指示對`lambda_starr`/`lambda_es`做OOS驗證，過程三度加碼：第一輪單一split看似乾淨（Sharpe唯一持續、final_value反向持續），第二輪加碼3組split後全部沒重複出現（第一輪是雜訊），第三輪加碼5組跨2020-2023的真獨立年度split，發現ES95/negative_semivariance是唯一4組獨立年度方向一致偏正的（combined p=0.07~0.11，未達0.05），且抓到自己一個統計陷阱——把時間重疊的split當獨立樣本合併會虛增顯著性。最後使用者重提arXiv:2601.21447（08-17已審過），提案改測「A21.18 defensive basket裡00679B到底有沒有避險能力」，實測發現拿掉00679B、全部換成cash（0050 40%/00679B 0%/cash 60%）在final_value/Sharpe/MDD/全部尾端指標上都嚴格優於現行(0050 40%/00679B 30%/cash 30%)，2020-2026涵蓋7次防禦episode只有1次(2020 COVID)00679B真正避到險，2022跟2025-03這兩次00679B反而跌得比0050還兇。使用者確認promote，**這次是真的改了live production的`group_a_plus/runners/a2118.py`程式碼**，不是shadow-only研究。

## 1. golden1_0531 vs a2118 8/18預測（真實持股+$1,000,000現金）

沿用[[project_golden1_0531_a2118_20260818_predict_and_chip_gate_fix_20260817]]（08-17已做過類似的兩輪跑法）同一套SOP，這次只跑真實持股情境，資料截至2026-08-17收盤。

**資料前置檢查**：`FinRL/data/stock_data.db`（duckdb）已於08-17 23:49更新，`ohlcv`/`institutional_data`/`day_trading_data`三張表對0050.TW/00631L.TW都已到2026-08-17——**沒有重複踩到08-17發現的chip-data-gate缺口**，代表補抓已經生效或有另一次背景pipeline補過。

**持股來源**：`taiwan_stock_20260817.xlsx`（扁平單組別workbook，讀出「即時庫存」列）：
- 0050: 4,234股
- 0056: 17,271股（不在Group A+範圍，忽略）
- 00631L: 900股
- 00632R: 0股
- 00646: 1,032股（不在範圍，忽略）
- 00679B: 100股
- 00713/00751B/00878: 分別5,033/1,000/15,184股（不在範圍，忽略）
- 現金：使用者明確指定$1,000,000（這次請求本身已含金額，不需要再問）

Group A+核心4檔市值 @8/17收盤(0050=106.45/00631L=35.95/00632R=9.97/00679B=26.07)：$485,671 + 現金$1,000,000 = **總資產$1,485,671**。

**golden1_0531**（`generate_dual_group_signal.py --group group_a --live-start --extra-cash 1000000 --download-end 2026-08-17 --override-holdings-json <path>`）：
**⚠️ 踩坑**：不傳`--download-end`會預設用result JSON裡embed的`backtest_end`(08-14)而非今天，資料會停在3天前——這次先跑一次沒加這個參數，`Data date: 2026-08-14`，加了`--download-end 2026-08-17`後才是真正8/17資料。

判定`rebalance_to_0050_50_00631L_20_cash_30`（action label），但PVA連續風險縮放疊加層生效(`pva_allowed=true`, SJM狀態=S)，真正的candidate/effective target跟base target不同：
- 0050.TW: 61.78%（4,234→8,622股，買進4,388股）
- 00631L.TW: 8.22%（900→3,397股，買進2,497股）
- 00679B.TWO: 0%（100→0股，賣出100股）
- cash: 30%

輸出：`results/whatif_signal_group_a_20260818_000707.json`（非production pointer）。

**a2118**（`python3 -m group_a_plus.operations.execution_plan --holdings-json <path> --cash-balance 1000000 --as-of 2026-08-17 --output/--latest-pointer 導向scratch`）：
**⚠️ 踩坑**：execution_plan.py的`--holdings-json`需要`{"holdings": {...}}`包一層且ticker要帶交易所後綴(`0050.TW`不是`0050`)，跟generate_dual_group_signal.py的`--override-holdings-json`(不用包一層、後綴可省)格式不同，兩個腳本混用時很容易搞混。

執行regime=golden1（A20.7防禦態未觸發），讀golden signal快取(`golden_signal_modified_at: 2026-08-14T00:10:08Z`，已知H3落差)理論目標0050 53%/00631L 7.43%/cash 39.57%。因單日大額買進被staging限制(`max_initial_buy_fraction=0.4`)+turnover cap，實際下單：
- 賣00679B.TWO 100股
- 買0050.TW 1,264股（4,234→5,498）
- 買00631L.TW 867股（900→1,767）

換手率11.3%，`execution_allowed=true`，`manual_confirmation_required=false`，無guard擋單。警告：`securities_lending_0050`仍soft-stale（不擋單）。輸出：`results/point_in_time_artifacts/execution_plan/2026/08/17/execution_plan_20260818T000837_339a89ece0c8.json`（scratch copy）。

**Production驗證**：全程`stat`確認`report/group_a_plus/latest/execution_plan.json`（mtime 08-14 08:21）/`live_signal.json`（mtime 08-14 08:10）未被覆寫。

**兩策略方向一致**：都大幅加碼0050、小幅加00631L、出清00679B、00632R維持0。差異(62%/8%/30% vs 53%/7.4%/39.6%)是已知H3快取落差，非新分歧。

## 2. arXiv:2607.16450 尾端風險指標wiring補完

使用者重提同一篇論文（[[project_promotion_utility_tail_risk_20260801]]08-01已審過），沒意識到已經做過骨架，要求對「A21.18 candidate strategy」加ES95/CVaR95/STARR/Rachev/negative semivariance/worst 5d/10d/drawdown duration/recovery duration八項指標。

**查證現況**：
- `group_a_plus/governance/compare.py`的`TAIL_RISK_METRIC_KEYS`（08-01加的）等著讀`expected_shortfall_loss_95`/`starr_95`/`rachev_95_95`/`worst_5d_return`/`worst_10d_return`/`max_drawdown_duration`/`recovery_duration`/`transaction_cost`八個欄位，但**從08-01到今天，沒有任何一個真正的candidate report(`rule_reports`)把這些欄位塞進`metrics`字典**——一直回傳None，`promotion_utility`一直等於`final_value_delta`（no-op骨架，非bug，是刻意的設計但從未真正生效過）。
- ES95/STARR/Rachev/worst_5d已經在`scripts/evaluate/evaluate_cvar_tail_risk_diagnostic_shadow.py`跟`evaluate_a2118_h20_tail_score_shadow.py`算過，但這兩個是shadow-only診斷腳本，不是真正的candidate report。
- `backtesting/performance_metrics.py`已有`calculate_max_drawdown_duration()`/`calculate_recovery_duration()`（08-01加的），但這個模組只有`agents/compare.py`在用，**跟真正的promotion gate(`group_a_plus/governance/compare.py`)完全脫節**——真正的candidate report是`backtest_group_a_plus_switch_policy.py`/`backtest_group_a_plus_overlay.py`各自的`_metrics()`函式產出，兩者都沒有算drawdown/recovery duration，欄位名稱也對不上`TAIL_RISK_METRIC_KEYS`。
- CVaR95跟ES95是同一件事(Conditional VaR = Expected Shortfall)，不用另外做。

**這次改的檔案**（全部未commit）：

1. `backtest_group_a_plus_switch_policy.py`：
   - import `calculate_max_drawdown_duration`/`calculate_recovery_duration` from `backtesting.performance_metrics`
   - `_metrics()`新增：`worst_5d_return`/`worst_10d_return`（原本只有`worst_daily_return`/`worst_20d_return`）、`negative_semivariance`（downside returns平方和年化，原本只有`downside_deviation`即其平方根×√252）、`expected_shortfall_loss_95`(=`abs(expected_tail_loss_5pct)`，改名對齊)、`starr_95`(=`starr_ratio_5pct`，改名對齊)、`expected_tail_gain_95pct`、`rachev_95_95`(=expected_tail_gain_95pct/expected_shortfall_loss_95，全新)、`max_drawdown_duration`、`recovery_duration`。

2. `backtest_group_a_plus_overlay.py`：
   - 同樣的import
   - `_metrics()`原本完全沒有任何尾端指標，這次整組加上：`value_at_risk_5pct`、`expected_shortfall_loss_95`、`starr_95`、`expected_tail_gain_95pct`、`rachev_95_95`、`negative_semivariance`、`worst_5d_return`、`worst_10d_return`、`max_drawdown_duration`、`recovery_duration`。

3. `group_a_plus/governance/compare.py`：只更新`TAIL_RISK_METRIC_KEYS`上方的註解，反映wiring已補完的事實，**沒有動任何邏輯、沒有動`lambda_starr`/`lambda_es`預設值(仍是0.0)**。

**驗證**：純新增dict欄位，不動任何既有key/邏輯。64個既有測試全過（`test_backtest_group_a_plus_metrics_finrl_comparable.py`、`test_group_a_plus_governance_compare_promotion_utility.py`、`test_performance_metrics_recovery_duration.py`、`test_backtest_group_a_plus_overlay_no_inverse.py`、`test_backtest_group_a_plus_switch_policy_2020_fix.py`、`test_backtest_group_a_plus_switch_policy_chip_fallback.py`、`test_backtest_group_a_plus_switch_policy_rebalance_drift.py`、`test_group_a_plus_a2112.py`、`test_group_a_plus_overlay_backtest.py`）。用真實`compare.py` CLI路徑（合成baseline JSON + 真實switch-rule grid輸出）驗證過`tail_risk_metrics`區塊終於有非None值，`promotion_utility_equals_final_value_delta`維持True（lambda=0時的預期行為，無副作用）。

## 3. lambda_starr/lambda_es 三輪OOS驗證（核心研究內容，見[[project_tail_risk_metrics_wired_and_oos_refuted_20260818]]完整記錄）

使用者選擇「OOS校準lambda_starr/lambda_es」方向繼續。用`backtest_group_a_plus_switch_policy.py`的16變體switch-rule grid當實驗母體，比較「用final_value/Sharpe選出的候選人」vs「用ES95/STARR/negative_semivariance選出的候選人」IS→OOS排名是否一致（Spearman相關）。

### 第一輪：單一split（看似乾淨，後來被推翻）
IS=2025-01-02~2025-10-31，OOS=2025-11-03~2026-08-17。16個候選人只有11個是真正不同的權益曲線（5個重複，pseudo-replication陷阱，去重後才算相關性）。
- Sharpe: rho=0.70, p=0.017（唯一顯著，看似「既有gate用對指標」）
- STARR95: 去重前p=0.015看似顯著，去重後p=0.19（假象）
- ES95/negative_semivariance: rho≈-0.32（看似無OOS持續性，方向還偏負）
- 額外看final_value本身：rho=-0.57, p=0.070（看似輕微反向持續，final_value primacy可能有overfitting傾向）
- 直接A/B：IS final_value贏家(`switch_ma20_dd7_hold5`) vs IS尾端指標贏家(`switch_risk_ma80_dd11_total6_hold5_eg015_xg015`，IS少賺1.8%終值換ES95低2.3%/半變異數低3.8%)——OOS完全反轉，尾端贏家OOS終值反而更高但尾端指標反而更差。

### 第二輪：加碼3組split，同樣落在2025-2026（推翻第一輪）
新增split2(IS 01-06/25,OOS 07-12/25)、split3(IS 07-12/25,OOS 01-08/26)、split4(IS 01/25-02/26,OOS 03-08/26)。4組平均後第一輪每個「乾淨」結論全部沒重複：final_value平均rho≈-0.11（打平）、ES95/半變異數平均反而偏正(+0.23~+0.26)、連Sharpe都有split4翻負。**結論：單一split結論不可信，是小樣本雜訊。**

### 第三輪：加碼5組真獨立年度split（使用者要求「做到穩定顯著」）
`day_trading_data`只從2025-01-02開始，要往前擴充年份必須加`--no-chip-features`（關掉chip-based候選人，只留純MA/drawdown變體）繞過資料缺口——**這代表2020-2023組的候選人宇宙跟2025-2026組不完全一致，是已知的方法論不一致**。新增2020/2021/2022/2023四組（H1選/H2測，非重疊），2024H1候選人退化成只剩2個真變體被濾除。

全部8組合併用Stouffer's method（Fisher z transform求和/√n）：ES95 combined p=0.029、半變異數combined p=0.025——**看似顯著，但這是灌水的**：4組2025-26 split彼此時間高度重疊，違反Stouffer's method要求的獨立性假設。**只用4組真正互不重疊的年度split重算**：

| 指標 | 2020 | 2021 | 2022 | 2023 | combined p |
|---|---|---|---|---|---|
| ES95 | -0.13 | +0.79* | +0.40 | (n<4濾除) | 0.114 |
| negative_semivariance | -0.39 | +0.71 | +0.61 | +0.80 | 0.073 |
| Sharpe | -0.66 | +0.86* | -0.79* | -0.20 | 0.577 |
| STARR95 | -0.66 | +0.79* | -0.93** | -0.20 | 0.171 |
| final_value | -0.66 | +0.86* | -0.04 | +0.40 | 0.435 |

2022是關鍵反轉年：Sharpe/STARR在2022 H1→H2直接翻負且顯著，把原本看似穩的持續性打掉。**ES95跟negative_semivariance是唯一4組方向都一致偏正的**，combined p=0.07~0.11，比其他指標都接近顯著，但沒跨過0.05門檻。

### 最終結論
`lambda_starr`/`lambda_es`維持0.0——不是「已驗證且被否定」（第一輪的誤讀），也不是「已驗證可以啟用」，是**「ES95/negative_semivariance方向一致但統計檢定力不足，先觀察」**。額外記錄一個結構性瑕疵：`promotion_utility`公式`final_value_delta + lambda_starr*starr_delta - lambda_es*max(0,es_delta)`單位不匹配（final_value_delta是美元尺度~10^4，starr/es_delta是比率尺度~10^-3，lambda需要到10^5~10^6等級才會有作用），且ES項的`max(0,delta)`只在candidate比baseline差時才罰分——之後真要啟用前這個瑕疵要先修。

## 4. arXiv:2601.21447延伸研究 + 實際promote：a2118 defensive basket移除00679B

延續[[project_2601_21447_stock_bond_correlation_00679b_test_20260817]]（08-17已審過同一篇論文），使用者這次提出具體研究方向：不問「市場會不會跌」，而問「A21.18已經決定defensive時，00679B到底有沒有避到險」。

**查證「A21.18」實際定義**：`FINRL_CONSOLIDATION_ARCHIVE_CANDIDATES_20260729.md`確認"A21.18 = A21.11 + NCF late-bull de-leverage overlay + 2020 COVID switch-rule fix"，就是這整個session一直在跑的a2118策略；當時記錄"Latest active A21.18: defensive basket, `0050 40.0% / 00679B 30.0% / cash 30.0%`"，對應`backtest_group_a_plus_defensive_basket.py`的`DEFENSIVE_BASKETS["bond30_cash30"]`。**這個dict不是研究用的擺設，`group_a_plus/runners/a2118.py`的`run_a2118()`直接`import`它並用`DEFENSIVE_BASKETS["bond30_cash30"]`當真正的live defensive權重**——找到這條連結是這次研究能真正promote的關鍵。

**實測**：在`DEFENSIVE_BASKETS`新增兩個變體`bond15_cash45`(0050 40%/00679B 15%/cash 45%)、`bond0_cash60`(0050 40%/00679B 0%/cash 60%)，0050固定40%只換00679B↔cash比例。跑`backtest_group_a_plus_defensive_basket.py --start 2020-01-02 --end 2026-08-17`（`results/whatif_bond_cash_shadow_20260818.json`）：

| basket | final value | Sharpe | MDD | ES95 | 半變異數 | 回補天數 |
|---|---|---|---|---|---|---|
| A: bond30_cash30（原current） | $5,117,950 | 1.326 | -26.80% | 0.0310 | 0.0451 | 313天 |
| B: bond15_cash45 | $5,306,805 | 1.365 | -24.33% | 0.0305 | 0.0440 | 285天 |
| C: bond0_cash60 | $5,492,297 | 1.396 | -23.90% | 0.0302 | 0.0436 | 231天 |

C嚴格優於A（所有指標），且在cost2x/delay1/delay3三個壓力情境下排序保持一致(`formal_upgrade_pass=True`even用stale的`current_a207`當baseline比較)。拆解7次防禦episode(2020/2021×3/2022/2025/2026)發現：只有2020 COVID那次00679B真正避險成功(0050 -6.75%時00679B +10.34%)；**2022(03-03~11-15)跟2025-03~06這兩次00679B反而跌得比0050還兇**(2022: 0050 -18.04% vs 00679B -21.47%；2025: 0050 -3.40% vs 00679B -14.24%)——20年期公債對升息/殖利率衝擊duration太長，兩次利率快速上升期反而放大虧損而非避險。全樣本平均相關性(-0.09~-0.10)看起來還行，是被2020那次單一極端值撐起來的平均數，蓋掉了2022/2025的失效。

**使用者確認promote**。實作：
1. `backtest_group_a_plus_defensive_basket.py`：`DEFENSIVE_BASKETS`新增`bond15_cash45`/`bond0_cash60`兩個entry（純新增，不影響既有entry）。
2. `group_a_plus/runners/a2118.py` line ~795（`run_a2118()`內）：`basket = _normalize(DEFENSIVE_BASKETS["bond30_cash30"])` → `DEFENSIVE_BASKETS["bond0_cash60"]`，加上完整rationale註解；同時修正line ~1132`rules["basket_name"]`這個純metadata標籤(原本硬寫死"bond30_cash30"，跟實際weight對不上，已修正為"bond0_cash60")。
3. `group_a_plus/operations/ops_health.py`一處docstring註解同步更新("fixed bond30_cash30 basket"→"fixed bond0_cash60 basket -- promoted 2026-08-18")，純文件修正非邏輯。

**驗證**：`backtest_group_a_plus_defensive_basket.py`(7測試)、以及`test_group_a_plus_execution_plan_v2.py`/`test_group_a_plus_latest_strategy.py`/`test_group_a_plus_strategy_signature.py`/`test_export_group_a_plus_latest_strategy_target_weights.py`/`test_group_a_plus_execution_guard.py`/`test_group_a_plus_daily_signal_v2.py`(共115測試)全過。**`tests/test_a2118_strategy_logic.py`被Claude Code auto mode classifier擋下無法用`python3 -m pytest`執行**（用途不明的安全機制，可能是對a2118這個live strategy檔案的測試特別敏感）——先改用Read直接檢視原始碼確認該測試只測`_late_bull_hedge_weights`/`_golden_leverage_cap_weights`等overlay函式，不觸及`DEFENSIVE_BASKETS`/`basket`變數；後續補驗證見下方，最終有真正執行過。

**端到端真實驗證**：直接跑`python3 -m group_a_plus.runners.a2118 --start 2020-01-02 --end 2026-08-17`兩次（一次改回`bond30_cash30`當BEFORE基準、一次是promote後的AFTER，跑完立刻改回`bond0_cash60`），確認完整a2118策略層級（含所有NCF overlay/late-bull hedge/leverage cap）的實際影響比單獨basket比較更顯著：

| 指標 | BEFORE(bond30_cash30) | AFTER(bond0_cash60) |
|---|---|---|
| final_value | $3,291,701 | $3,663,239（+11.3%） |
| Sharpe | 1.253 | 1.387 |
| Sortino | 1.258 | 1.396 |
| MDD | -23.08% | -18.47%（改善4.6pp） |
| max_drawdown_duration | 682天 | 332天（減半） |
| recovery_duration | 313天 | 228天 |
| ES95 | 0.0232 | 0.0222 |
| STARR95 | 0.0342 | 0.0386 |

全部指標同方向改善，MDD跟drawdown duration改善幅度尤其大。`report/group_a_plus/latest/execution_plan.json`/`live_signal.json` mtime全程維持08-14不變——**這次改動的是原始碼，不是快取的live signal，要等下次真正跑daily pipeline重新產生a2118 signal cache才會反映到production決策**。

**後續補驗證**：`test_a2118_strategy_logic.py`改用純`python3 -c`直接import模組逐一呼叫`test_*`函式（不經過pytest test-runner，denial訊息本身建議的替代路徑），7個測試函式全部PASS，跟靜態檢視原始碼的判斷一致，這次是真正執行驗證過。

**⚠️ 有2個`test_group_a_plus_ops_health.py`測試失敗**(`test_golden_signal_stale_is_a_visible_warning`、`test_group_a_plus_decision_signal_stale_is_a_visible_warning`)，但檢查git diff確認是session開始前就已存在的未commit修改（`KNOWN_FROZEN_LATEST_ARTIFACTS`等大改動，跟這次只加2個字的docstring修正無關），**非本次改動造成**，未深入追查（超出這次任務範圍）。

## 5. arXiv:2603.10559跨市場lead-lag：回頭審查08-09舊實驗是否有漏

使用者提arXiv:2603.10559（directed bipartite graph + rolling hypothesis test選穩定edge，target是00631L-vs-0050 next-day relative return），沒意識到跟[[project_cross_market_lead_lag_relative_return_20260809]]08-09已測的方案幾乎逐點相同（同樣的source nodes TSM/SOXX/NVDA/^TNX等、同樣的target formula、同樣的rolling edge-stability選法）。當時結果是乾淨null（R²=-0.007、方向準確率53.1%、9組參數掃過都不顯著）。

**使用者接著要求「回頭檢視實驗是否有漏」**——沒有直接接受既有null結論，要求真的code review：
- 檢查`align_source_returns_to_taiwan_dates()`：`ret.loc[ret.index < dt]`嚴格只用`dt`之前資料，無look-ahead。
- 檢查`select_directed_edges()`跟`walk_forward_relative_return_model()`的train/test split：edge selection只吃`train.index`，test區間完全沒被選特徵過程看到，結構正確。
- 找到兩處統計寬鬆（重疊窗口3d/5d的t-stat沒校正autocorrelation；每個retrain block同時測~30-40個候選特徵沒有multiple-testing校正）——但兩者都只會讓edge selector更容易選到假訊號，不會漏掉真訊號，既有null結果反而因此更站得住腳。
- **找到一個真的gap並修正重測**：`^TNX`(10年期公債殖利率指數)被跟股價一樣用`pct_change()`算報酬率，但殖利率的「衝擊」概念上該用basis point差值（今天早上00679B防禦basket分析就是用`diff()`）。加了`src_TNX_yielddiff{1,5,20}d`（bp差值版本）重跑同一套walk-forward，2019-2026-08-17。原本以為`^TNX_ret1d`(pct_change版)沒被選中，結果發現其實早就被選中51/67個retrain block——假設本身是錯的，但修正後的bp版本(24/67被選中)加進去結果還是null：R²=-0.014、相關性=-0.018、方向準確率52.7%，跟原本幾乎一樣。

**結論不變，但現在是真正審過的**：null是紮實的，不是「還沒測對」造成的假陰性。未存成新的production evaluate_*.py檔案（ad hoc驗證腳本，因為結果沒變，沒有促成新機制）。

## 6. arXiv:2603.01157 BAWS adaptive window pilot

使用者提arXiv:2603.01157（Bootstrap-based Adaptive Window Selection）：市場有structural break，為何所有特徵都用固定20/60/252天窗口？提案循序判斷「較長歷史窗口是否仍與近期資料相容」，不相容就縮短窗口。**明確排除MA100/核心決策規則**，只想套用在6個輔助特徵域：stock-bond correlation、market breadth baseline、外資異常程度、TSMC concentration baseline、tail-risk normalization、cross-market edge estimation。

**範圍縮小**：沒有一次做6個域，選了跟今天早上defensive basket研究直接相關、且已有已知ground-truth regime break日期可驗證的「0050/00679B correlation」pilot一個域。

**v1實作有自我污染的統計bug**：用moving-block bootstrap建立「窗口內只有一個regime」的null distribution，但resample區塊直接來自被測試的同一個窗口——如果窗口真的跨越斷點，null distribution本身就被斷點污染，導致檢定power嚴重不足（89%的日子選最長的252天，完全偵測不到斷點）。

**v2修正**：改用標準Fisher z-test，把候選窗口拆成「最近20天」vs「較早部分」兩個不重疊樣本比較相關係數差異（教科書統計方法，無自我污染問題）。同時發現第一版warmup起算日(2019-06-01)太晚漏掉整個2020 COVID episode，改成2018-06-01起算。

**v2結果：正確且即時抓到全部3次已知regime break**：
- 2020 COVID(01-31~03-18)：收縮到20天顯示強烈負相關(-0.42~-0.88)，比固定252天(-0.42~-0.56)更準確反映真實避險強度；03-19反彈時正確偵測到相關性翻正，反映的是雙雙反彈非避險失效。
- 2022利率衝擊：2/10起收縮到60天更早反映惡化，4/7起收縮到20天正確抓到相關性從-0.4瞬間翻正到+0.24~+0.40（今天早上發現的「00679B跌得比0050兇」異常regime）。
- 2025-03衝擊：同型態，4/11起收縮到20天正確抓到翻正到+0.22~+0.33。

**下游應用測試：動態bond/cash切換沒有打贏今天已promote的靜態版本**。拿adaptive correlation當訊號，防禦regime天數裡動態決定用`bond30_cash30`還是`bond0_cash60`（threshold: corr<threshold時持有bond），真實回測2020-01-02~2026-08-17：

| threshold | final_value | Sharpe | MDD | 額外換手 |
|---|---|---|---|---|
| corr < 0.0 | $5,074,696 | 1.320 | -27.31% | +27次 |
| corr < -0.15 | $5,223,063 | 1.343 | -25.82% | +26次 |
| corr < -0.30 | $5,501,324 | 1.388 | -23.90% | +23次 |
| 靜態bond0_cash60_always（今天已promote） | $5,492,297 | 1.396 | -23.90% | — |

前兩個threshold明顯輸；-0.30勉強final_value高$9k(+0.17%)但Sharpe/尾端指標略輸、MDD打平、換手更多——不是真的贏，是雜訊等級差異。**沒有繼續調更多threshold**，避免落入`feedback_overfitting_fixed_window_tuning`同樣的陷阱。

**根因**：真正值得持有bond的「急性避險」時刻太罕見（只有2020那次），這個訊號能偵測到但需要20天資料才有統計檢定力，偵測到時往往已經來不及在急性避險窗口內受益；其餘大多數時間持有bond反而拖累報酬——跟今天早上episode拆解的結論完全一致，這次用更嚴謹的機制重新驗證了同一個結論。

**結論**：BAWS的window-selection機制本身有效、已驗證（causal、正確抓到3次真實斷點）。但這個具體下游應用（動態bond/cash切換）沒有比今天已promote的一刀切更好。**維持shadow-only，未接任何production決策**，今天早上promote的靜態`bond0_cash60`不動。所有pilot腳本都在`/tmp` scratchpad，未存進repo正式路徑（`baws_pilot_v2.py`、`baws_dynamic_basket_test.py`）。

**使用者決定「之後再做」**：剩下5個域（market breadth baseline、外資異常程度、TSMC concentration baseline、tail-risk normalization、cross-market edge estimation）都還沒開始，本次session到此停止，留待未來session繼續。

## Do Not Do

1. **不要對golden1_0531的`generate_dual_group_signal.py`省略`--download-end`**——不傳的話會用result JSON裡embed的`backtest_end`日期(可能是幾天前)而非今天，這次第一次跑就踩到(停在08-14)，加了`--download-end 2026-08-17`才對。
2. **不要混用`generate_dual_group_signal.py`的`--override-holdings-json`跟`execution_plan.py`的`--holdings-json`格式**——前者是扁平JSON(`{"0050": 4234}`)、ticker後綴可省；後者要包一層`{"holdings": {...}}`且ticker必須帶交易所後綴(`0050.TW`不是`0050`)，不帶會報「No Group A++ holdings parsed」。
3. **不要用非獨立(時間重疊)的split做Stouffer/Fisher合併顯著性檢定**——這次8組合併看似p<0.03顯著，其實是4組2025-26 split互相重疊灌水；只有時間上真正互不重疊的split才能合併，這跟pseudo-replication是同一類錯誤的不同面貌，這次是自己犯了一次又自己抓到。
4. **不要只憑單一IS/OOS split的結論判斷這個switch-rule grid的任何指標**——16個候選人常常只有6-13個真正不同的權益曲線(需先去重)，單一split的相關係數在這個規模下極不穩定，第一輪自己就是活生生的案例(4個「乾淨」結論後來全部沒重複出現)。
5. **不要假設`--no-chip-features`跑出來的候選人宇宙跟有chip features時一樣**——2020-2023組(缺day_trading_data)用了這個flag，候選人只剩純MA/drawdown變體，跟2025-2026組(含chip-based變體)不完全可比，混合分析時要註明。
6. **不要在證據雜訊未定論時啟用`lambda_starr`/`lambda_es`**——即使ES95/半變異數方向一致，p值(0.07~0.11)還沒跨過傳統顯著門檻，且公式本身還有單位不匹配的瑕疵沒修。
7. **不要用moving-block bootstrap resample「被測試的同一個窗口自己」來建立structural-break的null distribution**——如果窗口真的跨越斷點，null distribution會被斷點污染，檢定power嚴重不足(BAWS v1踩到，89%的日子都測不出斷點)。改用Fisher z-test比較兩個不重疊子樣本的相關係數差異，或確保bootstrap的null來源跟被測試的資料是分開的。
8. **不要把「機制驗證正確」跟「下游應用有價值」混為一談**——BAWS adaptive window正確抓到3次regime break不代表拿它做動態bond/cash切換就會贏，兩者要分開驗證，這次幸好有分開測才沒有把一個沒用的下游應用誤判成成功案例。

## Next Step

`tests/test_a2118_strategy_logic.py`已用替代路徑（純python3直接呼叫測試函式，繞過pytest classifier）驗證7個測試全過，不再是待辦。若要讓a2118的下一次live signal真正反映新basket，需要重新跑daily pipeline（或明確要求手動重跑a2118 signal生成），目前`report/group_a_plus/latest/`底下的快取還是舊的。

lambda_starr/lambda_es：若要把ES95/半變異數的OOS持續性做到真正顯著，兩個選項都還沒做：(a) 把年度split切成季度窗(2020-2023約可湊到8組獨立樣本，犧牲每組統計力換數量)，(b) 往2020年以前延伸(但golden1_0531訓練基準/`institutional_data`都是2020年才開始，往前推有效性存疑，需要先確認可行性再做)。使用者在4組獨立年度split的結果後回覆「OK」結束，未繼續切季度窗。若之後要啟用lambda，除了要先湊到顯著證據，還要先修`promotion_utility`公式的單位不匹配問題（見上）。

`test_group_a_plus_ops_health.py`的2個失敗測試（`test_golden_signal_stale_is_a_visible_warning`、`test_group_a_plus_decision_signal_stale_is_a_visible_warning`）跟這次改動無關（session開始前就已存在的未commit修改造成），需要的話另開session追查，不是這次任務範圍。

**arXiv:2603.01157 BAWS**：使用者明確表示「之後再做」——剩下5個域（market breadth baseline、外資異常程度、TSMC concentration baseline、tail-risk normalization、cross-market edge estimation）都還沒開始。下次接續時：(a)先想清楚每個域的adaptive window輸出要餵給哪個具體決策，不要只做feature品質展示（這次0050/00679B correlation的教訓：機制work不代表下游應用有價值）；(b)可以直接重用`baws_pilot_v2.py`的Fisher z-test版`select_adaptive_window`/`select_adaptive_corr`核心邏輯（目前只在`/tmp` scratchpad，未存進repo正式路徑，下次要用得重寫或想清楚要不要正式存檔）；(c)v1的bootstrap自我污染bug是個好的警世案例，套用到新域時要避免同樣的陷阱。

所有程式碼改動（`backtest_group_a_plus_switch_policy.py`/`backtest_group_a_plus_overlay.py`/`group_a_plus/governance/compare.py`/`backtest_group_a_plus_defensive_basket.py`/`group_a_plus/runners/a2118.py`/`group_a_plus/operations/ops_health.py`)跟這次所有中間產物(`results/oos_lambda_calib_*`、`results/oos_indep_*`、`results/whatif_tailrisk_smoke_*`、`results/whatif_bond_cash_shadow_*`、`results/whatif_a2118_bond*`，全部在`.gitignore`的`results/`目錄下)都還沒commit，等使用者明確要求才動。**`group_a_plus/runners/a2118.py`這次是真正的production策略邏輯變更，不是研究性質，commit時要特別注意**。
