# FinRL 台股量化交易系統 - 系統設計文件

## 版本資訊
- **版本**: 2.0.0
- **更新日期**: 2026-06-15
- **狀態**: Phase 1-5 全部完成

---

## 1. 系統架構總覽

```
FinRL/
├── v2/                          # FinRL v2 核心系統
│   ├── data/                    # 資料層
│   │   ├── data_loader.py       # 台股數據載入器（Yahoo Finance + TWSE API）
│   │   ├── technical_indicators.py  # 技術指標計算（TA-Lib / Pandas）
│   │   └── stock_db.py          # SQLite 資料庫管理
│   │
│   ├── environments/            # 環境層
│   │   ├── taiwan_stock_env.py  # Gym-style 交易環境（52維 state）
│   │   ├── action_space.py      # 動作空間定義（離散/連續）
│   │   └── reward_function.py   # 複合獎勵函數
│   │
│   ├── agents/                  # Agent 層
│   │   ├── ppo_agent.py         # PPO (近端策略優化) Agent
│   │   ├── a2c_agent.py         # A2C (Advantage Actor-Critic) Agent
│   │   ├── sac_agent.py         # SAC (Soft Actor-Critic) Agent
│   │   └── train.py             # 統一訓練介面
│   │
│   ├── backtesting/             # 回測層
│   │   ├── backtest_engine.py   # 回測引擎
│   │   ├── performance_metrics.py  # 績效指標
│   │   └── visualizer.py        # 視覺化（Equity Curve, Drawdown）
│   │
│   └── requirements.txt         # 依賴套件
│
├── data/                        # 數據存儲
│   ├── stock_data.db            # SQLite 快取資料庫
│   └── portfolio_cache/         # Parquet 格式快取
│
└── results/                     # 訓練/回測結果
```

---

## 2. 台股特殊規則

| 規則 | 數值 | 說明 |
|------|------|------|
| 涨跌停限制 | ±10% | 當日價格不能超過前一日收盤價的 ±10% |
| T+2 交割 | - | 成交後第2個交易日完成資金和股票交割 |
| 最小交易單位 | 1000 股 | 1張為一單位 |
| 最大持有 | 40000 股 | 40張為上限 |
| 手續費 | 0.15% | 券商折扣後 |
| 交易稅 | 0.3% | 僅賣出時收取 |
| 停損門檻 | -5% | 未實現虧損超過5%時自動停損 |

---

## 3. State Space（52維）

### 3.1 價格特徵（6維）
| 特徵 | 維度 | 說明 |
|------|------|------|
| open, high, low, close | 4 | OHLC 價格 |
| volume | 1 | 成交量 |
| turnover | 1 | 成交額 |

### 3.2 技術指標（44維）
| 指標群 | 維度 | 說明 |
|--------|------|------|
| MA 系列 | 7 | MA3, MA5, MA10, MA20, MA60, MA120, MA240 |
| MA 交叉 | 1 | 快速MA與慢速MA交叉信號 |
| MA 比率 | 3 | 價格/MA 的比率 |
| MA 斜率 | 3 | MA 的變化率 |
| MACD | 5 | MACD, Signal, Histogram, OS, DS |
| RSI | 2 | RSI(6), RSI(12) |
| KDJ | 3 | K, D, J 值 |
| 威廉指標 | 1 | Williams %R |
| Bollinger Bands | 3 | Upper, Middle, Lower Band |
| ATR | 1 | Average True Range |
| DMI | 3 | +DI, -DI, ADX |
| MFI | 1 | Money Flow Index |
| 動量 | 4 | 1/3/5/10 日動量 |
| 位置 | 2 | 價格位置（近期高低點的%） |
| 成交量特徵 | 1 | 量增信號 |

### 3.3 型態特徵（8維）
| 特徵 | 維度 | 說明 |
|------|------|------|
| 突破高點 | 1 | 突破N日高點 |
| 跌破低點 | 1 | 跌破N日低點 |
| 成交量爆發 | 1 | 成交量異動 |
| 動量信號 | 1 | 動量方向 |
| 震幅 | 1 | 當日高低點差異 |
| 連續漲跌 | 1 | N日連續漲跌 |
| 跳空 | 1 | 跳空缺口 |
| 趨勢強度 | 1 | 趨勢明確程度 |

### 3.4 法人特徵（8維）
| 特徵 | 維度 | 說明 |
|------|------|------|
| 外資淨買超 | 1 | 外國機構投資人買賣超 |
| 投信淨買超 | 1 | 境內投信基金淨買超 |
| 自營商淨買超 | 1 | 券商自營部位淨買超 |
| 法人總計 | 1 | 三大法人合計淨買超 |

### 3.5 部位特徵（4維）
| 特徵 | 維度 | 說明 |
|------|------|------|
| 持倉比例 | 1 | 持股數 / 最大持股 |
| 市值佔比 | 1 | 持股市值 / 總市值 |
| 未實現損益率 | 1 | 未實現損益 / 初始資金 |
| 成本偏離率 | 1 | 成本價偏離率 |

---

## 4. Action Space

### 4.1 離散動作空間（9類）
| Action ID | 名稱 | 說明 |
|-----------|------|------|
| 0 | HOLD | 觀望，不做任何操作 |
| 1 | BUY_1000 | 買入 1000 股（1張） |
| 2 | SELL_1000 | 賣出 1000 股（1張） |
| 3 | CLOSE_POSITION | 清倉（賣出全部持股） |
| 4 | STOP_LOSS | 停損（強制賣出全部持股） |
| 5 | BUY_3000 | 買入 3000 股（3張） |
| 6 | SELL_3000 | 賣出 3000 股（3張） |
| 7 | BUY_5000 | 買入 5000 股（5張） |
| 8 | SELL_5000 | 賣出 5000 股（5張） |

