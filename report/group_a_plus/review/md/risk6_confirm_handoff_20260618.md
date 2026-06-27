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

## 2026-06-19 PDF 方向 1：Bayesian-style Rule Selector

使用者在 PDF 可導入方向中選擇 `1`，本次依 `Bayesian Methods in Finance.pdf` 的 model uncertainty / Bayesian model averaging 概念，新增 research-only 腳本：

- `backtest_group_a_plus_bayesian_selector.py`

### 方法

把每條 switch rule 視為一個 model，候選固定為：

- `ma20_dd7_hold5`
- `risk_ma90_dd12_total6_hold5`
- A20.7 `risk_ma75_dd11_total6_hold5_eg0175_xg020`

每日只用前一日以前的 rolling return 計算 posterior-like score，score 由 Sortino、annual return、MDD、ETL 組成，再用 MAP rule 決定當天採用哪條 rule 的 `golden1` / `group_a_plus_defensive` regime。為避免短期噪音過度切換，加入 `--switch-score-edge`，只有候選 score 超過 default rule 指定門檻才允許切走。

### 指令

```bash
python3 -m py_compile backtest_group_a_plus_bayesian_selector.py
python3 backtest_group_a_plus_bayesian_selector.py --start 2025-01-02 --end 2026-06-18 --output-prefix results/group_a_plus_bayesian_selector_2025_2026_20260619
python3 backtest_group_a_plus_bayesian_selector.py --start 2025-01-02 --end 2026-06-18 --switch-score-edge 0.10 --output-prefix results/group_a_plus_bayesian_selector_2025_2026_edge010_20260619
python3 backtest_group_a_plus_bayesian_selector.py --start 2025-01-02 --end 2026-06-18 --switch-score-edge 0.20 --output-prefix results/group_a_plus_bayesian_selector_2025_2026_edge020_20260619
python3 backtest_group_a_plus_bayesian_selector.py --start 2020-01-02 --end 2026-06-18 --switch-score-edge 0.20 --output-prefix results/group_a_plus_bayesian_selector_2020_2026_edge020_20260619
python3 backtest_group_a_plus_bayesian_selector.py --start 2020-01-02 --end 2024-12-31 --switch-score-edge 0.20 --output-prefix results/group_a_plus_bayesian_selector_2020_2024_edge020_20260619
```

### 2025~2026 結果

| variant | final | Sharpe | Sortino | MDD | STARR 5% | rule usage |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| A20.7 | 2333356.2334819334 | 2.3399277909169327 | 2.4896386567803552 | -0.2527534866588963 | 0.06905139898243232 | A20.7 only |
| Bayesian selector `edge=0.00` | 2139180 左右 | 2.255 | 2.352 | -0.2528 | 0.0659 | A20.7 247 days / MA20 105 days |
| Bayesian selector `edge=0.10` | 2212377 左右 | 2.290 | 2.417 | -0.2528 | 0.0676 | A20.7 301 days / MA20 51 days |
| Bayesian selector `edge=0.20` | 2333356.2334819334 | 2.3399277909169327 | 2.4896386567803552 | -0.2527534866588963 | 0.06905139898243232 | A20.7 352 days |

### 2020~2024 / 2020~2026 檢查

| window | variant | final | Sharpe | Sortino | MDD | STARR 5% | rule usage |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 2020~2024 | A20.7 | 2343193.374873824 | 0.870 | 0.827 | -0.3776 | 0.0235 | A20.7 |
| 2020~2024 | Bayesian selector `edge=0.20` | 2196181 左右 | 0.884 | 0.843 | -0.3344 | 0.0240 | A20.7 1046 days / MA20 169 days |
| 2020~2026 | A20.7 | 5364941 左右 | 1.220 | 1.192 | -0.3776 | 0.0337 | A20.7 |
| 2020~2026 | Bayesian selector `edge=0.20` | 5055823 左右 | 1.264 | 1.249 | -0.3344 | 0.0352 | A20.7 1333 days / MA20 234 days |

### 判斷

- Bayesian-style selector 可改善 Sharpe、Sortino、MDD、STARR，但會犧牲 final return。
- 2025~2026 最新區間只要允許切到 MA20，就會拖累 A20.7；`edge=0.20` 以上等同完全不切換，因此沒有新增 alpha。
- 因此本次 PDF 方向 1 已落地為 research-only 工具，但不建議升級正式 latest strategy。
- 正式 latest strategy 仍維持 A20.7：`switch_risk_ma75_dd11_total6_hold5_eg0175_xg020`。

## 2026-06-19 PDF 方向 2、3：成本型 no-trade 與 EWMA 波動 selector

使用者要求「再試 2,3」。本次新增 research-only 腳本：

- `backtest_group_a_plus_pdf_directions_2_3.py`

### 方向 2：Transaction-cost-aware no-trade / turnover cap

目的：依 `Nonlinear Optimization with Financial Applications.pdf` 的 transaction cost / rebalancing 概念，測試 A20.7 在 regime switch 時加入：

- 交易成本：commission `0.1425%`、ETF sell tax `0.1%`、slippage `0.05%`
- no-trade band：若目標權重差異低於 band 就不交易
- turnover cap：若需要交易的權重差異過大，只做部分調整

指令：

```bash
python3 -m py_compile backtest_group_a_plus_pdf_directions_2_3.py
python3 backtest_group_a_plus_pdf_directions_2_3.py --start 2025-01-02 --end 2026-06-18 --output-prefix results/group_a_plus_pdf_directions_2_3_2025_2026_20260619
python3 backtest_group_a_plus_pdf_directions_2_3.py --start 2020-01-02 --end 2024-12-31 --output-prefix results/group_a_plus_pdf_directions_2_3_2020_2024_20260619
python3 backtest_group_a_plus_pdf_directions_2_3.py --start 2020-01-02 --end 2026-06-18 --output-prefix results/group_a_plus_pdf_directions_2_3_2020_2026_20260619
```

結果：

| window | variant | final | Sharpe | MDD | total cost | trades | 判斷 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 2025~2026 | A20.7 no cost | 2333356 | 2.340 | -25.28% | 0 | 2 | 正式比較基準 |
| 2025~2026 | best cost-aware `band00_capnone` | 2331056 | 約 2.338 | 約 -25.28% | 959 | 2 | 成本後略低於 A20.7 |
| 2020~2024 | A20.7 no cost | 2343193 | 0.870 | -37.76% | 0 | 2 | 高 final、風險較高 |
| 2020~2024 | best cost-aware `band00_cap10` | 2343441 | 約 0.870 | 約 -37.76% | 422 | 2 | 幾乎等價，不是穩健改善 |
| 2020~2026 | A20.7 no cost | 5364941 | 1.220 | -37.76% | 0 | 4 | 基準 |
| 2020~2026 | best final `band20_cap10` | 5677452 | 1.215 | -37.01% | 560 | 1 | 少防守/部分交易造成 final 高，但 Sharpe 未改善 |

判斷：

- A20.7 本身 switch 次數很少，2025~2026 只有 2 次，因此交易成本不是主要問題。
- no-trade band / turnover cap 在長區間提高 final 的情況，主要來自跳過或弱化防守切換，等於承擔更多進攻曝險，不是穩健的成本優化。
- 方向 2 不升級正式策略；保留為 execution research。

### 方向 3：EWMA volatility-regime selector

目的：依 `Quantitative Finance for Physicists - An Introduction` 的 conditional heteroskedasticity / volatility clustering 概念，測試：

- 用 0050 EWMA volatility 相對 126 日中位數的比率判斷高波動 regime。
- 高波動時改用 `ma20_dd7_hold5` 的短週期防守 regime。
- 其他時間維持 A20.7。

結果：

| window | variant | final | Sharpe | Sortino | MDD | MA20 days | 判斷 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 2025~2026 | A20.7 | 2333356 | 2.340 | 2.490 | -25.28% | 0 | 正式基準 |
| 2025~2026 | best EWMA `ewma120_neg5d` | 2171687 | 2.294 | 2.408 | -25.28% | 45 | 明顯拖累 final/Sharpe |
| 2020~2024 | A20.7 | 2343193 | 0.870 | 0.827 | -37.76% | 0 | 高 final、風險較高 |
| 2020~2024 | best EWMA `ewma120_neg5d` | 2237644 | 0.927 | 0.896 | -34.31% | 111 | 風險改善但 final 降低 |
| 2020~2026 | A20.7 | 5364941 | 1.220 | 1.192 | -37.76% | 0 | 基準 |
| 2020~2026 | best EWMA `ewma120_neg5d` | 4799025 | 1.274 | 1.263 | -34.31% | 160 | 風險改善但 final 明顯降低 |

判斷：

- EWMA selector 的效果和 Bayesian selector 類似：風險指標改善，但以犧牲 final return 換來。
- 2025~2026 最新區間不支持加入 EWMA selector；只要切到 MA20，就拖累 A20.7。
- 方向 3 不升級正式策略；可作為風險報表或保守版 portfolio 的研究工具。

### 總結

- 方向 2、3 都已落地並回測。
- 兩者都沒有通過「不傷害 2025~2026 最新 A20.7」的要求。
- 正式 latest strategy 仍維持 A20.7：`switch_risk_ma75_dd11_total6_hold5_eg0175_xg020`。

## 2026-06-19 PDF 下一批方向 1：Financial Econometrics / GARCH proxy

使用者要求試下一批第 1 個 PDF 方向：`Financial Econometrics Modeling Derivatives - Pricing.pdf`。本次依 conditional heteroskedasticity / GARCH 概念新增 research-only 腳本：

