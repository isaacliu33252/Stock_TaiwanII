# GroupA+ External Sensitivity Observation 交接記錄（2026-07-22）

本文件記錄 2026-07-22 這輪 GroupA+ 最新策略治理改善。重點是把 NCF panel drift 的 external-feature sensitivity blocker 從「硬編碼觀察次數」改成「可累積、可查核的 observation log」，並接進 daily pipeline、panel drift progress、final governance snapshot。

## 最高優先邊界

- `golden1_0531` 是舊 release 策略，不能修改。
- 本輪沒有修改 `golden1_0531` release 策略。
- 本輪沒有放行下單。
- 本輪沒有允許 target weight change。
- 本輪沒有允許 auto rebalance。
- 本輪沒有允許 PPO/model training。
- 本輪沒有允許 promotion to live。
- 本輪沒有允許新增 00631L。
- 本輪沒有允許開 00632R。
- 本輪只改「最新 GroupA+ governance / shadow / report pipeline」。

## 目前最新決策狀態

截至本輪完成後：

- `as_of`: `2026-07-23`
- `actual_data_date`: `2026-07-22`
- promotion decision: `blocked_model_gates_manual_approval_pending`
- true model hard blockers: `panel_drift`, `multi_window`
- deployment consistency gate: `pass`
- manual approval: still pending
- `golden1_0531`: unchanged

最新 final snapshot：

- `report/group_a_plus/latest/final_governance_snapshot.json`
- `report/group_a_plus/latest/final_governance_snapshot.md`

## 本輪新增的核心機制

### 1. External sensitivity observation log

新增腳本：

- `scripts/evaluate/build_group_a_plus_external_sensitivity_observation_log.py`

新增測試：

- `tests/test_build_group_a_plus_external_sensitivity_observation_log.py`

功能：

- 讀取 same-method external sensitivity audit。
- 讀取 same-method baseline manifest。
- 將每日 observation append / upsert 到 latest log。
- 以 `(observation_date, sensitivity_audit)` 作為 upsert key，避免同一天同檔重複累加。
- 計算：
  - `observation_count`
  - `valid_observation_count`
  - `stable_observation_count`
  - `latest_observation_date`
  - `latest_trigger_critical_exceeded`
- 明確輸出 decision boundary，全部保持 diagnostic-only。

輸出：

- `report/group_a_plus/latest/external_sensitivity_observation_log.json`
- `report/group_a_plus/latest/external_sensitivity_observation_log.md`
- `report/group_a_plus/external_sensitivity_observation_log/history/external_sensitivity_observation_log_YYYYMMDD.json`

目前 2026-07-22 實際結果：

```json
{
  "observation_count": 1,
  "valid_observation_count": 1,
  "stable_observation_count": 0,
  "latest_observation_date": "2026-07-22",
  "latest_trigger_critical_exceeded": ["h20_prob_up", "confidence"]
}
```

解讀：

- 今天已有 1 次有效觀察。
- 但不是 stable observation。
- `h20_prob_up` 與 `confidence` 仍超過 trigger-critical limit。
- external sensitivity blocker 不可解除。

### 2. External feature sensitivity governance 改成讀 log

修改腳本：

- `scripts/evaluate/build_ncf_panel_external_feature_sensitivity_governance.py`

修改測試：

- `tests/test_build_ncf_panel_external_feature_sensitivity_governance.py`

新增/修改重點：

- `build_report()` 新增 `observation_log` 參數。
- CLI 新增 `--observation-log`。
- 有 observation log 時，使用 log summary 計算完成次數。
- 沒有 observation log 時，保留舊相容行為：有 sensitivity audit 則視為完成 1 次。
- 新增 stable observation gate：
  - required stable sessions: `3`
  - 必須 `stable_observation_sessions >= 3`
  - 必須 latest sensitivity 不再 trigger-critical exceeded
  - 必須 same-method baseline manifest valid
  - 必須 remediation action 仍存在，才能 `resolution_allowed = true`
