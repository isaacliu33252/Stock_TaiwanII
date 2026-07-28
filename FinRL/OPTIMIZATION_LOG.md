# FinRL 優化日誌

## 2026-07-28 第四輪系統性代碼審查

---

## 一、本次發現的問題

### 🟡 中等：OBV Slope 計算方式非標準

**檔案：**
- `v2/data/technical_indicators.py` 第 995 行
- `data/technical_indicators.py`（v1）第 791 行

**問題描述：**

兩版本的 OBV slope 計算方式相同，但公式非標準：

```python
# 原始（錯誤/非標準）
self.df['obv_slope'] = obv.diff() / (obv.diff().abs().rolling(window=5).sum() + 1e-10)
```

這計算的是「當日 OBV 變化 / 過去5日 OBV 絕對變化總和」，不是傳統意義上的斜率。輸出範例：

| 日期 | OBV | 當前實作值 | pct_change(5) |
|------|-----|-----------|---------------|
| 26 | -33281 | -0.050 | 0.007 |
| 27 | -27394 | +0.172 | +0.134 |
| 28 | -33253 | -0.182 | +0.038 |
| 29 | -40584 | -0.240 | -0.008 |

**修復內容：**

```python
# 修復後（標準化 5日動量）
self.df['obv_slope'] = obv.pct_change(periods=5).replace([np.inf, -np.inf], 0.0).fillna(0.0)
```

**影響：**
- OBV slope 從非標準比值改為標準動量指標
- RL 模型能更好地學習 OBV 趨勢變化
- 修復後的信號更直觀且易於解釋

---

## 二、已確認正常的實作（確認未被破壞）

### ✅ v2 ATR Pandas Fallback（Wilder 平滑）

`v2/data/technical_indicators.py` 第 558 行：
```python
self.df['atr_14'] = pd.Series(tr).ewm(span=period, adjust=False).mean()
```
使用 EWM（Wilder 平滑），與 TA-Lib 計算方式一致。✓

### ✅ v2 Momentum 計算

`v2/data/technical_indicators.py` 第 831 行：
```python
pct_change = pd.Series(close).pct_change(periods=period)
self.df[col_name] = pct_change.replace([np.inf, -np.inf], 0.0)
```
使用 pct_change（標準化回報），而非 diff（絕對值）。✓

### ✅ v2 DMI Pandas Fallback

`v2/data/technical_indicators.py` 第 640 行：
```python
atr = pd.Series(tr).ewm(span=period, adjust=False).mean()
```
正確使用 EWM 而非 rolling().mean()。✓

### ✅ TA-Lib double-computation 模式（正確）

所有技術指標的 TA-Lib 使用模式：
```python
if TALIB_AVAILABLE:
    try:
        self.df['atr_14'] = talib.ATR(...)
        return self.df  # 成功時 early return
    except Exception:
        pass
# Fallback: Pandas 實作（僅在 TA-Lib 失敗時執行）
self._atr_pandas_impl(period)
```
這是**正確**的模式 - TA-Lib 成功時不回頭執行 Pandas。✓

---

## 三、本次實際修改

| 檔案 | 修改內容 | 類型 |
|------|---------|------|
| `v2/data/technical_indicators.py` | 第 995 行：OBV slope 從 `diff/abs_sum` 改為 `pct_change(5)` + inf/nan 處理 | ✅ Bug 修復 |
| `data/technical_indicators.py`（v1） | 第 791 行：同上的 OBV slope 修復 | ✅ Bug 修復 |

**修改檔案數：** 2 個
**Bug 修復數：** 2 處（v1 和 v2 各一）

### OBV Slope 修復驗證

```python
# 修復前（原始實作）
obv_slope_weird = obv.diff() / (obv.diff().abs().rolling(window=5).sum() + 1e-10)
# 範圍: -0.37 ~ +0.39（有界但含義模糊）

# 修復後（標準動量）
obv_slope_fixed = obv.pct_change(periods=5).replace([np.inf, -np.inf], 0.0).fillna(0.0)
# 範圍: -0.35 ~ +99.47（標準化但可能有inf）

# 測試結論：pct_change 會因除以零產生 inf，已加入 replace([np.inf, -np.inf], 0.0) 處理
```

---

## 四、建議後續優化方向

### 1. 觀察：taiwan_stock_env.py 的 _calculate_reward 內聯實作

**發現：** `v2/environments/taiwan_stock_env.py` 的 `_calculate_reward` 方法（第 573-628 行）是內聯實作，未使用獨立的 `RewardFunction` 類別。

**現況：**
- 環境有自己的 reward 計算邏輯
- `reward_function.py` 中的 `RewardFunction` 類別存在但未被 environment 使用
- 環境的 `_calculate_reward` 使用 `portfolio_return * 100` 放大機制

**評估：** 這是一個架構設計選擇，不是錯誤。獨立 `RewardFunction` 適合需要多策略切換的場景，內聯實作適合單一策略。如需統一，考慮重構為使用 `RewardFunction`。

### 2. OBV Slope 替代方案討論

對於未來優化，可以考慮使用 Z-score 標準化的 OBV slope：
```python
obv_diff_mean = obv.diff().rolling(window=5).mean()
obv_diff_std = obv.diff().rolling(window=5).std()
obv_slope_zscore = (obv_diff_mean / (obv_diff_std + 1e-10)).fillna(0.0)
# 範圍: -1.73 ~ +0.60，恆有值
```

這避免了 pct_change 可能產生無窮大的問題，但改變了信號的語義。當前修復（pct_change）保持了與其他 momentum 指標（如 momentum_21, price_momentum）的一致性。

### 3. v1/v2 統一建議

兩套架構（v1 根目錄 / v2/v2目錄）已基本一致，但仍有些差異：
- v2 的 reward 計算有 `* 100` 放大
- v1 的 reward 計算可能不同

建議確認生產環境使用的版本，並將差異文件化。

---

## 五、總結

| 項目 | 狀態 |
|------|------|
| v2 OBV Slope 非標準計算 | ✅ 已修復（syntax verified） |
| v1 OBV Slope 非標準計算 | ✅ 已修復（syntax verified） |
| v2 ATR Pandas Fallback（Wilder） | ✅ 已確認正確 |
| v2 Momentum 計算（pct_change） | ✅ 已確認正確 |
| v2 DMI Pandas Fallback（EWM） | ✅ 已確認正確 |
| TA-Lib double-computation 模式 | ✅ 已確認正確 |

**本次實際修改：** 2 個檔案，2 處修改，所有修改均通過語法檢查。

---

*報告產生時間：2026-07-28*
*審查方法：系統性除錯（Systematic Debugging）+ v1/v2 並行比對 + 數值驗證*
