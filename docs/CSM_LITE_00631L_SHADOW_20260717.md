# CSM-lite 00631L shadow 交接記錄（2026-07-17）

## 背景

使用者指定分析 `C:\Users\isaac\Downloads\2606.04153v1.pdf`，判斷是否有優點可導入 GroupA+ 最新策略。

PDF 論文：

- 標題：`A new decomposition approach to modeling financial returns: Conditioning sign on magnitude`
- 作者：Arsene Brou、Richard Luger
- 狀態：Journal of Banking and Finance accepted manuscript
- arXiv：`2606.04153v1`

## 論文核心

論文提出 `CSM`（Conditioning Sign on Magnitude）：

- 將報酬拆成 `sign` 與 `magnitude`
- `sign`：報酬方向，正或負
- `magnitude`：絕對報酬，接近波動狀態
- 先建模 magnitude，再讓 sign model 條件化在 contemporaneous magnitude 上

直覺：

- 波動 / 幅度狀態會影響下一期正報酬機率。
- 傳統線性 return regression 可能抓不到 sign 與 magnitude 的非線性關係。
- 對投資人而言，market timing 更重視方向判斷，而不是單純 return MSE。

論文實證：

- 原始實證為月頻 S&P 500 excess return。
- CSM 在 out-of-sample R2、terminal wealth、CER gain 上常優於線性模型、CSR、部分 nonlinear benchmark。
- 但 crisis appendix 顯示 GFC / COVID 中 CSM 不一定最強，短期 momentum 有時更穩。

## 可借用之處

可以借用：

- `direction` 與 `magnitude` 分開建模。
- 用 magnitude / volatility state 輔助方向機率。
- 評估時重視 direction / market timing，而不是只看預測誤差。

不能直接照搬：

- 論文是月頻美股市場，不是台股日頻。
- 原方法用 contemporaneous magnitude；live 使用時若直接用真實當期 magnitude 會 lookahead。
- GroupA+ 的問題是 00631L / 0050 / 現金配置，不能直接等同 S&P 500 market timing。

## 本次導入方式

新增 research-only evaluator：

- `scripts/evaluate/evaluate_csm_lite_00631l_shadow.py`

輸出：

- `results/csm_lite_00631l_shadow_20250102_20260716.json`
- `results/csm_lite_00631l_shadow_20250102_20260716_frame.csv`
- `results/csm_lite_00631l_shadow_20250102_20260716_with_baseline.json`
- `results/csm_lite_00631l_shadow_20250102_20260716_with_baseline_frame.csv`
- `results/csm_lite_00631l_shadow_2018_correction.json`
- `results/csm_lite_00631l_shadow_2018_correction_frame.csv`
- `results/csm_lite_00631l_shadow_2020_backfill.json`
- `results/csm_lite_00631l_shadow_2020_backfill_frame.csv`
- `results/csm_lite_00631l_shadow_2026_recent.json`
- `results/csm_lite_00631l_shadow_2026_recent_frame.csv`

實作設計：

- 使用既有 `ncf_00631l_panel_latest_20260716.csv`
- 沿用 `evaluate_direction_magnitude_shadow.py` 的 feature builder
- 目標：
  - direction：`forward_gain_h20 > 0`
  - magnitude：`abs(forward_gain_h20)`
- 先用 `HistGradientBoostingRegressor` 預測 h20 magnitude
- 再將 `predicted_magnitude` 與 `predicted_magnitude_ratio` 加入 sign model
- sign model：
  - `direction_only_logistic`
  - `csm_lite_logistic`
  - `csm_lite_hgb`
- 評估：
  - TimeSeriesSplit
  - gap = 20，降低 h20 label overlap 造成的洩漏
  - AUC
  - Brier
  - low-prob no-add precision

重要防線：

- 不使用真實 future magnitude 作為 sign feature。
- 只使用模型預測 magnitude。
- 不接 `daily_signal.py`
- 不改 target weights
- 不改最新策略 manifest

## 主視窗結果

視窗：`2025-01-02` 到 `2026-07-16`

### 不含 baseline feature

| 模型 | AUC | Brier | AUC vs baseline | Brier vs baseline |
| --- | ---: | ---: | ---: | ---: |
| baseline `prob_up_h20` | 0.7992 | 0.2256 | 0.0000 | 0.0000 |
| direction-only logistic | 0.4659 | 0.2488 | -0.3333 | +0.0232 |
| CSM-lite logistic | 0.4963 | 0.2545 | -0.3029 | +0.0288 |
| CSM-lite HGB | 0.6018 | 0.0936 | -0.1974 | -0.1320 |

