# ============================================================================
# FinRL 台股交易系統 - Environments 模組
# ============================================================================
"""
本模組包含自定義的股票交易環境，基於 Gymnasium 框架。

功能特色：
- 台股交易規則支援（漲跌停10%、最小交易單位1000股）
- T+2 交割制度支援（當日買入無法當日賣出）
- 完整的動作空間定義（買、賣、持有、清倉、停損）
- 可自定義的 Reward 函數（複合獎勵函數）
- 52維狀態向量（價格、技術指標、型態、基本面、部位、市場情緒）

使用方式：
    import gymnasium as gym
    from .environments import TaiwanStockTradingEnv, DiscreteActions, RewardFunction
    
    env = TaiwanStockTradingEnv(df=data, initial_balance=1_000_000)
    observation, info = env.reset()
    action = env.action_space.sample()
    observation, reward, terminated, truncated, info = env.step(action)
"""

# 匯出版本資訊
__version__ = "1.0.0"

# 匯出主要類別
from environments.taiwan_stock_env import TaiwanStockTradingEnv
from environments.action_space import DiscreteActions, translate_action, is_valid_buy_action, is_valid_sell_action
from environments.reward_function import RewardFunction, simple_reward, sharpe_based_reward

# 方便直接匯入所有環境
__all__ = [
    "TaiwanStockTradingEnv",  # 主要交易環境
    "DiscreteActions",         # 離散動作空間枚舉
    "RewardFunction",          # 複合獎勵函數類
    "simple_reward",           # 簡單獎勵函數
    "sharpe_based_reward",     # Sharpe獎勵函數
    "translate_action",        # 動作翻譯
    "is_valid_buy_action",     # 買入動作有效性檢查
    "is_valid_sell_action",   # 賣出動作有效性檢查
]