- 即使 `external_sensitivity_blocker_resolved = true`，仍不代表 promotion allowed；promotion 還要看其他 gates。

目前 2026-07-22 governance 結果：

```json
{
  "required_observation_sessions": 3,
  "completed_observation_sessions": 1,
  "remaining_observation_sessions": 2,
  "stable_observation_sessions": 0,
  "remaining_stable_observation_sessions": 3,
  "latest_trigger_critical_exceeded": ["h20_prob_up", "confidence"],
  "resolution_allowed": false,
  "reason": "external-feature sensitivity exceeds trigger-critical limits"
}
```

目前 status：

- `blocked_observation_required`

### 3. Daily pipeline 接入 observation log

修改腳本：

- `scripts/run/run_ncf_daily_pipeline.py`

修改測試：

- `tests/test_run_ncf_daily_pipeline.py`

新增 pipeline step：

- `external_sensitivity_observation_log`

插入位置：

1. `ncf_panel_drift_remediation_plan_initial`
2. `external_sensitivity_observation_log`
3. `ncf_panel_external_feature_sensitivity_governance`
4. `ncf_panel_drift_remediation_plan`
5. `panel_drift_resolution_progress`

新增 command 行為：

- 使用當天 `ncf_panel_drift_no_external_vs_external_{stamp}.json`
- 使用當天 `ncf_panel_same_method_baseline_manifest_{stamp}.json`
- `--observation-date` 使用 `date_stamp` 轉成 `YYYY-MM-DD`
- `--existing-log` 指向 latest observation log
- output 指向 latest observation log

governance command 現在會傳：

- `--observation-log report/group_a_plus/latest/external_sensitivity_observation_log.json`

manifest outputs 新增：

- `external_sensitivity_observation_log`

已補進本次 outputs-only manifest：

- `results/ncf_daily_pipeline_20260722.json`

注意：`results/ncf_daily_pipeline_20260722.json` 目前是 `mode = governance_final_outputs_only`、`status = backfilled_outputs_only`。這不代表完整 pipeline 重新跑過；只代表已記錄現有 final governance/reporting outputs。

### 4. Panel drift resolution progress 顯示 stable observation 還差幾次

修改腳本：

- `scripts/evaluate/build_group_a_plus_panel_drift_resolution_progress.py`

修改測試：

- `tests/test_build_group_a_plus_panel_drift_resolution_progress.py`

新增欄位：

- `stable_observation_sessions`
- `remaining_stable_observation_sessions`

目前最新 progress：

```json
{
  "status": "blocked",
  "unresolved_action_ids": ["quantify_external_feature_sensitivity"],
  "remaining_observation_sessions": 2,
  "remaining_stable_observation_sessions": 3
}
```

目前 next actions 文字已修正為：

- `complete 3 additional stable same-method external-sensitivity observation session(s)`

原因：解除 blocker 的條件不是「再跑 2 次有效觀察」而是「累積 3 次 stable observation」。目前 stable 是 0/3。

### 5. Final governance snapshot 納入 observation log 摘要

修改腳本：

- `scripts/evaluate/build_group_a_plus_final_governance_snapshot.py`

修改測試：

- `tests/test_build_group_a_plus_final_governance_snapshot.py`

新增 CLI：

- `--external-sensitivity-observation-log`

新增 snapshot 欄位：

- `external_sensitivity_observation_log.observation_count`
- `external_sensitivity_observation_log.valid_observation_count`
- `external_sensitivity_observation_log.stable_observation_count`
- `external_sensitivity_observation_log.latest_observation_date`
- `external_sensitivity_observation_log.latest_trigger_critical_exceeded`
- `panel_drift_resolution_progress.remaining_stable_observation_sessions`

目前 final snapshot 摘要：

