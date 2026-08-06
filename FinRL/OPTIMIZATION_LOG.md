# FinRL 優化日誌

## 2026-08-06 第十三輪系統性代碼審查

---

## 一、本次審查範圍

針對 FinRL 台股量化交易系統 v2 核心模組進行優化審查：

1. `v2/data/technical_indicators.py`（技術指標）
2. `v2/environments/taiwan_stock_env.py`（交易環境）
3. `v2/backtesting/performance_metrics.py`（績效指標）
4. `v2/backtesting/backtest_engine.py`（回測引擎）
5. `v2/environments/reward_function.py`（獎勵函數）

---

## 二、語法驗證

所有核心檔案通過 Python 編譯檢查：

```bash
$ python3 -m py_compile v2/data/technical_indicators.py    # ✅ OK
$ python3 -m py_compile v2/backtesting/performance_metrics.py # ✅ OK
$ python3 -m py_compile v2/environments/taiwan_stock_env.py   # ✅ OK
$ python3 -m py_compile v2/backtesting/backtest_engine.py    # ✅ OK
$ python3 -m py_compile v2/environments/reward_function.py    # ✅ OK
```

---

## 三、本次發現問題

### 🔴 問題 1：`volume_spike` 與 `volume_ratio` 完全重複

**嚴重程度：** 低（程式碼品質）
**受影響檔案：** `v2/data/technical_indicators.py`

**問題描述：**

`calculate_pattern_features()` 和 `calculate_volume_features()` 各自獨立計算了相同的指標：

```python
# calculate_pattern_features() (line 912):
self.df['volume_spike'] = self.df['volume'] / (volume_ma5 + 1e-10)

# calculate_volume_features() (line 993):
self.df['volume_ratio'] = self.df['volume'] / (self.df['volume'].rolling(window=5).mean() + 1e-10)
```

兩者公式完全相同，都是「當日成交量 / 5日均量」，只是變數名稱不同。

實測驗證：
```python
# 兩個 DataFrame 的值完全相同
volume_spike == volume_ratio: True
```

**修復內容：**

移除 `calculate_volume_features()` 中的 `volume_ratio` 計算（因為 `volume_spike` 已存在）。

```python
# 刪除 calculate_volume_features() 中的這段：
# 量比：當日成交量 / 5日均量（與 v1 一致，是 volume_spike 的另一表示）
self.df['volume_ratio'] = self.df['volume'] / (self.df['volume'].rolling(window=5).mean() + 1e-10)
```

同步更新 `get_feature_list()` 中的特徵列表，移除 `volume_ratio`。

**修復後結果：**
- 技術指標總數從 63 欄減少為 62 欄（移除 1 個重複欄位）
- `volume_ratio` 不再出現於特徵列表中
- 功能不變，指標更精簡

---

### 🟡 問題 2：技術指標文檔註釋混淆

**嚴重程度：** 低（文件品質）
**受影響檔案：** `v2/data/technical_indicators.py`

**問題描述：**

`get_feature_list()` 中「位置」區塊的註釋僅標註「rolling_mdd_period 在 calculate_position_features 中計算」，但未說明這些特徵的實際意義。

```python
# 位置
# 注意：rolling_mdd_period 在 calculate_position_features 中計算
# 使用 rolling_mdd_63 作為標準名稱（明確標示窗口大小）
features.extend(['high_252_position', 'rolling_mdd_63'])
```

**修復內容：**

將註釋改為更具資訊價值的描述：

```python
# 位置
# high_252_position: (close - 252日低點) / (252日高點 - 252日低點)
# rolling_mdd_63: 63日滾動最大回撤
features.extend(['high_252_position', 'rolling_mdd_63'])
```

---

## 四、已確認無問題的模組（上次修復後持續追蹤）

### ✅ KDJ 指標範圍修復有效（2026-08-05）

KDJ 指標的 RSV .clip(rsv, 0, 100) 修復已確認有效：

```
kdj_k range: [0.00, 100.00]    ✅
kdj_d range: [0.00, 100.00]    ✅
kdj_j range: [-32.92, 109.77]  ✅
```

### ✅ Sortino Ratio 邊界條件修復有效（2026-08-05）

Sortino Ratio 的 `downside_std < 1e-10` 處理已確認有效：

```python
All zeros - Sortino: 0.0              ✅
All same negative (-0.5%) - Sortino: 0.0  ✅
All same positive (0.5%) - Sortino: inf    ✅
```

### ✅ v2 交易環境 Position 更新（持續確認）

所有 BUY/SELL/CLOSE 動作的 position 更新均正確（2026-08-05 已驗證）。

### ✅ TA-Lib 安裝狀態

TA-Lib 當前未安裝，所有指標使用 Pandas fallback 計算。

---

## 五、本次實際修改

| 檔案 | 修改類型 | 變更 |
|------|----------|------|
| `v2/data/technical_indicators.py` | 移除重複程式碼 | 刪除 `volume_ratio` 計算（line 992-993） |
| `v2/data/technical_indicators.py` | 程式碼清理 | 更新 `get_feature_list()` 移除 `volume_ratio` |
| `v2/data/technical_indicators.py` | 文檔改進 | 改善「位置」特徵的註釋說明 |

**修改行數：** -4 行（刪除重複）+ 2 行（文檔改善）

---