- `backtest_group_a_plus_financial_econometrics.py`

環境沒有 `arch` / `statsmodels`，因此本次不安裝套件，改用固定參數 GARCH(1,1)-style recursion 作為 volatility-state proxy：

- `sigma_t^2 = omega + alpha * r_{t-1}^2 + beta * sigma_{t-1}^2`
- `alpha=0.08`
- `beta=0.90`
- volatility state 使用 GARCH proxy vol ratio 與 rolling percentile

### 測試方法

1. **GARCH selector**
   - 預設使用 A20.7。
   - GARCH proxy 顯示高波動時，改用 `ma20_dd7_hold5` 的短週期防守 regime。

2. **GARCH guard**
   - 預設沿用 A20.7。
   - 若 GARCH 高波動、5 日報酬為負、且 total risk score 達門檻，直接強制進 `group_a_plus_defensive`。
   - 使用 5 日最短持有與 GARCH ratio 退出條件。

### 指令

```bash
python3 -m py_compile backtest_group_a_plus_financial_econometrics.py
python3 backtest_group_a_plus_financial_econometrics.py --start 2025-01-02 --end 2026-06-18 --output-prefix results/group_a_plus_financial_econometrics_garch_2025_2026_20260619
python3 backtest_group_a_plus_financial_econometrics.py --start 2020-01-02 --end 2024-12-31 --output-prefix results/group_a_plus_financial_econometrics_garch_2020_2024_20260619
python3 backtest_group_a_plus_financial_econometrics.py --start 2020-01-02 --end 2026-06-18 --output-prefix results/group_a_plus_financial_econometrics_garch_2020_2026_20260619
```

### 2025~2026 結果

| variant | final | Sharpe | Sortino | MDD | STARR 5% | 補充 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| A20.7 | 2333356 | 2.340 | 2.490 | -25.28% | 0.0691 | 正式基準 |
| MA20 | 2153677 | 2.268 | 2.366 | -25.58% | 0.0672 | 短週期防守 |
| best GARCH selector `r130_p90_neg5d` | 2156972 | 2.270 | - | -25.28% | - | MA20 34 days |
| best GARCH guard `r105_p70_risk0` | 2119476 | 2.313 | 2.429 | -25.28% | 0.0697 | events 7 |

檢查所有 GARCH selector / guard 候選後，沒有任何候選同時滿足：

- final >= A20.7 的 98%
- Sharpe >= A20.7
- MDD 不差於 A20.7

### 2020~2024 / 2020~2026 結果

| window | variant | final | Sharpe | Sortino | MDD | 補充 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 2020~2024 | A20.7 | 2343193 | 0.870 | 0.827 | -37.76% | 基準 |
| 2020~2024 | best GARCH selector `r105_p70_neg5d` | 2210040 | 0.920 | - | -33.86% | MA20 204 days |
| 2020~2024 | best GARCH guard `r105_p70_risk4` | 2133252 | 0.900 | - | -31.94% | events 14 |
| 2020~2026 | A20.7 | 5364941 | 1.220 | 1.192 | -37.76% | 基準 |
| 2020~2026 | best GARCH selector `r105_p70_neg5d` | 4667035 | 1.259 | - | -33.99% | MA20 258 days |
| 2020~2026 | best GARCH guard `r105_p70_risk4` | 4443140 | 1.255 | - | -31.94% | events 23 |

### 判斷

- GARCH proxy 和 EWMA selector 的結論一致：能改善長區間 Sharpe/MDD，但代價是 final return 明顯下降。
- 2025~2026 最新區間明確不支持加入 GARCH selector/guard；只要引入短週期防守或額外 GARCH guard，就拖累 A20.7。
- `Financial Econometrics Modeling Derivatives - Pricing.pdf` 的 GARCH/conditional volatility 概念已落地測試，但不升級正式 latest strategy。
- 正式 latest strategy 仍維持 A20.7：`switch_risk_ma75_dd11_total6_hold5_eg0175_xg020`。

## 2026-06-19 PDF 下一批方向 2：Copula tail dependence

使用者要求「再試2」，本次依下一批第 2 個 PDF 方向 `Copula Methods in Finance.pdf`，新增 research-only 腳本：

- `backtest_group_a_plus_copula_tail.py`

### 方法

不擬合完整 parametric copula，改用可重現的 rolling empirical copula proxy：

- 對 `0050.TW`、`00631L.TW`、`00632R.TW`、`00679B.TWO` 日報酬做 rolling empirical CDF rank。
- 偵測下尾共動：
  - `0050` 與 `00631L` 同時進下尾
  - equity sleeve 多標的同時進下尾
  - `00632R` 在 equity 下跌時沒有提供反向保護
  - `00679B` 在 equity 下跌時也同步不利
- 產生 `joint_tail_score`，再測兩種用法：
  - Copula selector：tail score 高時改用 `ma20_dd7_hold5`
  - Copula guard：tail score 高時直接強制進 `group_a_plus_defensive`

### 指令

```bash
python3 -m py_compile backtest_group_a_plus_copula_tail.py
python3 backtest_group_a_plus_copula_tail.py --start 2025-01-02 --end 2026-06-18 --output-prefix results/group_a_plus_copula_tail_2025_2026_20260619
python3 backtest_group_a_plus_copula_tail.py --start 2020-01-02 --end 2024-12-31 --output-prefix results/group_a_plus_copula_tail_2020_2024_20260619
python3 backtest_group_a_plus_copula_tail.py --start 2020-01-02 --end 2026-06-18 --output-prefix results/group_a_plus_copula_tail_2020_2026_20260619
```

### 結果

| window | variant | final | Sharpe | MDD | 補充 |
| --- | --- | ---: | ---: | ---: | --- |
| 2025~2026 | A20.7 | 2333356 | 2.340 | -25.28% | 正式基準 |
| 2025~2026 | best Copula selector `w126_q05_s2_neg5d` | 2188870 | 2.292 | -25.28% | MA20 13 days |
| 2025~2026 | target `w60_q05_s3_neg5d` | 2180983 | 2.279 | -25.28% | MA20 5 days |
| 2025~2026 | best Copula guard `w126_q10_s2` | 2147536 | 2.323 | -25.28% | events 18 |
| 2020~2024 | A20.7 | 2343193 | 0.870 | -37.76% | 基準 |
| 2020~2024 | best Copula selector `w60_q05_s3_neg5d` | 2283443 | 0.935 | -32.96% | MA20 19 days |
| 2020~2024 | best Copula guard `w126_q05_s2` | 2154658 | 0.907 | -33.26% | events 58 |
| 2020~2026 | A20.7 | 5364941 | 1.220 | -37.76% | 基準 |
| 2020~2026 | best Copula selector `w60_q05_s3_neg5d` | 4915704 | 1.276 | -32.96% | MA20 25 days |
| 2020~2026 | best Copula guard `w126_q05_s2` | 4543159 | 1.259 | -33.26% | events 74 |

### 判斷

- Copula tail dependence 比 EWMA/GARCH 更精準一點：`w60_q05_s3_neg5d` 只在少數共跌日切到 MA20，長區間 Sharpe 與 MDD 改善明顯，final 犧牲小於 EWMA/GARCH。
- 但 2025~2026 最新區間仍明顯拖累 A20.7；最佳 selector final 只有約 `2.189M`，低於 A20.7 的 `2.333M`。
- 檢查所有 Copula selector / guard 候選後，沒有任何候選同時滿足：
  - final >= A20.7 的 98%
  - Sharpe >= A20.7
  - MDD 不差於 A20.7
- 因此 Copula tail dependence 可保留為「保守版風險 overlay」研究候選，但不升級正式 latest strategy。
- 正式 latest strategy 仍維持 A20.7：`switch_risk_ma75_dd11_total6_hold5_eg0175_xg020`。

## 2026-06-19 Copula 方法微調檢查

使用者詢問 Copula 方法是否可再微調改善。本次新增 focused refine 腳本：

- `refine_group_a_plus_copula_tail.py`

### 微調方向

原始 Copula selector 是「tail stress 時切換到 MA20 規則」，這可能同時增加防守，也可能在 A20.7 原本防守時被 MA20 狀態覆蓋。因此本次補測：

- 更嚴格 tail 分位數：`q=0.03/0.05`
- 更嚴格 tail score：`score=3/4`
- tail intensity 門檻：`0/0.25/0.50/0.70`
- 5 日跌幅門檻：`-2%/-3%/-4%/-6%`
- 僅在 A20.7 仍為 golden 時觸發
- add-on 模式：只新增防守，不移除 A20.7 原本防守
- cooldown：`0/10` 日

完整大網格因保存所有 curve 欄位造成 pandas fragmentation warning，已中止；改跑 tight grid：

```bash
python3 -m py_compile refine_group_a_plus_copula_tail.py
python3 refine_group_a_plus_copula_tail.py --start 2025-01-02 --end 2026-06-18 --windows 40,60,90 --tail-qs 0.03,0.05 --min-scores 3,4 --min-intensities 0.0,0.25,0.50,0.70 --max-return-5d=-0.02,-0.03,-0.04,-0.06 --cooldown-days 0,10 --output-prefix results/group_a_plus_copula_tail_refine_2025_2026_tight_20260619
```

### 結果

| 條件 | 結果 |
| --- | --- |
| tight grid candidates | 1152 |
| passing candidates | 768 |
| passing 且有實際觸發 | 0 |
| best passing | `selector_w40_q03_s3_i25_r02_golden` |
| best passing final / Sharpe / MDD | 完全等同 A20.7 |
| best passing trigger days | 0 |
| 有觸發候選中最高 final | 約 2214352 |
| A20.7 final | 2333356 |

