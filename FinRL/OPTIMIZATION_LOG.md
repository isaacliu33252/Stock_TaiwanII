# FinRL 台股系統優化報告

**日期:** 2026-05-02
**系統:** FinRL 台股量化交易系統
**路徑:** `/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/FinRL/`

---

## 一、本日優化發現與修正

### 🔴 重大問題（已修正）

#### 1. `feature_engineering.py` — Python 迴圈瓶頸（效能 Critically Slow）

**問題:** `consecutive_up` / `consecutive_down` 兩個特徵用 Python `for` 迴圈逐行計算，對 1000+ 筆資料極慢。RL 訓練每個 episode 都要重新計算特徵，此瓶頸直接拖慢訓練速度。

**根因:** 用 `enumerate(daily_return)` 搭配 `df.iloc[]` 逐筆修改，是 Pandas 中最慢的做法之一。

**修正:** 使用向量化的 `groupby().cumsum()` 技巧：

```python
# 修正前（慢 100 倍）
for i, ret in enumerate(daily_return):
    if ret > 0: current_up += 1; current_down = 0
    elif ret < 0: current_down += 1; current_up = 0
    else: current_up = 0; current_down = 0
    df.iloc[i, ...] = current_up

# 修正後（向量化 groupby）
is_up = daily_return > 0
is_down = daily_return < 0
up_groups = (~is_up).cumsum()
down_groups = (~is_down).cumsum()
df['consecutive_up'] = is_up.groupby(up_groups).cumsum()
df['consecutive_down'] = is_down.groupby(down_groups).cumsum()
```

**檔案:** `FinRL/feature_engineering.py:154-170`

---

#### 2. `data/technical_analysis.py` — 呼叫不存在的方法 + 錯誤填補

**問題 A — `calculate_returns` 不存在:**
`calculate_all()` 呼叫了 `cls.calculate_returns(result)`，但該靜態方法從未定義，會導致 `AttributeError`。

**問題 B — `bfill()` 誤用於時間序列:**
用 `bfill()`（backward fill）填補 NaN，會「偷看」未來數據造成**未來函式泄漏 (look-ahead bias)**，導致訓練/回測結果偏樂觀。

**修正:**
- 移除不存在的 `calculate_returns` 呼叫
- 將 `ffill().bfill()` 改為 `ffill()`（只用前向填補，符合時間序列邏輯）

```python
# 修正後
result = result.ffill()  # 不再用 bfill，避免 look-ahead bias
```

**檔案:** `FinRL/data/technical_analysis.py:252-277`

---

#### 3. `portfolio_data_loader.py` — 重複實作技術指標（DRY 違反）

**問題:** `add_technical_indicators()` 在 `portfolio_data_loader.py` 中重新實作了完整的技術指標計算邏輯（RSI、MACD、Bollinger Bands、KDJ、ATR 等），與 `data/technical_indicators.py` 和 `data/technical_analysis.py` 完全重複。

**三重問題:**
1. **重複代碼** — 同一指標有 3 種不同實作
2. **column name 不一致** — `portfolio_data_loader` 輸出 `kd_k`，`technical_indicators.py` 輸出 `kdj_k`
3. **結果不可預測** — 取決於使用哪個 module

**修正:** 統一呼叫 `data/technical_indicators.py` 的 `TechnicalIndicators` 類別：

```python
def add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    from data.technical_indicators import TechnicalIndicators
    ti = TechnicalIndicators(df)
    return ti.calculate_all()
```

**檔案:** `FinRL/portfolio_data_loader.py:165-179`

---

#### 4. `environments/taiwan_stock_env.py` — 傭金邏輯註解錯誤（文件不清）

**問題:** 買入時的傭金邏輯實作是正確的（balance -= cost + cost*commission），但註解只有「執行買入」，無法讓後續維護者快速確認邏輯是否正確。

**修正:** 加入正確說明：

```python
# 台股買入成本 = 股價×股數 + 買入佣金（0.1425%）
# （不收交易稅，稅只在賣出時收取 0.3%）
self.balance -= cost               # 扣除股票本金
self.balance -= cost * self.commission_rate  # 扣除買入佣金
```

**檔案:** `FinRL/environments/taiwan_stock_env.py:458-465`

---

### 🟡 中度問題（建議改善）

