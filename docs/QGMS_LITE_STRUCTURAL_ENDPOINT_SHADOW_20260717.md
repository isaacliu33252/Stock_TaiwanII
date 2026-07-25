# QGMS-lite structural endpoint shadow 交接記錄（2026-07-17）

## 背景

使用者指定分析 `C:\Users\isaac\Downloads\2511.16319v1.pdf`，判斷其中是否有優點可導入 GroupA+ 最新策略。

PDF 論文標題為 `Quantitative Geometric Market Structuralism (QGMS): A Framework for Detecting Structural Endpoints in Financial Market`。本文主張市場走勢可拆解為幾何子結構，並透過比例、角度、時間結構與多層級一致性辨識 `terminal zone` / `structural endpoint`。

## PDF 可取之處

可借用的概念：

- `structural endpoint`：不要只看趨勢強弱，也要偵測上漲腿是否進入末端過熱。
- `geometric convergence`：用價格腿長、時間腿長、斜率變化衡量結構收斂。
- `hierarchical consistency`：短期腿是否和較大層級走勢結構一致。
- `validation before action`：論文強調盲測與 timestamped validation，這和本專案 shadow-first 的導入原則一致。

不可直接導入的原因：

- 論文核心運算子 `Phi(Si)` 未公開，屬 proprietary。
- 沒有可重現公式、程式碼、完整統計表或 Taiwan ETF 驗證。
- 案例多為敘事型個案，不能直接拿來改 GroupA+ live 權重。

因此本次只導入透明代理版 `QGMS-lite`，不是原始 QGMS。

## 本次新增內容

新增檔案：

- `scripts/evaluate/evaluate_qgms_lite_structural_endpoint_shadow.py`

新增輸出：

- `results/qgms_lite_structural_endpoint_shadow_20250102_20260716.json`
- `results/qgms_lite_structural_endpoint_shadow_20250102_20260716_frame.csv`
- `results/qgms_lite_structural_endpoint_shadow_2020_crash.json`
- `results/qgms_lite_structural_endpoint_shadow_2020_crash_frame.csv`
- `results/qgms_lite_structural_endpoint_shadow_2022_rate_hike.json`
- `results/qgms_lite_structural_endpoint_shadow_2022_rate_hike_frame.csv`
- `results/qgms_lite_structural_endpoint_shadow_2026_recent.json`
- `results/qgms_lite_structural_endpoint_shadow_2026_recent_frame.csv`
- `results/qgms_srr_overlap_shadow_20250102_20260716.json`
- `results/qgms_srr_overlap_shadow_20250102_20260716_frame.csv`
- `results/qgms_srr_overlap_shadow_2026_recent.json`
- `results/qgms_srr_overlap_shadow_2026_recent_frame.csv`
- `results/qgms_srr_overlap_shadow_2020_covid.json`
- `results/qgms_srr_overlap_shadow_2020_covid_frame.csv`
- `results/qgms_srr_overlap_shadow_2022_rate_hike.json`
- `results/qgms_srr_overlap_shadow_2022_rate_hike_frame.csv`

## 實作方式

`QGMS-lite` 使用 `0050.TW` 與 `00631L.TW` 收盤價，做研究型 no-add shadow 評估。

為了避免 lookahead，轉折偵測採用線上確認：

- 只用當天以前資料。
- 價格相對上一個 pivot 移動超過 `min_swing_pct=3.5%` 才確認新 swing。
- pivot 是在反向移動確認日才被視為已知，不回頭拿未來高低點作弊。

主要特徵：

- `leg_ratio`：目前腿長和上一腿長比例。
- `duration_ratio`：目前腿時間和上一腿時間比例。
- `slope_ratio`：目前斜率和上一腿斜率比例。
- `vol_adjusted_extension`：目前腿長相對 20 日波動的延伸程度。
- `relative_momentum_20d`：00631L 相對 0050 的 20 日過度延伸。
- `hierarchy_score`：目前腿和父層結構的比例一致性。

預設訊號：

- `endpoint_watch_active`：上漲腿中，`qgms_lite_endpoint_score >= 0.55`。
- `strong_endpoint_active`：上漲腿中，`qgms_lite_endpoint_score >= 0.65`。

政策：

- `shadow_only_no_weight_change`
- 不改 `daily_signal.py`
- 不改 target weight
- 不改 GroupA+ 最新策略 manifest

## 回測標籤

使用和 SRR-lite no-add shadow 類似的事件標籤：

- `forward_rel_00631l_vs_0050 <= -1%`，或
- `forward_mdd_00631l <= -5%`

評估 horizon：

- 5 交易日
- 10 交易日

## 主要結果

### 2025-01-02 到 2026-07-16

`endpoint_watch_active`：

- active days：8
- 5 日 precision：50.0%
- 5 日 recall：3.7%
- 5 日 false positive rate：1.52%
- 10 日 precision：87.5%
- 10 日 recall：5.4%
- 10 日 false positive rate：0.41%
- active 10 日平均相對 0050：-0.95%
- inactive 10 日平均相對 0050：+1.76%
- active 10 日平均 00631L forward MDD：-7.53%
- inactive 10 日平均 00631L forward MDD：-3.86%

