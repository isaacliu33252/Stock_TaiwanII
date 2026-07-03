# Group A+ A2118 Tiered Shadow 交接記錄 - 2026-06-29

## 0. 核心結論

本輪完成 A2118 最新策略治理修正、H=5 hold 測試補強、opportunity-cost label 分析，以及 tiered de-leverage shadow backtest。

**最終決策：不改 active strategy。**

現行 active 仍維持：

```json
{
  "id": "a2118_a2111_ncf_late_bull_deleverage",
  "runner": "group_a_plus.runners.a2118",
  "runner_params": {
    "ncf_panel_631l_path": "results/ncf_00631l_v5_tabnet_panel.csv",
    "h20_max": 0.33,
    "conf_min": 0.55,
    "h5_reentry_min": 0.55
  }
}
```

新發現的最佳 shadow candidate：

```text
gain_prob_soft_min = 0.30
soft_hedge_intensity = 0.25
```

它在完整 costed backtest 中小幅改善 Sharpe / Sortino / final value，但會讓今日 live 00631L 權重從約 5.3% 放寬到約 9.2%，風控明顯變鬆；樣本也只有兩段 hedge window，因此只保留 shadow，不升 production。

---

## 1. 本輪完成事項

| 項目 | 狀態 |
|------|------|
| 修正 latest manifest 測試，從 a2111 改為 a2118 | 完成 |
| 補 A2118 H=5 hold 單元測試 | 完成 |
| A2118 CLI 新增 `--h5-reentry-min` | 完成 |
| 重跑 latest runner，讓 `recent_result` 與 manifest 參數一致 | 完成 |
| 新增 opportunity-cost label 評估腳本 | 完成 |
| Recovery / rally-risk gate 初步掃描 | 完成 |
| Tiered de-leverage shadow 參數與回測 | 完成 |
| Hold exit 提早退出分析 | 完成 |

---

## 2. 重要檔案

### 修改或新增的程式

| 檔案 | 說明 |
|------|------|
| `group_a_plus/runners/a2118.py` | 新增 optional soft hedge regime / CLI 參數；預設關閉，不改 active 行為 |
| `tests/test_group_a_plus_latest_strategy.py` | latest manifest 測試改為檢查 active A2118 與 runner params |
| `tests/test_group_a_plus_ncf_integration.py` | 新增 A2118 H=5 hold 狀態機測試 |
| `scripts/evaluate/evaluate_group_a_plus_opportunity_cost.py` | 新增 opportunity-cost / recovery gate / tiered / hold-exit 分析腳本 |

### 產出檔案

| 檔案 | 說明 |
|------|------|
| `results/group_a_plus_runner_a2118.json` | 已重跑為 active A2118 v5 + h20=0.33 + h5_reentry=0.55 |
| `results/group_a_plus_runner_a2118_frame.csv` | active A2118 逐日 frame |
| `results/group_a_plus_opportunity_cost_a2118.json` | opportunity-cost 分析摘要 |
| `results/group_a_plus_opportunity_cost_a2118.csv` | opportunity-cost 逐日標籤資料 |
| `results/group_a_plus_runner_a2118_tiered_gain035_shadow.json` | tiered shadow 初版，gain>=0.35 soft intensity 0.5 |
| `results/group_a_plus_runner_a2118_tiered_gain035_shadow_frame.csv` | 上述 frame |
| `results/group_a_plus_runner_a2118_tiered_gain030_i025_shadow.json` | 最佳 shadow，gain>=0.30 soft intensity 0.25 |
| `results/group_a_plus_runner_a2118_tiered_gain030_i025_shadow_frame.csv` | 上述 frame |
| `results/group_a_plus_runner_a2118_tiered_gain_soft_sweep.json` | gain threshold x soft intensity 小掃描 |

注意：`results/*.json/csv` 多數未被 git 追蹤，但已實際寫在工作區。

---

## 3. Active A2118 重新對齊結果

重跑命令：

```bash
.venv/bin/python -m group_a_plus.runners.latest \
  --start 2025-01-02 \
  --end 2026-06-26 \
  --output results/group_a_plus_runner_a2118.json \
  --frame-output results/group_a_plus_runner_a2118_frame.csv
```

確認結果：

| 指標 | 數值 |
|------|------:|
| Final | 2,015,230 |
| 年化 | 60.64% |
| Sharpe | 2.43999 |
| Sortino | 2.67813 |
| MDD | -13.82% |
| 初始 trigger | 2 |
| hold days | 15 |
| total hedge days | 17 |

Trigger dates：

```text
2026-02-23
2026-04-30
```

---

## 4. 測試結果

執行：

```bash
.venv/bin/python -m pytest -q \
  tests/test_group_a_plus_latest_strategy.py \
  tests/test_group_a_plus_ncf_integration.py \
  -x
```

結果：

```text
67 passed in 2.05s
```

另有：

