# Multi-Scale Volatility Walk-Forward Ablation（2026-07-17）

## 目的

延續 `2606.06190v1.pdf` 的 multi-scale volatility regime 概念，檢查它是否對 00631L no-add 風險有 out-of-sample 增益。

這次是 research-only：

- 不接 live。
- 不改 `daily_signal.py`。
- 不改 GroupA+ 最新策略權重。
- 不改 `golden1_0531`。

## 新增腳本

- `scripts/evaluate/evaluate_multi_scale_vol_regime_walkforward_ablation.py`

輸出：

- `results/multi_scale_vol_regime_walkforward_ablation_20180102_20260716_h10.json`
- `results/multi_scale_vol_regime_walkforward_ablation_20180102_20260716_h10_predictions.csv`
- `results/multi_scale_vol_regime_walkforward_ablation_20180102_20260716_h5.json`
- `results/multi_scale_vol_regime_walkforward_ablation_20180102_20260716_h5_predictions.csv`

## 方法

資料視窗：

- `2018-01-02 ~ 2026-07-16`
- rows：2072

Validation：

- Purged walk-forward
- `n_splits = 8`
- `test_size = 63`
- `min_train_size = 252`
- purge = horizon

Label：

- H5 / H10 no-add risk
- `00631L` forward relative underperform vs `0050 <= -1%`
- 或 `00631L` forward MDD `<= -5%`

模型：

- Logistic regression
- `class_weight = balanced`
- `StandardScaler`

Feature sets：

| feature set | 內容 |
| --- | --- |
| `short_vol_only` | 5 日 volatility percentile |
| `medium_vol_only` | 20 日 volatility percentile |
| `long_vol_only` | 60 日 volatility percentile |
| `scale_percentiles` | 5/20/60 日 volatility percentile |
| `regime_codes` | 5/20/60 日 Calm/Turbulent/Crisis code |
| `uncertainty` | entropy、disagreement、crisis probability proxy |
| `signal_flags` | all_crisis、micro_shock、high_uncertainty 等布林訊號 |
| `all_vol_features` | 全部 volatility features |

Alert 評估：

- 每個 fold 使用 train prediction 的 80% quantile 作 alert threshold。
- 在 test fold 評估 precision / recall / FPR。

## H10 結果

Event rate：33.0%

| 排名 | feature set | AUC | AP | Brier delta vs base-rate | alert precision | alert recall | alert FPR |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | `medium_vol_only` | 0.5967 | 0.4767 | +0.0041 | 44.7% | 34.7% | 27.3% |
| 2 | `long_vol_only` | 0.5500 | 0.3913 | +0.0061 | 35.9% | 23.5% | 26.6% |
| 3 | `scale_percentiles` | 0.5374 | 0.3823 | +0.0090 | 36.5% | 21.4% | 23.7% |
| 4 | `short_vol_only` | 0.5332 | 0.4074 | +0.0075 | 41.0% | 28.1% | 25.6% |

Raw score：

| raw score | AUC | AP | active days | precision | recall | FPR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `crisis_probability_proxy` | 0.5393 | 0.3446 | 803 | 38.2% | 44.9% | 35.7% |
| `regime_entropy` | 0.5500 | 0.3556 | 1269 | 36.4% | 67.5% | 58.1% |
| `cross_scale_disagreement` | 0.5495 | 0.3542 | 1269 | 36.4% | 67.5% | 58.1% |
| `vol_no_add_active` | 0.5435 | 0.3527 | 694 | 38.8% | 39.3% | 30.6% |

解讀：

- `medium_vol_only` 是最好的 feature set，但 AUC 仍未達 0.60。
- Brier delta 為正，代表比 fold train base-rate 校準更差。
- alert FPR 27.3%，不適合作 no-add guard。

## H5 結果

Event rate：25.3%

| 排名 | feature set | AUC | AP | Brier delta vs base-rate | alert precision | alert recall | alert FPR |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | `medium_vol_only` | 0.5721 | 0.3769 | +0.0355 | 34.9% | 34.6% | 28.2% |
| 2 | `short_vol_only` | 0.5304 | 0.3249 | +0.0364 | 33.3% | 28.8% | 25.1% |
| 3 | `scale_percentiles` | 0.5198 | 0.2966 | +0.0386 | 28.0% | 27.5% | 30.8% |
| 4 | `long_vol_only` | 0.5091 | 0.2869 | +0.0378 | 24.2% | 20.3% | 27.6% |

Raw score：

| raw score | AUC | AP | active days | precision | recall | FPR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `crisis_probability_proxy` | 0.5380 | 0.2693 | 803 | 29.1% | 44.6% | 36.8% |
| `regime_entropy` | 0.5273 | 0.2655 | 1269 | 26.8% | 64.8% | 60.1% |
| `cross_scale_disagreement` | 0.5293 | 0.2666 | 1269 | 26.8% | 64.8% | 60.1% |
| `vol_no_add_active` | 0.5257 | 0.2642 | 694 | 28.2% | 37.3% | 32.2% |

解讀：

- H5 比 H10 更弱。
- 沒有任何 feature set 同時滿足排序、校準與低 FPR。

## 最終判斷

不要導入 live。

原因：

- 最佳 H10 AUC 只有 `0.5967`，未達穩健升級門檻。
- H5 / H10 的 Brier delta 都是正值，代表機率校準比 base-rate 更差。
- alert FPR 約 25% ~ 30%，不適合做 no-add 或 crash guard。
- 多特徵組合沒有勝過單一 `medium_vol_only`，代表複雜化沒有實質增益。

可保留的東西：

- `medium_vol_only` 可作為 future research feature。
- multi-scale regime 可以留在人工 review 的背景欄位，但不能阻擋交易。
- 若未來要再試，方向應是與既有 NCF / trend / drawdown features 做嚴格 ablation，而不是調 volatility threshold。

## 驗證命令

```bash
.venv/bin/python -m py_compile scripts/evaluate/evaluate_multi_scale_vol_regime_walkforward_ablation.py
```

```bash
.venv/bin/python scripts/evaluate/evaluate_multi_scale_vol_regime_walkforward_ablation.py --start 2018-01-02 --end 2026-07-16 --horizon 10 --output results/multi_scale_vol_regime_walkforward_ablation_20180102_20260716_h10.json
```

```bash
.venv/bin/python scripts/evaluate/evaluate_multi_scale_vol_regime_walkforward_ablation.py --start 2018-01-02 --end 2026-07-16 --horizon 5 --output results/multi_scale_vol_regime_walkforward_ablation_20180102_20260716_h5.json
```