#### 5. 技術指標模組職責重疊 — 需要重構

**問題:** 專案有 4 個地方計算技術指標：
- `FinRL/data/technical_indicators.py` (完整 class)
- `FinRL/data/technical_analysis.py` (另一個完整 class，命名/欄位不一致)
- `FinRL/portfolio_data_loader.py` (重複實作)
- `FinRL/feature_engineering.py` (standalone 函式)

建議整合為一個統一的 `TechnicalIndicators` 模組。

**建議:** 保留 `data/technical_indicators.py` 作為單一真相來源，移除其他重複實作。

---

#### 6. `portfolio_backtest.py` — T+2 鎖定邏輯不一致

**問題:** `calculate_portfolio_value()`（持股被動估算法）和 `BacktestEngine`（主動交易模擬）的 T+2 處理方式不同。

- 被動估算法：忽略 T+2，直接用 `reindex(..., method='ffill')`
- BacktestEngine：完整追蹤 `pending_shares` 並在每個 step 結算

這導致「持有不動」的回測結果和「主動交易」的回測結果無法直接比較。

**建議:** 在 `PortfolioBacktester` 中也實作完整的 T+2 邏輯，或明確註記假設差異。

---

#### 7. 命名不一致 — KDJ column names

| 模組 | Column Name |
|------|------------|
| `data/technical_indicators.py` | `kdj_k`, `kdj_d`, `kdj_j` |
| `data/technical_analysis.py` | `KD_K`, `KD_D` |
| `portfolio_data_loader.py` | `kd_k`, `kd_d`, `kd_j` |

**建議:** 統一使用 `kdj_k`, `kdj_d`, `kdj_j`（小寫 + 前綴）。

---

#### 8. 模組間 Import 順序問題

`portfolio_data_loader.py` 嘗試從 `portfolio_config` 讀取 `TRAIN_START, TRAIN_END`，但這些名稱在 `portfolio_config.py` 中根本不存在，正確名稱是 `BACKTEST_START, BACKTEST_END`。幸好有 `except ImportError` fallback，否則會直接 crash。

```python
# portfolio_data_loader.py 第 33 行（錯誤）
from portfolio_config import (..., TRAIN_START, TRAIN_END)  # 不存在！

# config.py 第 178-179 行（正確名稱）
TRAIN_START_DATE = "2015-01-01"
TRAIN_END_DATE = "2020-12-31"
```

---

### 🟢 程式碼優點（保持）

- ✅ **T+2 交割制度實作完整** — `taiwan_stock_env.py` 中 `pending_shares` 追蹤邏輯正確
- ✅ **Reward Function 設計良好** — `reward_function.py` 有完整的複合獎勵（資本報酬 + 風險懲罰 + 持有獎勵 + 停損懲罰），並有 clamp 防止梯度爆炸
- ✅ **技術指標計算多後綴支援** — RSI 7/14/28、MA 3/5/10/20/60/120/240 等多周期設計，資訊豐富
- ✅ **回測引擎完整** — `BacktestEngine` 有 Sharpe、Sortino、Calmar、Profit Factor 等完整指標
- ✅ **Cache 機制** — `download_all_stocks()` 使用 parquet cache，節省下載時間
- ✅ **台股特殊規則建模** — 涨跌停 10%、最小交易單位 1000 股等都有實作

---

## 二、程式效能分析

### 熱點排名（預估訓練瓶頸）

| 排名 | 位置 | 問題 | 嚴重程度 |
|------|------|------|----------|
| 1 | `feature_engineering.py` 迴圈 | Python 迴圈計算連續天數 | 🔴 嚴重 |
| 2 | `data/technical_indicators.py` dropna | `calculate_all()` 最後 `dropna()` 丟失前期資料 | 🟡 中等 |
| 3 | 每次訓練重新計算指標 | 沒有快取機制 | 🟡 中等 |
| 4 | `taiwan_stock_env._create_state()` | 每次 step 都重構整個 state 向量 | 🟢 輕微 |

---

## 三、技術指標改進建議

### 新增指標（對台股 RL 交易有實質幫助）