### 4.2 連續動作空間
- 動作值域: [-1, 1]
- 映射為目標持倉比重 [0, 1]

---

## 5. 獎勵函數（Composite Reward）

### 5.1 獎勵組成
| 組成部分 | 權重 | 說明 |
|----------|------|------|
| Capital Reward | 100x | 投資組合市值變化率（主要獎勵） |
| Holding Bonus | 0.1 | 持有獲利部位時的小獎勵 |
| Trade Penalty | 0.001 | 避免過度交易的小懲罰 |
| Stop Loss Penalty | 0.05 | 停損動作的懲罰 |
| Drawdown Penalty | 0.5x | 最大回撒懲罰（回撤>20%時） |
| Win Rate Bonus | 0.1x | 勝率獎勵（勝率>50%時） |

---

## 6. Agent 演算法

### 6.1 PPO（近端策略優化）
| 超參數 | 數值 | 說明 |
|--------|------|------|
| learning_rate | 3e-4 | 學習率 |
| n_steps | 2048 | 每次收集的樣本數 |
| batch_size | 64 | 批次大小 |
| n_epochs | 10 | 更新次數 |
| gamma | 0.99 | 折扣因子 |
| clip_range | 0.2 | PPO Clip 範圍 |

### 6.2 A2C（Advantage Actor-Critic）
| 超參數 | 數值 | 說明 |
|--------|------|------|
| learning_rate | 3e-4 | 學習率 |
| n_steps | 2048 | 每次收集的樣本數 |
| gamma | 0.99 | 折扣因子 |
|gae_lambda | 0.95 | GAE Lambda |

### 6.3 SAC（Soft Actor-Critic）
| 超參數 | 數值 | 說明 |
|--------|------|------|
| learning_rate | 3e-4 | 學習率 |
| buffer_size | 100000 | 經驗回放緩衝區大小 |
| gamma | 0.99 | 折扣因子 |
| tau | 0.005 | 軟更新參數 |

---

## 7. 回測績效指標

| 指標 | 說明 |
|------|------|
| Total Return | 總回報率 |
| Sharpe Ratio | 夏普比率（風險調整後收益） |
| Max Drawdown | 最大回撤 |
| Win Rate | 勝率 |
| Profit Factor | 盈利因子（總盈利/總虧損） |
| Calmar Ratio | 卡爾馬比率（年化收益/最大回撤） |
| Sortino Ratio | 索提諾比率（只考慮下行風險） |
| Trade Count | 總交易次數 |

---

## 8. 數據來源

### 8.1 Yahoo Finance（主要）
- 速度：快
- 免費：是
- 數據完整性：高
- 台股代碼格式：2330.TW, 0050.TW

### 8.2 TWSE API（三大法人）
- 提供：外資、投信、自營商買賣超
- API 端點：https://www.twse.com.tw/rwd/zh/fund/T86

### 8.3 本地快取
- SQLite：stock_data.db
- Parquet：portfolio_cache/*.parquet

---

## 9. 安裝方式

```bash
# 1. 安裝依賴
cd /mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/FinRL/v2
pip install -r requirements.txt

# 2. 驗證安裝
python -c "from FinRL.v2 import TaiwanStockTradingEnv; print('OK')"
```

---

## 10. 使用範例

```python
from FinRL.v2 import TaiwanStockTradingEnv, PPOAgent
from FinRL.v2.data import TaiwanStockDataLoader
from FinRL.v2.data.technical_indicators import TechnicalIndicators

# 1. 載入數據
loader = TaiwanStockDataLoader()
df = loader.load('2330', '2020-01-01', '2024-12-31')

# 2. 計算技術指標
ti = TechnicalIndicators(df)
df = ti.calculate_all()

# 3. 創建環境
env = TaiwanStockTradingEnv(df, mode='discrete')

# 4. 訓練 Agent
agent = PPOAgent(env)
agent.train(total_timesteps=100000)

# 5. 回測
from FinRL.v2.backtesting import run_backtest
results, equity, trades = run_backtest(df, agent)
```

---

## 11. 檔案清單

### 資料層
- `FinRL/v2/data/data_loader.py` - 台股數據載入器
- `FinRL/v2/data/technical_indicators.py` - 技術指標計算（TA-Lib / Pandas）
- `FinRL/v2/data/stock_db.py` - SQLite 資料庫管理
- `FinRL/v2/data/__init__.py` - 子模組初始化

### 環境層
- `FinRL/v2/environments/taiwan_stock_env.py` - Gym-style 交易環境（52維 state）
- `FinRL/v2/environments/action_space.py` - 動作空間定義
- `FinRL/v2/environments/reward_function.py` - 複合獎勵函數
- `FinRL/v2/environments/__init__.py` - 子模組初始化

### Agent 層
- `FinRL/v2/agents/ppo_agent.py` - PPO Agent
- `FinRL/v2/agents/a2c_agent.py` - A2C Agent
- `FinRL/v2/agents/sac_agent.py` - SAC Agent
- `FinRL/v2/agents/train.py` - 統一訓練介面
- `FinRL/v2/agents/__init__.py` - 子模組初始化

### 回測層
- `FinRL/v2/backtesting/backtest_engine.py` - 回測引擎
- `FinRL/v2/backtesting/performance_metrics.py` - 績效指標
- `FinRL/v2/backtesting/visualizer.py` - 視覺化
- `FinRL/v2/backtesting/__init__.py` - 子模組初始化

### 配置文件
- `FinRL/v2/requirements.txt` - 依賴套件
- `FinRL/v2/__init__.py` - 主初始化檔案