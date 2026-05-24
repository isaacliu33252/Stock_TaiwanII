"""
Group A bridge for FinRL-X backtesting.

Keep PortfolioEnv replay as the authoritative simulator, but expose a stable
helper that also runs the FinRL-X weight-centric BacktestEngine on top of the
same replay weights for reporting and comparison.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from ..strategies import GroupAFinRLXConfig, GroupAFinRLXStrategy, StrategyResult
from .backtest_engine import BacktestConfig, BacktestEngine, BacktestResult


@dataclass
class GroupABridgeConfig:
    payload_path: str
    name: str = "GroupAFinRLX"
    target_date: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    model_path: Optional[str] = None
    download_end: Optional[str] = None
    initial_capital: Optional[float] = None
    benchmark_tickers: list[str] = field(default_factory=lambda: ["0050.TW"])
    price_dir: Optional[str] = None
    risk_free_rate: float = 0.02
    deterministic: bool = True


@dataclass
class GroupABridgeResult:
    strategy_result: StrategyResult
    backtest_result: BacktestResult
    summary: Dict[str, Any]


def _window_value(metadata: dict[str, Any], key: str) -> Optional[str]:
    window = metadata.get("window") or {}
    value = window.get(key)
    return str(value) if value else None


def _coerce_equity_curve(strategy_result: StrategyResult) -> pd.Series:
    metadata = strategy_result.metadata or {}
    curve = metadata.get("equity_curve") or []
    weights = metadata.get("weights_full")
    if not curve:
        return pd.Series(dtype=float, name="env_portfolio_value")

    values = np.asarray(curve, dtype=float)
    if isinstance(weights, pd.DataFrame) and not weights.empty:
        usable = min(len(values), len(weights.index))
        return pd.Series(
            values[:usable],
            index=pd.DatetimeIndex(weights.index[:usable]),
            name="env_portfolio_value",
        ).sort_index()

    index = pd.RangeIndex(start=0, stop=len(values), step=1)
    return pd.Series(values, index=index, name="env_portfolio_value")


def _series_metrics(equity: pd.Series, risk_free_rate: float) -> Dict[str, float]:
    clean = equity.astype(float).dropna()
    if clean.empty:
        return {
            "total_return": 0.0,
            "annual_return": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
        }

    returns = clean.pct_change().dropna()
    total_return = float(clean.iloc[-1] / clean.iloc[0] - 1.0) if len(clean) > 1 else 0.0
    annual_return = float((1.0 + total_return) ** (252.0 / max(len(returns), 1)) - 1.0) if len(clean) > 1 else 0.0

    rf_daily = float(risk_free_rate) / 252.0
    excess = returns - rf_daily
    excess_std = float(excess.std(ddof=1)) if len(excess) > 1 else 0.0
    sharpe = float(excess.mean() / excess_std * np.sqrt(252.0)) if excess_std > 0 else 0.0

    running_max = clean.cummax()
    drawdown = (clean / running_max) - 1.0
    max_drawdown = float(drawdown.min()) if not drawdown.empty else 0.0

    return {
        "total_return": total_return,
        "annual_return": annual_return,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
    }


def build_group_a_strategy_result(
    config: GroupABridgeConfig,
    data: Optional[Dict[str, pd.DataFrame]] = None,
) -> StrategyResult:
    strategy = GroupAFinRLXStrategy(
        GroupAFinRLXConfig(
            name=config.name,
            result_json=config.payload_path,
            model_path=config.model_path,
            download_end=config.download_end,
            backtest_start=config.start_date,
            initial_cash=config.initial_capital,
            deterministic=config.deterministic,
        )
    )
    return strategy.generate_weights(data or {}, target_date=config.target_date or config.end_date)


def run_group_a_finrlx_backtest(
    config: GroupABridgeConfig,
    data: Optional[Dict[str, pd.DataFrame]] = None,
) -> GroupABridgeResult:
    strategy_result = build_group_a_strategy_result(config, data=data)
    metadata = strategy_result.metadata or {}

    start_date = config.start_date or _window_value(metadata, "backtest_start")
    end_date = config.end_date or config.target_date or _window_value(metadata, "backtest_end")
    if not start_date or not end_date:
        raise ValueError("Unable to resolve Group A backtest window")

    initial_capital = float(config.initial_capital or metadata.get("initial_cash") or 1_000_000.0)
    engine = BacktestEngine(
        BacktestConfig(
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            benchmark_tickers=config.benchmark_tickers,
            price_dir=config.price_dir,
            risk_free_rate=config.risk_free_rate,
        )
    )
    backtest_result = engine.run(strategy_result)

    env_equity = _coerce_equity_curve(strategy_result)
    env_metrics = _series_metrics(env_equity, config.risk_free_rate)
    finrlx_equity = backtest_result.portfolio_values.astype(float)
    env_final = float(env_equity.iloc[-1]) if not env_equity.empty else float("nan")
    finrlx_final = float(finrlx_equity.iloc[-1]) if not finrlx_equity.empty else float("nan")
    dca_total_contributions = float(metadata.get("dca_total_contributions", 0.0) or 0.0)
    env_profit_net_of_contributions = env_final - initial_capital - dca_total_contributions
    finrlx_profit = finrlx_final - initial_capital

    summary = {
        "strategy_name": strategy_result.strategy_name,
        "payload_path": metadata.get("payload_path"),
        "model_path": metadata.get("model_path"),
        "window": {
            "start_date": start_date,
            "end_date": end_date,
        },
        "env_replay": {
            "initial_capital": initial_capital,
            "dca_total_contributions": dca_total_contributions,
            "final_value": env_final,
            "profit_net_of_contributions": env_profit_net_of_contributions,
            "metrics": env_metrics,
            "trade_count": int(metadata.get("trade_count", 0)),
            "decision_count": int(len(metadata.get("decision_history") or [])),
        },
        "finrlx_backtest": {
            "initial_capital": initial_capital,
            "final_value": finrlx_final,
            "profit": finrlx_profit,
            "metrics": {key: float(value) if isinstance(value, (int, float, np.floating)) else value for key, value in backtest_result.metrics.items()},
            "trade_count": int(backtest_result.metrics.get("num_trades", 0)),
        },
        "comparison": {
            "final_value_diff": finrlx_final - env_final,
            "final_value_diff_pct_of_initial": (finrlx_final - env_final) / initial_capital if initial_capital else 0.0,
            "profit_diff_vs_env_net_of_contributions": finrlx_profit - env_profit_net_of_contributions,
            "note": (
                "PortfolioEnv replay remains canonical. FinRL-X backtest is a "
                "weight-centric comparison layer and can drift because Group A "
                "uses stateful logic, DCA external cash flows, and next-open "
                "execution semantics."
            ),
        },
    }

    return GroupABridgeResult(
        strategy_result=strategy_result,
        backtest_result=backtest_result,
        summary=summary,
    )