### 判斷

- 只要 Copula overlay 在 2025~2026 實際觸發，就會拖累 A20.7。
- 所有通過「final >= A20.7 98%、Sharpe >= A20.7、MDD 不差」的候選，都是 0 觸發，等於沒有策略變化。
- 因此 Copula 方法不能靠門檻微調升級成正式 latest strategy。
- Copula `w60_q05_s3_neg5d` 仍可保留為保守版研究候選，因為它在 2020~2026 改善 Sharpe/MDD，但不適合替代最新 A20.7。
- 正式 latest strategy 仍維持 A20.7：`switch_risk_ma75_dd11_total6_hold5_eg0175_xg020`。

## 2026-06-19 PDF 下一批方向 3：Monte Carlo / bootstrap stress

使用者要求看下一個 PDF，本次依 `Monte-Carlo Methods In Finance-Jackel.pdf` 的 simulation / resampling 思路新增：

- `monte_carlo_group_a_plus_stress.py`

### 方法

不是新增策略規則，而是用 block bootstrap 檢查路徑穩健性：

- 使用 2020-01-02 ~ 2026-06-18 的實際策略日報酬。
- 同步抽樣各策略同一天報酬，保留策略之間的相對比較。
- block size：20 trading days。
- horizon：252 trading days。
- simulations：5000。
- 比較：
  - `golden1`
  - `group_a_plus_defensive`
  - A20.7
  - `ma20`
  - Copula 保守版 `copula_w60_q05_s3_neg5d`

### 指令

```bash
python3 -m py_compile monte_carlo_group_a_plus_stress.py
python3 monte_carlo_group_a_plus_stress.py --start 2020-01-02 --end 2026-06-18 --simulations 5000 --horizon 252 --block-size 20 --output-prefix results/group_a_plus_monte_carlo_stress_2020_2026_20260619
```

### Monte Carlo 結果

| strategy | hist final | MC median return | MC p05 return | MC p05 MDD | prob negative |
| --- | ---: | ---: | ---: | ---: | ---: |
| `golden1` | 5937391 | 33.82% | -14.32% | -36.13% | 14.26% |
| `group_a_plus_defensive` | 4862684 | 29.41% | -12.71% | -32.25% | 13.88% |
| A20.7 | 5364941 | 31.61% | -13.96% | -33.12% | 13.52% |
| `ma20` | 4601374 | 28.42% | -11.29% | -29.17% | 12.82% |
| Copula `w60_q05_s3_neg5d` | 4915704 | 29.49% | -11.11% | -29.67% | 12.24% |

### Pairwise win rate

| comparison | win rate |
| --- | ---: |
| A20.7 > Golden1 | 28.74% |
| Golden1 > A20.7 | 71.26% |
| A20.7 > GroupA+ defensive | 69.14% |
| A20.7 > MA20 | 72.48% |
| A20.7 > Copula conservative | 68.84% |
| Copula conservative > A20.7 | 31.16% |
| Copula conservative > Golden1 | 26.98% |

### 判斷

- Monte Carlo stress 沒有產生可升級的新規則，但補充了路徑穩健性判斷。
- Golden1 的 median return 最高，但 p05 return / p05 MDD 較差，代表它仍是更進攻的路徑。
- Copula conservative 與 MA20 的 tail risk 最好，負報酬機率與 p05 MDD 較低，但長期報酬與勝率輸 A20.7。
- A20.7 不是最高報酬路徑，也不是最低風險路徑；它是收益/風險較均衡的正式 latest。
- 正式 latest strategy 仍維持 A20.7：`switch_risk_ma75_dd11_total6_hold5_eg0175_xg020`。

## 2026-06-19 PDF Chapter 8：Scaling / power-law tail proxy

依使用者補充的 `Quantitative Finance for Physicists` 第 8 章，新增：

- `backtest_group_a_plus_scaling_tail.py`

### 方法

把第 8 章的 scaling / power-law tail 概念轉成 deterministic screening proxy：

- 使用 0050 的 1d / 2d / 4d returns。
- 用 rolling Hill-style left-tail alpha 近似冪律尾部厚度。
- 用 1d / 2d / 4d rolling VaR breach 建立 multi-scale breach score。
- 用 20 日 breach cluster 判斷尾部壓力是否集中。
- 測兩種 overlay：
  - selector：壓力日把 A20.7 regime 替換成 MA20 regime。
  - guard：壓力日強制進 `group_a_plus_defensive`，至少持有 5 日。

### 指令

```bash
python3 -m py_compile backtest_group_a_plus_scaling_tail.py
python3 backtest_group_a_plus_scaling_tail.py --start 2025-01-02 --end 2026-06-18 --output-prefix results/group_a_plus_scaling_tail_2025_2026_20260619
python3 backtest_group_a_plus_scaling_tail.py --start 2020-01-02 --end 2024-12-31 --windows 378 --tail-counts 8,12,16 --quantiles 0.03,0.05 --min-scores 2 --max-alphas 2.2,2.6,3.0,3.5 --min-clusters 1,2,3 --output-prefix results/group_a_plus_scaling_tail_2020_2024_focused_20260619
python3 backtest_group_a_plus_scaling_tail.py --start 2020-01-02 --end 2026-06-18 --windows 378 --tail-counts 8,12,16 --quantiles 0.03,0.05 --min-scores 2 --max-alphas 2.2,2.6,3.0,3.5 --min-clusters 1,2,3 --output-prefix results/group_a_plus_scaling_tail_2020_2026_focused_20260619
```

### 結果

| window | A20.7 final / Sharpe / MDD | best scaling final / Sharpe / MDD | strict pass with triggers |
| --- | ---: | ---: | ---: |
| 2025-01-02 ~ 2026-06-18 | 2333356 / 2.340 / -25.28% | 2343317 / 2.343 / -25.58% | 0 |
| 2020-01-02 ~ 2024-12-31 | 2343193 / 0.870 / -37.76% | 2345347 / 0.945 / -33.76% | 10 |
| 2020-01-02 ~ 2026-06-18 | 5364941 / 1.220 / -37.76% | 5561217 / 1.284 / -37.76% | 10 |

### 判斷

- 第 8 章 scaling tail proxy 是目前 PDF 方向中較有參考價值的一個。
- 它在 2020~2024 與 2020~2026 可以改善 Sharpe，且全期間 final 從 5364941 提高到 5561217。
- 但最新 2025~2026 strict pass = 0；最佳候選雖然 final 與 Sharpe 略高，但 MDD 從 -25.28% 變 -25.58%，未通過「不傷害最新 A20.7」門檻。
- 因此暫不覆蓋 latest pointer。可列為 A20.8 觀察候選或風險研究候選。
- 正式 latest strategy 仍維持 A20.7：`switch_risk_ma75_dd11_total6_hold5_eg0175_xg020`。

## 2026-06-19 PDF Chapter 12：Agent-Based observable agents

依使用者補充的 `Quantitative Finance for Physicists` 第 12 章，新增：

- `backtest_group_a_plus_abm_agents.py`

### 方法

把代理人基模型轉成可觀測 proxy，而不是模擬不可觀測的真實交易者數量：

- fundamentalist agent：用 total risk score、外資/投信、外資持股變化近似基本面/籌碼交易者。
- momentum agent：用 20 日報酬與 MA gap 近似 chartist / trend follower。
- contrarian agent：用 drawdown、20 日過熱報酬、波動率比值近似反向操作者。
- 每個代理人每天投 `golden1` 或 `group_a_plus_defensive`。
- 用過去 rolling payoff 作為 fitness，經 softmax 形成 agent weights。
- aggregate demand 達門檻時 override A20.7 regime。

### 指令

完整 grid 太慢且過度搜尋，改用 focused grid：

```bash
python3 -m py_compile backtest_group_a_plus_abm_agents.py
python3 backtest_group_a_plus_abm_agents.py --start 2025-01-02 --end 2026-06-18 --fitness-windows 40,60 --betas 3.0,6.0 --demand-thresholds 0.35,0.50 --risk-thresholds 6 --low-risk-thresholds 1,2 --momentum-days 20 --trend-returns 0.025 --hot-returns 0.08,0.12 --buy-dip-drawdowns=-0.06,-0.10 --min-hold-days 0,5 --output-prefix results/group_a_plus_abm_agents_2025_2026_focused_20260619
python3 backtest_group_a_plus_abm_agents.py --start 2020-01-02 --end 2024-12-31 --fitness-windows 40,60 --betas 3.0,6.0 --demand-thresholds 0.35,0.50 --risk-thresholds 6 --low-risk-thresholds 1,2 --momentum-days 20 --trend-returns 0.025 --hot-returns 0.08,0.12 --buy-dip-drawdowns=-0.06,-0.10 --min-hold-days 0,5 --output-prefix results/group_a_plus_abm_agents_2020_2024_focused_20260619
python3 backtest_group_a_plus_abm_agents.py --start 2020-01-02 --end 2026-06-18 --fitness-windows 40,60 --betas 3.0,6.0 --demand-thresholds 0.35,0.50 --risk-thresholds 6 --low-risk-thresholds 1,2 --momentum-days 20 --trend-returns 0.025 --hot-returns 0.08,0.12 --buy-dip-drawdowns=-0.06,-0.10 --min-hold-days 0,5 --output-prefix results/group_a_plus_abm_agents_2020_2026_focused_20260619
```

### 結果

