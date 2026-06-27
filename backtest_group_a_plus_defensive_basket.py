#!/usr/bin/env python3
"""Evaluate A21 defensive baskets with dividends, costs, and delay stress."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from backtest_group_a_plus_policy_signal import (
    DEFAULT_DECISION_POINTER,
    DEFAULT_GOLDEN_SIGNAL,
    TICKERS,
    _load,
    _load_policy_signal,
    _normalize,
    _resolve,
    _weights_from_group_a,
    _weights_from_group_a_plus,
)
from backtest_group_a_plus_switch_policy import DB_PATH, _load_chip_features, _load_prices, _metrics, _switch_returns
from backtest_group_a_plus_warmup_consistency import _trim_window, _warmup_start
from group_a_plus.runners.a207 import A207_RULE


PROJECT_ROOT = Path(__file__).resolve().parent
BOND_ETFS = {"00679B.TWO"}


DEFENSIVE_BASKETS = {
    "current_a207": None,
    "cash30": {"0050.TW": 0.60, "00631L.TW": 0.10, "cash": 0.30},
    "cash40": {"0050.TW": 0.50, "00631L.TW": 0.10, "cash": 0.40},
    "bond20": {"0050.TW": 0.50, "00631L.TW": 0.10, "00679B.TWO": 0.20, "cash": 0.20},
    "bond40": {"0050.TW": 0.40, "00679B.TWO": 0.40, "cash": 0.20},
    "bond30_cash30": {"0050.TW": 0.40, "00679B.TWO": 0.30, "cash": 0.30},
    "inverse10_bond20": {
        "0050.TW": 0.40,
        "00631L.TW": 0.10,
        "00632R.TW": 0.10,
        "00679B.TWO": 0.20,
        "cash": 0.20,
    },
}


def _load_total_return_prices(db_path: Path, index: pd.DatetimeIndex) -> tuple[pd.DataFrame, dict[str, Any]]:
    placeholders = ", ".join(["?"] * len(TICKERS))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            f"""
            SELECT dt, ticker, close, coalesce(dividends, 0.0) AS dividends
            FROM ohlcv
            WHERE ticker IN ({placeholders}) AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [*TICKERS, str(index[0].date()), str(index[-1].date())],
        ).fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"])
    close = rows.pivot(index="dt", columns="ticker", values="close").reindex(index)
    dividends = rows.pivot(index="dt", columns="ticker", values="dividends").reindex(index).fillna(0.0)
    if close[list(TICKERS)].isna().any().any():
        raise RuntimeError("Missing close prices while constructing total-return series")
    total_return = pd.DataFrame(index=index)
    for ticker in TICKERS:
        growth = (close[ticker] + dividends[ticker]).div(close[ticker].shift(1))
        growth.iloc[0] = 1.0
        total_return[ticker] = float(close[ticker].iloc[0]) * growth.cumprod()
    coverage = {
        "method": "(close_t + dividend_t) / close_t_minus_1",
        "dividend_event_count": {ticker: int((dividends[ticker] != 0.0).sum()) for ticker in TICKERS},
        "dividend_sum": {ticker: float(dividends[ticker].sum()) for ticker in TICKERS},
    }
    return total_return, coverage


def _delayed_regime(regime: pd.Series, delay_days: int) -> pd.Series:
    if delay_days <= 0:
        return regime.copy()
    return regime.shift(delay_days).fillna("golden1").astype(str)


def _asymmetric_delayed_regime(regime: pd.Series, enter_delay: int, exit_delay: int) -> pd.Series:
    targets = regime.astype(str).tolist()
    state = targets[0]
    pending: tuple[int, str] | None = None
    output: list[str] = []
    for position, target in enumerate(targets):
        if pending is not None and position >= pending[0]:
            state = pending[1]
            pending = None
        if target != state and pending is None:
            delay = enter_delay if target == "group_a_plus_defensive" else exit_delay
            if delay <= 0:
                state = target
            else:
                pending = (position + delay, target)
        output.append(state)
    return pd.Series(output, index=regime.index, dtype=object)


