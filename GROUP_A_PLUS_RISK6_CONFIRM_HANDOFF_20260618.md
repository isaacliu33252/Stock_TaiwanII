# GroupA+ Risk6 確認版交接紀錄 - 2026-06-18

## 目的

本紀錄整理 2026-06-18 針對 GroupA+ 最新策略的資料補齊、6/22 預測、重實驗與策略改善結果。重點是確認最新可用資料是否已納入、Golden1_0531 與 GroupA+ 對 2026-06-22 的預測結果，以及 GroupA+ 最新策略是否能在不增加多餘切換的前提下加入更強的風險確認條件。

## 資料補齊狀態

本次以 2026-06-18 為資料截止日，已重新下載與更新可用資料。

已執行的主要資料更新命令：

```bash
python3 refresh_group_data.py --group both --target-date 2026-06-18 --force --summary-path results/data_refresh_20260618_latest_rerun.json
python3 FinRL/data/stock_db.py --add-institutional 0050.TW,00631L.TW,00632R.TW,00679B.TWO --start 2026-06-18 --end 2026-06-18
python3 FinRL/data/stock_db.py --add-margin 0050.TW,00631L.TW,00632R.TW,00679B.TWO --start 2026-06-18 --end 2026-06-18
python3 FinRL/data/stock_db.py --add-market-margin --start 2026-06-18 --end 2026-06-18
MPLCONFIGDIR=/tmp/matplotlib-finmind python3 fetch_finmind_chip_data.py --tickers 0050,00631L,00632R,00679B --futures-ids TX --option-ids TXO --index-ids TAIEX,TPEx --start 2026-06-18 --end 2026-06-18 --datasets institutional,margin,foreign_shareholding,derivative_institutional,per,securities_lending,short_sale_balances,total_return_index,day_trading,dealer_futures,dealer_options
```

FinMind free 單日寫入結果：

| 資料集 | 寫入筆數 |
| --- | ---: |
| institutional | 2 |
| margin | 0 |
| foreign_shareholding | 0 |
| derivative_institutional | 9 |
| per | 0 |
| securities_lending | 1 |
| short_sale_balances | 0 |
| total_return_index | 2 |
| day_trading | 4 |
| dealer_futures | 51 |
| dealer_options | 42 |

最終資料庫日期檢查：

| 資料表 | 最新日期 |
| --- | --- |
| ohlcv | 2026-06-18 |
| institutional_data | 2026-06-18 |
| margin_data | 2026-06-17 |
| market_margin_data | 2026-06-17 |
| foreign_shareholding_data | 2026-06-17 |
| derivative_institutional_data | 2026-06-18 |
| short_sale_balance_data | 2026-06-17 |
| securities_lending_data | 2026-06-18 |
| day_trading_data | 2026-06-18 |
| dealer_futures_data | 2026-06-18 |
| dealer_options_data | 2026-06-18 |
| total_return_index_data | 2026-06-18 |
| shareholding_distribution | 2026-06-12 |

## Free 權限限制

目前沒有 `FINMIND_API_TOKEN`，以 FinMind free 權限測試後，以下資料無法補齊或無法穩定取得：

- `TaiwanStockHoldingSharesPer`
- `derivative_large_trader`
- `margin_maintenance`
- `government_bank`
- `derivative_afterhours`

因此本次策略改善只使用 free 權限可取得且已寫入資料庫的資料，不假設付費資料存在。

## 2026-06-22 預測

預測使用資料截止日為 2026-06-18，`as-of-date` 設為 2026-06-22。2026-06-22 是未來交易日預測，因此實際價格與籌碼資料仍以 2026-06-18 為準，允許 `stale_days=4`。

### Golden1_0531

執行命令：

```bash
python3 generate_dual_group_signal.py --group group_a --result-json results/group_a_backtest_20250101_20260525_20260526_193252.json --download-end 2026-06-18 --as-of-date 2026-06-22 --live-start --extra-cash 1000000 --override-holdings-json '{"0050.TW":0,"00631L.TW":0,"00679B.TWO":0,"00632R.TW":0}' --max-stale-days 5
```

輸出檔案：

- `results/signal_group_a_golden1_0531_predict_20260622_from_20260618_total1000000.json`
- `results/signal_group_a_golden1_0531_predict_20260622_from_20260618_total1000000.csv`

預測結果：

| 欄位 | 值 |
| --- | --- |
| requested_as_of_date | 2026-06-22 |
| actual_data_date | 2026-06-18 |
| stale_days | 4 |
| signal_status | rebalance |
| signal_reason | rebalance_to_0050_60_00631L_20_cash_20 |
| 0050.TW 目標權重 | 60% |
| 00631L.TW 目標權重 | 20% |
| 00679B.TWO 目標權重 | 0% |
| 00632R.TW 目標權重 | 0% |
| 現金目標權重 | 20% |

目標股數：

| 標的 | 最新價格 | 目標股數 |
| --- | ---: | ---: |
| 0050.TW | 107.30000305175781 | 5592 |
| 00631L.TW | 38.33000183105469 | 5218 |
| 00679B.TWO | 27.040000915527344 | 0 |
| 00632R.TW | 10.029999732971191 | 0 |

### GroupA+

執行命令：

```bash
python3 group_a_00679b_continuous_shadow.py --signal-json results/signal_group_a_20260618_165000.json --group-a-plus-config group_a_plus_config.json --total-assets 1000000 --current-00679b-shares 0 --dynamic-overlay --min-trade-value 0 --output-prefix results/group_a_plus_final_signal_predict_20260622_from_20260618_total1000000
```

輸出檔案：

- `results/group_a_plus_final_signal_predict_20260622_from_20260618_total1000000.json`
- `results/group_a_plus_final_signal_predict_20260622_from_20260618_total1000000.csv`
- `results/group_a_plus_final_signal_predict_20260622_from_20260618_total1000000.md`

預測結果：

| 欄位 | 值 |
| --- | --- |
| requested_as_of_date | 2026-06-22 |
| actual_data_date | 2026-06-18 |
| signal_status | rebalance |
| signal_reason | rebalance_to_0050_60_00631L_20_cash_20 |
| overlay regime | risk_on |
| overlay_00679b_weight | 0% |
| 0050.TW 目標權重 | 60% |
| 00631L.TW 目標權重 | 20% |
| 00632R.TW 目標權重 | 0% |
| 00679B.TWO 目標權重 | 0% |
| 現金目標權重 | 20% |
| execution cost | 1539.7727279838562 |
| cash_after_cost | 198578.2906570259 |
| buy_notional | 799881.9366149902 |

目標股數：

| 標的 | 目標股數 |
| --- | ---: |
| 0050.TW | 5591 |
| 00631L.TW | 5217 |
| 00679B.TWO | 0 |
| 00632R.TW | 0 |

比較報告：

- `report/group_a_plus/compare/html/group_a_plus_vs_golden1_0531_20260618_165043.html`
- `report/group_a_plus/compare/json/group_a_plus_vs_golden1_0531_20260618_165043.json`
- `report/group_a_plus/latest/strategy_compare.json`

## 最新策略改善：A20.1 Risk6 Confirmation

本次改善重點是讓 GroupA+ 的 switch policy 不只依賴價格與回撤條件，也納入可用籌碼與衍生性商品風險分數確認。實驗結果顯示，最強且不改變既有有效切換點的確認條件是 `total_risk_score >= 6`。

已修改內容：

- `evaluate_group_a_plus_switch_sweep.py`
  - 新增 `--chip-scores`
  - 新增 `--total-risk-scores`
  - 原本已有 `--derivative-scores`
- `backtest_group_a_plus_switch_policy.py`
  - 新增規則 `risk_ma90_dd12_total6_hold5`
  - 新增 `_confirmation_strength(rule)` 作為 recommended tie-break
  - 當 Sharpe、MDD、return 相近或相同時，優先選擇有風險確認條件的規則
- `group_a_plus_config.json`
  - description 加入 A20.1 switch layer 說明
  - `latest_reference.switch_policy_result` 更新為 `results/group_a_plus_switch_policy_backtest_risk6_confirm_20260618.json`
- `report/group_a_plus/latest/switch_backtest.json`
  - 指向最新 risk6 confirmation 回測結果

## 重實驗命令

完整 sweep：

```bash
python3 evaluate_group_a_plus_switch_sweep.py --start 2025-01-02 --end 2026-06-18 --ma-windows 60,90,120,150 --drawdowns=-0.08,-0.10,-0.12,-0.15 --hold-days 5,10,15,20 --enter-ma-gaps=-0.02,-0.03,-0.04 --exit-ma-gaps 0.01,0.015,0.02 --chip-scores 0,1,2 --derivative-scores 0,1 --total-risk-scores 0,2,3 --output results/group_a_plus_switch_chip_deriv_total_sweep_20260618.json
```

