# Heterogeneous Vol Regime Shadow 交接（2026-07-17）

## 來源

- PDF：`C:\Users\isaac\Downloads\2603.16035.pdf`
- 論文：`Identification Verification for Structural Vector Autoregressions with Sparse Heterogeneous Markov Switching Heteroskedasticity`
- 作者 / 時間：Fei Shang、Tomasz Wozniak，2026-03

## 可導入優點

這篇不適合直接變成 0050 / 00631L 買賣規則，但有三個可導入到 GroupA+ research layer 的概念：

- **heterogeneous volatility process**：不同來源或衝擊應各自有波動 regime，不要強迫所有來源共用單一市場狀態。
- **sparse / overcomplete regime**：先允許較多 regime，再觀察哪些 regime 真的有樣本與訊號，不要只硬切 Calm / Crisis。
- **heteroskedasticity verification**：把來源拿來當風險背景前，先確認它真的出現可觀察的非恆定波動。

## 本專案導入方式

新增 research-only proxy：

- `scripts/evaluate/evaluate_heterogeneous_vol_regime_shadow.py`

邊界：

- 不接 `group_a_plus/operations/daily_signal.py`
- 不改 `target_weights`
- 不改 `golden1_0531`
- 不新增 live guard
- 只產生 shadow dashboard / research artifact

這不是完整 Bayesian SVAR-HMSH。原因：

- 原論文是 macro-financial SVAR identification，不是台股 ETF alpha model。
- 完整 MCMC / Markov-switching SVAR 導入成本高，且會增加 daily pipeline 依賴與維護風險。
- 對 GroupA+ 目前最有價值的是「來源層級波動健康檢查」，不是 structural shock impulse response。

## 實作摘要

來源：

| source | table | ticker |
| --- | --- | --- |
| `0050_local` | `ohlcv` | `0050.TW` |
| `00631l_levered` | `ohlcv` | `00631L.TW` |
| `00632r_inverse` | `ohlcv` | `00632R.TW` |
| `twii_market` | `external_market_ohlcv` | `^TWII` |
| `soxx_semiconductor` | `external_market_ohlcv` | `SOXX` |
| `qqq_growth` | `external_market_ohlcv` | `QQQ` |
| `tsm_adr` | `external_market_ohlcv` | `TSM` |
| `usdtwd_fx` | `external_market_ohlcv` | `TWD=X` |

外部來源使用嚴格時間對齊：

- 台灣日期 `d` 只使用 `source_dt < d` 的外部收盤資料。
- 避免同日美股資料 lookahead。

每個 source 獨立計算：

- 20 日 realized volatility
- 252 日 causal rolling percentile
- 5 個 overcomplete regimes：
  - `Dormant`：`<20%`
  - `Low`：`20%~40%`
  - `Normal`：`40%~70%`
  - `Elevated`：`70%~90%`
  - `Crisis`：`>=90%`
- `variance_ratio = recent_var_20d / long_var_252d`
- `heteroskedastic_active = variance_ratio >= 1.5 OR vol_percentile >= 85%`

source verification：

- 至少有 2 個非 Unknown active regimes
- `heteroskedastic_active_days >= 5`

Shadow signals：

| signal | 定義 |
| --- | --- |
| `heterogeneous_stress_active` | verified source stress count >= 3 且 heteroskedastic source count >= 3 |
| `sparse_crisis_active` | verified source crisis count >= 2 |
| `local_levered_stress_active` | 0050 與 00631L 同時 stress |

Forward label：

- H5 / H10
- `00631L` 相對 `0050` forward underperform `<= -1%`
- 或 `00631L` forward MDD `<= -5%`

## 主視窗結果

視窗：`2025-01-02 ~ 2026-07-17`

| signal | active days | H10 precision | H10 recall | H10 FPR |
| --- | ---: | ---: | ---: | ---: |
| `heterogeneous_stress_active` | 106 | 46.2% | 35.8% | 24.3% |
| `sparse_crisis_active` | 64 | 57.8% | 27.0% | 11.5% |
| `local_levered_stress_active` | 153 | 45.1% | 50.4% | 35.7% |

單一 source 觀察：