```bash
.venv/bin/python -m py_compile \
  group_a_plus/runners/a2118.py \
  scripts/evaluate/evaluate_group_a_plus_opportunity_cost.py
```

皆通過。

---

## 5. Opportunity-Cost Label 分析

新增腳本：

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_opportunity_cost.py
```

Label 定義：

```text
hedge_beats_base_20d = fwd_return_0050_20d > fwd_return_00631L_20d
```

因 A2118 的 hard hedge 是把一半 00631L 權重搬到 0050，所以這個 label 直接衡量「降 00631L 是否比維持 base 好」。

### 主要結果

| Slice | Rows | Labeled | Hedge win rate | Mean delta 20d |
|------|-----:|--------:|---------------:|---------------:|
| all_labeled | 357 | 337 | 23.15% | -0.198% |
| golden1 | 287 | 267 | 18.35% | -0.263% |
| late_bull_eligible | 196 | 176 | 18.18% | -0.246% |
| a2118_initial_trigger | 2 | 2 | 50.00% | -0.199% |
| a2118_hedge_execution_days | 17 | 17 | 47.06% | -0.038% |

解讀：

- 單看 20 日報酬，A2118 不是明確 alpha。
- A2118 更像風控 overlay：17 個 hedge days 的平均 forward MDD 為約 -10.27%，但平均報酬拖累只有 -0.038%。
- 因此不應把 A2118 解讀為純報酬增強策略。

---

## 6. Recovery / Rally-Risk Gate

A2118 兩個初始 trigger 的差異：

| 日期 | prob_fwd_gain_gt5_h20 | tail_reward_risk_score_h20 | 結果 |
|------|----------------------:|----------------------------:|------|
| 2026-02-23 | 0.253 | -0.608 | hedge 正貢獻 |
| 2026-04-30 | 0.430 | -0.379 | hedge 負貢獻 |

候選規則：

```text
Only allow hard hedge when prob_fwd_gain_gt5_h20 <= 0.35 or <= 0.40
```

效果：

| 規則 | Kept trigger | Suppressed | Win rate | Mean delta 20d |
|------|-------------:|-----------:|---------:|---------------:|
| current A2118 | 2 | 0 | 50% | -0.199% |
| gain_prob <= 0.35 | 1 | 1 | 100% | +0.267% |
| gain_prob <= 0.40 | 1 | 1 | 100% | +0.267% |

結論：

- 有改善訊號。
- 但只保留 1 筆樣本，不可升 production。
- 可作為 shadow diagnostic。

---

## 7. Tiered De-Leverage Shadow

### 7.1 新增 runner 可選參數

`group_a_plus/runners/a2118.py` 新增：

```bash
--gain-prob-soft-min
--soft-hedge-intensity
```

新增 soft regime：

```text
ncf_late_bull_hedge_soft
```

預設：

```text
gain_prob_soft_min = None
soft_hedge_intensity = 0.5
```

因 `gain_prob_soft_min=None`，預設完全不啟用 soft hedge，所以 active strategy 行為不變。

### 7.2 Soft hedge 權重

Current hard hedge：

```json
{
  "0050.TW": 0.7473586977537088,
  "00631L.TW": 0.05264130224629131,
  "cash": 0.20
}
```

最佳 shadow soft hedge，`soft_hedge_intensity=0.25`：

```json
{
  "0050.TW": 0.7078777210689903,
  "00631L.TW": 0.09212227893100977,
  "cash": 0.20
}
```

也就是只做 25% 強度降槓，而不是砍半 00631L。

### 7.3 掃描結果

掃描：

```text
gain_prob_soft_min in [0.30, 0.35, 0.40, 0.45]
soft_hedge_intensity in [0.25, 0.50, 0.75]
```

最佳：

```text
gain_prob_soft_min = 0.30
soft_hedge_intensity = 0.25
```

完整 costed backtest 對比：

| 指標 | Current A2118 | Tiered Shadow Best | 差異 |
|------|--------------:|-------------------:|-----:|
| Final | 2,015,230 | 2,019,938 | +4,708 |
| 年化 | 60.64% | 60.89% | +0.25pp |
| Sharpe | 2.43999 | 2.44630 | +0.00631 |
| Sortino | 2.67813 | 2.69723 | +0.01910 |
| MDD | -13.82% | -13.82% | 0 |
| Worst 20d | -9.47% | -9.47% | 0 |
| Transaction cost | 6,508 | 7,845 | +1,337 |
| Turnover | 2,920,753 | 3,471,488 | +550,735 |
| Rebalance count | 8 | 14 | +6 |

Regime count:

| Regime | Current | Tiered Shadow |
|--------|--------:|--------------:|
| golden1 | 270 | 270 |
| group_a_plus_defensive | 69 | 69 |
| ncf_late_bull_hedge | 17 | 7 |
| ncf_late_bull_hedge_soft | 0 | 10 |
| group_a_plus_recovery | 1 | 1 |

結論：

- Tiered shadow 在完整成本回測中確實改善。
- 改善幅度很小，但方向一致：Final / Sharpe / Sortino 均提升，MDD 不變。
- 成本與 rebalance 增加。
- 樣本仍太少，不升 active。

---

## 8. Live 影響

以目前 live NCF：

```text
prob_fwd_gain_gt5_h20 = 0.770988
```

若套用最佳 tiered shadow：

```text
gain_prob_soft_min = 0.30
soft_hedge_intensity = 0.25
```

會觸發 soft hedge。

Active current 目標：

```text
0050    74.7%
00631L   5.3%
cash    20.0%
```

Tiered shadow 目標：

```text
0050    70.8%
00631L   9.2%
cash    20.0%
```

這代表今日會明顯放鬆風控。雖然回測小幅改善，但 live 風險承擔變高，因此暫不升 production。

---

## 9. Hold Exit 提早退出分析

測試 profiles：

```text
exit_after_gain_prob >= 0.30 / 0.35 / 0.40 / 0.45
exit_after_h5_prob >= 0.35 / 0.40 / 0.45 / 0.50
```

最佳報酬 profile：

```text
exit_after_gain_prob >= 0.35 or 0.40
```

結果：

| Profile | Active days | Mean intensity | Mean delta 20d | Drawdown-day intensity |
|---------|------------:|---------------:|---------------:|-----------------------:|
| current_h5_exit | 17 | 1.00 | -0.038% | 1.00 |
| exit_after_gain_prob>=0.35 | 7 | 0.412 | +0.117% | 0.40 |
| exit_after_gain_prob>=0.40 | 7 | 0.412 | +0.117% | 0.40 |

結論：

- 報酬改善較大。
- 但 drawdown-day 保護強度降到 40%，削弱太多。
- 不建議優先採用。

---

## 10. 重跑命令

### Active A2118

```bash
.venv/bin/python -m group_a_plus.runners.latest \
  --start 2025-01-02 \
  --end 2026-06-26 \
  --output results/group_a_plus_runner_a2118.json \
  --frame-output results/group_a_plus_runner_a2118_frame.csv
