# GroupA+ PDF Research 導入審查（2026-07-17）

## 審查結論

未發現需要阻擋 coworker 使用本 project 的問題。

目前狀態可以保留：

- SRR-lite：live shadow alert，人工審核，不自動調倉。
- QGMS-lite：research-only，不接 live。
- CSM-lite：research-only，不接 live。
- Multi-scale volatility：research-only，不接 live。
- Density head tail risk：research-only，不接 live。
- CVaR tail-risk diagnostic：research-only，不接 live。
- Cross-market graph：research-only，不升級成自動交易規則。

最重要的邊界：

- 不改 `golden1_0531`。
- 不因六篇 PDF 改 GroupA+ 最新策略權重。
- 不讓 QGMS / CSM / multi-scale volatility / density head tail risk / CVaR tail-risk diagnostic 進 `daily_signal.py`。
- SRR-lite 即使進 live，也只進 alert/report，不改 `target_weights`。

## 審查範圍

Live / production path：

- `group_a_plus/operations/daily_signal.py`
- `group_a_plus/integrations/srr_lite_shadow.py`
- `group_a_plus/integrations/cross_market_graph_shadow.py`

Research evaluators：

- `scripts/evaluate/evaluate_qgms_lite_structural_endpoint_shadow.py`
- `scripts/evaluate/evaluate_qgms_srr_overlap_shadow.py`
- `scripts/evaluate/evaluate_csm_lite_00631l_shadow.py`
- `scripts/evaluate/evaluate_multi_scale_vol_regime_shadow.py`
- `scripts/evaluate/evaluate_multi_scale_vol_regime_walkforward_ablation.py`
- `scripts/evaluate/evaluate_density_head_tail_risk_shadow.py`
- `scripts/evaluate/evaluate_cvar_tail_risk_diagnostic_shadow.py`

Release / handoff：

- `results/group_a_release_Golden1_0531.json`
- `results/group_a_backtest_20250101_20260525_20260526_193252.json`
- `docs/FINAL_HANDOFF_GROUPA_PLUS_RESEARCH_20260717.md`
- `docs/QGMS_LITE_STRUCTURAL_ENDPOINT_SHADOW_20260717.md`
- `docs/CSM_LITE_00631L_SHADOW_20260717.md`
- `docs/MULTI_SCALE_VOL_REGIME_SHADOW_20260717.md`
- `docs/MULTI_SCALE_VOL_REGIME_WALKFORWARD_ABLATION_20260717.md`
- `docs/DENSITY_HEAD_TAIL_RISK_SHADOW_20260717.md`
- `docs/CVAR_TAIL_RISK_DIAGNOSTIC_SHADOW_20260717.md`

## Findings

### P0 / P1

無。

沒有看到會直接破壞 live pipeline、改 target weights、改 frozen release，或造成 coworker 無法繼續使用的問題。

### P2

無需立即修正。

目前 worktree 有大量既有 modified / untracked 檔案，這是研究與報告累積狀態。它不是 runtime bug，但交接時要提醒 coworker 不要直接清理 `results/`、`report/group_a_plus/latest/` 或 release manifest。

## Live 邊界檢查

### SRR-lite

檢查結果：通過。

證據：

- `group_a_plus/integrations/srr_lite_shadow.py` 回傳 `policy = shadow_only_no_weight_change`。
- 同一 payload 明確設定：
  - `allow_auto_weight_change = False`
  - `allow_crash_watch_auto_weight_change = False`
- `daily_signal.py` 只把 SRR-lite 放進 alert payload 與輸出欄位。

關鍵位置：

- `group_a_plus/integrations/srr_lite_shadow.py:168`
- `group_a_plus/integrations/srr_lite_shadow.py:181`
- `group_a_plus/integrations/srr_lite_shadow.py:182`
- `group_a_plus/operations/daily_signal.py:1267`
- `group_a_plus/operations/daily_signal.py:1291`
- `group_a_plus/operations/daily_signal.py:1634`
- `group_a_plus/operations/daily_signal.py:1746`

判斷：

- SRR-lite 不會自動改倉。
- SRR-lite no-add 只作人工 review。
- SRR-lite crash-watch 是 low-level hint，不阻擋交易。

### QGMS / CSM / Multi-scale volatility / Density head tail risk / CVaR tail-risk diagnostic

檢查結果：通過。

精準掃描結果顯示：

- QGMS 只出現在 `scripts/evaluate` 與 `docs`。
- CSM 只出現在 `scripts/evaluate` 與 `docs`。
- Multi-scale volatility 只出現在 `scripts/evaluate` 與 `docs`。
- Density head tail risk 只出現在 `scripts/evaluate` 與 `docs`。
- CVaR tail-risk diagnostic 只出現在 `scripts/evaluate` 與 `docs`。
- 以上 research-only evaluators 沒有 import 到 `group_a_plus/operations/daily_signal.py`。
- 以上 research-only evaluators 沒有接 live pipeline。

判斷：

- 不會影響 coworker 日常跑最新策略。
- 不會改 target weights。
- 不會改 daily signal output schema，除了 SRR-lite 已明確新增的 shadow 欄位。

### Cross-market graph

檢查結果：維持原先 research-only / shadow-only 邊界。

`daily_signal.py` 中 cross-market graph alert 文案明確寫：