```json
{
  "promotion_decision": "blocked_model_gates_manual_approval_pending",
  "panel_drift_resolution_progress": {
    "status": "blocked",
    "unresolved_action_ids": ["quantify_external_feature_sensitivity"],
    "remaining_observation_sessions": 2,
    "remaining_stable_observation_sessions": 3,
    "external_sensitivity_status": "blocked_observation_required"
  },
  "external_sensitivity_observation_log": {
    "observation_count": 1,
    "valid_observation_count": 1,
    "stable_observation_count": 0,
    "latest_observation_date": "2026-07-22",
    "latest_trigger_critical_exceeded": ["h20_prob_up", "confidence"]
  }
}
```

## 本輪實際重建的 outputs

本輪已用 2026-07-22 既有最新資料重建：

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_external_sensitivity_observation_log.py \
  --sensitivity-audit results/ncf_panel_drift_no_external_vs_external_20260722.json \
  --same-method-baseline-manifest results/ncf_panel_same_method_baseline_manifest_20260722.json \
  --observation-date 2026-07-22 \
  --existing-log report/group_a_plus/latest/external_sensitivity_observation_log.json \
  --output report/group_a_plus/latest/external_sensitivity_observation_log.json \
  --output-md report/group_a_plus/latest/external_sensitivity_observation_log.md
```

```bash
.venv/bin/python scripts/evaluate/build_ncf_panel_external_feature_sensitivity_governance.py \
  --sensitivity-audit results/ncf_panel_drift_no_external_vs_external_20260722.json \
  --same-method-baseline-manifest results/ncf_panel_same_method_baseline_manifest_20260722.json \
  --remediation-plan results/ncf_panel_drift_remediation_plan_initial_20260722.json \
  --observation-log report/group_a_plus/latest/external_sensitivity_observation_log.json \
  --allow-missing-sensitivity-audit \
  --output results/ncf_panel_external_feature_sensitivity_governance_20260722.json
```

```bash
.venv/bin/python scripts/evaluate/build_ncf_panel_drift_remediation_plan.py \
  --diagnosis results/ncf_panel_drift_diagnosis_20260722.json \
  --model-set-isolation-report results/ncf_panel_drift_model_set_isolation_report_20260722.json \
  --same-method-baseline-manifest results/ncf_panel_same_method_baseline_manifest_20260722.json \
  --external-sensitivity-governance results/ncf_panel_external_feature_sensitivity_governance_20260722.json \
  --output results/ncf_panel_drift_remediation_plan_20260722.json
```

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_panel_drift_resolution_progress.py \
  --remediation-plan results/ncf_panel_drift_remediation_plan_20260722.json \
  --external-sensitivity-governance results/ncf_panel_external_feature_sensitivity_governance_20260722.json \
  --output report/group_a_plus/latest/panel_drift_resolution_progress.json \
  --output-md report/group_a_plus/latest/panel_drift_resolution_progress.md
```

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_final_governance_snapshot.py \
  --daily-status report/group_a_plus/latest/daily_status.json \
  --ops-health report/group_a_plus/latest/ops_health.json \
  --promotion-gate results/group_a_plus_promotion_gate_20260722.json \
  --promotion-blocked-diagnostic report/group_a_plus/latest/promotion_blocked_diagnostic.json \
  --multi-window-failure-attribution report/group_a_plus/latest/multi_window_failure_attribution.json \
  --panel-drift-triage report/group_a_plus/latest/panel_drift_triage.json \
  --panel-drift-resolution-progress report/group_a_plus/latest/panel_drift_resolution_progress.json \
  --external-sensitivity-observation-log report/group_a_plus/latest/external_sensitivity_observation_log.json \
  --deployment-summary report/group_a_plus/latest/deployment_summary.json \
  --output report/group_a_plus/latest/final_governance_snapshot.json \
  --output-md report/group_a_plus/latest/final_governance_snapshot.md
