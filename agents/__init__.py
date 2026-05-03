# ============================================================================
# FinRL 台股交易系統 - Agents 模組
# ============================================================================
"""
本模組包含各種強化學習 Agent 的實現。

支援的 Agent：
- PPO (Proximal Policy Optimization) - 首選
- A2C (Advantage Actor-Critic) - Baseline

使用方式：
    from agents import PPOAgent
    
    agent = PPOAgent(env)
    agent.train(total_timesteps=100000)
    action, _ = agent.predict(state)
"""

# 匯出版本資訊
__version__ = "1.0.0"

# 匯出主要類別
from .ppo_agent import PPOAgent, create_ppo_agent, load_ppo_agent
from .a2c_agent import A2CAgent, create_a2c_agent, load_a2c_agent

# 向後相容性別名 (已棄用)
PPOTrainer = PPOAgent
A2CTrainer = A2CAgent

# 方便直接匯入所有 Agent
__all__ = [
    "PPOAgent", "A2CAgent",
    "create_ppo_agent", "load_ppo_agent",
    "create_a2c_agent", "load_a2c_agent",
    # 向後相容
    "PPOTrainer", "A2CTrainer"
]