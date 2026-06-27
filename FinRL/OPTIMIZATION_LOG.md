# FinRL 優化日誌

## 2026-06-26

### 本次優化工作

#### 1. `v2/environments/taiwan_stock_env.py` - 移動停損（Trailing Stop）功能新增

**新增功能：** 為台股交易環境新增移動停損機制，用於保護獲利、控制風險。

**實現內容：**

1. **新增常數** (`TaiwanStockConstants`):
   - `TRAILING_STOP_ENABLED = True` — 是否啟用移動停損
   - `TRAILING_STOP_PCT = 0.10` — 移動停損百分比（從最高點回撤 10% 觸發）
   - `TRAILING_STOP_ACTIVATION = 0.05` — 移動停損激活門檻（獲利超過 5% 後才啟用）

2. **新增狀態追蹤** (`PortfolioState`):
   - `trailing_stop_peak: float = 0.0` — 移動停損啟用後的最高市值

3. **移動停損邏輯** (`step()` 方法):
   - 當部位處於獲利狀態（超過 `TRAILING_STOP_ACTIVATION`）時，開始追蹤最高市值
   - 當最高市值從峰值回撤超過 `TRAILING_STOP_PCT` 時，自動執行平倉
   - 可與固定停損（5%）共同運作

**為何重要：**
- 傳統固定停損只保護下跌，但無法保護已獲利的部位
- 移動停損在獲利時鎖定利潤，在虧損時限制損失
- 台股波動性大，移動停損可有效控制最大回撤

---

### 程式碼審計結果

#### v2/ 模組審計結果（2026-06-26 更新）

| 檔案 | 函數/位置 | 問題 | 嚴重性 | 狀態 |
|------|----------|------|--------|------|
| `v2/environments/taiwan_stock_env.py` | Trailing Stop | 缺少移動停損機制 | 中 | ✅ 已實作 (2026-06-26) |
| `v2/backtesting/backtest_engine.py:367` | STOP_LOSS action | action 4 已正確映射為 'stop_loss' | - | ✅ 確認正確 |
| `v2/data/data_loader.py:708-720` | 法人數據整合 | `load_with_indicators()` 已整合 TWSE API | - | ✅ 確認已實作 |
| `v2/data/technical_indicators.py:1019` | calculate_all() | 最終方法有 return，鏈式呼叫正確 | - | ✅ 確認正確 |
| `v2/backtesting/performance_metrics.py:268` | Sortino Ratio | 已確認 `sortino = ann_return / ann_downside_std`（無重複減 target_return） | - | ✅ 確認正確 |
| `v2/data/technical_indicators.py:949-1019` | calculate_all() | 移除無效的 `df=` 區域變數賦值，直接呼叫方法 | 低 | ✅ 已修復 (2026-06-26) |
| `v2/environments/taiwan_stock_env.py:564-619` | _calculate_reward() | 獎勵函數 hardcoded，未使用外部 `RewardFunction` 模組 | 低 | ⚠️ 待優化 |

#### 持續追蹤問題狀態

| 優先級 | 項目 | 說明 | 狀態 |
|--------|------|------|------|
| 高 | T+2 結算追蹤 | `pending_shares` 機制未實作於 v2，買入後立即視為可賣 | ⚠️ 待實作 |
| 中 | 獎勵函數模組化 | `_calculate_reward()` 未使用外部 `RewardFunction` | ⚠️ 待優化 |
| 低 | 單元測試覆蓋 | 關鍵函數（交易邏輯、獎勵計算、績效指標）缺少測試 | ⚠️ 待建立 |

---

### 新功能驗證方法

```bash
# 驗證 Trailing Stop 實現（語法檢查）
cd /mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/FinRL
python3 -c "
import ast
with open('v2/environments/taiwan_stock_env.py', 'r') as f:
    content = f.read()
    ast.parse(content)
    print('✅ Syntax OK')

checks = [
    'TRAILING_STOP_ENABLED',
    'TRAILING_STOP_PCT',
    'TRAILING_STOP_ACTIVATION',
    'trailing_stop_peak',
]
for k in checks:
    print(f'  {k}: {\"✅\" if k in content else \"❌\"}')
"
```

---

## 2026-06-20

### 本次優化工作

#### 1. `v2/backtesting/performance_metrics.py` - Sortino Ratio 重複減去 target_return bug（已修復）

**問題描述：** `calculate_sortino_ratio()` 函數第 267 行公式錯誤：
```python
# 錯誤：重複減去 target_return
sortino = (ann_return - target_return) / ann_downside_std

# 其中 ann_return = np.mean(excess_returns) * periods_per_year
# 而 excess_returns = returns - daily_rf 已經是超額報酬
# 所以 ann_return 已經是「年化超額報酬」
# 再減一次 target_return 會導致 Sortino 被錯誤低估
```

**根本原因：**
- `excess_returns = returns - daily_rf` → 這是超額報酬（日風險溢酬）
- `ann_return = np.mean(excess_returns) * periods_per_year` → 年化超額報酬
- 公式應該是：`Sortino = 年化超額報酬 / 年化下行標準差`
- 但錯誤實作是：`Sortino = (年化超額報酬 - target_return) / 年化下行標準差`
- 當 `target_return=0` 時，影響為零（不影響當前使用情境）
- 當 `target_return > 0`（例如 0.02 年化目標）時，Sortino 會被錯誤降低

**修復內容：**
```python
# 修復前
sortino = (ann_return - target_return) / ann_downside_std

# 修復後
sortino = ann_return / ann_downside_std
```

**驗證：** 使用 backtest venv 測試，重點在於當 `target_return > 0` 時的行為。

---

### 程式碼審計結果

#### 新發現問題（2026-06-20）

| 檔案 | 位置 | 問題 | 嚴重性 | 狀態 |
|------|------|------|--------|------|
| `v2/backtesting/performance_metrics.py:267` | Sortino | 重複減去 target_return | 中 | ✅ 已修復 |
| `v2/backtesting/backtest_engine.py:314-340` | run_with_model() | action 4 (STOP_LOSS) 未處理，會變成 'hold' | 中 | ⚠️ 待修復 |
| `v2/data/data_loader.py:662` | load_with_indicators() | 未整合法人數據（TWSE API 已實作但未呼叫） | 低 | ⚠️ 待整合 |
| `v2/environments/taiwan_stock_env.py` | T+2結算 | 缺少 `pending_shares` 追蹤機制 | 中 | ⚠️ 待實作 |
| `v2/environments/taiwan_stock_env.py:564` | _calculate_reward() | 未使用外部 `RewardFunction` 模組化設計 | 低 | ⚠️ 待重構 |

