# 專案操作說明

最後更新：2026-07-16

本文件記錄目前專案中較穩定的操作入口，不搬移也不重新命名既有 scripts。這份文件刻意採保守做法，目標是讓 coworker 原本的使用方式可以繼續運作。

## 範圍

目前專案大致包含四類工作：

- 研究與 sweep：探索型 scripts，通常位於 `scripts/evaluate/`、`scripts/backtest/`、`scripts/sweep/`、`scripts/misc/`，以及部分歷史根目錄 scripts。
- 每日訊號產出：會更新 `report/group_a_plus/` 與相關 `latest` JSON 的可重複流程。
- 資料抓取與快取更新：`scripts/fetch/` 底下的 scripts，以及部分歷史根目錄 fetch 工具。
- 測試與驗證：主要在 `tests/`，另有部分歷史測試探索範圍包含 `FinRL/`。

## 安全的日常流程

執行或提交每日工作前，先檢查 worktree：

```bash
git status --short
```

原因：這個 repository 經常會有生成報表變更。先看 worktree 可以避免把生成輸出與 source code 變更混在同一個提交中。

變更特定邏輯時，優先跑對應的 focused tests：

```bash
pytest tests/path_to_relevant_test.py -q
```

如果改到共用 import、package path 或測試設定，至少跑一次測試探索：

```bash
pytest tests/ --collect-only -q
```

## 常用入口區域

每日與 pipeline runners：

- `scripts/run/`
- `group_a_plus/runners/latest.py`
- `scripts/run/run_group_a_plus_pipeline.py`
- `scripts/run/run_ncf_daily_pipeline.py`

回測與研究評估：

- `scripts/backtest/`
- `scripts/evaluate/`
- `group_a_plus/strategies/`
- `group_a_plus/integrations/`

營運訊號模組：

- `group_a_plus/operations/daily_signal.py`
- `group_a_plus/operations/execution_plan.py`
- `group_a_plus/operations/ops_health.py`
- `group_a_plus/operations/alert_state.py`

資料與 symbol helpers：

- `group_a_plus/data/`
- `group_a_plus/utils/symbols.py`
- `scripts/fetch/`

## 相容性規則

現階段不要直接移動或刪除根目錄 scripts，除非同時留下相容 wrapper。wrapper 應呼叫新的位置，並印出簡短 deprecation note。

在團隊確認前，不要移除已追蹤的 report、model、news 檔案。這些檔案可能被 coworker 當作 fixture、golden output 或 handoff artifact 使用。

不要在沒有獨立遷移計畫的情況下更改 `FinRL/` 或其中 nested `.git` 的角色。它可能被 coworker 視為 vendored project、本機 fork 或歷史 dependency。

## 測試 Markers

`pytest.ini` 已宣告未來可用的 markers：

- `unit`：快速、可重現、不依賴外部服務的測試。
- `integration`：跨模組、subprocess 或 end-to-end 行為測試。
- `network`：需要外部網路或第三方 API 的測試。
- `slow`：執行時間明顯較長的測試或 sweep。
- `gpu`：需要 GPU 或較重 ML runtime 的測試。
- `requires_data`：需要本機 cache、DB、生成報表或 model artifact 的測試。

目前這些 marker 宣告只提供分類基礎，不會自行改變既有測試執行行為。
