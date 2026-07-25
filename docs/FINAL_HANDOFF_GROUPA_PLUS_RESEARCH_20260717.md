# GroupA+ 研究收尾總交接（2026-07-17）

## 最終決策

目前不要再把新研究訊號升級成自動交易規則。

可保留：

- `SRR-lite no_add_active`：live shadow alert，人工審核，不自動調倉。
- `SRR-lite crash_watch_active`：low-level live shadow alert，人工審核，不阻擋交易。
- `QGMS-lite structural endpoint`：research-only evaluator，可觀察 00631L 上漲腿末端，不接 live。
- `CSM-lite sign-on-magnitude`：research-only evaluator，可作為 magnitude regime / calibration 研究，不接 live。
- `multi-scale volatility regime`：research-only evaluator，可作 volatility background regime 研究，不接 live。
- `density head tail risk`：research-only evaluator，可作 00631L tail calibration 研究，不接 live。
- `CVaR tail-risk diagnostic`：research-only evaluator，可作 portfolio downside-risk table，不接 live。
- `cross-market directed graph`：research-only，不接 live alert。
- `SRR ensemble / QGMS overlap`：research-only，只作為交叉檢查。

不可做：

- 不要讓 SRR-lite、QGMS-lite、CSM-lite、multi-scale volatility、density head tail risk、CVaR tail-risk diagnostic、cross-market graph 直接改 target weights。
- 不要讓 QGMS-lite 作為 SRR-lite confirm，因為目前同日 overlap 為 0。
- 不要用 2026 年 5 月單段 QGMS 表現升級 live。
- 不要用 CSM-lite 的低 Brier 當成 no-add 訊號可用證據，因為 AUC 與 no-add precision 不支持。
- 不要用 multi-scale volatility 的高 recall 升級 live，因為 false positive rate 太高，Brier skill 全視窗為負。
- 不要用 density head 的 tail calibration 改善直接升級 live，因為 distributional forecast 不等於 alpha，且 GMM 跨視窗不穩。
- 不要用 CVaR optimizer 結果替代最新策略；`min_cvar` 會退化成現金，`tangency_cvar` 會大幅犧牲上行。
- 不要用 2022 單一年 cross-market 表現升級 live。

## 策略狀態

### 最新策略權重

維持現有 GroupA+ 最新策略權重，不因六篇 PDF 研究結果改動。

### Golden1_0531

`golden1_0531` 是 2026-05-31 release 的固定策略，不應隨時間改變。先前確認後的重點：

- release manifest：`results/group_a_release_Golden1_0531.json`
- 固定 release payload：`results/group_a_backtest_20250101_20260525_20260526_193252.json`
- 2026-07-17 以 frozen Golden1_0531 推估為 `50% 0050 / 20% 00631L / 30% cash`

## 已接 live shadow 的內容

### SRR-lite

主要檔案：

- `group_a_plus/integrations/srr_lite_shadow.py`
- `group_a_plus/operations/daily_signal.py`
- `tests/test_group_a_plus_srr_lite_shadow.py`

政策：

- `allow_auto_weight_change = False`
- `allow_crash_watch_auto_weight_change = False`
- 只提供人工 review 訊號。

條件：

- no-add：`score >= 0.65` 且 `density >= 0.65` 且 `velocity >= 0.18`
- crash-watch：`score >= 0.75` 且 `density >= 0.65`

## Research-only 內容

### Cross-market graph

主要檔案：

- `scripts/evaluate/evaluate_cross_market_directed_graph_shadow.py`
- `scripts/evaluate/export_cross_market_graph_prediction_frame.py`
- `scripts/evaluate/evaluate_cross_market_graph_daily_scorecard.py`
- `scripts/evaluate/sweep_cross_market_graph_daily_thresholds.py`

結論：

- 2022 有一定訊號品質。
- 2025 不觸發。
- 2026 唯一觸發是 false positive。
- threshold sweep 沒找到值得 live 升級的規則。

### QGMS-lite

來源 PDF：

- `C:\Users\isaac\Downloads\2511.16319v1.pdf`

主要檔案：

- `scripts/evaluate/evaluate_qgms_lite_structural_endpoint_shadow.py`
- `scripts/evaluate/evaluate_qgms_srr_overlap_shadow.py`
- `docs/QGMS_LITE_STRUCTURAL_ENDPOINT_SHADOW_20260717.md`