核心確認：

- `results/group_a_plus_switch_core_chip_deriv_confirmation_20260618.json`
- `results/group_a_plus_switch_high_threshold_confirmation_20260618.json`

改善版回測：

```bash
python3 backtest_group_a_plus_switch_policy.py --start 2025-01-02 --end 2026-06-18 --initial-value 1000000 --output-prefix results/group_a_plus_switch_policy_backtest_risk6_confirm_20260618
```

語法與 JSON 驗證：

```bash
python3 -m py_compile backtest_group_a_plus_switch_policy.py evaluate_group_a_plus_switch_sweep.py
python3 -m json.tool group_a_plus_config.json >/tmp/group_a_plus_config_check.json
```

## 實驗結果

完整 sweep：

| 指標 | 值 |
| --- | ---: |
| rules_total | 10368 |
| eligible | 5184 |
| 最佳規則 | switch_ma90_dd12_hold5_eg020_xg010 |
| final | 2318924.8421924673 |
| total_return | 1.3189248421924673 |
| Sharpe | 2.326417252471209 |
| max_drawdown | -0.2534834443117512 |
| defense_days | 67 |
| switches | 2 |

高門檻確認：

- `chip_score >= 4`
- `derivative_score >= 2`
- `total_risk_score >= 6`

以上三種確認條件都維持同一組有效切換事件與原績效。若門檻再提高，會拖累或導致不切換。

改善版 recommended：

| 欄位 | 值 |
| --- | --- |
| recommended rule | switch_risk_ma90_dd12_total6_hold5 |
| ma_window | 90 |
| enter_ma_gap | -0.02 |
| exit_ma_gap | 0.01 |
| drawdown_window | 90 |
| enter_drawdown | -0.12 |
| exit_momentum_days | 5 |
| min_hold_days | 5 |
| require_total_risk_score | 6 |
| exit_max_total_risk_score | 6 |

改善版回測績效：

| 指標 | 值 |
| --- | ---: |
| final | 2325814.145408824 |
| total_return | 1.325814145408824 |
| annual_return | 0.7851544312753163 |
| volatility | 0.2762912982813835 |
| Sharpe | 2.333534662012485 |
| max_drawdown | -0.2534834443117512 |
| defense_days | 67 |
| switch_count | 2 |

切換事件：

| 日期 | 事件 | chip_score | derivative_score | total_risk_score |
| --- | --- | ---: | ---: | ---: |
| 2025-02-27 | switch_to_group_a_plus_defensive | 4 | 2 | 6 |
| 2025-06-09 | switch_to_golden | - | - | - |

輸出檔案：

- `results/group_a_plus_switch_policy_backtest_risk6_confirm_20260618.json`
- `results/group_a_plus_switch_policy_backtest_risk6_confirm_20260618.csv`
- `results/group_a_plus_switch_policy_backtest_risk6_confirm_20260618_curve.csv`
- `results/group_a_plus_switch_policy_backtest_risk6_confirm_20260618_recommended_regime.csv`

## 策略結論

1. 最新 GroupA+ recommended 已更新為 `switch_risk_ma90_dd12_total6_hold5`。
2. 這不是單純改名，而是在原本 MA90、90 日回撤 -12%、最短持有 5 日的切換架構上，增加 `total_risk_score >= 6` 的風險確認。
3. 這個條件在 2025-01-02 到 2026-06-18 的重實驗中沒有破壞有效切換，且績效略優於先前基準。
4. 2026-06-22 預測仍維持 risk_on，GroupA+ overlay 不加 00679B，配置與 Golden1_0531 接近，核心仍是 0050 60%、00631L 20%、現金 20%。
5. 目前 free 權限可用資料已納入最新策略評估；付費資料缺口已標明，未把不可取得資料硬塞進模型假設。

## 風險與後續建議

- 2026-06-22 是未來預測日，實際下單前仍應在當日盤前或資料更新後重跑。
- `margin_data`、`market_margin_data`、`foreign_shareholding_data`、`short_sale_balance_data` 最新只到 2026-06-17，原因是公開資料或 free 權限尚未提供 2026-06-18 的完整資料。
- `shareholding_distribution` 最新為 2026-06-12，屬週頻資料，並非每日更新。
- 若之後取得 FinMind token，可優先補 `TaiwanStockHoldingSharesPer`、大型交易人、維持率、公股銀行與盤後衍生性商品資料，再重新評估 total risk score 的權重。
- 下一步可做 walk-forward 或滾動視窗驗證，確認 `total_risk_score >= 6` 不是單一區間過度配適。

## 2026-06-18 PDF 檢視補充：Applied Quantitative Finance

使用者指定檢查 `C:\Users\isaac\Downloads\FinMathematics-master\FinMathematics-master` 內 PDF 是否有優點可加入最新策略。本次先挑 `Applied Quantitative Finance.pdf`，原因是 `Quantitative Trading.pdf` 為掃描影像，無法直接抽文字；`Applied Quantitative Finance.pdf` 可用 `pypdf` 抽取文字，且目錄包含 Value at Risk、歷史模擬、隱含波動、統計程序控制、長記憶交易與 locally time homogeneous volatility 等內容。

可轉入 GroupA+ 的概念：

- VaR/尾端風險：不要只看均值、Sharpe 與一般波動，要檢查近期報酬是否落入歷史 5% 尾端區域。
- 局部時間同質波動：市場波動參數不是固定的，近期 20 日波動若相對 60 日波動升高，應視為 regime 變動候選。
- 參數自適應與回測驗證：新增風險條件不能只因理論合理就升級，必須和現有 `risk6` recommended 做同區間重跑比較。

已加入程式的候選診斷：

- `backtest_group_a_plus_switch_policy.py`
  - 新增 `tail_risk_score`
  - 新增 `hist_var_0050_20d_5pct`
  - 新增 `realized_vol_0050_20d`
  - 新增 `realized_vol_0050_60d`
  - 新增 `realized_vol_ratio_20_60`
  - 新增候選規則 `switch_risk_ma90_dd12_total6_tail1_hold5`
- `evaluate_group_a_plus_switch_sweep.py`
  - 新增 `--tail-risk-scores`

PDF 啟發實驗命令：

```bash
python3 evaluate_group_a_plus_switch_sweep.py --start 2025-01-02 --end 2026-06-18 --ma-windows 90 --drawdowns=-0.12 --hold-days 5 --enter-ma-gaps=-0.02 --exit-ma-gaps 0.01 --chip-scores 0 --derivative-scores 0 --total-risk-scores 6 --tail-risk-scores 0,1,2 --output results/group_a_plus_pdf_tailrisk_probe_20260618.json
python3 backtest_group_a_plus_switch_policy.py --start 2025-01-02 --end 2026-06-18 --initial-value 1000000 --output-prefix results/group_a_plus_switch_policy_backtest_pdf_tailrisk_review_20260618
```

PDF 啟發實驗結果：

| variant | final | Sharpe | MDD | defense_days | switch_count | 結論 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `switch_risk6_ma90_dd12_hold5_eg020_xg010` | 2325814.145408824 | 2.333534662012485 | -0.2534834443117512 | 67 | 2 | 維持最佳 |
| `switch_tail1_risk6_ma90_dd12_hold5_eg020_xg010` | 2303283.389220137 | 2.2847520894449334 | -0.26603594888113935 | 46 | 2 | 延後防守、績效較差 |
| `switch_tail2_risk6_ma90_dd12_hold5_eg020_xg010` | 2246432 左右 | 2.229631 左右 | -0.275387 左右 | 0 | 0 | 門檻過嚴，等同不切換 |

關鍵判斷：

- `tail1` 會把原本 2025-02-27 的防守切換延後到 2025-03-31。
- 2025-02-27 當天雖然 `total_risk_score=6`，但 `tail_risk_score=0`，所以 tail 條件會錯過有效保護。
- 因此 PDF 啟發的 tail risk feature 已可作為診斷欄位與後續 sweep 參數，但不應升級為最新 recommended。
- 最新 recommended 仍維持 `switch_risk_ma90_dd12_total6_hold5`。

## 2026-06-18 PDF 檢視補充二：Nonlinear Optimization with Financial Applications

使用者要求留下前一份 PDF 實驗紀錄後，再看一份 PDF。本次選擇 `Nonlinear Optimization with Financial Applications.pdf`，原因是該書目錄直接包含：

- Portfolio optimization
- Optimal portfolios with restrictions
- Larger-scale portfolios
- Including transaction costs
- Rebalancing allowing for transaction costs
- Downside risk
- Worst-case analysis

相較純衍生品定價書，這份 PDF 更接近 GroupA+ 的 ETF 配置、切換與風控評估問題。