解讀：

- 既有 NCF `prob_up_h20` baseline 很強，AUC 約 0.799。
- CSM-lite 沒有提升方向排序能力。
- HGB CSM-lite 的 Brier 較低，但 AUC 仍遠低於 baseline，代表它偏保守或校準較好，不代表 no-add 可用。

### 含 baseline feature

| 模型 | AUC | Brier | AUC vs baseline | Brier vs baseline |
| --- | ---: | ---: | ---: | ---: |
| baseline `prob_up_h20` | 0.7992 | 0.2256 | 0.0000 | 0.0000 |
| direction-only logistic | 0.4710 | 0.2491 | -0.3282 | +0.0235 |
| CSM-lite logistic | 0.4986 | 0.2548 | -0.3006 | +0.0292 |
| CSM-lite HGB | 0.6007 | 0.0936 | -0.1985 | -0.1320 |

解讀：

- 即使把 `prob_up_h20` 放入 feature，CSM-lite 仍沒有勝過 baseline。
- 目前不支持升級。

## No-add 檢查

主視窗中，h20 forward return 多數偏強。

baseline `prob_up_h20 <= 0.45`：

- active days：88
- nonpositive precision：5.7%
- active mean forward return：+14.0%

CSM-lite logistic `prob <= 0.45`：

- active days：67
- nonpositive precision：0.0%
- active mean forward return：+11.8%

CSM-lite HGB `prob <= 0.45`：

- active days：23
- nonpositive precision：0.0%
- active mean forward return：+13.1%

解讀：

- 低機率日並沒有對應後續不利報酬。
- 這不適合做 00631L no-add guard。

## 2020 stress window

使用：

- `results/ncf_00631l_panel_backfill_2020_20260716.csv`
- `2020-01-02` 到 `2020-12-31`

結果：

| 模型 | AUC | Brier | AUC vs baseline | Brier vs baseline |
| --- | ---: | ---: | ---: | ---: |
| baseline `prob_up_h20` | 0.5724 | 0.0769 | 0.0000 | 0.0000 |
| direction-only logistic | 0.1862 | 0.2411 | -0.3862 | +0.1642 |
| CSM-lite logistic | 0.1931 | 0.2412 | -0.3793 | +0.1643 |
| CSM-lite HGB | 0.0552 | 0.0341 | -0.5172 | -0.0427 |

No-add：

- baseline 在 `prob <= 0.45` 沒有觸發。
- CSM-lite logistic 觸發 42 天，但 nonpositive precision = 0.0%，active mean forward return = +16.5%。
- CSM-lite HGB 沒有觸發。

解讀：

- 2020 stress window 不支持 CSM-lite。
- CSM-lite logistic 反而在後續正報酬期間誤判 no-add。

## Crash window 補充回測

### 2018 correction

使用：

- `results/ncf_00631l_panel_backfill_2017_2019_20260710.csv`
- `2018-01-02` 到 `2018-12-31`

方向模型：

| 模型 | AUC | Brier | AUC vs baseline | Brier vs baseline |
| --- | ---: | ---: | ---: | ---: |
| baseline `prob_up_h20` | 0.5963 | 0.1538 | 0.0000 | 0.0000 |
| direction-only logistic | 0.4088 | 0.2368 | -0.1875 | +0.0829 |
| CSM-lite logistic | 0.4182 | 0.2332 | -0.1781 | +0.0793 |
| CSM-lite HGB | 0.4054 | 0.1066 | -0.1909 | -0.0472 |

No-add 檢查，`prob <= 0.45`：

| 模型 | active days | nonpositive precision | active mean forward return |
| --- | ---: | ---: | ---: |
| baseline | 0 | 無樣本 | 無樣本 |
| CSM-lite logistic | 30 | 3.3% | +4.54% |
| CSM-lite HGB | 1 | 0.0% | +6.76% |

解讀：

- CSM-lite 未擊敗 baseline。
- CSM-lite logistic 觸發不少 no-add，但 precision 只有 3.3%，且平均 forward return 為正。
- 不適合當 crash/no-add guard。

### 2026 recent

使用：

- `results/ncf_00631l_panel_latest_20260716.csv`
- `2026-01-02` 到 `2026-07-16`

方向模型：

