# GroupA+ 最新策略交接紀錄 2026-06-19

## 目前正式策略

正式 latest strategy 維持 A20.7：

`switch_risk_ma75_dd11_total6_hold5_eg0175_xg020`

### 規則參數

| 欄位 | 值 |
| --- | ---: |
| `ma_window` | 75 |
| `enter_ma_gap` | -0.0175 |
| `exit_ma_gap` | 0.0200 |
| `drawdown_window` | 75 |
| `enter_drawdown` | -0.11 |
| `exit_momentum_days` | 5 |
| `min_hold_days` | 5 |
| `require_total_risk_score` | 6 |
| `exit_max_total_risk_score` | 6 |
| `require_tail_risk_score` | 0 |

正式 latest pointer：

- `report/group_a_plus/latest/switch_backtest.json`

確認內容：

- latest variant：`switch_risk_ma75_dd11_total6_hold5_eg0175_xg020`
- latest final：`2333356.2334819334`
- latest STARR 5%：`0.06905139898243232`

## 最新區間回測：2025-01-02 ~ 2026-06-18

輸出：

- `results/group_a_plus_switch_policy_backtest_latest_ma75_risk6_confirm_20260618.json`
- `results/group_a_plus_switch_policy_backtest_latest_ma75_risk6_confirm_20260618.csv`
- `results/group_a_plus_switch_policy_backtest_latest_ma75_risk6_confirm_20260618_curve.csv`
- `results/group_a_plus_switch_policy_backtest_latest_ma75_risk6_confirm_20260618_recommended_regime.csv`

### 核心結果

| 指標 | A20.7 |
| --- | ---: |
| final | 2333356.2334819334 |
| total_return | 1.3333562334819336 |
| annual_return | 0.7891268088537762 |
| volatility | 0.2765637569309657 |
| downside_deviation | 0.2599329902918739 |
| Sharpe | 2.3399277909169327 |
| Sortino | 2.4896386567803552 |
| MDD | -0.2527534866588963 |
| VaR 5% | -0.024120399728167707 |
| ETL 5% | -0.03718987332346835 |
| STARR 5% | 0.06905139898243232 |
| volatility-weighted ETL 5% | -0.048858150651903146 |
| worst_daily_return | -0.08752595361174664 |
| worst_20d_return | -0.18926309603946512 |

### 切換事件

| 日期 | 事件 | ma_gap | drawdown | chip_score | derivative_score | total_risk_score |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 2025-02-25 | switch_to_group_a_plus_defensive | -0.01792424670813675 | -0.052592956560674864 | 5 | 1 | 6 |
| 2025-06-05 | switch_to_golden | 0.021083048030267726 | -0.08234404295555386 | 2 | 0 | 2 |

### 對照

| variant | final | Sharpe | Sortino | MDD | ETL 5% | STARR 5% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `golden1_0531_1m` | 2246432.231891271 | 2.229630818237287 | 2.3271844833336277 | -0.27538670040425206 | -0.03772760000608948 | 0.06524748850458718 |
| `group_a_plus_defensive_1m` | 2112079.6651531374 | 2.2676785041878786 | 2.3935445287597306 | -0.25346979287067073 | -0.03317434565254426 | 0.06802626369512531 |
| A20.7 | 2333356.2334819334 | 2.3399277909169327 | 2.4896386567803552 | -0.2527534866588963 | -0.03718987332346835 | 0.06905139898243232 |

判斷：

- 最新區間 A20.7 是三者中 final、Sharpe、Sortino、STARR 最佳。
- MDD 與 defensive 接近，明顯優於 Golden1。
- 正式 latest 可以維持 A20.7。

## 2020~2024 回測驗證

使用者要求將新策略回測 2020~2024，已完成。

輸出：

- `results/group_a_plus_switch_policy_backtest_2020_2024_a207_latest_20260619.json`
- `results/group_a_plus_switch_policy_backtest_2020_2024_a207_latest_20260619.csv`
- `results/group_a_plus_switch_policy_backtest_2020_2024_a207_latest_20260619_curve.csv`
- `results/group_a_plus_switch_policy_backtest_2020_2024_a207_latest_20260619_recommended_regime.csv`

### 結果

