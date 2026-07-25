# Density Head Tail Risk Shadow 交接（2026-07-17）

## 來源

- PDF：`C:\Users\isaac\Downloads\2606.30037v1.pdf`
- 論文：`Heads, Not Backbones: Output Heads Dominate Architectures on Fat-Tailed Returns`
- arXiv：`2606.30037v1`

## 論文重點

這篇論文的核心不是交易策略，而是風險分布預測：

- 在 fat-tailed returns 上，output head 往往比 backbone architecture 更重要。
- Point head 對尾部風險不敏感。
- Gaussian / GMM density head 可改善 CRPS、pinball loss、coverage、VaR / ES 類風險指標。
- GMM 的價值主要出現在 crisis / high-volatility regime。
- 但論文也明確指出：naive trading strategy 會虧錢，distributional forecast 不等於 alpha。

## 本專案導入方式

本次沒有訓練新的 deep backbone，也沒有改 live 策略。

新增 research-only evaluator：

- `scripts/evaluate/evaluate_density_head_tail_risk_shadow.py`

設計：

- 既有 NCF panel 視為 point / backbone signal。
- 使用 `prob_up_h20` 與 `prob_magnitude` 建 point mean proxy：
  - `point_mu_h20 = (2 * prob_up_h20 - 1) * prob_magnitude`
- 在 walk-forward train fold 上估 residual distribution。
- 比較三種 head：
  - `point`：deterministic point forecast
  - `gaussian`：train residual Gaussian
  - `gmm`：train residual Gaussian mixture，預設 `K=4`

目的：

- 測試 density head 是否改善 00631L H20 tail calibration。
- 評估 risk-management value，不評估交易 alpha。

不做：

- 不接 `daily_signal.py`
- 不改 GroupA+ 最新策略權重
- 不改 `golden1_0531`
- 不做 no-add guard

## 評估指標

主要看 distributional / tail metrics：

- sample CRPS
- pinball loss：`q01 / q025 / q05 / q10 / q50 / q90 / q95`
- VaR breach rate：`1% / 2.5% / 5% / 10%`
- central coverage：`90% / 95% / 98%`
- expected shortfall proxy：`ES 2.5% / ES 5%`
- tail alert：用 train / global `q05` 的低分位數作風險背景訊號，檢查 adverse forward return 或 MDD。

## 主視窗結果

輸入 panel：

- `results/ncf_00631l_panel_latest_20260716.csv`

請注意：

- 指定日期是 `2025-01-02 ~ 2026-07-16`
- 但 H20 forward label 需要未來 20 個交易日
- 所以有效評估視窗是 `2025-01-02 ~ 2026-06-17`

| head | CRPS | q05 pinball | VaR 5% breach | central 90% coverage | tail alert precision | tail alert FPR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| point | 0.1735 | 0.0355 | 19.6% | 0.0% | 51.8% | 13.6% |
| Gaussian | 0.1232 | 0.0278 | 7.9% | 72.9% | 46.4% | 15.1% |
| GMM | 0.1664 | 0.0362 | 15.4% | 26.8% | 39.3% | 17.1% |

解讀：

- Gaussian residual head 明顯改善 CRPS、q05 pinball、VaR breach 與 coverage。
- GMM 沒有改善主視窗，甚至比 Gaussian 差。
- Tail alert precision 沒有因 Gaussian / GMM 改善，不能當 no-add guard。

## Crash / Stress Windows

### 2018 Correction

輸入 panel：

- `results/ncf_00631l_panel_backfill_2017_2019_20260710.csv`

有效視窗：

- `2018-01-02 ~ 2018-12-28`

| head | CRPS | q05 pinball | VaR 5% breach | central 90% coverage | tail alert precision | tail alert FPR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| point | 0.1807 | 0.1501 | 57.4% | 0.0% | 42.3% | 40.5% |
| Gaussian | 0.1413 | 0.0269 | 7.1% | 92.9% | 16.2% | 27.9% |
| GMM | 0.2696 | 0.0713 | 23.0% | 25.7% | 32.4% | 22.5% |

解讀：

- Gaussian residual head 對 tail calibration 很有幫助。
- GMM 在 2018 明顯不穩，CRPS 比 point 更差。
- Tail alert 不可用，Gaussian alert precision 太低。

### 2020 COVID

輸入 panel：

- `results/ncf_00631l_panel_backfill_2020_20260716.csv`

有效視窗：

- `2020-01-02 ~ 2020-06-30`

