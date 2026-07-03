# NCF Ensemble Calibration/Weighting 交接紀錄 — 2026-07-01

## 背景

使用者問「Group A+ 有什麼可以改善的?」，實際攤開 `results/ncf_00631l_latest_20260630.json` 的
H20 classification ensemble 輸出後發現：

- `gb` 模型 Brier=0.434（比「全部猜0.5」的naive baseline 0.25 還爛）
- ensemble 混合後的 Brier(0.2432) 甚至比單一最佳模型 `et`(0.1922) 還差
- 根因：ensemble 權重公式只看 AUC（`w_i = max(0, AUC_i-0.5)`），完全不管校準品質；
  isotonic calibration 的接受條件寫的是「AUC要進步」（`scripts/misc/ncf_00631l.py` 原本
  `if auc_iso > auc_raw:`），但 isotonic regression 是保序轉換，理論上不太會動到AUC——
  這個接受條件形同虛設，導致很多模型的機率其實沒被有效校準。

## 已經做的程式碼修改（目前線上狀態）

`scripts/misc/ncf_00631l.py` 和 `ncf_00632r.py` 兩個檔案都改了，改動完全對稱，共4個地方：

1. 主要 base model 校準接受條件（00631L ~line 1794, 00632R ~line 1377）：
   從 `if auc_iso > auc_raw:` 改成
   `if brier_iso < brier_raw and auc_iso >= auc_raw - CALIB_MAX_AUC_DROP:`
   （`CALIB_MAX_AUC_DROP = 0.03`，定義在函式開頭 `MIN_CALIB` 旁邊）

2. `stable_rf` 子模型的校準接受條件（00631L ~line 2000, 00632R ~line 1479）：同樣邏輯。

3. 主要 ensemble 權重公式（00631L ~line 1885, 00632R ~line 1394）：
   從純 `w_i = max(0, AUC_i - 0.5)` 改成
   `w_i ∝ max(0, AUC_i - 0.5) × max(0, naive_brier - Brier_i)`
   （`naive_brier = p_base*(1-p_base)`，`p_base` 是驗證集 base rate）。
   若所有模型都被 Brier 篩掉（`total_w<=0`），退回純 AUC 加權；若還是全零，退回等權重。

4. 00631L 額外有一個「加入 stable_rf 後重算權重」的區塊（~line 2027 `W2`），同樣公式套用。

**這兩個檔案目前處於 V2（Brier+AUC guard 0.03）狀態，尚未 commit（本來就是 git untracked 的既有WIP）。**

## 三版對比實測結果

跑法：`--train-start 2020-01-01`(00631L)/`2015-01-01`(00632R) `--val-start 2025-01-02 --val-end latest`，
輸出存在 `/tmp/claude-*/scratchpad/`（未覆蓋正式 `results/` 檔案）。

### 00631L
| Horizon | 舊(AUC-gate,原始) | V1(純Brier-gate) | V2(Brier+guard0.03) |
|---|---|---|---|
| H1 Brier | 0.2505 | 0.2380 | 0.2418 |
| H5 Brier | 0.2472 | 0.2374 | 0.2380 |
| H20 AUC/Brier | ~0.69 / 0.2432 | 0.6721 / 0.1881 | 0.6252 / 0.2450（0/7模型通過校準）|

### 00632R
| Horizon | 舊(AUC-gate,原始) | V1(純Brier-gate) | V2(Brier+guard0.03) |
|---|---|---|---|
| H1 | AUC=0.543 Brier=0.2549 | AUC=0.537 Brier=0.2430 | AUC=0.537 Brier=0.2430 |
| H5 | AUC=0.661 Brier=0.2376 | AUC=0.631 Brier=0.2070 | AUC=0.612 Brier=0.2085 |
| H20 | AUC=0.816 Brier=0.1676 | AUC=0.642 Brier=0.1348 | AUC=0.767 Brier=0.1676（0/7模型通過校準）|