- `soxx_semiconductor`：H10 precision `49.7%`，recall `59.9%`，FPR `35.3%`
- `qqq_growth`：H10 precision `49.6%`，recall `46.7%`，FPR `27.7%`
- `usdtwd_fx`：H10 precision `31.3%`，偏弱

2026-07-17 latest snapshot：

- `heterogeneous_stress_count = 7`
- `heterogeneous_crisis_count = 5`
- `heteroskedastic_source_count = 6`
- `heterogeneous_stress_active = true`
- `sparse_crisis_active = true`

Latest source state：

| source | latest regime | vol percentile | variance ratio |
| --- | --- | ---: | ---: |
| `0050_local` | Elevated | 87.3% | 1.77 |
| `00631l_levered` | Crisis | 93.3% | 2.06 |
| `00632r_inverse` | Crisis | 92.1% | 2.10 |
| `twii_market` | Elevated | 70.6% | 1.22 |
| `soxx_semiconductor` | Crisis | 91.3% | 2.48 |
| `qqq_growth` | Crisis | 90.5% | 1.76 |
| `tsm_adr` | Crisis | 94.4% | 1.98 |
| `usdtwd_fx` | Dormant | 0.8% | 0.16 |

## Crash / Stress Window 結果

| window | signal | active days | H10 precision | H10 recall | H10 FPR |
| --- | --- | ---: | ---: | ---: | ---: |
| 2018 correction | `sparse_crisis_active` | 82 | 40.2% | 36.7% | 31.6% |
| 2020 COVID | `sparse_crisis_active` | 59 | 47.5% | 66.7% | 41.9% |
| 2022 rate-hike | `sparse_crisis_active` | 81 | 40.7% | 26.6% | 61.5% |
| 2026 recent | `sparse_crisis_active` | 29 | 72.4% | 67.7% | 57.1% |

解讀：

- 主視窗的 `sparse_crisis_active` 比寬鬆 stress 訊號乾淨，FPR 較低。
- 但 crash / stress windows 不穩，尤其 2020、2022、2026 recent 的 FPR 仍偏高。
- 2026 recent precision 高，部分是因近期下跌標籤密集，不能單獨作為 live promotion 證據。

## 最終決策

不導入 live。

保留為 research-only / dashboard：

- 可作 7/20 盤前人工 review 的 volatility background。
- 可和 SRR / QGMS / NCF warning 一起看，但不自動阻擋交易。
- 若未來要升級，必須先做 purged walk-forward ablation，並證明 FPR 明顯低於現有 volatility proxy。

## Walk-Forward Ablation 追加結果

追加腳本：

- `scripts/evaluate/evaluate_heterogeneous_vol_regime_walkforward_ablation.py`

視窗：

- `2018-01-02 ~ 2026-07-17`
- purged walk-forward
- `n_splits = 8`
- `test_size = 63`
- `purge = horizon`

H10 結果：

| feature set | AUC | AP | Brier delta vs base-rate | alert precision | alert recall | alert FPR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `local_sources` | 0.5892 | 0.4476 | +0.0026 | 47.2% | 36.8% | 28.0% |
| `rule_flags` | 0.5101 | 0.4657 | -0.0004 | 53.8% | 37.7% | 22.0% |
| `cross_market_sources` | 0.4845 | 0.4516 | +0.0097 | 59.8% | 24.0% | 11.0% |

H5 結果：

| feature set | AUC | AP | Brier delta vs base-rate | alert precision | alert recall | alert FPR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `local_sources` | 0.5494 | 0.3336 | +0.0379 | 34.0% | 31.6% | 28.0% |
| `all_heterogeneous_features` | 0.5382 | 0.3600 | +0.0343 | 34.8% | 25.3% | 21.7% |
| `cross_market_sources` | 0.5312 | 0.3741 | +0.0258 | 39.2% | 25.3% | 17.9% |

Walk-forward 解讀：

- H10 的 local volatility sources 有一點排序訊號，但 AUC 未達 0.60，且 Brier 比 base-rate 差。
- `cross_market_sources` 的 H10 alert FPR 較低，但 AUC 低於 0.50，不可解讀為穩定風險模型。
- H5 全部 feature set 都偏弱，校準明顯不佳。
- `promotion_decision = research_only`。

追加結論：

