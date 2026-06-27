"""
Backtest Engine — FinRL-X style weight-centric backtesting
===========================================================
使用 bt library 執行權重驅動回測，保留本地 FinRL 常用績效指標。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import bt
import numpy as np
import pandas as pd

from ..strategies.base_strategy import StrategyResult

logger = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    start_date: str
    end_date: str
    initial_capital: float = 1_000_000.0
    rebalance_freq: str = "D"
    transaction_cost: float = 0.001
    benchmark_tickers: List[str] = field(default_factory=lambda: ["0050.TW"])
    tax_rate: float = 0.003
    brokerage_fee: float = 0.001425
    min_brokerage_fee: float = 20.0
    cost_model: Optional[Any] = None
    price_dir: Optional[str] = None
    risk_free_rate: float = 0.02


@dataclass
class BacktestResult:
    strategy_name: str
    portfolio_returns: pd.Series
    portfolio_values: pd.Series
    weights_history: pd.DataFrame
    trades: pd.DataFrame
    metrics: Dict[str, float] = field(default_factory=dict)
    benchmark_values: Optional[pd.Series] = None
    benchmark_returns: Optional[pd.Series] = None

    def summary(self) -> str:
        if self.portfolio_values.empty:
            return f"Strategy: {self.strategy_name}\nNo backtest results."

        period_start = self.portfolio_values.index[0].date()
        period_end = self.portfolio_values.index[-1].date()
        m = self.metrics
        return "\n".join(
            [
                f"Strategy: {self.strategy_name}",
                f"Period: {period_start} -> {period_end}",
                f"Total Return: {m.get('total_return', 0.0) * 100:.2f}%",
                f"Annual Return: {m.get('annual_return', 0.0) * 100:.2f}%",
                f"Sharpe Ratio: {m.get('sharpe', 0.0):.3f}",
                f"Sortino Ratio: {m.get('sortino', 0.0):.3f}",
                f"Max Drawdown: {m.get('max_drawdown', 0.0) * 100:.2f}%",
                f"Calmar Ratio: {m.get('calmar', 0.0):.3f}",
                f"Win Rate: {m.get('win_rate', 0.0) * 100:.1f}%",
                f"Total Trades: {m.get('num_trades', 0)}",
            ]
        )


class BacktestEngine:
    """
    FinRL-X 風格的權重式回測引擎。

    權重來源優先順序：
    1. `StrategyResult.metadata["weights_full"]`
    2. `StrategyResult.weights`

    價格來源優先順序：
    1. `metadata["prices"]` / `["price_frame"]` / `["close_prices"]`
    2. `metadata["price_data"]`
    3. 本地 `data/cache/*.parquet`
    """

    def __init__(self, config: Optional[BacktestConfig] = None):
        self.config = config or BacktestConfig(
            start_date="2020-01-01",
            end_date="2025-12-31",
        )
        self.logger = logging.getLogger(f"{__name__}.BacktestEngine")

    def run(self, strategy_result: StrategyResult) -> BacktestResult:
        weights = self._resolve_weights(strategy_result)
        start = pd.Timestamp(self.config.start_date)
        end = pd.Timestamp(self.config.end_date)
        weights = weights.loc[(weights.index >= start) & (weights.index <= end)]
        if weights.empty:
            raise ValueError(f"No weights in date range [{start.date()}, {end.date()}]")

        tickers = list(weights.columns)
        prices = self._resolve_prices(strategy_result, tickers, start, end)
        prices = prices.loc[(prices.index >= start) & (prices.index <= end), tickers]
        prices = prices.sort_index().ffill().dropna(how="all")
        if prices.empty:
            raise ValueError("No price data available after alignment.")

        weights = self._align_weights_to_prices(weights, prices.index)
        if weights.empty:
            raise ValueError("No valid rebalance dates overlap with price data.")

        strategy_name = strategy_result.strategy_name or "RLPortfolio"
        strategy = self._build_bt_strategy(strategy_name, weights)
        backtest = bt.Backtest(
            strategy,
            prices,
            initial_capital=self.config.initial_capital,
            commissions=self._cost_fn,
            progress_bar=False,
        )
        result = bt.run(backtest)

        equity = self._scaled_equity(result.prices[strategy_name].astype(float)).rename("portfolio_value")
        returns = equity.pct_change().dropna().rename("portfolio_return")
        weights_history = self._get_weights_history(result, strategy_name)
        trades = self._get_trades(result, strategy_name)

        benchmark_values, benchmark_returns = self._run_benchmark(prices, start, end)
        metrics = self._compute_metrics(
            returns=returns,
            equity=equity,
            benchmark_returns=benchmark_returns,
            trades=trades,
            weights=weights_history,
        )

        return BacktestResult(
            strategy_name=strategy_name,
            portfolio_returns=returns,
            portfolio_values=equity,
            weights_history=weights_history,
            trades=trades,
            metrics=metrics,
            benchmark_values=benchmark_values,
            benchmark_returns=benchmark_returns,
        )

    def _cost_fn(self, quantity: float, price: float) -> float:
        if self.config.cost_model is not None:
            return float(self.config.cost_model(quantity, price))
        trade_value = abs(float(quantity) * float(price))
        brokerage = max(
            trade_value * self.config.brokerage_fee,
            self.config.min_brokerage_fee,
        )
        tax = trade_value * self.config.tax_rate if quantity < 0 else 0.0
        return float(brokerage + tax)

    def _resolve_weights(self, strategy_result: StrategyResult) -> pd.DataFrame:
        metadata = strategy_result.metadata or {}
        full_weights = metadata.get("weights_full")
        weights = full_weights if isinstance(full_weights, pd.DataFrame) and not full_weights.empty else strategy_result.weights
        if weights is None or weights.empty:
            raise ValueError("StrategyResult does not contain usable weights.")

        frame = weights.copy()
        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = [col[0] if isinstance(col, tuple) else col for col in frame.columns]
        frame = self._coerce_datetime_index(frame)
        frame = frame.apply(pd.to_numeric, errors="coerce").fillna(0.0)
        frame = frame.loc[:, ~frame.columns.duplicated()].copy()
        frame = frame.sort_index().clip(lower=0.0)
        return frame

    def _resolve_prices(
        self,
        strategy_result: StrategyResult,
        tickers: List[str],
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> pd.DataFrame:
        metadata = strategy_result.metadata or {}

        for key in ("prices", "price_frame", "close_prices"):
            value = metadata.get(key)
            if isinstance(value, pd.DataFrame) and not value.empty:
                prices = self._coerce_datetime_index(value.copy()).sort_index()
                return prices.loc[:, [tic for tic in tickers if tic in prices.columns]]

        price_data = metadata.get("price_data")
        if isinstance(price_data, dict) and price_data:
            prices = self._price_dict_to_frame(price_data, tickers)
            if not prices.empty:
                return prices

        return self._fetch_prices(tickers, start, end)

    def _price_dict_to_frame(
        self,
        price_data: Dict[str, pd.DataFrame],
        tickers: List[str],
    ) -> pd.DataFrame:
        frames: List[pd.DataFrame] = []
        for ticker in tickers:
            df = price_data.get(ticker)
            if not isinstance(df, pd.DataFrame) or df.empty:
                continue
            local = self._coerce_datetime_index(df.copy())
            if "close" not in local.columns:
                continue
            frames.append(local[["close"]].rename(columns={"close": ticker}))
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, axis=1).sort_index()

    def _fetch_prices(
        self,
        tickers: List[str],
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> pd.DataFrame:
        frames: List[pd.DataFrame] = []
        for ticker in tickers:
            cache_file = self._locate_price_file(ticker)
            if cache_file is None:
                self.logger.warning("Price file not found for %s", ticker)
                continue
            price_df = self._read_price_file(cache_file, ticker)
            if price_df.empty:
                continue
            frames.append(price_df[[ticker]])

        if not frames:
            raise FileNotFoundError(f"No price data found for {tickers}")

        prices = pd.concat(frames, axis=1).sort_index().ffill()
        return prices.loc[(prices.index >= start) & (prices.index <= end)]

    def _locate_price_file(self, ticker: str) -> Optional[Path]:
        patterns = [
            f"{ticker}_*_1d.parquet",
            f"{ticker.replace('.TW', '')}_TW_*_1d.parquet",
        ]
        for cache_dir in self._candidate_cache_dirs():
            for pattern in patterns:
                matches = sorted(cache_dir.glob(pattern))
                if matches:
                    return matches[-1]
        return None

    def _candidate_cache_dirs(self) -> List[Path]:
        roots: List[Path] = []
        if self.config.price_dir:
            roots.append(Path(self.config.price_dir))

        package_root = Path(__file__).resolve().parents[1]
        roots.extend(
            [
                package_root / "data" / "cache",
                Path.cwd() / "data" / "cache",
                Path.cwd() / "FinRL" / "data" / "cache",
            ]
        )

        unique_roots: List[Path] = []
        for root in roots:
            resolved = root.resolve()
            if resolved.exists() and resolved not in unique_roots:
                unique_roots.append(resolved)
        return unique_roots

    def _read_price_file(self, path: Path, ticker: str) -> pd.DataFrame:
        df = pd.read_parquet(path)
        local = self._coerce_datetime_index(df)
        if "close" in local.columns:
            prices = local[["close"]].rename(columns={"close": ticker})
        elif ticker in local.columns:
            prices = local[[ticker]].copy()
        else:
            raise ValueError(f"Unsupported price file format: {path}")
        return prices.sort_index()

    def _build_bt_strategy(self, strategy_name: str, weights: pd.DataFrame) -> bt.Strategy:
        return bt.Strategy(
            strategy_name,
            [
                bt.algos.SelectAll(),
                bt.algos.WeighTarget(weights),
                bt.algos.Rebalance(),
            ],
        )

    def _align_weights_to_prices(
        self,
        weights: pd.DataFrame,
        trading_index: pd.DatetimeIndex,
    ) -> pd.DataFrame:
        trading_days = pd.DatetimeIndex(trading_index).sort_values()
        if trading_days.empty:
            return pd.DataFrame(columns=weights.columns)

        aligned_rows = []
        aligned_index = []
        for when, row in weights.sort_index().iterrows():
            pos = trading_days.searchsorted(when, side="left")
            if pos >= len(trading_days):
                continue
            aligned_index.append(trading_days[pos])
            aligned_rows.append(row)

        if not aligned_rows:
            return pd.DataFrame(columns=weights.columns)

        aligned = pd.DataFrame(aligned_rows, index=pd.DatetimeIndex(aligned_index), columns=weights.columns)
        return aligned.groupby(level=0).last().sort_index().fillna(0.0).clip(lower=0.0)

    def _run_benchmark(
        self,
        prices: pd.DataFrame,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> tuple[Optional[pd.Series], Optional[pd.Series]]:
        tickers = [ticker for ticker in self.config.benchmark_tickers if ticker]
        if not tickers:
            return None, None

        benchmark_prices = prices[[ticker for ticker in tickers if ticker in prices.columns]].copy()
        missing = [ticker for ticker in tickers if ticker not in benchmark_prices.columns]
        if missing:
            fetched = self._fetch_prices(missing, start, end)
            benchmark_prices = pd.concat([benchmark_prices, fetched], axis=1)

        benchmark_prices = benchmark_prices.loc[:, ~benchmark_prices.columns.duplicated()].sort_index().ffill()
        benchmark_prices = benchmark_prices[[ticker for ticker in tickers if ticker in benchmark_prices.columns]]
        if benchmark_prices.empty:
            self.logger.warning("No benchmark prices available, skipping benchmark.")
            return None, None

        benchmark = bt.Backtest(
            bt.Strategy(
                "Benchmark",
                [
                    bt.algos.SelectAll(),
                    bt.algos.WeighEqually(),
                    bt.algos.Rebalance(),
                ],
            ),
            benchmark_prices,
            initial_capital=self.config.initial_capital,
            progress_bar=False,
        )
        result = bt.run(benchmark)
        equity = self._scaled_equity(result.prices["Benchmark"].astype(float)).rename("benchmark_value")
        returns = equity.pct_change().dropna().rename("benchmark_return")
        return equity, returns

    def _scaled_equity(self, series: pd.Series) -> pd.Series:
        equity = series.astype(float).copy()
        if equity.empty:
            return equity
        first_value = float(equity.iloc[0])
        if first_value == 0:
            return equity
        scale = self.config.initial_capital / first_value
        return equity * scale

    def _get_weights_history(self, result: bt.backtest.Result, strategy_name: str) -> pd.DataFrame:
        try:
            weights = result.get_security_weights(strategy_name)
        except TypeError:
            weights = result.get_security_weights()
        except Exception as exc:
            self.logger.warning("Could not extract weights history: %s", exc)
            return pd.DataFrame()
        return weights.sort_index().fillna(0.0)

    def _get_trades(self, result: bt.backtest.Result, strategy_name: str) -> pd.DataFrame:
        try:
            trades = result.get_transactions(strategy_name)
        except TypeError:
            trades = result.get_transactions()
        except Exception as exc:
            self.logger.warning("Could not extract trades: %s", exc)
            return pd.DataFrame()

        if trades is None or trades.empty:
            return pd.DataFrame()

        frame = trades.reset_index()
        frame.columns = ["date", "ticker", "price", "quantity"]
        frame["date"] = pd.to_datetime(frame["date"])
        frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
        frame["quantity"] = pd.to_numeric(frame["quantity"], errors="coerce")
        frame["side"] = np.where(frame["quantity"] >= 0, "buy", "sell")
        frame["trade_value"] = (frame["price"] * frame["quantity"].abs()).astype(float)
        frame["commission"] = np.maximum(
            frame["trade_value"] * self.config.brokerage_fee,
            self.config.min_brokerage_fee,
        )
        frame["tax"] = np.where(frame["quantity"] < 0, frame["trade_value"] * self.config.tax_rate, 0.0)
        frame["fees"] = frame["commission"] + frame["tax"]
        return frame.set_index("date").sort_index()

    def _compute_metrics(
        self,
        returns: pd.Series,
        equity: pd.Series,
        benchmark_returns: Optional[pd.Series],
        trades: pd.DataFrame,
        weights: pd.DataFrame,
    ) -> Dict[str, float]:
        if equity.empty:
            return {}

        total_return = float(equity.iloc[-1] / equity.iloc[0] - 1.0) if len(equity) > 1 else 0.0
        n_periods = max(len(returns), 1)
        annual_return = float((1.0 + total_return) ** (252.0 / n_periods) - 1.0) if len(equity) > 1 else 0.0
        daily_vol = float(returns.std(ddof=1)) if not returns.empty else 0.0
        annual_vol = float(daily_vol * np.sqrt(252.0))
        rf_daily = self.config.risk_free_rate / 252.0

        excess_returns = returns - rf_daily
        # 正確 Sharpe：分子分母都使用 excess_returns
        excess_std = excess_returns.std(ddof=1)
        sharpe = float(excess_returns.mean() / excess_std * np.sqrt(252.0)) if excess_std > 0 else 0.0

        downside = returns[returns < rf_daily]
        downside_std = float(downside.std(ddof=1) * np.sqrt(252.0)) if len(downside) > 0 else 0.0
        sortino = float((annual_return - self.config.risk_free_rate) / downside_std) if downside_std > 0 else 0.0

        running_max = equity.cummax()
        drawdown = (equity / running_max) - 1.0
        max_drawdown = float(drawdown.min()) if not drawdown.empty else 0.0
        calmar = float(annual_return / abs(max_drawdown)) if max_drawdown < 0 else 0.0

        non_zero_returns = returns[returns != 0]
        win_rate = float((non_zero_returns > 0).mean()) if not non_zero_returns.empty else 0.0

        active_sharpe = 0.0
        benchmark_total_return = 0.0
        benchmark_annual_return = 0.0
        if benchmark_returns is not None and not benchmark_returns.empty:
            aligned = returns.align(benchmark_returns, join="inner")
            active = aligned[0] - aligned[1]
            if active.std(ddof=1) > 0:
                active_sharpe = float(active.mean() / active.std(ddof=1) * np.sqrt(252.0))
            benchmark_total_return = float((1.0 + aligned[1]).prod() - 1.0)
            benchmark_annual_return = float((1.0 + benchmark_total_return) ** (252.0 / max(len(aligned[1]), 1)) - 1.0)

        avg_gross_exposure = float(weights.sum(axis=1).mean()) if not weights.empty else 0.0
        cash_weight = float(np.clip(1.0 - avg_gross_exposure, 0.0, 1.0))
        turnover_multiple = float(trades["trade_value"].sum() / self.config.initial_capital) if not trades.empty else 0.0

        return {
            "total_return": total_return,
            "annual_return": annual_return,
            "sharpe": sharpe,
            "sortino": sortino,
            "max_drawdown": max_drawdown,
            "calmar": calmar,
            "win_rate": win_rate,
            "num_trades": int(len(trades)) if not trades.empty else 0,
            "annual_volatility": annual_vol,
            "sharpe_vs_benchmark": active_sharpe,
            "benchmark_total_return": benchmark_total_return,
            "benchmark_annual_return": benchmark_annual_return,
            "avg_gross_exposure": avg_gross_exposure,
            "avg_cash_weight": cash_weight,
            "turnover_multiple": turnover_multiple,
        }

    def _coerce_datetime_index(self, frame: pd.DataFrame) -> pd.DataFrame:
        local = frame.copy()
        if "date" in local.columns:
            local["date"] = pd.to_datetime(local["date"])
            local = local.set_index("date")
        else:
            local.index = pd.to_datetime(local.index)
        local.index = pd.DatetimeIndex(local.index).tz_localize(None)
        return local.sort_index()
