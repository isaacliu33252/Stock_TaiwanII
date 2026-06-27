# Group A+ TDCC 重啟交接記錄
日期：2026-06-12

## 已完成

### group_a_plus_config.json 修改

已啟用 TDCC overlay，更新內容：

```json
"dynamic_weight_bands": {
  "risk_on":  0.00,  // 牛市：不解發
  "caution": 0.02,   // 微觸發
  "risk_off": 0.05,  // 中度風險
  "severe":   0.08   // 顯著風險
},
"regime_stability_consecutive_days": 3
```

其他設定維持不變：
- 00631L 槓桿上限：risk_on 20%、caution 18%、risk_off/severe 0%
- Fast risk-off：enabled
- VIX / turbulence / second-stage：保持 disabled
- Bond sleeve：TDCC 動態啟用，risk_on 0%、caution 2%、risk_off 5%、severe 8%，需連續 3 天確認
- Execution：risk_on/caution turnover cap 100%，risk_off/severe turnover cap 12%

### 2026-06-12 focused sweep 更新

新增 12 組 `bands x stability_days` 測試：
- bands：`0/1/2/4%`、`0/2/3/5%`、`0/2/5/8%`
- stability_days：`0`、`2`、`3`、`5`

最佳結果：
- variant：`focused_tdcc_0258_stab3`
- Final：`2,233,527`
- Sharpe：`2.8699`
- MDD：`-16.33%`
- Vol：`21.45%`
- 相對 base approximation：Final `+25,560`、Sharpe `+0.1024`、MDD `+0.53pp`、Vol `-0.53pp`

輸出：
- `results/group_a_plus_focused_tdcc_stability_sweep_20260612.json`
- `results/group_a_plus_focused_tdcc_stability_sweep_20260612.csv`
- `results/group_a_plus_focused_tdcc_stability_sweep_20260612_curve.csv`

### 2026-06-12 execution turnover 更新

在 `focused_tdcc_0258_stab3` 上加測 risk_off/severe 單次換手上限：
- caps：`50%`、`35%`、`25%`、`15%`、`10%`

2025-2026 replay 最佳結果：
- variant：`focused_tdcc_0258_stab3_turn15`
- Final：`2,280,348`
- Sharpe：`2.9280`
- MDD：`-15.64%`
- Vol：`21.56%`
- 相對 base approximation：Final `+72,381`、Sharpe `+0.1605`、MDD `+1.22pp`、Vol `-0.42pp`

2008 stress-balanced 採用結果：
- variant：`focused_tdcc_0258_stab3_turn12`
- 2025-2026 replay：Final `2,278,160`、Sharpe `2.9156`、MDD `-15.77%`、Vol `21.63%`
- 相對 turn15：近期 Final 約少 `2,188`，但 2008 proxy Final `+4,452`、MDD `+0.53pp`、Sharpe `+0.0019`
- 正式 live default：risk_off/severe turnover cap `12%`

輸出：
- `results/group_a_plus_focused_execution_turnover_sweep_20260612.json`
- `results/group_a_plus_focused_execution_turnover_sweep_20260612.csv`
- `results/group_a_plus_focused_execution_turnover_sweep_20260612_curve.csv`
- `results/group_a_plus_focused_turnover_fine_sweep_20260612.json`
- `results/group_a_plus_focused_turnover_fine_sweep_20260612.csv`
- `results/group_a_plus_focused_stop_cooldown_sweep_20260612.json`
- `results/group_a_plus_focused_stop_cooldown_sweep_20260612.csv`
- `results/group_a_plus_2008_turnover_sweep_20260612.json`
- `results/group_a_plus_2008_turnover_sweep_20260612.csv`

### 2026-06-12 2008 proxy stress 測試

測試範圍：`2007-07-02 ~ 2010-12-31`，共 `873` rows。

目前 GroupA+ profile：`focused_tdcc_0258_stab3_turn12`

| Strategy | Mode | Final | Sharpe | MDD | Vol |
|---|---|---:|---:|---:|---:|
| Golden1_0531 | base | `1,494,399` | `0.5724` | `-38.02%` | `20.43%` |
| Golden1_0531 | GroupA+ current | `1,348,993` | `0.4774` | `-49.82%` | `24.33%` |
| latest production | base | `1,318,406` | `0.3757` | `-49.74%` | `22.95%` |
| latest production | GroupA+ current | `1,483,596` | `0.6824` | `-39.32%` | `19.49%` |

結論：
- latest production 加上目前 GroupA+ 後，2008 proxy 上比 latest base 明顯改善：Final `+165,189`、Sharpe `+0.3067`、MDD 約改善 `10.42pp`、Vol 降低約 `3.45pp`。
- latest GroupA+ 也優於 Golden1_0531 + GroupA+：Final `+134,603`、Sharpe `+0.2049`、MDD 約改善 `10.50pp`。
- Golden1_0531 base 仍有較高 Final，但目前 GroupA+ 的定位是降低 crisis path drawdown/volatility，不是單純追最高 Final。

