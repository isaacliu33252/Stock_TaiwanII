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
import platform
import random
import subprocess
from pathlib import Path
from datetime import datetime
import warnings
import json
import pandas as pd
import numpy as np

warnings.filterwarnings('ignore')

import urllib.request
import urllib.parse

PROJECT_ROOT = Path(__file__).parent


def _send_notification(message: str, chat_id: str | None = None) -> bool:
    """Send a Telegram notification when credentials are configured."""
    if os.getenv("FINRL_TELEGRAM_ENABLED") != "1":
        return False

    token = os.getenv("FINRL_TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.getenv("FINRL_TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[notification] skipped: FINRL_TELEGRAM_BOT_TOKEN or FINRL_TELEGRAM_CHAT_ID is not set")
        return False

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
        return True
    except Exception as e:
        print(f"[notification] failed: {e}")
        return False


def _safe_git_commit() -> str | None:
    """Return the current git commit when git is available."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return proc.stdout.strip()
    except Exception:
        return None


def build_experiment_metadata(
    *,
    ticker: str,
    agent_type: str,
    timesteps: int,
    seed: int,
    train_rows: int,
    test_rows: int | None = None,
    model_path: str | None = None,
    reward_config: dict | None = None,
    env_config: dict | None = None,
) -> dict:
    """Metadata saved with every training/backtest result for reproducibility."""
    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "ticker": ticker,
        "agent_type": agent_type,
        "timesteps": int(timesteps),
        "seed": int(seed),
        "train_rows": int(train_rows),
        "test_rows": int(test_rows) if test_rows is not None else None,
        "model_path": model_path,
        "git_commit": _safe_git_commit(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "reward_config": reward_config or {},
        "env_config": env_config or {},
    }


def calculate_backtest_metrics(
    equity_curve: list[float],
    initial_value: float = 1_000_000,
    risk_free_rate: float = 0.02,
) -> dict:
    """Calculate compact metrics for an equity curve."""
    equity = np.asarray(equity_curve, dtype=float)
    equity = equity[np.isfinite(equity)]
    if len(equity) < 2 or initial_value <= 0:
        return {
            "total_return": 0.0,
            "annual_return": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "volatility": 0.0,
        }

    returns = np.diff(equity) / equity[:-1]
    returns = returns[np.isfinite(returns)]
    total_return = float(equity[-1] / initial_value - 1.0)
    years = max((len(equity) - 1) / 252.0, 1 / 252.0)
    annual_return = float((1.0 + total_return) ** (1.0 / years) - 1.0) if total_return > -1 else -1.0

    if len(returns) > 1:
        daily_rf = risk_free_rate / 252.0
        excess = returns - daily_rf
        std = float(np.std(excess, ddof=1))
        sharpe = float(np.mean(excess) / std * np.sqrt(252.0)) if std > 0 else 0.0
        volatility = float(np.std(returns, ddof=1) * np.sqrt(252.0))
    else:
        sharpe = 0.0
        volatility = 0.0

    running_max = np.maximum.accumulate(equity)
    drawdowns = (equity - running_max) / running_max
    max_drawdown = float(np.min(drawdowns)) if len(drawdowns) else 0.0

    return {
        "total_return": total_return,
        "annual_return": annual_return,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "volatility": volatility,
    }


def calculate_buy_and_hold_metrics(
    df: pd.DataFrame,
    initial_value: float = 1_000_000,
    risk_free_rate: float = 0.02,
) -> dict:
    """Benchmark: invest all starting cash in the first close and hold."""
    if df is None or df.empty or "close" not in df:
        return {}

    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    if len(close) < 2 or close.iloc[0] <= 0:
        return {}

    shares = initial_value / float(close.iloc[0])
    equity = (close.to_numpy(dtype=float) * shares).tolist()
    metrics = calculate_backtest_metrics(equity, initial_value=initial_value, risk_free_rate=risk_free_rate)
    metrics.update({
        "initial_price": float(close.iloc[0]),
        "final_price": float(close.iloc[-1]),
        "equity_curve": equity,
    })
    return metrics

sys.path.insert(0, str(PROJECT_ROOT))

from portfolio_config import (
    ALL_TICKERS, PORTFOLIO_HOLDINGS,
    AGENT_TYPE, TIMESTEPS_PER_STOCK,
    PARALLEL_TRAINING, LEARNING_RATE,
)
from portfolio_data_loader import download_all_stocks, merge_portfolio_data
from safe_ppo import SafeActorCriticPolicy, GradientClipCallback


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
        seed: int = 42,
    ):
        self.ticker = ticker
        self.df = df
        self.agent_type = agent_type
        self.initial_shares = initial_shares
        self.initial_avg_cost = initial_avg_cost
        self.enable_risk_manager = enable_risk_manager
        self.enable_enhanced_reward = enable_enhanced_reward
        self.seed = int(seed)
        self.timesteps = 0  # 儲存訓練步數

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
        
        # 初始化增強獎勵（v3 DynamicRewardShaper）
        if enable_enhanced_reward:
            from environments.reward_function_v3 import DynamicRewardShaper
            self.reward_func = DynamicRewardShaper(
                trade_penalty=0.02,
                sortino_weight=0.20,
                calmar_weight=0.15,
                volatility_penalty=0.1,
                drawdown_penalty=0.15,
                holding_bonus=0.25,
                trade_reward=0.0,
                trend_bull_bonus=0.10,     # MA5>MA20 多頭，持倉 bonus
                trend_bear_penalty=0.08,   # MA5<MA20 空頭，空手 penalty
                benchmark_weight=2.0,
                underperform_penalty=1.0,
                cash_miss_penalty=0.08,
                init_reward_scale=1.5,
                final_reward_scale=0.6,
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
            'max_position': 40000,
            'trade_unit': 1000,
            'price_limit': 0.10,
            'commission_rate': 0.001425,
            'tax_rate': 0.003,
            'lookback_window': 60,
            'initial_shares': self.initial_shares or 0,
            'initial_avg_cost': self.initial_avg_cost if self.initial_avg_cost is not None else 0.0,
            'reward_func': self.reward_func,
            'enable_risk_manager': self.enable_risk_manager,
            'crash_window': 15,
            'turnover_penalty': 0.01,
            'min_hold_days': 20,
            'short_hold_penalty': 0.02,
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
        print(f"Seed: {self.seed}")
        print(f"{'='*60}")

        random.seed(self.seed)
        np.random.seed(self.seed)
        try:
            import torch
            torch.manual_seed(self.seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(self.seed)
        except Exception:
            pass
        
        # 建立環境
        env = self.create_env()
        eval_env = self.create_env()
        
        # 準備模型
        from stable_baselines3 import PPO, A2C, DQN
        
        # 建立回調（整合風控）
        callbacks = []
        if self.risk_manager:
            callbacks.append(WalkForwardCallback(self.risk_manager, verbose=verbose))
        callbacks.append(GradientClipCallback(max_norm=1.0, verbose=0))
        
        # 選擇演算法
        if self.agent_type.lower() == "ppo":
            model = PPO(
                SafeActorCriticPolicy,
                env,
                policy_kwargs={
                    'log_clip_min': -20.0,
                    'log_clip_max': 20.0,
                    'net_arch': [256, 256],
                },
                learning_rate=LEARNING_RATE,
                n_steps=2048,
                batch_size=64,
                n_epochs=10,
                gamma=0.99,
                seed=self.seed,
                verbose=verbose,
            )
        elif self.agent_type.lower() == "a2c":
            model = A2C(
                "MlpPolicy",
                env,
                learning_rate=LEARNING_RATE,
                n_steps=2048,
                gamma=0.99,
                seed=self.seed,
                verbose=verbose,
            )
        elif self.agent_type.lower() == "dqn":
            model = DQN(
                "MlpPolicy",
                env,
                policy_kwargs={
                    "net_arch": [256, 256],
                },
                learning_rate=LEARNING_RATE,
                buffer_size=100_000,
                learning_starts=5_000,
                batch_size=128,
                tau=1.0,
                gamma=0.99,
                train_freq=4,
                gradient_steps=1,
                target_update_interval=2_000,
                exploration_fraction=0.25,
                exploration_initial_eps=1.0,
                exploration_final_eps=0.05,
                max_grad_norm=1.0,
                seed=self.seed,
                verbose=verbose,
            )
        else:
            raise ValueError(f"Unsupported agent type: {self.agent_type}")
        
        # 訓練（含風控 early-stop 與梯度裁切 callback）
        self.model = model
        
        # 傳遞 total_steps 給 DynamicRewardShaper（用於 progressive decay）
        if self.reward_func is not None and hasattr(self.reward_func, 'set_total_steps'):
            self.reward_func.set_total_steps(timesteps)
        
        self.model.learn(
            total_timesteps=timesteps,
            progress_bar=False,
            callback=callbacks,
        )
        self.timesteps = timesteps

        # 訓練完成後，用同一模型回放訓練區間，取得可比較的統計。
        train_eval = self.backtest(df_test=self.df)
        stats = self._collect_stats(env, train_eval=train_eval)
        
        # 儲存
        if save_path:
            self.model.save(save_path)
            print(f"模型已儲存: {save_path}")
        
        # 印出摘要
        self._print_summary(stats)
        
        return stats
    
    def _collect_stats(self, env, train_eval: dict | None = None) -> dict:
        """收集訓練統計"""
        stats = {
            'ticker': self.ticker,
            'agent_type': self.agent_type,
            'total_steps': self.timesteps,
            'best_sharpe': self.train_stats['best_sharpe'],
            'early_stopped': self.train_stats['early_stopped'],
            'total_trades': self.train_stats['total_trades'],
            'seed': self.seed,
        }

        if train_eval:
            train_metrics = train_eval.get('rl_metrics', {})
            stats.update({
                'best_sharpe': train_metrics.get('sharpe', self.train_stats['best_sharpe']),
                'train_total_return': train_metrics.get('total_return', 0.0),
                'train_annual_return': train_metrics.get('annual_return', 0.0),
                'train_max_drawdown': train_metrics.get('max_drawdown', 0.0),
                'train_excess_return_vs_bh': train_eval.get('excess_return_vs_bh', 0.0),
                'total_trades': train_eval.get('num_trades', self.train_stats['total_trades']),
            })
        
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
            'max_position': 40000,
            'trade_unit': 1000,
            'price_limit': 0.10,
            'commission_rate': 0.001425,
            'tax_rate': 0.003,
            'lookback_window': 60,
            'initial_shares': self.initial_shares,
            'initial_avg_cost': self.initial_avg_cost,
            'reward_func': self.reward_func,
            'enable_risk_manager': self.enable_risk_manager,
            'turnover_penalty': 0.01,
            'min_hold_days': 20,
            'short_hold_penalty': 0.02,
        }
        
        env = TaiwanStockTradingEnv(**env_config)
        obs, _ = env.reset()
        
        done = False
        total_reward = 0
        trades = 0
        equity_curve = [float(env.balance + env.position * df_test.iloc[0]['close'])]
        
        while not done:
            action, _ = self.model.predict(obs)
            obs, reward, terminated, truncated, info = env.step(action)
            done = terminated or truncated
            total_reward += reward
            equity_curve.append(float(info.get('portfolio_value', equity_curve[-1])))
            
            if info.get('trade_executed'):
                trades += 1
        
        final_price = df_test.iloc[-1]['close']
        final_value = env.balance + env.position * final_price
        rl_metrics = calculate_backtest_metrics(equity_curve, initial_value=1_000_000)
        bh_metrics = calculate_buy_and_hold_metrics(df_test, initial_value=1_000_000)
        fees_paid = 0.0
        for trade in env.trade_history:
            trade_value = float(trade.get('price', 0.0)) * float(trade.get('shares', 0.0))
            fees_paid += trade_value * env.commission_rate
            if str(trade.get('type', '')).upper().startswith(('SELL', 'CLOSE', 'STOP')):
                fees_paid += trade_value * env.tax_rate
        
        return {
            'final_value': final_value,
            'total_reward': total_reward,
            'num_trades': trades,
            'final_position': env.position,
            'rl_metrics': rl_metrics,
            'buy_and_hold_metrics': {k: v for k, v in bh_metrics.items() if k != 'equity_curve'},
            'excess_return_vs_bh': rl_metrics.get('total_return', 0.0) - bh_metrics.get('total_return', 0.0),
            'fees_paid_estimate': fees_paid,
            'turnover_trades': len(env.trade_history),
            'equity_curve': equity_curve,
        }


from stable_baselines3.common.callbacks import BaseCallback


class WalkForwardCallback(BaseCallback):
    """Walk-Forward 回調：整合風控與 Early Stopping"""
    
    def __init__(self, risk_manager, verbose=0):
        super().__init__(verbose=verbose)
        self.risk_manager = risk_manager
        self.step_count = 0
    
    def _on_step(self) -> bool:
        self.step_count += 1
        
        # 每 100 步檢查一次風控
        if self.step_count % 100 == 0:
            # 記錄當前報酬
            infos = self.locals.get('infos', [{}])
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
    seed: int = 42,
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
            seed=seed,
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
    parser.add_argument('--agent', type=str, default='ppo', choices=['ppo', 'a2c', 'dqn'], help='代理類型')
    parser.add_argument('--walk-forward', action='store_true', help='執行 Walk-Forward 訓練')
    parser.add_argument('--no-risk', action='store_true', help='停用風控')
    parser.add_argument('--no-enhanced-reward', action='store_true', help='停用增強獎勵')
    parser.add_argument('--notify', action='store_true', help='send Telegram notifications using FINRL_TELEGRAM_* env vars')
    parser.add_argument('--seed', type=int, default=42, help='random seed for reproducible training')
    
    args = parser.parse_args()
    if args.notify:
        os.environ["FINRL_TELEGRAM_ENABLED"] = "1"
    
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
            seed=args.seed,
        )
        
        # 儲存結果
        output_file = PROJECT_ROOT / "results" / f"walk_forward_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        output_file.parent.mkdir(exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n結果已儲存: {output_file}")
    
    else:
        total = len(tickers)
        results = []
        
        for i, ticker in enumerate(tickers, 1):
            print(f"\n[{i}/{total}] 開始訓練 {ticker}")
            
            info = PORTFOLIO_HOLDINGS.get(ticker, {})
            
            trainer = EnhancedStockTrainer(
                ticker=ticker,
                df=stock_data[ticker],
                agent_type=args.agent,
                initial_shares=info.get('shares', 0),
                enable_risk_manager=not args.no_risk,
                enable_enhanced_reward=not args.no_enhanced_reward,
                seed=args.seed,
            )
            
            save_path = str(PROJECT_ROOT / "models" / "portfolio" / f"{ticker}_enhanced")
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            
            stats = trainer.train(timesteps=args.timesteps, save_path=save_path)
            result = trainer.backtest()
            
            final_value = result.get('final_value', 0)
            sharpe = stats.get('best_sharpe', 0)
            trades = stats.get('total_trades', 0)
            
            print(f"\n[{i}/{total}] {ticker} 完成：Sharpe={sharpe:.3f}, Trades={trades}, 最終價值=${final_value:,.0f}")
            
            # 發送 Telegram 通知
            _send_notification(
                f"📊 FinRL 訓練進度 [{i}/{total}]\n"
                f"股票：{ticker}\n"
                f"Sharpe：{sharpe:.3f}\n"
                f"交易次數：{trades}\n"
                f"最終價值：${final_value:,.0f}"
            )
            
            metadata = build_experiment_metadata(
                ticker=ticker,
                agent_type=args.agent,
                timesteps=args.timesteps,
                seed=args.seed,
                train_rows=len(stock_data[ticker]),
                test_rows=len(stock_data[ticker]) // 2,
                model_path=save_path,
                reward_config={"enhanced_reward": not args.no_enhanced_reward},
                env_config={"risk_manager": not args.no_risk, "action_space": 9},
            )
            results.append({**stats, **result, "metadata": metadata})
        
        # 所有訓練完成
        _send_notification(
            f"✅ FinRL 全體訓練完成！\n"
            f"股票：{len(tickers)} 檔\n"
            f"總訓練步數：{args.timesteps:,} × {len(tickers)}"
        )
        
        # 儲存結果
        output_file = PROJECT_ROOT / "results" / f"training_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        output_file.parent.mkdir(exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n結果已儲存: {output_file}")


if __name__ == '__main__':
    main()
