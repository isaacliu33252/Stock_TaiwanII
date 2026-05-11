#!/usr/bin/env python3
# ============================================================================
# RL Portfolio Backtester - 用訓練好的 RL Agent 做投資組合回測
# ============================================================================
"""
對比「RL Agent 决策」vs「單純持有」的投資績效。

用途：
    1. 驗證訓練出來的 RL Agent 是否能跑赢 buy & hold
    2. 了解 RL Agent 在哪些市場環境下決策顯著不同
    3. 診斷 RL Agent 是否學到了有意義的交易信號

實作方式：
    - 每個股票各自有一個訓練好的 Agent
    - 每天每個 Agent 根據當前狀態預測動作（0-4）
    - 如果 Agent 說 SELL 但沒有持股，自動轉為 HOLD
    - 最後把 RL 組合 vs buy & hold 組合擺在一起比

用法:
    # 測試 0050
    python rl_portfolio_backtest.py --agent ppo --tickers 0050.TW --start 2021-01-01 --end 2024-12-31

    # 所有股票
    python rl_portfolio_backtest.py --agent ppo --start 2021-01-01 --end 2024-12-31

    # 沒有訓練好的模型時，自動生成隨機策略的 Baseline
    python rl_portfolio_backtest.py --random-baseline --start 2021-01-01 --end 2024-12-31
"""

import argparse
import sys
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from portfolio_config import PORTFOLIO_HOLDINGS, RISK_FREE_RATE
from portfolio_data_loader import download_all_stocks


# ─────────────────────────────────────────────────────────────────────────────
# Stable-Baselines3 Agent Runner
# ─────────────────────────────────────────────────────────────────────────────

class RLAgentRunner:
    """
    負責載入並執行訓練好的 RL Agent。

    流程：
        1. 嘗試從 models/portfolio/ 目錄載入 .zip 模型
        2. 若找不到，退化為 RandomRunner
        3. 每個 step 呼叫 model.predict(state, deterministic=True)
    """

    def __init__(self, ticker: str, agent_type: str, models_dir: Path):
        self.ticker = ticker
        self.agent_type = agent_type
        self.models_dir = models_dir
        self.model = None
        self.env = None
        self._load_model()

    def _load_model(self):
        model_file = self.models_dir / f"{self.ticker.replace('.', '_')}_{self.agent_type}.zip"
        if not model_file.exists():
            print(f"      ⚠  模型不存在: {model_file} → 使用 Random Baseline")
            self.model = None
            return

        try:
            if self.agent_type == "ppo":
                from stable_baselines3 import PPO
                self.model = PPO.load(str(model_file))
            elif self.agent_type == "a2c":
                from stable_baselines3 import A2C
                self.model = A2C.load(str(model_file))
            print(f"      ✅ 模型載入: {model_file.name}")
        except Exception as e:
            print(f"      ⚠  模型載入失敗: {e} → 使用 Random Baseline")
            self.model = None

    def predict(self, state: np.ndarray, deterministic: bool = True) -> int:
        """給定狀態，回傳動作（0-4）"""
        if self.model is None:
            # Random baseline
            import gymnasium as gym
            return gym.spaces.Discrete(5).sample()
        return self.model.predict(state, deterministic=deterministic)[0]


class RandomBaseline:
    """純隨機策略的 Baseline Runner。"""
    def __init__(self, ticker: str):
        self.ticker = ticker
        import gymnasium as gym
        self._space = gym.spaces.Discrete(5)

    def predict(self, state: np.ndarray, deterministic: bool = True) -> int:
        return self._space.sample()


# ─────────────────────────────────────────────────────────────────────────────
# RL Backtester
# ─────────────────────────────────────────────────────────────────────────────