def _recovery_ramp_regime(
    execution_regime: pd.Series,
    features: pd.DataFrame,
    trend_vol_threshold: float | None = None,
    trend_ma_gap_persist_days: int | None = None,
    vol_enter_threshold: float | None = None,
) -> pd.Series:
    """
    Trend-confirmed recovery ramp with optional volatility early-entry guard.

    Recovery from defensive requires BOTH:
      (a) ma_gap >= 0 AND exit_momentum > 0  [existing]
      (b) trend confirmation (if configured):
          - vol_threshold: realized_vol_0050_20d < threshold
          - ma_gap_persist_days: ma_gap >= 0 for N consecutive days

    Vol early-entry (if vol_enter_threshold set):
      When realized_vol_0050_20d > threshold, force regime to defensive
      regardless of base regime signal.

    Parameters
    ----------
    trend_vol_threshold : float | None
        Recovery requires realized_vol_0050_20d < this value.
    trend_ma_gap_persist_days : int | None
        Recovery requires ma_gap >= 0 for N consecutive days.
    vol_enter_threshold : float | None
        If set, force defensive when realized_vol_0050_20d > this value.
    """
    output: list[str] = []
    in_defense = False
    recovery = False
    ma_gap_persist_count = 0  # consecutive days ma_gap >= 0

    for dt, state in execution_regime.items():
        base_state = str(state)

        # Vol-based early defensive entry
        if vol_enter_threshold is not None:
            vol_val = float(features.loc[dt, "realized_vol_0050_20d"])
            if vol_val > vol_enter_threshold:
                in_defense = False
                recovery = False
                ma_gap_persist_count = 0
                output.append("group_a_plus_defensive")
                continue

        if base_state != "group_a_plus_defensive":
            in_defense = False
            recovery = False
            ma_gap_persist_count = 0
            output.append("golden1")
            continue
        if not in_defense:
            in_defense = True
            recovery = False
            ma_gap_persist_count = 0
        row = features.loc[dt]

        if not recovery:
            base_ok = row["ma_gap"] >= 0.0 and row["exit_momentum"] > 0.0

            # Trend vol filter
            vol_ok = True
            if trend_vol_threshold is not None and base_ok:
                vol_val = float(row.get("realized_vol_0050_20d", 999.0))
                vol_ok = vol_val < trend_vol_threshold

            # Trend persistence filter
            persist_ok = True
            if trend_ma_gap_persist_days is not None and trend_ma_gap_persist_days > 0 and base_ok:
                if row["ma_gap"] >= 0.0:
                    ma_gap_persist_count += 1
                else:
                    ma_gap_persist_count = 0
                persist_ok = ma_gap_persist_count >= trend_ma_gap_persist_days

            if base_ok and vol_ok and persist_ok:
                recovery = True

        output.append("group_a_plus_recovery" if recovery else "group_a_plus_defensive")
    return pd.Series(output, index=execution_regime.index, dtype=object)


