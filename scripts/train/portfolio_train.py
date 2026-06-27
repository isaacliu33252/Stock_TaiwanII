# ============================================================================
# Portfolio Multi-Agent Trainer - 投資組合多智能體訓練器
# ============================================================================
"""
訓練 8 檔股票各一個 RL Agent (共 8 個 Agent)

支援:
    - PPO / A2C / SAC
    - 平行訓練 (每支股票一個環境)
    - 個別儲存模型
    - 進度報告
"""

import os
import sys
import argparse
from pathlib import Path
from datetime import datetime
import warnings
import pandas as pd
import numpy as np

warnings.filterwarnings('ignore')

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from portfolio_config import (
    ALL_TICKERS, PORTFOLIO_HOLDINGS,
    AGENT_TYPE, TIMESTEPS_PER_STOCK,
    PARALLEL_TRAINING, LEARNING_RATE,
    SAVE_FREQUENCY, EVAL_FREQUENCY
)
from portfolio_data_loader import download_all_stocks, merge_portfolio_data
from config import PPO_CONFIG, A2C_CONFIG


def setup_imports():
    """動態導入 stable-baselines3"""
    try:
        from stable_baselines3 import PPO, A2C, SAC
        from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
        from stable_baselines3.common.callbacks import EvalCallback, BaseCallback
        import gymnasium as gym
        return True
    except ImportError:
        return False


class StockTrainer:
    """
    單支股票的訓練器
    """

    def __init__(self, ticker: str, df: pd.DataFrame, agent_type: str = "ppo",
                 initial_shares: int = 0, initial_avg_cost: float = 0.0):
        self.ticker = ticker
        self.df = df
        self.agent_type = agent_type
        self.model = None
        self.env = None
        self.info = PORTFOLIO_HOLDINGS.get(ticker, {})
        self.initial_shares = initial_shares
        self.initial_avg_cost = initial_avg_cost

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

    def get_agent_config(self):
        """取得 Agent 超參數"""
        if self.agent_type == "ppo":
            return PPO_CONFIG.copy()
        elif self.agent_type == "a2c":
            return A2C_CONFIG.copy()
        return {}

    def train(self, timesteps: int = 100_000, save_path: str = None):
        """訓練一支股票的 Agent"""
        print(f"\n{'='*60}")
        print(f"訓練 {self.ticker} ({self.info.get('name', '')})")
        print(f"Agent: {self.agent_type.upper()}, 步數: {timesteps:,}")
        print(f"資料: {len(self.df)} 筆, {self.df['date'].min()} ~ {self.df['date'].max()}")
        print(f"{'='*60}")

        # 建立環境
        env = self.create_env()

        # 設定參數
        config = self.get_agent_config()
        config['learning_rate'] = LEARNING_RATE

        # 提取 policy_kwargs 相關參數
        policy_kwargs = {}
        if 'net_arch' in config:
            policy_kwargs['net_arch'] = config.pop('net_arch')

        # 過濾掉非 SB3 參數
        # PPO 有效參數
        ppo_valid = {
            'n_steps', 'batch_size', 'n_epochs', 'gamma', 'gae_lambda',
            'clip_range', 'learning_rate', 'ent_coef',
            'clip_range_vf', 'max_grad_norm',
        }
        # A2C 有效參數
        a2c_valid = {
            'n_steps', 'gamma', 'gae_lambda', 'learning_rate', 'ent_coef',
            'use_rmsprop', 'rmsprop_eps', 'max_grad_norm',
        }

        valid = ppo_valid if self.agent_type == "ppo" else a2c_valid
        filtered_config = {k: v for k, v in config.items() if k in valid}
        if policy_kwargs:
            filtered_config['policy_kwargs'] = policy_kwargs

        # 建立 Agent
        if self.agent_type == "ppo":
            from stable_baselines3 import PPO
            self.model = PPO("MlpPolicy", env, **filtered_config, verbose=1)
        elif self.agent_type == "a2c":
            from stable_baselines3 import A2C
            self.model = A2C("MlpPolicy", env, **filtered_config, verbose=1)

        # 訓練
        self.model.learn(
            total_timesteps=timesteps,
            callback=None,
            progress_bar=True
        )

        # 儲存
        if save_path:
            self.model.save(save_path)
            print(f"模型已儲存: {save_path}")

        return self.model