結論：

- 原始 QGMS 論文的核心 `Phi(Si)` 未公開，不能直接重現。
- 本專案只導入透明代理版，使用線上 swing confirmation，避免 lookahead。
- 2025-2026 主視窗 QGMS endpoint 10 日 precision 為 `87.5%`，但 recall 只有 `5.5%`。
- 2020 COVID precision 為 `0.0%`，2022 rate-hike 沒觸發。
- 不適合 live guard，只能作研究型人工 review 候選。

### QGMS 與 SRR overlap

主視窗 `2025-01-02 ~ 2026-07-16`：

| 訊號 | active days | H10 precision | H10 recall | H10 FPR |
| --- | ---: | ---: | ---: | ---: |
| SRR no-add | 8 | 50.0% | 3.1% | 1.65% |
| QGMS endpoint | 8 | 87.5% | 5.5% | 0.41% |
| SRR no-add OR QGMS endpoint | 16 | 68.8% | 8.6% | 2.06% |
| SRR no-add AND QGMS endpoint | 0 | 無樣本 | 0.0% | 0.0% |

解讀：

- QGMS 不是 SRR confirm。
- QGMS 是不同型態的補充訊號。
- 即使 union 指標較好，也仍不升級 live，因為跨 crash window 不穩。

### CSM-lite

來源 PDF：

- `C:\Users\isaac\Downloads\2606.04153v1.pdf`

主要檔案：

- `scripts/evaluate/evaluate_csm_lite_00631l_shadow.py`
- `docs/CSM_LITE_00631L_SHADOW_20260717.md`

可參考概念：

- 將報酬拆成 `sign` 與 `magnitude`。
- 用 predicted magnitude / volatility state 輔助 sign probability。
- 後續若要再研究，方向應是 `magnitude regime feature` 或 calibration，而不是獨立 no-add 訊號。

本次實測結論：

- 主視窗 `2025-01-02 ~ 2026-07-16`：既有 NCF baseline `prob_up_h20` AUC = `0.7992`。
- CSM-lite logistic AUC = `0.4963`，CSM-lite HGB AUC = `0.6018`，都未擊敗 baseline。
- CSM-lite HGB Brier 較低，但 AUC 差，不能視為 no-add 可用。
- 2018 correction、2020 stress、2026 recent crash-window 檢查均不支持 live 導入。
- 2022 rate-hike 未測，因為目前沒有 2022 對應的 00631L NCF backfill panel。

Crash-window 摘要：

| 視窗 | baseline AUC | CSM-lite logistic AUC | CSM-lite HGB AUC | no-add 結論 |
| --- | ---: | ---: | ---: | --- |
| 2018 correction | 0.5963 | 0.4182 | 0.4054 | logistic `prob<=0.45` precision 3.3%，平均 forward return +4.54% |
| 2020 stress | 0.5724 | 0.1931 | 0.0552 | logistic `prob<=0.45` precision 0.0%，平均 forward return +16.5% |
| 2026 recent | 無法計算 | 無法計算 | 無法計算 | 樣本幾乎全為正向；低機率日平均 forward return 仍為正 |

最終決策：

- CSM-lite 不接 `daily_signal.py`。
- 不新增 live alert。
- 不做 no-add guard。
- 不改 target weights。

### Multi-scale volatility regime

來源 PDF：

- `C:\Users\isaac\Downloads\2606.06190v1.pdf`

主要檔案：

- `scripts/evaluate/evaluate_multi_scale_vol_regime_shadow.py`
- `scripts/evaluate/evaluate_multi_scale_vol_regime_walkforward_ablation.py`
- `docs/MULTI_SCALE_VOL_REGIME_SHADOW_20260717.md`
- `docs/MULTI_SCALE_VOL_REGIME_WALKFORWARD_ABLATION_20260717.md`

可參考概念：

- 將 volatility regime 拆成多尺度，而不是只看單一短期波動。
- 使用 regime entropy / cross-scale disagreement 表示不確定性。
- 把 Crisis / Turbulent / Calm 當成背景狀態，而不是直接交易訊號。

本次實作：