def _trade_cost(
    current_values: dict[str, float],
    target_values: dict[str, float],
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> tuple[float, float]:
    cost = 0.0
    turnover = 0.0
    for ticker in TICKERS:
        trade = float(target_values.get(ticker, 0.0)) - float(current_values.get(ticker, 0.0))
        turnover += abs(trade)
        if trade > 0.0:
            cost += trade * (commission_rate + slippage_rate)
        elif trade < 0.0:
            tax = 0.0 if ticker in BOND_ETFS else equity_etf_sell_tax
            cost += abs(trade) * (commission_rate + slippage_rate + tax)
    return cost, turnover


def _simulate_costed_curve(
    prices: pd.DataFrame,
    regimes: pd.Series,
    weights_by_regime: dict[str, dict[str, float]],
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> tuple[pd.Series, dict[str, float]]:
    shares = {ticker: 0.0 for ticker in TICKERS}
    cash = float(initial_value)
    current_regime: str | None = None
    values: list[float] = []
    total_cost = 0.0
    total_turnover = 0.0
    rebalance_count = 0

    for dt, price_row in prices.iterrows():
        gross_value = cash + sum(shares[ticker] * float(price_row[ticker]) for ticker in TICKERS)
        next_regime = str(regimes.loc[dt])
        if next_regime != current_regime:
            weights = _normalize(weights_by_regime[next_regime])
            current_values = {ticker: shares[ticker] * float(price_row[ticker]) for ticker in TICKERS}
            net_value = gross_value
            cost = 0.0
            turnover = 0.0
            for _iteration in range(3):
                target_values = {ticker: net_value * weights.get(ticker, 0.0) for ticker in TICKERS}
                cost, turnover = _trade_cost(
                    current_values,
                    target_values,
                    commission_rate,
                    slippage_rate,
                    equity_etf_sell_tax,
                )
                net_value = max(gross_value - cost, 0.0)
            shares = {
                ticker: net_value * weights.get(ticker, 0.0) / max(float(price_row[ticker]), 1e-12)
                for ticker in TICKERS
            }
            cash = net_value * weights.get("cash", 0.0)
            gross_value = net_value
            total_cost += cost
            total_turnover += turnover
            rebalance_count += 1
            current_regime = next_regime
        values.append(gross_value)
    return pd.Series(values, index=prices.index, dtype=float), {
        "transaction_cost": float(total_cost),
        "turnover_value": float(total_turnover),
        "rebalance_count": int(rebalance_count),
    }


def _dominates(candidate: dict[str, Any], reference: dict[str, Any], tolerance: float = 1e-12) -> bool:
    return bool(
        candidate["final_value"] + tolerance >= reference["final_value"]
        and candidate["sharpe_ratio"] + tolerance >= reference["sharpe_ratio"]
        and candidate["max_drawdown"] + tolerance >= reference["max_drawdown"]
    )


def _stress_episodes(frame: pd.DataFrame, min_trading_days: int = 5) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    price_stress = (frame["ma_gap"] <= A207_RULE.enter_ma_gap) | (frame["drawdown"] <= A207_RULE.enter_drawdown)
    active = False
    start: pd.Timestamp | None = None
    episodes: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    for dt, row in frame.iterrows():
        if not active and bool(price_stress.loc[dt]):
            active = True
            start = dt
        elif active and row["ma_gap"] >= A207_RULE.exit_ma_gap and row["exit_momentum"] > 0.0:
            segment = frame.loc[start:dt]
            if len(segment) >= min_trading_days and start is not None:
                episodes.append((start, dt))
            active = False
            start = None
    if active and start is not None:
        segment = frame.loc[start:]
        if len(segment) >= min_trading_days:
            episodes.append((start, frame.index[-1]))
    return episodes


def _episode_curve(
    prices: pd.DataFrame,
    weights: dict[str, float],
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> tuple[pd.Series, float]:
    weights = _normalize(weights)
    first = prices.iloc[0]
    current_values = {ticker: 0.0 for ticker in TICKERS}
    net_value = initial_value
    entry_cost = 0.0
    for _iteration in range(3):
        targets = {ticker: net_value * weights.get(ticker, 0.0) for ticker in TICKERS}
        entry_cost, _turnover = _trade_cost(
            current_values, targets, commission_rate, slippage_rate, equity_etf_sell_tax
        )
        net_value = max(initial_value - entry_cost, 0.0)
    shares = {
        ticker: net_value * weights.get(ticker, 0.0) / max(float(first[ticker]), 1e-12)
        for ticker in TICKERS
    }
    cash = net_value * weights.get("cash", 0.0)
    curve = pd.Series(
        [cash + sum(shares[ticker] * float(row[ticker]) for ticker in TICKERS) for _dt, row in prices.iterrows()],
        index=prices.index,
        dtype=float,
    )
    end_values = {ticker: shares[ticker] * float(prices.iloc[-1][ticker]) for ticker in TICKERS}
    exit_cost, _turnover = _trade_cost(
        end_values,
        {ticker: 0.0 for ticker in TICKERS},
        commission_rate,
        slippage_rate,
        equity_etf_sell_tax,
    )
    curve.iloc[-1] = max(curve.iloc[-1] - exit_cost, 0.0)
    return curve, float(entry_cost + exit_cost)


def _episode_selection(
    frame: pd.DataFrame,
    prices: pd.DataFrame,
    baskets: dict[str, dict[str, float]],
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> tuple[list[dict[str, Any]], str | None, list[dict[str, str]]]:
    episodes = _stress_episodes(frame)
    details: dict[str, list[dict[str, float]]] = {name: [] for name in baskets}
    episode_rows: list[dict[str, str]] = []
    for episode_id, (start, end) in enumerate(episodes, 1):
        segment = prices.loc[start:end]
        metrics_by_basket: dict[str, dict[str, Any]] = {}
        for basket_name, weights in baskets.items():
            curve, cost = _episode_curve(
                segment,
                weights,
                initial_value,
                commission_rate,
                slippage_rate,
                equity_etf_sell_tax,
            )
            metrics_by_basket[basket_name] = {**_metrics(curve, initial_value), "transaction_cost": cost}
        baseline = metrics_by_basket["current_a207"]
        for basket_name, metrics in metrics_by_basket.items():
            details[basket_name].append(
                {
                    "return_delta": metrics["total_return"] - baseline["total_return"],
                    "mdd_delta": metrics["max_drawdown"] - baseline["max_drawdown"],
                    "joint_win": float(_dominates(metrics, baseline)),
                }
            )
        episode_rows.append(
            {"episode": str(episode_id), "start": str(start.date()), "end": str(end.date()), "trading_days": str(len(segment))}
        )

    summaries: list[dict[str, Any]] = []
    for basket_name, rows in details.items():
        if basket_name == "current_a207" or not rows:
            continue
        return_deltas = pd.Series([row["return_delta"] for row in rows], dtype=float)
        mdd_deltas = pd.Series([row["mdd_delta"] for row in rows], dtype=float)
        summaries.append(
            {
                "basket": basket_name,
                "episode_count": len(rows),
                "joint_win_count": int(sum(row["joint_win"] for row in rows)),
                "return_win_count": int((return_deltas >= -1e-12).sum()),
                "median_return_delta": float(return_deltas.median()),
                "mean_return_delta": float(return_deltas.mean()),
                "worst_return_delta": float(return_deltas.min()),
                "median_mdd_delta": float(mdd_deltas.median()),
                "worst_mdd_delta": float(mdd_deltas.min()),
            }
        )
    ranked = sorted(
        summaries,
        key=lambda row: (
            row["worst_return_delta"],
            row["median_return_delta"],
            row["joint_win_count"],
            row["median_mdd_delta"],
        ),
        reverse=True,
    )
    return summaries, (ranked[0]["basket"] if ranked else None), episode_rows


def _latency_matrix(
    prices: pd.DataFrame,
    regime: pd.Series,
    golden_weights: dict[str, float],
    baseline_weights: dict[str, float],
    candidate_weights: dict[str, float],
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
    features: pd.DataFrame | None = None,
    recovery_weights: dict[str, float] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for enter_delay in range(4):
        for exit_delay in range(4):
            delayed = _asymmetric_delayed_regime(regime, enter_delay, exit_delay)
            metrics: dict[str, dict[str, Any]] = {}
            for name, defensive_weights in (
                ("baseline", baseline_weights),
                ("candidate", candidate_weights),
            ):
                execution_regime = delayed
                weights_by_regime = {
                    "golden1": golden_weights,
                    "group_a_plus_defensive": defensive_weights,
                }
                if name == "candidate" and features is not None and recovery_weights is not None:
                    execution_regime = _recovery_ramp_regime(delayed, features)
                    weights_by_regime["group_a_plus_recovery"] = recovery_weights
                curve, _execution = _simulate_costed_curve(
                    prices,
                    execution_regime,
                    weights_by_regime,
                    initial_value,
                    commission_rate,
                    slippage_rate,
                    equity_etf_sell_tax,
                )
                metrics[name] = _metrics(curve, initial_value)
            candidate, baseline = metrics["candidate"], metrics["baseline"]
            rows.append(
                {
                    "enter_delay": enter_delay,
                    "exit_delay": exit_delay,
                    "delta_final": candidate["final_value"] - baseline["final_value"],
                    "delta_sharpe": candidate["sharpe_ratio"] - baseline["sharpe_ratio"],
                    "delta_mdd": candidate["max_drawdown"] - baseline["max_drawdown"],
                    "joint_pass": _dominates(candidate, baseline),
                }
            )
    final_deltas = pd.Series([row["delta_final"] for row in rows], dtype=float)
    summary = {
        "scenario_count": len(rows),
        "joint_pass_count": sum(1 for row in rows if row["joint_pass"]),
        "final_pass_count": sum(1 for row in rows if row["delta_final"] >= -1e-12),
        "sharpe_pass_count": sum(1 for row in rows if row["delta_sharpe"] >= -1e-12),
        "mdd_pass_count": sum(1 for row in rows if row["delta_mdd"] >= -1e-12),
        "median_delta_final": float(final_deltas.median()),
        "worst_delta_final": float(final_deltas.min()),
    }
    return rows, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision-pointer", default=str(DEFAULT_DECISION_POINTER))
    parser.add_argument("--golden-signal", default=str(DEFAULT_GOLDEN_SIGNAL))
    parser.add_argument("--start", default="2020-01-02")
    parser.add_argument("--end", default="2024-12-31")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--warmup-days", type=int, default=180)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--latency-basket", choices=tuple(DEFENSIVE_BASKETS), default=None)
    parser.add_argument("--recovery-ramp", action="store_true")
    parser.add_argument("--output-prefix", default="results/group_a_plus_defensive_basket_20260620")
    args = parser.parse_args()

    policy_signal, policy_signal_path = _load_policy_signal(_resolve(args.decision_pointer))
    golden_signal_path = _resolve(args.golden_signal)
    golden_signal = _load(golden_signal_path)
    current_defensive = _weights_from_group_a_plus(policy_signal)
    golden_weights = _weights_from_group_a(golden_signal)
    baskets = {
        name: _normalize(current_defensive if weights is None else weights)
        for name, weights in DEFENSIVE_BASKETS.items()
    }

    load_start = _warmup_start(args.start, args.warmup_days)
    full_close = _load_prices(_resolve(args.db), list(TICKERS), load_start, args.end)
    full_chip = _load_chip_features(_resolve(args.db), full_close.index, load_start, args.end)
    full_events, full_frame = _switch_returns(full_close, full_chip, A207_RULE)
    close_prices, frame, events = _trim_window(full_close, full_frame, full_events, args.start, args.end)
    total_return_prices, dividend_coverage = _load_total_return_prices(_resolve(args.db), close_prices.index)

    scenarios = {
        "base": {"delay": 0, "cost_multiplier": 1.0},
        "cost2x": {"delay": 0, "cost_multiplier": 2.0},
        "delay1": {"delay": 1, "cost_multiplier": 1.0},
        "delay3": {"delay": 3, "cost_multiplier": 1.0},
    }
    rows: list[dict[str, Any]] = []
    frames: dict[str, pd.DataFrame] = {}
    for basket_name, defensive_weights in baskets.items():
        weights_by_regime = {"golden1": golden_weights, "group_a_plus_defensive": defensive_weights}
        for scenario_name, scenario in scenarios.items():
            regimes = _delayed_regime(frame["regime"], int(scenario["delay"]))
            execution_regimes = regimes
            weights_by_execution_regime = dict(weights_by_regime)
            if args.recovery_ramp and basket_name != "current_a207":
                execution_regimes = _recovery_ramp_regime(regimes, frame)
                weights_by_execution_regime["group_a_plus_recovery"] = current_defensive
            multiplier = float(scenario["cost_multiplier"])
            curve, execution = _simulate_costed_curve(
                total_return_prices,
                execution_regimes,
                weights_by_execution_regime,
                args.initial_value,
                args.commission_rate * multiplier,
                args.slippage_rate * multiplier,
                args.equity_etf_sell_tax,
            )
            metrics = _metrics(curve, args.initial_value)
            variant = f"a21_{basket_name}_{scenario_name}"
            rows.append(
                {
                    "variant": variant,
                    "basket": basket_name,
                    "scenario": scenario_name,
                    **metrics,
                    **execution,
                    "delay_days": int(scenario["delay"]),
                    "cost_multiplier": multiplier,
                    "recovery_ramp": bool(args.recovery_ramp and basket_name != "current_a207"),
                    "formal_eligible": False,
                    "formal_ineligible_reason": "requires matched dividend-and-cost baseline; use candidate_summary",
                    "override_days": int((regimes != frame["regime"]).sum()) if basket_name == "current_a207" else int((frame["regime"] == "group_a_plus_defensive").sum()),
                    "defense_days": int((execution_regimes != "golden1").sum()),
                }
            )
            out_frame = frame.copy()
            out_frame["execution_regime"] = execution_regimes
            out_frame["portfolio_value"] = curve
            frames[variant] = out_frame

    row_map = {(row["basket"], row["scenario"]): row for row in rows}
    baseline_by_scenario = {
        scenario: row_map[("current_a207", scenario)] for scenario in scenarios
    }
    candidate_summary: list[dict[str, Any]] = []
    for basket_name in baskets:
        if basket_name == "current_a207":
            continue
        base = row_map[(basket_name, "base")]
        base_ref = baseline_by_scenario["base"]
        stress_passes = 0
        for scenario_name in scenarios:
            candidate = row_map[(basket_name, scenario_name)]
            reference = baseline_by_scenario[scenario_name]
            if _dominates(candidate, reference):
                stress_passes += 1
        formal = _dominates(base, base_ref) and stress_passes == len(scenarios)
        candidate_summary.append(
            {
                "basket": basket_name,
                "base_final_value": base["final_value"],
                "base_sharpe_ratio": base["sharpe_ratio"],
                "base_max_drawdown": base["max_drawdown"],
                "delta_final": base["final_value"] - base_ref["final_value"],
                "delta_sharpe": base["sharpe_ratio"] - base_ref["sharpe_ratio"],
                "delta_mdd": base["max_drawdown"] - base_ref["max_drawdown"],
                "stress_pass_count": stress_passes,
                "stress_scenario_count": len(scenarios),
                "formal_upgrade_pass": formal,
            }
        )
    ranked = sorted(
        candidate_summary,
        key=lambda row: (
            row["formal_upgrade_pass"],
            row["stress_pass_count"],
            row["base_sharpe_ratio"],
            row["base_max_drawdown"],
            row["base_final_value"],
        ),
        reverse=True,
    )
    best = ranked[0]
    best_variant = f"a21_{best['basket']}_base"
    episode_summary, episode_selected_basket, stress_episodes = _episode_selection(
        frame,
        total_return_prices,
        baskets,
        args.initial_value,
        args.commission_rate,
        args.slippage_rate,
        args.equity_etf_sell_tax,
    )
    latency_basket = args.latency_basket or episode_selected_basket
    latency_rows: list[dict[str, Any]] = []
    latency_summary: dict[str, Any] = {}
    if latency_basket is not None:
        latency_rows, latency_summary = _latency_matrix(
            total_return_prices,
            frame["regime"],
            golden_weights,
            baskets["current_a207"],
            baskets[latency_basket],
            args.initial_value,
            args.commission_rate,
            args.slippage_rate,
            args.equity_etf_sell_tax,
            frame if args.recovery_ramp else None,
            baskets["current_a207"] if args.recovery_ramp else None,
        )
    report = {
        "experiment": "group_a_plus_a21_defensive_basket_robustness",
        "method_note": (
            "A20.7 warmup signals are fixed. ETF returns add local OHLCV dividends. "
            "Execution charges commission and slippage on buys/sells, 0.1% sell tax on non-bond ETFs, "
            "and no sell tax on 00679B during the tested statutory exemption period."
        ),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "actual_window": {"start": str(close_prices.index[0].date()), "end": str(close_prices.index[-1].date()), "rows": len(close_prices)},
        "warmup": {"days": args.warmup_days, "start": load_start},
        "cost_assumptions": {
            "commission_rate": args.commission_rate,
            "slippage_rate": args.slippage_rate,
            "equity_etf_sell_tax": args.equity_etf_sell_tax,
            "bond_etf_sell_tax": 0.0,
        },
        "recovery_ramp": {
            "enabled": args.recovery_ramp,
            "trigger": "while defensive: ma_gap >= 0 and exit_momentum > 0",
            "target": "current_a207 defensive weights until formal exit",
            "one_shot_per_defense_episode": True,
        },
        "dividend_coverage": dividend_coverage,
        "events": events,
        "inputs": {
            "policy_signal": str(policy_signal_path.relative_to(PROJECT_ROOT)),
            "golden_signal": str(golden_signal_path.relative_to(PROJECT_ROOT)),
        },
        "weights": {"golden1": _normalize(golden_weights), "defensive_baskets": baskets},
        "summary": {"a207": baseline_by_scenario["base"]},
        "rows": rows,
        "candidate_summary": candidate_summary,
        "stress_episodes": stress_episodes,
        "episode_selection_summary": episode_summary,
        "episode_selected_basket": episode_selected_basket,
        "latency_basket": latency_basket,
        "latency_matrix": latency_rows,
        "latency_summary": latency_summary,
        "episode_selected_latency_matrix": latency_rows,
        "episode_selected_latency_summary": latency_summary,
        "formal_upgrade_pass_count": sum(1 for row in candidate_summary if row["formal_upgrade_pass"]),
        "best": best,
    }

    prefix = Path(args.output_prefix)
    if not prefix.is_absolute():
        prefix = (PROJECT_ROOT / prefix).resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    prefix.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(rows).to_csv(prefix.with_suffix(".csv"), index=False, encoding="utf-8-sig")
    frames[best_variant].to_csv(prefix.with_name(prefix.name + "_best_frame.csv"), encoding="utf-8-sig")
    print(f"JSON: {prefix.with_suffix('.json')}")
    print(f"Best: {best['basket']}")


if __name__ == "__main__":
    main()
