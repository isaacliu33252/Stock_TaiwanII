"""
Backtest Engine — FinRL-X 台股系統
====================================
移植 FinRL-X src/backtest/backtest_engine.py 的 bt library 架構，
並保留 Isaac 既有的績效指標（Sharpe, Sortino, Calmar, MDD 等）。

backtest_engine 負責：
  1. 接收 StrategyResult（weights DataFrame）
  2. 用 bt library 跑回測
  3. 輸出完整績效指標
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import numpy as np
import pandas as pd
import bt

from ..strategies.base_strategy import StrategyResult

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Config & Result
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BacktestConfig:
    """回測設定。"""
    start_date: str
    end_date: str
    initial_capital: float = 1_000_000.0
    rebalance_freq: str = "Q"          # Q/M/W/D
    transaction_cost: float = 0.001    # 0.1% per trade（手續費+稅）
    benchmark_tickers: List[str] = field(default_factory=lambda: ["0050.TW"])
    # 台股特有
    tax_rate: float = 0.003            # 交易稅（賣出）
    brokerage_fee: float = 0.001425    # 券商手續費
    min_brokerage_fee: float = 20.0   # 最低手續費
    # Cost model（FinRL-X 新增，優先使用）
    cost_model: Optional[Any] = None


@dataclass
class BacktestResult:
    """回測結果。"""
    strategy_name: str
    portfolio_returns: pd.Series
    portfolio_values: pd.Series
    weights_history: pd.DataFrame
    trades: pd.DataFrame
    metrics: Dict[str, float] = field(default_factory=dict)
    benchmark_values: Optional[pd.Series] = None
    benchmark_returns: Optional[pd.Series] = None

    def summary(self) -> str:
        m = self.metrics
        lines = [
            f"Strategy: {self.strategy_name}",
            f"Period: {self.portfolio_returns.index[0].date()} → {self.portfolio_returns.index[-1].date()}",
            f"Total Return: {m.get('total_return', 0)*100:.2f}%",
            f"Annual Return: {m.get('annual_return', 0)*100:.2f}%",
            f"Sharpe Ratio: {m.get('sharpe', 0):.3f}",
            f"Sortino Ratio: {m.get('sortino', 0):.3f}",
            f"Max Drawdown: {m.get('max_drawdown', 0)*100:.2f}%",
            f"Calmar Ratio: {m.get('calmar', 0):.3f}",
            f"Win Rate: {m.get('win_rate', 0)*100:.1f}%",
            f"Total Trades: {m.get('num_trades', 0)}",
        ]
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Backtest Engine
# ─────────────────────────────────────────────────────────────────────────────

class BacktestEngine:
    """
    執行策略回測，輸出績效指標。

    與 FinRL-X 的 backtest_engine.py 完全相容：
      - 接收 StrategyResult（weights DataFrame）
      - 內建完整的台股交易成本模型
      - 用 bt library 計算組合回報
    """

    def __init__(self, config: BacktestConfig = None):
        self.config = config or BacktestConfig(
            start_date="2020-01-01",
            end_date="2025-12-31",
        )
        self.logger = logging.getLogger(f"{__name__}.BacktestEngine")

    # ─────────────────────────── 主要 API ─────────────────────────────────

    def run(self, strategy_result: StrategyResult) -> BacktestResult:
        """
        執行回測。

        Args:
            strategy_result: 策略輸出的 StrategyResult
                             （weights DataFrame 為核心，index=date, columns=tickers）
        Returns:
            BacktestResult
        """
        weights = strategy_result.weights.copy()

        # 確保 columns 為 tickers（移除 multi-index 如果有的話）
        if isinstance(weights.columns, pd.MultiIndex):
            weights.columns = [c[0] if isinstance(c, tuple) else c for c in weights.columns]

        # 對齊日期
        weights.index = pd.to_datetime(weights.index)
        start = pd.to_datetime(self.config.start_date)
        end = pd.to_datetime(self.config.end_date)
        weights = weights.loc[(weights.index >= start) & (weights.index <= end)]

        if weights.empty:
            raise ValueError(f"No weights in date range [{start.date()}, {end.date()}]")

        # 取得價格資料（從 weights 的 tickers）
        tickers = list(weights.columns)
        prices = self._fetch_prices(tickers, start, end)

        # 建立 bt strategy
        strategy = self._build_bt_strategy(weights, prices)

        # 執行回測
        backtest = bt.Backtest(
            strategy,
            prices,
            initial_capital=self.config.initial_capital,
            commissions=self._cost_fn,
            progress_bar=False,
        )
        result = bt.run(backtest)

        # 取出各 series
        equity = result.get_series(" equity")
        returns = result.get_series("returns")

        # Benchmark（如果有）
        bm_values = None
        bm_returns = None
        if self.config.benchmark_tickers:
            bm_values, bm_returns = self._run_benchmark(prices)

        # 計算完整指標
        weights_history = self._get_weights_history(result)
        trades = self._get_trades(result)

        metrics = self._compute_metrics(
            returns, equity, bm_returns,
            trades, weights_history
        )

        return BacktestResult(
            strategy_name=strategy_result.strategy_name,
            portfolio_returns=returns,
            portfolio_values=equity,
            weights_history=weights_history,
            trades=trades,
            metrics=metrics,
            benchmark_values=bm_values,
            benchmark_returns=bm_returns,
        )

    # ─────────────────────────── 內部方法 ─────────────────────────────────

    def _cost_fn(self, q, price):
        """台股交易成本：手續費(0.1425%) + 交易稅(0.3%，僅賣出)"""
        trade_value = abs(q) * price
        # 手續費（買+賣）
        brokerage = max(trade_value * self.config.brokerage_fee, self.config.min_brokerage_fee)
        # 交易稅（只有賣出時）
        tax = trade_value * self.config.tax_rate if q < 0 else 0.0
        return brokerage + tax

    def _fetch_prices(self, tickers: List[str], start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        """
        取得價格資料。
        現階段從 cache 讀取（data/data_loader.py 的既有機制）。
        未來可替換為 src/data/data_fetcher.py。
        """
        cache_dir = Path("data/cache")
        dfs = []
        for tic in tickers:
            p = cache_dir / f"{tic.replace('.TW','')}_TW_{start.strftime('%Y-%m-%d')}_{end.strftime('%Y-%m-%d')}_1d.parquet"
            if p.exists():
                try:
                    import pyarrow.dataset as pad
                    ds = pad.dataset(str(p))
                    df = ds.to_table(timestamp_as_object=True).to_pandas(index="date")
                    df = df.sort_index()
                    dfs.append(df[["close"]].rename(columns={"close": tic}))
                except Exception:
                    df = pd.read_parquet(str(p))
                    if "date" in df.columns:
                        df = df.set_index("date").sort_index()
                    dfs.append(df[["close"]].rename(columns={"close": tic}))
            else:
                self.logger.warning(f"Price file not found: {p}")

        if not dfs:
            raise FileNotFoundError(f"No price data found for {tickers} in {cache_dir}")

        prices = pd.concat(dfs, axis=1).sort_index()
        # forward fill missing
        prices = prices.fillna(method="ffill").fillna(0)
        return prices.loc[start:end]

    def _build_bt_strategy(self, weights: pd.DataFrame, prices: pd.DataFrame) -> bt.Algo:
        """用 bt library 建立策略。"""
        # 將 weights 轉為 bt.Algo
        def weight_allocate(tickers, w_df, prices):
            def algo(p):
                date = p.now
                if date in w_df.index:
                    w = w_df.loc[date]
                    for tic in tickers:
                        if tic in w.index and w[tic] > 0:
                            p.update(tic, w[tic])
                return True
            return algo

        algo = weight_allocate(list(weights.columns), weights, prices)

        strategy = bt.Strategy(
            self.config.strategy_name if hasattr(self, 'strategy_name') else "RLPortfolio",
            algos=[
                bt.algos.SelectAll(),
                bt.algos.WeighSpecified(**{tic: 0.0 for tic in weights.columns}),
                algo,
                bt.algos.Rebalance(),
            ],
        )
        return strategy

    def _run_benchmark(self, prices: pd.DataFrame) -> tuple:
        """跑 Benchmark（預設 0050.TW）。"""
        bm_tic = self.config.benchmark_tickers[0]
        if bm_tic not in prices.columns:
            self.logger.warning(f"Benchmark {bm_tic} not in price data, skipping benchmark")
            return None, None
        bm_prices = prices[[bm_tic]].dropna()
        bm_strategy = bt.Strategy(
            "Benchmark",
            algos=[
                bt.algos.SelectAll(),
                bt.algos.WeighEqually(),
                bt.algos.Rebalance(),
            ],
        )
        bm_bt = bt.Backtest(bm_strategy, bm_prices, initial_capital=self.config.initial_capital)
        bm_result = bt.run(bm_bt)
        bm_equity = bm_result.get_series(" equity")
        bm_returns = bm_result.get_series("returns")
        return bm_equity, bm_returns

    def _get_weights_history(self, result) -> pd.DataFrame:
        """從 bt result 取出權重歷史。"""
        try:
            # bt stores weights in the strategy
            frames = []
            for strat in result.strategies:
                w = strat.weight_history
                if w is not None and not w.empty:
                    frames.append(w)
            if frames:
                return pd.concat(frames, axis=0).sort_index()
        except Exception as e:
            self.logger.warning(f"Could not extract weights_history: {e}")
        return pd.DataFrame()

    def _get_trades(self, result) -> pd.DataFrame:
        """從 bt result 取出交易記錄。"""
        try:
            for strat in result.strategies:
                t = strat.trades
                if t is not None and not t.empty:
                    return t.copy()
        except Exception as e:
            self.logger.warning(f"Could not extract trades: {e}")
        return pd.DataFrame()

    def _compute_metrics(
        self,
        returns: pd.Series,
        equity: pd.Series,
        bm_returns: pd.Series,
        trades: pd.DataFrame,
        weights: pd.DataFrame,
    ) -> Dict[str, float]:
        """計算完整績效指標。"""
        n_days = len(returns)
        annualization = 252 / n_days if n_days > 0 else 1

        total_return = equity.iloc[-1] / equity.iloc[0] - 1 if not equity.empty else 0.0
        annual_return = (1 + total_return) ** annualization - 1

        # Volatility
        daily_vol = returns.std()
        annual_vol = daily_vol * np.sqrt(252)

        # Sharpe
        rf = 0.02  # 無風險利率
        excess = returns - rf / 252
        sharpe = excess.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0.0

        # Sortino
        downside = returns[returns < 0]
        downside_std = downside.std() * np.sqrt(252) if len(downside) > 0 else 1e-9
        sortino = (annual_return - rf) / downside_std if downside_std > 0 else 0.0

        # Max Drawdown
        cummax = equity.cummax()
        drawdown = (equity - cummax) / cummax
        max_dd = drawdown.min()

        # Calmar
        calmar = annual_return / abs(max_dd) if max_dd != 0 else 0.0

        # Win rate
        positive = (returns > 0).sum()
        total = (returns != 0).sum()
        win_rate = positive / total if total > 0 else 0.0

        # Sharpe vs benchmark
        rl_vs_bm = 0.0
        if bm_returns is not None and not bm_returns.empty:
            aligned_ret, aligned_bm = returns.align(bm_returns, join="inner")
            rl_vs_bm = (aligned_ret - aligned_bm).mean() / (aligned_ret - aligned_bm).std() * np.sqrt(252) if (aligned_ret - aligned_bm).std() > 0 else 0.0

        return {
            "total_return": total_return,
            "annual_return": annual_return,
            "sharpe": sharpe,
            "sortino": sortino,
            "max_drawdown": max_dd,
            "calmar": calmar,
            "win_rate": win_rate,
            "num_trades": len(trades) if not trades.empty else 0,
            "annual_volatility": annual_vol,
            "sharpe_vs_benchmark": rl_vs_bm,
            "benchmark_return": bm_returns.mean() * 252 if bm_returns is not None else 0.0,
        }