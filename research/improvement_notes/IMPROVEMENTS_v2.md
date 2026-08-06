# FinRL 改善建議 v2.0 實作完成
==========================================

## 已實作的三項改善：

### 1. 增強版 Reward Function
**檔案：** `environments/reward_function_v2.py`

**新增功能：**
- Sortino Ratio 獎勵（只計算下行風險）
- Calmar Ratio 獎勵
- 波動度懲罰（避免過度交易）
- 動態權重調整
- inactivity 懲罰（避免不作為）

**使用方法：**
```python
from environments.reward_function_v2 import RewardFunction

reward_func = RewardFunction(
    sortino_weight=0.2,      # Sortino 權重
    calmar_weight=0.15,      # Calmar 權重
    volatility_penalty=0.1,   # 波動度懲罰
)

total_reward, breakdown = reward_func.calculate(
    portfolio_value=1_050_000,
    previous_portfolio_value=1_000_000,
    position=2000,
    close_price=650.0,
    avg_cost=640.0,
    action=0,
    max_drawdown=0.05,
    trade_history=[],
    volatility=0.15,  # 新增
)
```

---

### 2. 增強版 Risk Manager
**檔案：** `risk_manager_v2.py`

**新增功能：**
- Early Stopping（根據 Sharpe 持續低迷）
- 動態 Kelly 倉位建議
- 單日最大虧損檢查
- 完整風險評估信號
- 與訓練流程直接整合

**使用方法：**
```python
from risk_manager_v2 import RiskManager

risk_mgr = RiskManager(
    early_stop_patience=30,         # 30步沒改善就停
    early_stop_sharpe_threshold=0.0, # Sharpe 低於 0 就考慮停
    max_daily_loss=0.05,             # 單日虧損 5% 就減倉
)

risk_mgr.reset(initial_value=1_000_000)

signal = risk_mgr.check_all(
    current_price=645.0,
    avg_cost=640.0,
    position=2000,
    current_step=50,
    days_held=10,
    portfolio_value=1_020_000,
    previous_portfolio_value=1_000_000,
)

print(signal)
# {'action': 'hold', 'reason': '...', 'risk_level': 'low', 'position_size': 0.25, 'can_trade': True}
```

---

### 3. 增強版 Walk-Forward
**檔案：** `walk_forward_v2.py`

**新增功能：**
- 與 risk_manager_v2 整合
- 統計顯著性檢驗（t-test）
- Sortino Ratio 評估
- 風險等級分類（low/medium/high/critical）
- 自動生成 JSON 報告
- Monte Carlo 準備框架

**使用方法：**
```python
from walk_forward_v2 import EnhancedWalkForward, WalkForwardConfig

config = WalkForwardConfig(
    train_window_years=2.0,   # 訓練 2 年
    test_window_days=60,       # 測試 60 天
    step_days=20,              # 每 20 天滑動
)

wf = EnhancedWalkForward(stock_data, holdings, config)
results = wf.run()
wf.print_summary()
wf.save_results('walk_forward_results.json')
```

---

### 4. 整合訓練流程 v2
**檔案：** `portfolio_train_v2.py`

**整合以上三項改善到統一訓練流程：**

```bash
# 單一股票訓練
python3 portfolio_train_v2.py --tickers 0050.TW --timesteps 100000

# 所有股票訓練
python3 portfolio_train_v2.py --all --timesteps 100000

# Walk-Forward 訓練
python3 portfolio_train_v2.py --all --walk-forward --timesteps 100000

# 停用風控（測試用）
python3 portfolio_train_v2.py --tickers 0050.TW --no-risk
```

---

## 改善效果預期：

| 指標 | 改善前 | 改善後 |
|------|--------|--------|
| Sharpe Ratio | ~0.38 | 預期 0.5+ |
| 最大回撤 | -23.5% | 預期 <15% |
| Overfitting | 可能嚴重 | 滾動視窗驗證 |
| 訓練穩定性 | 中等 | 更穩定 |

---

## 檔案清單

| 檔案 | 說明 |
|------|------|
| `environments/reward_function_v2.py` | 增強版獎勵函數 |
| `risk_manager_v2.py` | 增強版風險管理 |
| `walk_forward_v2.py` | 增強版滾動回測 |
| `portfolio_train_v2.py` | 整合訓練流程 |
| `IMPROVEMENTS_v2.md` | 本文檔 |
| `stock_recommendations_20260501.xlsx` | 股票建議（Excel） |

---

更新日期：2026-05-01