- 沒有導入完整 MS-GARCH / TVTP。
- 使用 00631L 5/20/60 日 realized volatility rolling percentile 代理 Calm / Turbulent / Crisis。
- 產生 `all_crisis_active`、`micro_shock_active`、`high_uncertainty_active`、`vol_no_add_active` 等 shadow 訊號。

主視窗 `2025-01-02 ~ 2026-07-16`：

- `vol_no_add_active`：active days 120，H10 precision `45.8%`，recall `42.6%`，FPR `26.9%`。
- `all_crisis_active`：active days 10，H10 precision `40.0%`，recall `3.1%`，FPR `2.5%`。
- Brier skill proxy：`-0.1824`。

Crash-window 摘要：

| 視窗 | 代表訊號 | H10 precision | H10 recall | H10 FPR | 解讀 |
| --- | --- | ---: | ---: | ---: | --- |
| 2018 correction | `vol_no_add_active` | 35.1% | 57.8% | 61.9% | 太寬 |
| 2020 COVID | `all_crisis_active` | 37.8% | 40.5% | 37.8% | 可抓壓力但不乾淨 |
| 2022 rate-hike | `micro_shock_active` | 61.0% | 20.2% | 20.5% | 有研究參考價值 |
| 2026 recent | `vol_no_add_active` | 51.9% | 79.2% | 52.0% | 高 recall 但 FPR 高，且 forward return 偏正 |

Overlap 摘要：

- `vol OR SRR`：H10 precision `46.0%`，FPR `27.7%`，沒有改善 SRR。
- `vol AND QGMS`：H10 precision `85.7%`，但只有 7 天樣本，不能升級 live。
- `vol AND CSM`：0 天樣本。
- `vol AND cross-market`：1 天且 false positive。

Walk-forward ablation：

- 視窗：`2018-01-02 ~ 2026-07-16`
- validation：purged walk-forward，`n_splits=8`，`test_size=63`，`purge=horizon`
- H10 最佳 feature set：`medium_vol_only`
- H10 AUC：`0.5967`，AP：`0.4767`，Brier delta vs base-rate：`+0.0041`
- H10 alert precision：`44.7%`，recall：`34.7%`，FPR：`27.3%`
- H5 最佳 feature set：`medium_vol_only`
- H5 AUC：`0.5721`，AP：`0.3769`，Brier delta vs base-rate：`+0.0355`
- H5 alert precision：`34.9%`，recall：`34.6%`，FPR：`28.2%`

Walk-forward 解讀：

- 20 日 volatility percentile 有一點排序訊號。
- 但校準不佳，Brier 比 fold train base-rate 更差。
- 多尺度組合沒有勝過單一 20 日 volatility。
- 不足以升級 live guard。

最終決策：

- 不接 `daily_signal.py`。
- 不新增 live alert。
- 不做 no-add guard。
- 不改 target weights。
- 可保留為未來 volatility background regime feature 的研究基礎。

### Density head tail risk

來源 PDF：

- `C:\Users\isaac\Downloads\2606.30037v1.pdf`

主要檔案：

- `scripts/evaluate/evaluate_density_head_tail_risk_shadow.py`
- `docs/DENSITY_HEAD_TAIL_RISK_SHADOW_20260717.md`

可參考概念：

- 對 fat-tailed returns，風險模型應評估 predictive distribution，而不是只看 point / direction。
- Gaussian / GMM density head 可改善 CRPS、pinball loss、VaR coverage、central interval coverage。
- Distributional forecast 是 risk-management 工具，不等於 alpha。

本次實作：

- 沒有訓練 deep backbone。
- 使用既有 00631L NCF panel 作 point/backbone proxy。
- `point_mu_h20 = (2 * prob_up_h20 - 1) * prob_magnitude`
- 比較 `point`、`Gaussian residual head`、`GMM residual head`。

主視窗 `2025-01-02 ~ 2026-07-16`：

- 因 H20 forward label，實際有效評估到 `2026-06-17`。
- Gaussian CRPS `0.1232`，優於 point `0.1735` 與 GMM `0.1664`。
- Gaussian q05 pinball `0.0278`，優於 point `0.0355` 與 GMM `0.0362`。
- Gaussian VaR 5% breach `7.9%`，較 point `19.6%` 改善，但仍高於理想 5%。
- GMM 主視窗不佳。