解讀：

- 訊號很少，但 10 日視窗命中率高。
- recall 很低，不能當完整風險偵測器。
- 它比較像「少量高確信的上漲腿末端人工警示」。

### 2026-01-02 到 2026-07-16

`endpoint_watch_active`：

- active days：8
- 5 日 precision：50.0%
- 5 日 recall：9.3%
- 5 日 false positive rate：4.71%
- 10 日 precision：87.5%
- 10 日 recall：13.2%
- 10 日 false positive rate：1.33%

觸發日：

- 2026-05-04：10 日標籤 false
- 2026-05-05：10 日標籤 true
- 2026-05-06：10 日標籤 true
- 2026-05-07：10 日標籤 true
- 2026-05-08：10 日標籤 true
- 2026-05-11：10 日標籤 true
- 2026-05-12：10 日標籤 true
- 2026-05-29：10 日標籤 true

解讀：

- 最近有效訊號集中在 2026 年 5 月。
- 此結果支持保留為人工 review 訊號。
- 但樣本過度集中，不能據此自動化。

### 2020 crash window

`2020-01-02` 到 `2020-06-30`：

- active days：1
- 5 日 precision：0.0%
- 10 日 precision：0.0%

解讀：

- 對 COVID crash 這種系統性急跌沒有足夠偵測力。
- 不可取代 SRR-lite crash watch。

### 2022 rate-hike window

`2022-01-03` 到 `2022-12-30`：

- active days：0

解讀：

- 對 2022 年升息型下跌沒有觸發。
- 不可作為熊市或宏觀風險偵測器。

## 為什麼不導入最新策略自動權重

不導入 live 自動權重，原因如下：

- 原始 QGMS 核心公式未公開，本次只是透明代理模型。
- 有效樣本集中在 2026 年 5 月，外部 crash window 驗證不足。
- 2020 與 2022 不能提供穩定風險偵測。
- `strong_endpoint_active` 在目前預設下完全沒有觸發，代表高門檻樣本不足。
- 若直接改權重，可能讓 GroupA+ 對少量事件過度反應。

因此本次導入範圍停在 evaluator 與研究輸出，不接進 `group_a_plus/operations/daily_signal.py`。

## 與目前策略的關係

目前 GroupA+ 最新策略狀態：

- SRR-lite：可留 live shadow alert，人工審核，不自動改權重。
- cross-market graph：研究用，不接 live alert。
- QGMS-lite：研究用，可作為 00631L 上漲腿末端人工警示候選，不接 live alert。

QGMS-lite 的定位比 SRR-lite 更窄：

- SRR-lite 看市場共振與系統脆弱度。
- QGMS-lite 看 00631L 自身上漲腿是否接近結構末端。

兩者不是替代關係。

## QGMS-lite 與 SRR-lite overlap 檢查

新增檔案：

- `scripts/evaluate/evaluate_qgms_srr_overlap_shadow.py`

目的：

- 檢查 QGMS-lite 是不是能確認 SRR-lite。
- 檢查 QGMS-lite 是否能補 SRR-lite 漏掉的 no-add 日期。
- 只讀既有 daily frame，不重訓參數，不接 live。

### 2025-01-02 到 2026-07-16 overlap

10 日 no-add label：

| 訊號 | active days | precision | recall | false positive rate |
| --- | ---: | ---: | ---: | ---: |
| SRR no-add | 8 | 50.0% | 3.1% | 1.65% |
| SRR crash-watch | 17 | 29.4% | 3.9% | 4.94% |
| QGMS endpoint | 8 | 87.5% | 5.5% | 0.41% |
| SRR no-add OR QGMS endpoint | 16 | 68.8% | 8.6% | 2.06% |
| SRR crash-watch OR QGMS endpoint | 25 | 48.0% | 9.4% | 5.35% |
| SRR no-add AND QGMS endpoint | 0 | 無樣本 | 0.0% | 0.0% |
| SRR crash-watch AND QGMS endpoint | 0 | 無樣本 | 0.0% | 0.0% |

重點：

- QGMS endpoint 和 SRR 同日完全沒有重疊。
- QGMS 不是 SRR 的 confirm signal。
- QGMS 是不同型態的輔助訊號，主要補 2026 年 5 月的 00631L 上漲腿末端。
- `SRR no-add OR QGMS endpoint` 有改善 recall，precision 也高於 SRR no-add 單獨，但 active days 從 8 增加到 16。
- `SRR crash-watch OR QGMS endpoint` false positive rate 偏高，不適合 live。

### 2026 recent overlap

視窗：`2026-05-15` 到 `2026-07-16`

10 日 no-add label：

| 訊號 | active days | precision | recall | false positive rate |
| --- | ---: | ---: | ---: | ---: |
| SRR no-add | 1 | 100.0% | 4.2% | 0.0% |
| SRR crash-watch | 2 | 100.0% | 8.3% | 0.0% |
| QGMS endpoint | 1 | 100.0% | 4.2% | 0.0% |
| SRR no-add OR QGMS endpoint | 2 | 100.0% | 8.3% | 0.0% |
| SRR crash-watch OR QGMS endpoint | 3 | 100.0% | 12.5% | 0.0% |