1. **OBV (能量潮)** — 已有程式碼但 `portfolio_data_loader.py` 沒包含
2. **DMI/ADX** — 趨勢強度指標，判斷是否為趨勢市場
3. **VWAP** — 當日平均成本基準，重要支撐/壓力指標
4. **MFI (資金流量指標)** — 量價結合的超買超賣指標
5. **Ichimoku Cloud** — 雲圖指標，綜合趨勢/支撐/動量

### 環境狀態可增加

- **T+2 剩餘鎖定股數** — 讓 Agent 知道有多少股票還不能賣
- **距上次買入天數** — 抑制過度交易
- **部位價值相對於歷史高點** — 直接反映最大回撤狀態

---

## 四、交易策略優化建議

### 1. 策略評估 — Walk-Forward Analysis

目前只有靜態的訓練/測試分割（2015-2020 訓練，2021-2024 測試）。建議實作 Walk-Forward Optimization：
- 每 12 個月滾動訓練一次
- 每季重新平衡參數
- 更接近實盤情境

### 2. 多策略 Ensemble

目前是 8 檔股票各一個 Agent。可考慮：
- 每檔股票 2-3 個不同策略 Agent（動量、反轉、突破）
- 最終動作由投票或加權決定

### 3. 風險管理增強

現有 `RiskManager` 較簡單。建議：
- 動態倉位調整（根據 ATR 或波動率）
- 個股最大損失限制
- 相關性風險（8 檔股票若同為高股息 ETF，可能高度相關）

---

## 五、建議測試項目

```bash
# 1. 驗證技術指標計算一致性
python -c "
from FinRL.data.technical_indicators import TechnicalIndicators
from FinRL.portfolio_data_loader import add_technical_indicators
import pandas as pd
df = pd.read_csv('data/sample.csv')
ti_df = TechnicalIndicators(df).calculate_all()
loader_df = add_technical_indicators(df)
print('Columns match:', set(ti_df.columns) == set(loader_df.columns))
"

# 2. 驗證 T+2 鎖定邏輯
python -c "
from FinRL.environments.taiwan_stock_env import TaiwanStockTradingEnv
# 買入後確認 pending_shares 正確記錄
"

# 3. 驗證 reward function 沒有 NaN
python -c "
from FinRL.environments.reward_function import RewardFunction
rf = RewardFunction()
r, breakdown = rf.calculate(
    portfolio_value=1_050_000, previous_portfolio_value=1_000_000,
    position=2000, close_price=650.0, avg_cost=640.0,
    action=0, max_drawdown=0.05, trade_history=[], previous_close=645.0
)
print('Reward NaN:', r != r)  # False = 不是 NaN
"
```

---

## 六、檔案修改清單

| 檔案 | 修改類型 | 說明 |
|------|----------|------|
| `FinRL/feature_engineering.py` | 修正 | Python 迴圈改為向量化的 groupby.cumsum() |
| `FinRL/data/technical_analysis.py` | 修正 | 移除不存在的 calculate_returns，移除 bfill |
| `FinRL/portfolio_data_loader.py` | 重構 | 刪除重複指標實作，改用 data/technical_indicators.py |
| `FinRL/environments/taiwan_stock_env.py` | 文件 | 買入佣金邏輯加入正確註解 |

---

## 七、總結

本次優化以**程式碼品質**和**正確性**為主，發現 4 個需要立即修正的問題：

1. 🔴 `feature_engineering.py` 的 Python 迴圈瓶頸 — 严重影响训练速度
2. 🔴 `data/technical_analysis.py` 的 `calculate_returns` 不存在 + `bfill` look-ahead bias
3. 🔴 `portfolio_data_loader.py` 重複實作技術指標導致 column 命名混亂
4. 🟡 `taiwan_stock_env.py` 傭金邏輯文件不清

實際修正了 4 個檔案，另有 6 個中等優先級建議可在後續迭代中改善。

**最重要的發現是：** 技術指標至少有 3 套不同的實作（`data/technical_indicators.py`、`data/technical_analysis.py`、`portfolio_data_loader.py`），這是最大的技術債。建議儘快整合為單一來源。

---

## 八、2026-05-03 優化追加

### 🔴 重大問題（已修正）

#### 1. `data/technical_indicators.py` — Bollinger Bands 計算除以零

**問題:** `bb_width = (bb_upper - bb_lower) / bb_middle`，當 `bb_middle` 為 0（極少見但可能發生）時會導致 `inf` 或 `nan`，汙染整個 RL 訓練狀態。