class PortfolioTrainer:
    """
    投資組合多智能體訓練管理器
    """

    def __init__(
        self,
        tickers: list = None,
        agent_type: str = "ppo",
        timesteps: int = 100_000,
        data_start: str = "1990-01-01",
        data_end: str = "2000-12-31"
    ):
        self.tickers = tickers or ALL_TICKERS
        self.agent_type = agent_type
        self.timesteps = timesteps
        self.data_start = data_start
        self.data_end = data_end

        self.models_dir = PROJECT_ROOT / "FinRL" / "models" / "portfolio"
        self.models_dir.mkdir(parents=True, exist_ok=True)

        self.stock_data = {}
        self.trainers = {}

    def prepare_data(self):
        """下載並準備所有股票的數據"""
        print("=" * 60)
        print("多智能體訓練 - 資料準備")
        print("=" * 60)

        self.stock_data = download_all_stocks(
            self.tickers,
            self.data_start,
            self.data_end,
            cache_dir=str(PROJECT_ROOT / "data" / "portfolio_cache")
        )

        return self.stock_data

    def train_all(self, resume=False):
        """訓練所有股票的 Agent

        Args:
            resume: 若為 True，跳過已存在模型檔的股票（断点续训）
        """
        print("=" * 60)
        print(f"開始多智能體訓練 - {len(self.tickers)} 檔股票")
        print(f"Agent: {self.agent_type.upper()}, 每檔 {self.timesteps:,} 步")
        if resume:
            print("模式: resume（跳過已訓練的股票）")
        print("=" * 60)

        results = {}

        for i, ticker in enumerate(self.tickers):
            if ticker not in self.stock_data:
                print(f"[{i+1}/{len(self.tickers)}] {ticker} 無數據，跳過")
                continue

            # --resume: 檢查是否已訓練過
            if resume:
                model_path = self.models_dir / f"{ticker.replace('.', '_')}_{self.agent_type}.zip"
                if model_path.exists():
                    print(f"[{i+1}/{len(self.tickers)}] {ticker} 已存在模型，跳過")
                    results[ticker] = {
                        "name": PORTFOLIO_HOLDINGS.get(ticker, {}).get('name', ''),
                        "shares": PORTFOLIO_HOLDINGS.get(ticker, {}).get('shares', 0),
                        "model_path": str(model_path),
                        "data_points": len(self.stock_data[ticker]),
                    }
                    continue

            df = self.stock_data[ticker]
            
            # 從 PORTFOLIO_HOLDINGS 取得初始持股
            holding = PORTFOLIO_HOLDINGS.get(ticker, {})
            initial_shares = holding.get('shares', 0)
            initial_avg_cost = holding.get('cost_basis', 0.0)

            # 建立訓練器（含初始持股）
            trainer = StockTrainer(
                ticker, df, self.agent_type,
                initial_shares=initial_shares,
                initial_avg_cost=initial_avg_cost
            )
            self.trainers[ticker] = trainer

            # 訓練
            save_path = str(self.models_dir / f"{ticker.replace('.', '_')}_{self.agent_type}")
            model = trainer.train(
                timesteps=self.timesteps,
                save_path=save_path
            )

            results[ticker] = {
                "name": trainer.info.get('name', ''),
                "shares": trainer.info.get('shares', 0),
                "model_path": save_path,
                "data_points": len(df),
            }

        # 訓練完成摘要
        print("\n" + "=" * 60)
        print("多智能體訓練完成！")
        print("=" * 60)
        for ticker, info in results.items():
            print(f"  {ticker} ({info['name']}) - {info['data_points']} 筆 -> {info['model_path']}")

        # 儲存訓練摘要
        summary_path = self.models_dir / "training_summary.txt"
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write(f"訓練完成時間: {datetime.now()}\n")
            f.write(f"Agent 類型: {self.agent_type}\n")
            f.write(f"每檔訓練步數: {self.timesteps:,}\n")
            f.write(f"日期區間: {self.data_start} ~ {self.data_end}\n\n")
            for ticker, info in results.items():
                f.write(f"{ticker} ({info['name']}): {info['shares']} 股, {info['data_points']} 筆資料\n")

        print(f"\n訓練摘要已儲存: {summary_path}")
        return results


# =============================================================================
# 主程式
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='投資組合多智能體訓練')
    parser.add_argument('--agent', type=str, default='ppo',
                        choices=['ppo', 'a2c', 'sac'],
                        help='Agent 類型')
    parser.add_argument('--timesteps', type=int, default=100_000,
                        help='每支股票的訓練步數')
    parser.add_argument('--start', type=str, default='1990-01-01',
                        help='訓練資料開始日期')
    parser.add_argument('--end', type=str, default='2000-12-31',
                        help='訓練資料結束日期')
    parser.add_argument('--stocks', type=str, default=None,
                        help='指定股票 (逗號分隔，預設全部)')
    parser.add_argument('--resume', action='store_true',
                        help='续训模式：跳過已存在模型的股票（断点续训）')
    args = parser.parse_args()

    # 檢查依賴
    if not setup_imports():
        print("錯誤: 需要 stable-baselines3")
        print("安裝: pip install stable-baselines3 gymnasium")
        sys.exit(1)

    # 選擇股票
    if args.stocks:
        tickers = [t.strip() for t in args.stocks.split(',')]
    else:
        tickers = ALL_TICKERS

    # 建立訓練器
    trainer = PortfolioTrainer(
        tickers=tickers,
        agent_type=args.agent,
        timesteps=args.timesteps,
        data_start=args.start,
        data_end=args.end
    )

    # 準備資料
    trainer.prepare_data()

    # 訓練
    results = trainer.train_all(resume=args.resume)

    print("\n完成！")
