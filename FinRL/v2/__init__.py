"""
================================================================================
FinRL v2 台股量化交易系統 - 主初始化檔案
================================================================================
FinRL (Financial Reinforcement Learning) 台股量化交易系統

這個系統基於深度強化學習技術，專為台灣股票市場設計。

主要功能：
    - 資料層：數據取得、技術指標計算、數據庫管理
    - 環境層：Gym-style 交易環境、動作空間、獎勵函數
    - Agent層：PPO、A2C、SAC 等 RL 演算法
    - 回測層：績效指標、回測引擎、視覺化

台股特殊規則：
    - 涨跌停限制: ±10%
    - T+2 交割制度
    - 最小交易單位: 1000 股
    - 最大持有: 40000 股
    - 交易稅: 0.3%（賣出時）
    - 手續費: 0.15%（券商折扣）

使用範例:
    >>> from FinRL.v2 import TaiwanStockTradingEnv, PPOAgent
    >>> from FinRL.v2.data import TaiwanStockDataLoader
    >>> 
    >>> # 載入數據
    >>> loader = TaiwanStockDataLoader()
    >>> df = loader.load_with_indicators('2330', '2020-01-01', '2024-12-31')
    >>> 
    >>> # 創建環境
    >>> env = TaiwanStockTradingEnv(df)
    >>> 
    >>> # 訓練 Agent
    >>> agent = PPOAgent(env)
    >>> agent.train(total_timesteps=100000)
    >>> 
    >>> # 回測
    >>> from FinRL.v2.backtesting import run_backtest
    >>> results, equity, trades = run_backtest(df, agent)

作者: FinRL量化交易專家
版本: 2.0.0
日期: 2026-05-23
================================================================================
"""

# =============================================================================
# 版本資訊
# =============================================================================

__version__ = "2.0.0"
__author__ = "FinRL量化交易專家"
__description__ = "FinRL 台股量化交易系統 v2"
__license__ = "MIT"

# =============================================================================
# 基礎套件導入（必須在使用 pd.DataFrame 之前）
# =============================================================================
import pandas as pd
import gymnasium as gym


# =============================================================================
# 子模組導入
# =============================================================================

# 資料層
from .data import (
    TaiwanStockDataLoader,
    TechnicalIndicators,
    StockDatabase,
    fetch_stock_data,
    load_cached_data,
    save_to_cache,
)

# 環境層
from .environments import (
    TaiwanStockTradingEnv,
    ActionMode,
    DiscreteActions,
    ContinuousActionSpec,
    build_action_space,
    translate_action,
    RewardFunction,
    composite_reward,
)

# Agent層
from .agents import (
    PPOAgent,
    A2CAgent,
    SACAgent,
    TrainingRunner,
    train_model,
    train_ppo,
    train_a2c,
    train_sac,
)

# 回測層
from .backtesting import (
    PerformanceMetrics,
    PerformanceResult,
    BacktestEngine,
    BacktestConfig,
    Visualizer,
    calculate_sharpe_ratio,
    calculate_max_drawdown,
    calculate_win_rate,
    calculate_profit_factor,
    run_backtest,
    plot_equity_curve,
    plot_drawdown,
    plot_returns_distribution,
)


# =============================================================================
# 便捷常數
# =============================================================================

# 台股交易規則常數
INITIAL_CAPITAL = 1_000_000      # 初始資金：100萬 TWD
MAX_POSITION = 40000            # 最大持股數：40000股（40張）
MIN_TRADE_UNIT = 1000            # 最小交易單位：1000股（1張）
BROKERAGE_FEE = 0.0015           # 手續費：0.15%
TRANSACTION_TAX = 0.003          # 交易稅：0.3%（賣出時）
LIMIT_UP_RATIO = 0.10            # 漲停限制：10%
LIMIT_DOWN_RATIO = 0.10          # 跌停限制：10%
STOP_LOSS_THRESHOLD = -0.05      # 停損門檻：-5%


# =============================================================================
# 工廠函數
# =============================================================================

def create_data_loader(
    cache_dir: str = None,
    db_path: str = None,
) -> TaiwanStockDataLoader:
    """
    創建數據載入器
    
    參數:
        cache_dir: 快取目錄路徑
        db_path: SQLite 資料庫路徑
        
    返回:
        TaiwanStockDataLoader 實例
    """
    return TaiwanStockDataLoader(cache_dir=cache_dir, db_path=db_path)


def create_env(
    df: pd.DataFrame,
    mode: str = 'discrete',
    reward_mode: str = 'composite',
) -> TaiwanStockTradingEnv:
    """
    創建交易環境
    
    參數:
        df: 包含 OHLCV + 技術指標的 DataFrame
        mode: 動作模式 ('discrete' 或 'continuous')
        reward_mode: 獎勵模式 ('composite' 或 'simple')
        
    返回:
        TaiwanStockTradingEnv 實例
    """
    return TaiwanStockTradingEnv(df=df, mode=mode, reward_mode=reward_mode)