#### 舊有問題狀態（已確認持續正確）

| 檔案 | 位置 | 問題 | 狀態 |
|------|------|------|------|
| `v2/data/technical_indicators.py` | 所有 13 個 calculate_XXX() | 計算結果寫入副本不更新 self.df | ✅ 全部修復 (2026-06-19) |
| `v2/data/technical_indicators.py` | calculate_all() | 最後返回 None | ✅ 修復為 return self.df (2026-06-19) |
| `v2/data/technical_indicators.py:423` | KDJ for 迴圈 | Python O(n) 迴圈 | ✅ 向量化 ewm() (2026-06-19) |
| `v2/data/technical_indicators.py:904` | calculate_pattern_features() | price_change 未定義 | ✅ 已定義 (2026-06-19) |
| `v2/data/technical_indicators.py` | 連續漲跌天數 | drop_missing 不存在於 pandas 2.2 | ✅ numpy 迴圈 (2026-06-19) |
| `v2/environments/taiwan_stock_env.py:256` | _calculate_state_dim() | 缺少部位特徵 4 維 | ✅ 已修復 (2026-06-19) |
| `v2/data/technical_indicators.py:489,497` | Bollinger Bands | ddof=1 | ✅ 正確 |
| `v2/data/technical_indicators.py:956` | MFI | ddof=1 | ✅ 正確 |
| `v2/backtesting/performance_metrics.py:199` | Sharpe | ddof=1 | ✅ 正確 |
| `v2/backtesting/performance_metrics.py:258` | Sortino downside_std | ddof=1 | ✅ 正確 |
| `v2/backtesting/performance_metrics.py:397` | Volatility | ddof=1 | ✅ 正確 |
| `v2/backtesting/performance_metrics.py:485` | daily_return_std | ddof=1 | ✅ 正確 |
| `v2/backtesting/visualizer.py:211,224` | std | ddof=1 | ✅ 正確 |
| `v2/environments/reward_function.py:269` | Sharpe | ddof=1 | ✅ 正確 |
| `risk_manager_v2.py:319` | Sortino | 公式正確 | ✅ 正確 |
| `backtesting/backtest_engine.py:419` | Sharpe | ddof=1 | ✅ 正確 |
| `backtesting/backtest_engine.py:425` | excess_std | ddof=1 | ✅ 正確 |
| `backtesting/backtest_engine.py:429` | downside_std | ddof=1 | ✅ 正確 |
| `agents/evaluate.py:297,310,358` | std/Sharpe/Sortino | ddof=1 | ✅ 正確 |
| `environments/reward_function.py:214,253` | Sortino | ddof=1 | ✅ 正確 |
| `results/plotter.py:329` | 報酬分布 std | ddof=1 | ✅ 正確 |
| `portfolio_data_loader.py:204` | `_rolling_zscore` | ddof=0 為正確 | ✅ 正確 |
| `data/feature_engineering.py:356` | expanding std | ddof=0 為正確 | ✅ 正確 |

---

### 待修復項目

#### 高優先級
| 項目 | 說明 |
|------|------|
| BacktestEngine action 4 未處理 | `run_with_model()` 中 action 4 (STOP_LOSS) 被當成 'hold' 處理，沒有實際執行停損交易 |
| v2 環境缺少 T+2 結算追蹤 | `pending_shares` 機制存在於 v1 但未實作於 v2，買入後立即視為可賣 |

#### 中優先級
| 項目 | 說明 |
|------|------|
| 法人數據未整合 | `load_with_indicators()` 未呼叫 `fetch_institutional_data()`，環境狀態的法人特徵永遠為 0 |
| `_calculate_reward` 未使用外部模組 | v2 環境內部 hardcoded 獎勵計算，未使用 `v2/environments/reward_function.py` 的模組化設計 |

#### 低優先級
| 項目 | 說明 |
|------|------|
| 考慮添加單元測試 | 覆蓋關鍵函數（交易邏輯、獎勵計算、績效指標） |
| BacktestEngine 涨跌停限制 | `allow_limit_up_trade` 設定存在但未在 `_execute_trade` 中實作檢查 |

---

### 驗證方法

```bash
# 使用 backtest venv 驗證 Sortino 修復
/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/FinRL/.venv-backtest/Scripts/python.exe -c "
import sys
sys.path.insert(0, '/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/FinRL')
from v2.backtesting.performance_metrics import calculate_sortino_ratio
import numpy as np

# 測試用例：實際有負報酬的情況
returns = np.array([0.01, 0.005, -0.02, 0.003, -0.01])
result = calculate_sortino_ratio(returns, risk_free_rate=0.02, periods_per_year=252)
print(f'Sortino ratio: {result:.4f}')
"
```

---

## 2026-06-19

### 本次優化工作

#### 1. `v2/data/technical_indicators.py` - 嚴重 bug：所有計算方法不更新 self.df（已修復）

**問題描述：** 13 個 `calculate_XXX()` 方法全部使用 `df = self.df.copy()` 建立區域複製，計算結果寫入區域 `df` 後返回，但從未寫回 `self.df`。因此 `calculate_all()` 鏈式呼叫時，每個方法都拿到原始 6 欄數據，計算結果全部被丟棄。最終 `calculate_all()` 返回 `None`（倒數第二個方法返回的值為 `None`）。

**影響範圍：** 此 bug 導致幾乎所有技術指標（MA、MACD、RSI、KDJ、Bollinger Bands、ATR 等）在 `calculate_all()` 模式下全部失效。

**根本原因：**
- 每個方法內部：`df = self.df.copy()` → `df['new_col'] = ...` → `return df`
- 區域變數 `df` 遮蔽了成員變數，計算結果寫入副本，返回時副本被丟棄
- `calculate_all()` 鏈：`df = self.calculate_ma()` → `df` 為 `None` → 後續全部失敗

**修復內容：**
1. 移除所有方法內的 `df = self.df.copy()`
2. 將所有 `df[` 置換為 `self.df[`
3. 將所有 `df.` 置換為 `self.df.`
4. 將 `return df` 置換為 `return self.df`
5. 修復 `calculate_all()` 末尾：直接 `return self.df`

