# FinRL 量化交易系統優化日誌

**日期：** 2026-05-01
**優化工程師：** Hermes Agent (Systematic Debugging + Writing Plans)
**專案：** Stock_taiwan2 / FinRL 台股量化交易系統

---

## 一、今日優化摘要

### ✅ 已實作修復（9個檔案，14處變更）

| 檔案 | 問題 | 修復內容 |
|------|------|----------|
| `rl_portfolio_backtest.py` | **T+2 結算制度未實作** | 新增 `pending_shares` 追蹤、結算邏輯、鎖定股數計算 |
| `rl_portfolio_backtest.py` | Sharpe std 偏誤 | 所有 `.std()` → `.std(ddof=1)` |
| `walk_forward.py` | 波動度 std 偏誤 | `.std()` → `.std(ddof=1)` |
| `portfolio_backtest.py` | 波動度 std 偏誤 | `.std()` → `.std(ddof=1)` |
| `backtesting/backtest_engine.py` | Sharpe/Sortino/Bench std 偏誤 | 3處 `.std()` → `.std(ddof=1)` |
| `data/technical_indicators.py` | BB/Volatility/Volume std 偏誤 | 3處 `.std()` → `.std(ddof=1)` |
| `data/data_processor.py` | Z-score std 偏誤 | `.std()` → `.std(ddof=1)` |
| `portfolio_data_loader.py` | BB std 偏誤 | `.std()` → `.std(ddof=1)` |
| `feature_engineering.py` | BB/Volatility std 偏誤 | 4處 `.std()` → `.std(ddof=1)` |

---

## 二、重大問題發現

### 🔴 問題 1：T+2 結算制度在 RL 回測中未實作（嚴重）

**位置：** `rl_portfolio_backtest.py` 的 `_run_single_stock()` 方法
**嚴重性：** 高 — 導致回測結果過度樂觀，無法真實反映台股 T+2 制度約束

**問題說明：**
- 原始程式碼 BUY/SELL 動作都是「立即」執行，沒有 T+2 鎖定追蹤
- 台灣股市實施 T+2 交割制度：今天買入的股票，**後天（T+2）** 才能賣出
- 這導致 RL Agent 可以「當天買當天賣」，與真實市場規則不符

**修復內容：**
```python
# 新增：pending_shares 追蹤字典
pending_shares: dict = {}  # {step -> shares bought at that step (locked until step+2)}
settled_position = 0       # 已交割、可立即賣出的持股
avg_cost_settled = 0.0     # 已交割持股的平均成本

# 每日結算邏輯：處理 T+2 股票交割
settlement_key = current_step - 2
if settlement_key in pending_shares and pending_shares[settlement_key] > 0:
    # 股票從 locked → settled
    ...

# 可賣出股數 = 總持股 - T+2 鎖定
locked_shares = sum(count for step, count in pending_shares.items()
                    if step > current_step and count > 0)
sellable = settled_position
```

**影響範圍：**
- `rl_portfolio_backtest.py` 中所有 RL vs BH 回測結果
- 此前 RL Agent 看起來表現好，可能是因為「當天買當天賣」的不當優勢

---

### 🟡 問題 2：所有統計指標使用 population std 而非 sample std（中等）

**位置：** 幾乎所有計算波動度/標準差的地方
**嚴重性：** 中 — 導致 Sharpe Ratio、Volatility 等指標輕微低估風險

**問題說明：**
- Pandas/NumPy 預設 `.std()` = **population std**（除 N）
- 金融統計應使用 **sample std**（除 N-1，ddof=1）
- 差異在大型資料集時約 0.5%，但在小樣本（如單檔股票年化）可達 2-3%

**修復範例：**
```python
# 修復前
volatility = daily_returns.std() * np.sqrt(252)

# 修復後
volatility = daily_returns.std(ddof=1) * np.sqrt(252)
```

**影響檔案：** 見上方表格

---

## 三、程式碼品質問題

### 🟡 重複程式碼：`detect_anomalies()` 有兩個版本

**位置：**
- `data/data_processor.py`：`detect_anomalies()` 方法（定義於 line 176）
- `data/feature_engineering.py`：獨立的 `detect_anomalies()` 函數

**問題：** 兩者功能相同但實作略有不同，可能導致行為不一致
**建議：** 統一使用 `DataProcessor.detect_anomalies()`，或合併為共用工具函數

---

### 🟡 `volume_normalized` 欄位名稱不一致

**位置：**
- `data/feature_engineering.py`：有 `volume_normalized`（Z-score 標準化成交量）
- `data/technical_indicators.py`：也有 `volume_normalized`

**建議：** 確認兩者計算邏輯一致，避免特徵衝突

---

### 🟢 良好的設計模式（值得保留）

1. **T+2 實作（`taiwan_stock_env.py`）：** 完整正確的 T+2 結算追蹤，包含 `pending_shares` 鎖定機制
2. **RiskManager：** 完整的風控模組，包含 Kelly Criterion、停損停利、冷卻期
3. **Walk-Forward 分析：** 統計嚴謹的蒙特卡羅模擬 + Walk-Forward 框架
4. **RewardFunction：** 複合獎勵函數，考慮資本報酬、風險懲罰、持有獎勵