| window | A20.7 final / Sharpe / MDD | best ABM final / Sharpe / MDD | strict pass with overrides |
| --- | ---: | ---: | ---: |
| 2025-01-02 ~ 2026-06-18 | 2333356 / 2.340 / -25.28% | 2328382 / 2.332 / -25.28% | 0 |
| 2020-01-02 ~ 2024-12-31 | 2343193 / 0.870 / -37.76% | 2119982 / 0.888 / -32.34% | 0 |
| 2020-01-02 ~ 2026-06-18 | 5364941 / 1.220 / -37.76% | 4567651 / 1.251 / -33.39% | 0 |

### 判斷

- ABM observable agents 有降低風險效果，但代價是 final 明顯下降。
- 2020~2026 最佳 ABM Sharpe 從 1.220 提高到 1.251，MDD 從 -37.76% 改善到 -33.39%，但 final 從 5364941 降到 4567651。
- 2025~2026 最新段 final / Sharpe 都低於 A20.7，strict pass = 0。
- 因此第 12 章 ABM 方法暫不適合加入最新 groupA+；只適合作為保守風險 overlay 的研究記錄。
- 正式 latest strategy 仍維持 A20.7：`switch_risk_ma75_dd11_total6_hold5_eg0175_xg020`。

## 2026-06-19 Current handoff conclusion

### 正式 latest

- 正式 latest pointer 不變：
  - `report/group_a_plus/latest/switch_backtest.json`
- 正式 latest strategy：
  - `switch_risk_ma75_dd11_total6_hold5_eg0175_xg020`
- 2025-01-02 ~ 2026-06-18 正式指標：
  - final：2333356
  - Sharpe：2.340
  - Sortino：2.490
  - MDD：-25.28%

### PDF 方向總結

| PDF / chapter direction | script | conclusion |
| --- | --- | --- |
| Bayesian selector | `backtest_group_a_plus_bayesian_selector.py` | 降風險但報酬下降，不升級 |
| Nonlinear optimization / no-trade / turnover cap | `backtest_group_a_plus_pdf_directions_2_3.py` | 成本與換手改善有限，不升級 |
| EWMA / time-series vol selector | `backtest_group_a_plus_pdf_directions_2_3.py` | 風險改善但 2025~2026 輸 A20.7，不升級 |
| Financial Econometrics / GARCH proxy | `backtest_group_a_plus_financial_econometrics.py` | 最新段 final / Sharpe 輸 A20.7，不升級 |
| Copula tail dependence | `backtest_group_a_plus_copula_tail.py` | 長期保守化有效，但最新段拖累，不升級 |
| Copula tight refine | `refine_group_a_plus_copula_tail.py` | 最新段有觸發即傷害 A20.7，不升級 |
| Monte Carlo stress | `monte_carlo_group_a_plus_stress.py` | 不是新規則；確認 A20.7 是收益/風險折衷 |
| Chapter 8 scaling / power-law tail | `backtest_group_a_plus_scaling_tail.py` | 最值得觀察；長期改善，但最新段 strict pass = 0 |
| Chapter 12 ABM agents | `backtest_group_a_plus_abm_agents.py` | 可降風險但報酬犧牲過大，不升級 |

### 可保留觀察候選

- Chapter 8 scaling-tail proxy 可列為 A20.8 觀察候選：
  - 2020~2026 best focused result：final 5561217、Sharpe 1.284、MDD -37.76%。
  - 但 2025~2026 best：final 2343317、Sharpe 2.343、MDD -25.58%，MDD 比 A20.7 的 -25.28% 差，因此不能直接替換 latest。
- Copula conservative / MA20 類型可作為保守風險 overlay 參考：
  - tail risk 較低，但長期 final 與 latest 勝率輸 A20.7。

### 接手建議

- 不要覆蓋 `report/group_a_plus/latest/switch_backtest.json`，除非新候選同時通過：
  - 2025~2026 final 不低於 A20.7。
  - 2025~2026 Sharpe 不低於 A20.7。
  - 2025~2026 MDD 不差於 A20.7。
  - 有實際 trigger / override，不是 0 觸發等同原策略。
- 下一步若要繼續微調，優先從 Chapter 8 scaling-tail candidate 下手，而不是 ABM 或 Copula。

## 2026-06-19 FinceptTerminal reference trial：1~5

使用者要求把 `C:\Users\isaac\Downloads\FinceptTerminal-main\FinceptTerminal-main` 中可參考的 5 個方向都試一次。本次沒有搬大型 Qt/C++ terminal，只抽取適合目前 Python/groupA+ 流程的概念。

### 1. JSON output standardization

新增：

- `tw_output_standard.py`

用途：

- 統一輸出 `success / data / metadata / error`。
- 後續 runner / registry / overlay 統一可讀 JSON，避免只靠 stdout。

### 2. Data registry / topic registry

新增：

- `group_a_plus_data_registry.py`

指令：

```bash
python3 group_a_plus_data_registry.py --output results/group_a_plus_data_registry_20260619.json
```

結果：

- 產出本地 DuckDB tables、日期覆蓋、欄位、ticker/id values、news files、topic registry。
- 類似 Fincept DataHub 的靜態版，用來讓接手者知道哪些資料源已可用。

### 3. Standardized A20.7 runner

新增：

- `group_a_plus_runner.py`

指令：

```bash
python3 group_a_plus_runner.py --start 2025-01-02 --end 2026-06-18 --output results/group_a_plus_runner_a207_2025_2026_20260619.json --frame-output results/group_a_plus_runner_a207_2025_2026_20260619_frame.csv
```

結果：

- 以標準 JSON 重跑 A20.7。
- frame CSV 保留逐日 features / regime / portfolio value。
- 不覆蓋 latest pointer。

### 4. News anomaly overlay

新增：

- `backtest_group_a_plus_news_anomaly.py`

方法：

- 讀取本地 `news/ltn_mainstream_*.jsonl`。
- 用市場詞與 risk-off 詞建立 daily news risk count。
- rolling 60 日 z-score 偵測新聞異常。
- 測 selector / guard overlay：
  - selector：news risk 觸發時用 MA20 regime 替換 A20.7 regime。
  - guard：news risk 觸發時強制 defensive。

指令：

```bash
python3 backtest_group_a_plus_news_anomaly.py --start 2025-01-02 --end 2026-06-18 --output-prefix results/group_a_plus_news_anomaly_2025_2026_20260619
python3 backtest_group_a_plus_news_anomaly.py --start 2020-01-02 --end 2024-12-31 --output-prefix results/group_a_plus_news_anomaly_2020_2024_20260619
python3 backtest_group_a_plus_news_anomaly.py --start 2020-01-02 --end 2026-06-18 --output-prefix results/group_a_plus_news_anomaly_2020_2026_20260619
```

結果：

| window | A20.7 final / Sharpe / MDD | best news final / Sharpe / MDD | trigger / override days | effective strict pass |
| --- | ---: | ---: | ---: | ---: |
| 2025-01-02 ~ 2026-06-18 | 2333356 / 2.340 / -25.28% | 2221347 / 2.302 / -25.28% | 7 / 1 | 0 |
| 2020-01-02 ~ 2024-12-31 | 2343193 / 0.870 / -37.76% | 2156344 / 0.886 / -33.28% | 15 / 5 | 0 |
| 2020-01-02 ~ 2026-06-18 | 5364941 / 1.220 / -37.76% | 4635528 / 1.243 / -33.58% | 116 / 28 | 0 |

判斷：

- News anomaly 有保守降風險效果，但報酬犧牲太大。
- 最新段 final / Sharpe 都輸 A20.7。
- 不加入 latest；只保留為新聞風險監控研究。

### 5. Derivative/options overlay

新增：

- `backtest_group_a_plus_derivative_options_overlay.py`

方法：

- 參考 Fincept options analytics 的「衍生品風險拆解」概念，但使用本地可觀測資料：
  - TXO foreign put-call net OI
  - TXO put-call net OI 5 日變化
  - dealer TXO 5 日成交量 z-score
  - existing derivative_score
- 建立 `option_stress_score`，測 selector / guard overlay。

指令：

```bash
python3 backtest_group_a_plus_derivative_options_overlay.py --start 2025-01-02 --end 2026-06-18 --output-prefix results/group_a_plus_derivative_options_overlay_2025_2026_20260619
python3 backtest_group_a_plus_derivative_options_overlay.py --start 2020-01-02 --end 2024-12-31 --output-prefix results/group_a_plus_derivative_options_overlay_2020_2024_20260619
python3 backtest_group_a_plus_derivative_options_overlay.py --start 2020-01-02 --end 2026-06-18 --output-prefix results/group_a_plus_derivative_options_overlay_2020_2026_20260619
```

結果：

| window | A20.7 final / Sharpe / MDD | best options final / Sharpe / MDD | trigger / override days | effective strict pass |
| --- | ---: | ---: | ---: | ---: |
| 2025-01-02 ~ 2026-06-18 | 2333356 / 2.340 / -25.28% | 2333356 / 2.340 / -25.28% | 2 / 0 | 0 |
| 2020-01-02 ~ 2024-12-31 | 2343193 / 0.870 / -37.76% | 2343193 / 0.870 / -37.76% | 0 / 0 | 0 |
| 2020-01-02 ~ 2026-06-18 | 5364941 / 1.220 / -37.76% | 5364941 / 1.220 / -37.76% | 2 / 0 | 0 |

判斷：

- options overlay 的最佳結果等同 A20.7。
- 少數 trigger 沒有造成實際 regime override，代表現有 A20.7 的 total risk / derivative features 已經吸收主要資訊。
- 不加入 latest。

### FinceptTerminal trial conclusion