- 異質 source-vol regime 可作 dashboard。
- 不能升級為 no-add / reduce / execution guard。
- 若要再研究，下一步應做 threshold sweep 或和 SRR/QGMS 做 conditional review，而不是直接接 live。

## Conditional Overlap / Threshold Sweep 追加結果

追加腳本：

- `scripts/evaluate/evaluate_heterogeneous_vol_regime_conditional_overlap.py`

主視窗：

- `2025-01-02 ~ 2026-07-17`

Overlap 摘要：

| signal | active days | H10 precision | H10 recall | H10 FPR |
| --- | ---: | ---: | ---: | ---: |
| `sparse_crisis_active` | 64 | 57.8% | 27.0% | 11.5% |
| `SRR no_add` | 8 | 50.0% | 2.9% | 1.7% |
| `QGMS endpoint` | 8 | 87.5% | 5.1% | 0.4% |
| `hetero_sparse OR SRR no_add` | 69 | 56.5% | 28.5% | 12.8% |
| `hetero_sparse OR QGMS endpoint` | 72 | 61.1% | 32.1% | 11.9% |
| `hetero_sparse AND SRR no_add` | 3 | 66.7% | 1.5% | 0.4% |
| `hetero_sparse AND QGMS endpoint` | 0 | 無樣本 | 0.0% | 0.0% |

Threshold sweep：

| threshold signal | active days | H10 precision | H10 recall | H10 FPR |
| --- | ---: | ---: | ---: | ---: |
| `verified_crisis_count >= 3` | 61 | 59.0% | 26.3% | 10.6% |
| `verified_crisis_count >= 2` | 64 | 57.8% | 27.0% | 11.5% |
| `verified_crisis_count >= 4` | 46 | 50.0% | 16.8% | 9.8% |
| `verified_crisis_count >= 5` | 37 | 45.9% | 12.4% | 8.5% |

Conditional 解讀：

- `hetero_sparse OR QGMS endpoint` 是目前最像「人工 review dashboard」的組合：precision / recall 比單獨 sparse crisis 好一些，FPR 仍約 11.9%。
- `hetero_sparse AND SRR no_add` 樣本只有 3 天，不能作規則。
- `hetero_sparse AND QGMS endpoint` 沒有樣本，不能作 confirm。
- threshold 從 crisis count `>=2` 調到 `>=3` 有小幅改善，但不足以改變 live 結論。

追加決策：

- 可把 `sparse_crisis_active` 或 `verified_crisis_count >= 3` 當成人工 review 的背景欄位。
- 不接 execution guard。
- 不把 QGMS/SRR overlap 升級成自動 no-add。

## Parameter Sweep / 微調結果

追加腳本：

- `scripts/evaluate/sweep_heterogeneous_vol_regime_params.py`

掃描視窗：

- `2025-01-02 ~ 2026-07-17`

掃描範圍：

- `vol_window`：`10, 20, 30`
- `percentile_window`：`126, 252`
- `hetero_source_min_count`：`3, 4`
- `crisis_source_min_count`：`2, 3, 4, 5`
- label 維持：`00631L` 相對 `0050` H10 underperform `<= -1%` 或 H10 MDD `<= -5%`

H10 base event rate：

- `36.8%`

最佳 research 候選：

| signal | vol window | percentile window | crisis min | active days | latest active | H10 precision | H10 recall | H10 FPR |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| `sparse_crisis_active` | 20 | 252 | 3 | 61 | true | 59.0% | 26.3% | 10.6% |
| `sparse_crisis_active` | 30 | 252 | 2 | 63 | true | 58.7% | 27.0% | 11.1% |
| current `sparse_crisis_active` | 20 | 252 | 2 | 64 | true | 57.8% | 27.0% | 11.5% |

微調解讀：

- 可微調，但幅度不大。
- 最合理候選是維持 `vol_window=20`、`percentile_window=252`，只把人工 review 門檻從 `verified_crisis_count >= 2` 調成 `>= 3`。
- 這會讓 H10 precision 從 `57.8%` 升到 `59.0%`，FPR 從 `11.5%` 降到 `10.6%`，代價是 recall 從 `27.0%` 小降到 `26.3%`。
- 因為改善幅度小，且 walk-forward calibration 仍不足，結論仍是 research advisory，不升級 live guard。

Stress-window validation for `crisis_source_min_count = 3`：