def create_agent(
    env: gym.Env,
    algo: str = 'ppo',
    **kwargs
):
    """
    創建 RL Agent
    
    參數:
        env: Gym 環境
        algo: 演算法 ('ppo', 'a2c', 'sac')
        **kwargs: 其他參數
        
    返回:
        Agent 實例
    """
    if algo.lower() == 'ppo':
        return PPOAgent(env, **kwargs)
    elif algo.lower() == 'a2c':
        return A2CAgent(env, **kwargs)
    elif algo.lower() == 'sac':
        return SACAgent(env, **kwargs)
    else:
        raise ValueError(f"不支援的演算法: {algo}")


def create_backtest_engine(
    df: pd.DataFrame,
    config: BacktestConfig = None,
    name: str = "Backtest"
) -> BacktestEngine:
    """
    創建回測引擎
    
    參數:
        df: 股價數據
        config: 回測配置
        name: 回測名稱
        
    返回:
        BacktestEngine 實例
    """
    return BacktestEngine(df=df, config=config, name=name)


# =============================================================================
# 快速開始範例
# =============================================================================

def quick_start(
    symbol: str = '2330',
    start_date: str = '2020-01-01',
    end_date: str = '2024-12-31',
    total_timesteps: int = 50000,
    algo: str = 'ppo',
):
    """
    快速開始：下載數據、創建環境、訓練 Agent、執行回測
    
    這是一個便捷函數，用於快速測試系統功能。
    
    參數:
        symbol: 股票代碼
        start_date: 開始日期
        end_date: 結束日期
        total_timesteps: 訓練步數
        algo: 演算法 ('ppo', 'a2c', 'sac')
        
    返回:
        (agent, results, equity_curve)
    """
    print("=" * 60)
    print(f"FinRL v2 快速開始")
    print(f"  股票: {symbol}")
    print(f"  期間: {start_date} ~ {end_date}")
    print(f"  演算法: {algo}")
    print(f"  訓練步數: {total_timesteps:,}")
    print("=" * 60)
    
    # 1. 載入數據
    print("\n[1] 載入數據...")
    loader = create_data_loader()
    df = loader.load_with_indicators(symbol, start_date, end_date)
    print(f"  載入 {len(df)} 筆數據")
    
    # 2. 創建環境
    print("\n[2] 創建交易環境...")
    env = create_env(df)
    print(f"  State 維度: {env.state_dim}")
    
    # 3. 創建 Agent
    print("\n[3] 創建 Agent...")
    agent = create_agent(env, algo)
    print(f"  Agent 類型: {algo.upper()}")
    
    # 4. 訓練
    print("\n[4] 訓練 Agent...")
    agent.train(total_timesteps=total_timesteps)
    print("  訓練完成")
    
    # 5. 回測
    print("\n[5] 執行回測...")
    from FinRL.v2.backtesting import run_backtest
    results, equity, trades = run_backtest(df, agent)
    print(f"  總報酬率: {results.total_return:.2f}%")
    print(f"  夏普比率: {results.sharpe_ratio:.2f}")
    print(f"  最大回撤: {results.max_drawdown:.2f}%")
    
    print("\n" + "=" * 60)
    print("快速開始完成")
    print("=" * 60)
    
    return agent, results, equity


# =============================================================================
# 導出所有公開 API
# =============================================================================

__all__ = [
    # 版本資訊
    '__version__',
    '__author__',
    '__description__',
    # 工廠函數
    'create_data_loader',
    'create_env',
    'create_agent',
    'create_backtest_engine',
    'quick_start',
    # 常數
    'INITIAL_CAPITAL',
    'MAX_POSITION',
    'MIN_TRADE_UNIT',
    'BROKERAGE_FEE',
    'TRANSACTION_TAX',
    'LIMIT_UP_RATIO',
    'LIMIT_DOWN_RATIO',
    'STOP_LOSS_THRESHOLD',
    # 資料層
    'TaiwanStockDataLoader',
    'TechnicalIndicators',
    'StockDatabase',
    'fetch_stock_data',
    'load_cached_data',
    'save_to_cache',
    # 環境層
    'TaiwanStockTradingEnv',
    'ActionMode',
    'DiscreteActions',
    'ContinuousActionSpec',
    'build_action_space',
    'translate_action',
    'RewardFunction',
    'composite_reward',
    # Agent層
    'PPOAgent',
    'A2CAgent',
    'SACAgent',
    'TrainingRunner',
    'train_model',
    'train_ppo',
    'train_a2c',
    'train_sac',
    # 回測層
    'PerformanceMetrics',
    'PerformanceResult',
    'BacktestEngine',
    'BacktestConfig',
    'Visualizer',
    'calculate_sharpe_ratio',
    'calculate_max_drawdown',
    'calculate_win_rate',
    'calculate_profit_factor',
    'run_backtest',
    'plot_equity_curve',
    'plot_drawdown',
    'plot_returns_distribution',
]