---

## 四、技術指標改進建議

### 建議 1：加入 OBV（On-Balance Volume）趨勢指標

**理由：** 台股成交量與價格趨勢關聯性強，OBV 可捕捉資金流向

```python
def add_obv(df):
    obv = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()
    df['obv'] = obv
    df['obv_ma5'] = obv.rolling(5).mean()
    return df
```

---

### 建議 2：加入 VWAP（Volume Weighted Average Price）

**理由：** VWAP 是機構投資人重要參考指標，有助於 RL Agent 學習合理價格區間

```python
def add_vwap(df):
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    df['vwap'] = (typical_price * df['volume']).cumsum() / df['volume'].cumsum()
    return df
```

---

### 建議 3：加入 ADX（Average Directional Index）趨勢強度

**理由：** 測量趨勢強度，幫助區分盤整與趨勢市場

---

## 五、交易策略優化建議

### 建議 1：整合 RiskManager 到 RL 環境

**現況：** `RiskManager` 是獨立模組，但未與 `TaiwanStockTradingEnv` 整合
**建議：** 在 `_validate_action()` 中呼叫 `RiskManager.get_risk_signal()` 過濾不良交易

---

### 建議 2：加入倉位大小建議（Position Sizing）

**現況：** 固定 `trade_unit = 1000` 股
**建議：** 根據 Kelly Criterion 動態調整倉位

---

### 建議 3：改善 RL State 設計

**現況：** `rl_portfolio_backtest.py` 構造的 state 只有 3 個有意義特徵，其餘 49 個都是 0.0
**建議：** 使用真實的 `TaiwanStockTradingEnv._get_state()` 而非手動構造

---

## 六、回測準確性建議

### 建議 1：加入交易成本敏感度分析

**理由：** 目前佣金/稅率是固定值，但不同券商可能不同

```python
def sensitivity_analysis(base_commission=0.001425, tax_rates=[0.003, 0.001]):
    # 測試不同交易成本下的策略表現
    ...
```

---

### 建議 2：加入滑點（Slippage）模擬

**理由：** 實盤交易有滑點，直接影響策略績效

```python
def apply_slippage(price, slippage_pct=0.001):
    return price * (1 + np.random.uniform(-slippage_pct, slippage_pct))
```

---

## 七、效能優化建議

### 建議 1：快取技術指標計算結果

**問題：** 每次訓練都重新計算 MA、MACD、RSI 等指標
**建議：** 將計算後的 DataFrame 快取至磁碟

```python
import joblib
cache_path = f"data/features_cache/{ticker}_{start}_{end}.pkl"
if os.path.exists(cache_path):
    df = joblib.load(cache_path)
else:
    df = calculate_indicators(raw_df)
    joblib.dump(df, cache_path)
```

---

### 建議 2：向量化 T+2 結算計算

**問題：** 目前 T+2 結算用 Python dict 逐日追蹤
**建議：** 使用 Pandas shift 運算實現向量化

---

## 八、建議優先順序

| 優先順序 | 項目 | 影響 |
|----------|------|------|
| 🔴 P0 | T+2 結算實作（已修復 rl_portfolio_backtest） | 回測準確性 |
| 🔴 P0 | 修復 rl_portfolio_backtest 使用真實 state | RL 訓練效果 |
| 🟡 P1 | 統一 std(ddof=1) 標準差計算（已修復） | 指標準確性 |
| 🟡 P1 | 整合 RiskManager 到 RL 環境 | 風控能力 |
| 🟢 P2 | 加入 OBV/VWAP/ADX 指標 | 特徵品質 |
| 🟢 P2 | 加入滑點模擬 | 回測真實性 |
| 🟢 P3 | 快取技術指標計算 | 執行效能 |

---

## 九、驗證方法

修復後，建議用以下方式驗證：

```bash
# 1. 測試 T+2 結算邏輯
python -c "
from rl_portfolio_backtest import RLPortfolioBacktester
# 觀察：連續兩天 BUY 後，第三天才有足夠 sellable shares
"

# 2. 驗證 std(ddof=1) 修復
python -c "
import numpy as np
arr = np.random.randn(100)
pop_std = arr.std()
samp_std = arr.std(ddof=1)
print(f'Population std: {pop_std:.6f}')
print(f'Sample std:     {samp_std:.6f}')
print(f'Difference: {(samp_std/pop_std - 1)*100:.2f}%')
"
```

---

## 十、修改檔案清單

```
rl_portfolio_backtest.py          (+55 行 T+2 邏輯, +2 行 std 修復)
walk_forward.py                   (+1 行 std 修復)
portfolio_backtest.py             (+1 行 std 修復)
backtesting/backtest_engine.py    (+3 行 std 修復)
data/technical_indicators.py      (+3 行 std 修復)
data/data_processor.py            (+1 行 std 修復)
data/feature_engineering.py       (+4 行 std 修復)
portfolio_data_loader.py          (+1 行 std 修復)
feature_engineering.py            (+1 行 std 修復)
OPTIMIZATION_LOG.md               (本檔案)
```

---

*Generated by Hermes Agent - Systematic Debugging + Writing Plans*
*Date: 2026-05-01*
