"""FinRL Taiwan package exports.

The data utilities are used by lightweight runtime and signal scripts. Keep
heavy optional modules lazy enough that missing backtesting-only dependencies do
not block those workflows.

Fable audit (2026-07-28, #8): this package (v1) and FinRL/v2/ are two
independently-evolving RL-agent implementations, not a maintained/deprecated
pair -- there is no shared code between their data/environments/agents
modules. This v1 tree (agents/{a2c,ppo,sac}_agent.py, run_backtest.py,
data/technical_indicators.py, environments/*) is its own standalone RL
experimentation pipeline; the live GroupA+ decision path
(group_a_plus/*, group_a_plus_latest_runner.py) does not import from either
FinRL tree. The one place v2 is actually consumed in production tooling is
backtest_group_a_plus_switch_policy.py, which uses
FinRL.v2.backtesting.performance_metrics for baseline/candidate metric
reconciliation -- v1 has no equivalent consumer. If you are only working on
GroupA+ strategy logic, neither tree needs to be kept in sync with the other.
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
