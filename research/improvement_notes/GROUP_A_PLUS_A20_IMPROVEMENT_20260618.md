# GroupA+ A20 改善紀錄 - 2026-06-18

## 目標

重驗 A16 與 2026-06-18 cap/grid 結論後，改善 GroupA+。

這次目標不是單純追求最高報酬，而是找一個平衡型防守 profile：

- 保留 2025-2026 近期 replay 的改善。
- 避免 A16 在壓力窗的 guardrail 變弱。
- 將 TDCC overlay 定位為風控工具，不當成主要 alpha 來源。
- 不依賴 00632R，因為近期 replay severe regime 沒有觸發。

## 改動

選定 profile：

```text
focused_tdcc_0124_stab5_turn12_fast_cd3
```

`group_a_plus_config.json` 的主要變更：

| 控制項 | A16 舊值 | A20 新值 |
|---|---:|---:|
| TDCC caution 00679B | 1% | 1% |
| TDCC risk_off 00679B | 3% | 2% |
| TDCC severe 00679B | 5% | 4% |
| regime stability days | 2 | 5 |
| risk_off turnover cap | 14% | 12% |
| severe turnover cap | 14% | 12% |
| fast risk-off duration | 3 天 | 3 天 |
| 00631L risk_on cap | 20% | 20% |
| 00631L caution cap | 18% | 18% |
| 00631L risk_off/severe cap | 0% | 0% |

## 近期 Replay

來源：

- `results/group_a_plus_a20_turn10_12_replay_20260618.json`
- `results/group_a_plus_a20_turn10_12_replay_20260618.csv`

| Variant | Final | Sharpe | MDD | Vol |
|---|---:|---:|---:|---:|
| Base approx | 2,207,967 | 2.7675 | -16.86% | 21.98% |
| A16 `0135_stab2_turn14_fast_cd3` | 2,290,066 | 2.9335 | -15.75% | 21.63% |
| A20 `0124_stab5_turn12_fast_cd3` | 2,291,456 | 2.9231 | -15.86% | 21.73% |

A20 相對 base：

- Final：+83,489
- Sharpe：+0.1556
- MDD：改善 +0.999pp
- Vol：降低 -0.252pp

A20 相對 A16：

- Final：+1,390
- Sharpe：-0.0104
- MDD：-0.118pp
- Vol：+0.100pp

## Multi-Window Stress

來源：

- `results/group_a_plus_a20_turn10_12_stress_20260618.json`
- `results/group_a_plus_a20_turn10_12_stress_20260618.csv`
- `results/group_a_plus_a20_a16_stress_recheck_20260618.json`

Aggregate 相對 base：

| Variant | 正報酬窗數 | Avg Final Delta | Worst Final Delta | Min Sharpe Delta | Avg MDD 改善 | Avg Vol 降低 |
|---|---:|---:|---:|---:|---:|---:|
| A16 `0135_stab2_turn14_fast_cd3` | 4/5 | +53,077 | -29,143 | -0.0013 | +5.956pp | +2.363pp |
| A15 `0124_stab5_turn14_fast_cd3` | 4/5 | +56,037 | -20,127 | +0.0382 | +5.303pp | +2.135pp |
| A20 `0124_stab5_turn12_fast_cd3` | 4/5 | +54,330 | -18,627 | +0.0230 | +5.162pp | +2.045pp |

解讀：

- A16 仍是好的 return-seeking research candidate，但 stress min-Sharpe 會轉負。
- A15 在這三者中 stress-Sharpe 最強。
- A20 提高近期 final，並改善 worst-window final drag，同時維持 stress min-Sharpe 為正。

## 最新訊號與 Policy Decision

來源：

- Group A signal：`results/signal_group_a_20260617_230855.json`
- GroupA+ final signal：`results/group_a_plus_final_signal_a20_20260617.json`
- Policy signal：`results/group_a_plus_policy_signal_20260618_104659.json`
- Decision：`report/group_a_plus/decision/json/decision_focused_tdcc_0124_stab5_turn12_fast_cd3_20260618_104659.json`