| window | threshold | active days | H10 precision | H10 recall | H10 FPR |
| --- | --- | ---: | ---: | ---: | ---: |
| 2018 correction | `>=2` | 82 | 40.2% | 36.7% | 31.6% |
| 2018 correction | `>=3` | 67 | 38.8% | 28.9% | 26.5% |
| 2020 COVID | `>=2` | 59 | 47.5% | 66.7% | 41.9% |
| 2020 COVID | `>=3` | 58 | 48.3% | 66.7% | 40.5% |
| 2022 rate-hike | `>=2` | 81 | 40.7% | 26.6% | 61.5% |
| 2022 rate-hike | `>=3` | 64 | 35.9% | 18.5% | 52.6% |
| 2026 recent | `>=2` | 29 | 72.4% | 67.7% | 57.1% |
| 2026 recent | `>=3` | 28 | 75.0% | 67.7% | 50.0% |

Stress-window 解讀：

- `>=3` 通常會降低 active days 與 FPR。
- 但 2018、2022 的 precision / recall 變差，代表它不是穩定升級。
- 2026 recent precision 高，但 FPR 仍達 `50.0%`，不能作自動 no-add / reduce。
- 下一步若要改善，不應再單純調 threshold；應改成和 SRR / QGMS / NCF stale / institution stale 做「人工 review scorecard」。

## Latest Advisory Artifact

追加腳本：

- `scripts/evaluate/build_heterogeneous_vol_regime_advisory.py`

最新輸出：

- `report/group_a_plus/latest/heterogeneous_vol_regime_advisory.json`

2026-07-17 advisory snapshot：

- `policy = manual_review_only_no_weight_change`
- `active_allocation_impact = none`
- `level = high`
- `suggested_review = avoid_adding_00631l_until_manual_review`
- `verified_crisis_count = 5`
- `verified_stress_count = 7`
- `allow_auto_weight_change = false`
- `allow_execution_block = false`
- `allow_00631l_auto_reduce = false`
- `allow_00631l_auto_add = false`
- `param_sweep_best = sparse_crisis_active, vol_window=20, percentile_window=252, crisis_source_min_count=3`

Top stress sources:

| source | regime | vol percentile | variance ratio |
| --- | --- | ---: | ---: |
| `tsm_adr` | Crisis | 94.4% | 1.98 |
| `00631l_levered` | Crisis | 93.3% | 2.06 |
| `00632r_inverse` | Crisis | 92.1% | 2.10 |
| `soxx_semiconductor` | Crisis | 91.3% | 2.48 |
| `qqq_growth` | Crisis | 90.5% | 1.76 |
| `0050_local` | Elevated | 87.3% | 1.77 |

Live context captured from `live_signal_20260720_estimate.json`:

- requested as-of：`2026-07-20`
- actual data date：`2026-07-17`
- execution regime：`golden1`
- execution allowed：`false`
- target weights：`50% 0050 / 20% 00631L / 30% cash`

Interpretation:

- 這份 advisory 只提醒人工檢查 00631L 加碼 / rebalancing timing。
- 它不能自動減碼、不能自動阻擋下單、不能改 GroupA+ target weights。

## 產物

- `scripts/evaluate/evaluate_heterogeneous_vol_regime_shadow.py`
- `results/heterogeneous_vol_regime_shadow_20250102_20260717.json`
- `results/heterogeneous_vol_regime_shadow_20250102_20260717_frame.csv`
- `results/heterogeneous_vol_regime_shadow_2018_correction.json`
- `results/heterogeneous_vol_regime_shadow_2018_correction_frame.csv`
- `results/heterogeneous_vol_regime_shadow_2020_covid.json`
- `results/heterogeneous_vol_regime_shadow_2020_covid_frame.csv`
- `results/heterogeneous_vol_regime_shadow_2022_rate_hike.json`
- `results/heterogeneous_vol_regime_shadow_2022_rate_hike_frame.csv`
- `results/heterogeneous_vol_regime_shadow_2026_recent.json`
- `results/heterogeneous_vol_regime_shadow_2026_recent_frame.csv`
- `results/heterogeneous_vol_regime_walkforward_ablation_20180102_20260717_h10.json`
- `results/heterogeneous_vol_regime_walkforward_ablation_20180102_20260717_h10_predictions.csv`
- `results/heterogeneous_vol_regime_walkforward_ablation_20180102_20260717_h5.json`
- `results/heterogeneous_vol_regime_walkforward_ablation_20180102_20260717_h5_predictions.csv`
- `results/heterogeneous_vol_regime_conditional_overlap_20250102_20260717.json`
- `results/heterogeneous_vol_regime_conditional_overlap_20250102_20260717_frame.csv`
- `scripts/evaluate/build_heterogeneous_vol_regime_advisory.py`
- `report/group_a_plus/latest/heterogeneous_vol_regime_advisory.json`

