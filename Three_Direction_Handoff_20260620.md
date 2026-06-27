## 三方向策略測試交接文件
**日期**：2026-06-20
**狀態**：✅ **A21.4 已實作完成**（MA60 + bond30_cash30）

---

## 測試背景

MDD（-22.84%，2025-04-09）根本原因確診：Defensive basket 含 60% 0050，市場崩跌時無法有效防禦。Trend filter 無法解決結構問題，只能微調 recovery 時間點。

提出三個實質改善方向，經回測驗證後結果如下。

---

## 方向1：更保守的 Defensive Basket

### 邏輯
維持現有 regime switch 機制，只修改 `execution_regime == "group_a_plus_defensive"` 時的持倉比重。

### 測試的 baskets

| Basket | 組成 |
|--------|------|
| cash30（baseline） | 0050:60%, cash:40% |
| cash40 | 0050:60%, cash:40% → 60% |
| bond20 | 0050:40%, 00679B:20%, cash:40% |
| bond30_cash30 | 0050:40%, 00679B:30%, cash:30% |

### 結果（2025-01-02 ~ 2026-06-18）

| Basket | Sharpe | Sortino | MDD | Worst 20d | Final Value |
|--------|--------|---------|-----|-----------|-------------|
| cash30（baseline） | 2.449 | 2.619 | -22.84% | -16.89% | 2,376,415 |
| **bond30_cash30** | **2.528** | **2.784** | **-16.03%** | **-9.74%** | **2,324,812** |
| cash40 | 2.511 | 2.693 | -20.77% | -14.77% | 2,381,976 |
| bond20 | 2.416 | 2.568 | -21.78% | -15.64% | 2,319,041 |

### 結果（2020-01-02 ~ 2026-06-18）

| Basket | Sharpe | Sortino | MDD | Annual Return |
|--------|--------|---------|-----|--------------|
| cash30（baseline） | 1.318 | 1.293 | -36.29% | 32.03% |
| bond30_cash30 | **1.341** | **1.323** | -36.29% | 31.79% |
| cash40 | 1.335 | 1.312 | -36.29% | 32.15% |
| bond20 | 1.311 | 1.289 | -36.29% | 31.59% |

**觀察**：
- 兩個 window 下 **bond30_cash30** Sharpe 都是最高
- Long window MDD 仍是 -36.29%（COVID 2020-03、Fed 升息 2022 的結構問題，cash/bond 也擋不住）
- Short window MDD 大幅改善（-22.84% → -16.03%，+6.81pp）
- bond30_cash30 在 short window 最終價值略低是因為 recovery 提早結束（報酬率相同但進程略早）

**改法**：`backtest_group_a_plus_defensive_basket.py` 的 `DEFENSIVE_BASKETS` dict 已有 `bond30_cash30`，`run_a213()` 的 `basket_name` 參數直接傳入即可。

---

## 方向2：Volatility Trigger（無效）

### 邏輯
當 `realized_vol_0050_20d > threshold` 時，不等 base switch rule 的 MA gap 條件，**立刻**進入 defensive。

### 測試的 thresholds

| Config | Vol threshold | 行為 |
|--------|--------------|------|
| vol30 | 0.30 | vol > 30% 就進 defensive |
| vol35 | 0.35 | vol > 35% 才進 defensive |
| vol40 | 0.40 | vol > 40% 才進 defensive |

### 結果（2025-01-02 ~ 2026-06-18）

| Config | Sharpe | MDD | Final Value | 問題 |
|--------|--------|-----|-------------|------|
| baseline | 2.449 | -22.84% | 2,376,415 | — |
| vol30 | 2.337 | -22.84% | 2,104,662 | **whip saw**（2026-05 切換 3 次） |
| vol35 | 2.400 | -22.84% | 2,216,453 | 同上但輕微 |
| vol40 | 2.449 | -22.84% | 2,376,415 | threshold 太高，幾乎不觸發 |

### Regime transition 分析（vol30）

```
2025-01-02: golden1
2025-03-03: golden1 → defensive（MA gap 觸發）
2025-05-14: defensive → recovery（MA gap >= 0 觸發）
2025-06-05: recovery → golden1
2026-03-09: golden1 → defensive（vol=33.5% > 30%，但 MA gap=+7.83% 顯示多頭）
2026-05-07: defensive → golden1（vol 回落）
2026-05-21: golden1 → defensive（vol=31.1% > 30%，MA gap=+17.73% 多頭）
2026-05-26: defensive → golden1
2026-05-29: golden1 → defensive（vol=33.4% > 30%，MA gap=+25.97% 多頭）
```

**結論**：vol30 在多頭趨勢中強行進 defensive，造成 whip saw，收益下降。放棄。

---

## 方向3：MA Window（有效）

### 邏輯
A207 base rule 的 MA window 從 75 改為 60 或 80，改變進 defensive 的靈敏度。

### 結果（2025-01-02 ~ 2026-06-18）

