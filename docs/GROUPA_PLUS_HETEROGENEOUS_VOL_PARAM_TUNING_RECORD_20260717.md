# GroupA+ Heterogeneous Vol Param Tuning Record（2026-07-17）

## 背景

- 來源文件：`C:\Users\isaac\Downloads\2603.16035.pdf`
- 導入方向：只取 heterogeneous volatility / sparse regime / verification 概念，作為 GroupA+ research-only risk dashboard。
- 不作完整 SVAR-HMSH live model。

## 已完成最佳化

新增參數掃描：

- `scripts/evaluate/sweep_heterogeneous_vol_regime_params.py`

輸出：

- `results/heterogeneous_vol_regime_param_sweep_20250102_20260717.json`
- `results/heterogeneous_vol_regime_param_sweep_20250102_20260717_candidates.csv`

掃描範圍：

- `vol_window`: `10, 20, 30`
- `percentile_window`: `126, 252`
- `hetero_source_min_count`: `3, 4`
- `crisis_source_min_count`: `2, 3, 4, 5`

## 最佳候選

最佳 research-only 候選：

- `signal = sparse_crisis_active`
- `vol_window = 20`
- `percentile_window = 252`
- `crisis_source_min_count = 3`

對照原始設定：

| setting | active days | H10 precision | H10 recall | H10 FPR |
| --- | ---: | ---: | ---: | ---: |
| 原始：`crisis_source_min_count = 2` | 64 | 57.8% | 27.0% | 11.5% |
| 微調：`crisis_source_min_count = 3` | 61 | 59.0% | 26.3% | 10.6% |

## Stress Window 驗證

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

## 決策

保留微調結果，但只作 research advisory：

- 可作 7/20 manual review 背景。
- 不導入 live target weights。
- 不導入 execution guard。
- 不自動阻擋 rebalance。
- 不自動減碼或加碼 `00631L`。
- 不改 GroupA+ 最新策略。
- 不改 `Golden1_0531`。

實務建議：

- `crisis_source_min_count = 3` 可作較乾淨的人工 review 門檻。
- 7/20 若有 rebalance，建議人工確認；`00631L` 不自動加碼。

## 相關產物

- `docs/HETEROGENEOUS_VOL_REGIME_SHADOW_20260717.md`
- `scripts/evaluate/evaluate_heterogeneous_vol_regime_shadow.py`
- `scripts/evaluate/sweep_heterogeneous_vol_regime_params.py`
- `scripts/evaluate/build_heterogeneous_vol_regime_advisory.py`
- `report/group_a_plus/latest/heterogeneous_vol_regime_advisory.json`