日期：

- QGMS endpoint：`2026-05-29`
- SRR crash-watch：`2026-06-01`, `2026-06-25`
- SRR no-add：`2026-06-25`

解讀：

- 2026 recent 支持 QGMS 作為互補警示。
- 但樣本只有 1 個 QGMS overlap-window 訊號，不能升級 live。

### 2020 COVID overlap

視窗：`2020-01-02` 到 `2020-06-30`

10 日 no-add label：

| 訊號 | active days | precision | recall | false positive rate |
| --- | ---: | ---: | ---: | ---: |
| SRR crash-watch | 7 | 85.7% | 17.1% | 1.23% |
| QGMS endpoint | 1 | 0.0% | 0.0% | 1.23% |
| SRR crash-watch OR QGMS endpoint | 8 | 75.0% | 17.1% | 2.47% |

解讀：

- 2020 中 QGMS 加入後讓 precision 變差。
- COVID crash 應由 SRR-lite 這類 systemic fragility 訊號處理，不應靠 QGMS-lite。

### 2022 rate-hike overlap

視窗：`2022-01-03` 到 `2022-10-31` 的 SRR overlap 區間。

10 日 no-add label：

| 訊號 | active days | precision | recall | false positive rate |
| --- | ---: | ---: | ---: | ---: |
| SRR no-add | 1 | 100.0% | 0.8% | 0.0% |
| SRR crash-watch | 13 | 46.2% | 4.9% | 8.86% |
| QGMS endpoint | 0 | 無樣本 | 0.0% | 0.0% |

解讀：

- QGMS 對 2022 升息下跌沒有幫助。
- 它不是 macro drawdown detector。

## 驗證命令

語法檢查：

```bash
.venv/bin/python -m py_compile scripts/evaluate/evaluate_qgms_lite_structural_endpoint_shadow.py
```

主視窗：

```bash
.venv/bin/python scripts/evaluate/evaluate_qgms_lite_structural_endpoint_shadow.py --start 2025-01-02 --end 2026-07-16 --output results/qgms_lite_structural_endpoint_shadow_20250102_20260716.json
```

Crash windows：

```bash
.venv/bin/python scripts/evaluate/evaluate_qgms_lite_structural_endpoint_shadow.py --start 2020-01-02 --end 2020-06-30 --output results/qgms_lite_structural_endpoint_shadow_2020_crash.json
.venv/bin/python scripts/evaluate/evaluate_qgms_lite_structural_endpoint_shadow.py --start 2022-01-03 --end 2022-12-30 --output results/qgms_lite_structural_endpoint_shadow_2022_rate_hike.json
.venv/bin/python scripts/evaluate/evaluate_qgms_lite_structural_endpoint_shadow.py --start 2026-01-02 --end 2026-07-16 --output results/qgms_lite_structural_endpoint_shadow_2026_recent.json
```

SRR overlap：

```bash
.venv/bin/python scripts/evaluate/evaluate_qgms_srr_overlap_shadow.py --srr-frame results/srr_lite_shadow_backtest_20250102_20260716_tuned_frame.csv --qgms-frame results/qgms_lite_structural_endpoint_shadow_20250102_20260716_frame.csv --output results/qgms_srr_overlap_shadow_20250102_20260716.json
.venv/bin/python scripts/evaluate/evaluate_qgms_srr_overlap_shadow.py --srr-frame results/srr_lite_shadow_crash_2026_recent_20260515_20260716_frame.csv --qgms-frame results/qgms_lite_structural_endpoint_shadow_2026_recent_frame.csv --output results/qgms_srr_overlap_shadow_2026_recent.json
.venv/bin/python scripts/evaluate/evaluate_qgms_srr_overlap_shadow.py --srr-frame results/srr_lite_shadow_crash_2020_covid_20200102_20200630_frame.csv --qgms-frame results/qgms_lite_structural_endpoint_shadow_2020_crash_frame.csv --output results/qgms_srr_overlap_shadow_2020_covid.json
.venv/bin/python scripts/evaluate/evaluate_qgms_srr_overlap_shadow.py --srr-frame results/srr_lite_shadow_crash_2022_rate_hike_20220103_20221031_frame.csv --qgms-frame results/qgms_lite_structural_endpoint_shadow_2022_rate_hike_frame.csv --output results/qgms_srr_overlap_shadow_2022_rate_hike.json
```

## 結論

`2511.16319v1.pdf` 的優點可以導入為研究型 `QGMS-lite structural endpoint shadow`，但不能導入最新策略的自動權重。

目前建議：

- 保留 evaluator 與輸出檔。
- 暫不接 live pipeline。
- QGMS-lite 不作為 SRR-lite confirm；兩者同日 overlap 目前為 0。
- 若未來要升級，較合理方向是「SRR no-add OR QGMS endpoint」的人工 review alert，而不是自動權重。
- 升級條件至少要包含：跨年份有效、不同 crash window 有穩定命中、false positive 低、且不降低 GroupA+ 主要回測績效。
