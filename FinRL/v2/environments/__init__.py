"""
================================================================================
FinRL v2 台股量化交易系統 - 環境層初始化
================================================================================
這個模組包含 RL 交易環境的實現：

主要功能：
    1. TaiwanStockTradingEnv - Gym-style 交易環境（52維 state）
    2. action_space - 離散/連續動作空間定義
    3. reward_function - 複合獎勵函數

台股特殊規則：
    - 涨跌停限制: ±10%
    - T+2 交割制度
    - 最小交易單位 1000 股
    - 最大持有 40000 股

作者: FinRL量化交易專家
日期: 2026-05-23
================================================================================
"""

from .taiwan_stock_env import TaiwanStockTradingEnv
from .action_space import (
    ActionMode,
    DiscreteActions,
    ContinuousActionSpec,
    build_action_space,
    translate_action,
)
from .reward_function import (
    RewardFunction,
    composite_reward,
)

__all__ = [
    # Environment
    "TaiwanStockTradingEnv",
    # Action Space
    "ActionMode",
    "DiscreteActions",
    "ContinuousActionSpec",
    "build_action_space",
    "translate_action",
    # Reward Function
    "RewardFunction",
    "composite_reward",
]