### 可轉入 GroupA+ 的概念

1. Downside risk：一般變異數會同時懲罰「高於目標」與「低於目標」的偏離，但策略真正需要避免的是下行偏離。因此應補充 downside deviation 與 Sortino，而不只看 Sharpe。
2. Worst-case analysis：除了全期績效與最大回撤，也應看最差單日與最差固定期間報酬，避免策略只在平均上漂亮。
3. Transaction cost / rebalancing：該書提醒再平衡不應只看理論最佳權重，還要考慮交易成本與必要調整幅度。GroupA+ 目前已有 execution cost 與 turnover cap，後續可再做「最小必要調整」版本，但本輪先不改下單邏輯。

### 已加入程式的評估欄位

`backtest_group_a_plus_switch_policy.py` 的 `_metrics()` 新增：

- `downside_deviation`
- `sortino_ratio`
- `worst_daily_return`
- `worst_20d_return`

這是評估面改善，不直接改倉位、不直接改切換門檻，避免在未驗證前讓正式策略變得不穩。

### 重實驗命令

```bash
python3 backtest_group_a_plus_switch_policy.py --start 2025-01-02 --end 2026-06-18 --initial-value 1000000 --output-prefix results/group_a_plus_switch_policy_backtest_downside_worstcase_review_20260618
```

輸出檔案：

- `results/group_a_plus_switch_policy_backtest_downside_worstcase_review_20260618.json`
- `results/group_a_plus_switch_policy_backtest_downside_worstcase_review_20260618.csv`
- `results/group_a_plus_switch_policy_backtest_downside_worstcase_review_20260618_curve.csv`
- `results/group_a_plus_switch_policy_backtest_downside_worstcase_review_20260618_recommended_regime.csv`

### 重實驗結果

最新 recommended 仍為：

`switch_risk_ma90_dd12_total6_hold5`

| 指標 | 值 |
| --- | ---: |
| final | 2325814.145408824 |
| total_return | 1.325814145408824 |
| annual_return | 0.7851544312753163 |
| volatility | 0.2762912982813835 |
| downside_deviation | 0.25980498057678825 |
| Sharpe | 2.333534662012485 |
| Sortino | 2.4816126308305324 |
| max_drawdown | -0.2534834443117512 |
| worst_daily_return | -0.08768987531552874 |
| worst_20d_return | -0.18961361089643902 |

Sortino 排名前幾名：

| variant | final | Sharpe | Sortino | MDD | worst_daily | worst_20d |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `switch_ma90_dd12_hold5_eg020_xg010` | 2325814.145408824 | 2.333534662012485 | 2.4816126308305324 | -0.2534834443117512 | -0.08768987531552874 | -0.18961361089643902 |
| `switch_risk_ma90_dd12_total6_hold5` | 2325814.145408824 | 2.333534662012485 | 2.4816126308305324 | -0.2534834443117512 | -0.08768987531552874 | -0.18961361089643902 |
| `switch_ma120_dd12_hold15` | 2305290 左右 | 2.311599 左右 | 2.452955 左右 | -0.257288 左右 | -0.088682 左右 | -0.191732 左右 |
| `switch_risk_ma90_dd12_total6_tail1_hold5` | 2303283.389220137 | 2.2847520894449334 | 2.416336 左右 | -0.26603594888113935 | -0.090949 左右 | -0.201251 左右 |

### 結論

- 這份 PDF 帶來的是「評估品質改善」，不是正式配置績效改善。
- 新增 Sortino 與 worst-case 欄位後，`switch_risk_ma90_dd12_total6_hold5` 仍維持 recommended。
- 純價格版 `switch_ma90_dd12_hold5_eg020_xg010` 在績效欄位與 risk6 相同，但缺少 `total_risk_score>=6` 的風險確認；因此仍選 risk6，語義與防誤觸較好。
- 交易成本與再平衡章節值得後續再做「最小必要調整 / no-trade band」實驗，但不應在本輪未重跑前直接改正式策略。

## 2026-06-18 PDF 檢視補充三：Quantitative Finance for Physicists - An Introduction

使用者指定 PDF：`Quantitative Finance for Physicists - An Introduction.pdf`。

該書章節包含：

- 第 5 章 Time Series Analysis
- 第 6 章 Fractals
- 第 8 章 Scaling in Financial Time Series
- 第 10 章 Portfolio Management
- 第 11 章 Market Risk Measurement
- 第 12 章 Agent-Based Modeling of Financial Markets

本次優先抽取第 5、8、10、11、12 章。對 GroupA+ 最可落地的是第 11 章的 coherent risk / Expected Tail Loss，因為它可直接補強回測風險報表。第 12 章的 agent-based / chartist 模型也有啟發，但比較適合後續設計「技術交易擁擠」或「動能過熱」診斷，不適合在未驗證前直接改切換門檻。

### 可轉入 GroupA+ 的概念

1. Time Series / Conditional Heteroskedasticity：金融報酬常有波動聚集，單一固定波動假設不足。GroupA+ 已有波動與回撤條件，後續可再測 GARCH/EWMA 型風險濾網。
2. Scaling / Fat Tails：報酬分布厚尾，平均與標準差不足以描述極端損失。這支持保留 VaR、ETL、worst-case 指標。
3. Coherent Risk / Expected Tail Loss：VaR 只看分位點，ETL 會看尾端內平均損失，適合作為回測風險欄位。
4. Agent-Based / Chartists：當追價交易者比例升高，模型可能產生更高波動或不穩定。可作為後續「動能擁擠」診斷方向，但本輪不直接納入 recommended。

### 已加入程式的評估欄位

`backtest_group_a_plus_switch_policy.py` 的 `_metrics()` 新增：

- `value_at_risk_5pct`
- `expected_tail_loss_5pct`

這是第 11 章 Market Risk Measurement 的直接落地版本。它補足已有的 `downside_deviation`、`sortino_ratio`、`worst_daily_return`、`worst_20d_return`。

### 重實驗命令

```bash
python3 backtest_group_a_plus_switch_policy.py --start 2025-01-02 --end 2026-06-18 --initial-value 1000000 --output-prefix results/group_a_plus_switch_policy_backtest_physicist_etl_review_20260618
```

輸出檔案：

- `results/group_a_plus_switch_policy_backtest_physicist_etl_review_20260618.json`
- `results/group_a_plus_switch_policy_backtest_physicist_etl_review_20260618.csv`
- `results/group_a_plus_switch_policy_backtest_physicist_etl_review_20260618_curve.csv`
- `results/group_a_plus_switch_policy_backtest_physicist_etl_review_20260618_recommended_regime.csv`

### 重實驗結果

最新 recommended 仍為：

`switch_risk_ma90_dd12_total6_hold5`

| 指標 | 值 |
| --- | ---: |
| final | 2325814.145408824 |
| total_return | 1.325814145408824 |
| annual_return | 0.7851544312753163 |
| volatility | 0.2762912982813835 |
| downside_deviation | 0.25980498057678825 |
| Sharpe | 2.333534662012485 |
| Sortino | 2.4816126308305324 |
| max_drawdown | -0.2534834443117512 |
| value_at_risk_5pct | -0.024071234487319793 |
| expected_tail_loss_5pct | -0.037154551087349746 |
| worst_daily_return | -0.08768987531552874 |
| worst_20d_return | -0.18961361089643902 |

依 ETL 較不負排序時，短週期防守規則的尾端平均損失較小，但 final 明顯低於 `risk6`：

| variant | final | ETL 5% | Sharpe | Sortino | MDD |
| --- | ---: | ---: | ---: | ---: | ---: |
| `switch_chip_ma20_dd5_score1_hold5` | 2121642 左右 | -0.033155 左右 | 2.275563 | 2.382973 | -0.260740 |
| `group_a_plus_defensive_1m` | 2112080 左右 | -0.033174 左右 | 2.267679 | 2.393545 | -0.253470 |
| `switch_risk_ma20_dd5_total2_hold5` | 2132383 左右 | -0.033185 左右 | 2.284302 | 2.394789 | -0.260740 |
| `switch_risk_ma90_dd12_total6_hold5` | 2325814.145408824 | -0.037154551087349746 | 2.333534662012485 | 2.4816126308305324 | -0.2534834443117512 |

依 final 排名時，`risk6` 仍最佳；與純價格版 `switch_ma90_dd12_hold5_eg020_xg010` 指標相同，但 `risk6` 有 `total_risk_score>=6` 確認條件，語義較好。

### 結論