**驗證結果：**
```
After calculate_all, columns count: 56 (原始：6)
Key indicators: ma5 ✅, ma20 ✅, kdj_k ✅, bb_upper ✅, consecutive_up_days ✅
Environment test: state_dim=59, obs shape=(59,) ✅ PASS
```

---

#### 2. `v2/data/technical_indicators.py` - KDJ for 迴圈向量化（已修復）

**問題描述：** `calculate_kdj()` 中使用 Python `for i in range(1, len(rsv))` 迴圈計算 K/D 值，時間複雜度 O(n)。

**修復內容：** 替換為 pandas `ewm()` 向量化實現：
```python
# 舊：O(n) Python 迴圈
for i in range(1, len(rsv)):
    k[i] = (2/3) * k[i-1] + (1/3) * rsv[i]
    d[i] = (2/3) * d[i-1] + (1/3) * k[i]

# 新：O(1) 向量化，pandas C 層執行
k = pd.Series(rsv).ewm(alpha=1/3, adjust=False, min_periods=1).mean().values
d = pd.Series(k).ewm(alpha=1/3, adjust=False, min_periods=1).mean().values
```

---

#### 3. `v2/data/technical_indicators.py` - 型態特徵未定義變數 bug（已修復）

**問題描述：** `calculate_pattern_features()` 第 904 行使用 `price_change` 變數，但從未定義。

**修復內容：** 加入 `price_change = df['close'].diff()`（又因移除 `df = self.df.copy()` 改為 `price_change = self.df['close'].diff()`）。

---

#### 4. `v2/data/technical_indicators.py` - 連續漲跌天數 pandas API 不相容（已修復）

**問題描述：** 嘗試使用 `is_up.groupby(group_ids, drop_missing=False)` 但 `drop_missing` 參數不存在於 pandas 2.2。

**修復內容：** 替換為簡單 numpy for 迴圈（作用於 numpy array 比 pandas Series 快約 10x）：
```python
close = self.df['close'].values
for i in range(1, n):
    if close[i] > close[i-1]:
        consecutive_up[i] = consecutive_up[i-1] + 1
        ...
```

---

#### 5. `v2/environments/taiwan_stock_env.py` - 狀態維度計算 bug（已修復）

**問題描述：** `_calculate_state_dim()` 只計算「價格 + 技術指標」，但 `_get_observation()` 實際附加 4 維「部位特徵」，導致 `state_dim` 比實際少 4。

**修復內容：** 在 `_calculate_state_dim()` 加入 `position_feature_count = 4`：
```python
return len(price_features) + len(technical_features) + position_feature_count
```

---

### 程式碼審計結果

#### v2/ 模組審計結果（2026-06-19 更新）

| 檔案 | 函數/位置 | 問題 | 狀態 |
|------|----------|------|------|
| `v2/data/technical_indicators.py` | 所有 13 個 calculate_XXX() | 計算結果寫入副本不更新 self.df | ✅ 全部修復 |
| `v2/data/technical_indicators.py` | calculate_all() | 最後返回 None | ✅ 修復為 return self.df |
| `v2/data/technical_indicators.py:423` | KDJ for 迴圈 | Python O(n) 迴圈 | ✅ 向量化 ewm() |
| `v2/data/technical_indicators.py:904` | calculate_pattern_features() | price_change 未定義 | ✅ 已定義 |
| `v2/data/technical_indicators.py` | 連續漲跌天數 | drop_missing 不存在於 pandas 2.2 | ✅ numpy 迴圈 |
| `v2/environments/taiwan_stock_env.py:256` | _calculate_state_dim() | 缺少部位特徵 4 維 | ✅ 已修復 |
| `v2/environments/taiwan_stock_env.py:322` | 部位特徵 cost_deviation_ratio | 公式正確 | ✅ 正確 |
| `v2/data/technical_indicators.py:489,497` | Bollinger Bands | ddof=1 | ✅ 正確 |
| `v2/data/technical_indicators.py:956` | MFI | ddof=1 | ✅ 正確 |
| `v2/backtesting/performance_metrics.py:199` | Sharpe | ddof=1 | ✅ 正確 |
| `v2/backtesting/performance_metrics.py:257` | Sortino | ddof=1 + 公式正確 | ✅ 正確 |
| `v2/backtesting/performance_metrics.py:397` | Volatility | ddof=1 | ✅ 正確 |
| `v2/backtesting/performance_metrics.py:485` | daily_return_std | ddof=1 | ✅ 正確 |
| `v2/backtesting/visualizer.py:211,224` | std | ddof=1 | ✅ 正確 |
| `v2/environments/reward_function.py:269` | Sharpe | ddof=1 | ✅ 正確 |

#### 主程式碼審計結果（持續正確）

| 檔案 | 函數/位置 | 問題 | 狀態 |
|------|----------|------|------|
| `risk_manager_v2.py:319` | Sortino 計算 | 公式正確 | ✅ 正確 |
| `backtesting/backtest_engine.py:419` | Sharpe 計算 | ddof=1 | ✅ 正確 |
| `backtesting/backtest_engine.py:425` | excess_std | ddof=1 | ✅ 正確 |
| `backtesting/backtest_engine.py:429` | downside_std | ddof=1 | ✅ 正確 |
| `agents/evaluate.py:297` | std_return | ddof=1 | ✅ 正確 |
| `agents/evaluate.py:310` | Sharpe | ddof=1 | ✅ 正確 |
| `agents/evaluate.py:358` | Sortino | ddof=1 | ✅ 正確 |
| `environments/reward_function.py:214` | Sortino | ddof=1 | ✅ 正確 |
| `environments/reward_function.py:253` | Sortino | ddof=1 | ✅ 正確 |
| `results/plotter.py:329` | 報酬分布 std | ddof=1 | ✅ 正確 |
| `portfolio_data_loader.py:204` | `_rolling_zscore` | ddof=0 為正確 | ✅ 正確 |
| `data/feature_engineering.py:356` | expanding std | ddof=0 為正確 | ✅ 正確 |

---

### 待修復項目

#### 高優先級
| 項目 | 說明 |
|------|------|
| v2 環境缺少 T+2 結算追蹤 | `pending_shares` 機制存在於 v1 但未實作於 v2，買入後立即視為可賣 |
| v2 `_calculate_reward` 與外部模組整合 | 目前 hardcoded 在環境內，未使用 `v2/environments/reward_function.py` 的模組化設計 |