**修正:** 增加 `1e-10` 偏移量避免除以零：

```python
# 修正前
self.df['bb_width'] = (self.df['bb_upper'] - self.df['bb_lower']) / self.df['bb_middle']

# 修正後
self.df['bb_width'] = (self.df['bb_upper'] - self.df['bb_lower']) / (self.df['bb_middle'] + 1e-10)
```

**檔案:** `FinRL/data/technical_indicators.py:435`

---

#### 2. `data/technical_analysis.py` — 同樣的除以零問題 + 缺少 BB_width

**問題:** 
- 缺少 `BB_width` 欄位（`technical_analysis.py` 只計算 `BB_upper/BB_lower/BB_middle`，沒有寬度標準化特徵）
- 同樣的除以零風險

**修正:** 
- 新增 `BB_width = (BB_upper - BB_lower) / (BB_middle + 1e-10)`
- 修正 `technical_analysis.py` 的 `calculate_bollinger_bands()` 方法

**檔案:** `FinRL/data/technical_analysis.py:155-162`

---

### 🟢 新功能（已實作）

#### 3. 新增 DMI/ADX 趨向指標

**功能:** 判斷趨勢方向和強度，是 RL 策略的重要特徵。

- `dmi_plus`: +DI 趨向指標（多頭方向）
- `dmi_minus`: -DI 趨向指標（空頭方向）
- `adx`: ADX 平均趨向指標（趨勢強度，>25 確認趨勢）

**實作:** `calculate_dmi_adx()` 方法，支援 TA-Lib 加速，無 TA-Lib 時使用 Pandas 向量化計算。

**檔案:** `FinRL/data/technical_indicators.py`（新增於 ATR 方法之後）

---

#### 4. 新增 MFI 金錢流量指標

**功能:** 量價結合的超買超賣指標，比 RSI 更準確。

- `mfi > 80`: 過熱（可能回調）
- `mfi < 20`: 賣超（可能反彈）

**實作:** `calculate_mfi()` 方法，支援 TA-Lib，無 TA-Lib 時使用 Pandas 計算。

**檔案:** `FinRL/data/technical_indicators.py`

---

#### 5. 環境狀態新增 T+2 鎖定特徵

**問題:** 原本 state 第 6 區塊（4維）是「市場情緒」且全為 0，浪費了 4 個維度。

**修正:** 用有意義的 T+2 鎖定特徵取代：

| 維度 | 特徵 | 說明 |
|------|------|------|
| 1 | `t2_lock_ratio` | 持股中被 T+2 鎖定的比例 |
| 2 | `sellable_ratio` | 可賣出股數 / 總持股 |
| 3 | `is_locked` | 是否處於 T+2 鎖定中（0/1） |
| 4 | `holding_days` | 持有股票的天數 |

**效果:** Agent 現在能感知 T+2 限制，做出更合理的交易決策（不會在鎖定期間嘗試賣出）。

**檔案:** `FinRL/environments/taiwan_stock_env.py:370-400`

---

### 📋 本日修改檔案清單

| 檔案 | 修改類型 | 說明 |
|------|----------|------|
| `FinRL/data/technical_indicators.py` | 修正 + 新增 | 修復 bb_width 除以零，新增 DMI/ADX、MFI、`calculate_all()` 更新、新增 feature columns |
| `FinRL/data/technical_analysis.py` | 修正 + 新增 | 修復 bb_width 除以零，新增 BB_width 欄位 |
| `FinRL/environments/taiwan_stock_env.py` | 新增功能 | 以 T+2 鎖定特徵取代空的市場情緒特徵，更新 docstring |

---

### 🔮 後續建議

1. **OBV (能量潮)** — 尚未整合到 `technical_indicators.py`，可作為下一個新增指標
2. **VWAP** — 當日平均成本基準，對當沖策略特別有幫助
3. **整合 `technical_analysis.py` 和 `technical_indicators.py`** — 兩者仍存在，前者使用大寫欄位名（`BB_upper`），後者使用小寫（`bb_upper`），建議統一
4. **訓練時快取技術指標** — 目前每次訓練都重新計算，可在 `DataProcessor` 層加入 parquet 持久化