- 這份 PDF 帶來的是「尾端風險評估改善」，不是正式策略績效改善。
- ETL 指標揭露一個取捨：更早、更短週期的防守能改善尾端平均日損，但犧牲太多 final return。
- 綜合 final、Sharpe、Sortino、MDD 與風險確認語義後，最新 recommended 仍維持 `switch_risk_ma90_dd12_total6_hold5`。
- Agent-based 章節可作為下一輪研究：用成交量、日內當沖量、槓桿 ETF 動能、融資與選擇權偏度建立「chartist crowding」候選分數，再用 sweep 驗證。

## 2026-06-18 PDF 第 11 章補強：Kupiec Test 與波動率加權歷史模擬

使用者補充 `Quantitative Finance for Physicists - An Introduction` 第 11 章 Market Risk Measurement 的重點，包含 VaR、ETL、coherent risk measures、歷史模擬、波動率加權與 Kupiec Test。本次依該章內容把 GroupA+ 回測風險檢驗補齊。

### 已加入程式的欄位

`backtest_group_a_plus_switch_policy.py` 的 `_metrics()` 新增：

- `var_breach_count_5pct`
- `var_breach_ratio_5pct`
- `kupiec_lr_5pct`
- `kupiec_pvalue_5pct`
- `volatility_weighted_var_5pct`
- `volatility_weighted_etl_5pct`

其中：

- `var_breach_count_5pct`：實際報酬低於 5% VaR 的次數。
- `var_breach_ratio_5pct`：實際 breach 比率。
- `kupiec_lr_5pct` / `kupiec_pvalue_5pct`：檢驗 5% VaR 的實際 breach 頻率是否和理論 5% 明顯不符。
- `volatility_weighted_var_5pct` / `volatility_weighted_etl_5pct`：使用 EWMA 波動率加權後的歷史模擬 VaR/ETL。

### 重實驗命令

```bash
python3 backtest_group_a_plus_switch_policy.py --start 2025-01-02 --end 2026-06-18 --initial-value 1000000 --output-prefix results/group_a_plus_switch_policy_backtest_physicist_kupiec_volweighted_20260618
```

輸出檔案：

- `results/group_a_plus_switch_policy_backtest_physicist_kupiec_volweighted_20260618.json`
- `results/group_a_plus_switch_policy_backtest_physicist_kupiec_volweighted_20260618.csv`
- `results/group_a_plus_switch_policy_backtest_physicist_kupiec_volweighted_20260618_curve.csv`
- `results/group_a_plus_switch_policy_backtest_physicist_kupiec_volweighted_20260618_recommended_regime.csv`

### Recommended 結果

最新 recommended 仍為：

`switch_risk_ma90_dd12_total6_hold5`

| 指標 | 值 |
| --- | ---: |
| value_at_risk_5pct | -0.024071234487319793 |
| expected_tail_loss_5pct | -0.037154551087349746 |
| var_breach_count_5pct | 18 |
| var_breach_ratio_5pct | 0.05128205128205128 |
| kupiec_lr_5pct | 0.012048648252033445 |
| kupiec_pvalue_5pct | 0.9125946906191519 |
| volatility_weighted_var_5pct | -0.034821017602288215 |
| volatility_weighted_etl_5pct | -0.0487490000546896 |

### 判斷

- 5% VaR 的實際 breach 比率為 5.13%，非常接近理論 5%。
- Kupiec p-value 為 0.913，未顯示 5% VaR 覆蓋率有明顯偏誤。
- 波動率加權 VaR/ETL 比一般歷史模擬更保守，適合作為壓力風險觀察欄位。
- 這次補強改善的是風險模型驗證與報表完整度，不改變正式 recommended。

## 2026-06-18 補充回測：2020-01-01 到 2024-12-31

使用者要求策略回測 2020~2024。本次使用目前最新的 `backtest_group_a_plus_switch_policy.py`，包含 A20.1 risk6、A20.4 ETL、A20.5 Kupiec 與波動率加權 VaR/ETL 評估欄位。

### 資料檢查

四個標的在此區間資料完整：

| ticker | 起始日 | 結束日 | 筆數 |
| --- | --- | --- | ---: |
| 0050.TW | 2020-01-02 | 2024-12-31 | 1215 |
| 00631L.TW | 2020-01-02 | 2024-12-31 | 1215 |
| 00632R.TW | 2020-01-02 | 2024-12-31 | 1215 |
| 00679B.TWO | 2020-01-02 | 2024-12-31 | 1215 |

### 回測命令

```bash
python3 backtest_group_a_plus_switch_policy.py --start 2020-01-01 --end 2024-12-31 --initial-value 1000000 --output-prefix results/group_a_plus_switch_policy_backtest_2020_2024_20260618
```

輸出檔案：

- `results/group_a_plus_switch_policy_backtest_2020_2024_20260618.json`
- `results/group_a_plus_switch_policy_backtest_2020_2024_20260618.csv`
- `results/group_a_plus_switch_policy_backtest_2020_2024_20260618_curve.csv`
- `results/group_a_plus_switch_policy_backtest_2020_2024_20260618_recommended_regime.csv`

### 2020~2024 Recommended

此區間 recommended 為：

`switch_ma20_dd7_hold5`

| 指標 | 值 |
| --- | ---: |
| final | 2159413.2614561943 |
| total_return | 1.1594132614561943 |
| annual_return | 0.16657577118284128 |
| volatility | 0.19707365131554813 |
| downside_deviation | 0.2039414309349385 |
| Sharpe | 0.9098145827021811 |
| Sortino | 0.8791763449499925 |
| max_drawdown | -0.32708975389876493 |
| value_at_risk_5pct | -0.01844703004961485 |
| expected_tail_loss_5pct | -0.028589521143004476 |
| var_breach_count_5pct | 61 |
| var_breach_ratio_5pct | 0.05024711696869852 |
| kupiec_pvalue_5pct | 0.9685113494349635 |
| volatility_weighted_etl_5pct | -0.01992672584277648 |
| worst_daily_return | -0.08165665491955665 |
| worst_20d_return | -0.22993809378457397 |
| switch_count | 34 |

### 指定比較

| variant | final | total_return | Sharpe | Sortino | MDD | ETL 5% | vol-weighted ETL 5% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `golden1_0531_1m` | 2286404 左右 | 1.286404 | 0.858842 | 0.812946 | -0.370064 | -0.034186 | -0.025462 |
| `group_a_plus_defensive_1m` | 2052614 左右 | 1.052614 | 0.828629 | 0.795463 | -0.344919 | -0.030294 | -0.022420 |
| `switch_ma20_dd7_hold5` | 2159413.2614561943 | 1.159413 | 0.909815 | 0.879176 | -0.327090 | -0.028590 | -0.019927 |
| `switch_ma90_dd12_hold5_eg020_xg010` | 2136587 左右 | 1.136587 | 0.891373 | 0.856273 | -0.313735 | -0.029301 | -0.019985 |
| `switch_risk_ma90_dd12_total6_hold5` | 2323055 左右 | 1.323055 | 0.866320 | 0.822660 | -0.375804 | -0.034375 | -0.025748 |

### 判斷

- 2020~2024 和 2025~2026 的最佳規則不同。
- 若以 Sharpe、Sortino、MDD 與尾端風險平衡來看，2020~2024 由 `switch_ma20_dd7_hold5` 勝出。
- 若只看 final value，`switch_risk_ma90_dd12_total6_hold5` 最高，但波動與回撤顯著較大，MDD 達 -37.58%。
- 因此 `risk6` 比較像 2025~2026 最新區間的 recommended；在 2020~2024 長區間，較快的 MA20/DD7 防守較穩。
- 此回測會更新 `report/group_a_plus/latest/switch_backtest.json` 指向 2020~2024 結果；若要恢復 latest pointer 到 2026 最新資料版本，可重新跑 2026 最新區間或手動改回 A20.5 結果。

## 2026-06-18 補充微調：2020~2024 MA20/DD7 鄰近 Sweep

使用者詢問「做微調，會有差異？」本次以 2020~2024 區間的 recommended `switch_ma20_dd7_hold5` 為中心，做短週期防守規則的鄰近參數 sweep。

### 微調目的

確認 `switch_ma20_dd7_hold5` 是否只是粗略最佳，或在 MA window、drawdown、hold days、enter/exit MA gap 附近微調後能改善 Sharpe、MDD、ETL 或 final。

### Sweep 命令

```bash
python3 evaluate_group_a_plus_switch_sweep.py --start 2020-01-01 --end 2024-12-31 --ma-windows 15,20,25,30 --drawdowns=-0.05,-0.06,-0.07,-0.08,-0.09 --hold-days 3,5,7,10 --enter-ma-gaps=-0.015,-0.02,-0.025,-0.03,-0.035 --exit-ma-gaps 0.005,0.01,0.015 --chip-scores 0 --derivative-scores 0 --total-risk-scores 0 --tail-risk-scores 0 --output results/group_a_plus_switch_micro_sweep_2020_2024_20260618.json
```