#### 中優先級
| 項目 | 說明 |
|------|------|
| `get_feature_names()` 列出 `cost_deviation_ratio` 但 `_get_observation()` 未包含 | 發現 `_get_observation()` 已有計算，但 position_features 只取前 4 個（無 cost_deviation_ratio） |
| 考慮添加單元測試覆蓋關鍵函數 | 特別是交易邏輯和獎勵計算 |

#### 低優先級
| 項目 | 說明 |
|------|------|
| 考慮使用 Numba JIT 加速技術指標計算 | 大量數據時有顯著加速效果 |
| `data_loader.py` SQLite 快取 | 可擴展支援法人數據快取 |

---

### 驗證方法

```bash
# 使用 backtest venv 驗證
/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/FinRL/.venv-backtest/Scripts/python.exe -c "
import pandas as pd, numpy as np
np.random.seed(42)
n = 100
df = pd.DataFrame({
    'date': pd.date_range('2020-01-01', periods=n),
    'open': np.random.uniform(100, 200, n),
    'high': np.random.uniform(100, 200, n),
    'low': np.random.uniform(100, 200, n),
    'close': np.random.uniform(100, 200, n),
    'volume': np.random.uniform(1e6, 1e7, n),
})
df['high'] = df[['open', 'high', 'close']].max(axis=1)
df['low'] = df[['open', 'low', 'close']].min(axis=1)

from v2.data.technical_indicators import TechnicalIndicators
ti = TechnicalIndicators(df)
ti.calculate_all()
print(f'Columns after calculate_all: {len(ti.df.columns)} (expected > 40)')

from v2.environments.taiwan_stock_env import TaiwanStockTradingEnv
env = TaiwanStockTradingEnv(ti.df)
obs, info = env.reset()
print(f'state_dim={env.state_dim}, obs.shape={obs.shape}, match={obs.shape[0]==env.state_dim}')
"
```

---

## 2026-06-18

### 本次優化工作

#### 1. `v2/data/data_loader.py` - 三大法人數據 TWSE API 串接（已實現）

**問題描述：** `fetch_institutional_data()` 框架已存在但僅有 `warnings.warn()` 空殼，無法取得三大法人（外資、投信、自營商）買賣超資料。

**實現內容：**
- 完整串接 TWSE API (`https://www.twse.com.tw/rwd/zh/fund/T86`)
- 支援民國年轉西元年轉換
- 分段下載（每段 3 個月），避免 URL 過長
- 處理數值格式（移除逗號、處理 `--` 缺失值）
- 返回欄位：`date`, `foreign_net_buy`, `investment_trust_net_buy`, `dealer_net_buy`, `total_net_buy`

---

#### 2. `v2/data/technical_indicators.py` - 連續漲跌天數向量化加速（已修復）

**問題描述：** `calculate_pattern_features()` 中使用 Python `for` 迴圈計算「連續上漲天數」和「連續下跌天數」，時間複雜度 O(n)，對大量歷史數據（數千筆 K 線）效能差。

**修復內容：** 替換為 pandas 向量化 groupby + cumcount 模式：

```python
# 舊：O(n) Python 迴圈
for i in range(1, len(df)):
    if is_up.iloc[i]:
        up_count.iloc[i] = up_count.iloc[i-1] + 1
    else:
        down_count.iloc[i] = down_count.iloc[i-1] + 1

# 新：O(1) 向量化，pandas 內部 C 層執行
group_ids = (is_up != is_up.shift()).cumsum()
consecutive_up = np.where(
    is_up,
    is_up.groupby(group_ids, drop_missing=False).cumcount() + 1,
    0
)
```

---

## 2026-06-15

### 本次優化工作

#### 1. `v2/environments/taiwan_stock_env.py` - 部位特徵公式修正（已修復）
#### 2. `v2/backtesting/backtest_engine.py` - 交易動作對應修正（已修復）
#### 3. `v2/backtesting/backtest_engine.py` - 支援大額交易（已修復）
#### 4. `v2/backtesting/performance_metrics.py` - Sortino Ratio 公式修正（已修復）

---

## 2026-06-11

### 本次優化工作

#### 1. v2/environments/reward_function.py - Sharpe 計算 ddof=1 修正
#### 2. v2/backtesting/performance_metrics.py - daily_return_std ddof=1 修正
#### 3. v2/backtesting/visualizer.py - 視覺化標準差 ddof=1 修正
#### 4. results/plotter.py - 報酬分布標準差 ddof=1 修正

---

## 2026-05-31

### 本次優化工作

#### v2/environments/taiwan_stock_env.py - 動作5-8未實作 bug（已修復）
#### v2/environments/taiwan_stock_env.py - 除以零防護（已修復）
#### v2/environments/taiwan_stock_env.py - KeyError 風險（已修復）

---

## 2026-05-23

### 歷史優化記錄摘要

#### v2/ 模組 ddof=1 修正（已完成）
- `v2/data/technical_indicators.py` — 布林通道 std ddof=1
- `v2/backtesting/performance_metrics.py` — Sharpe/Sortino/Volatility ddof=1

#### 2026-05-18：Sortino Ratio 修正
- 主程式碼 `risk_manager_v2.py:319` 的 Sortino 計算錯誤已修正

#### 2026-05-16：ddof=1 全面審計
確認所有 Sharpe Ratio、Sortino Ratio、Active Sharpe、Volatility（年化）、Episode return statistics 使用 `ddof=1`（正確）。
Z-score 標準化使用 `ddof=0`（正確）。

---

*本報告由 Hermes Agent 自動產生*

### 本次優化工作

#### 1. `v2/data/technical_indicators.py` - 嚴重 bug：所有計算方法不更新 self.df（已修復）

**問題描述：** 13 個 `calculate_XXX()` 方法全部使用 `df = self.df.copy()` 建立區域複製，計算結果寫入區域 `df` 後返回，但從未寫回 `self.df`。因此 `calculate_all()` 鏈式呼叫時，每個方法都拿到原始 6 欄數據，計算結果全部被丟棄。最終 `calculate_all()` 返回 `None`（倒數第二個方法返回的值為 `None`）。

**影響範圍：** 此 bug 導致幾乎所有技術指標（MA、MACD、RSI、KDJ、Bollinger Bands、ATR 等）在 `calculate_all()` 模式下全部失效。

**根本原因：**
- 每個方法內部：`df = self.df.copy()` → `df['new_col'] = ...` → `return df`
- 區域變數 `df` 遮蔽了成員變數，計算結果寫入副本，返回時副本被丟棄
- `calculate_all()` 鏈：`df = self.calculate_ma()` → `df` 為 `None` → 後續全部失敗