輸出：
- `results/group_a_plus_golden1_vs_latest_twii_proxy_2008_20260612.json`
- `results/group_a_plus_golden1_vs_latest_twii_proxy_2008_20260612.csv`

限制：
- 這是 TWII-derived proxy，不是真實 ETF 2008 歷史。
- `00679B` 為合成 proxy，因為 2008 沒有真實 00679B 歷史。
- TDCC/法人/融資/LLM 等缺歷史資料的 feature 以 proxy 或 zero-fill 處理，只適合作為壓力測試，不可當精確歷史交易績效。

---

## 待配套調整（建議項目）

### 1. DCA 月金額（已測）
目前：5000/月 → 建議調高至 8000/月

TDCC 啟用後，risk_off 期間股息會再投入，相當於自動複利。增加 DCA 金額可以擴大這個效果。

2026-06-12 sensitivity 結果，使用目前 `focused_tdcc_0258_stab3_turn12`：

| 月 DCA | Final | Sharpe | MDD | Vol | DCA total | Contribution return |
|---:|---:|---:|---:|---:|---:|---:|
| `5,000` | `2,278,160` | `2.9156` | `-15.77%` | `21.63%` | `85,000` | `109.97%` |
| `8,000` | `2,370,192` | `3.0400` | `-15.02%` | `21.71%` | `136,000` | `108.64%` |
| `10,000` | `2,431,547` | `3.1175` | `-14.53%` | `21.78%` | `170,000` | `107.82%` |

判斷：
- `8,000/月` 是較平衡的資金計畫：Final、Sharpe、MDD 都比 `5,000/月` 好，資金效率只小幅下降。
- `10,000/月` 帳戶 Final 更高，但 contribution return 進一步被新增資金時點稀釋。
- 這是 capital policy，不是策略 alpha；績效比較時要看 contribution return，不只看 Final。

輸出：
- `results/group_a_plus_dca_5000_sensitivity_20260612.json`
- `results/group_a_plus_dca_8000_sensitivity_20260612.json`
- `results/group_a_plus_dca_10000_sensitivity_20260612.json`

改法：在產生 signal 的 payload 設定檔（`group_a_payload_hold10_candidate_*.json` 或類似）加入：
```json
"group_a_dca_config": {
  "dca_day": 20,
  "monthly_amounts": {"0050.TW": 8000.0}
}
```

### 2. Execution turnover 節流（已完成）
讓 TDCC 在 risk_off 時分批買入 00679B：
```json
"execution_control": {
  "max_turnover_ratio_by_regime": {
    "risk_on": 1.0,
    "caution": 1.0,
    "risk_off": 0.12,
    "severe": 0.12
  }
}
```

### 3. 00679B 初始持量確認
確認 config 中的 `default_current_shares: 10000` 與實際帳戶持有相符。

---

## TDCC 背景資料

### 回測數據（2024-01 至 2026-06）
| 指標 | 無 TDCC | 有 TDCC | 差異 |
|------|---------|---------|------|
| 年化報酬 | 64.25% | 61.05% | -3.2% |
| Sharpe | 2.073 | 2.179 | +0.106 |
| MDD | -28.15% | -26.42% | +1.72% |
| 交易次數 | 多 | 少 36 筆 | - |
| 手續費 | 高 | 節省 14,375 | - |

### TDCC 取捨邏輯
- 年化 -3.2% 原因：牛市高點再投資股息
- 價值在長期：TDCC 的核心價值是熊市期間保留現金/減少虧損，長期複利效果
- Isaac 接受短期代價換長期複利

### TDCC 生效原理
- `dynamic_weight_bands`：風險越高，系統將越多資金配置到 00679B（而非全部套牢在股票）
- `tdcc_state`（由 `_raw_tdcc_state` 計算）決定何時進場
- 實際買賣由 `backtest_group_a_plus_overlay.py` 的 `_group_a_plus_target()` + `signal_audit` 機制執行

---

## 關鍵檔案路徑

- Config：`/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/group_a_plus_config.json`
-  TDCC 回測結果：`results/group_a_tdcc_destination_primary_hold10_full_20240101_20260605.json`
-  回測脚本：`backtest_group_a_plus_overlay.py`
-  Signal 產生：`generate_dual_group_signal.py`
-  DCA 設定：`results/group_a_payload_hold10_candidate_20260605.json`

---

## 備註
- TDCC 目前使用 `reinvest_weights` 模式（股息於除息日立即按當前權重再投入）
- 00679B 的 `target_policy: static`，`reference_static_mix` 固定 20% 債
- 已啟用 `regime_stability_consecutive_days = 3`
- 已啟用 risk_off/severe `max_turnover_ratio = 0.12`
