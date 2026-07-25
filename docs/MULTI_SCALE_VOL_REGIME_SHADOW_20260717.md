# Multi-Scale Volatility Regime Shadow 交接（2026-07-17）

## 來源

- PDF：`C:\Users\isaac\Downloads\2606.06190v1.pdf`
- 論文：`Multi-Scale Markov-Switching GARCH: Volatility Regime Detection in EUR/USD`
- 作者 / 時間：Jayesh Chaudhary，2026-05

## 論文可參考優點

這篇論文的重點不是單一技術指標，而是把波動 regime 拆成多尺度：

- 1D / 4H / 1H 三層 regime，共同判斷 Calm / Turbulent / Crisis。
- 使用 Markov-Switching GARCH 與 time-varying transition probabilities。
- 用 27 維 joint regime tensor 讓不同尺度的 regime 組合進入預測。
- 用 entropy filter 避免在 regime 不確定時過度交易。
- 論文回測顯示 volatility calibration 與 VaR conservative coverage 有改善。

## 本專案導入方式

本次沒有導入完整 MS-GARCH，也沒有改 live 策略。

原因：

- 完整 MS-GARCH / TVTP 實作成本高，且需 intraday 資料；目前 GroupA+ 主要資料與決策頻率是日頻。
- 論文標的是 EUR/USD，不是台股 ETF 或 00631L。
- 直接套用會有 coworker 環境、依賴與維護成本風險。

本次只新增透明代理版 shadow evaluator：

- 檔案：`scripts/evaluate/evaluate_multi_scale_vol_regime_shadow.py`
- 狀態：research-only
- 不接 `group_a_plus/operations/daily_signal.py`
- 不改 target weights
- 不改 `golden1_0531`

## 實作摘要

使用 00631L 日報酬估計 realized volatility：

| 尺度 | 視窗 | 對應概念 |
| --- | ---: | --- |
| short | 5 日 | micro shock proxy |
| medium | 20 日 | meso volatility proxy |
| long | 60 日 | macro stress proxy |

每個尺度使用 causal rolling percentile：

- `< 50%`：Calm
- `50% ~ 85%`：Turbulent
- `>= 85%`：Crisis

衍生 shadow signals：

| 訊號 | 定義 |
| --- | --- |
| `all_crisis_active` | 5/20/60 日全部 Crisis |
| `synchronized_turbulence_active` | 5/20/60 日全部至少 Turbulent |
| `micro_shock_active` | short Crisis，但 long 不是 Crisis |
| `macro_stress_divergence_active` | long Crisis，但 short Calm |
| `high_uncertainty_active` | 三尺度 regime entropy >= 0.95 |
| `vol_no_add_active` | `all_crisis_active OR synchronized_turbulence_active` |

Forward label：

- H5 / H10
- `00631L` 相對 `0050` forward underperform `<= -1%`
- 或 `00631L` forward MDD `<= -5%`

## 主視窗結果

視窗：`2025-01-02 ~ 2026-07-16`

| 訊號 | active days | H10 precision | H10 recall | H10 FPR | active H10 ret | active H10 rel vs 0050 | active H10 MDD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `vol_no_add_active` | 120 | 45.8% | 42.6% | 26.9% | +5.43% | +2.39% | -4.35% |
| `all_crisis_active` | 10 | 40.0% | 3.1% | 2.5% | +8.06% | +4.16% | -2.33% |
| `micro_shock_active` | 82 | 42.7% | 27.1% | 19.4% | +4.49% | +1.98% | -4.41% |
| `high_uncertainty_active` | 32 | 34.4% | 8.5% | 8.7% | +2.50% | +1.18% | -2.88% |

Brier skill proxy：

- event rate：19.7%
- Brier skill：`-0.1824`

解讀：

- `vol_no_add_active` 太寬，FPR 偏高。
- `all_crisis_active` 很稀疏，且在主視窗反而平均 forward return 偏正。
- regime proxy 不能直接當隔日高波動機率。

## Crash Window 結果