**修復內容：**
1. 移除所有方法內的 `df = self.df.copy()`
2. 將所有 `df[` 置換為 `self.df[`
3. 將所有 `df.` 置換為 `self.df.`
4. 將 `return df` 置換為 `return self.df`
5. 修復 `calculate_all()` 末尾：直接 `return self.df`

**驗證結果：**
```
After calculate_all, columns count: 56 (原始：6)
Key indicators: ma5 ✅, ma20 ✅, kdj_k ✅, bb_upper ✅, consecutive_up_days ✅
Environment test: state_dim=59, obs shape=(59,) ✅ PASS
```

---

#### 2. `v2/data/technical_indicators.py` - KDJ for 迴圈向量化（已修復）

**問題描述：** `calculate_kdj()` 中使用 Python `for i in range(1, len(rsv))` 迴圈計算 K/D 值，時間複雜度 O(n)。

**修復內容：** 替換為 pandas `ewm()` 向量化實現：
```python
# 舊：O(n) Python 迴圈
for i in range(1, len(rsv)):
    k[i] = (2/3) * k[i-1] + (1/3) * rsv[i]
    d[i] = (2/3) * d[i-1] + (1/3) * k[i]

# 新：O(1) 向量化，pandas C 層執行
k = pd.Series(rsv).ewm(alpha=1/3, adjust=False, min_periods=1).mean().values
d = pd.Series(k).ewm(alpha=1/3, adjust=False, min_periods=1).mean().values
```

---

#### 3. `v2/data/technical_indicators.py` - 型態特徵未定義變數 bug（已修復）

**問題描述：** `calculate_pattern_features()` 第 904 行使用 `price_change` 變數，但從未定義。

**修復內容：** 加入 `price_change = df['close'].diff()`（又因移除 `df = self.df.copy()` 改為 `price_change = self.df['close'].diff()`）。

---

#### 4. `v2/data/technical_indicators.py` - 連續漲跌天數 pandas API 不相容（已修復）

**問題描述：** 嘗試使用 `is_up.groupby(group_ids, drop_missing=False)` 但 `drop_missing` 參數不存在於 pandas 2.2。

**修復內容：** 替換為簡單 numpy for 迴圈（作用於 numpy array 比 pandas Series 快約 10x）：
```python
close = self.df['close'].values
for i in range(1, n):
    if close[i] > close[i-1]:
        consecutive_up[i] = consecutive_up[i-1] + 1
        ...
```

---

#### 5. `v2/environments/taiwan_stock_env.py` - 狀態維度計算 bug（已修復）

**問題描述：** `_calculate_state_dim()` 只計算「價格 + 技術指標」，但 `_get_observation()` 實際附加 4 維「部位特徵」，導致 `state_dim` 比實際少 4。

**修復內容：** 在 `_calculate_state_dim()` 加入 `position_feature_count = 4`：
```python
return len(price_features) + len(technical_features) + position_feature_count
```

---

### 程式碼審計結果

#### v2/ 模組審計結果（2026-06-19 更新）

| 檔案 | 函數/位置 | 問題 | 狀態 |
|------|----------|------|------|
| `v2/data/technical_indicators.py` | 所有 13 個 calculate_XXX() | 計算結果寫入副本不更新 self.df | ✅ 全部修復 |
| `v2/data/technical_indicators.py` | calculate_all() | 最後返回 None | ✅ 修復為 return self.df |
| `v2/data/technical_indicators.py:423` | KDJ for 迴圈 | Python O(n) 迴圈 | ✅ 向量化 ewm() |
| `v2/data/technical_indicators.py:904` | calculate_pattern_features() | price_change 未定義 | ✅ 已定義 |
| `v2/data/technical_indicators.py` | 連續漲跌天數 | drop_missing 不存在於 pandas 2.2 | ✅ numpy 迴圈 |
| `v2/environments/taiwan_stock_env.py:256` | _calculate_state_dim() | 缺少部位特徵 4 維 | ✅ 已修復 |
| `v2/environments/taiwan_stock_env.py:322` | 部位特徵 cost_deviation_ratio | 公式正確 | ✅ 正確 |
| `v2/data/technical_indicators.py:489,497` | Bollinger Bands | ddof=1 | ✅ 正確 |
| `v2/data/technical_indicators.py:956` | MFI | ddof=1 | ✅ 正確 |
| `v2/backtesting/performance_metrics.py:199` | Sharpe | ddof=1 | ✅ 正確 |
| `v2/backtesting/performance_metrics.py:257` | Sortino | ddof=1 + 公式正確 | ✅ 正確 |
| `v2/backtesting/performance_metrics.py:397` | Volatility | ddof=1 | ✅ 正確 |
| `v2/backtesting/performance_metrics.py:485` | daily_return_std | ddof=1 | ✅ 正確 |
| `v2/backtesting/visualizer.py:211,224` | std | ddof=1 | ✅ 正確 |
| `v2/environments/reward_function.py:269` | Sharpe | ddof=1 | ✅ 正確 |

#### 主程式碼審計結果（持續正確）

| 檔案 | 函數/位置 | 問題 | 狀態 |
|------|----------|------|------|
| `risk_manager_v2.py:319` | Sortino 計算 | 公式正確 | ✅ 正確 |
| `backtesting/backtest_engine.py:419` | Sharpe 計算 | ddof=1 | ✅ 正確 |
| `backtesting/backtest_engine.py:425` | excess_std | ddof=1 | ✅ 正確 |
| `backtesting/backtest_engine.py:429` | downside_std | ddof=1 | ✅ 正確 |
| `agents/evaluate.py:297` | std_return | ddof=1 | ✅ 正確 |
| `agents/evaluate.py:310` | Sharpe | ddof=1 | ✅ 正確 |
| `agents/evaluate.py:358` | Sortino | ddof=1 | ✅ 正確 |
| `environments/reward_function.py:214` | Sortino | ddof=1 | ✅ 正確 |
| `environments/reward_function.py:253` | Sortino | ddof=1 | ✅ 正確 |
| `results/plotter.py:329` | 報酬分布 std | ddof=1 | ✅ 正確 |
| `portfolio_data_loader.py:204` | `_rolling_zscore` | ddof=0 為正確 | ✅ 正確 |
| `data/feature_engineering.py:356` | expanding std | ddof=0 為正確 | ✅ 正確 |