## 重跑命令

```bash
.venv/bin/python scripts/evaluate/evaluate_heterogeneous_vol_regime_shadow.py \
  --start 2025-01-02 \
  --end 2026-07-17 \
  --output results/heterogeneous_vol_regime_shadow_20250102_20260717.json

.venv/bin/python scripts/evaluate/evaluate_heterogeneous_vol_regime_shadow.py \
  --start 2018-01-02 \
  --end 2018-12-31 \
  --output results/heterogeneous_vol_regime_shadow_2018_correction.json

.venv/bin/python scripts/evaluate/evaluate_heterogeneous_vol_regime_shadow.py \
  --start 2020-01-02 \
  --end 2020-06-30 \
  --output results/heterogeneous_vol_regime_shadow_2020_covid.json

.venv/bin/python scripts/evaluate/evaluate_heterogeneous_vol_regime_shadow.py \
  --start 2022-01-03 \
  --end 2022-10-31 \
  --output results/heterogeneous_vol_regime_shadow_2022_rate_hike.json

.venv/bin/python scripts/evaluate/evaluate_heterogeneous_vol_regime_shadow.py \
  --start 2026-05-15 \
  --end 2026-07-17 \
  --output results/heterogeneous_vol_regime_shadow_2026_recent.json

.venv/bin/python scripts/evaluate/evaluate_heterogeneous_vol_regime_walkforward_ablation.py \
  --start 2018-01-02 \
  --end 2026-07-17 \
  --horizon 10 \
  --output results/heterogeneous_vol_regime_walkforward_ablation_20180102_20260717_h10.json

.venv/bin/python scripts/evaluate/evaluate_heterogeneous_vol_regime_walkforward_ablation.py \
  --start 2018-01-02 \
  --end 2026-07-17 \
  --horizon 5 \
  --output results/heterogeneous_vol_regime_walkforward_ablation_20180102_20260717_h5.json

.venv/bin/python scripts/evaluate/evaluate_heterogeneous_vol_regime_conditional_overlap.py \
  --output results/heterogeneous_vol_regime_conditional_overlap_20250102_20260717.json

.venv/bin/python scripts/evaluate/sweep_heterogeneous_vol_regime_params.py \
  --output results/heterogeneous_vol_regime_param_sweep_20250102_20260717.json

.venv/bin/python scripts/evaluate/evaluate_heterogeneous_vol_regime_shadow.py \
  --start 2018-01-02 \
  --end 2018-12-31 \
  --crisis-source-min-count 3 \
  --output results/heterogeneous_vol_regime_shadow_2018_correction_crisis3.json

.venv/bin/python scripts/evaluate/evaluate_heterogeneous_vol_regime_shadow.py \
  --start 2020-01-02 \
  --end 2020-06-30 \
  --crisis-source-min-count 3 \
  --output results/heterogeneous_vol_regime_shadow_2020_covid_crisis3.json

.venv/bin/python scripts/evaluate/evaluate_heterogeneous_vol_regime_shadow.py \
  --start 2022-01-03 \
  --end 2022-10-31 \
  --crisis-source-min-count 3 \
  --output results/heterogeneous_vol_regime_shadow_2022_rate_hike_crisis3.json

.venv/bin/python scripts/evaluate/evaluate_heterogeneous_vol_regime_shadow.py \
  --start 2026-05-15 \
  --end 2026-07-17 \
  --crisis-source-min-count 3 \
  --output results/heterogeneous_vol_regime_shadow_2026_recent_crisis3.json

.venv/bin/python scripts/evaluate/build_heterogeneous_vol_regime_advisory.py \
  --output report/group_a_plus/latest/heterogeneous_vol_regime_advisory.json
```