## 六、架構觀察（無需修改）

### TA-Lib Double-Computation 模式分析

部分技術指標函數採用「TA-Lib 優先 + Pandas fallback」模式：

**結構 A（正確結構，如 ATR、DMI、MFI、Williams %R）：**
```python
if TALIB_AVAILABLE:
    try:
        result = talib.XXX(...)   # 使用 TA-Lib
        return self.df             # 成功後直接返回
    except:
        pass                       # TA-Lib 失敗時 pass 到 Pandas
# Pandas fallback（TA-Lib 不可用或失敗時執行）
```

**結構 B（MACD、Bollinger Bands）：**
```python
if TALIB_AVAILABLE:
    try:
        result = talib.XXX(...)   # 使用 TA-Lib
        self.df[col] = result
        return self.df             # 成功後直接返回
    except:
        pass                       # 失敗時 pass
# Pandas fallback
```

**結論：** 所有函數都正確地在 TA-Lib 成功後立即 `return`，Pandas fallback 不會在 TA-Lib 成功後執行。

**但存在一個潛在風險：** 當 `TALIB_AVAILABLE=True` 但 TA-Lib 函數拋出異常時，`pass` 陳述式會執行，控制流會落入後面的 Pandas fallback 實作。這是預期行為。

---

## 七、後續優化方向

### 1. 安裝 TA-Lib 提升效能

TA-Lib 當前未安裝，所有指標使用 Pandas fallback 計算。建議安裝以提升計算效能（約 10-50 倍加速）：

```bash
# Windows (使用 conda)
conda install -c conda-forge ta-lib

# 或使用 pip（需要先安裝 TA-Lib C 庫）
pip install ta-lib
```

### 2. 考虑引入單元測試框架

建議增加以下測試以確保程式碼品質：
- KDJ 指標範圍邊界測試（盤整資料、趨勢資料）
- Sortino Ratio 邊界條件測試（全零報酬、恆定負報酬、恆定正報酬）
- 技術指標 NaN/Inf 值檢查
- 交易環境 BUY/SELL/CLOSE 動作 position 更新驗證

### 3. 考慮使用 Polars 替代 Pandas 加速計算

對於大數據集（> 10000 行），可考虑：
- 使用 `polars` 替代 `pandas` 加速計算
- 使用 `numba` JIT 編譯熱路徑

### 4. 統一 v1/v2 架構

v1 和 v2 並存造成維護負擔。建議逐步遷移至 v2。

---

## 八、總結

| 項目 | 狀態 | 說明 |
|------|------|------|
| v2 KDJ 指標範圍 | ✅ 正確 | RSV.clip(0, 100) 修復有效 |
| v2 Sortino Ratio 邊界 | ✅ 正確 | downside_std < 1e-10 修復有效 |
| v2 交易環境 Position 更新 | ✅ 正確 | 所有動作 position 更新正確 |
| volume_spike / volume_ratio 重複 | ✅ 已修復 | 移除重複的 volume_ratio |
| 技術指標文檔註釋 | ✅ 已改善 | 位置特徵註釋更具資訊價值 |
| TA-Lib 安裝狀態 | ⚠️ 未安裝 | 使用 Pandas fallback |
| 語法驗證 | ✅ 全部通過 | 5 個核心檔案 |

**本次發現問題：** 2 個（volume_ratio 重複、文件註釋不清）
**本次修復問題：** 2 個
**累計已修復問題：** 8 個

---

## 九、驗證測試腳本

```python
import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'v2')

from v2.data.technical_indicators import TechnicalIndicators
from v2.backtesting.performance_metrics import calculate_sortino_ratio
import pandas as pd
import numpy as np

# Test 1: volume_ratio NOT in result (removed as duplicate)
np.random.seed(42)
n = 300
df = pd.DataFrame({
    'date': pd.date_range('2023-01-01', periods=n, freq='D'),
    'open': 100 + np.cumsum(np.random.randn(n) * 0.5),
    'high': 100 + np.cumsum(np.random.randn(n) * 0.5) + 2,
    'low': 100 + np.cumsum(np.random.randn(n) * 0.5) - 2,
    'close': 100 + np.cumsum(np.random.randn(n) * 0.5),
    'volume': np.random.randint(1000, 10000, n)
})

ti = TechnicalIndicators(df)
df_result = ti.calculate_all()
assert 'volume_ratio' not in df_result.columns, "volume_ratio should be removed"
assert 'volume_spike' in df_result.columns, "volume_spike should remain"
print(f"✅ volume_ratio removed, volume_spike retained")
print(f"   Total columns: {len(df_result.columns)}")

# Test 2: KDJ bounded [0, 100]
assert df_result['kdj_k'].min() >= 0 and df_result['kdj_k'].max() <= 100, "KDJ K out of range"
print("✅ KDJ bounded [0, 100]")

# Test 3: Sortino edge cases
assert calculate_sortino_ratio([0.0]*252, 0.02) == 0.0, "Sortino zeros failed"
assert calculate_sortino_ratio([-0.005]*100, 0.02) == 0.0, "Sortino constant negative failed"
print("✅ Sortino edge cases pass")

print("\nAll verification tests passed!")
```

---

*報告產生時間：2026-08-06*
*審查方法：系統性除錯（Systematic Debugging）+ 程式碼結構分析 + 單元測試*
