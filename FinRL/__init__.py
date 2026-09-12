"""FinRL Taiwan package exports.

The data utilities are used by lightweight runtime and signal scripts. Keep
heavy optional modules lazy enough that missing backtesting-only dependencies do
not block those workflows.

v2 System:
    The FinRL.v2 sub-package contains the full RL trading system with
    PPO/A2C/SAC agents, TaiwanStockTradingEnv, and backtesting engines.
    Import via: from FinRL.v2 import TaiwanStockTradingEnv, PPOAgent
    Or from here: from FinRL import TaiwanStockTradingEnv, PPOAgent
"""

__version__ = "2.0.0"
__author__ = "FinRL Taiwan Team"

# =============================================================================
# v2 RL Trading System - 動態導入
# =============================================================================
# v2 目錄位於 FinRL/FinRL/v2/（相對於頂層 FinRL/__init__.py）
# 需要將 FinRL 包的目錄加入 sys.path，才能導入 v2 模組
import sys
import os

# 取得 FinRL 包的目錄（FinRL/FinRL/）
# __file__ 在頂層 FinRL/__init__.py 載入時是 FinRL/__init__.py
# 而 FinRL 包的真正位置是 FinRL/FinRL/
# 我們需要往上找兩層：FinRL/__init__.py → FinRL目錄 → 父目錄 → + FinRL
_top_init = os.path.abspath(__file__)  # FinRL/__init__.py
_finrl_dir = os.path.dirname(_top_init)  # FinRL/
_finrl_pkg_dir = os.path.join(_finrl_dir, 'FinRL')  # FinRL/FinRL/
_v2_dir = os.path.join(_finrl_pkg_dir, 'v2')  # FinRL/FinRL/v2/

# 將 FinRL 包的目錄加入 sys.path（這樣 v2 可以被找到）
if _finrl_pkg_dir not in sys.path:
    sys.path.insert(0, _finrl_dir)  # 加入 FinRL/，讓子包 FinRL 可被找到

# 直接導入 v2 模組
import FinRL.v2 as _v2_module

# 將 v2 的導出拉到 FinRL 命名空間
for _attr in dir(_v2_module):
    if not _attr.startswith('_'):
        globals()[_attr] = getattr(_v2_module, _attr)

# 導入相對子模組（維持舊有功能）
from . import agents
from . import data
from . import environments
from . import results

try:
    from . import backtesting
    from .backtesting import (
        BacktestConfig,
        BacktestResult,
        FinRLXBacktestEngine,
        GroupABridgeConfig,
        GroupABridgeResult,
        run_group_a_finrlx_backtest,
    )
    BacktestEngine = FinRLXBacktestEngine
except ImportError:
    backtesting = None
    BacktestConfig = BacktestResult = FinRLXBacktestEngine = BacktestEngine = None
    GroupABridgeConfig = GroupABridgeResult = run_group_a_finrlx_backtest = None

try:
    from . import strategies
    from .strategies import (
        BaseStrategy,
        GroupAFinRLXConfig,
        GroupAFinRLXStrategy,
        RLCachedStrategy,
        RLPortfolioConfig,
        RLPortfolioStrategy,
        StrategyConfig,
        StrategyResult,
    )
except ImportError:
    strategies = None
    BaseStrategy = GroupAFinRLXConfig = GroupAFinRLXStrategy = RLCachedStrategy = RLPortfolioConfig = RLPortfolioStrategy = None
    StrategyConfig = StrategyResult = None

from .environments import (
    ActionMode,
    ContinuousActionSpec,
    DynamicRewardShaper,
    TaiwanStockTradingEnv,
)

__all__ = [
    "data",
    "environments",
    "agents",
    "results",
    "backtesting",
    "strategies",
    # v2 RL System
    "TaiwanStockTradingEnv",
    "PPOAgent",
    "A2CAgent",
    "SACAgent",
    "TrainingRunner",
    "TaiwanStockDataLoader",
    "TechnicalIndicators",
    "StockDatabase",
    "BacktestEngine",
    "PerformanceMetrics",
    "PerformanceResult",
    "BacktestConfig",
    "Visualizer",
    "create_data_loader",
    "create_env",
    "create_agent",
    "create_backtest_engine",
    "quick_start",
    "INITIAL_CAPITAL",
    "MAX_POSITION",
    "MIN_TRADE_UNIT",
    "BROKERAGE_FEE",
    "TRANSACTION_TAX",
    "LIMIT_UP_RATIO",
    "LIMIT_DOWN_RATIO",
    "STOP_LOSS_THRESHOLD",
    "ActionMode",
    "DiscreteActions",
    "ContinuousActionSpec",
    "build_action_space",
    "translate_action",
    "RewardFunction",
    "composite_reward",
    "train_model",
    "train_ppo",
    "train_a2c",
    "train_sac",
    "calculate_sharpe_ratio",
    "calculate_max_drawdown",
    "calculate_win_rate",
    "calculate_profit_factor",
    "run_backtest",
    "plot_equity_curve",
    "plot_drawdown",
    "plot_returns_distribution",
]