- 1~3 是有用的工程基礎設施，已落地：
  - `tw_output_standard.py`
  - `group_a_plus_data_registry.py`
  - `group_a_plus_runner.py`
- 4~5 是可測策略 overlay，但都沒有通過 effective strict pass：
  - news：保守但降報酬。
  - options：幾乎等同 A20.7，沒有新增有效 override。
- 正式 latest strategy 仍維持 A20.7：`switch_risk_ma75_dd11_total6_hold5_eg0175_xg020`。
- 若後續要繼續從 FinceptTerminal 借概念，優先方向不是再調 news/options overlay，而是把 1~3 擴成完整 pipeline governance：標準輸出、資料 coverage registry、runner catalog、結果比較器。

## 2026-06-19 Pipeline governance continuation

依使用者要求「OK, 繼續」，把前述 1~3 擴成可用治理工具。

### 新增工具

- `group_a_plus_runner_catalog.py`
- `group_a_plus_data_coverage_check.py`
- `compare_group_a_plus_results.py`

### Runner catalog

指令：

```bash
python3 group_a_plus_runner_catalog.py --start 2025-01-02 --end 2026-06-18 --output results/group_a_plus_runner_catalog_20260619.json
```

用途：

- 記錄可跑 runner、命令模板、輸出型態。
- 目前 catalog 包含：
  - A20.7 baseline runner
  - news anomaly overlay
  - derivative/options overlay
  - scaling-tail research candidate
- 明確寫入 formal upgrade guardrails：
  - final 不低於 baseline
  - Sharpe 不低於 baseline
  - MDD 不差於 baseline
  - effective override days > 0

### Data coverage check

指令：

```bash
python3 group_a_plus_data_coverage_check.py --start 2025-01-02 --end 2026-06-18 --output results/group_a_plus_data_coverage_2025_2026_20260619.json
python3 group_a_plus_data_coverage_check.py --start 2020-01-02 --end 2026-06-18 --output results/group_a_plus_data_coverage_2020_2026_20260619.json
```

結果：

| window | status | note |
| --- | --- | --- |
| 2025-01-02 ~ 2026-06-18 | warn | OHLCV 無硬失敗；部分可選籌碼資料只到 2026-06-17，TDCC 到 2026-06-12 |
| 2020-01-02 ~ 2026-06-18 | warn | 長期可選籌碼/衍生品資料有起訖不齊；runner 會 zero-fill optional gaps |

判斷：

- OHLCV 是 hard requirement；目前沒有 hard fail。
- chip/news/derivative 是 warning，因既有 runner 對 optional features zero-fill。
- 這個工具可在每日 refresh 後先跑，避免用缺資料誤判策略。

### Result comparator

指令：

```bash
python3 compare_group_a_plus_results.py --baseline results/group_a_plus_runner_a207_2025_2026_20260619.json --candidates results/group_a_plus_news_anomaly_2025_2026_20260619.json results/group_a_plus_derivative_options_overlay_2025_2026_20260619.json results/group_a_plus_scaling_tail_2025_2026_20260619.json results/group_a_plus_abm_agents_2025_2026_focused_20260619.json --output results/group_a_plus_compare_2025_2026_20260619.json
python3 compare_group_a_plus_results.py --baseline results/group_a_plus_runner_a207_2020_2026_20260619.json --candidates results/group_a_plus_news_anomaly_2020_2026_20260619.json results/group_a_plus_derivative_options_overlay_2020_2026_20260619.json results/group_a_plus_scaling_tail_2020_2026_focused_20260619.json results/group_a_plus_abm_agents_2020_2026_focused_20260619.json --output results/group_a_plus_compare_2020_2026_20260619.json
```

結果：

| window | candidate rows | formal upgrade pass | research watchlist pass | conclusion |
| --- | ---: | ---: | ---: | --- |
| 2025-01-02 ~ 2026-06-18 | 3604 | 0 | 0 | 沒有候選可替代 latest |
| 2020-01-02 ~ 2026-06-18 | 904 | 4 | 10 | 長期有 scaling-tail guard 候選，但最新段未通過 |

2020~2026 comparator top formal passes：

| variant | final | Sharpe | MDD | override days |
| --- | ---: | ---: | ---: | ---: |
| `scaling_guard_w378_k8_q03_s2_a30_c3` | 5428232 | 1.278 | -37.35% | 22 |
| `scaling_guard_w378_k12_q03_s2_a30_c3` | 5428232 | 1.278 | -37.35% | 22 |
| `scaling_guard_w378_k12_q03_s2_a35_c3` | 5428232 | 1.278 | -37.35% | 22 |
| `scaling_guard_w378_k16_q03_s2_a35_c3` | 5428232 | 1.278 | -37.35% | 22 |

### Governance conclusion

- Governance 工具已能自動回答三件事：
  - local data coverage 是否足夠。
  - runner 命令與輸出在哪裡。
  - 候選是否真的通過 formal upgrade / watchlist guardrails。
- 目前最重要結論沒有變：
  - 2025~2026 comparator：formal upgrade pass = 0。
  - 因此正式 latest 不變，仍是 A20.7。
- Chapter 8 scaling-tail guard 在 2020~2026 有長期 formal pass，但 latest 2025~2026 不通過，所以只列為 A20.8 觀察候選。

## 2026-06-19 Architecture Refactor Step 1 - Data Layer

目標：

- 參考 Fincept Terminal 的 bounded context / DataHub 思路，先把 GroupA+ 的資料登錄與 coverage check 收進正式模組。
- 保留舊入口檔，避免破壞已存在命令與交接紀錄。

新增模組：

| path | purpose |
| --- | --- |
| `group_a_plus/__init__.py` | GroupA+ pipeline package |
| `group_a_plus/paths.py` | 共用 `PROJECT_ROOT` / `NEWS_DIR` |
| `group_a_plus/data/__init__.py` | data context package |
| `group_a_plus/data/registry.py` | local DB/news registry implementation |
| `group_a_plus/data/coverage.py` | local data coverage implementation |

相容入口：

| old path | now delegates to |
| --- | --- |
| `group_a_plus_data_registry.py` | `group_a_plus.data.registry.main()` |
| `group_a_plus_data_coverage_check.py` | `group_a_plus.data.coverage.main()` |

驗證指令：

```bash
python3 group_a_plus_data_registry.py --output results/group_a_plus_data_registry_arch_step1_wrapper_20260619.json
python3 -m group_a_plus.data.registry --output results/group_a_plus_data_registry_arch_step1_module_20260619.json
python3 group_a_plus_data_coverage_check.py --start 2025-01-02 --end 2026-06-18 --output results/group_a_plus_data_coverage_arch_step1_wrapper_20260619.json
python3 -m group_a_plus.data.coverage --start 2025-01-02 --end 2026-06-18 --output results/group_a_plus_data_coverage_arch_step1_module_20260619.json
```

驗證結果：

| check | result |
| --- | --- |
| registry wrapper | success, table_count 15, topics 16, news_files 90 |
| registry module | success, table_count 15, topics 16, news_files 90 |
| coverage wrapper | success, status warn, hard_failures 0, soft_gaps 5 |
| coverage module | success, status warn, hard_failures 0, soft_gaps 5 |

下一步建議：

- Step 2：把 `group_a_plus_runner.py` 收進 `group_a_plus/runners/`，並保留舊入口。
- Step 3：把 strategy catalog / comparator 收進 `group_a_plus/promotion/` 或 `group_a_plus/governance/`。

## 2026-06-19 Architecture Refactor Step 2 - A20.7 Runner

目標：

- 把正式 A20.7 baseline runner 收進 `group_a_plus/runners/`。
- 保留 `group_a_plus_runner.py` 舊入口，讓既有命令與 catalog 不會失效。
- 不改策略邏輯、不改 latest pointer。

新增模組：

| path | purpose |
| --- | --- |
| `group_a_plus/runners/__init__.py` | runner context package |
| `group_a_plus/runners/a207.py` | A20.7 baseline runner implementation |

相容入口：

| old path | now delegates to |
| --- | --- |
| `group_a_plus_runner.py` | `group_a_plus.runners.a207.main()` |

驗證指令：

```bash
python3 group_a_plus_runner.py --start 2025-01-02 --end 2026-06-18 --output results/group_a_plus_runner_a207_arch_step2_wrapper_20260619.json --frame-output results/group_a_plus_runner_a207_arch_step2_wrapper_20260619_frame.csv
python3 -m group_a_plus.runners.a207 --start 2025-01-02 --end 2026-06-18 --output results/group_a_plus_runner_a207_arch_step2_module_20260619.json --frame-output results/group_a_plus_runner_a207_arch_step2_module_20260619_frame.csv
python3 -m compileall group_a_plus group_a_plus_runner.py
```

驗證結果：

| check | final | Sharpe | Sortino | MDD | events | rows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| wrapper | 2333356.2334819334 | 2.3399277909169327 | 2.4896386567803552 | -0.2527534866588963 | 2 | 352 |
| module | 2333356.2334819334 | 2.3399277909169327 | 2.4896386567803552 | -0.2527534866588963 | 2 | 352 |

額外檢查：

- wrapper/module frame row count 都是 352。
- wrapper/module `portfolio_value` curve 完全一致。
- `compileall` 通過。

下一步建議：

- Step 3：搬 `group_a_plus_runner_catalog.py` 與 `compare_group_a_plus_results.py` 到 governance/promotion context。

## 2026-06-19 Architecture Refactor Step 3 - Governance

目標：