| variant | final | total_return | Sharpe | Sortino | MDD | ETL 5% | STARR 5% | switch_count |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `golden1_0531_1m` | 2286403.73298109 | 1.28640373298109 | 0.85884249512305 | 0.8129461692354303 | -0.3700639131250332 | -0.034185918243866416 | 0.02305197636166174 |  |
| `group_a_plus_defensive_1m` | 2052613.726685848 | 1.052613726685848 | 0.8286287202207893 | 0.795462903399181 | -0.3449191318695233 | -0.030294494697666968 | 0.022343899866443136 |  |
| 2020~2024 recommended `switch_ma20_dd7_hold5` | 2159413.2614561943 | 1.1594132614561943 | 0.9098145827021811 | 0.8791763449499925 | -0.32708975389876493 | -0.028589521143004476 | 0.024887085201101496 | 34 |
| A20.7 | 2343193.374873824 | 1.3431933748738238 | 0.8702898255394882 | 0.826594074932757 | -0.37759346735702204 | -0.034560167394787206 | 0.023491463009054372 | 2 |

### A20.7 在 2020~2024 的切換事件

| 日期 | 事件 | ma_gap | drawdown | chip_score | derivative_score | total_risk_score |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 2020-03-06 | switch_to_group_a_plus_defensive | -0.048714847961127905 | -0.10395537686230549 | 6 | 0 | 6 |
| 2020-06-01 | switch_to_golden | 0.02170984595630343 | -0.08660565558539823 | 1 | 0 | 1 |

判斷：

- A20.7 在 2020~2024 的 final 最高。
- 但 Sharpe、Sortino、MDD、ETL、STARR 都輸給 `switch_ma20_dd7_hold5`。
- A20.7 只切換 2 次，舊區間太偏進攻，回撤與尾部損失較差。
- 因此 A20.7 適合目前 2025~2026 regime，但不適合直接作為全歷史唯一規則。

## A20.7 微調實驗

使用者要求對最新策略做微調。已跑兩輪 sweep，固定：

- `require_total_risk_score=6`
- `exit_max_total_risk_score=6`
- `min_hold_days=5`
- 不啟用 tail risk 硬門檻

### Sweep 1：A20.7 周邊細網格

輸出：

- `results/group_a_plus_latest_a207_micro_sweep_20260619.json`
- `results/group_a_plus_latest_a207_micro_sweep_20260619.csv`
- `results/group_a_plus_latest_a207_micro_sweep_20260619_best_regime.csv`

設定：

- MA：72,73,74,75,76,77,78
- drawdown：-0.105,-0.11,-0.115
- enter gap：-0.01625,-0.0175,-0.01875,-0.02
- exit gap：0.01875,0.02,0.02125,0.0225

結果：

- rules_total：224
- eligible：112
- best：`switch_risk6_ma73_dd11_hold5_eg017_xg022`
- 但與正式 A20.7 指標完全相同，切換日期也相同。

### Sweep 2：降低 exit gap

輸出：

- `results/group_a_plus_latest_a207_micro_sweep_exit_low_20260619.json`
- `results/group_a_plus_latest_a207_micro_sweep_exit_low_20260619.csv`
- `results/group_a_plus_latest_a207_micro_sweep_exit_low_20260619_best_regime.csv`

設定：

- MA：68,69,70,71,72,73,74,75,76
- drawdown：-0.105,-0.11,-0.115
- enter gap：-0.015,-0.01625,-0.0175,-0.01875
- exit gap：0.0125,0.015,0.01625,0.0175,0.01875,0.02

結果：

- rules_total：432
- eligible：216
- best：`switch_risk6_ma75_dd11_hold5_eg017_xg020`
- 這就是正式 A20.7。
- 沒有任何候選同時滿足 final 高於 A20.7、Sharpe 不低於 A20.7、MDD 不差於 A20.7。

### 微調結論

- A20.7 附近是一個績效平台，多組近鄰參數會產生相同切換日期與相同績效。
- 若放寬 enter gap 到 -1.50% 或 -1.625%，會提前至 2025-02-14 進防守，但 final、Sharpe、MDD 都變差。
- 若 exit gap 造成 2025-06-06 才回 Golden，final 與 Sharpe 也下降。
- 本次沒有找到可升級為 A20.8 的候選。
- 正式策略維持 A20.7。

## PDF 導入狀態

已分析並導入過的 PDF 概念：

1. `Applied Quantitative Finance.pdf`
   - 導入 tail risk / volatility regime 診斷。
   - tail1 作為硬門檻會延後防守並降低績效，不升級。

2. `Nonlinear Optimization with Financial Applications.pdf`
   - 導入 downside deviation、Sortino、worst_daily_return、worst_20d_return。

