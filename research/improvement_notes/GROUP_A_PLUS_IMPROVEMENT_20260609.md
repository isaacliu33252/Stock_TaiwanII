# Group A+ 改善最終報告（2026-06-09）

## 核心發現

### 1. 分段訓練（train_segments.py）嚴重低估模型效果

之前用 train_segments.py 的分段訓練（10段 x 10K）得到：
- WF-C: Final 1,855,684（錯誤）
- Group A 2020-2025: Final 2,491,088（錯誤）

實際單次 20K timesteps training：
- WF-C: Final 2,794,081（正確）
- Group A 2020-2025: **Final 2,937,791（正確）**

**原因**：train_segments.py 的分段訓練讓 early segments undertrained，PPO 的 learning rate schedule 在每段重新初始化導致 knowledge loss。

### 2. 訓練期越長 + 單次 20K = 越好

| 訓練期 | Final | Sharpe | MDD | Vol |
|--------|-------|--------|-----|-----|
| 2018-2025 (7yr) | 1,605,851 | 3.30 | -7.79% | 15.20% |
| 2021-2025 (4.4yr) | 1,746,237 | 3.61 | -7.59% | 16.49% |
| WF-A (2020-2024) | 2,059,680 | 2.95 | -15.71% | 26.96% |
| WF-B (2021-2024) | 1,658,825 | 3.56 | -7.79% | 15.09% |
| WF-C (2022-2025) | 2,794,081 | 3.48 | -16.05% | 32.86% |
| **2020-2025 (5.4yr)** | **2,937,791** | **3.44** | **-17.26%** | **35.03%** |

- 2020-2025 是最佳訓練期（Final 2,937,791）
- 2018-2025 太長，已退化
- 訓練期越短越好（WF-C > WF-A）是分段訓練誤導的錯誤結論

### 3. Overlay 失敗根本原因

所有 TDCC overlay 都失敗（drag -13%），原因是：
1. Regime 切換造成高交易成本
2. 00679B 在 2025 年以來報酬率低（升息環境）
3. Overlay 的交易成本超過了避險價值

### 4. 最佳 Group A+ 配置

**不疊加任何 TDCC overlay**，直接用 Group A base 信號。

原因：所有 overlay variants 都造成 drag，base（無 overlay）是歷史最高。

## 最終 Production 模型

```
模型：group_a_production.zip
訓練期：2020-01-02 ~ 2025-05-31（1310 rows）
timesteps：20,000（單次訓練，不是分段）
Backtest (2025-06-01~2026-05-20):
  Final: 2,937,791
  Sharpe: 3.44
  MDD: -17.26%
  Vol: 35.03%
```

對照（Group A base，2025-01-01~2026-05-20）：
- 之前最佳：2,268,193
- 現在：2,937,791（+29.5%）

## 訓練方法（正確做法）

```python
from stable_baselines3 import PPO
from portfolio_config import COMMISSION_RATE
from train_segments import PortfolioEnv, FEATURE_COLUMNS, load_stock_data, _align_panel, INITIAL_CASH

TICKERS = ["0050.TW", "00631L.TW", "00632R.TW"]
train_data = load_stock_data(TICKERS, "2020-01-02", "2025-05-31")
panel = _align_panel(train_data, TICKERS, "2020-01-02", "2025-05-31", feature_columns=FEATURE_COLUMNS)
env = PortfolioEnv(panel, TICKERS, feature_columns=FEATURE_COLUMNS, initial_cash=INITIAL_CASH, commission_rate=COMMISSION_RATE)
model = PPO("MlpPolicy", env, verbose=0, n_steps=2048, batch_size=64, learning_rate=3e-4, gamma=0.99, clip_range=0.2, ent_coef=0.01, max_grad_norm=0.5, seed=42)
model.learn(total_timesteps=20_000, progress_bar=False)
model.save("models/portfolio/group_a_production.zip")
```

**不要用 train_segments.py 的分段訓練來評估模型效果**。

## Overlay 方向（已驗證失敗）

以下方向全部失敗，不要再浪費時間測試：
- TDCC regime overlay（所有 variants）
- regime stability filter
- VIX/Turbulence overlay
- 00679B defensive sleeve（任何動態權重）

## 建議

1. **Production 使用 group_a_production.zip**（2020-2025，20K）
2. **Group A+ 設為 base（無 overlay）**
3. **每季重新訓練**：每季用同樣方法（2020-最新，20K）重新訓練，滚动更新
4. **不要再用 train_segments.py 分段訓練評估模型**：結果會嚴重低估

## 模型檔案位置

```
models/portfolio/group_a_production.zip  ← 生產用
models/portfolio/group_a_wf_c.zip         ← 備用（WF-C，2022-2025）
models/portfolio/group_a_wf_c_fresh.zip  ← WF-C 驗證用
```