class RLPortfolioBacktester:
    """
    使用 RL Agent 决策進行投資組合回測。

    對比：
        - RL 組合：每個股票由 RL Agent 决策
        - Buy & Hold 組合：初始買入後持有不動

    核心：每個股票獨立一個 TaiwanStockTradingEnv + Agent。
    """

    def __init__(
        self,
        stock_data: dict,           # {ticker: DataFrame}
        holdings: dict,             # PORTFOLIO_HOLDINGS
        agent_type: str = "ppo",
        models_dir: Path = None,
        use_random_baseline: bool = False,
    ):
        self.stock_data = stock_data
        self.holdings = holdings
        self.agent_type = agent_type
        self.models_dir = models_dir or (PROJECT_ROOT / "FinRL" / "models" / "portfolio")
        self.use_random_baseline = use_random_baseline

        self.rl_portfolio_values = {}   # {ticker: series}
        self.bh_portfolio_values = {}    # {ticker: series}
        self.agent_trades = {}          # {ticker: list of trade dicts}
        self.metrics = {}

    def _build_aligned_data(self):
        """對齊所有股票的交易日。"""
        all_dates = set()
        for ticker, df in self.stock_data.items():
            if 'date' not in df.columns:
                continue
            all_dates.update(pd.to_datetime(df['date']).tolist())
        common_dates = sorted(all_dates)
        self.common_dates = pd.DatetimeIndex(common_dates)

    def _run_single_stock(self, ticker: str, df: pd.DataFrame) -> dict:
        """對單一股票跑 RL vs Buy&Hold 回測。"""
        info = self.holdings.get(ticker, {})
        shares = info.get('shares', 0)

        df = df.copy()
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date').sort_index()

        # ── 對齊日期 ────────────────────────────────────────────────
        df_aligned = df.reindex(self.common_dates, method='ffill')

        # ── 初始化 Agent ────────────────────────────────────────────
        if self.use_random_baseline:
            agent = RandomBaseline(ticker)
        else:
            agent = RLAgentRunner(ticker, self.agent_type, self.models_dir)

        # ── 初始化余額與持股 ─────────────────────────────────────────
        initial_balance = 1_000_000
        balance = initial_balance
        position = shares   # RL 從一開始就假設持有這些股票
        avg_cost = 0.0

        if shares > 0 and len(df_aligned) > 0:
            first_price = df_aligned['close'].dropna().iloc[0]
            avg_cost = first_price

        commission_rate = 0.001425
        tax_rate = 0.003
        trade_unit = 1000

        rl_values = []
        bh_values = []
        trades = []

        # ── T+2 結算追蹤（與 taiwan_stock_env.py 一致）─────────────
        # pending_shares: {step -> shares bought at that step (locked until step+2)}
        pending_shares: dict = {}
        # avg_cost 改為追蹤「已交割持股」的平均成本
        settled_position = 0  # 已交割、可立即賣出的持股
        avg_cost_settled = 0.0  # 已交割持股的平均成本
        prev_close = None
        current_step = 0

        for i, date in enumerate(self.common_dates):
            current_step = i  # 使用 index 作為 step

            if date not in df_aligned.index:
                rl_values.append(np.nan)
                bh_values.append(np.nan)
                continue

            row = df_aligned.loc[date]
            close = row['close']
            if pd.isna(close):
                rl_values.append(np.nan)
                bh_values.append(np.nan)
                continue

            # ── T+2 結算：處理前天買入的股票交割 ─────────────────────
            # 前天（step-2）買入的股票今天結算交割
            settlement_key = current_step - 2
            if settlement_key in pending_shares and pending_shares[settlement_key] > 0:
                settled_shares = pending_shares[settlement_key]
                # 計算這批股票的買入成本（含佣金）
                settlement_cost = settled_shares * close  # 簡化：用當日 close 作為成本 proxy
                if settled_position > 0:
                    # 加權平均成本
                    total_cost = settled_position * avg_cost_settled + settlement_cost
                    settled_position += settled_shares
                    avg_cost_settled = total_cost / settled_position if settled_position > 0 else 0.0
                else:
                    settled_position = settled_shares
                    avg_cost_settled = settlement_cost / settled_shares if settled_shares > 0 else 0.0
                pending_shares[settlement_key] = 0

            # 計算可賣出股數（總持股 - T+2 鎖定）
            locked_shares = sum(count for step, count in pending_shares.items()
                                if step > current_step and count > 0)
            sellable = settled_position

            # ── Buy & Hold 組合值 ──────────────────────────────────
            bh_value = shares * close

            # ── RL Agent 决策 ──────────────────────────────────────
            if avg_cost_settled > 0 and sellable > 0:
                unrealized = (close - avg_cost_settled) / avg_cost_settled
            else:
                unrealized = 0.0

            state = np.array([
                close / 1000,           # normalize price
                sellable / 4000,        # sellable position ratio
                unrealized,              # unrealized pnl
                0.0, 0.0, 0.0, 0.0, 0.0,
                0.0, 0.0, 0.0, 0.0, 0.0,
                0.0, 0.0, 0.0, 0.0, 0.0,
                0.0, 0.0, 0.0, 0.0, 0.0,
                0.0, 0.0, 0.0, 0.0, 0.0,
                0.0, 0.0, 0.0, 0.0, 0.0,
                0.0, 0.0, 0.0, 0.0, 0.0,
                0.0, 0.0, 0.0, 0.0, 0.0,
                0.0, 0.0, 0.0, 0.0, 0.0,
                0.0, 0.0,
            ], dtype=np.float32)

            action = agent.predict(state, deterministic=True)

            # ── 執行交易（含 T+2 鎖定追蹤）──────────────────────────
            executed = False
            msg = "HOLD"

            if action == 1 and balance >= close * trade_unit:   # BUY
                cost = close * trade_unit * (1 + commission_rate)
                if balance >= cost:
                    balance -= cost
                    # 買入後先進入 pending_shares（T+2 鎖定）
                    settle_step = current_step + 2
                    pending_shares[settle_step] = pending_shares.get(settle_step, 0) + trade_unit
                    settled_position += trade_unit
                    total_cost_new = settled_position * avg_cost_settled + cost
                    avg_cost_settled = total_cost_new / settled_position if settled_position > 0 else 0.0
                    executed = True
                    msg = f"BUY {trade_unit}@{close:.2f}"
                    trades.append({'date': date, 'action': 'BUY', 'price': close, 'shares': trade_unit})

            elif action in [2, 3, 4] and sellable >= trade_unit:   # SELL / CLOSE / STOP_LOSS
                sell_shares = min(trade_unit, sellable)
                proceeds = close * sell_shares * (1 - commission_rate - tax_rate)
                balance += proceeds
                settled_position -= sell_shares
                if settled_position == 0:
                    avg_cost_settled = 0.0
                pnl = proceeds - sell_shares * (close / (1 + commission_rate + tax_rate))
                executed = True
                msg = f"SELL {sell_shares}@{close:.2f} PnL={pnl:.0f}"
                trades.append({'date': date, 'action': 'SELL', 'price': close, 'shares': sell_shares, 'pnl': pnl})

            # ── RL 組合價值（含 T+2 鎖定）───────────────────────────
            # 鎖定中的股票仍計入組合價值（但不可賣）
            locked_value = locked_shares * close
            rl_value = balance + (sellable + locked_shares) * close
            rl_values.append(rl_value)
            bh_values.append(bh_value)
            prev_close = close

        # 組合成 Series
        rl_series = pd.Series(rl_values, index=self.common_dates)
        bh_series = pd.Series(bh_values, index=self.common_dates)

        return {
            'rl': rl_series,
            'bh': bh_series,
            'trades': trades,
            'final_rl': rl_series.dropna().iloc[-1] if len(rl_series.dropna()) > 0 else 0,
            'final_bh': bh_series.dropna().iloc[-1] if len(bh_series.dropna()) > 0 else 0,
            'n_trades': len(trades),
        }

    def run(self, output: bool = True) -> dict:
        """執行所有股票的 RL 回測。"""
        self._build_aligned_data()

        ticker_results = {}

        for ticker, df in self.stock_data.items():
            if output:
                print(f"  {ticker}: ", end="")
            result = self._run_single_stock(ticker, df)
            ticker_results[ticker] = result

            if output:
                rl_ret = (result['final_rl'] / result['rl'].dropna().iloc[0] - 1) * 100
                bh_ret = (result['final_bh'] / result['bh'].dropna().iloc[0] - 1) * 100
                diff = rl_ret - bh_ret
                print(f"RL={rl_ret:+.1f}% BH={bh_ret:+.1f}% Δ={diff:+.1f}% trades={result['n_trades']}")

        self.ticker_results = ticker_results

        # ── 計算整體組合 ──────────────────────────────────────────────
        rl_combined = pd.concat([r['rl'] for r in ticker_results.values()], axis=1).sum(axis=1)
        bh_combined = pd.concat([r['bh'] for r in ticker_results.values()], axis=1).sum(axis=1)

        self.rl_combined = rl_combined.dropna()
        self.bh_combined = bh_combined.dropna()

        rl_initial = self.rl_combined.iloc[0]
        bh_initial = self.bh_combined.iloc[0]

        rl_total = self.rl_combined.iloc[-1] / rl_initial - 1
        bh_total = self.bh_combined.iloc[-1] / bh_initial - 1

        rl_daily = self.rl_combined.pct_change().dropna()
        bh_daily = self.bh_combined.pct_change().dropna()

        rl_sharpe = (rl_daily.mean() * 252 - RISK_FREE_RATE) / (rl_daily.std(ddof=1) * np.sqrt(252) + 1e-10)
        bh_sharpe = (bh_daily.mean() * 252 - RISK_FREE_RATE) / (bh_daily.std(ddof=1) * np.sqrt(252) + 1e-10)

        rl_cum = (1 + rl_daily).cumprod()
        rl_running_max = rl_cum.cummax()
        rl_mdd = ((rl_cum - rl_running_max) / rl_running_max).min()

        bh_cum = (1 + bh_daily).cumprod()
        bh_running_max = bh_cum.cummax()
        bh_mdd = ((bh_cum - bh_running_max) / bh_running_max).min()

        self.metrics = {
            'rl_total_return': rl_total,
            'bh_total_return': bh_total,
            'rl_annual_return': (1 + rl_total) ** (252 / len(rl_daily)) - 1,
            'bh_annual_return': (1 + bh_total) ** (252 / len(bh_daily)) - 1,
            'rl_sharpe': rl_sharpe,
            'bh_sharpe': bh_sharpe,
            'rl_mdd': rl_mdd,
            'bh_mdd': bh_mdd,
            'outperformance': rl_total - bh_total,
        }

        if output:
            self._print_summary()

        return self.metrics

    def _print_summary(self):
        m = self.metrics
        print("\n" + "=" * 60)
        print("  RL Agent vs Buy & Hold 對比報告")
        print("=" * 60)
        print(f"  Agent: {self.agent_type.upper()} ({'Random Baseline' if self.use_random_baseline else 'Trained Model'})")
        print(f"  總報酬     RL: {m['rl_total_return']*100:+8.2f}%  |  BH: {m['bh_total_return']*100:+8.2f}%")
        print(f"  年化報酬   RL: {m['rl_annual_return']*100:+8.2f}%  |  BH: {m['bh_annual_return']*100:+8.2f}%")
        print(f"  Sharpe    RL: {m['rl_sharpe']:>+8.3f}  |  BH: {m['bh_sharpe']:>+8.3f}")
        print(f"  最大回測  RL: {m['rl_mdd']*100:>+8.2f}%  |  BH: {m['bh_mdd']*100:>+8.2f}%")
        print(f"  超額報酬（RL - BH）: {m['outperformance']*100:>+8.2f}%")
        print("=" * 60)

    def plot_comparison(self, save_path: str = None):
        """繪製 RL vs BH 組合價值曲線。"""
        try:
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates

            fig, axes = plt.subplots(2, 1, figsize=(14, 10))

            # 圖1：組合價值
            ax1 = axes[0]
            dates = self.rl_combined.index
            ax1.plot(dates, self.rl_combined.values, label='RL Agent', linewidth=1.5, color='blue')
            ax1.plot(dates, self.bh_combined.values, label='Buy & Hold', linewidth=1.5, color='orange', alpha=0.7)
            ax1.set_title('RL Agent vs Buy & Hold 組合價值', fontsize=14)
            ax1.set_ylabel('組合價值 (TWD)')
            ax1.legend()
            ax1.grid(True, alpha=0.3)
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
            plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45)

            # 圖2：累計超額報酬
            ax2 = axes[1]
            excess = (self.rl_combined / self.bh_combined - 1) * 100
            ax2.plot(dates, excess.values, label='超額報酬 (RL - BH)', linewidth=1.5, color='green')
            ax2.axhline(0, color='black', linewidth=0.5)
            ax2.fill_between(dates, 0, excess.values,
                             where=excess.values >= 0, color='green', alpha=0.2)
            ax2.fill_between(dates, 0, excess.values,
                             where=excess.values < 0, color='red', alpha=0.2)
            ax2.set_title('累計超額報酬 (%)', fontsize=14)
            ax2.set_ylabel('超額報酬 (%)')
            ax2.legend()
            ax2.grid(True, alpha=0.3)
            ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
            plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)

            plt.tight_layout()

            if save_path:
                plt.savefig(save_path, dpi=150, bbox_inches='tight')
                print(f"圖表已儲存: {save_path}")
            plt.close()

        except ImportError:
            print("⚠ 需要 matplotlib 才能繪圖")


