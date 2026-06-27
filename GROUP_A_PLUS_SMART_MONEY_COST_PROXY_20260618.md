# GroupA+ FinGenius 主力成本乖離率等價實驗 - 2026-06-18

## 目的

將 FinGenius 的「主力成本乖離率」概念轉成台股 GroupA+ 可回測的本地資料 proxy。

FinGenius 原始工具依賴 A 股籌碼與東方財富資金流資料，不能直接套到台股。因此本實驗用既有 DuckDB 資料建立台股等價特徵：

- 0050 價格：`ohlcv`
- 三大法人 / 外資買賣超：`institutional_data`
- 融資買賣：`margin_data`
- 既有 chip / derivative risk score：沿用 `backtest_group_a_plus_switch_policy.py`

## 實作

修改檔案：

- `backtest_group_a_plus_switch_policy.py`
- `evaluate_group_a_plus_switch_sweep.py`

新增特徵：

| 欄位 | 意義 |
|---|---|
| `smart_money_cost_20d` | 近 20 日主力成本 proxy |
| `smart_money_cost_60d` | 近 60 日主力成本 proxy |
| `smart_money_cost_gap_20d` | 0050 close / smart_money_cost_20d - 1 |
| `smart_money_cost_gap_60d` | 0050 close / smart_money_cost_60d - 1 |
| `smart_money_pressure_20d` | 近 20 日主力承接力 proxy |
| `smart_money_cost_risk` | 成本乖離風險旗標 |

成本 proxy 計算方式：

- 權重 = max(三大法人買超, 0) + max(外資買超, 0) + max(融資買進 - 融資賣出, 0)
- 主力成本 = 近 N 日加權平均 0050 close
- 若權重為 0，fallback 到近 N 日簡單均價

新增 switch rule 參數：

- `enter_cost_gap_below`：跌破主力成本一定幅度時，可觸發防守。
- `enter_cost_gap_above`：高於主力成本一定幅度時，可觸發過熱防守。
- `exit_cost_gap_below`：離開防守時要求成本乖離回到指定水準以上。

## Smoke Test

期間：2025-01-02 ~ 2026-06-17

`smart_money_cost_gap_20d` 分布：

| 指標 | 數值 |
|---|---:|
| min | -20.73% |
| mean | +1.76% |
| median | +1.49% |
| 75% | +4.39% |
| max | +15.77% |

2026-06-17 最新狀態：

- `smart_money_cost_gap_20d`：+4.64%
- `smart_money_cost_risk`：0

## Sweep 設定

來源：

- `results/group_a_plus_switch_sweep_smart_money_cost_20260618.json`
- `results/group_a_plus_switch_sweep_smart_money_cost_20260618.csv`

掃描條件：

- 原 switch sweep 參數：ma 90/120/150、drawdown -8/-10/-12/-15%、hold 5/10/15/20、entry gap -2/-3/-4%、exit gap +1/+1.5/+2%、derivative score 0/1
- 額外成本條件：
  - `enter_cost_gap_below`：-2%、-4%
  - `enter_cost_gap_above`：+10%、+12%、+15%

總組合：5,184

## 結果

目前正式 switch：

| Variant | Final | Sharpe | MDD | Switches | Defense days |
|---|---:|---:|---:|---:|---:|
| `switch_ma90_dd12_hold5_eg020_xg010` | 2,292,473 | 2.3006 | -25.35% | 2 | 67 |

Smart-money sweep 最佳 Sharpe：

| Variant | Final | Sharpe | MDD | Switches | Defense days |
|---|---:|---:|---:|---:|---:|
| `switch_costa150_deriv1_ma90_dd12_hold20_eg020_xg010` | 2,243,472 | 2.3163 | -25.35% | 4 | 91 |

事件：

| 日期 | 動作 | ma_gap | drawdown | smart_money_cost_gap_20d | chip | derivative |
|---|---|---:|---:|---:|---:|---:|
| 2025-02-27 | switch_to_group_a_plus_defensive | -2.27% | -5.82% | -3.91% | 4 | 2 |
| 2025-06-09 | switch_to_golden | +1.62% | -8.74% | +0.97% | 0 | 0 |
| 2026-05-06 | switch_to_group_a_plus_defensive | +26.63% | 0.00% | +15.45% | 5 | 2 |
| 2026-06-09 | switch_to_golden | +22.72% | -3.81% | +2.17% | 6 | 1 |

## 判斷

主力成本乖離率 proxy 有效可用，但暫不升級 production。

理由：

- 優點：最佳 smart-money 規則 Sharpe 提高，2.3006 → 2.3163。
- 缺點：Final 明顯降低，2,292,473 → 2,243,472，少約 49,001。
- MDD 沒有進一步改善，仍為 -25.35%。
- 增加一次 2026-05-06 過熱防守，降低波動但少吃後續上行。

因此目前保留為 research feature / stress fallback，不取代正式 switch rule。

## 結論

可以做，且已完成可回測版本。

目前最好的使用方式不是直接升級 production，而是：

1. 作為 GroupA+ switch policy 的候選條件。
2. 在下次市場明顯過熱或轉弱時，重新跑 smart-money cost sweep。
3. 若未來跨期間驗證能同時維持 final 並提高 Sharpe，再升級為正式候選。
