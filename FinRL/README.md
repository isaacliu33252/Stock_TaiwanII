# FinRL 台股量化交易系統

基於深度強化學習 (Deep Reinforcement Learning) 的台股自動化交易系統。

## 📁 專案結構

```
FinRL/
├── __init__.py              # 專案初始化
├── requirements.txt          # 依賴套件
├── README.md                # 本文件
│
├── config/                   # 設定模組
│   ├── __init__.py
│   ├── taiwan_stock_config.py   # 台股交易規則
│   └── hyperparameters.py       # Agent 超參數
│
├── data/                     # 數據處理層
│   ├── __init__.py
│   ├── data_loader.py            # 台股數據載入器
│   ├── technical_indicators.py   # 技術指標計算
│   └── feature_engineering.py    # 特徵工程
│
├── environments/              # RL 環境層
│   ├── __init__.py
│   ├── taiwan_stock_env.py       # 主交易環境 (52維狀態)
│   ├── action_space.py           # 離散動作空間 (5類)
│   └── reward_function.py        # 複合獎勵函數
│
├── agents/                    # Agent 代理層
│   ├── __init__.py
│   ├── ppo_agent.py              # PPO 訓練器
│   ├── a2c_agent.py              # A2C 訓練器
│   └── train.py                  # 訓練主腳本
│
├── backtesting/               # 回測層
│   ├── __init__.py
│   ├── backtest_engine.py         # 回測引擎
│   ├── performance_metrics.py     # 績效指標計算
│   └── visualizer.py             # 視覺化模組
│
├── results/                    # 結果輸出
│   ├── __init__.py
│   ├── plotter.py
│   └── result_tracker.py
│
└── config.py                   # 舊版設定 (相容性)
```

## 🎯 系統架構

### 狀態空間 (52維)

| 類別 | 維度 | 範例特徵 |
|------|------|---------|
| 價格特徵 | 6 | close, open, high, low, volume, turnover |
| 技術指標 | 20 | MA, MACD, RSI, KDJ, BB, ATR |
| 型態特徵 | 8 | 突破信號、量增、動量 |
| 基本面特徵 | 8 | 三大法人淨買、殖利率、PE、PB |
| 部位特徵 | 6 | 持股、未實現盈虧、最大回撒 |
| 市場情緒 | 4 | 大盤報酬、波動率 |

### 動作空間 (5類離散)

| 動作 | 值 | 說明 |
|------|-----|------|
| HOLD | 0 | 觀望，不動作 |
| BUY_1000 | 1 | 買入 1000 股 |
| SELL_1000 | 2 | 賣出 1000 股 |
| CLOSE_POSITION | 3 | 清倉 |
| STOP_LOSS | 4 | 停損 |

### 台股特殊規則

- **涨跌停限制**: 10%
- **T+2 交割**: 當日買入，T+2 才能賣出
- **最小交易單位**: 1000 股 (一張)
- **最大持股**: 4000 股 (4 張)

## 🚀 快速開始

### 1. 安裝依賴

```bash
cd FinRL
pip install -r requirements.txt
```

### 2. 訓練模型

```bash
python agents/train.py --stock 2330 --agent ppo --timesteps 100000
```

### 3. 評估模型

```bash
python agents/train.py --stock 2330 --agent ppo --eval_only
```

## 📊 績效指標

系統計算以下指標：

- **Total Return**: 總報酬率
- **Sharpe Ratio**: 夏普比率
- **Max Drawdown**: 最大回撒
- **Win Rate**: 勝率
- **Profit Factor**: 利潤因子
- **Calmar Ratio**: 卡爾瑪比率
- **Annual Return**: 年化報酬率

## 📦 主要模組

### TaiwanStockDataLoader
從 Yahoo Finance 和 TWSE API 取得台股數據。

### TaiwanStockTradingEnv
Gym-style 交易環境，實現 52 維狀態空間和 5 類離散動作。

### PPOTrainer / A2CTrainer
使用 Stable-Baselines3 的 PPO/A2C 演算法進行訓練。

### BacktestEngine
完整的回測框架，支援績效計算和視覺化。

## 📝 使用範例

```python
from FinRL.data.data_loader import TaiwanStockDataLoader
from FinRL.data.technical_indicators import TechnicalIndicators
from FinRL.environments.taiwan_stock_env import TaiwanStockTradingEnv
from FinRL.agents.ppo_agent import PPOTrainer

# 1. 載入數據
loader = TaiwanStockDataLoader()
df = loader.download_price_data('2330', '2020-01-01', '2024-12-31')

# 2. 計算技術指標
ti = TechnicalIndicators(df)
df = ti.calculate_all()

# 3. 建立環境
env = TaiwanStockTradingEnv(df)

# 4. 訓練模型
trainer = PPOTrainer(env, env)
trainer.train(total_timesteps=50000)

# 5. 評估
results = trainer.evaluate(env, n_episodes=10)
```

## ⚙️ 配置參數

### 台股規則 (taiwan_stock_config.py)

```python
TAIWAN_STOCK_CONFIG = {
    'trade_unit': 1000,       # 最小交易單位
    'max_position': 4000,     # 最大持股
    'price_limit': 0.10,     # 涨跌停 10%
    'commission_rate': 0.0015, # 佣金 0.15%
    'tax_rate': 0.003,        # 證交稅 0.3%
}
```

### PPO 超參數 (hyperparameters.py)

```python
PPO_CONFIG = {
    'n_steps': 2048,           # 採樣步數
    'batch_size': 64,         # 批次大小
    'n_epochs': 10,           # 更新 epoch 數
    'gamma': 0.99,            # 折扣因子
    'clip_range': 0.2,        # PPO clipping
    'learning_rate': 3e-4,    # 學習率
}
```

## 📄 License

MIT License

## 👥 作者

FinRL 量化交易專家團隊
