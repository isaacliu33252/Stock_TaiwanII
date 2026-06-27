"""
================================================================================
FinRL v2 台股量化交易系統 - Agent層初始化
================================================================================
這個模組包含強化學習 Agent 的實現：

主要功能：
    1. ppo_agent - PPO (近端策略優化) 訓練器
    2. a2c_agent - A2C (優勢演員-評論家) 訓練器
    3. sac_agent - SAC (軟演員-評論家) 訓練器
    4. train - 統一訓練介面

支援的演算法：
    - PPO: 離散/連續動作，穩定收斂
    - A2C: 離散/連續動作，快速訓練
    - SAC: 連續動作，最大熵

作者: FinRL量化交易專家
日期: 2026-05-23
================================================================================
"""

from .ppo_agent import PPOAgent, train_ppo
from .a2c_agent import A2CAgent, train_a2c
from .sac_agent import SACAgent, train_sac
from .train import TrainingRunner, train_model

__all__ = [
    # PPO Agent
    "PPOAgent",
    "train_ppo",
    # A2C Agent
    "A2CAgent",
    "train_a2c",
    # SAC Agent
    "SACAgent",
    "train_sac",
    # Training Runner
    "TrainingRunner",
    "train_model",
]