### 輸出檔案

- `results/group_a_plus_switch_micro_sweep_2020_2024_20260618.json`
- `results/group_a_plus_switch_micro_sweep_2020_2024_20260618.csv`
- `results/group_a_plus_switch_micro_sweep_2020_2024_20260618_best_regime.csv`

### Sweep 結果

| 欄位 | 值 |
| --- | ---: |
| rules_total | 1200 |
| eligible | 3 |
| best variant | `switch_ma15_dd07_hold3_eg035_xg005` |
| final | 2246259.517979381 |
| total_return | 1.246259517979381 |
| Sharpe | 0.9432041954406568 |
| max_drawdown | -0.3235953968673918 |
| defense_days | 237 |
| switch_count | 28 |

最佳規則參數：

| 參數 | 值 |
| --- | ---: |
| ma_window | 15 |
| enter_ma_gap | -0.035 |
| exit_ma_gap | 0.005 |
| drawdown_window | 15 |
| enter_drawdown | -0.07 |
| exit_momentum_days | 5 |
| min_hold_days | 3 |
| require_chip_score | 0 |
| require_derivative_score | 0 |
| require_total_risk_score | 0 |
| require_tail_risk_score | 0 |

### 與原 2020~2024 recommended 比較

| 策略 | final | total_return | Sharpe | MDD | defense_days | switch_count |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 原 `switch_ma20_dd7_hold5` | 2159413.2614561943 | 1.1594132614561943 | 0.9098145827021811 | -0.32708975389876493 | 309 | 34 |
| 微調最佳 `switch_ma15_dd07_hold3_eg035_xg005` | 2246259.517979381 | 1.246259517979381 | 0.9432041954406568 | -0.3235953968673918 | 237 | 28 |

改善幅度：

- final 增加約 `86846.25652318669`
- total_return 增加約 `8.6846` 個百分點
- Sharpe 從 `0.9098` 提升到 `0.9432`
- MDD 從 `-32.71%` 改善到 `-32.36%`
- switch_count 從 `34` 降到 `28`

### Top 參數集中區

Sharpe 前幾名集中在：

- `ma_window=15`
- `enter_drawdown=-0.07` 或 `-0.08`
- `hold_days=3` 或 `5`
- `enter_ma_gap=-0.035`
- `exit_ma_gap=0.005`

這表示 2020~2024 長區間中，較快的 MA15、防守觸發稍嚴、退出門檻較低，比 MA20/DD7 原設定更穩。

### 初步判斷

- 微調確實有改善，不只是雜訊上的微小差異。
- 但 1200 組中只有 3 組 eligible，代表可接受參數區仍偏窄。
- 目前不建議直接把 `switch_ma15_dd07_hold3_eg035_xg005` 升級成最新正式策略，應再做 walk-forward、分年度、2025~2026 out-of-sample 驗證。
- 對 2020~2024 區間而言，`switch_ma15_dd07_hold3_eg035_xg005` 是目前較佳微調候選。

## 2026-06-18 微調候選穩定性驗證：分年度與 2025~2026 OOS

延續 2020~2024 微調結果，針對候選 `switch_ma15_dd07_hold3_eg035_xg005` 做分年度與 2025~2026 out-of-sample 驗證。驗證範圍不是重新掃 1200 組，而是縮小到 MA15/MA20、DD7、hold3/hold5、enter gap -3.5%/-3.0%、exit gap 0.5%/1.0% 的 16 組鄰近規則。

### 驗證命令樣板

```bash
python3 evaluate_group_a_plus_switch_sweep.py --start YYYY-01-01 --end YYYY-12-31 --ma-windows 15,20 --drawdowns=-0.07 --hold-days 3,5 --enter-ma-gaps=-0.035,-0.03 --exit-ma-gaps 0.005,0.01 --chip-scores 0 --derivative-scores 0 --total-risk-scores 0 --tail-risk-scores 0 --output results/group_a_plus_micro_validate_YYYY_20260618.json
```

2025~2026 使用：

```bash
python3 evaluate_group_a_plus_switch_sweep.py --start 2025-01-01 --end 2026-06-18 --ma-windows 15,20 --drawdowns=-0.07 --hold-days 3,5 --enter-ma-gaps=-0.035,-0.03 --exit-ma-gaps 0.005,0.01 --chip-scores 0 --derivative-scores 0 --total-risk-scores 0 --tail-risk-scores 0 --output results/group_a_plus_micro_validate_2025_2026_20260618.json
```

### 驗證輸出

- `results/group_a_plus_micro_validate_2020_20260618.json`
- `results/group_a_plus_micro_validate_2021_20260618.json`
- `results/group_a_plus_micro_validate_2022_20260618.json`
- `results/group_a_plus_micro_validate_2023_20260618.json`
- `results/group_a_plus_micro_validate_2024_20260618.json`
- `results/group_a_plus_micro_validate_2025_2026_20260618.json`

### 分年度結果

| period | 年度最佳 | best final | best Sharpe | best MDD | 候選 final | 候選 Sharpe | 候選 MDD | 原 MA20/DD7 final | 原 MA20/DD7 Sharpe |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2020 | `switch_ma15_dd07_hold3_eg035_xg005` | 1337717.179 | 1.449956 | -0.275051 | 1337717.179 | 1.449956 | -0.275051 | 1325486.690 | 1.418699 |
| 2021 | `switch_ma20_dd07_hold3_eg030_xg005` | 1197744.831 | 1.151213 | -0.106855 | 1194436.863 | 1.138649 | -0.105903 | 1190242.207 | 1.123559 |
| 2022 | `switch_ma15_dd07_hold3_eg030_xg005` | 791194.777 | -1.085847 | -0.319179 | 786929.112 | -1.106284 | -0.322849 | 781272.672 | -1.152885 |
| 2023 | `switch_ma15_dd07_hold3_eg035_xg005` | 1255346.092 | 1.779839 | -0.085248 | 1255346.092 | 1.779839 | -0.085248 | 1237863.026 | 1.740586 |
| 2024 | `switch_ma15_dd07_hold3_eg035_xg005` | 1383552.722 | 1.581434 | -0.199312 | 1383552.722 | 1.581434 | -0.199312 | 1375698.228 | 1.561138 |
| 2025~2026 | `switch_ma20_dd07_hold5_eg035_xg005` | 2159529.881 | 2.273221 | -0.255848 | 2127527.649 | 2.210463 | -0.265154 | 2153677.140 | 2.267601 |

### 穩定性判斷

- 候選 `switch_ma15_dd07_hold3_eg035_xg005` 在 2020、2023、2024 是年度最佳。
- 2021 與 2022 不是最佳，但表現接近年度最佳，且仍優於原 MA20/DD7 設定。
- 2025~2026 out-of-sample 明確輸給 `switch_ma20_dd07_hold5_eg035_xg005` 與原 MA20/DD7 類規則，Sharpe 與 MDD 都較差。
- 結論：此候選可視為 2020~2024 較佳微調候選，但不應直接取代最新 2025~2026 策略，也不應升級為全時段正式 recommended。
- 後續若要正式採用，應做 regime-aware rule selection：例如 2020~2024 採 MA15/DD7，2025~2026 採 MA20/DD7 或 risk6，並用 walk-forward 決定切換，而不是固定單一參數。

## 2026-06-18 最新策略改善：A20.6 MA80/DD11 Risk6 Confirm

使用者要求「最新策略還能改善」。本次把最新策略定義為 2025~2026 最新資料區間下的 `switch_risk_ma90_dd12_total6_hold5`，不是 2020~2024 的 MA15/MA20 候選。

### Fine Sweep 目的

針對原最新規則 `risk_ma90_dd12_total6_hold5` 附近做更細參數掃描，確認 MA window、drawdown window、enter/exit gap、hold days 與 total risk score 是否可小幅改善。

### Fine Sweep 命令

```bash
python3 evaluate_group_a_plus_switch_sweep.py --start 2025-01-01 --end 2026-06-18 --ma-windows 75,80,85,90,95,100,105 --drawdowns=-0.10,-0.11,-0.12,-0.13,-0.14 --hold-days 3,5,7,10 --enter-ma-gaps=-0.015,-0.02,-0.025,-0.03 --exit-ma-gaps 0.005,0.01,0.015 --chip-scores 0 --derivative-scores 0 --total-risk-scores 4,5,6,7 --tail-risk-scores 0 --output results/group_a_plus_latest_risk6_fine_sweep_20260618.json
```

### Fine Sweep 輸出

- `results/group_a_plus_latest_risk6_fine_sweep_20260618.json`
- `results/group_a_plus_latest_risk6_fine_sweep_20260618.csv`
- `results/group_a_plus_latest_risk6_fine_sweep_20260618_best_regime.csv`

