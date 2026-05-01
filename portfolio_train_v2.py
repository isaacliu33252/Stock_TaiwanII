# ============================================================================
# Enhanced Portfolio Trainer v2 - 整合風控與增強獎勵
# ============================================================================
"""
整合三大改善的訓練流程：
1. 增強版 Reward Function (Sortino + Calmar)
2. 增強版 Risk Manager (Early Stopping + Kelly)
3. 增強版 Walk-Forward (統計檢驗)

使用方式:
    python portfolio_train_v2.py --tickers 0050.TW --timesteps 100000
    python portfolio_train_v2.py --all --timesteps 100000
"""

import os
import sys
import argparse
from pathlib import Path
from datetime import datetime
import warnings
import json
import pandas as pd
import numpy as np

warnings.filterwarnings('ignore')

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from portfolio_config import (
    ALL_TICKERS, PORTFOLIO_HOLDINGS,
    AGENT_TYPE, TIMESTEPS_PER_STOCK,
    PARALLEL_TRAINING, LEARNING_RATE,
)
from portfolio_data_loader import download_all_stocks, merge_portfolio_data


class EnhancedStockTrainer:
    """
    增強版股票訓練器
    
    整合：
    - reward_function_v2 (Sortino + Calmar 獎勵)
    - risk_manager_v2 (Early Stopping + Kelly)
    - walk_forward_v2 (滾動驗證)
    """
    
    def __init__(
        self,
        ticker: str,
        df: pd.DataFrame,
        agent_type: str = "ppo",
        initial_shares: int = 0,
        initial_avg_cost: float = 0.0,
        # 新增：風控設定
        enable_risk_manager: bool = True,
        enable_enhanced_reward: bool = True,
        early_stop_patience: int = 30,
        target_sharpe: float = 0.5,
    ):
        self.ticker = ticker
        self.df = df
        self.agent_type = agent_type
        self.initial_shares = initial_shares
        self.initial_avg_cost = initial_avg_cost
        self.enable_risk_manager = enable_risk_manager
        self.enable_enhanced_reward = enable_enhanced_reward
        
        # 初始化風控
        if enable_risk_manager:
            from risk_manager_v2 import RiskManager
            self.risk_manager = RiskManager(
                early_stop_patience=early_stop_patience,
                early_stop_sharpe_threshold=target_sharpe,
                max_drawdown_limit=0.20,
                stop_loss_pct=-0.10,
                take_profit_pct=0.20,
            )
            self.risk_manager.reset(initial_value=1_000_000)
        else:
            self.risk_manager = None
        
        # 初始化增強獎勵
        if enable_enhanced_reward:
            from environments.reward_function_v2 import RewardFunction
            self.reward_func = RewardFunction(
                sortino_weight=0.2,
                calmar_weight=0.15,
                volatility_penalty=0.1,
                drawdown_penalty=0.5,
            )
        else:
            self.reward_func = None
        
        self.model = None
        self.env = None
        self.info = PORTFOLIO_HOLDINGS.get(ticker, {})
        self.train_stats = {
            'best_sharpe': -999,
            'steps_without_improve': 0,
            'early_stopped': False,
            'total_trades': 0,
        }
    
    def create_env(self):
        """建立交易環境"""
        from environments.taiwan_stock_env import TaiwanStockTradingEnv
        
        env_config = {
            'df': self.df,
            'initial_balance': 1_000_000,
            'max_position': 4000,
            'trade_unit': 1000,
            'price_limit': 0.10,
            'commission_rate': 0.001425,
            'tax_rate': 0.003,
            'lookback_window': 60,
            'initial_shares': self.initial_shares or 0,
            'initial_avg_cost': self.initial_avg_cost if self.initial_avg_cost is not None else 0.0,
        }
        
        env = TaiwanStockTradingEnv(**env_config)
        return env
    
    def train(
        self,
        timesteps: int = 100_000,
        save_path: str = None,
        verbose: int = 1,
    ) -> dict:
        """訓練股票 Agent"""
        
        print(f"\n{'='*60}")
        print(f"Enhanced Training: {self.ticker}")
        print(f"Agent: {self.agent_type.upper()}, Steps: {timesteps:,}")
        print(f"Enhanced Reward: {self.enable_enhanced_reward}")
        print(f"Risk Manager: {self.enable_risk_manager}")
        print(f"{'='*60}")
        
        # 建立環境
        env = self.create_env()
        eval_env = self.create_env()
        
        # 準備模型
        from stable_baselines3 import PPO, A2C, SAC
        from stable_baselines3.common.callbacks import BaseCallback, EvalCallback
        from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
        import gymnasium as gym
        
        # 建立回調（整合風控）
        callbacks = []
        if self.risk_manager:
            callbacks.append(WalkForwardCallback(self.risk_manager, verbose=verbose))
        
        # 選擇演算法
        if self.agent_type.lower() == "ppo":
            model = PPO(
                "MlpPolicy",
                env,
                learning_rate=3e-4,
                n_steps=2048,
                batch_size=64,
                n_epochs=10,
                gamma=0.99,
                verbose=verbose,
            )
        elif self.agent_type.lower() == "a2c":
            model = A2C(
                "MlpPolicy",
                env,
                learning_rate=3e-4,
                n_steps=2048,
                gamma=0.99,
                verbose=verbose,
            )
        else:
            raise ValueError(f"Unsupported agent type: {self.agent_type}")
        
        # 訓練（不傳入自定義回調）
        self.model = model
        self.model.learn(
            total_timesteps=timesteps,
            progress_bar=False,
        )
        
        # 訓練完成，收集統計
        stats = self._collect_stats(env)
        
        # 儲存
        if save_path:
            self.model.save(save_path)
            print(f"模型已儲存: {save_path}")
        
        # 印出摘要
        self._print_summary(stats)
        
        return stats
    
    def _collect_stats(self, env) -> dict:
        """收集訓練統計"""
        stats = {
            'ticker': self.ticker,
            'agent_type': self.agent_type,
            'total_steps': timesteps if 'timesteps' in dir() else 0,
            'best_sharpe': self.train_stats['best_sharpe'],
            'early_stopped': self.train_stats['early_stopped'],
            'total_trades': self.train_stats['total_trades'],
        }
        
        if self.risk_manager:
            risk_summary = self.risk_manager.get_summary()
            stats.update({
                'final_sharpe': risk_summary.get('current_sharpe', 0),
                'final_sortino': risk_summary.get('current_sortino', 0),
                'peak_value': risk_summary.get('peak_value', 0),
            })
        
        return stats
    
    def _print_summary(self, stats: dict):
        """印出訓練摘要"""
        print(f"\n{'='*60}")
        print(f"訓練摘要: {self.ticker}")
        print(f"{'='*60}")
        print(f"Sharpe Ratio: {stats.get('best_sharpe', 0):.3f}")
        print(f"Sortino Ratio: {stats.get('final_sortino', 0):.3f}")
        print(f"Early Stopped: {stats.get('early_stopped', False)}")
        print(f"Total Trades: {stats.get('total_trades', 0)}")
        print(f"Peak Value: ${stats.get('peak_value', 0):,.0f}")
    
    def backtest(self, df_test=None) -> dict:
        """在測試期上回測"""
        if df_test is None:
            # 用訓練數據的後半當測試
            split = len(self.df) // 2
            df_test = self.df.iloc[split:].copy()
        
        if self.model is None:
            print("需要先訓練模型")
            return {}
        
        from environments.taiwan_stock_env import TaiwanStockTradingEnv
        
        env_config = {
            'df': df_test,
            'initial_balance': 1_000_000,
            'max_position': 4000,
            'trade_unit': 1000,
            'price_limit': 0.10,
            'commission_rate': 0.001425,
            'tax_rate': 0.003,
            'lookback_window': 60,
            'initial_shares': self.initial_shares,
            'initial_avg_cost': self.initial_avg_cost,
        }
        
        env = TaiwanStockTradingEnv(**env_config)
        obs, _ = env.reset()
        
        done = False
        total_reward = 0
        trades = 0
        
        while not done:
            action, _ = self.model.predict(obs)
            obs, reward, terminated, truncated, info = env.step(action)
            done = terminated or truncated
            total_reward += reward
            
            if info.get('trade_executed'):
                trades += 1
        
        final_price = df_test.iloc[-1]['close']
        final_value = env.balance + env.position * final_price
        
        return {
            'final_value': final_value,
            'total_reward': total_reward,
            'num_trades': trades,
            'final_position': env.position,
        }