| 模型 | AUC | Brier | Brier vs baseline |
| --- | ---: | ---: | ---: |
| baseline `prob_up_h20` | 無法計算 | 0.2526 | 0.0000 |
| direction-only logistic | 無法計算 | 0.1654 | -0.0872 |
| CSM-lite logistic | 無法計算 | 0.1652 | -0.0874 |
| CSM-lite HGB | 無法計算 | 0.0154 | -0.2372 |

AUC 無法計算原因：

- 評估樣本幾乎全為正向 h20 label。
- 第一個 fold 訓練資料為單一類別，因此 evaluator 使用 base-rate fallback，並在 `one_class_fallback` 記錄。

No-add 檢查，`prob <= 0.45`：

| 模型 | active days | nonpositive precision | active mean forward return |
| --- | ---: | ---: | ---: |
| baseline | 21 | 0.0% | +19.69% |
| CSM-lite logistic | 12 | 0.0% | +20.68% |
| CSM-lite HGB | 0 | 無樣本 | 無樣本 |

解讀：

- 2026 recent 是強多頭樣本，不能用 AUC 評估。
- CSM-lite 低機率日仍對應高正報酬，不可作 no-add。

### 2022 rate-hike

未回測。

原因：

- 目前可用的 00631L NCF panel 有 2017-2019、2020、2025-2026。
- 沒有 2022 對應的 `ncf_00631l_panel_backfill_2022...csv`。
- 若硬用沒有 NCF panel 的資料，會和本次 CSM-lite 設計不一致，不能公平比較 baseline `prob_up_h20`。

資料缺口記錄：

- 若未來要測 2022，需要先產生 2022 00631L NCF backfill panel。

## 為什麼不導入最新策略

不導入 live / 最新策略，原因如下：

- 主視窗沒有擊敗既有 NCF `prob_up_h20`。
- 2020 stress window 更弱。
- no-add 低機率日 precision 不足，甚至 active mean return 為正。
- CSM 原論文是月頻 S&P 500，不是日頻 00631L。
- 若接 live，可能讓 GroupA+ 錯過 00631L 上漲期。

## 最終決策

`2606.04153v1.pdf` 有概念價值，但本次 empirical shadow 不支持導入 GroupA+ 最新策略。

保留：

- `scripts/evaluate/evaluate_csm_lite_00631l_shadow.py`
- 本交接文件
- results 研究輸出

不做：

- 不接 `daily_signal.py`
- 不新增 live alert
- 不做 no-add guard
- 不改 target weights

## 驗證命令

語法檢查：

```bash
.venv/bin/python -m py_compile scripts/evaluate/evaluate_csm_lite_00631l_shadow.py
```

主視窗：

```bash
.venv/bin/python scripts/evaluate/evaluate_csm_lite_00631l_shadow.py --output results/csm_lite_00631l_shadow_20250102_20260716.json
```

主視窗，含 baseline feature：

```bash
.venv/bin/python scripts/evaluate/evaluate_csm_lite_00631l_shadow.py --include-baseline-feature --output results/csm_lite_00631l_shadow_20250102_20260716_with_baseline.json
```

2020 stress：

```bash
.venv/bin/python scripts/evaluate/evaluate_csm_lite_00631l_shadow.py --panel results/ncf_00631l_panel_backfill_2020_20260716.csv --start 2020-01-02 --end 2020-12-31 --n-splits 3 --gap 20 --output results/csm_lite_00631l_shadow_2020_backfill.json
```

2018 correction：

```bash
.venv/bin/python scripts/evaluate/evaluate_csm_lite_00631l_shadow.py --panel results/ncf_00631l_panel_backfill_2017_2019_20260710.csv --start 2018-01-02 --end 2018-12-31 --n-splits 3 --gap 20 --output results/csm_lite_00631l_shadow_2018_correction.json
```

2026 recent：

```bash
.venv/bin/python scripts/evaluate/evaluate_csm_lite_00631l_shadow.py --panel results/ncf_00631l_panel_latest_20260716.csv --start 2026-01-02 --end 2026-07-16 --n-splits 3 --gap 20 --output results/csm_lite_00631l_shadow_2026_recent.json
```

## 後續建議

不要繼續微調 CSM-lite 參數追求單一視窗最佳。

若未來要重啟：

- 先改成多 horizon：h5 / h10 / h20。
- target 改成 `00631L relative vs 0050`，而不是單純 `00631L forward_gain_h20`。
- 使用 walk-forward expanding window，而不是只靠 TimeSeriesSplit。
- 必須先證明 no-add precision 在 2020、2022、2025-2026 都穩定。