| head | CRPS | q05 pinball | VaR 5% breach | central 90% coverage | tail alert precision | tail alert FPR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| point | 0.1618 | 0.1068 | 56.3% | 0.0% | 27.8% | 21.0% |
| Gaussian | 0.1244 | 0.0517 | 21.8% | 75.9% | 11.1% | 25.8% |
| GMM | 0.2167 | 0.0648 | 29.9% | 27.6% | 11.1% | 25.8% |

解讀：

- Gaussian 比 point / GMM 都好，但 5% VaR breach 仍高達 21.8%，COVID 壓力期仍不足。
- GMM 仍不穩。
- Tail alert 不可用。

### 2026 Recent

輸入 panel：

- `results/ncf_00631l_panel_latest_20260716.csv`

有效視窗：

- `2026-01-02 ~ 2026-06-17`

| head | CRPS | q05 pinball | VaR 5% breach | central 90% coverage | tail alert precision | tail alert FPR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| point | 0.2275 | 0.0117 | 1.2% | 0.0% | 70.6% | 11.9% |
| Gaussian | 0.1892 | 0.0172 | 0.0% | 16.0% | 52.9% | 19.0% |
| GMM | 0.1026 | 0.0144 | 3.7% | 33.3% | 100.0% | 0.0% |

解讀：

- GMM 在 2026 recent 表現最好，但這是單一近端視窗。
- 2018 / 2020 不支持 GMM 穩定導入。
- 不能用 2026 recent 單段結果升級 live。

## 最終決策

不導入 live。

原因：

- 論文本身不是交易策略，且 naive trading strategy 失敗。
- 本專案 proxy 顯示 Gaussian residual head 有 tail calibration 研究價值，但 tail alert 不足以成為 guard。
- GMM 在主視窗、2018、2020 都不穩，只在 2026 recent 表現好。
- Density head 改善的是風險分布，不等於可交易 alpha。

可保留的研究價值：

- Gaussian residual head 可作 future tail calibration baseline。
- 評估指標應納入 CRPS、pinball、VaR breach、coverage，而不只看 AUC / precision。
- 若未來要升級，應做真正的 NCF density head retrain 或 GMM+EVT tail model，再做 walk-forward promotion review。

## 產物

- `scripts/evaluate/evaluate_density_head_tail_risk_shadow.py`
- `results/density_head_tail_risk_shadow_00631l_20250102_20260716.json`
- `results/density_head_tail_risk_shadow_00631l_20250102_20260716_predictions.csv`
- `results/density_head_tail_risk_shadow_00631l_2018_correction.json`
- `results/density_head_tail_risk_shadow_00631l_2018_correction_predictions.csv`
- `results/density_head_tail_risk_shadow_00631l_2020_covid.json`
- `results/density_head_tail_risk_shadow_00631l_2020_covid_predictions.csv`
- `results/density_head_tail_risk_shadow_00631l_2026_recent.json`
- `results/density_head_tail_risk_shadow_00631l_2026_recent_predictions.csv`

## 驗證命令

```bash
.venv/bin/python -m py_compile scripts/evaluate/evaluate_density_head_tail_risk_shadow.py
```

```bash
.venv/bin/python scripts/evaluate/evaluate_density_head_tail_risk_shadow.py --panel results/ncf_00631l_panel_latest_20260716.csv --start 2025-01-02 --end 2026-07-16 --output results/density_head_tail_risk_shadow_00631l_20250102_20260716.json
```

```bash
.venv/bin/python scripts/evaluate/evaluate_density_head_tail_risk_shadow.py --panel results/ncf_00631l_panel_backfill_2017_2019_20260710.csv --start 2018-01-02 --end 2018-12-31 --n-splits 3 --gap 20 --output results/density_head_tail_risk_shadow_00631l_2018_correction.json
.venv/bin/python scripts/evaluate/evaluate_density_head_tail_risk_shadow.py --panel results/ncf_00631l_panel_backfill_2020_20260716.csv --start 2020-01-02 --end 2020-06-30 --n-splits 3 --gap 20 --output results/density_head_tail_risk_shadow_00631l_2020_covid.json
.venv/bin/python scripts/evaluate/evaluate_density_head_tail_risk_shadow.py --panel results/ncf_00631l_panel_latest_20260716.csv --start 2026-01-02 --end 2026-07-16 --n-splits 3 --gap 20 --output results/density_head_tail_risk_shadow_00631l_2026_recent.json
```
