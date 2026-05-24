"""FinRL Taiwan package exports.

The data utilities are used by lightweight runtime and signal scripts. Keep
heavy optional modules lazy enough that missing backtesting-only dependencies do
not block those workflows.
"""

__version__ = "1.0.0"
__author__ = "FinRL Taiwan Team"

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
    "backtesting",
    "results",
    "strategies",
    "TaiwanStockTradingEnv",
    "ActionMode",
    "ContinuousActionSpec",
    "DynamicRewardShaper",
    "BaseStrategy",
    "GroupAFinRLXConfig",
    "GroupAFinRLXStrategy",
    "RLPortfolioConfig",
    "RLPortfolioStrategy",
    "RLCachedStrategy",
    "StrategyConfig",
    "StrategyResult",
    "BacktestEngine",
    "BacktestConfig",
    "BacktestResult",
    "FinRLXBacktestEngine",
    "GroupABridgeConfig",
    "GroupABridgeResult",
    "run_group_a_finrlx_backtest",
]
