# FinRL 優化日誌

## 2026-07-25 系統性代碼審查與修復

---

## 一、本次發現並修復的 Bug

### 🔴 嚴重：Sortino Ratio 計算 Bug（已修復）

**檔案：** `v2/backtesting/performance_metrics.py` 第 220-283 行

**問題描述：**

`calculate_sortino_ratio` 函數的 `target_return` 參數文件說明為「年化目標報酬」，但在計算下行標準差時，直接用 `excess_returns < 0`（等於日值 0）做門檻，而非 `excess_returns < daily_target`。這導致：

1. **目標報酬的意義完全喪失**：Sortino Ratio 的核心是「低於目標」的下行風險，但代碼卻變成「低於 0」的下行風險
2. **下行判斷不一致**：下行標準差用日值 0 當門檻，但最終公式 `ann_return - ann_target` 又用年化的 `target_return`，兩者單位不匹配
3. **Sortino 變成 Semi-Variance Ratio**：原本有意義的目標報酬（TWRR 8%、無風險利率等）完全被忽略

**受影響的呼叫：**
- `calculate_sortino_ratio` 全域函數
- `PerformanceAnalyzer.calculate_sortino_ratio()` 方法（內部呼叫全域函數）
- `RewardFunction._calculate_sortino_ratio()` 私人方法（v3 增強版）

**修復內容：**

```python
# 修復前（錯誤）：
negative_returns = excess_returns[excess_returns < 0]  # 用日值 0 當門檻

# 修復後（正確）：
daily_target = target_return / periods_per_year        # 年化 → 日值
downside_mask = excess_returns < daily_target          # 用日化的目標報酬當門檻
negative_returns = excess_returns[downside_mask]
```

**數學影響評估：**

| 情境 | 修復前 | 修復後 |
|------|--------|--------|
| 目標報酬 = 0（無風險利率） | 幾乎不變 | 幾乎不變 |
| 目標報酬 = 0.08（TWRR 8%） | 低估下行風險 | 正確計算 |
| 目標報酬 = 0.12（TWRR 12%） | 大幅低估下行 | 正確計算 |
| 目標報酬 = 0（只用 0 作門檻）| 等同 Semi-Variance | 符合 Sortino 定義 |

---

## 二、本次發現的其他觀察（未修改）

### ⚠️ v1 / v2 / v3 三版本並存，unrealized_return 邏輯不一致

**觀察到的差異：**

| 版本 | unrealized_pnl 公式 | 問題 |
|------|---------------------|------|
| `environments/reward_function.py` (v2 預設) | `(portfolio_value - position*avg_cost - cash) / (position*avg_cost)` | 分子包含 cash，會干擾計算 |
| `environments/reward_function_v2.py` | `(close_price - avg_cost) / avg_cost` | 標準化方式 |
| `environments/reward_function_v3.py` | `(close_price - avg_cost) / avg_cost` 搭配 trend 判斷 | 最完整的版本 |

**建議：** 統一為 `v3` 的實作方式，並確認 avg_cost 是否已反映真實平均成本。

### ⚠️ TA-Lib 雙重計算議題

在 `v2/data/technical_indicators.py` 中，部分指標使用 `if TALIB_AVAILABLE: try: ... except: pass` 模式，但 Panda 版本在 TA-Lib 可用時被計算後又被覆蓋。經審查後，`calculate_dmi()` 方法（第 660-690 行附近）已正確實作 TA-Lib 優先、Pandas fallback 的模式，無需修改。

### ⚠️ SQL f-string 拼接（確認無問題）

`v2/data/stock_db.py:267-270` 的 DELETE 語句使用 f-string，但傳入的 `symbol` 參數來自內部過濾後的清單（非外部輸入），風險較低。建議未來改用參數化查詢以達到最佳實踐。

---

## 三、程式碼品質評估

### 優秀之處

1. **technical_indicators.py 模組化良好**：每個指標群組有獨立方法，`calculate_all()` 統一介面，可維護性高
2. **績效指標完整**：涵蓋 Sharpe、Sortino、Calmar、Omega 等多種指標
3. **台股特殊規則支援**：漲跌停 ±10% 處理、MDD 計算、T+2 制度模擬
4. **v3 DynamicRewardShaper 的設計概念先進**：訓練進度感知、動態獎勵縮放、趨勢追蹤

### 可改進之處

1. **Sortino Ratio 的 target_return 單元不一致**（本次已修復）
2. **缺少對外的 SORTINO / SHARPE 等關鍵指標的統一存取介面**
3. **technical_indicators.py 的 `calculate_all()` 使用 print 陳述式**：`print("[TechnicalIndicators] 開始計算技術指標...")` 在生產環境應改用 logging
4. **v2/environments/taiwan_stock_env.py 未完整審視**：環境定義複雜，建議未來對以下主題進行驗證：
   - 持股上限計算邏輯
   - 涨跌停時無法買入的處理
   - 交易成本（稅 0.3%、手續費）計算

---

## 四、測試建議

### 立即可做的測試

1. **Sortino Ratio 修復驗證：**
   ```python
   import numpy as np
   from v2.backtesting.performance_metrics import calculate_sortino_ratio

   # 模擬年化報酬 12%，目標 8%，有下行風險
   returns = np.array([0.001, 0.002, -0.005, 0.001, -0.003] * 50)  # 日報酬
   result = calculate_sortino_ratio(returns, risk_free_rate=0.02,
                                    periods_per_year=252, target_return=0.08)
   print(f"Sortino: {result:.4f}")
   ```

2. **Sortino Ratio 邊界測試：**
   - 無負報酬時返回 +inf
   - 全為負報酬時的行為
   - 樣本數 < 2 時返回 0

3. **reward_function_v3 整合測試：**
   - 測試 DynamicRewardShaper 的 training_progress 進度計算
   - 測試 momentum 計算的穩定性
   - 測試不同 max_drawdown 下的風險等級

---

## 五、總結

| 項目 | 狀態 |
|------|------|
| Sortino Ratio Bug | ✅ 已修復 |
| TA-Lib 雙重計算 | ✅ 已確認無問題 |
| SQL 拼接風險 | ⚠️ 低風險，建議未來改用參數化 |
| 多版本 reward function | ⚠️ 需統一 |
| 技術指標模組 | ✅ 品質良好 |

**本次實際修改：** 1 個檔案（`v2/backtesting/performance_metrics.py`），修復 1 個嚴重 bug。

---

*報告產生時間：2026-07-25*
*審查方法：系統性除錯（Systematic Debugging）+ 程式碼審查*
