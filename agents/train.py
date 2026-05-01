"""
train.py - 訓練主腳本
================================================================================
將所有元件整合在一起，提供統一的訓練流程。

支援 PPO 和 A2C 兩種 Agent 的訓練。

使用範例:
    >>> python train.py --agent ppo --stock 2330 --timesteps 100000
    >>> python train.py --agent a2c --stock 2330 --timesteps 100000
    >>> python train.py --agent ppo --stock 2330.TW --timesteps 50000 --eval_only

作者: FinRL量化交易專家
"""

import argparse
import os
import sys
from pathlib import Path
from datetime import datetime
import warnings

warnings.filterwarnings('ignore')

# 添加專案根目錄到路徑
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def parse_args():
    """
    解析命令列參數
    
    Returns:
        Namespace: 解析後的參數
    """
    parser = argparse.ArgumentParser(
        description='FinRL 台股量化交易系統 - 訓練模組',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  python train.py --agent ppo --stock 2330 --timesteps 100000
  python train.py --agent a2c --stock 2330 --timesteps 100000
  python train.py --agent ppo --stock 2330.TW --timesteps 50000 --eval_only
  python train.py --agent ppo --stock 2603 --timesteps 200000 --start_date 2020-01-01
        """
    )
    
    # === 基本參數 ===
    parser.add_argument(
        '--stock', 
        type=str, 
        default='2330',
        help='股票代碼 (例如 2330 或 2330.TW)'
    )
    parser.add_argument(
        '--agent', 
        type=str, 
        default='ppo', 
        choices=['ppo', 'a2c'],
        help='使用的代理模型 (ppo 或 a2c)'
    )
    parser.add_argument(
        '--timesteps', 
        type=int, 
        default=100_000,
        help='訓練步數 (預設: 100000)'
    )
    
    # === 日期區間 ===
    parser.add_argument(
        '--start_date', 
        type=str, 
        default='2019-01-01',
        help='訓練數據開始日期 (預設: 2019-01-01)'
    )
    parser.add_argument(
        '--end_date', 
        type=str, 
        default='2024-12-31',
        help='訓練數據結束日期 (預設: 2024-12-31)'
    )
    
    # === 路徑設定 ===
    parser.add_argument(
        '--model_dir', 
        type=str, 
        default=None,
        help='模型儲存目錄 (預設: 自動產生)'
    )
    parser.add_argument(
        '--data_dir', 
        type=str, 
        default='./data',
        help='數據目錄 (預設: ./data)'
    )
    
    # === 訓練選項 ===
    parser.add_argument(
        '--eval_only', 
        action='store_true',
        help='僅進行評估，不訓練'
    )
    parser.add_argument(
        '--test_ratio', 
        type=float, 
        default=0.2,
        help='測試集比例 (預設: 0.2 = 20%%)'
    )
    
    # === 超參數覆寫 ===
    parser.add_argument(
        '--learning_rate', 
        type=float, 
        default=None,
        help='學習率 (預設: 3e-4 for PPO, 3e-4 for A2C)'
    )
    parser.add_argument(
        '--n_steps', 
        type=int, 
        default=None,
        help='每回合收集的步數 (預設: PPO=2048, A2C=5)'
    )
    parser.add_argument(
        '--batch_size', 
        type=int, 
        default=None,
        help='批次大小 (預設: 64 for PPO)'
    )
    parser.add_argument(
        '--clip_range', 
        type=float, 
        default=None,
        help='PPO clip range (預設: 0.2)'
    )
    
    # === 其他 ===
    parser.add_argument(
        '--seed', 
        type=int, 
        default=42,
        help='隨機種子 (預設: 42)'
    )
    parser.add_argument(
        '--verbose', 
        type=int, 
        default=1,
        help='詳細程度 (0=靜音, 1=一般, 2=詳細)'
    )
    
    return parser.parse_args()


def print_banner(args):
    """
    印出程式標題
    
    Args:
        args: 命令列參數
    """
    print("\n" + "=" * 70)
    print("         FinRL 台股量化交易系統 - 訓練模組")
    print("=" * 70)
    print(f"  股票代碼:     {args.stock}")
    print(f"  代理模型:     {args.agent.upper()}")
    print(f"  訓練步數:     {args.timesteps:,}")
    print(f"  數據區間:     {args.start_date} ~ {args.end_date}")
    print(f"  測試集比例:   {args.test_ratio:.0%}")
    print("=" * 70)


def setup_directories(args):
    """
    建立必要的目錄結構
    
    Args:
        args: 命令列參數
    
    Returns:
        Path: 模型輸出目錄
    """
    # 建立結果目錄
    results_dir = Path('./results')
    models_dir = results_dir / 'models'
    logs_dir = results_dir / 'logs'
    checkpoints_dir = results_dir / 'checkpoints'
    training_logs_dir = results_dir / 'training_logs'
    
    for d in [results_dir, models_dir, logs_dir, checkpoints_dir, training_logs_dir]:
        d.mkdir(parents=True, exist_ok=True)
    
    return results_dir


def load_data(args):
    """
    載入並預處理股價數據
    
    Args:
        args: 命令列參數
    
    Returns:
        pd.DataFrame: 處理後的股票數據
    """
    print("\n[Step 1] 載入數據...")
    
    try:
        # 嘗試從 FinRL 資料夾匯入
        from FinRL.data.data_loader import TaiwanStockDataLoader
        from FinRL.data.technical_indicators import TechnicalIndicators
    except ImportError as e:
        print(f"[警告] 無法匯入 FinRL 資料處理模組: {e}")
        print("[警告] 將嘗試使用標準方法載入數據...")
        return None
    
    # 建立數據載入器
    loader = TaiwanStockDataLoader(
        cache_dir=Path(args.data_dir) / 'cache',
        data_dir=Path(args.data_dir) / 'raw'
    )
    
    # 下載股價數據
    symbol = args.stock
    if not symbol.endswith('.TW'):
        symbol = symbol + '.TW'
    
    print(f"  下載 {symbol} 數據 ({args.start_date} ~ {args.end_date})...")
    
    df = loader.download_price_data(
        symbol=symbol,
        start=args.start_date,
        end=args.end_date,
        interval='1d'
    )
    
    if df.empty:
        print(f"[錯誤] 無法載入 {symbol} 的數據")
        return None
    
    print(f"  載入 {len(df)} 筆數據")
    print(f"  日期範圍: {df['date'].min()} ~ {df['date'].max()}")
    
    # 計算技術指標
    print("\n[Step 2] 計算技術指標...")
    
    ti = TechnicalIndicators(df, lookback_window=60)
    df = ti.calculate_all()
    
    print(f"  計算完成，共 {len(df.columns)} 個欄位")
    
    return df


def create_environment(df, args):
    """
    建立訓練和評估環境
    
    Args:
        df: 股票數據
        args: 命令列參數
    
    Returns:
        tuple: (train_env, eval_env)
    """
    print("\n[Step 3] 建立交易環境...")
    
    from FinRL.environments.taiwan_stock_env import TaiwanStockTradingEnv
    from FinRL.environments.reward_function import RewardFunction
    
    # 建立獎勵函數
    reward_func = RewardFunction()
    
    # 分割訓練/測試集
    split_idx = int(len(df) * (1 - args.test_ratio))
    train_df = df.iloc[:split_idx].reset_index(drop=True)
    test_df = df.iloc[split_idx:].reset_index(drop=True)
    
    print(f"  訓練集: {len(train_df)} 筆")
    print(f"  測試集: {len(test_df)} 筆")
    
    # 建立環境
    common_kwargs = {
        'initial_balance': 1_000_000,
        'max_position': 4000,
        'trade_unit': 1000,
        'price_limit': 0.10,
        'commission_rate': 0.0015,
        'tax_rate': 0.003,
        'lookback_window': 60,
        'reward_func': reward_func
    }
    
    train_env = TaiwanStockTradingEnv(df=train_df, **common_kwargs)
    test_env = TaiwanStockTradingEnv(df=test_df, **common_kwargs)
    
    print(f"  環境建立完成")
    print(f"  狀態維度: {train_env.state_dim}")
    print(f"  動作空間: {train_env.action_space.n} 類離散動作")
    print(f"    0: HOLD (觀望)")
    print(f"    1: BUY_1000 (買入1000股)")
    print(f"    2: SELL_1000 (賣出1000股)")
    print(f"    3: CLOSE_POSITION (清倉)")
    print(f"    4: STOP_LOSS (停損)")
    
    return train_env, test_env


def create_agent(train_env, eval_env, args):
    """
    建立 Agent
    
    Args:
        train_env: 訓練環境
        eval_env: 評估環境
        args: 命令列參數
    
    Returns:
        Agent: PPOAgent 或 A2CAgent
    """
    print("\n[Step 4] 建立模型...")
    
    if args.agent.lower() == 'ppo':
        from FinRL.agents.ppo_agent import PPOAgent
        
        # PPO 超參數
        ppo_config = {
            'n_steps': args.n_steps if args.n_steps else 2048,
            'batch_size': args.batch_size if args.batch_size else 64,
            'n_epochs': 10,
            'gamma': 0.99,
            'gae_lambda': 0.95,
            'clip_range': args.clip_range if args.clip_range else 0.2,
            'learning_rate': args.learning_rate if args.learning_rate else 3e-4,
            'ent_coef': 0.01,
            'max_grad_norm': 0.5,
            'verbose': args.verbose,
        }
        
        agent = PPOAgent(
            env=train_env,
            eval_env=eval_env,
            config=ppo_config
        )
        
        print(f"  Agent類型: PPO (Proximal Policy Optimization)")
        print(f"  n_steps: {ppo_config['n_steps']}")
        print(f"  batch_size: {ppo_config['batch_size']}")
        print(f"  learning_rate: {ppo_config['learning_rate']}")
        print(f"  clip_range: {ppo_config['clip_range']}")
        
    else:  # a2c
        from FinRL.agents.a2c_agent import A2CAgent
        
        # A2C 超參數
        a2c_config = {
            'n_steps': args.n_steps if args.n_steps else 5,
            'gamma': 0.99,
            'learning_rate': args.learning_rate if args.learning_rate else 3e-4,
            'ent_coef': 0.01,
            'max_grad_norm': 0.5,
            'verbose': args.verbose,
        }
        
        agent = A2CAgent(
            env=train_env,
            eval_env=eval_env,
            config=a2c_config
        )
        
        print(f"  Agent類型: A2C (Advantage Actor-Critic)")
        print(f"  n_steps: {a2c_config['n_steps']}")
        print(f"  learning_rate: {a2c_config['learning_rate']}")
    
    return agent


def train_agent(agent, args):
    """
    訓練 Agent
    
    Args:
        agent: Agent 實例
        args: 命令列參數
    
    Returns:
        dict: 訓練歷史
    """
    if args.eval_only:
        print("\n[Step 5] 載入已訓練的模型...")
        
        best_model_path = agent.get_model().save_path if hasattr(agent.get_model(), 'save_path') else None
        
        # 嘗試載入最佳模型
        if best_model_path and Path(best_model_path).exists():
            agent.load(best_model_path)
        else:
            # 嘗試找最終模型
            final_path = Path(agent.model_dir) / 'final_model.zip'
            if final_path.exists():
                agent.load(str(final_path))
            else:
                print("[錯誤] 找不到已訓練的模型")
                return None
        
    else:
        print(f"\n[Step 5] 訓練模型 ({args.timesteps:,} 步)...")
        print("=" * 60)
        
        history = agent.train(
            total_timesteps=args.timesteps,
            eval_freq=5000,
            save_freq=10000
        )
        
        print("\n訓練完成!")
    
    return agent.training_history


def evaluate_agent(agent, train_env, test_env, args):
    """
    評估 Agent
    
    Args:
        agent: Agent 實例
        train_env: 訓練環境
        test_env: 測試環境
        args: 命令列參數
    
    Returns:
        dict: 評估結果
    """
    print("\n" + "=" * 60)
    print("               模型評估")
    print("=" * 60)
    
    # 測試集評估
    print("\n--- 測試集績效 ---")
    test_results = agent.evaluate(
        env=test_env,
        n_episodes=10,
        deterministic=True
    )
    
    # 訓練集評估 (sample)
    print("\n--- 訓練集績效 (抽樣) ---")
    train_results = agent.evaluate(
        env=train_env,
        n_episodes=5,
        deterministic=True
    )
    
    return {
        'test': test_results,
        'train': train_results
    }


def generate_report(agent, eval_results, args):
    """
    生成回測報告
    
    Args:
        agent: Agent 實例
        eval_results: 評估結果
        args: 命令列參數
    """
    print("\n" + "=" * 60)
    print("               回測報告")
    print("=" * 60)
    
    # 建立視覺化目錄
    plots_dir = Path(agent.model_dir) / 'plots'
    plots_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        from FinRL.backtesting.performance_metrics import PerformanceMetrics
        
        # 讀取測試結果
        test_results = eval_results.get('test', {})
        
        print("\n【測試集績效摘要】")
        print(f"  平均報酬率: {test_results.get('mean_return', 0):.2%}")
        print(f"  報酬率標準差: {test_results.get('std_return', 0):.2%}")
        print(f"  平均 Reward: {test_results.get('mean_reward', 0):.2f}")
        print(f"  勝率: {test_results.get('win_rate', 0):.1%}")
        print(f"  正報酬 episode 數: {test_results.get('positive_episodes', 0)}/{test_results.get('n_episodes', 0)}")
        
        # 保存報告
        report_path = Path(agent.model_dir) / 'evaluation_report.json'
        import json
        with open(report_path, 'w') as f:
            json.dump({
                'stock': args.stock,
                'agent': args.agent,
                'timesteps': args.timesteps,
                'test_results': test_results,
                'train_results': eval_results.get('train', {}),
            }, f, indent=2, default=str)
        
        print(f"\n評估報告已保存: {report_path}")
        
    except ImportError:
        print("[警告] 無法匯入視覺化模組")


def main():
    """主訓練流程"""
    # 解析參數
    args = parse_args()
    
    # 印出標題
    print_banner(args)
    
    # 設定隨機種子
    import numpy as np
    np.random.seed(args.seed)
    
    # 建立目錄
    results_dir = setup_directories(args)
    
    # 嘗試載入數據
    df = load_data(args)
    
    if df is None:
        print("\n[錯誤] 無法載入數據，請確認資料處理模組可用")
        return
    
    # 建立環境
    train_env, test_env = create_environment(df, args)
    
    # 建立 Agent
    agent = create_agent(train_env, test_env, args)
    
    # 訓練/評估
    history = train_agent(agent, args)
    
    if history is not None:
        # 評估模型
        eval_results = evaluate_agent(agent, train_env, test_env, args)
        
        # 生成報告
        generate_report(agent, eval_results, args)
    
    print("\n" + "=" * 70)
    print("                    訓練完成!")
    print("=" * 70)
    print(f"\n結果目錄: {agent.model_dir}")
    print("建議查看:")
    print(f"  - 模型: {agent.model_dir}")
    print(f"  - 日誌: {agent.log_dir}")
    print(f"  - 報告: {agent.model_dir}/evaluation_report.json")


if __name__ == '__main__':
    main()