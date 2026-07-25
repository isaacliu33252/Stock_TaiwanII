# 2606.30037 GroupA+ 導入審查（2026-07-17）

## PDF

- 檔案：`C:\Users\isaac\Downloads\2606.30037.pdf`
- 標題：`Heads, Not Backbones: Output Heads Dominate Architectures on Fat-Tailed Returns`
- 主題：fat-tailed return 的 density forecasting，重點是 output head 而不是 backbone。

## 論文重點

這篇不是交易策略，而是 tail-risk 分布預測研究。

核心結論：

- 在 fat-tailed return 上，output head 常比 backbone 更重要。
- Point head / Huber 對尾部風險不敏感。
- Gaussian / GMM density head 可改善 CRPS、pinball loss、coverage、VaR / ES 類風險指標。
- GMM 對 crisis / high-volatility regime 最有價值。
- 但論文也明確指出：naive trading strategy 會虧錢，distributional forecast 不等於 alpha。

## GroupA+ 已有導入

本專案已做 research-only shadow：

- `scripts/evaluate/evaluate_density_head_tail_risk_shadow.py`
- `docs/DENSITY_HEAD_TAIL_RISK_SHADOW_20260717.md`
- `results/density_head_tail_risk_shadow_00631l_20250102_20260716.json`

本次補上 latest advisory：

- `scripts/evaluate/build_density_head_tail_risk_advisory.py`
- `report/group_a_plus/latest/density_head_tail_risk_advisory.json`

本次追加參數掃描：

- `scripts/evaluate/sweep_density_head_tail_risk_params.py`
- `results/density_head_tail_risk_param_sweep_00631l_20250102_20260716.json`
- `results/density_head_tail_risk_param_sweep_00631l_20250102_20260716_rows.csv`

## 本專案實測結論

輸入：

- `results/ncf_00631l_panel_latest_20260716.csv`
- 評估 00631L H20 forward tail calibration。

主視窗有效評估：

- `2025-01-02 ~ 2026-06-17`

| head | CRPS | q05 pinball | VaR 5% breach | central 90% coverage |
| --- | ---: | ---: | ---: | ---: |
| point | 0.1735 | 0.0355 | 19.6% | 0.0% |
| Gaussian residual | 0.1232 | 0.0278 | 7.9% | 72.9% |
| GMM residual | 0.1664 | 0.0362 | 15.4% | 26.8% |

Best:

- `best_by_crps = gaussian`
- `best_by_pinball_q05 = gaussian`
- `recommended_research_baseline = gaussian_residual_head`

參數掃描：

- `gmm_components`: `2, 3, 4, 6, 8`
- `alert_quantile`: `0.10, 0.20, 0.30`
- `seed`: `42, 137`
- total rows: `30`

Win count：

- `gaussian_wins_crps = 30 / 30`
- `gaussian_wins_pinball_q05 = 30 / 30`
- `gmm_wins_crps = 0 / 30`
- `gmm_wins_pinball_q05 = 0 / 30`

最佳 GMM 候選：

- `gmm_components = 2`
- `alert_quantile = 0.10`
- `seed = 42`
- `gmm_crps = 0.1341`
- `gmm_pinball_q05 = 0.0294`
- `gmm_var05_breach_rate = 8.9%`
- `gmm_central90_coverage = 58.2%`

同組 Gaussian：

- `gaussian_crps = 0.1232`
- `gaussian_pinball_q05 = 0.0278`
- `gaussian_var05_breach_rate = 7.9%`
- `gaussian_central90_coverage = 72.9%`

微調結論：

- GMM 可微調，但無法打敗 Gaussian residual head。
- 目前最佳化後應固定 `gaussian_residual_head` 為 research baseline。
- GMM 不升級，不接 live，不作 no-add guard。

Crash-window 參數掃描：

