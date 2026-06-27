"""
FinRL 台股交易系統 - Environments 模組
"""

__version__ = "1.0.0"

try:
    from .taiwan_stock_env import TaiwanStockTradingEnv
    from .action_space import (
        ActionMode,
        ContinuousActionSpec,
        DiscreteActions,
        translate_action,
        is_valid_buy_action,
        is_valid_sell_action,
    )
    from .reward_function import RewardFunction, simple_reward, sharpe_based_reward
    from .reward_function_v3 import DynamicRewardShaper
except ImportError:
    from environments.taiwan_stock_env import TaiwanStockTradingEnv
    from environments.action_space import (
        ActionMode,
        ContinuousActionSpec,
        DiscreteActions,
        translate_action,
        is_valid_buy_action,
        is_valid_sell_action,
    )
    from environments.reward_function import RewardFunction, simple_reward, sharpe_based_reward
    from environments.reward_function_v3 import DynamicRewardShaper

__all__ = [
    "TaiwanStockTradingEnv",
    "DynamicRewardShaper",
    "ActionMode",
    "ContinuousActionSpec",
    "DiscreteActions",
    "RewardFunction",
    "simple_reward",
    "sharpe_based_reward",
    "translate_action",
    "is_valid_buy_action",
    "is_valid_sell_action",
]