### Fine Sweep 結果

| 欄位 | 值 |
| --- | ---: |
| rules_total | 6720 |
| eligible | 5491 |
| sweep best | `switch_risk4_ma80_dd11_hold3_eg015_xg015` |
| best final | 2331697.046615322 |
| best total_return | 1.331697046615322 |
| best Sharpe | 2.3388947223844325 |
| best MDD | -0.2527534866588963 |
| defense_days | 68 |
| switch_count | 2 |

`risk4`、`risk5`、`risk6` 在 top 組合中績效相同，因為實際進防守日的 `total_risk_score=6`。因此正式採用較強語義的 `total_risk_score>=6`，而不是放寬到 risk4。

### 已加入正式規則

`backtest_group_a_plus_switch_policy.py` 新增：

`switch_risk_ma80_dd11_total6_hold5_eg015_xg015`

規則參數：

| 參數 | 值 |
| --- | ---: |
| ma_window | 80 |
| enter_ma_gap | -0.015 |
| exit_ma_gap | 0.015 |
| drawdown_window | 80 |
| enter_drawdown | -0.11 |
| exit_momentum_days | 5 |
| min_hold_days | 5 |
| require_total_risk_score | 6 |
| exit_max_total_risk_score | 6 |

### 正式回測命令

```bash
python3 backtest_group_a_plus_switch_policy.py --start 2025-01-01 --end 2026-06-18 --initial-value 1000000 --output-prefix results/group_a_plus_switch_policy_backtest_latest_ma80_risk6_confirm_20260618
```

正式回測輸出：

- `results/group_a_plus_switch_policy_backtest_latest_ma80_risk6_confirm_20260618.json`
- `results/group_a_plus_switch_policy_backtest_latest_ma80_risk6_confirm_20260618.csv`
- `results/group_a_plus_switch_policy_backtest_latest_ma80_risk6_confirm_20260618_curve.csv`
- `results/group_a_plus_switch_policy_backtest_latest_ma80_risk6_confirm_20260618_recommended_regime.csv`

### 新舊最新策略比較

| variant | final | total_return | annual_return | Sharpe | Sortino | MDD | ETL 5% | vol-weighted ETL 5% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 舊 `switch_risk_ma90_dd12_total6_hold5` | 2325814.145408824 | 1.325814145408824 | 0.7851544312753163 | 2.333534662012485 | 2.4816126308305324 | -0.2534834443117512 | -0.037154551087349746 | -0.0487490000546896 |
| 新 `switch_risk_ma80_dd11_total6_hold5_eg015_xg015` | 2331697.046615322 | 1.331697046615322 | 0.78825326969272 | 2.3388947223844325 | 2.488440089629703 | -0.2527534866588963 | -0.03717461771901778 | -0.04883159236295872 |

改善幅度：

- final 增加約 `5882.901206498966`
- total_return 增加約 `0.5883` 個百分點
- Sharpe 從 `2.3335` 提升到 `2.3389`
- Sortino 從 `2.4816` 提升到 `2.4884`
- MDD 從 `-25.35%` 改善到 `-25.28%`
- ETL 5% 與 volatility-weighted ETL 5% 略差一點點，屬於小幅進攻換取整體績效改善。

### 新規則切換事件

| 日期 | 事件 | ma_gap | drawdown | chip_score | derivative_score | total_risk_score |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 2025-02-25 | switch_to_group_a_plus_defensive | -0.01792424670813675 | -0.052592956560674864 | 5 | 1 | 6 |
| 2025-06-06 | switch_to_golden | 0.017066377264902677 | -0.08082849328956299 | 2 | 0 | 2 |

舊規則切換日為 2025-02-27 進防守、2025-06-09 退出；新規則提早兩個自然日進防守，並提早到 2025-06-06 退出。

### A20.6 結論

- 最新策略可小幅改善。
- 正式 recommended 更新為 `switch_risk_ma80_dd11_total6_hold5_eg015_xg015`。
- 此改善不是大幅跳升，而是對 2025~2026 區間的 risk6 switch layer 做更精細的 MA/DD/gap 調整。
- 因仍保留 `total_risk_score>=6`，風險確認語義沒有放寬。
- 後續仍需用 2020~2024、分年度與 walk-forward 檢查，避免只對 2025~2026 過度配適。

## 2026-06-18 最新策略二次改善：A20.7 MA75/DD11 Risk6 Confirm

延續 A20.6，使用者再問「最新策略還能改善？」本次不放寬風險確認條件，固定 `total_risk_score=6`，在 A20.6 的 MA80/DD11 附近做第二輪 refine。

### Refine2 Sweep 命令

```bash
python3 evaluate_group_a_plus_switch_sweep.py --start 2025-01-01 --end 2026-06-18 --ma-windows 70,75,80,85,90 --drawdowns=-0.105,-0.11,-0.115,-0.12 --hold-days 3,5,7 --enter-ma-gaps=-0.01,-0.0125,-0.015,-0.0175,-0.02 --exit-ma-gaps 0.01,0.0125,0.015,0.0175,0.02 --chip-scores 0 --derivative-scores 0 --total-risk-scores 6 --tail-risk-scores 0 --output results/group_a_plus_latest_ma80_risk6_refine2_sweep_20260618.json
```

### Refine2 輸出

- `results/group_a_plus_latest_ma80_risk6_refine2_sweep_20260618.json`
- `results/group_a_plus_latest_ma80_risk6_refine2_sweep_20260618.csv`
- `results/group_a_plus_latest_ma80_risk6_refine2_sweep_20260618_best_regime.csv`

### Refine2 結果

| 欄位 | 值 |
| --- | ---: |
| rules_total | 1125 |
| eligible | 857 |
| sweep best | `switch_risk6_ma75_dd11_hold3_eg017_xg020` |
| best final | 2333356.2334819334 |
| best total_return | 1.3333562334819336 |
| best Sharpe | 2.3399277909169327 |
| best MDD | -0.2527534866588963 |
| defense_days | 67 |
| switch_count | 2 |

top 組合中 hold3、hold5、hold7 績效相同，因此正式採用 hold5，保持與 A20.6 同樣的持有語義。

### 已加入正式規則

`backtest_group_a_plus_switch_policy.py` 新增：

`switch_risk_ma75_dd11_total6_hold5_eg0175_xg020`

規則參數：

| 參數 | 值 |
| --- | ---: |
| ma_window | 75 |
| enter_ma_gap | -0.0175 |
| exit_ma_gap | 0.02 |
| drawdown_window | 75 |
| enter_drawdown | -0.11 |
| exit_momentum_days | 5 |
| min_hold_days | 5 |
| require_total_risk_score | 6 |
| exit_max_total_risk_score | 6 |

### 正式回測命令

```bash
python3 backtest_group_a_plus_switch_policy.py --start 2025-01-01 --end 2026-06-18 --initial-value 1000000 --output-prefix results/group_a_plus_switch_policy_backtest_latest_ma75_risk6_confirm_20260618
```

正式回測輸出：

- `results/group_a_plus_switch_policy_backtest_latest_ma75_risk6_confirm_20260618.json`
- `results/group_a_plus_switch_policy_backtest_latest_ma75_risk6_confirm_20260618.csv`
- `results/group_a_plus_switch_policy_backtest_latest_ma75_risk6_confirm_20260618_curve.csv`
- `results/group_a_plus_switch_policy_backtest_latest_ma75_risk6_confirm_20260618_recommended_regime.csv`

### A20.5 / A20.6 / A20.7 比較

| variant | final | total_return | annual_return | Sharpe | Sortino | MDD | ETL 5% | vol-weighted ETL 5% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A20.5 `switch_risk_ma90_dd12_total6_hold5` | 2325814.145408824 | 1.325814145408824 | 0.7851544312753163 | 2.333534662012485 | 2.4816126308305324 | -0.2534834443117512 | -0.037154551087349746 | -0.0487490000546896 |
| A20.6 `switch_risk_ma80_dd11_total6_hold5_eg015_xg015` | 2331697.046615322 | 1.331697046615322 | 0.78825326969272 | 2.3388947223844325 | 2.488440089629703 | -0.2527534866588963 | -0.03717461771901778 | -0.04883159236295872 |
| A20.7 `switch_risk_ma75_dd11_total6_hold5_eg0175_xg020` | 2333356.2334819334 | 1.3333562334819336 | 0.7891268088537762 | 2.3399277909169327 | 2.4896386567803552 | -0.2527534866588963 | -0.03718987332346835 | -0.048858150651903146 |

### A20.7 切換事件