- 把 runner catalog 與結果比較器收進 governance context。
- 保留舊入口，讓既有 catalog/compare 命令不失效。
- 不改 formal upgrade / research watchlist guardrails。

新增模組：

| path | purpose |
| --- | --- |
| `group_a_plus/governance/__init__.py` | governance context package |
| `group_a_plus/governance/catalog.py` | runner catalog implementation |
| `group_a_plus/governance/compare.py` | candidate comparison / promotion gate implementation |

相容入口：

| old path | now delegates to |
| --- | --- |
| `group_a_plus_runner_catalog.py` | `group_a_plus.governance.catalog.main()` |
| `compare_group_a_plus_results.py` | `group_a_plus.governance.compare.main()` |

補充：

- catalog 仍保留舊 `python3 group_a_plus_runner.py ...` command template。
- catalog 新增 module command template：
  - `python3 -m group_a_plus.runners.a207 ...`
  - `python3 -m group_a_plus.governance.compare ...`

驗證指令：

```bash
python3 group_a_plus_runner_catalog.py --start 2025-01-02 --end 2026-06-18 --output results/group_a_plus_runner_catalog_arch_step3_wrapper_20260619.json
python3 -m group_a_plus.governance.catalog --start 2025-01-02 --end 2026-06-18 --output results/group_a_plus_runner_catalog_arch_step3_module_20260619.json
python3 compare_group_a_plus_results.py --baseline results/group_a_plus_runner_a207_arch_step2_wrapper_20260619.json --candidates results/group_a_plus_news_anomaly_2025_2026_20260619.json results/group_a_plus_derivative_options_overlay_2025_2026_20260619.json results/group_a_plus_scaling_tail_2025_2026_20260619.json results/group_a_plus_abm_agents_2025_2026_focused_20260619.json --output results/group_a_plus_compare_arch_step3_wrapper_20260619.json
python3 -m group_a_plus.governance.compare --baseline results/group_a_plus_runner_a207_arch_step2_wrapper_20260619.json --candidates results/group_a_plus_news_anomaly_2025_2026_20260619.json results/group_a_plus_derivative_options_overlay_2025_2026_20260619.json results/group_a_plus_scaling_tail_2025_2026_20260619.json results/group_a_plus_abm_agents_2025_2026_focused_20260619.json --output results/group_a_plus_compare_arch_step3_module_20260619.json
python3 -m compileall group_a_plus group_a_plus_runner_catalog.py compare_group_a_plus_results.py
```

驗證結果：

| check | result |
| --- | --- |
| catalog wrapper | success, baseline `a207_runner`, runners 4 |
| catalog module | success, baseline `a207_runner`, runners 4 |
| compare wrapper | success, candidate_files 4, rows 3604, formal 0, watchlist 0 |
| compare module | success, candidate_files 4, rows 3604, formal 0, watchlist 0 |

compare top candidate 仍是：

| variant | final | Sharpe | MDD |
| --- | ---: | ---: | ---: |
| `scaling_selector_w378_k8_q03_s2_a22_c1_any` | 2343317.419640927 | 2.342542127898225 | -0.25584794695809554 |

判斷：

- Step 3 沒有改變正式升級結論。
- 2025-01-02 ~ 2026-06-18 formal upgrade pass 仍為 0。
- 正式 latest 仍維持 A20.7。

下一步建議：

- Step 4：把實際持股/Excel 評估收進 `group_a_plus/portfolio/`，包含 `evaluate_group_a_plus_plus_00751b_cash.py`。

## 2026-06-19 Current Handoff Summary

目前正式策略狀態：

- latest pointer 未更動。
- 正式 latest 仍是 A20.7：`switch_risk_ma75_dd11_total6_hold5_eg0175_xg020`。
- 2025-01-02 ~ 2026-06-18 A20.7 指標：
  - final value：2333356.2334819334
  - Sharpe：2.3399277909169327
  - Sortino：2.4896386567803552
  - MDD：-0.2527534866588963
  - events：2
  - rows：352
- 2025-01-02 ~ 2026-06-18 governance compare：
  - candidate files：4
  - candidate rows：3604
  - formal upgrade pass：0
  - research watchlist pass：0

已完成架構改造：

| step | context | main modules | compatibility entry points |
| --- | --- | --- | --- |
| 1 | data | `group_a_plus/data/registry.py`, `group_a_plus/data/coverage.py` | `group_a_plus_data_registry.py`, `group_a_plus_data_coverage_check.py` |
| 2 | runners | `group_a_plus/runners/a207.py` | `group_a_plus_runner.py` |
| 3 | governance | `group_a_plus/governance/catalog.py`, `group_a_plus/governance/compare.py` | `group_a_plus_runner_catalog.py`, `compare_group_a_plus_results.py` |

可直接重跑的核心命令：

```bash
python3 -m group_a_plus.data.registry --output results/group_a_plus_data_registry_latest.json
python3 -m group_a_plus.data.coverage --start 2025-01-02 --end 2026-06-18 --output results/group_a_plus_data_coverage_latest.json
python3 -m group_a_plus.runners.a207 --start 2025-01-02 --end 2026-06-18 --output results/group_a_plus_runner_a207_latest.json --frame-output results/group_a_plus_runner_a207_latest_frame.csv
python3 -m group_a_plus.governance.catalog --start 2025-01-02 --end 2026-06-18 --output results/group_a_plus_runner_catalog_latest.json
python3 -m group_a_plus.governance.compare --baseline results/group_a_plus_runner_a207_latest.json --candidates results/group_a_plus_news_anomaly_2025_2026_20260619.json results/group_a_plus_derivative_options_overlay_2025_2026_20260619.json results/group_a_plus_scaling_tail_2025_2026_20260619.json results/group_a_plus_abm_agents_2025_2026_focused_20260619.json --output results/group_a_plus_compare_latest.json
```

後續建議順序：

1. Step 4：搬 `evaluate_group_a_plus_plus_00751b_cash.py` 到 `group_a_plus/portfolio/`。
2. Step 5：把 news/options/scaling/ABM overlays 慢慢收進 `group_a_plus/strategies/`，但先保留根目錄舊入口。
3. Step 6：把交接報告拆成 `report/group_a_plus/architecture/` 與 `report/group_a_plus/results/`，避免單一 handoff 過長。

## 2026-06-19 Architecture Refactor Step 4 - Portfolio Evaluation

目標：

- 把實際持股 / Excel 評估工具收進 portfolio context。
- 保留舊入口，讓既有 `evaluate_group_a_plus_plus_00751b_cash.py` 命令不失效。
- 不改 00751B vs cash 的計算方法與結論。

新增模組：

| path | purpose |
| --- | --- |
| `group_a_plus/portfolio/__init__.py` | portfolio context package |
| `group_a_plus/portfolio/cash_00751b.py` | GroupA++ 00751B vs cash implementation |

相容入口：

| old path | now delegates to |
| --- | --- |
| `evaluate_group_a_plus_plus_00751b_cash.py` | `group_a_plus.portfolio.cash_00751b.main()` |

驗證指令：

```bash
python3 evaluate_group_a_plus_plus_00751b_cash.py --start 2025-01-02 --end 2026-06-18 --output-prefix results/group_a_plus_plus_00751b_cash_arch_step4_wrapper_20260619 --workbook-output taiwan_stock_20260619_groupA++_00751B_eval_arch_step4_wrapper.xlsx
python3 -m group_a_plus.portfolio.cash_00751b --start 2025-01-02 --end 2026-06-18 --output-prefix results/group_a_plus_plus_00751b_cash_arch_step4_module_20260619 --workbook-output taiwan_stock_20260619_groupA++_00751B_eval_arch_step4_module.xlsx
python3 -m compileall group_a_plus evaluate_group_a_plus_plus_00751b_cash.py
```

驗證結果：

| check | result |
| --- | --- |
| wrapper | success, JSON/curve/workbook generated |
| module | success, JSON/curve/workbook generated |
| curve compare | wrapper/module `portfolio_value` curves match |
| compileall | pass |

2025-01-02 ~ 2026-06-18 指標：

| scenario | final | total return | Sharpe | MDD |
| --- | ---: | ---: | ---: | ---: |
| GroupA++ with 00751B | 408236.6019592285 | 0.19568883056873765 | 1.0347341538789327 | -0.14681351187276837 |
| GroupA++ 00751B as cash | 413516.61599731445 | 0.21115352378900898 | 1.6145959682879059 | -0.08406182067361323 |
| 00751B only | 129039.99328613281 | -0.039309214935799974 | -0.14083934911521664 | -0.16384988078934404 |
| cash replacing 00751B | 134320.00732421875 | 0.0 | 0.0 | 0.0 |

判斷：

- Step 4 沒有改變先前投資結論。
- close-only local data 下，00751B 仍不優於 zero-yield cash。
- 2025~2026 portfolio drag：-5280.0140380859375。
- 若要更精準比較，下一步要匯入 00751B 配息資料後做 total-return 版本。

下一步建議：

- Step 5：建立 `group_a_plus/strategies/`，先搬 news/options/scaling/ABM overlays 的 entry points。

## 2026-06-19 Architecture Refactor Step 5 - Strategy Entry Points

目標：

- 建立 `group_a_plus/strategies/` context。
- 先搬四個研究 overlay 的 module entry points：
  - news anomaly
  - derivative/options overlay
  - scaling-tail proxy
  - ABM observable agents
- 不改 overlay 策略內部邏輯；根目錄原腳本仍保留。

新增模組：