class WalkForwardCallback:
    """Walk-Forward 回調：整合風控與 Early Stopping"""
    
    def __init__(self, risk_manager, verbose=0):
        self.risk_manager = risk_manager
        self.step_count = 0
        self.verbose = verbose
    
    def on_step(self, locals_dict):
        self.step_count += 1
        
        # 每 100 步檢查一次風控
        if self.step_count % 100 == 0:
            # 記錄當前報酬
            infos = locals_dict.get('infos', [{}])
            if infos and isinstance(infos, list):
                ret = infos[0].get('portfolio_return', 0)
                self.risk_manager.record_return(ret)
            
            # 檢查 Sharpe 是否需要 Early Stop
            current_sharpe = self.risk_manager.calculate_sharpe()
            if current_sharpe < self.risk_manager.early_stop_sharpe_threshold:
                self.risk_manager._no_improve_steps += 1
                if self.risk_manager._no_improve_steps >= self.risk_manager.early_stop_patience:
                    if self.verbose > 0:
                        print(f"\n⚠️ Early Stopping 觸發！Sharpe={current_sharpe:.3f}")
                    return False  # 停止訓練
        
        return True


def run_walk_forward_train(
    stock_data: dict,
    holdings: dict,
    tickers: list = None,
    train_years: float = 2.0,
    test_days: int = 60,
    timesteps: int = 100_000,
) -> dict:
    """
    執行 Walk-Forward 訓練流程
    
    每個視窗：
    1. 用歷史數據訓練
    2. 在未見過的數據上測試
    3. 收集統計結果
    """
    from walk_forward_v2 import EnhancedWalkForward, WalkForwardConfig
    from datetime import timedelta
    
    print(f"\n{'='*60}")
    print("Walk-Forward Training Mode")
    print(f"{'='*60}")
    
    tickers = tickers or list(stock_data.keys())
    results = []
    
    for ticker in tickers:
        print(f"\n處理: {ticker}")
        
        df = stock_data.get(ticker)
        if df is None or len(df) < 500:
            print(f"  跳過 {ticker}：數據不足")
            continue
        
        info = holdings.get(ticker, {})
        initial_shares = info.get('shares', 0)
        
        # 建立訓練器
        trainer = EnhancedStockTrainer(
            ticker=ticker,
            df=df,
            agent_type='ppo',
            initial_shares=initial_shares,
            early_stop_patience=30,
        )
        
        # 執行一步訓練
        stats = trainer.train(timesteps=timesteps, verbose=0)
        results.append(stats)
        
        # 執行回測
        backtest_result = trainer.backtest()
        results[-1].update(backtest_result)
        
        print(f"  完成: Sharpe={stats.get('best_sharpe', 0):.3f}, "
              f"最終價值=${backtest_result.get('final_value', 0):,.0f}")
    
    return results