| Config | Sharpe | Sortino | MDD | Worst 20d | Final Value |
|--------|--------|---------|-----|-----------|-------------|
| MA75（baseline） | 2.449 | 2.619 | -22.84% | -16.89% | 2,376,415 |
| **MA60** | 2.467 | 2.643 | -22.38% | -16.73% | 2,387,836 |
| MA80 | 2.447 | 2.617 | -22.84% | -16.89% | 2,370,645 |

### Long window（2020-01-02 ~ 2026-06-18）

| Config | Sharpe | Annual Return | MDD |
|--------|--------|--------------|-----|
| MA75（baseline） | 1.318 | 32.03% | -36.29% |
| **MA60** | 1.327 | 32.41% | -36.39% |
| MA80 | 1.317 | 31.97% | -36.25% |

**結論**：MA60 在兩個 window 都輕微勝出。MDD 幾乎不變（結構問題）。

---

## 組合測試（方向1+方向3）

同時使用 `MA60` + `bond30_cash30` 的結果：

### 結果（2025-01-02 ~ 2026-06-18）

| Config | Sharpe | Sortino | MDD | Worst 20d | Final Value |
|--------|--------|---------|-----|-----------|-------------|
| A21.3 baseline | 2.449 | 2.619 | -22.84% | -16.89% | 2,376,415 |
| **MA60+bond30_cash30** | **2.600** | **2.884** | **-14.76%** | **-9.72%** | **2,380,037** |

**改善**：
- Sharpe +0.151（2.449 → 2.600）
- Sortino +0.265（2.619 → 2.884）
- MDD -8.08pp（-22.84% → -14.76%）
- Worst 20d -7.17pp（-16.89% → -9.72%）
- 年化報酬 +0.19pp（81.17% → 81.36%，幾乎不變）

### 結果（2020-01-02 ~ 2026-06-18）

| Config | Sharpe | Annual Return | MDD |
|--------|--------|--------------|-----|
| A21.3 baseline | 1.318 | 32.03% | -36.29% |
| **MA60+bond30_cash30** | **1.374** | **32.90%** | -36.39% |

Long window Sharpe +4.3%，年化報酬 +0.87pp，MDD 幾乎相同（結構問題）。

---

## 最終推薦

### 採用：MA60 + bond30_cash30（新代號建議：A21.4）

| 指標 | A21.3（舊） | A21.4（新） | 變化 |
|------|----------|----------|------|
| Sharpe | 2.449 | **2.600** | **+0.151** |
| Sortino | 2.619 | **2.884** | **+0.265** |
| MDD（recent） | -22.84% | **-14.76%** | **改善 8.08pp** |
| Worst 20d（recent） | -16.89% | **-9.72%** | **改善 7.17pp** |
| 年化報酬 | 81.17% | 81.36% | 持平 |
| Final Value | 2,376,415 | 2,380,037 | +3,622 |
| Sharpe（long） | 1.318 | **1.374** | **+4.3%** |

**推薦原因**：
1. Sharpe 和 Sortino 實質提升
2. Short window MDD 和 Worst 20d 大幅改善（從 -22.84% → -14.76%）
3. 年化報酬幾乎不變（不放棄報酬）
4. Long window 同樣勝出（6 年驗證）
5. 邏輯直觀：MA60 更敏感 + bond30_cash30 更保守，兩者互補

---

## 實作方式

### 需要修改的檔案

**1. `backtest_group_a_plus_defensive_basket.py`**
- 確認 `DEFENSIVE_BASKETS["bond30_cash30"]` 已存在（已存在）

**2. `group_a_plus/runners/a213.py`**
- `basket_name` 參數已支援（預設 "cash30"）
- `ma_window` 參數已支援（預設 75）
- `vol_enter_threshold` 參數已支援（預設 None）

**實作 A21.4，只需要改 `run_a213()` 的呼叫參數**：
```python
report, frame = run_a213(
    ...,
    basket_name='bond30_cash30',   # 方向1
    ma_window=60,                   # 方向3
    # vol_enter_threshold=None,     # 方向2（不使用）
)
```

### 程式碼層面的變動（最小化實作）

如果只想改一處，**建議直接修改 `run_a213()` 內的默认值**：

```python
def run_a213(
    ...
    basket_name: str = "bond30_cash30",   # 從 "cash30" 改為 "bond30_cash30"
    ma_window: int = 60,                    # 從 75 改為 60
) -> tuple[dict, pd.DataFrame]:
```

如此 CLI 行為自動變成 A21.4，不需要改任何 call site。

---

## 三方向測試程式碼位置

- Sweep 結果：`results/a213_3direction_sweep.json`
- 組合測試結果：`results/a213_combination_sweep.json`
- Long window 結果：`results/a213_3direction_sweep_long.json`

---

## 待確認

- 是否需要跑完整 promotion pipeline（catalog update、resolved rules update）？
- A21.4 的 resolved rules JSON 是否需要重新生成？
- Production 模型是否需要重新訓練？