| 日期 | 事件 | ma_gap | drawdown | chip_score | derivative_score | total_risk_score |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 2025-02-25 | switch_to_group_a_plus_defensive | -0.01792424670813675 | -0.052592956560674864 | 5 | 1 | 6 |
| 2025-06-05 | switch_to_golden | 0.021083048030267726 | -0.08234404295555386 | 2 | 0 | 2 |

### A20.7 判斷

- A20.7 相對 A20.6 只早一天退出防守，屬於非常小幅的參數改善。
- final、Sharpe、Sortino 再提升，MDD 持平。
- ETL 5% 與 volatility-weighted ETL 5% 比 A20.6 再略差，表示它更偏進攻。
- 因仍維持 `total_risk_score>=6`，風險確認沒有放寬。
- 最新 recommended 更新為 `switch_risk_ma75_dd11_total6_hold5_eg0175_xg020`，但仍需後續用 2020~2024 與 walk-forward 檢查過度配適。

## 2026-06-18 最新策略再檢查：Regime-Aware 上限實驗

使用者再次詢問「最新策略還能改善？」本次先檢查 A20.7 在不同區間的穩定性，再做一個 regime-aware 上限實驗。

### 穩定性檢查結論

| 區間 | 風險調整最佳 | 判斷 |
| --- | --- | --- |
| 2020~2024 | `switch_ma20_dd7_hold5` | 舊區間短週期防守較穩 |
| 2025~2026 | `switch_risk_ma75_dd11_total6_hold5_eg0175_xg020` | 最新 A20.7 最佳 |
| 2020~2026 | `switch_ma90_dd12_hold5_eg020_xg010` | 全期單一規則較中性 |

A20.7 在 2025~2026 是最佳，但放到 2020~2026 全期時，Sharpe 低於 `MA90/DD12`，MDD 也較深。因此，若要再改善，不應繼續只微調 2025~2026 單一區間，而應做 regime-aware rule selection。

### Regime-Aware 上限實驗

實驗設定：

- 2020-01-02 到 2024-12-31 使用 `switch_ma20_dd7_hold5`
- 2025-01-01 到 2026-06-18 使用 A20.7 `switch_risk_ma75_dd11_total6_hold5_eg0175_xg020`

輸出：

- `results/group_a_plus_regime_aware_2020_2026_ma20_then_a207_20260618.json`
- `results/group_a_plus_regime_aware_2020_2026_ma20_then_a207_20260618.csv`

結果：

| 指標 | Regime-aware 上限 |
| --- | ---: |
| final | 4972873.815355964 |
| total_return | 3.972873815355964 |
| annual_return | 0.28190992637303847 |
| Sharpe | 1.294016432765248 |
| Sortino | 1.2946271613594627 |
| MDD | -0.32708975389876493 |
| ETL 5% | -0.030862729503793165 |
| volatility-weighted ETL 5% | -0.05101483596268919 |
| switch_count | 36 |

對照全期單一規則 `switch_ma90_dd12_hold5_eg020_xg010`：

- final：`4908123.923958069`
- Sharpe：`1.277932828372868`
- MDD：`-0.3137345194318949`

### 判斷

- Regime-aware 上限實驗可提高 full-period final 與 Sharpe。
- 但 MDD 比全期單一 `MA90/DD12` 更深，且使用 2025 作為切點有 hindsight bias。
- 因此它不能直接升級為正式策略，只能證明「下一個有效改善方向」是自動 regime selection，而不是繼續微調 A20.7。
- latest pointer 已恢復到 A20.7：`switch_risk_ma75_dd11_total6_hold5_eg0175_xg020`。

## 2026-06-18 PDF 再分析：Bayesian Methods in Finance

使用者要求從 `C:\Users\isaac\Downloads\FinMathematics-master\FinMathematics-master` 再找一份 PDF，分析是否有可導入 GroupA+ 最新策略的優點。本次選用：

- `Bayesian Methods in Finance.pdf`

### 章節定位

用 `pypdf` 讀取目錄與相關頁面，重點章節如下：

| 頁碼 | 章節 | 對 GroupA+ 的關聯 |
| ---: | --- | --- |
| 152 | Model Uncertainty | 不應只把單一最佳策略視為真實模型，應處理策略模型不確定性 |
| 154 | Bayesian Model Averaging | 可用候選策略的 posterior-like 權重做軟選擇，而不是硬切單一規則 |
| 237 | Markov Regime-Switching GARCH Models | 可用低/中/高波動狀態做自動 regime selection |
| 296 | Risk Measures in Portfolio Construction | downside risk、VaR、CVaR 比標準差更貼近投資人感知風險 |
| 299 | CVaR Optimization | CVaR/ETL 可用於策略或權重選擇，並比 VaR 更適合優化 |

### 可導入項目

1. **立即可導入：STARR / CVaR-adjusted return**
   - 前面已經導入 5% ETL，本次補上 `starr_ratio_5pct`。
   - 定義：平均日報酬 / `abs(expected_tail_loss_5pct)`。
   - 目的：補足 Sharpe/Sortino，讓策略排序同時考慮尾部損失效率。
   - 已修改：`backtest_group_a_plus_switch_policy.py` 的 `_metrics()`。

2. **下一階段可實驗：Bayesian-style model averaging**
   - 候選模型可先固定為：
     - 2020~2024 較穩的 `switch_ma20_dd7_hold5`
     - 全期較均衡的 `switch_ma90_dd12_hold5_eg020_xg010`
     - 最新區間最佳的 A20.7 `switch_risk_ma75_dd11_total6_hold5_eg0175_xg020`
   - 用 rolling window 的 Sharpe、Sortino、MDD、ETL 建立 posterior-like score。
   - 以 softmax 權重或門檻選出當期策略，避免固定 2025 作為 hindsight 切點。

3. **下一階段可實驗：regime-switching volatility state**
   - 不必一開始實作完整 Bayesian MS-GARCH。
   - 可先用簡化版三狀態波動：
     - low volatility
     - normal volatility
     - high volatility
   - 狀態可由 20/60/120 日波動分位數與轉移穩定天數推估，再決定使用 MA20、MA90 或 A20.7。

4. **暫不建議直接導入：完整 Bayesian MS-GARCH / MCMC**
   - 需要大量估計與穩定性驗證。
   - 對目前 GroupA+ 的回測框架而言，直接導入容易增加計算複雜度與過度配適。
   - 建議先做 proxy regime selector，若 walk-forward 有明顯改善，再考慮更完整模型。

### 本次實作

新增 `starr_ratio_5pct` 後重跑最新 A20.7 回測：

- 指令：
  - `python3 -m py_compile backtest_group_a_plus_switch_policy.py`
  - `python3 backtest_group_a_plus_switch_policy.py --start 2025-01-02 --end 2026-06-18 --output-prefix results/group_a_plus_switch_policy_backtest_latest_ma75_risk6_confirm_20260618 --latest-pointer report/group_a_plus/latest/switch_backtest.json`
- 輸出：
  - `results/group_a_plus_switch_policy_backtest_latest_ma75_risk6_confirm_20260618.json`
  - `results/group_a_plus_switch_policy_backtest_latest_ma75_risk6_confirm_20260618.csv`
  - `results/group_a_plus_switch_policy_backtest_latest_ma75_risk6_confirm_20260618_curve.csv`
  - `results/group_a_plus_switch_policy_backtest_latest_ma75_risk6_confirm_20260618_recommended_regime.csv`

### STARR 檢查結果

| variant | final | Sharpe | Sortino | MDD | ETL 5% | STARR 5% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `golden1_0531_1m` | 2246432.231891271 | 2.229630818237287 | 2.3271844833336277 | -0.27538670040425206 | -0.03772760000608948 | 0.06524748850458718 |
| `group_a_plus_defensive_1m` | 2112079.6651531374 | 2.2676785041878786 | 2.3935445287597306 | -0.25346979287067073 | -0.03317434565254426 | 0.06802626369512531 |
| A20.7 `switch_risk_ma75_dd11_total6_hold5_eg0175_xg020` | 2333356.2334819334 | 2.3399277909169327 | 2.4896386567803552 | -0.2527534866588963 | -0.03718987332346835 | 0.06905139898243232 |

### 判斷

- A20.7 在 STARR 5% 仍高於 Golden1 與單純 GroupA+ defensive，表示用尾部損失調整後仍合理。
- 本次 PDF 導入未改變正式 recommended；正式策略仍維持 A20.7。
- 真正有機會改善的方向是 Bayesian-style / regime-aware rule selection，而不是繼續在 A20.7 的 MA/DD 門檻做小幅微調。

## 2026-06-19 新策略 A20.7 回測：2020~2024

使用者要求「將新策略回測2020~2024」。本次以最新 A20.7 switch rule 參與同一套 2020~2024 回測，並保留獨立輸出，避免覆蓋舊結果。

### 指令