| 視窗 | 訊號 | active days | H10 precision | H10 recall | H10 FPR | active H10 ret | active H10 rel vs 0050 | active H10 MDD |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2018 correction | `vol_no_add_active` | 148 | 35.1% | 57.8% | 61.9% | +0.20% | +0.34% | -3.30% |
| 2018 correction | `micro_shock_active` | 21 | 52.4% | 12.2% | 6.5% | +0.05% | -0.14% | -2.24% |
| 2020 COVID | `vol_no_add_active` | 89 | 29.2% | 61.9% | 85.1% | +1.53% | +1.44% | -6.00% |
| 2020 COVID | `all_crisis_active` | 45 | 37.8% | 40.5% | 37.8% | +0.05% | +0.97% | -9.18% |
| 2022 rate-hike | `vol_no_add_active` | 101 | 59.4% | 48.4% | 52.6% | -2.53% | -0.90% | -6.38% |
| 2022 rate-hike | `micro_shock_active` | 41 | 61.0% | 20.2% | 20.5% | -3.58% | -1.43% | -7.57% |
| 2026 recent | `vol_no_add_active` | 81 | 51.9% | 79.2% | 52.0% | +5.04% | +2.07% | -4.44% |
| 2026 recent | `micro_shock_active` | 56 | 44.6% | 47.2% | 41.3% | +5.81% | +2.43% | -3.58% |

Brier skill proxy：

| 視窗 | Brier skill |
| --- | ---: |
| 2025-2026 main | -0.1824 |
| 2018 correction | -0.8682 |
| 2020 COVID | -0.5006 |
| 2022 rate-hike | -0.5212 |
| 2026 recent | -0.1145 |

解讀：

- 2022 壓力期的 `micro_shock_active` 比較像有用的風險背景特徵。
- 2020 的 `all_crisis_active` 可抓到部分壓力，但仍太慢、太寬，且不能作為乾淨 no-add 規則。
- 2026 recent 因 00631L 多數 forward return 偏正，volatility stress 不等於應減碼。

## 與既有 shadow overlap

主視窗：`2025-01-02 ~ 2026-07-16`

| 組合 | active days | H10 precision | H10 recall | H10 FPR |
| --- | ---: | ---: | ---: | ---: |
| `SRR no_add` | 8 | 50.0% | 3.1% | 1.7% |
| `vol OR SRR` | 124 | 46.0% | 44.2% | 27.7% |
| `vol AND SRR` | 4 | 50.0% | 1.6% | 0.8% |
| `QGMS endpoint` | 8 | 87.5% | 5.4% | 0.4% |
| `vol OR QGMS` | 121 | 46.3% | 43.4% | 26.9% |
| `vol AND QGMS` | 7 | 85.7% | 4.7% | 0.4% |
| `CSM HGB low prob` | 23 | 13.0% | 2.3% | 8.3% |
| `vol OR CSM` | 143 | 40.6% | 45.0% | 35.1% |
| `vol AND CSM` | 0 | 無樣本 | 0.0% | 0.0% |
| `cross-market no_add` | 1 | 0.0% | 0.0% | 0.4% |
| `vol AND cross-market` | 1 | 0.0% | 0.0% | 0.4% |

解讀：

- `vol_no_add_active` 跟 SRR union 後只會變寬，沒有提升 precision。
- `vol AND QGMS` 數字看起來不差，但樣本只有 7 天，且是 2025-2026 主視窗內，不能升級 live。
- CSM / cross-market overlap 沒提供可導入證據。

## 最終決策

不導入 live。

原因：

- 主 no-add proxy false positive rate 太高。
- Brier skill 全視窗為負，不能當高波動機率模型。
- crash windows 表現不穩，2022 有參考價值但 2018/2020/2026 不足以支持 live。
- 這是 realized-volatility percentile proxy，不是完整 MS-GARCH。

可保留的研究價值：

- 作為 future `volatility background regime feature`。
- 可在 SRR/QGMS 人工 review 報告中作背景說明，但不應阻擋交易。
- 若未來要升級，應先做 walk-forward feature ablation，而不是直接調門檻。