```

### Opportunity-cost 分析

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_opportunity_cost.py
```

### Tiered shadow best

```bash
.venv/bin/python -m group_a_plus.runners.a2118 \
  --start 2025-01-02 \
  --end 2026-06-26 \
  --ncf-panel-631l results/ncf_00631l_v5_tabnet_panel.csv \
  --h20-max 0.33 \
  --conf-min 0.55 \
  --h5-reentry-min 0.55 \
  --gain-prob-soft-min 0.30 \
  --soft-hedge-intensity 0.25 \
  --output results/group_a_plus_runner_a2118_tiered_gain030_i025_shadow.json \
  --frame-output results/group_a_plus_runner_a2118_tiered_gain030_i025_shadow_frame.csv
```

### Tiered quick sweep

目前是用 inline Python 呼叫 `run_a2118()` 跑完，輸出：

```text
results/group_a_plus_runner_a2118_tiered_gain_soft_sweep.json
```

如要長期保留，建議下次把 sweep 也正式化成 script。

---

## 11. 後續建議

### Priority 1 - 保留 shadow，不改 active

Active 仍用：

```text
a2118 v5 + h20=0.33 + conf=0.55 + h5_reentry=0.55
```

Tiered candidate 只作 shadow：

```text
gain_prob_soft_min=0.30
soft_hedge_intensity=0.25
```

### Priority 2 - 每日產出 shadow 權重

每日 live signal 可同時輸出：

```text
active_target_weights
tiered_shadow_target_weights
prob_fwd_gain_gt5_h20
soft_hedge_triggered
```

先觀察 30-60 個交易日，不立即交易。

### Priority 3 - 若要升級，需要更嚴格 gate

升級條件建議：

```text
1. 至少新增 3-5 個 live/shadow hedge windows
2. Tiered shadow final / Sharpe / Sortino 持續優於 active
3. MDD / worst 20d 不惡化
4. 交易成本增加可接受
5. 00631L live 放寬不與人工風控判斷衝突
```

### Priority 4 - Formalize sweep script

目前 tiered sweep 是 inline Python。若要繼續研究，建議新增：

```text
scripts/evaluate/evaluate_group_a_plus_a2118_tiered_sweep.py
```

輸出固定欄位、固定 JSON schema，避免下次重跑難以比較。

---

## 12. 工作樹注意事項

工作樹本來已有大量未提交變更。本輪主要新增 / 修改：

```text
group_a_plus/runners/a2118.py
tests/test_group_a_plus_latest_strategy.py
tests/test_group_a_plus_ncf_integration.py
scripts/evaluate/evaluate_group_a_plus_opportunity_cost.py
GROUP_A_PLUS_A2118_TIERED_SHADOW_HANDOFF_20260629.md
```

另產生多個 `results/` 檔案。未對其他既有變更做 revert。

