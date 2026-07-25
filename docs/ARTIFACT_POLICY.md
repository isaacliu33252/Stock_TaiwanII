# 產出檔管理政策

最後更新：2026-07-16

本文件說明生成輸出應如何處理。這次變更不移除既有已追蹤檔案，只先定義後續清理時較安全的原則。

## 目標

- 讓 source review 保持清楚。
- 保留重要研究結果的可重現性。
- 避免破壞 coworker 依賴的既有生成檔。
- 將 source code 與本機 cache、model binary、大型 sweep output 分開管理。

## 建議分類

建議追蹤在 Git：

- `group_a_plus/`、`scripts/`、`config/`、`environments/` 與其他維護中 package 的 source code。
- 必須用於 deterministic tests 的小型測試資料，建議放在 `tests/fixtures/`。
- 明確用於 regression check 的小型 golden outputs。
- 文件與 handoff notes。

不建議新增追蹤在 Git：

- `results/` 底下的大型 sweep result。
- `models/` 底下的 model binary。
- `data/cache/`、`data/raw/`、`data/portfolio_cache/`、`data/taifex/` 等本機 cache。
- `news/` 底下下載或生成的新聞語料。
- `logs/` 與 `log/` 底下的 runtime logs。
- 每日生成的 HTML、JSON、MD 報表，除非明確升級為 handoff artifact。

需要理由才建議追蹤：

- `report/group_a_plus/latest/*.json` 可能對 handoff 或 regression 有用，但每個被追蹤的檔案都應有明確使用者或用途。
- `report/group_a_plus/shadow/*.json` 只有在它是具名研究 artifact 或 golden comparison 時才建議追蹤。
- `results/*.json` sweep output 應先整理成文件摘要，再考慮是否追蹤完整 raw output。

## 清理方式

後續清理應分階段，不要一次大量刪除。

1. 盤點已追蹤 artifact：

   ```bash
   git ls-files data models results report news logs log
   ```

2. 確認哪些檔案被 tests 或 handoff docs 使用。

3. 必要的小型樣本移到 `tests/fixtures/`，或明確記錄為何要留在原位置。

4. 若某些生成檔應保留在本機但不再進 Git，只從 index 移除：

   ```bash
   git rm --cached path/to/generated_file
   ```

5. artifact policy 與 index cleanup 應獨立提交，不要和模型或策略邏輯變更混在一起。

## 目前相容性決策

截至 2026-07-16，本次相容型整理沒有刪除或 untrack 任何生成 artifact。專案已經對多個 output directory 設定 ignore rules，但仍有部分檔案在這些目錄下被 Git 追蹤。這需要一次團隊可見的清理，因為 coworker 可能依賴特定歷史輸出。