## Walk-Forward Ablation 追加結果

追加文件：

- `docs/MULTI_SCALE_VOL_REGIME_WALKFORWARD_ABLATION_20260717.md`

追加腳本：

- `scripts/evaluate/evaluate_multi_scale_vol_regime_walkforward_ablation.py`

視窗：

- `2018-01-02 ~ 2026-07-16`
- purged walk-forward
- `n_splits = 8`
- `test_size = 63`
- `purge = horizon`

H10 最佳：

- feature set：`medium_vol_only`
- AUC：`0.5967`
- AP：`0.4767`
- Brier delta vs base-rate：`+0.0041`
- alert precision：`44.7%`
- alert recall：`34.7%`
- alert FPR：`27.3%`

H5 最佳：

- feature set：`medium_vol_only`
- AUC：`0.5721`
- AP：`0.3769`
- Brier delta vs base-rate：`+0.0355`
- alert precision：`34.9%`
- alert recall：`34.6%`
- alert FPR：`28.2%`

追加結論：

- 20 日 volatility percentile 有一點排序訊號。
- 但 Brier delta 為正，代表校準比 base-rate 更差。
- alert FPR 仍高，不適合 live guard。
- 多尺度組合沒有勝過單一 20 日 volatility，暫時不值得複雜化。

## 產物

- `scripts/evaluate/evaluate_multi_scale_vol_regime_shadow.py`
- `scripts/evaluate/evaluate_multi_scale_vol_regime_walkforward_ablation.py`
- `results/multi_scale_vol_regime_shadow_20250102_20260716.json`
- `results/multi_scale_vol_regime_shadow_20250102_20260716_frame.csv`
- `results/multi_scale_vol_regime_shadow_2018_correction.json`
- `results/multi_scale_vol_regime_shadow_2018_correction_frame.csv`
- `results/multi_scale_vol_regime_shadow_2020_covid.json`
- `results/multi_scale_vol_regime_shadow_2020_covid_frame.csv`
- `results/multi_scale_vol_regime_shadow_2022_rate_hike.json`
- `results/multi_scale_vol_regime_shadow_2022_rate_hike_frame.csv`
- `results/multi_scale_vol_regime_shadow_2026_recent.json`
- `results/multi_scale_vol_regime_shadow_2026_recent_frame.csv`
- `results/multi_scale_vol_regime_walkforward_ablation_20180102_20260716_h10.json`
- `results/multi_scale_vol_regime_walkforward_ablation_20180102_20260716_h10_predictions.csv`
- `results/multi_scale_vol_regime_walkforward_ablation_20180102_20260716_h5.json`
- `results/multi_scale_vol_regime_walkforward_ablation_20180102_20260716_h5_predictions.csv`

## 驗證

```bash
.venv/bin/python -m py_compile scripts/evaluate/evaluate_multi_scale_vol_regime_shadow.py
```

```bash
.venv/bin/python scripts/evaluate/evaluate_multi_scale_vol_regime_shadow.py --start 2025-01-02 --end 2026-07-16 --overlap --output results/multi_scale_vol_regime_shadow_20250102_20260716.json
```

```bash
.venv/bin/python scripts/evaluate/evaluate_multi_scale_vol_regime_shadow.py --start 2018-01-02 --end 2018-12-31 --output results/multi_scale_vol_regime_shadow_2018_correction.json
.venv/bin/python scripts/evaluate/evaluate_multi_scale_vol_regime_shadow.py --start 2020-01-02 --end 2020-06-30 --output results/multi_scale_vol_regime_shadow_2020_covid.json
.venv/bin/python scripts/evaluate/evaluate_multi_scale_vol_regime_shadow.py --start 2022-01-03 --end 2022-10-31 --output results/multi_scale_vol_regime_shadow_2022_rate_hike.json
.venv/bin/python scripts/evaluate/evaluate_multi_scale_vol_regime_shadow.py --start 2026-01-02 --end 2026-07-16 --output results/multi_scale_vol_regime_shadow_2026_recent.json
```