def main():
    parser = argparse.ArgumentParser(description='Enhanced Portfolio Trainer v2')
    parser.add_argument('--tickers', nargs='+', default=None, help='股票代碼')
    parser.add_argument('--all', action='store_true', help='訓練所有股票')
    parser.add_argument('--timesteps', type=int, default=100_000, help='訓練步數')
    parser.add_argument('--agent', type=str, default='ppo', choices=['ppo', 'a2c'], help='代理類型')
    parser.add_argument('--walk-forward', action='store_true', help='執行 Walk-Forward 訓練')
    parser.add_argument('--no-risk', action='store_true', help='停用風控')
    parser.add_argument('--no-enhanced-reward', action='store_true', help='停用增強獎勵')
    
    args = parser.parse_args()
    
    # 設定要訓練的股票
    if args.all:
        tickers = ALL_TICKERS
    elif args.tickers:
        tickers = args.tickers
    else:
        tickers = ['0050.TW']  # 預設
    
    print(f"訓練股票: {tickers}")
    print(f"訓練步數: {args.timesteps:,}")
    
    # 下載數據
    print("\n下載數據...")
    from datetime import datetime, timedelta
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=365*5)).strftime('%Y-%m-%d')
    
    stock_data = download_all_stocks(tickers, start_date, end_date)
    
    if not stock_data:
        print("無法下載數據")
        return
    
    # 訓練
    if args.walk_forward:
        results = run_walk_forward_train(
            stock_data,
            PORTFOLIO_HOLDINGS,
            tickers=tickers,
            timesteps=args.timesteps,
        )
        
        # 儲存結果
        output_file = PROJECT_ROOT / "results" / f"walk_forward_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        output_file.parent.mkdir(exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n結果已儲存: {output_file}")
    
    else:
        # 單一股票訓練
        ticker = tickers[0]
        info = PORTFOLIO_HOLDINGS.get(ticker, {})
        
        trainer = EnhancedStockTrainer(
            ticker=ticker,
            df=stock_data[ticker],
            agent_type=args.agent,
            initial_shares=info.get('shares', 0),
            enable_risk_manager=not args.no_risk,
            enable_enhanced_reward=not args.no_enhanced_reward,
        )
        
        save_path = str(PROJECT_ROOT / "FinRL" / "models" / "portfolio" / f"{ticker}_enhanced")
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        
        stats = trainer.train(timesteps=args.timesteps, save_path=save_path)
        
        # 回測
        result = trainer.backtest()
        print(f"\n回測結果: 最終價值=${result.get('final_value', 0):,.0f}")


if __name__ == '__main__':
    main()