- `python3 -m py_compile backtest_group_a_plus_switch_policy.py`
- `python3 backtest_group_a_plus_switch_policy.py --start 2020-01-02 --end 2024-12-31 --output-prefix results/group_a_plus_switch_policy_backtest_2020_2024_a207_latest_20260619`
- 因此腳本會同步更新 `report/group_a_plus/latest/switch_backtest.json`，回測後已立刻重跑 2025~2026 A20.7，將 latest pointer 恢復為正式最新策略。

### 輸出

- `results/group_a_plus_switch_policy_backtest_2020_2024_a207_latest_20260619.json`
- `results/group_a_plus_switch_policy_backtest_2020_2024_a207_latest_20260619.csv`
- `results/group_a_plus_switch_policy_backtest_2020_2024_a207_latest_20260619_curve.csv`
- `results/group_a_plus_switch_policy_backtest_2020_2024_a207_latest_20260619_recommended_regime.csv`

### 2020~2024 結果

| variant | final | total_return | Sharpe | Sortino | MDD | ETL 5% | STARR 5% | switch_count |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `golden1_0531_1m` | 2286403.73298109 | 1.28640373298109 | 0.85884249512305 | 0.8129461692354303 | -0.3700639131250332 | -0.034185918243866416 | 0.02305197636166174 |  |
| `group_a_plus_defensive_1m` | 2052613.726685848 | 1.052613726685848 | 0.8286287202207893 | 0.795462903399181 | -0.3449191318695233 | -0.030294494697666968 | 0.022343899866443136 |  |
| 2020~2024 recommended `switch_ma20_dd7_hold5` | 2159413.2614561943 | 1.1594132614561943 | 0.9098145827021811 | 0.8791763449499925 | -0.32708975389876493 | -0.028589521143004476 | 0.024887085201101496 | 34 |
| A20.7 `switch_risk_ma75_dd11_total6_hold5_eg0175_xg020` | 2343193.374873824 | 1.3431933748738238 | 0.8702898255394882 | 0.826594074932757 | -0.37759346735702204 | -0.034560167394787206 | 0.023491463009054372 | 2 |
| A20.6 `switch_risk_ma80_dd11_total6_hold5_eg015_xg015` | 2343193.374873824 | 1.3431933748738238 | 0.8702898255394882 | 0.826594074932757 | -0.37759346735702204 | -0.034560167394787206 | 0.023491463009054372 | 2 |
| A20.5 `switch_risk_ma90_dd12_total6_hold5` | 2323055.2244162415 | 1.3230552244162417 | 0.8663200842743398 | 0.8226599807737437 | -0.37580373037017245 | -0.03437488606803256 | 0.023373860463457404 | 2 |

### A20.7 切換事件

| 日期 | 事件 | ma_gap | drawdown | chip_score | derivative_score | total_risk_score |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 2020-03-06 | switch_to_group_a_plus_defensive | -0.048714847961127905 | -0.10395537686230549 | 6 | 0 | 6 |
| 2020-06-01 | switch_to_golden | 0.02170984595630343 | -0.08660565558539823 | 1 | 0 | 1 |

### 判斷

- A20.7 在 2020~2024 的 final 最高，高於 Golden1 與 2020~2024 recommended。
- 但 A20.7 的 Sharpe、Sortino、MDD、ETL、STARR 全部輸給 `switch_ma20_dd7_hold5`。
- A20.7 只切換 2 次，等於舊區間大多維持較進攻曝險；這提高 final，但也擴大回撤與尾部損失。
- 因此 2020~2024 不支持把 A20.7 作為全歷史唯一規則；它仍較適合 2025~2026 近期 regime。
- 結論維持：下一步應做 Bayesian-style / regime-aware rule selection，讓舊區間採短週期防守、近期區間採 A20.7，而不是把 A20.7 硬套全期。

## 2026-06-19 A20.7 最新策略微調實驗

使用者要求「對最新策略做微調」。本次不放寬風險確認，固定：

- `require_total_risk_score=6`
- `exit_max_total_risk_score=6`
- `min_hold_days=5`
- 不啟用 tail risk 硬門檻

目的：只在 A20.7 附近微調 MA window、drawdown、enter gap、exit gap，確認是否能找到比正式 A20.7 更好的近鄰參數。

### Sweep 1：A20.7 周邊細網格

指令：

```bash
python3 evaluate_group_a_plus_switch_sweep.py --start 2025-01-02 --end 2026-06-18 --ma-windows 72,73,74,75,76,77,78 --drawdowns=-0.105,-0.11,-0.115 --hold-days 5 --enter-ma-gaps=-0.01625,-0.0175,-0.01875,-0.02 --exit-ma-gaps 0.01875,0.02,0.02125,0.0225 --chip-scores 0 --derivative-scores 0 --total-risk-scores 6 --tail-risk-scores 0 --output results/group_a_plus_latest_a207_micro_sweep_20260619.json
```

輸出：

- `results/group_a_plus_latest_a207_micro_sweep_20260619.json`
- `results/group_a_plus_latest_a207_micro_sweep_20260619.csv`
- `results/group_a_plus_latest_a207_micro_sweep_20260619_best_regime.csv`

結果：

- rules_total：224
- eligible：112
- best：`switch_risk6_ma73_dd11_hold5_eg017_xg022`
- 但 best 與正式 A20.7 的交易日期、final、Sharpe、Sortino、MDD、ETL、STARR 完全相同。

| variant | final | Sharpe | Sortino | MDD | ETL 5% | STARR 5% | switch_count | 切換 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Sweep 1 best `switch_risk6_ma73_dd11_hold5_eg017_xg022` | 2333356.2334819334 | 2.3399277909169327 | 2.4896386567803552 | -0.2527534866588963 | -0.03718987332346835 | 0.06905139898243232 | 2 | 2025-02-25 進防守、2025-06-05 回 Golden |
| 正式 A20.7 `switch_risk_ma75_dd11_total6_hold5_eg0175_xg020` | 2333356.2334819334 | 2.3399277909169327 | 2.4896386567803552 | -0.2527534866588963 | -0.03718987332346835 | 0.06905139898243232 | 2 | 2025-02-25 進防守、2025-06-05 回 Golden |

### Sweep 2：降低 exit gap，測試更早退出防守

指令：

```bash
python3 evaluate_group_a_plus_switch_sweep.py --start 2025-01-02 --end 2026-06-18 --ma-windows 68,69,70,71,72,73,74,75,76 --drawdowns=-0.105,-0.11,-0.115 --hold-days 5 --enter-ma-gaps=-0.015,-0.01625,-0.0175,-0.01875 --exit-ma-gaps 0.0125,0.015,0.01625,0.0175,0.01875,0.02 --chip-scores 0 --derivative-scores 0 --total-risk-scores 6 --tail-risk-scores 0 --output results/group_a_plus_latest_a207_micro_sweep_exit_low_20260619.json
```

輸出：

- `results/group_a_plus_latest_a207_micro_sweep_exit_low_20260619.json`
- `results/group_a_plus_latest_a207_micro_sweep_exit_low_20260619.csv`
- `results/group_a_plus_latest_a207_micro_sweep_exit_low_20260619_best_regime.csv`

結果：

- rules_total：432
- eligible：216
- best：`switch_risk6_ma75_dd11_hold5_eg017_xg020`
- 這就是正式 A20.7 的同一組參數。
- 沒有任何候選同時滿足：
  - final 高於 A20.7
  - Sharpe 不低於 A20.7
  - MDD 不差於 A20.7

### 重要觀察

| 候選 | 變化 | 結果 |
| --- | --- | --- |
| `MA73/DD11/enter -1.75%/exit 2.25%` | 與 A20.7 等價 | 指標完全相同，切換日期相同 |
| `MA76/DD11/enter -1.75%/exit 1.875%` | 與 A20.7 等價 | 指標完全相同，切換日期相同 |
| `enter -1.50%` 或 `enter -1.625%` | 提早到 2025-02-14 進防守 | final 降到 2330731.433333792，Sharpe 降到 2.337588326759241，MDD 變差到 -0.25368855132388735 |
| exit gap 高於 A20.7 的部分組合 | 延後到 2025-06-06 回 Golden | final 降到 2331697.046615322，Sharpe 降到 2.3388947223844325 |

### 結論

- A20.7 附近已形成一個「平台」：多組近鄰參數產生同樣切換日期與同樣績效。
- 真正更早進場或更晚/更早出場的候選，績效反而下降。
- 本次微調沒有找到可升級為 A20.8 的候選。
- 正式 latest strategy 維持 A20.7：
  - `switch_risk_ma75_dd11_total6_hold5_eg0175_xg020`
- 後續若要改善，方向仍是 regime-aware / Bayesian-style model selection，而不是繼續壓榨 A20.7 附近門檻。