3. `Quantitative Finance for Physicists - An Introduction.pdf`
   - 導入 VaR、ETL、Kupiec test、volatility-weighted VaR/ETL。

4. `Bayesian Methods in Finance.pdf`
   - 導入 STARR 5% 指標。
   - 建議下一步做 Bayesian-style model averaging / regime-aware rule selection。

目前已落地到 `backtest_group_a_plus_switch_policy.py` 的評估欄位：

- `downside_deviation`
- `sortino_ratio`
- `worst_daily_return`
- `worst_20d_return`
- `value_at_risk_5pct`
- `expected_tail_loss_5pct`
- `starr_ratio_5pct`
- `var_breach_count_5pct`
- `var_breach_ratio_5pct`
- `kupiec_lr_5pct`
- `kupiec_pvalue_5pct`
- `volatility_weighted_var_5pct`
- `volatility_weighted_etl_5pct`

## 6/22 預測狀態

資料截止：2026-06-18  
預測日：2026-06-22  
stale_days：4

### Golden1_0531

輸出：

- `results/signal_group_a_golden1_0531_predict_20260622_from_20260618_total1000000_latest.json`
- `results/signal_group_a_golden1_0531_predict_20260622_from_20260618_total1000000_latest.csv`

結果：

- signal_status：`rebalance`
- signal_reason：`rebalance_to_0050_60_00631L_20_cash_20`
- target_weights：
  - 0050：0.6
  - 00631L：0.2
  - 00679B：0
  - 00632R：0
  - cash：約 0.2

### GroupA+ 最新策略

輸出：

- `results/group_a_plus_latest_strategy_predict_20260622_from_20260618_total1000000.json`
- `results/group_a_plus_latest_strategy_predict_20260622_from_20260618_total1000000.csv`
- `results/group_a_plus_latest_strategy_predict_20260622_from_20260618_total1000000.md`

結果：

- status：`rebalance`
- overlay_00679b_weight：0
- weights：
  - 0050：0.6
  - 00631L：0.2
  - 00632R：0
  - 00679B：0
  - cash：0.2

結論：

- Golden1_0531 與 GroupA+ 最新策略方向一致。
- 6/22 建議仍是 0050 60%、00631L 20%、現金 20%。
- GroupA+ 不加 00679B overlay。

## 重要判斷

1. **可以 switch to A20.7**
   - 最新 live / 近期 regime 使用 A20.7 是合理的。
   - latest pointer 已確認是 A20.7。

2. **不建議 A20.7 套全歷史**
   - 2020~2024 A20.7 final 高，但風險調整差。
   - 舊區間較適合 `switch_ma20_dd7_hold5`。

3. **微調 A20.7 已接近極限**
   - 兩輪鄰近 sweep 沒找到 A20.8。
   - 繼續壓 MA/DD/gap 門檻大概率只是過度配適。

4. **下一個真正改善方向**
   - regime-aware rule selection。
   - Bayesian-style model averaging。
   - 用 rolling Sharpe、Sortino、MDD、ETL、STARR 判斷該採 MA20/DD7、MA90/DD12 或 A20.7。

## 建議下一步

下一步不要再單純微調 A20.7。建議新增一個實驗：

`group_a_plus_regime_selector`

候選規則：

- 舊區間防守型：`switch_ma20_dd7_hold5`
- 全期均衡型：`switch_ma90_dd12_hold5_eg020_xg010`
- 近期風險確認型：A20.7 `switch_risk_ma75_dd11_total6_hold5_eg0175_xg020`

選擇方法：

- rolling 252 日或 504 日評估。
- score 使用 Sharpe、Sortino、MDD、ETL、STARR。
- 不使用固定 2025 切點，避免 hindsight bias。
- 以 walk-forward 驗證 2020~2026。

驗收條件：

- 2025~2026 不低於 A20.7 太多。
- 2020~2024 Sharpe/MDD/STARR 接近或優於 `switch_ma20_dd7_hold5`。
- 2020~2026 全期 Sharpe、MDD、STARR 優於單一 A20.7。

## 已同步的長紀錄

完整歷史細節仍保留在：

- `GROUP_A_PLUS_RISK6_CONFIRM_HANDOFF_20260618.md`
- `report/group_a_plus/review/md/risk6_confirm_handoff_20260618.md`

本檔是 2026-06-19 可直接接手版本。
