# 自動化流程交接記錄
**日期：** 2026-06-29  
**作者：** Isaac Liu  
**工具：** Claude Code（claude-sonnet-4-6），透過 WSL 終端機操作

> 本文件所有腳本、pipeline 修改、排程設定均透過 Claude Code 完成。
> 後續維護或功能擴充可繼續使用 Claude Code（在專案目錄下執行 `claude`）。

---

## 一、每日自動化架構

### 排程總覽

| 時間 | 腳本 | 工作 | 預估時間 |
|------|------|------|---------|
| 23:00 | `run_fetch.bat` | 下載市場資料 | 5–10 分鐘 |
| 23:30 | `run_daily.bat` | NCF 模型訓練 + 訊號產生 | 15–20 分鐘 |

### Windows 工作排程器
- 工作名稱：`台股資料下載`（23:00）
- 工作名稱：`台股NCF每日流程`（23:30）

查詢指令：
```powershell
schtasks /query /tn "台股資料下載"
schtasks /query /tn "台股NCF每日流程"
```

重建指令（如排程遺失）：
```powershell
schtasks /create /tn "台股資料下載" /tr "C:\Users\isaac\Downloads\Stock_taiwan2-main\Stock_taiwan2-main\run_fetch.bat" /sc daily /st 23:00 /f
schtasks /create /tn "台股NCF每日流程" /tr "C:\Users\isaac\Downloads\Stock_taiwan2-main\Stock_taiwan2-main\run_daily.bat" /sc daily /st 23:30 /f
```

---

## 二、相關檔案

### Bat 腳本
| 檔案 | 用途 |
|------|------|
| `run_fetch.bat` | 23:00 執行，下載資料（`--only-refresh`） |
| `run_daily.bat` | 23:30 執行，跑 NCF 模型（`--skip-refresh`） |

### Pipeline 腳本
`scripts/run/run_ncf_daily_pipeline.py`

新增參數：
- `--only-refresh`：只執行資料下載步驟（7步），跳過 NCF 模型
- `--skip-refresh`：跳過資料下載，直接跑 NCF 模型（4步）

### Log 檔案
| 檔案 | 內容 |
|------|------|
| `logs/daily.log` | 所有執行記錄，含進度與子程序輸出 |
| `logs/daily_error.log` | 錯誤輸出（若有） |

---

## 三、Pipeline 步驟明細

### `run_fetch.bat`（--only-refresh，7步）
1. refresh_group_data — OHLCV 資料更新
2. refresh_taifex — 期交所資料
3. refresh_institutional — 法人籌碼
4. refresh_margin — 融資融券
5. refresh_market_margin — 市場融資
6. refresh_shareholding — TDCC 持股分散
7. ohlcv_freshness — 資料新鮮度檢查

### `run_daily.bat`（--skip-refresh，4步）
1. ohlcv_freshness — 資料新鮮度確認
2. ncf_00631l — 00631L 模型訓練 + 訊號
3. ncf_00632r — 00632R 模型訓練 + 訊號
4. advisory_panel — 彙整建議面板

---

## 四、進度顯示

Pipeline 執行時終端機只顯示進度行：
```
[1/7] refresh_group_data  (0%)
  ✓ 完成 (14%)
[2/7] refresh_taifex  (14%)
  ✓ 完成 (28%)
...
```
詳細子程序輸出靜默寫入 `logs/daily.log`。

---

## 五、CI（GitHub Actions）

已建立 `.github/workflows/test.yml`，push 到 GitHub 後自動執行：
- Python 3.10 環境
- 安裝核心依賴（pandas、lightgbm、xgboost、torch CPU 版等）
- Import smoke check + 單元測試
- 排除需要外部 API / GPU 的測試

---

## 六、待辦事項（未來改善）

- [ ] **模型訓練與推理分離**：`ncf_00631l.py` / `ncf_00632r.py` 加入 `--mode train/predict`，每週訓練一次，每日只跑推理（可將 23:30 流程縮短至 1–2 分鐘）
- [ ] **LINE / Telegram 通知**：pipeline 完成後發送訊號摘要
- [ ] **假日判斷**：非交易日自動跳過不執行
- [ ] **requirements.txt 更新**：補齊 lightgbm、pytorch-tabnet、duckdb 等實際使用的套件
