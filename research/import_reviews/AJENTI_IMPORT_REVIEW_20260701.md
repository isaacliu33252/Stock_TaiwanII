# Ajenti Import Review / Group A+ Ops Health

**日期：** 2026-07-01  
**來源：** `C:\Users\isaac\Downloads\ajenti-master\ajenti-master`  
**目標系統：** Group A+ / A21.18 daily operations

---

## 一、結論

Ajenti 不適合直接導入交易策略或模型層，但其 **read-only dashboard / plugin health / dependency check** 思路適合導入 Group A+ 的每日營運健康檢查。

本次導入範圍：

- 不導入 Ajenti web panel
- 不導入 AngularJS UI
- 不導入 auth / socketio / gevent server stack
- 不導入 start/stop service 控制
- 不導入 filesystem move/delete/chmod 類功能
- 只導入只讀型 ops health report 概念

Active allocation impact: `none`

**重要政策：磁碟空間不作為健康狀態門檻。**  
依 2026-07-01 使用者指示：「不限磁碟空間」。`ops_health` 可以揭露 disk free ratio，但不得因磁碟剩餘空間低而讓總狀態變成 `warning` 或 `error`。

---

## 二、Ajenti 可借鑑優點

| Ajenti 設計 | 可移植價值 | Group A+ 對應 |
|---|---|---|
| `plugin.yml` + dependency check | 模組依賴與缺檔狀態可結構化 | NCF / Factor Lens / AlphaGen-lite / FinBERT / TBrain 模組健康 |
| Dashboard widgets | 輕量只讀狀態卡片 | CPU / memory / disk / pipeline / artifact health |
| Cron manager | 排程可視化與檢查概念 | Windows Task Scheduler / `run_daily.bat` / `run_fetch.bat` |
| Certificate checker | 外部服務到期/連線狀態檢查概念 | API key / provider / stale source health |
| Non-destructive config principle | 不覆寫、不破壞既有系統 | ops health 僅讀取與報告，不改配置 |

---

## 三、本次實作

新增：

- `group_a_plus/operations/ops_health.py`
- `scripts/run/check_ops_health.py`
- `tests/test_group_a_plus_ops_health.py`

更新：

- `scripts/run/run_ncf_daily_pipeline.py`
  - 每日 pipeline 結尾新增非致命 `[ops-health]` 區塊
  - 自動寫出 `report/group_a_plus/latest/ops_health.json`
- `tests/test_run_ncf_daily_pipeline.py`
  - 對齊目前 pipeline 已包含 `factor_lens` / `daily_signal`

輸出：

- `report/group_a_plus/latest/ops_health.json`

---

## 四、Ops Health 報告內容

`ops_health.json` 包含：

- `system_resources`
  - disk free ratio
  - CPU percent / count
  - memory available ratio
- `artifact_health`
  - `strategy.json`
  - `live_signal.json`
  - `execution_plan.json`
  - `strategy_env_health.json`
  - NCF 00631L panel
  - `run_daily.bat` / `run_fetch.bat` / `task_scheduler_setup.xml`
  - `logs/daily.log`
- `pipeline_health`
  - 最新 `ncf_daily_pipeline_*.json`
  - pipeline outputs 是否存在
  - NCF signal summary
- `module_health`
  - NCF 00631L / 00632R
  - Factor Lens
  - AlphaGen-lite shadow / feature pool
  - FinBERT / TBrain / factor_lens_gate from live signal

總狀態：`ok / warning / error`

---

## 五、目前實測結果

執行：

```bash
PYTHONPATH=. .venv/bin/python scripts/run/check_ops_health.py
```

輸出：

```text
Ops health: report/group_a_plus/latest/ops_health.json
Status: ok
```

政策調整：

- 依 2026-07-01 使用者指示：「不限磁碟空間」
- disk free ratio 保留在 `system_resources.disk.free_ratio`
- 但磁碟空間不再觸發 `warning` 或 `error`
- `system_resources.disk.status_policy = informational_only`

目前檢查重點：

- required artifacts: ok
- scheduler files: ok
- daily log: ok
- latest pipeline manifest: ok
- pipeline outputs: ok
- module outputs: ok

這代表 `ops_health` 目前只針對缺檔、pipeline 輸出、模組狀態、記憶體極端不足等項目產生健康狀態；磁碟容量只做資訊揭露。

### 磁碟政策確認（2026-07-01）

目前 `report/group_a_plus/latest/ops_health.json`：

```json
{
  "status": "ok",
  "active_allocation_impact": "none",
  "system_resources": {
    "disk": {
      "free_ratio": 0.0179,
      "status_policy": "informational_only"
    }
  }
}
```

即使 `free_ratio` 低於 5%，總狀態仍應維持依其他檢查項目判定；低磁碟空間只顯示，不阻塞。

---

## 六、驗證

```bash
.venv/bin/python -m pytest -q \
  tests/test_group_a_plus_ops_health.py \
  tests/test_group_a_plus_strategy_env.py \
  tests/test_run_ncf_daily_pipeline.py
```

結果：

```text
6 passed in 2.05s
```

---

## 七、後續建議

優先處理：

1. 下一步可將 `ops_health.json` 摘要加入每日通知或 commentary。
2. 若要擴充，優先加「排程上次成功時間」而不是 service 控制。
3. 磁碟空間維持 informational only，不作為阻塞條件。

維持限制：

- `ops_health` 僅能是只讀報告
- 不接 active allocation
- 不自動刪檔
- 不自動重啟服務