Crash-window 摘要：

| 視窗 | 最佳分布 head | 重點 |
| --- | --- | --- |
| 2018 correction | Gaussian | CRPS `0.1413`、q05 pinball `0.0269`、coverage 92.9%；GMM CRPS 比 point 更差 |
| 2020 COVID | Gaussian | CRPS `0.1244`、q05 pinball `0.0517`，但 VaR 5% breach 仍 21.8% |
| 2026 recent | GMM | CRPS `0.1026`，VaR 5% breach 3.7%，但只是單一近端視窗 |

最終決策：

- 不接 `daily_signal.py`。
- 不新增 live alert。
- 不做 no-add guard。
- 不改 target weights。
- Gaussian residual head 可保留為 tail calibration baseline。
- GMM 不穩，不作導入候選。

### CVaR tail-risk diagnostic

來源 PDF：

- `C:\Users\isaac\Downloads\2607.03082v1.pdf`

主要檔案：

- `scripts/evaluate/evaluate_cvar_tail_risk_diagnostic_shadow.py`
- `docs/CVAR_TAIL_RISK_DIAGNOSTIC_SHADOW_20260717.md`

可參考概念：

- portfolio review 不應只看 Sharpe / return，也要看 VaR、ES、MDD、Hill、POT-GPD。
- CVaR 類配置可降低 downside risk，但常犧牲 upside。
- Long-short 與高 turnover optimizer 不適合直接導入 GroupA+。

本次實作：

- 只測 `0050.TW`、`00631L.TW`、`cash`。
- long-only / cash allowed。
- `00631L <= 20%`。
- rolling lookback 252、每 21 個交易日 rebalance、交易成本 10 bps proxy。

主視窗 `2025-01-02 ~ 2026-07-16`：

| strategy | ann return | MDD | ES95 | STARR95 |
| --- | ---: | ---: | ---: | ---: |
| `0050_only` | 69.5% | -28.5% | 3.49% | 19.88 |
| `golden1_frozen_proxy_50_20_30` | 56.6% | -25.9% | 3.26% | 17.34 |
| `00631l_only` | 129.8% | -50.2% | 7.64% | 16.99 |
| `dynamic_tangency_cvar_net_cost10bps` | 14.6% | -11.0% | 1.73% | 8.45 |
| `dynamic_min_cvar_net_cost10bps` | 0.0% | 0.0% | 0.0% | 無 |

Crash-window 摘要：

- 2018 / 2020 / 2022：`dynamic_tangency_cvar` 大幅降低 MDD 與 ES，但報酬接近 0 或負值。
- 2026 recent：`dynamic_tangency_cvar` 風險很低，但大幅落後 00631L 與 Golden1 proxy 的上行。
- `dynamic_min_cvar` 退化成現金，不能作策略替代。

最終決策：

- 不接 `daily_signal.py`。
- 不新增 live alert。
- 不做 optimizer promotion。
- 不改 target weights。
- 可保留為 portfolio-level tail-risk review table。

## 重要文件索引

總結與交接：

- `docs/FINAL_HANDOFF_GROUPA_PLUS_RESEARCH_20260717.md`
- `docs/REVIEW_GROUPA_PLUS_PDF_RESEARCH_20260717.md`
- `docs/FINAL_HANDOFF_SRR_LITE_CROSS_MARKET_20260717.md`
- `docs/QGMS_LITE_STRUCTURAL_ENDPOINT_SHADOW_20260717.md`
- `docs/CSM_LITE_00631L_SHADOW_20260717.md`
- `docs/MULTI_SCALE_VOL_REGIME_SHADOW_20260717.md`
- `docs/MULTI_SCALE_VOL_REGIME_WALKFORWARD_ABLATION_20260717.md`
- `docs/DENSITY_HEAD_TAIL_RISK_SHADOW_20260717.md`
- `docs/CVAR_TAIL_RISK_DIAGNOSTIC_SHADOW_20260717.md`

SRR：

- `docs/CHANGELOG_20260716_SRR_LITE_SHADOW.md`
- `docs/SRR_LITE_CRASH_WINDOW_BACKTEST_20260716.md`
- `docs/SRR_LITE_ENSEMBLE_SHADOW_20260716.md`
- `docs/HANDOFF_SRR_LITE_SHADOW_20260716.md`