| path | purpose |
| --- | --- |
| `group_a_plus/strategies/__init__.py` | strategies context package |
| `group_a_plus/strategies/news_anomaly.py` | delegates to `backtest_group_a_plus_news_anomaly.py` |
| `group_a_plus/strategies/options_overlay.py` | delegates to `backtest_group_a_plus_derivative_options_overlay.py` |
| `group_a_plus/strategies/scaling_tail.py` | delegates to `backtest_group_a_plus_scaling_tail.py` |
| `group_a_plus/strategies/abm_agents.py` | delegates to `backtest_group_a_plus_abm_agents.py` |

Catalog 更新：

- `group_a_plus/governance/catalog.py` runner count 由 4 增加到 5。
- 新增 `abm_agents` runner。
- A20.7/news/options/scaling/ABM 皆有 `module` 與 `module_command_template`。

驗證指令：

```bash
python3 -m group_a_plus.governance.catalog --start 2025-01-02 --end 2026-06-18 --output results/group_a_plus_runner_catalog_arch_step5_module_20260619.json
python3 -m compileall group_a_plus
python3 -m group_a_plus.strategies.news_anomaly --start 2025-01-02 --end 2026-06-18 --z-thresholds 1.0 --min-counts 2 --max-return-5d 0.0 --min-hold-days 3 --output-prefix results/group_a_plus_news_anomaly_arch_step5_module_20260619
python3 -m group_a_plus.strategies.options_overlay --start 2025-01-02 --end 2026-06-18 --min-scores 2 --min-pcr-z 0.5 --min-dealer-z 0.5 --max-return-5d 0.0 --min-hold-days 3 --output-prefix results/group_a_plus_options_overlay_arch_step5_module_20260619
python3 -m group_a_plus.strategies.scaling_tail --start 2025-01-02 --end 2026-06-18 --windows 378 --tail-counts 8 --quantiles 0.03 --min-scores 2 --max-alphas 2.2 --min-clusters 1 --output-prefix results/group_a_plus_scaling_tail_arch_step5_module_20260619
python3 -m group_a_plus.strategies.abm_agents --start 2025-01-02 --end 2026-06-18 --fitness-windows 20 --betas 1.5 --demand-thresholds 0.20 --risk-thresholds 4 --low-risk-thresholds 1 --momentum-days 10 --trend-returns 0.015 --hot-returns 0.08 --buy-dip-drawdowns -0.06 --min-hold-days 0 --output-prefix results/group_a_plus_abm_agents_arch_step5_module_20260619
```

Smoke test 結果：

| module | rows | best variant | final | Sharpe | MDD |
| --- | ---: | --- | ---: | ---: | ---: |
| news anomaly | 352 | `news_selector_z10_c2_r00` | 2184977.369424982 | 2.286494299481211 | -0.2527534866588963 |
| options overlay | 352 | `opts_selector_s2_p05_d05_r00` | 2173422.0222228095 | 2.2841199269951726 | -0.2527534866588963 |
| scaling tail | 352 | `scaling_selector_w378_k8_q03_s2_a22_c1_any` | 2343317.419640927 | 2.342542127898225 | -0.25584794695809554 |
| ABM agents | 352 | `abm_fw20_b15_d20_r4_lr1_m10_tr015_hot08_dip06_h0_all` | 2155573.7102902494 | 2.312813447200839 | -0.2613280906153771 |

判斷：

- Step 5 只新增 module entry points，不改正式 latest。
- smoke test 用縮小 grid，不取代之前完整 backtest/comparator 結論。
- 正式 2025~2026 comparator formal pass 仍以 Step 3/既有完整 JSON 為準：0。

下一步建議：

- Step 6：整理報告結構，或開始把 strategy 內部共用載入/輸出函式抽到 `group_a_plus/strategies/common.py`。

## 2026-06-19 Architecture Refactor Step 6 - Report Structure

目標：

- 將架構狀態與正式結果摘要從大型 handoff 拆出。
- 保留本檔作為完整實驗歷史，不移除或改寫既有紀錄。
- 本步不修改策略程式、latest pointer 或 comparator 規則。

新增報告：

| path | purpose |
| --- | --- |
| `report/group_a_plus/architecture/ARCHITECTURE_20260619.md` | Step 1-6 架構、責任邊界、相容入口與核心命令 |
| `report/group_a_plus/results/RESULTS_20260619.md` | A20.7、promotion check、coverage、00751B 與 smoke test 結果 |

目前閱讀順序：

1. 先讀 `report/group_a_plus/results/RESULTS_20260619.md` 取得正式結論。
2. 再讀 `report/group_a_plus/architecture/ARCHITECTURE_20260619.md` 了解可用模組與命令。
3. 需要完整研究歷史時，再讀本 handoff。

Step 6 結論：

- 正式 latest 仍是 A20.7。
- 2025~2026 formal upgrade pass 仍為 0。
- 報告已分成 architecture / results / detailed review 三層。

下一步建議：

- Step 7：以逐檔方式抽取 strategy 共用 loading/output helper，且每次都比對 JSON 與 curve。

## 2026-06-19 Final Check and Continued Improvement

完整檢查：

| check | result |
| --- | --- |
| `compileall` | pass |
| package imports | pass |
| catalog runners | 6 |
| data coverage | warn, hard failures 0, soft gaps 5 |
| A20.7 recent reproduction | exact match with latest pointer |
| recent full comparator | rows 3604, formal 0, watchlist 0 |
| long full comparator | rows 904, formal 4, watchlist 10 |

A20.7 重現：

| window | final | Sharpe | Sortino | MDD | events |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2025-01-02 ~ 2026-06-18 | 2333356.2334819334 | 2.3399277909169327 | 2.4896386567803552 | -0.2527534866588963 | 2 |
| 2020-01-02 ~ 2026-06-18 | 5364941.308021644 | 1.2196021072572127 | 1.1916928689859192 | -0.37759346735702204 | 4 |

latest pointer 檢查：

- `report/group_a_plus/latest/switch_backtest.json`
- variant 仍是 `switch_risk_ma75_dd11_total6_hold5_eg0175_xg020`
- recent final / Sharpe / Sortino / MDD 與重跑結果精確一致。

### Scaling-tail ready refinement

新增：

- `backtest_group_a_plus_scaling_tail_ready.py`
- `group_a_plus/strategies/scaling_tail_ready.py`
- catalog id：`scaling_tail_ready`

修正：

- `hill_alpha == 0` 不再視為 tail stress，因為 0 也代表 rolling history 尚未成熟。
- feature 先載入 900 calendar days warmup，再切回 requested window。
- 只允許在 A20.7 為 `golden1` 時啟動短期 defensive addon。

結果：

| window | rows | effective | formal pass | best |
| --- | ---: | ---: | ---: | --- |
| 2025-01-02 ~ 2026-06-18 | 72 | 24 | 0 | final 2209180, Sharpe 2.293, MDD -25.28% |
| 2020-01-02 ~ 2026-06-18 | 72 | 72 | 36 | final 5562989, Sharpe 1.285, MDD -37.76% |

長期最佳：

- `scaling_ready_w378_k8_q03_s2_a30_c3_r00_h2`
- override days：6
- trigger dates：
  - 2024-07-18
  - 2024-08-02
  - 2024-08-06

判斷：

- ready-filter 與 warmup 是合理的訊號品質改善。
- 但 2025~2026 formal pass = 0，因此不可升級 latest。
- 正式 latest 繼續維持 A20.7。
- `scaling_tail_ready` 留作下一輪研究候選，不覆寫 latest pointer。

## 2026-06-19 FinGPT Sentiment Alignment Candidate

新增：

- `backtest_group_a_plus_fingpt_sentiment_alignment.py`
- `group_a_plus/strategies/fingpt_sentiment_alignment.py`
- `test_group_a_plus_fingpt_sentiment_alignment.py`
- catalog id：`fingpt_sentiment_alignment`

設計：

- 以規則式金融情緒代理重現 FinGPT 的多週新聞聚合概念。
- 聚合 7/14/28 日 sentiment、risk、concern ratio 與 news intensity。
- 分類利率、匯率/流動性、半導體及地緣政治事件。
- 新聞延遲一個曆日，週末新聞在下一交易日生效。
- 必須搭配 0050 五日報酬轉弱，且只覆蓋 A20.7 的 `golden1`。
- 正式資格要求至少兩個獨立來源覆蓋 50% 交易日。

結果：

| window | rows | effective | formal pass | best |
| --- | ---: | ---: | ---: | --- |
| 2025-01-02 ~ 2026-06-18 | 216 | 48 | 0 | final 2324806, Sharpe 2.338, MDD -25.28% |
| 2020-01-02 ~ 2026-06-18 | 216 | 192 | 0 | final 4933053, Sharpe 1.269, MDD -33.26% |

長期最佳：

- `fingpt_align_r20_s00_z00_ret00_h3`
- trigger days：20
- override days：60
- A20.7 長期基準：final 5364941、Sharpe 1.220、MDD -37.76%

判斷：

- 長期 Sharpe 與回撤改善，但最終價值下降約 8.1%。
- 近期表現略低於 A20.7，只有 3 個 override days。
- 近期雙來源覆蓋 0%，長期僅 1.08%，未達 50% 資料門檻。
- 保留為 risk-research candidate，不覆寫 latest pointer。

## 2026-06-19 A20.7 Dynamic Exposure Candidate

新增：

- `backtest_group_a_plus_dynamic_exposure.py`
- `group_a_plus/strategies/dynamic_exposure.py`
- `test_group_a_plus_dynamic_exposure.py`
- catalog id：`dynamic_exposure`

設計：

