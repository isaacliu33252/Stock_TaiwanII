# 相容型整理變更紀錄

日期：2026-07-16

## 摘要

本次變更新增文件與 pytest marker 宣告，讓專案更容易操作，同時避免中斷 coworker 既有工作流程。

本次沒有移動或刪除任何 scripts、reports、models、data files 或 package directories。

## 變更內容

### README 入口段落

在 `README.md` 最上方新增簡短專案入口。

為什麼這樣改：

- 既有 README 保留了有價值的研究歷史，但開頭是時間序的實驗紀錄。
- 新加入或回來維護的人，需要先看到穩定入口，再決定是否閱讀舊研究紀錄。

相容性影響：

- 低。既有 README 內容仍完整保留在新段落下方。
- 新增的 links 只指向新文件，沒有改動既有路徑。

### 操作說明文件

新增 `docs/OPERATIONS.md`。

為什麼這樣改：

- 每日流程、回測、fetcher、tests 分散在多個目錄。
- 單一操作地圖可以降低 coworker 依賴猜測或過期 shell history 的機率。

相容性影響：

- 無。此變更只有文件。

### 產出檔管理政策

新增 `docs/ARTIFACT_POLICY.md`。

為什麼這樣改：

- repository 內有許多生成輸出，且其中部分仍被 Git 追蹤。
- 未經協調就移除生成檔，可能破壞 handoff、regression 或 coworker 工作流程。
- 先寫下政策，可以讓後續清理分階段、可 review 地進行。

相容性影響：

- 本次無實際 artifact 影響。沒有刪除或 untrack 任何生成檔。

### Pytest marker 宣告

在 `pytest.ini` 新增 marker 宣告：

- `unit`
- `integration`
- `network`
- `slow`
- `gpu`
- `requires_data`

為什麼這樣改：

- 目前 CI 透過明確 `--ignore` 條列排除特殊測試。
- markers 是較長期、較安全的方式，可區分快速 deterministic tests 與需要 network、本機資料 cache、GPU 或長時間執行的 tests。

相容性影響：

- 低。宣告 markers 不會選取、取消選取或重新命名測試。
- 既有 `pytest` 指令仍可繼續使用。
- 本次整理沒有改變 CI 行為。

## 為什麼採保守做法

此專案仍在活躍使用，worktree 也已存在生成報表變更。若一次做大規模結構調整，可能因 script 路徑改變、預期輸出被移除或 CI 語意改變而影響 coworker。

本次刻意只做低風險、可回復的改善：

- 先補文件，再考慮搬移檔案。
- 先宣告測試分類，再改 CI selection。
- 先記錄 artifact 清理政策，再從 Git 移除任何檔案。
- 保留根目錄 scripts 與歷史研究紀錄。

## 建議下一步

1. 和 coworker 確認哪些已追蹤的 `report/`、`results/`、`models/`、`news/` 檔案仍需要保留。
2. 逐步替 tests 加上 markers，先從明確依賴外部資源或執行較慢的 tests 開始。
3. 等 marker coverage 可靠後，再把 CI 改成 marker-based selection。
4. 移動根目錄 scripts 前，先建立相容 wrapper。
5. 決定 `FinRL/` 應該是 vendored dependency、submodule，或正式吸收到主 package。