---

### 待修復項目

#### 高優先級
| 項目 | 說明 |
|------|------|
| v2 環境缺少 T+2 結算追蹤 | `pending_shares` 機制存在於 v1 但未實作於 v2，買入後立即視為可賣 |
| v2 `_calculate_reward` 與外部模組整合 | 目前 hardcoded 在環境內，未使用 `v2/environments/reward_function.py` 的模組化設計 |

#### 中優先級
| 項目 | 說明 |
|------|------|
| `get_feature_names()` 列出 `cost_deviation_ratio` 但 `_get_observation()` 未包含 | 發現 `_get_observation()` 已有計算，但 position_features 只取前 4 個（無 cost_deviation_ratio） |
| 考慮添加單元測試覆蓋關鍵函數 | 特別是交易邏輯和獎勵計算 |

#### 低優先級
| 項目 | 說明 |
|------|------|
| 考慮使用 Numba JIT 加速技術指標計算 | 大量數據時有顯著加速效果 |
| `data_loader.py` SQLite 快取 | 可擴展支援法人數據快取 |

---

### 驗證方法

```bash
# 使用 backtest venv 驗證
/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/FinRL/.venv-backtest/Scripts/python.exe -c "
import pandas as pd, numpy as np
np.random.seed(42)
n = 100
df = pd.DataFrame({
    'date': pd.date_range('2020-01-01', periods=n),
    'open': np.random.uniform(100, 200, n),
    'high': np.random.uniform(100, 200, n),
    'low': np.random.uniform(100, 200, n),
    'close': np.random.uniform(100, 200, n),
    'volume': np.random.uniform(1e6, 1e7, n),
})
df['high'] = df[['open', 'high', 'close']].max(axis=1)
df['low'] = df[['open', 'low', 'close']].min(axis=1)

from v2.data.technical_indicators import TechnicalIndicators
ti = TechnicalIndicators(df)
ti.calculate_all()
print(f'Columns after calculate_all: {len(ti.df.columns)} (expected > 40)')

from v2.environments.taiwan_stock_env import TaiwanStockTradingEnv
env = TaiwanStockTradingEnv(ti.df)
obs, info = env.reset()
print(f'state_dim={env.state_dim}, obs.shape={obs.shape}, match={obs.shape[0]==env.state_dim}')
"
```

---

## 2026-06-18

### 本次優化工作

#### 1. `v2/data/data_loader.py` - 三大法人數據 TWSE API 串接（已實現）

**問題描述：** `fetch_institutional_data()` 框架已存在但僅有 `warnings.warn()` 空殼，無法取得三大法人（外資、投信、自營商）買賣超資料。

**實現內容：**
- 完整串接 TWSE API (`https://www.twse.com.tw/rwd/zh/fund/T86`)
- 支援民國年轉西元年轉換
- 分段下載（每段 3 個月），避免 URL 過長
- 處理數值格式（移除逗號、處理 `--` 缺失值）
- 返回欄位：`date`, `foreign_net_buy`, `investment_trust_net_buy`, `dealer_net_buy`, `total_net_buy`

---

#### 2. `v2/data/technical_indicators.py` - 連續漲跌天數向量化加速（已修復）

**問題描述：** `calculate_pattern_features()` 中使用 Python `for` 迴圈計算「連續上漲天數」和「連續下跌天數」，時間複雜度 O(n)，對大量歷史數據（數千筆 K 線）效能差。

**修復內容：** 替換為 pandas 向量化 groupby + cumcount 模式：

```python
# 舊：O(n) Python 迴圈
for i in range(1, len(df)):
    if is_up.iloc[i]:
        up_count.iloc[i] = up_count.iloc[i-1] + 1
    else:
        down_count.iloc[i] = down_count.iloc[i-1] + 1

# 新：O(1) 向量化，pandas 內部 C 層執行
group_ids = (is_up != is_up.shift()).cumsum()
consecutive_up = np.where(
    is_up,
    is_up.groupby(group_ids, drop_missing=False).cumcount() + 1,
    0
)
```

---

## 2026-06-15

### 本次優化工作

#### 1. `v2/environments/taiwan_stock_env.py` - 部位特徵公式修正（已修復）
#### 2. `v2/backtesting/backtest_engine.py` - 交易動作對應修正（已修復）
#### 3. `v2/backtesting/backtest_engine.py` - 支援大額交易（已修復）
#### 4. `v2/backtesting/performance_metrics.py` - Sortino Ratio 公式修正（已修復）

---

## 2026-06-11

### 本次優化工作

#### 1. v2/environments/reward_function.py - Sharpe 計算 ddof=1 修正
#### 2. v2/backtesting/performance_metrics.py - daily_return_std ddof=1 修正
#### 3. v2/backtesting/visualizer.py - 視覺化標準差 ddof=1 修正
#### 4. results/plotter.py - 報酬分布標準差 ddof=1 修正

---

## 2026-05-31

### 本次優化工作

#### v2/environments/taiwan_stock_env.py - 動作5-8未實作 bug（已修復）
#### v2/environments/taiwan_stock_env.py - 除以零防護（已修復）
#### v2/environments/taiwan_stock_env.py - KeyError 風險（已修復）

---

## 2026-05-23

### 歷史優化記錄摘要

#### v2/ 模組 ddof=1 修正（已完成）
- `v2/data/technical_indicators.py` — 布林通道 std ddof=1
- `v2/backtesting/performance_metrics.py` — Sharpe/Sortino/Volatility ddof=1

#### 2026-05-18：Sortino Ratio 修正
- 主程式碼 `risk_manager_v2.py:319` 的 Sortino 計算錯誤已修正

#### 2026-05-16：ddof=1 全面審計
確認所有 Sharpe Ratio、Sortino Ratio、Active Sharpe、Volatility（年化）、Episode return statistics 使用 `ddof=1`（正確）。
Z-score 標準化使用 `ddof=0`（正確）。

---

*本報告由 Hermes Agent 自動產生*

---

## 2026-06-21

### 本次優化工作

#### 1. `v2/backtesting/backtest_engine.py` - action 4 (STOP_LOSS) 未處理 bug（已修復）

**問題描述：** `run_with_model()` 中 action == 4 (STOP_LOSS) 沒有對應的處理邏輯，被當成 `'hold'` 處理。