Cross-market：

- `docs/CROSS_MARKET_GRAPH_DAILY_SCORECARD_20260716.md`

相容性 / coworker：

- `docs/OPERATIONS.md`
- `docs/ARTIFACT_POLICY.md`
- `docs/CHANGELOG_20260716_COMPAT_CLEANUP.md`

## 主要 results artifact

SRR：

- `results/srr_lite_shadow_backtest_20250102_20260716_tuned.json`
- `results/srr_lite_shadow_backtest_20250102_20260716_tuned_frame.csv`
- `results/srr_lite_shadow_crash_2020_covid_20200102_20200630.json`
- `results/srr_lite_shadow_crash_2022_rate_hike_20220103_20221031.json`
- `results/srr_lite_shadow_crash_2026_recent_20260515_20260716.json`

Cross-market：

- `results/cross_market_directed_graph_shadow_prediction_frame_full_20260716.json`
- `results/cross_market_directed_graph_shadow_prediction_frame_full_20260716.csv`
- `results/cross_market_graph_daily_scorecard_20260716.json`
- `results/cross_market_graph_threshold_sweep_20260716.json`

QGMS：

- `results/qgms_lite_structural_endpoint_shadow_20250102_20260716.json`
- `results/qgms_lite_structural_endpoint_shadow_20250102_20260716_frame.csv`
- `results/qgms_lite_structural_endpoint_shadow_2020_crash.json`
- `results/qgms_lite_structural_endpoint_shadow_2022_rate_hike.json`
- `results/qgms_lite_structural_endpoint_shadow_2026_recent.json`
- `results/qgms_srr_overlap_shadow_20250102_20260716.json`
- `results/qgms_srr_overlap_shadow_2026_recent.json`
- `results/qgms_srr_overlap_shadow_2020_covid.json`
- `results/qgms_srr_overlap_shadow_2022_rate_hike.json`

CSM-lite：

- `results/csm_lite_00631l_shadow_20250102_20260716.json`
- `results/csm_lite_00631l_shadow_20250102_20260716_frame.csv`
- `results/csm_lite_00631l_shadow_20250102_20260716_with_baseline.json`
- `results/csm_lite_00631l_shadow_2018_correction.json`
- `results/csm_lite_00631l_shadow_2020_backfill.json`
- `results/csm_lite_00631l_shadow_2026_recent.json`

Multi-scale volatility：

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

Density head tail risk：

- `results/density_head_tail_risk_shadow_00631l_20250102_20260716.json`
- `results/density_head_tail_risk_shadow_00631l_20250102_20260716_predictions.csv`
- `results/density_head_tail_risk_shadow_00631l_2018_correction.json`
- `results/density_head_tail_risk_shadow_00631l_2018_correction_predictions.csv`
- `results/density_head_tail_risk_shadow_00631l_2020_covid.json`
- `results/density_head_tail_risk_shadow_00631l_2020_covid_predictions.csv`
- `results/density_head_tail_risk_shadow_00631l_2026_recent.json`
- `results/density_head_tail_risk_shadow_00631l_2026_recent_predictions.csv`

CVaR tail-risk diagnostic：

- `results/cvar_tail_risk_diagnostic_shadow_20250102_20260716.json`
- `results/cvar_tail_risk_diagnostic_shadow_20250102_20260716_returns.csv`
- `results/cvar_tail_risk_diagnostic_shadow_20250102_20260716_allocations.csv`
- `results/cvar_tail_risk_diagnostic_shadow_2018_correction.json`
- `results/cvar_tail_risk_diagnostic_shadow_2020_covid.json`
- `results/cvar_tail_risk_diagnostic_shadow_2022_rate_hike.json`
- `results/cvar_tail_risk_diagnostic_shadow_2026_recent.json`

## 驗證命令

核心測試：

```bash
.venv/bin/python -m pytest tests/test_group_a_plus_srr_lite_shadow.py tests/test_leveraged_compounding_regime.py -q
```

腳本語法：