- manual-review risk filter only
- does not change target weights

關鍵位置：

- `group_a_plus/operations/daily_signal.py:1243`
- `group_a_plus/operations/daily_signal.py:1251`
- `group_a_plus/integrations/cross_market_graph_shadow.py:95`

判斷：

- 不升級 live auto rule。
- 不改權重。

## Golden1_0531 檢查

檢查結果：通過。

`results/group_a_release_Golden1_0531.json` 仍顯示：

- `release_name = Golden1_0531`
- `release_date = 2026-05-31`
- `strategy_payload = results/group_a_backtest_20250101_20260525_20260526_193252.json`
- exposure caps：
  - `00631L.TW = 0.2`
  - `00632R.TW = 0.3`

總交接已明確記錄：

- `golden1_0531` 是 2026-05-31 release 的固定策略。
- 2026-07-17 以 frozen Golden1_0531 推估為 `50% 0050 / 20% 00631L / 30% cash`。

判斷：

- 沒有因 PDF 研究改 frozen release。
- 沒有把新研究訊號寫進 Golden1 release manifest。

## 文件一致性檢查

檢查結果：通過。

`docs/FINAL_HANDOFF_GROUPA_PLUS_RESEARCH_20260717.md` 已統一：

- 目前不要再把新研究訊號升級成自動交易規則。
- 維持現有 GroupA+ 最新策略權重，不因六篇 PDF 研究結果改動。
- QGMS / CSM / multi-scale volatility 不接 live。
- density head tail risk 不接 live。
- CVaR tail-risk diagnostic 不接 live。
- SRR-lite 只保留 live shadow alert。

關鍵位置：

- `docs/FINAL_HANDOFF_GROUPA_PLUS_RESEARCH_20260717.md:5`
- `docs/FINAL_HANDOFF_GROUPA_PLUS_RESEARCH_20260717.md:19`
- `docs/FINAL_HANDOFF_GROUPA_PLUS_RESEARCH_20260717.md:30`
- `docs/FINAL_HANDOFF_GROUPA_PLUS_RESEARCH_20260717.md:34`

## 相容性檢查

檢查結果：通過。

新增 research scripts 使用既有環境常見依賴：

- `duckdb`
- `numpy`
- `pandas`
- `sklearn`
- 既有 project module

沒有新增套件安裝需求。

已確認語法：

```bash
.venv/bin/python -m py_compile group_a_plus/integrations/srr_lite_shadow.py scripts/evaluate/evaluate_qgms_lite_structural_endpoint_shadow.py scripts/evaluate/evaluate_qgms_srr_overlap_shadow.py scripts/evaluate/evaluate_csm_lite_00631l_shadow.py scripts/evaluate/evaluate_multi_scale_vol_regime_shadow.py scripts/evaluate/evaluate_multi_scale_vol_regime_walkforward_ablation.py scripts/evaluate/evaluate_density_head_tail_risk_shadow.py scripts/evaluate/evaluate_cvar_tail_risk_diagnostic_shadow.py scripts/evaluate/evaluate_cross_market_graph_daily_scorecard.py scripts/evaluate/export_cross_market_graph_prediction_frame.py scripts/evaluate/sweep_cross_market_graph_daily_thresholds.py
```

已確認 JSON 可解析：

```bash
results/qgms_lite_structural_endpoint_shadow_20250102_20260716.json
results/csm_lite_00631l_shadow_20250102_20260716.json
results/multi_scale_vol_regime_shadow_20250102_20260716.json
results/multi_scale_vol_regime_walkforward_ablation_20180102_20260716_h10.json
results/density_head_tail_risk_shadow_00631l_20250102_20260716.json
results/cvar_tail_risk_diagnostic_shadow_20250102_20260716.json
results/group_a_release_Golden1_0531.json
```

已跑核心測試：

```bash
.venv/bin/python -m pytest tests/test_group_a_plus_srr_lite_shadow.py tests/test_leveraged_compounding_regime.py -q
```

結果：

```text
6 passed
```

## 不建議事項

不要做：

- 不要把 QGMS-lite 接進 `daily_signal.py`。
- 不要把 CSM-lite 接進 `daily_signal.py`。
- 不要把 multi-scale volatility 接進 `daily_signal.py`。
- 不要把 density head tail risk 接進 `daily_signal.py`。
- 不要把 CVaR tail-risk diagnostic 接進 `daily_signal.py`。
- 不要讓 SRR-lite 自動改 `target_weights`。
- 不要用單一 crash window 或單一 PDF 結果調參升級 live。
- 不要修改 `golden1_0531` frozen release。

## 後續可做

若要繼續，建議做：

- 將 SRR / QGMS / CSM / multi-scale volatility 整理成 daily report 的人工 review scorecard。
- scorecard 只顯示背景與風險提醒，不阻擋交易。
- 若要嘗試升級任何訊號，必須先跑獨立 walk-forward / out-of-sample / crash-window promotion review。

## 最終判定

本次 PDF research 導入審查通過。

可交接給 coworker 的安全狀態：

- live pipeline 可繼續使用。
- 最新策略權重不受六篇 PDF 影響。
- `golden1_0531` 保持 frozen。
- 新研究結果已留在 docs / scripts / results，不會自動介入交易。