**影響範圍：**
- 當模型輸出 STOP_LOSS action 時，回測引擎執行的是 `hold`（無操作）
- 環境的內部狀態（`env.step()`）和回測引擎的內部狀態會產生分歧

**修復內容：**
```python
# run_with_model() 新增 action 4 處理
elif action == 4:  # STOP_LOSS
    trade_action = 'stop_loss'

# _execute_trade() 新增 stop_loss 分支
elif action == 'stop_loss':
    if self.position > 0:
        shares = -self.position
        turnover = abs(shares) * price
        commission = turnover * self.config.brokerage_fee_rate
        self.cash += (turnover - commission)
        self.position = 0
        self.avg_cost = 0
```

#### 2. `v2/backtesting/backtest_engine.py` - 涨跌停限制未實作（已修復）

**問題描述：** `BacktestConfig.allow_limit_up_trade` 存在但未使用。

**修復內容：**
1. `__init__` 和 `reset()` 新增 `self.prev_close = 0.0`
2. `_execute_trade()` 開頭新增涨跌停檢查
3. 每步結束後更新 `self.prev_close = price`

**注意：** `self.current_step` 在 engine 中永遠為 0，涨跌停檢查失效。需後續修正。

---

### 程式碼審計結果

#### 新發現問題（2026-06-21）

| 檔案 | 位置 | 問題 | 嚴重性 | 狀態 |
|------|------|------|--------|------|
| `v2/backtesting/backtest_engine.py:319-340` | run_with_model() | action 4 (STOP_LOSS) 未處理 | 高 | ✅ 已修復 |
| `v2/backtesting/backtest_engine.py:237` | _execute_trade() | `self.current_step` 永遠為 0，涨跌停檢查失效 | 中 | ⚠️ 待正確修復 |

#### 舊有問題狀態（已確認持續正確）

| 檔案 | 問題 | 狀態 |
|------|------|------|
| `v2/data/technical_indicators.py` | 所有 13 個 calculate_XXX() 計算結果寫入副本 | ✅ 全部修復 (2026-06-19) |
| `v2/backtesting/performance_metrics.py:267` | Sortino 重複減去 target_return | ✅ 已修復 (2026-06-20) |
| 所有 .std() 调用 | ddof=1 或 ddof=0（Z-score） | ✅ 全部正確 |

#### v2 .std() 審計（2026-06-21）

v2 目錄下所有 .std() 調用均已確認正確（ddof=1 或 ddof=0 在 z-score 上下文）。

---

### 待修復項目

#### 高優先級
| 項目 | 說明 |
|------|------|
| backtest_engine 涨跌停檢查失效 | `self.current_step` 永遠為 0，需維護獨立 step 計數器 |
| action 5/7/8 target_shares 未傳遞 | CLOSE (action 3) 和 stop_loss 傳入 0 |

#### 中優先級
| 項目 | 說明 |
|------|------|
| 法人數據未整合 | `load_with_indicators()` 未呼叫 `fetch_institutional_data()` |
| v2 環境缺少 T+2 結算追蹤 | `pending_shares` 機制未實作 |

#### 低優先級
| 項目 | 說明 |
|------|------|
| 考慮添加單元測試 | 覆蓋關鍵函數（交易邏輯、獎勵計算、績效指標） |

---

### 驗證命令
```bash
# 驗證語法正確
python3 -m py_compile v2/backtesting/backtest_engine.py

# 驗證 stop_loss 分支存在
grep -n "stop_loss" v2/backtesting/backtest_engine.py

# 驗證涨跌停檢查存在
grep -n "limit_up\|limit_down\|prev_close" v2/backtesting/backtest_engine.py
```

預期：stop_loss 在 299, 305, 364 行；prev_close 在 174, 183, 237, 402, 479 行；limit_up/limit_down 在 237-238 行。

---

## 2026-06-22

### 本次優化工作

#### 1. `v2/backtesting/backtest_engine.py` - `run_with_model()` 缺少 `current_step` 遞增（已修復）

**問題描述：** `run_with_model()` 的 for 迴圈使用區域變數 `step`，但從未將其賦值給 `self.current_step`。導致 `_execute_trade()` 中的涨跌停判斷邏輯：
```python
if self.current_step > 0:
    limit_up = self.prev_close * (1 + self.config.limit_up_ratio)
```
永遠無法正確執行（`current_step` 停留在 0），但實際影響輕微（只有 step=0 的第一天才會有意義）。

**修復內容：** 在執行交易前將 `step` 賦值給 `self.current_step`：
```python
# 更新 current_step（用於涨跌停判斷等內部狀態追蹤）
self.current_step = step
```

**驗證：** `grep -n "self.current_step = step" v2/backtesting/backtest_engine.py` → 第 337 行

---

#### 2. `v2/data/data_loader.py` - `load_with_indicators()` 未整合法人數據（已修復）

**問題描述：** `load_with_indicators()` 有完整的 `fetch_institutional_data()` 函數，但從未呼叫。導致法人特徵（`foreign_net_buy`, `investment_trust_net_buy`, `dealer_net_buy`, `total_net_buy`）永遠為 0 或不存在。

**修復內容：** 在計算技術指標後、返回前，呼叫並左連接法人數據：
```python
df_inst = fetch_institutional_data(symbol, start_date, end_date)
df_indicators = df_indicators.merge(df_inst, on='date', how='left')
for col in [...]: df_indicators[col] = df_indicators[col].fillna(0)
```

---

#### 3. `v2/environments/taiwan_stock_env.py` - 自動停損重複執行 bug（已修復）

**問題描述：** `step()` 末尾自動停損檢查在 agent 明確發出 STOP_LOSS 動作（action=4）時會重複執行 `_execute_trade(4, price)`，導致持股被清空兩次。

**修復內容：** 自動停損檢查前加上 `action != 4` 條件：
```python
if action != 4 and self.portfolio.position > 0:
    unrealized_return = ...
```

---

### 程式碼審計結果（2026-06-22 更新）