```bash
.venv/bin/python -m py_compile scripts/evaluate/evaluate_qgms_lite_structural_endpoint_shadow.py scripts/evaluate/evaluate_qgms_srr_overlap_shadow.py scripts/evaluate/evaluate_srr_lite_shadow.py scripts/evaluate/evaluate_srr_lite_ensemble_shadow.py scripts/evaluate/evaluate_cross_market_graph_daily_scorecard.py scripts/evaluate/sweep_cross_market_graph_daily_thresholds.py scripts/evaluate/export_cross_market_graph_prediction_frame.py
```

CSM-lite 語法：

```bash
.venv/bin/python -m py_compile scripts/evaluate/evaluate_csm_lite_00631l_shadow.py
```

Multi-scale volatility 語法：

```bash
.venv/bin/python -m py_compile scripts/evaluate/evaluate_multi_scale_vol_regime_shadow.py
```

Multi-scale volatility walk-forward ablation 語法：

```bash
.venv/bin/python -m py_compile scripts/evaluate/evaluate_multi_scale_vol_regime_walkforward_ablation.py
```

Density head tail risk 語法：

```bash
.venv/bin/python -m py_compile scripts/evaluate/evaluate_density_head_tail_risk_shadow.py
```

CVaR tail-risk diagnostic 語法：

```bash
.venv/bin/python -m py_compile scripts/evaluate/evaluate_cvar_tail_risk_diagnostic_shadow.py
```

QGMS 主視窗：

```bash
.venv/bin/python scripts/evaluate/evaluate_qgms_lite_structural_endpoint_shadow.py --start 2025-01-02 --end 2026-07-16 --output results/qgms_lite_structural_endpoint_shadow_20250102_20260716.json
```

QGMS / SRR overlap：

```bash
.venv/bin/python scripts/evaluate/evaluate_qgms_srr_overlap_shadow.py --srr-frame results/srr_lite_shadow_backtest_20250102_20260716_tuned_frame.csv --qgms-frame results/qgms_lite_structural_endpoint_shadow_20250102_20260716_frame.csv --output results/qgms_srr_overlap_shadow_20250102_20260716.json
```

CSM-lite 主視窗：

```bash
.venv/bin/python scripts/evaluate/evaluate_csm_lite_00631l_shadow.py --output results/csm_lite_00631l_shadow_20250102_20260716.json
```

Multi-scale volatility 主視窗：

```bash
.venv/bin/python scripts/evaluate/evaluate_multi_scale_vol_regime_shadow.py --start 2025-01-02 --end 2026-07-16 --overlap --output results/multi_scale_vol_regime_shadow_20250102_20260716.json
```

Multi-scale volatility walk-forward ablation：

```bash
.venv/bin/python scripts/evaluate/evaluate_multi_scale_vol_regime_walkforward_ablation.py --start 2018-01-02 --end 2026-07-16 --horizon 10 --output results/multi_scale_vol_regime_walkforward_ablation_20180102_20260716_h10.json
.venv/bin/python scripts/evaluate/evaluate_multi_scale_vol_regime_walkforward_ablation.py --start 2018-01-02 --end 2026-07-16 --horizon 5 --output results/multi_scale_vol_regime_walkforward_ablation_20180102_20260716_h5.json
```

Density head tail risk 主視窗：

```bash
.venv/bin/python scripts/evaluate/evaluate_density_head_tail_risk_shadow.py --panel results/ncf_00631l_panel_latest_20260716.csv --start 2025-01-02 --end 2026-07-16 --output results/density_head_tail_risk_shadow_00631l_20250102_20260716.json
```

CVaR tail-risk diagnostic 主視窗：

```bash
.venv/bin/python scripts/evaluate/evaluate_cvar_tail_risk_diagnostic_shadow.py --start 2025-01-02 --end 2026-07-16 --output results/cvar_tail_risk_diagnostic_shadow_20250102_20260716.json
```

## 給下一位接手者

目前最重要的是維持邊界：

- SRR-lite 可以留在 live shadow，因為它已經是人工 review 且不改權重。
- QGMS-lite、CSM-lite、multi-scale volatility、density head tail risk、CVaR tail-risk diagnostic 和 cross-market graph 不要接 live。
- 若要再研究，先做 walk-forward / out-of-sample，而不是調門檻追求單一視窗最佳。
- 若要清理 results，先依 `docs/ARTIFACT_POLICY.md` 區分必要報告、可重生報告與 daily pipeline 產物，不要直接刪除 latest pointer 或 release manifest。