### 多年 walk-forward（2022-2026，5折，V1程式碼版本跑的，只有AUC沒有Brier）
跟 6/30 舊基準（記憶 `project_feature_sweep_20260630.md`：「00631L全年全Horizon>0.55、2026 H=20 AUC=0.871」；
「00632R H5每年>0.63最穩健、2024 H20=0.500結構性失效」）比較：

- 00631L 2026 H20 AUC 從 0.871 掉到 0.784（V1）
- 00631L 多了兩格略跌破0.55可用門檻：2024 H5=0.548、2026 H1=0.534
- 00632R H5「每年>0.63」在V1底下依然成立（0.633/0.671/0.709/0.661/0.706）
- 00632R 2024 H20=0.500 這個已知結構性失效完全沒變（修正沒動到它，符合預期）

## 核心發現（兩個獨立問題疊在一起）

1. **isotonic calibration 在 held-out 驗證集上不是保序的**：階梯函數在新資料上會造成大量並列(ties)，
   AUC對並列懲罰很重，所以「Brier改善」跟「AUC不掉」在小校準集(n_calib~150-300)下常常沒辦法兩全。
   這推翻了程式碼原本的假設/註解（已在V1修正裡更新註解說明）。

2. **ensemble 權重公式本身也有獨立的AUC代價**：00632R H20 在V2裡是 0/7 模型通過校準（等於沒套用任何
   校準），但 ensemble AUC 還是從 0.816 掉到 0.767——證明光是把權重公式從純AUC改成AUC×Brier，
   即使沒有任何校準介入，重新分配權重本身就會犧牲一些AUC（把權重從「AUC最高」的模型移向
   「Brier也不錯」的模型）。這代表問題1(校準接受條件)和問題2(權重公式)是兩個獨立的trade-off來源，
   不能用同一個門檻參數同時解決。

3. **0.03 的 AUC guard 對 H20 來說太嚴**：兩檔ETF的H20都變成 0/7 模型通過校準，幾乎完全否決了V1的
   Brier改善，等於白改。需要更大的guard（例如0.05~0.08）或非二元的作法。

## 目前狀態 / 沒做的事

- **完全沒有動到正式模型/正式訊號**：`results/ncf_00631l_latest_20260630.json`、
  `results/ncf_00632r_latest_20260630.json`、`report/group_a_plus/latest/live_signal.json`
  全部維持原狀，daily_signal 目前用的還是舊模型的輸出。
- 程式碼檔案（`ncf_00631l.py`、`ncf_00632r.py`）目前是V2狀態，**還沒決定是否要當成最終版本**。
- 沒有嘗試：加大 `calib_frac`（目前0.20）給isotonic更多校準資料減少tie-inflation；
  k-fold交叉驗證版isotonic取代單一80/20切分；Platt sigmoid校準（參數化、不會產生硬性tie）
  當isotonic的替代方案。

## 建議下一步（優先順序）

1. 先試「加大 calib_frac」（例如0.20→0.30），看能不能讓isotonic在更多資料上擬合、減少ties造成的AUC損失，
   這是成本最低、最直接針對根因的嘗試。
2. 如果還是沒有乾淨的平衡點，考慮把「校準接受條件」跟「ensemble權重公式」這兩個改動拆開分別驗證
   （目前混在一起跑，很難單獨歸因哪個改動造成多少AUC損失）。
3. 在拿到穩定驗證結果、且至少涵蓋一次非持續多頭的regime之前，**不要**把任何一版promote成正式模型
   （跟今天其他審查案例一致的保守原則：weekly_ma_bull、FinMind新聞情緒都因為單一多頭regime樣本
   而暫緩promote）。
4. 若決定放棄這個方向，回退方式：把 `CALIB_MAX_AUC_DROP` 相關的 if 條件退回原本
   `if auc_iso > auc_raw:`，ensemble 權重公式退回純 `max(0, AUC_i-0.5)` 即可還原成 6/30 的原始行為。