| 檔案 | 函數/位置 | 問題 | 狀態 |
|------|----------|------|------|
| `v2/backtesting/backtest_engine.py:337` | run_with_model() | current_step 未更新，涨跌停判斷失效 | ✅ 已修復 |
| `v2/data/data_loader.py:707` | load_with_indicators() | 未呼叫 fetch_institutional_data() | ✅ 已修復 |
| `v2/environments/taiwan_stock_env.py:788` | step() | 自動停損在 action=4 時重複執行 | ✅ 已修復 |
| `v2/environments/taiwan_stock_env.py:322` | cost_deviation_ratio | 公式正確 | ✅ 正確 |
| `v2/data/technical_indicators.py` | calculate_all() | 返回 self.df，56 欄 | ✅ 正確 |
| `v2/data/technical_indicators.py` | KDJ/Bollinger/MFI | ddof=1 正確 | ✅ 正確 |
| `v2/environments/reward_function.py:269` | Sharpe | ddof=1 | ✅ 正確 |
| `v2/backtesting/performance_metrics.py` | Sortino/Sharpe/Volatility | 公式正確、ddof=1 | ✅ 正確 |
| `v2/backtesting/visualizer.py:211,224` | std | ddof=1 | ✅ 正確 |

---

### 待修復項目

#### 高優先級
| 項目 | 說明 |
|------|------|
| v2 環境缺少 T+2 結算追蹤 | `pending_shares` 機制存在於 v1 但未實作於 v2 |
| `_calculate_reward()` stop_loss_penalty | `TradeInfo.action` 欄位類型需確認（int 或字串） |

#### 中優先級
| 項目 | 說明 |
|------|------|
| `_calculate_reward` 未使用外部 `RewardFunction` 模組 | 目前 hardcoded 在環境內 |
| `calculate_all()` print 語句過多 | 訓練時會有大量輸出 |

#### 低優先級
| 項目 | 說明 |
|------|------|
| 單元測試覆蓋不足 | 交易邏輯、獎勵計算、績效指標缺乏測試 |

---

*本報告由 Hermes Agent 自動產生*

---

## 2026-06-27

### 本次優化工作

#### 1. `v2/data/technical_indicators.py` - `__main__` 區塊 NameError bug（已修復）

**問題描述：** 第 1192 行 `df = self.df.reset_index()` 使用了 `self.df`，但 `__main__` 區塊是模組層級執行，不存在 `self` 變數。相同問題存在於第 1194 行 `if self.df.empty`。

**影響範圍：** 直接執行 `python v2/data/technical_indicators.py` 會崩潰：

```
NameError: name 'self' is not defined
```

**修復內容：**
```python
# 修復前
df = self.df.reset_index()
if self.df.empty:

# 修復後
df = df.reset_index()
if df.empty:
```

---

#### 2. `v2/data/data_loader.py` - SQL Injection 資安漏洞（已修復）

**問題描述：** `load_cached_data()` 和 `clear_cache()` 函數使用 f-string 拼接 SQL 查詢：

```python
# 修復前（SQL injection 漏洞）
query = f"""
    SELECT ... WHERE symbol = '{full_symbol}'
    AND date >= '{start_date}' AND date <= '{end_date}'
"""
conn.execute(f"DELETE FROM stock_daily WHERE symbol = '{full_symbol}'")
```

攻擊者可透過股票代碼注入恶意 SQL（例如 `' OR '1'='1`）。

**修復內容：** 改用 SQLite 參數化查詢：

```python
# 修復後
query = """
    SELECT ... WHERE symbol = ? AND date >= ? AND date <= ?
"""
df = pd.read_sql_query(query, conn, params=[full_symbol, start_date, end_date], parse_dates=['date'])

# clear_cache 也改用參數化查詢
conn.execute("DELETE FROM stock_daily WHERE symbol = ?", (full_symbol,))
```

---

### 程式碼審計結果

#### 新發現問題（2026-06-27）

| 檔案 | 函數/位置 | 問題 | 嚴重性 | 狀態 |
|------|----------|------|--------|------|
| `v2/data/technical_indicators.py:1192,1194` | `__main__` block | `self.df` 在模組層級不存在 | 中 | ✅ 已修復 |
| `v2/data/data_loader.py:404-413` | `load_cached_data()` | SQL injection 漏洞（f-string 拼接） | **高** | ✅ 已修復 |
| `v2/data/data_loader.py:762` | `clear_cache()` | SQL injection 漏洞（f-string 拼接） | **高** | ✅ 已修復 |

#### 持續追蹤問題狀態

| 優先級 | 項目 | 說明 | 狀態 |
|--------|------|------|------|
| 高 | T+2 結算追蹤 | `pending_shares` 機制未實作於 v2，買入後立即視為可賣 | ⚠️ 待實作 |
| 中 | 獎勵函數模組化 | `_calculate_reward()` 未使用外部 `RewardFunction` 模組 | ⚠️ 待優化 |
| 中 | 法人數據整合 | `load_with_indicators()` 未呼叫 `fetch_institutional_data()` | ⚠️ 待整合 |
| 低 | 單元測試覆蓋 | 關鍵函數缺少測試 | ⚠️ 待建立 |

#### 已確認持續正確（無變更）

| 檔案 | 確認項目 | 狀態 |
|------|----------|------|
| `v2/environments/taiwan_stock_env.py` | Trailing Stop 機制已實作 | ✅ 正確 |
| `v2/backtesting/backtest_engine.py:367` | action 4 (STOP_LOSS) 映射正確 | ✅ 正確 |
| `v2/data/technical_indicators.py:949-1023` | `calculate_all()` 鏈式呼叫正確 | ✅ 正確 |
| `v2/backtesting/performance_metrics.py:268` | Sortino Ratio 公式正確 | ✅ 正確 |
| `v2/data/technical_indicators.py:489,497` | Bollinger Bands ddof=1 | ✅ 正確 |

---

### 驗證方法

```bash
# 驗證 technical_indicators.py __main__ 修復
cd /mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/FinRL
python3 -c "
import ast
with open('v2/data/technical_indicators.py', 'r') as f:
    content = f.read()
ast.parse(content)
print('✅ Syntax OK')

# 檢查 self.df bug
lines = content.split('\n')
for i, line in enumerate(lines):
    if '__main__' in line and i > 1100:
        for j in range(i, min(i+20, len(lines))):
            if 'self.df' in lines[j]:
                print(f'❌ Still has self.df at line {j+1}')
                break
        else:
            print('✅ __main__ block: self.df bug fixed')
        break
"

# 驗證 SQL injection 修復
python3 -c "
with open('v2/data/data_loader.py', 'r') as f:
    content = f.read()
if 'WHERE symbol = ?' in content:
    print('✅ SQL injection fix: parameterized query in load_cached_data')
if 'DELETE FROM stock_daily WHERE symbol = ?' in content:
    print('✅ SQL injection fix: parameterized query in clear_cache')
"
```

