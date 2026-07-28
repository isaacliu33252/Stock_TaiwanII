# Group A+ 專案路由層

Fable audit (2026-07-28, #10): 84+ 篇根目錄 `GROUP_A_PLUS_*.md` 交接文件、79 篇
`docs/*.md`，沒有任何入口文件。這份文件不重寫任何內容，純粹告訴你去哪裡查，
不用先 grep 一輪檔名猜。

## 目前 production 策略

- 策略 ID：`a2118_a2111_ncf_late_bull_deleverage`（見
  `report/group_a_plus/latest/strategy.json` 的 `active_strategy`）
- Runner：`group_a_plus/runners/a2118.py`，經
  `group_a_plus/governance/latest.py` 的 `SUPPORTED_STRATEGIES` 解析
- 每日執行訊號：`report/group_a_plus/latest/execution_plan.json`（由
  `group_a_plus/operations/execution_plan.py` 產生，**不是**每日自動化的一部分，
  需要真實 cash balance 手動重跑）
- 每日 target signal：`group_a_plus/operations/daily_signal.py` →
  `report/group_a_plus/latest/live_signal.json` / `alert_state.json`

## 每日自動化

- 23:00 觸發：`task_scheduler_setup.xml`（Windows工作排程器）→
  `run_daily.bat` → `scripts/run/run_ncf_daily_pipeline.py`
- pipeline 內有 critical steps（失敗會中止整個 run）跟 best-effort steps
  （`BEST_EFFORT_STEP_NAMES`，失敗只記錄不中止）兩種
- 運維健康檢查：`group_a_plus/operations/ops_health.py` +
  `group_a_plus/operations/alert_state.py`（讀 `report/group_a_plus/latest/`
  底下的各種 JSON 快照組成 alert）

## 治理/清單類文件（避免重複審查已經處理過的東西）

- Runner catalog（含 active/shadow/archived 狀態）：
  `group_a_plus/governance/catalog.py`
- 永久性 shadow 研究模組複審清單：
  `group_a_plus/governance/shadow_registry.py`（每個模組的
  `review_trigger` 說明什麼時候該回頭看）
- 訊號驗證檢查清單（新 shadow candidate 要照做）：
  `GROUP_A_PLUS_SIGNAL_VALIDATION_CHECKLIST_20260723.md`

## 已關閉/已否決的研究方向在哪裡查

沒有單一檔案彙整全部已否決方向。查詢順序：

1. 這個 Claude 帳號的 auto-memory 系統（`project_*`/`feedback_*` 記憶，
   涵蓋 2026-06 至今絕大多數否決/promote 決策的簡短摘要+理由）
2. 最新的 `GROUP_A_PLUS_YYYYMMDD_SESSION_HANDOFF_INDEX.md`（目前最新一份是
   `GROUP_A_PLUS_20260725_SESSION_HANDOFF_INDEX.md`；日期更新的交接文件
   若存在會用相同命名規則出現在根目錄）
3. 個別主題的 `GROUP_A_PLUS_*_HANDOFF_*.md` / `docs/*.md`（依日期+關鍵字找）

`GROUP_A_PLUS_20260725_SESSION_HANDOFF_INDEX.md` 之前累積的交接文件沒有回溯
補索引，屬於已知缺口，不需要現在補齊。