- A20.7 完整防禦訊號優先，不改寫原始進出規則。
- Golden1 與 defensive 權重按 25% / 50% / 75% / 100% 混合。
- 提前防禦要求價格壓力及 total risk score 同時成立。
- 退出採逐級恢復；五日動能轉正且 20/60 日相對波動平穩時才加快。

結果：

| window | rows | effective | formal pass | best |
| --- | ---: | ---: | ---: | --- |
| 2025-01-02 ~ 2026-06-18 | 32 | 32 | 0 | final 2157557, Sharpe 2.291, MDD -25.29% |
| 2020-01-02 ~ 2026-06-18 | 32 | 32 | 0 | final 4667482, Sharpe 1.264, MDD -32.77% |

判斷：

- 長期 Sharpe 與 MDD 優於 A20.7，但 final value 下降約 13.0%。
- 近期 final、Sharpe、MDD 均未勝過 A20.7。
- 收緊到 risk score 6-7 的近期 focused sweep 仍為 0 formal pass。
- 不升級 latest；保留作風險預算或低回撤偏好帳戶的研究候選。

### 2026-06-20 micro refinement

新增限制與可觀測性：

- `min_tail_score=1` 尾部風險確認。
- warning 必須連續 1-2 日，且未使用未來資料。
- 新增 10% / 20% 初階防禦層級。
- best frame 增加 `desired_defensive_share` 與 `exposure_reason`。
- 驗證拆成 2020-2024 train、2025-2026 validation、2020-2026 long。

最佳結果：

| window | final delta | Sharpe delta | MDD delta | formal |
| --- | ---: | ---: | ---: | ---: |
| 2020-2024 train | -1.61% | +0.058 | +5.14pp | 0 |
| 2025-2026 validation | -4.04% | -0.002 | 0.00pp | 0 |
| 2020-2026 long | -5.17% | +0.063 | +5.14pp | 0 |

結論：risk score 4 只在 train 改善風險；validation 沒有 MDD 改善。
risk score 5 在 train 完全不觸發，顯示 regime instability。停止繼續微調
門檻，A20.7 latest 不變。

## 2026-06-20 A20.8 Coverage-Normalized Risk

新增：

- `backtest_group_a_plus_coverage_normalized.py`
- `group_a_plus/strategies/coverage_normalized.py`
- `test_group_a_plus_coverage_normalized.py`
- catalog id：`coverage_normalized`

資料診斷：

- `institutional_data`、`margin_data` 從 2020 開始。
- `shareholding_distribution` 為週資料，涵蓋長期但需 staleness 控制。
- 放空、借券、當沖、券商期貨/選擇權與衍生品法人資料多從 2025 開始。
- 固定 `total_risk_score >= 6` 在不同年代代表不同風險比例。

A20.8 規則：

- 逐特徵追蹤 maturity 與最近可用觀測。
- coverage 足夠時使用 `available_risk_count / available_features`。
- coverage 不足時 fallback A20.7 raw score。
- 只替換 entry risk confirmation；價格、hold、exit、weights 不變。

結果：

| window | selected | final delta | Sharpe delta | MDD delta | formal |
| --- | --- | ---: | ---: | ---: | ---: |
| 2020-2024 train | r35/m6 | -4.39% | +0.044 | +6.40pp | 0 |
| 2025-2026 validation | r50/m4 | 0.00% | 0.000 | 0.00pp | 0 |
| 2020-2026 long | r50/m6 | -4.17% | +0.062 | +6.40pp | 0 |

55%/60% 在 validation 延後防禦後反而略差。A20.8 保留為 coverage
audit 與低回撤研究候選；正式 latest 維持 A20.7。

## 2026-06-20 A20.9 Warmup Consistency / Source Hygiene

問題：

- 2025 起跑的 A20.7 在 2025-02-25 進防禦。
- 2020 起跑的 A20.7 對同一段資料在 2025-03-03 才進防禦。
- 原因之一是 MA75/rolling features 從 evaluation start 才開始。
- 另一原因是 2022 TDCC 週變化被無限 ffill 到 2025，且 2025 第一筆
  新資料會直接與 2022 最後一筆做假週差分。

核心修正：

- 日資料 `ffill(limit=5)`。
- TDCC `ffill(limit=10)`。
- TDCC 觀測間隔大於 21 calendar days 時，change 強制歸零。
- 新增 source-staleness regression test。

A20.9：

- 先載入 180/365/540 calendar days warmup。
- 在完整歷史計算 features 與 regime state，再切 requested window。
- 三個 warmup 長度事件完全一致。
- recent 與 long 的 2025-2026 重疊區間，regime 與全部核心風險欄位逐日
  精確一致。

結果：

| window | final delta | Sharpe delta | MDD delta | formal |
| --- | ---: | ---: | ---: | ---: |
| 2025-2026 | -0.249% | -0.012 | -0.31pp | 0 |
| 2020-2026 | 0.000% | 0.000 | 0.00pp | 0 |

判斷：近期 no-warmup 數字有小幅 optimistic start bias。資料時效修正保留，
A20.9 暫為 methodology candidate；latest pointer 仍為 A20.7。

## 2026-06-20 A21 Defensive Basket Robustness

新增：

- `backtest_group_a_plus_defensive_basket.py`
- `group_a_plus/strategies/defensive_basket.py`
- `test_group_a_plus_defensive_basket.py`
- catalog id：`defensive_basket`

方法：

- 固定 A20.7 + 180-day warmup 的 regime，不再改進出門檻。
- 本地 OHLCV `dividends` 建立 ETF total return。
- commission 0.1425%、slippage 0.05%。
- 非債券 ETF 賣出稅 0.1%；00679B 在測試期間依規定免證交稅。
- stress：cost 2x、signal delay 1 day、signal delay 3 days。
- A21 rows 設 `formal_eligible=false`，避免與舊 price-only baseline 誤比。

結果：

- train winner：`bond30_cash30`，但 validation final value 下降 39700。
- `cash40` 在 train/validation/long 的 base final delta 分別為
  +20382 / +17785 / +93832。
- `cash40` validation Sharpe +0.145，MDD +4.24pp。
- cost2x 與 delay1 仍優於 matched baseline。
- delay3 在 train / validation final 分別落後 13931 / 399。

判斷：`cash40` 是目前最有價值的觀察候選，但不是 train winner，且未通過
全部 delay stress，因此 A21 formal pass = 0；latest 維持 A20.7。

### A21.1 episode-selected cash30

新增 `cash30`：0050 60%、00631L 10%、cash 30%。不再增加其他權重。

選擇方法：

- 只用 2020-2024。
- A20.7 price stress / recovery 形成 9 個至少 5 trading days episodes。
- minimax 先比較 worst episode return delta，再比較 median、joint wins、MDD。
- train-only selector 選出 `cash30`。
- `cash30` worst episode delta -0.48%，優於 cash40 -0.95%。

獨立 validation：

| scenario | final delta | Sharpe delta | MDD delta |
| --- | ---: | ---: | ---: |
| base | +10535 | +0.077 | +2.17pp |
| cost2x | +11377 | +0.078 | +2.18pp |
| delay1 | +8459 | +0.075 | +2.11pp |
| delay3 | +1342 | +0.068 | +2.17pp |

validation 四情境全通過；但 train delay3 final delta = -6092。結論改為：
`cash30` 是 A21.1 provisional 首選，取代 cash40 作觀察，但 latest 暫不改。

### A21.2 locked latency matrix

- entry delay 與 exit delay 分別測 0/1/2/3 days，共 16 組。
- train 先選 `cash30`；validation/long 使用 `--latency-basket cash30` 鎖定，
  禁止在後期資料重選。

| window | joint/final pass | Sharpe pass | MDD pass | median final delta | worst |
| --- | ---: | ---: | ---: | ---: | ---: |
| train | 10/16 | 16/16 | 16/16 | +2172 | -6092 |
| validation | 15/16 | 16/16 | 16/16 | +8670 | -305 |
| long | 13/16 | 16/16 | 16/16 | +27026 | -10753 |

validation 唯一失敗為 enter delay 1 + exit delay 3，final -305，但 Sharpe/MDD
仍改善。證據很強但未達 16/16，A21.2 繼續 provisional，latest 不變。

### A21.3 recovery ramp

規則：

- A20.7 entry/formal exit 完全不變。
- defensive 初始使用 cash30。
- defensive 期間 `ma_gap >= 0` 且 5d momentum > 0 時，一次性切回原
  A20.7 defensive weights。
- 仍等 A20.7 正式 exit 才回 Golden1。

結果：

| window | final delta | Sharpe delta | MDD delta | core stress | latency |
| --- | ---: | ---: | ---: | ---: | ---: |
| train | +9876 | +0.010 | 0.00pp | 4/4 | 16/16 |
| validation | +7420 | +0.070 | +2.17pp | 4/4 | 16/16 |
| long | +41817 | +0.020 | 0.00pp | 4/4 | 16/16 |

新增正式候選 runner：

- `group_a_plus.runners.a213`
- `group_a_plus_a213_runner.py`
- decision record：`report/group_a_plus/decision/json/a213_promotion_candidate_20260620.json`

狀態已更新為 `activated_via_schema_v2`：

- `report/group_a_plus/latest/strategy.json` 啟用 A21.3。
- `group_a_plus.runners.latest` 為 allowlisted dispatcher。
- `group_a_plus_latest_runner.py` 為相容 CLI。
- 舊 `latest/switch_backtest.json` 保留 A20.7，供 price-only / two-regime
  consumers 使用。
- v2 latest runner 與 dedicated A21.3 runner 指標精確一致。
- 2026-06-18 最新 execution regime = `golden1`。