結果：

| 項目 | 結果 |
|---|---:|
| actual data date | 2026-06-17 |
| review decision | approve |
| policy decision | approved |
| allowed_for_execution | true |
| policy cash_after_cost | 約 199,507 |
| 0050 target shares | 6,554 |
| 00631L target shares | 2,750 |
| 00632R target shares | 0 |
| 00679B target shares | 18 |

修正：

- `group_a_plus_decision_policy.py` 的 cash floor enforcement 已修正。舊邏輯在現金已足夠時仍可能把 risky assets 放大到 99%、現金壓到 1%；新邏輯會先檢查原始 target shares 的 cash_after_cost，若已達 required cash，就保留原始配置。

## Policy / Switch Backtest

來源：

- Policy backtest：`results/group_a_plus_policy_signal_backtest_a20_pipeline.json`
- Switch backtest：`results/group_a_plus_switch_policy_backtest_a20_pipeline.json`
- Switch sweep：`results/group_a_plus_switch_sweep_a20_20260618.json`

Policy signal backtest（2025-01-02 ~ 2026-06-17）：

| Variant | Final | Sharpe | MDD |
|---|---:|---:|---:|
| GroupA+ original | 1,603,654 | 2.050 | -15.72% |
| GroupA+ policy adjusted | 2,085,465 | 2.236 | -25.35% |
| Golden1 | 2,214,965 | 2.198 | -27.54% |

Switch sweep 最佳規則：

```text
switch_ma90_dd12_hold5_eg020_xg010
```

規則內容：

- 預設持有 Golden1。
- 0050 跌破 90 日均線 2%，或 90 日回撤達 -12%，切到 GroupA+ defensive。
- 至少持有 defensive 5 天。
- 0050 回到 90 日均線上方 1%，且 5 日動能轉正，切回 Golden1。

正式 switch backtest（2025-01-02 ~ 2026-06-17）：

| Variant | Final | Sharpe | MDD | Defense days | Switch count |
|---|---:|---:|---:|---:|---:|
| Golden1 | 2,214,965 | 2.198 | -27.54% | 0 | 0 |
| GroupA+ defensive | 2,085,465 | 2.236 | -25.35% | 351 | 0 |
| `switch_ma90_dd12_hold5_eg020_xg010` | 2,292,473 | 2.301 | -25.35% | 67 | 2 |

Switch events：

- 2025-02-27：切到 GroupA+ defensive，ma_gap -2.27%、drawdown -5.82%。
- 2025-06-09：切回 Golden1，ma_gap +1.62%、drawdown -8.74%。

解讀：

- 新 switch policy 同時保留 Golden1 的主要上行，並把 MDD 拉近 GroupA+ defensive。
- 這是目前 GroupA+ 外層最有價值的改善；但 864-grid sweep 有 overfit 風險，應先作為 promotion candidate，不直接視為 fully live default。
- 已將 `switch_ma90_dd12_hold5_eg020_xg010` 加入 `backtest_group_a_plus_switch_policy.py` 的正式候選規則。

## 決策

將 A20 升為新的 `group_a_plus_config.json` promotion candidate，並把 `switch_ma90_dd12_hold5_eg020_xg010` 作為外層 switch policy 的優先候選。

A20 final signal 已用 2026-06-17 最新本地資料重生，daily status 正常，review 與 policy decision 已通過。保守起見，A20 + switch policy 仍標示為 promotion candidate，原因是 switch 規則需要再做 walk-forward / 子期間驗證。

## 後續

1. 對 `switch_ma90_dd12_hold5_eg020_xg010` 做 walk-forward / 子期間驗證，降低 864-grid overfit 風險。
2. 下次資料刷新後，用 `run_group_a_plus_pipeline.py` 固定順序重跑 full pipeline，避免 latest pointer 污染。
3. 若 switch 規則跨期間穩定，再升級為 recommended default；否則維持 A20 defensive profile 作為已核准的 fallback。
