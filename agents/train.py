"""
train.py - 訓練主腳本 (整合版)
================================================================================
將所有元件整合在一起，提供統一的訓練流程。

支援 PPO 和 A2C 兩種 Agent 的訓練。
使用範例:
    >>> python train.py --agent ppo --stock 2330 --timesteps 100000
    >>> python train.py --agent a2c --stock 2330 --timesteps 100000
    >>> python train.py --agent ppo --stock 2330.TW --timesteps 50000 --eval_only

基於 GitHub FinRL 結構，整合本地增強功能：
- 批次訓練支援（portfolio_train_v2）
- Telegram 通知
- 52維狀態空間

作者: FinRL量化交易專家
"""

import argparse
import os
import sys
from pathlib import Path
from datetime import datetime
import warnings
import pandas as pd

warnings.filterwarnings('ignore')

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import urllib.request
import urllib.parse


def _send_notification(message: str, chat_id: str = "8605791933"):
    """發送 Telegram 通知"""
    token = "8713079660:AAFKzYjHaJMyRUtqinIRDrklslCF20ynpuU"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }).encode()
    try:
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception as e:
        print(f"[通知發送失敗] {e}")


def parse_args():
    """解析命令列參數"""
    parser = argparse.ArgumentParser(
        description='FinRL 台股量化交易系統 - 訓練模組',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  python train.py --agent ppo --stock 2330 --timesteps 100000
  python train.py --agent ppo --stock 2330 --timesteps 50000 --eval_only
  python train.py --agent ppo --stock 2603 --timesteps 200000 --start_date 2020-01-01
        """
    )
    
    parser.add_argument('--stock', type=str, default='2330', help='股票代碼')
    parser.add_argument('--agent', type=str, default='ppo', choices=['ppo', 'a2c'], help='Agent 類型')
    parser.add_argument('--timesteps', type=int, default=100_000, help='訓練步數')
    parser.add_argument('--start_date', type=str, default='2021-01-01', help='數據開始日期')
    parser.add_argument('--end_date', type=str, default='2025-12-31', help='數據結束日期')
    parser.add_argument('--eval_only', action='store_true', help='僅評估')
    parser.add_argument('--test_ratio', type=float, default=0.2, help='測試集比例')
    parser.add_argument('--learning_rate', type=float, default=None, help='學習率')
    parser.add_argument('--batch_size', type=int, default=None, help='批次大小')
    parser.add_argument('--seed', type=int, default=42, help='隨機種子')
    parser.add_argument('--verbose', type=int, default=1, help='詳細程度')
    
    return parser.parse_args()


def print_banner(args):
    """印出程式標題"""
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
    """建立必要的目錄結構"""
    results_dir = Path('./results')
    models_dir = results_dir / 'models'
    logs_dir = results_dir / 'logs'
    
    for d in [results_dir, models_dir, logs_dir]:
        d.mkdir(parents=True, exist_ok=True)
    
    return results_dir


def load_data(args):
    """載入並預處理股價數據"""
    print("\n[Step 1] 載入數據...")
    
    try:
        from data.technical_indicators import TechnicalIndicators
        import yfinance as yf
    except ImportError as e:
        print(f"[警告] 無法匯入資料處理模組: {e}")
        return None
    
    symbol = args.stock
    if not symbol.endswith('.TW'):
        symbol = symbol + '.TW'
    
    print(f"  下載 {symbol} 數據 ({args.start_date} ~ {args.end_date})...")
    
    try:
        df = yf.download(symbol, start=args.start_date, end=args.end_date, progress=False)
        
        # 處理 MultiIndex 欄位問題 (yfinance 版本差異)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        df = df.reset_index()
        df.columns = [col.lower() if isinstance(col, str) else str(col) for col in df.columns]
    except Exception as e:
        print(f"[錯誤] 無法下載數據: {e}")
        return None
    
    if df.empty:
        print(f"[錯誤] 無法載入 {symbol} 的數據")
        return None
    
    print(f"  載入 {len(df)} 筆數據")
    
    # 計算技術指標
    print("\n[Step 2] 計算技術指標...")
    
    ti = TechnicalIndicators(df, lookback_window=60)
    df = ti.calculate_all()
    
    print(f"  計算完成，共 {len(df.columns)} 個欄位")
    
    return df


def create_environment(df, args):
    """建立訓練和評估環境"""
    print("\n[Step 3] 建立交易環境...")
    
    from environments.taiwan_stock_env import TaiwanStockTradingEnv
    from environments.reward_function import RewardFunction
    
    # 建立獎勵函數（使用本地增強版）
    reward_func = RewardFunction()
    
    split_idx = int(len(df) * (1 - args.test_ratio))
    train_df = df.iloc[:split_idx].reset_index(drop=True)
    test_df = df.iloc[split_idx:].reset_index(drop=True)
    
    print(f"  訓練集: {len(train_df)} 筆")
    print(f"  測試集: {len(test_df)} 筆")
    
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
    
    return train_env, test_env


def create_agent(train_env, eval_env, args):
    """建立 Agent"""
    print("\n[Step 4] 建立模型...")
    
    if args.agent.lower() == 'ppo':
        from agents.ppo_agent import PPOAgent
        
        ppo_config = {
            'n_steps': 2048,
            'batch_size': args.batch_size if args.batch_size else 64,
            'n_epochs': 10,
            'gamma': 0.99,
            'gae_lambda': 0.95,
            'clip_range': 0.2,
            'learning_rate': args.learning_rate if args.learning_rate else 3e-4,
            'ent_coef': 0.01,
            'max_grad_norm': 0.5,
            'verbose': args.verbose,
        }
        
        agent = PPOAgent(env=train_env, eval_env=eval_env, config=ppo_config)
        print(f"  Agent類型: PPO")
        
    else:
        from agents.a2c_agent import A2CAgent
        
        a2c_config = {
            'n_steps': 5,
            'gamma': 0.99,
            'learning_rate': args.learning_rate if args.learning_rate else 3e-4,
            'ent_coef': 0.01,
            'verbose': args.verbose,
        }
        
        agent = A2CAgent(env=train_env, eval_env=eval_env, config=a2c_config)
        print(f"  Agent類型: A2C")
    
    return agent


def train_agent(agent, args):
    """訓練 Agent"""
    if args.eval_only:
        print("\n[Step 5] 載入已訓練的模型...")
        best_path = Path(agent.model_dir) / 'best_model.zip'
        if best_path.exists():
            agent.load(str(best_path))
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
        
        # 發送 Telegram 通知
        _send_notification(f"✅ 訓練完成！\n股票: {args.stock}\nAgent: {args.agent.upper()}\n步數: {args.timesteps:,}")
    
    return agent.training_history


def evaluate_agent(agent, train_env, test_env, args):
    """評估 Agent"""
    print("\n" + "=" * 60)
    print("               模型評估")
    print("=" * 60)
    
    print("\n--- 測試集績效 ---")
    test_results = agent.evaluate(env=test_env, n_episodes=10, deterministic=True)
    
    print("\n--- 訓練集績效 (抽樣) ---")
    train_results = agent.evaluate(env=train_env, n_episodes=5, deterministic=True)
    
    return {'test': test_results, 'train': train_results}


def generate_report(agent, eval_results, args):
    """生成回測報告"""
    print("\n" + "=" * 60)
    print("               回測報告")
    print("=" * 60)
    
    test_results = eval_results.get('test', {})
    
    print("\n【測試集績效摘要】")
    print(f"  平均報酬率: {test_results.get('mean_return', 0):.2%}")
    print(f"  報酬率標準差: {test_results.get('std_return', 0):.2%}")
    print(f"  平均 Reward: {test_results.get('mean_reward', 0):.2f}")
    print(f"  勝率: {test_results.get('win_rate', 0):.1%}")
    
    import json
    report_path = Path(agent.model_dir) / 'evaluation_report.json'
    with open(report_path, 'w') as f:
        json.dump({
            'stock': args.stock,
            'agent': args.agent,
            'timesteps': args.timesteps,
            'test_results': test_results,
            'train_results': eval_results.get('train', {}),
        }, f, indent=2, default=str)
    
    print(f"\n評估報告已保存: {report_path}")


def main():
    """主訓練流程"""
    args = parse_args()
    print_banner(args)
    
    import numpy as np
    np.random.seed(args.seed)
    
    results_dir = setup_directories(args)
    df = load_data(args)
    
    if df is None:
        print("\n[錯誤] 無法載入數據")
        return
    
    train_env, test_env = create_environment(df, args)
    agent = create_agent(train_env, test_env, args)
    history = train_agent(agent, args)
    
    if history is not None:
        eval_results = evaluate_agent(agent, train_env, test_env, args)
        generate_report(agent, eval_results, args)
    
    print("\n" + "=" * 70)
    print("                    訓練完成!")
    print("=" * 70)


if __name__ == '__main__':
    main()