# ─────────────────────────────────────────────────────────────────────────────
# 主程式
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='RL Agent 投資組合回測')
    parser.add_argument('--agent', type=str, default='ppo',
                        choices=['ppo', 'a2c'],
                        help='Agent 類型')
    parser.add_argument('--tickers', type=str, default=None,
                        help='指定股票（逗號分隔），預設全部')
    parser.add_argument('--start', type=str, default='2021-01-01',
                        help='回測開始日期')
    parser.add_argument('--end', type=str, default='2024-12-31',
                        help='回測結束日期')
    parser.add_argument('--random-baseline', action='store_true',
                        help='使用隨機策略（無模型時也適用）')
    parser.add_argument('--save', action='store_true',
                        help='儲存結果圖表')
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(',')] if args.tickers else list(PORTFOLIO_HOLDINGS.keys())

    print("=" * 60)
    print("  RL Agent 投資組合回測")
    print("=" * 60)
    print(f"  Agent: {args.agent.upper()}")
    print(f"  股票: {tickers}")
    print(f"  日期: {args.start} ~ {args.end}")
    print(f"  模式: {'Random Baseline' if args.random_baseline else 'Trained Model'}")
    print("=" * 60)

    # 下載數據
    print("\n[1/2] 下載數據 ...")
    stock_data = download_all_stocks(
        tickers,
        args.start,
        args.end,
        cache_dir=str(PROJECT_ROOT / "data" / "portfolio_cache")
    )

    # 執行回測
    print("\n[2/2] 執行 RL 回測 ...")
    backtester = RLPortfolioBacktester(
        stock_data=stock_data,
        holdings=PORTFOLIO_HOLDINGS,
        agent_type=args.agent,
        use_random_baseline=args.random_baseline,
    )
    metrics = backtester.run(output=True)

    # 繪圖
    if args.save:
        chart_path = str(PROJECT_ROOT / "results" / "rl_backtest" / "rl_vs_bh.png")
        backtester.plot_comparison(save_path=chart_path)

    print("\n✅ 完成！")