```

## 測試與驗證

本輪最後驗證：

```bash
.venv/bin/python -m pytest \
  tests/test_build_group_a_plus_external_sensitivity_observation_log.py \
  tests/test_build_ncf_panel_external_feature_sensitivity_governance.py \
  tests/test_build_group_a_plus_panel_drift_resolution_progress.py \
  tests/test_build_group_a_plus_final_governance_snapshot.py \
  tests/test_run_ncf_daily_pipeline.py \
  -q
```

結果：

- `30 passed`

也跑過：

```bash
.venv/bin/python -m py_compile \
  scripts/evaluate/build_group_a_plus_external_sensitivity_observation_log.py \
  scripts/evaluate/build_ncf_panel_external_feature_sensitivity_governance.py \
  scripts/evaluate/build_group_a_plus_panel_drift_resolution_progress.py \
  scripts/evaluate/build_group_a_plus_final_governance_snapshot.py \
  scripts/run/run_ncf_daily_pipeline.py
```

結果：

- pass，沒有 compile error。

## 下一步建議

下一個交易日資料完成後，優先跑完整 daily pipeline 或至少跑 external sensitivity observation chain。目標是累積 same-method observation：

- valid observations 目前 `1/3`
- stable observations 目前 `0/3`

解除 external-feature sensitivity blocker 的必要條件：

1. sensitivity audit 存在。
2. same-method baseline manifest 是 `valid_shadow_baseline`。
3. remediation action `quantify_external_feature_sensitivity` 還在治理流程內。
4. 最新 sensitivity audit 不再超過 trigger-critical limits。
5. observation log 累積至少 3 次 stable observations。

即使以上條件達成，也只能解除 external sensitivity 這個子 blocker；promotion 仍需重新跑 promotion gate，並且 multi-window、panel drift、manual approval 等其他 gates 仍要通過。

## 後續操作注意

- 不要人工改 observation count；應由 `build_group_a_plus_external_sensitivity_observation_log.py` 自動 upsert。
- 不要把 non-stable observation 當成 blocker resolved。
- 不要為了通過 blocker 放寬 trigger limits，除非另有完整 shadow/backtest/gate review。
- 不要改 `golden1_0531`。
- 不要把 `results/ncf_daily_pipeline_20260722.json` 解讀成 full pipeline rerun；它目前是 outputs-only backfill manifest。
- worktree 目前已有大量既有 modified / untracked artifacts，後續不要用 destructive git command 清理。

## 本輪主要檔案清單

程式：

- `scripts/evaluate/build_group_a_plus_external_sensitivity_observation_log.py`
- `scripts/evaluate/build_ncf_panel_external_feature_sensitivity_governance.py`
- `scripts/evaluate/build_group_a_plus_panel_drift_resolution_progress.py`
- `scripts/evaluate/build_group_a_plus_final_governance_snapshot.py`
- `scripts/run/run_ncf_daily_pipeline.py`

測試：

- `tests/test_build_group_a_plus_external_sensitivity_observation_log.py`
- `tests/test_build_ncf_panel_external_feature_sensitivity_governance.py`
- `tests/test_build_group_a_plus_panel_drift_resolution_progress.py`
- `tests/test_build_group_a_plus_final_governance_snapshot.py`
- `tests/test_run_ncf_daily_pipeline.py`

最新報告：

- `report/group_a_plus/latest/external_sensitivity_observation_log.json`
- `report/group_a_plus/latest/external_sensitivity_observation_log.md`
- `report/group_a_plus/latest/panel_drift_resolution_progress.json`
- `report/group_a_plus/latest/panel_drift_resolution_progress.md`
- `report/group_a_plus/latest/final_governance_snapshot.json`
- `report/group_a_plus/latest/final_governance_snapshot.md`

結果：

- `results/ncf_panel_external_feature_sensitivity_governance_20260722.json`
- `results/ncf_panel_drift_remediation_plan_20260722.json`
- `results/ncf_daily_pipeline_20260722.json`