| window | rows | Gaussian wins CRPS | Gaussian wins q05 pinball | GMM wins CRPS | GMM wins q05 pinball | best GMM K |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2018 correction | 30 | 30 | 30 | 0 | 0 | 2 |
| 2020 COVID | 30 | 30 | 30 | 0 | 0 | 2 |
| 2026 recent | 30 | 0 | 0 | 30 | 6 | 2 |

Crash-window 解讀：

- 2018 / 2020 兩個真正 crash/stress windows 都是 Gaussian residual head 全勝。
- 2026 recent 對 GMM 有利，但 q05 pinball 只贏 `6 / 30`，且樣本是單一近端 regime。
- 因此 GMM 更像近期 regime 特化，不是跨 crash 穩定最佳化。
- 最終 baseline 仍維持 `gaussian_residual_head`。

Stress-window summary:

- 2018 correction：Gaussian 明顯改善 tail calibration，GMM 不穩。
- 2020 COVID：Gaussian 比 point / GMM 好，但 5% VaR breach 仍偏高。
- 2026 recent：GMM 表現最好，但只是一段近端視窗，不足以升級 live。

## 可導入優點

### 1. 不急著換 backbone，先改善 output head / tail calibration

可導入。

GroupA+ 對應：

- 目前 NCF / TabNet backbone 已有大量 drift guard 與 validation。
- 2606.30037 支持先做 tail density head shadow，而不是另換深度 backbone。

導入層級：

- Yes：research diagnostic
- No：live model replacement

### 2. 評估指標加入 CRPS / pinball / coverage

可導入。

GroupA+ 對應：

- 對 00631L 這類 fat-tailed leveraged ETF，AUC / precision 不夠。
- Tail model 應補看：
  - CRPS
  - q05 pinball
  - VaR breach rate
  - central coverage
  - ES proxy

導入層級：

- Yes：model review / promotion gate
- No：單獨交易訊號

### 3. Gaussian residual head 可作目前 baseline

可導入。

本專案實測與參數掃描都顯示不是 GMM 勝出，而是 Gaussian residual head 更穩。

原因：

- GMM 在 2018 / 2020 / 主視窗不穩。
- 00631L panel 樣本量與 regime coverage 不足以支撐穩定 GMM。
- 30 組 GMM sweep 中，Gaussian 在 CRPS 與 q05 pinball 皆全勝。
- Crash-window sweep 也支持同一結論：2018 / 2020 Gaussian 全勝，2026 recent 的 GMM 優勢不能單獨升級 live。

導入層級：

- Yes：tail calibration baseline
- No：no-add guard

### 4. GMM / EVT 可列為下一階段研究

可保留。

但條件：

- 需要更長 walk-forward。
- 需要 GMM+EVT 或更穩定 tail model。
- 需要在 2018 / 2020 / 2022 / 2026 都通過。

## 不導入部分

不導入 live：

- 不改 GroupA+ target weights。
- 不改 `Golden1_0531`。
- 不把 density head advisory 接成 execution guard。
- 不把 GMM 當成 00631L 自動 no-add / reduce trigger。
- 不因這篇改 NCF backbone。

## 對最新策略的影響

目前最新策略：

- `a2118_a2111_ncf_late_bull_deleverage`
- NCF panel：`results/ncf_00631l_panel_latest_20260716.csv`
- 7/20 reference target：
  - `0050.TW = 50%`
  - `00631L.TW = 20%`
  - cash = `30%`

2606.30037 不支持直接改這些權重。

它支持的決策是：

- 將 density-head tail-risk 放入 research advisory。
- 用 Gaussian residual head 當目前 calibration baseline。
- 保留 7/20 manual review / no auto rebalance / no 00631L auto add。

## 最終決策

Production decision：

- No：不導入 live target weights。
- No：不導入 execution guard。
- No：不改 NCF backbone。
- No：不自動加減 `00631L`。
- Yes：保留 density-head tail-risk advisory。
- Yes：後續模型 promotion 應納入 CRPS / pinball / VaR coverage。
