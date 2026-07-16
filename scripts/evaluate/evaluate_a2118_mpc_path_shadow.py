#!/usr/bin/env python3
"""Shadow-evaluate finite-path MPC de-risk/re-entry on top of active A21.18.

Research-only. This script does not update the active strategy, latest pointer,
live signal, or any execution file.

The intent is to replace the separate "H20 exits, H5 re-enters" chain with a
small finite-horizon path search. Each day, the evaluator scores a handful of
candidate 00631L exposure paths, executes only the first step, and recomputes on
the next day, matching a simple model-predictive-control workflow.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import _load_total_return_prices, _trade_cost
from backtest_group_a_plus_policy_signal import TICKERS, _normalize
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from scripts.evaluate.evaluate_group_a_plus_volatility_gate_shadow import _metric_delta


DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "a2118_mpc_path_shadow_latest.json"
PANEL_2025_2026 = "results/ncf_00631l_panel_latest_20260707.csv"
PANEL_2017_2019 = "results/ncf_00631l_panel_backfill_2017_2019_20260710.csv"

DEFAULT_WINDOWS = [
    ("covid_2020", "2020-01-02", "2020-12-31", PANEL_2025_2026, "tuning_window"),
    ("inflation_2022", "2022-01-03", "2022-12-30", PANEL_2025_2026, "tuning_window"),
    ("live_2024_2026", "2024-01-02", "latest", PANEL_2025_2026, "tuning_window"),
    ("active_2025_2026", "2025-01-02", "latest", PANEL_2025_2026, "tuning_window"),
    ("2017_bull", "2017-01-03", "2017-12-29", PANEL_2017_2019, "out_of_sample"),
    ("2018_correction", "2018-01-02", "2018-12-31", PANEL_2017_2019, "out_of_sample"),
    ("2019_recovery", "2019-01-02", "2019-12-31", PANEL_2017_2019, "out_of_sample"),
]

# Multipliers are relative to the current golden1 00631L weight. This preserves
# the user's 20->10 intuition while also working when live golden1 is not 20%.
DEFAULT_PATHS: dict[str, tuple[float, float, float, float]] = {
    "P0_hold": (1.0, 1.0, 1.0, 1.0),
    "P1_half_fast_reentry": (1.0, 0.5, 1.0, 1.0),
    "P2_half_hold_then_reentry": (1.0, 0.5, 0.5, 1.0),
    "P3_zero_then_step_reentry": (1.0, 0.0, 0.5, 1.0),
    "P4_late_half": (1.0, 1.0, 0.5, 1.0),
    "P5_quarter_trim_fast_reentry": (1.0, 0.75, 1.0, 1.0),
    "P6_half_then_quarter_reentry": (1.0, 0.5, 0.75, 1.0),
}

CONSERVATIVE_PATHS: dict[str, tuple[float, float, float, float]] = {
    "P0_hold": DEFAULT_PATHS["P0_hold"],
    "P1_half_fast_reentry": DEFAULT_PATHS["P1_half_fast_reentry"],
    "P2_half_hold_then_reentry": DEFAULT_PATHS["P2_half_hold_then_reentry"],
    "P5_quarter_trim_fast_reentry": DEFAULT_PATHS["P5_quarter_trim_fast_reentry"],
    "P6_half_then_quarter_reentry": DEFAULT_PATHS["P6_half_then_quarter_reentry"],
}

DISASTER_PATHS: dict[str, tuple[float, float, float, float]] = {
    "P0_hold": DEFAULT_PATHS["P0_hold"],
    "D1_zero_one_day": (1.0, 0.0, 1.0, 1.0),
    "D2_half_one_day": (1.0, 0.5, 1.0, 1.0),
    "D3_half_two_step": (1.0, 0.5, 0.5, 1.0),
}


def _path_set(name: str) -> dict[str, tuple[float, float, float, float]]:
    if name == "default":
        return dict(DEFAULT_PATHS)
    if name == "conservative":
        return dict(CONSERVATIVE_PATHS)
    if name == "disaster":
        return dict(DISASTER_PATHS)
    raise ValueError("--path-set must be 'default', 'conservative', or 'disaster'")


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def _resolve_end_date(db_path: Path, requested_end: str, ticker: str = "0050.TW") -> str:
    if str(requested_end).lower() != "latest":
        return requested_end
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        max_dt = con.execute("SELECT MAX(dt) FROM ohlcv WHERE ticker = ?", [ticker]).fetchone()[0]
    finally:
        con.close()
    if max_dt is None:
        raise ValueError(f"No OHLCV rows found for {ticker}")
    return pd.Timestamp(max_dt).strftime("%Y-%m-%d")


def _load_panel(path: str | Path | None) -> pd.DataFrame | None:
    if not path:
        return None
    panel_path = _resolve(path)
    if not panel_path.exists():
        return None
    panel = pd.read_csv(panel_path, index_col="date", parse_dates=True, encoding="utf-8-sig")
    panel.index = pd.to_datetime(panel.index).normalize()
    return panel


def _clamp_prob(value: Any, default: float = 0.5) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return float(default)
    if pd.isna(out):
        return float(default)
    return min(max(out, 0.0), 1.0)


def _scale_00631l_to_0050(weights: dict[str, float], multiplier: float) -> dict[str, float]:
    out = dict(weights)
    multiplier = min(max(float(multiplier), 0.0), 1.25)
    current = float(out.get("00631L.TW", 0.0) or 0.0)
    target = min(current * multiplier, current * 1.25)
    shift = current - target
    out["00631L.TW"] = target
    out["0050.TW"] = float(out.get("0050.TW", 0.0) or 0.0) + shift
    return _normalize(out)


def _scale_0050_to_cash(weights: dict[str, float], multiplier: float) -> dict[str, float]:
    out = dict(weights)
    multiplier = min(max(float(multiplier), 0.0), 1.25)
    current = float(out.get("0050.TW", 0.0) or 0.0)
    target = min(current * multiplier, current * 1.25)
    shift = current - target
    out["0050.TW"] = target
    out["cash"] = float(out.get("cash", 0.0) or 0.0) + shift
    return _normalize(out)


def _apply_path_action(weights: dict[str, float], multiplier: float, path_action: str) -> dict[str, float]:
    if path_action == "trim_00631l_to_0050":
        return _scale_00631l_to_0050(weights, multiplier)
    if path_action == "trim_0050_to_cash":
        return _scale_0050_to_cash(weights, multiplier)
    raise ValueError("--path-action must be 'trim_00631l_to_0050' or 'trim_0050_to_cash'")


def _path_turnover(path: tuple[float, ...], base_00631l_weight: float) -> float:
    return float(base_00631l_weight) * sum(abs(float(path[i]) - float(path[i - 1])) for i in range(1, len(path)))


def _row_signal_inputs(row: pd.Series | None) -> dict[str, float]:
    if row is None:
        row = pd.Series(dtype=float)
    p1 = _clamp_prob(row.get("prob_up_h1"))
    p5 = _clamp_prob(row.get("prob_up_h5"))
    p20 = _clamp_prob(row.get("prob_up_h20"))
    mdd = _clamp_prob(row.get("prob_fwd_mdd_gt5_h20"), default=max(0.0, 0.5 - p20) * 2.0)
    gain = _clamp_prob(row.get("prob_fwd_gain_gt5_h20"), default=max(p20, p5))
    confidence = _clamp_prob(row.get("confidence"), default=0.5)
    return {
        "p1": float(p1),
        "p5": float(p5),
        "p20": float(p20),
        "mdd": float(mdd),
        "gain": float(gain),
        "confidence": float(confidence),
    }


def _score_path(
    path: tuple[float, float, float, float],
    row: pd.Series | None,
    *,
    base_00631l_weight: float,
    lambda_drawdown: float,
    gamma_turnover: float,
    eta_missed_rebound: float,
    confidence_weight: float,
) -> dict[str, float]:
    inputs = _row_signal_inputs(row)
    p1 = inputs["p1"]
    p5 = inputs["p5"]
    p20 = inputs["p20"]
    mdd = inputs["mdd"]
    gain = inputs["gain"]
    confidence = inputs["confidence"]

    stage_probs = (p1, p5, p20)
    stage_weights = (0.20, 0.35, 0.45)
    future = tuple(float(v) for v in path[1:])

    directional_edge = sum(level * (prob - 0.5) * weight for level, prob, weight in zip(future, stage_probs, stage_weights))
    terminal_value_delta = directional_edge * (0.5 + confidence_weight * confidence)
    drawdown_risk = sum(
        level * max(mdd, max(0.0, 0.5 - prob) * 2.0) * weight
        for level, prob, weight in zip(future, stage_probs, stage_weights)
    )
    turnover = _path_turnover(path, base_00631l_weight)
    rebound_score = max(0.0, gain - 0.5) * 2.0 + max(0.0, p5 - 0.5)
    missed_rebound = sum((1.0 - level) * rebound_score * weight for level, weight in zip(future, stage_weights))
    utility = terminal_value_delta - lambda_drawdown * drawdown_risk - gamma_turnover * turnover - eta_missed_rebound * missed_rebound
    return {
        "utility": float(utility),
        "terminal_value_delta": float(terminal_value_delta),
        "drawdown_risk": float(drawdown_risk),
        "turnover": float(turnover),
        "missed_rebound": float(missed_rebound),
        "p1": float(p1),
        "p5": float(p5),
        "p20": float(p20),
        "mdd": float(mdd),
        "gain": float(gain),
        "confidence": float(confidence),
    }


def _score_path_value(
    path: tuple[float, float, float, float],
    row: pd.Series | None,
    *,
    base_00631l_weight: float,
    lambda_drawdown: float,
    gamma_turnover: float,
    eta_missed_rebound: float,
    confidence_weight: float,
    edge_scale: float,
    rebalance_cost_rate: float,
) -> dict[str, float]:
    inputs = _row_signal_inputs(row)
    p1 = inputs["p1"]
    p5 = inputs["p5"]
    p20 = inputs["p20"]
    mdd = inputs["mdd"]
    gain = inputs["gain"]
    confidence = inputs["confidence"]

    future = tuple(float(v) for v in path[1:])
    stage_probs = (p1, p5, p20)
    stage_widths = (1.0, 4.0, 15.0)
    stage_total = sum(stage_widths)
    confidence_multiplier = 0.5 + confidence_weight * confidence
    expected_relative_edges = tuple(
        edge_scale * (prob - 0.5) * confidence_multiplier for prob in stage_probs
    )

    hold_weight = 1.0
    # Incremental value versus holding the base 00631L weight. Positive means
    # the candidate path is expected to outperform hold after costs.
    terminal_value_delta = base_00631l_weight * sum(
        (level - hold_weight) * edge * width / stage_total
        for level, edge, width in zip(future, expected_relative_edges, stage_widths)
    )
    drawdown_risk = base_00631l_weight * sum(
        level * max(mdd, max(0.0, 0.5 - prob) * 2.0) * width / stage_total
        for level, prob, width in zip(future, stage_probs, stage_widths)
    )
    turnover = _path_turnover(path, base_00631l_weight)
    transaction_cost = turnover * float(rebalance_cost_rate)
    rebound_score = max(0.0, gain - 0.5) * 2.0 + max(0.0, p5 - 0.5)
    missed_rebound = base_00631l_weight * sum(
        (hold_weight - level) * rebound_score * width / stage_total
        for level, width in zip(future, stage_widths)
    )
    utility = terminal_value_delta - lambda_drawdown * drawdown_risk - gamma_turnover * transaction_cost - eta_missed_rebound * missed_rebound
    return {
        "utility": float(utility),
        "terminal_value_delta": float(terminal_value_delta),
        "drawdown_risk": float(drawdown_risk),
        "turnover": float(turnover),
        "transaction_cost": float(transaction_cost),
        "missed_rebound": float(missed_rebound),
        "p1": float(p1),
        "p5": float(p5),
        "p20": float(p20),
        "mdd": float(mdd),
        "gain": float(gain),
        "confidence": float(confidence),
    }


def _simulate_realized_path_value(
    path: tuple[float, float, float, float],
    prices: pd.DataFrame,
    current_dt: pd.Timestamp,
    base_weights: dict[str, float],
    *,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
    path_action: str = "trim_00631l_to_0050",
    offsets: tuple[int, int, int, int] = (0, 1, 5, 20),
) -> dict[str, float] | None:
    if current_dt not in prices.index:
        return None
    start_pos = int(prices.index.get_loc(current_dt))
    if start_pos + offsets[-1] >= len(prices):
        return None

    stage_offsets = offsets[:-1]
    stage_multipliers = path[1:]
    cash = float(base_weights.get("cash", 0.0) or 0.0)
    start_price = prices.iloc[start_pos]
    shares = {
        ticker: float(base_weights.get(ticker, 0.0) or 0.0) / max(float(start_price[ticker]), 1e-12)
        for ticker in TICKERS
    }
    total_cost = 0.0
    total_turnover = 0.0
    last_value = 1.0

    for offset, multiplier in zip(stage_offsets, stage_multipliers):
        price_row = prices.iloc[start_pos + offset]
        gross_value = cash + sum(shares[ticker] * float(price_row[ticker]) for ticker in TICKERS)
        target_weights = _apply_path_action(base_weights, multiplier, path_action)
        current_values = {ticker: shares[ticker] * float(price_row[ticker]) for ticker in TICKERS}
        net_value = gross_value
        cost = 0.0
        turnover = 0.0
        for _iteration in range(3):
            target_values = {ticker: net_value * target_weights.get(ticker, 0.0) for ticker in TICKERS}
            cost, turnover = _trade_cost(
                current_values,
                target_values,
                commission_rate,
                slippage_rate,
                equity_etf_sell_tax,
            )
            net_value = max(gross_value - cost, 0.0)
        shares = {
            ticker: net_value * target_weights.get(ticker, 0.0) / max(float(price_row[ticker]), 1e-12)
            for ticker in TICKERS
        }
        cash = net_value * target_weights.get("cash", 0.0)
        total_cost += cost
        total_turnover += turnover
        last_value = net_value

    final_price = prices.iloc[start_pos + offsets[-1]]
    final_value = cash + sum(shares[ticker] * float(final_price[ticker]) for ticker in TICKERS)
    return {
        "final_value": float(final_value),
        "net_return": float(final_value - 1.0),
        "transaction_cost": float(total_cost),
        "turnover": float(total_turnover),
        "last_rebalance_value": float(last_value),
    }


def _score_path_realized_oracle(
    path: tuple[float, float, float, float],
    row: pd.Series | None,
    *,
    base_00631l_weight: float,
    lambda_drawdown: float,
    gamma_turnover: float,
    eta_missed_rebound: float,
    confidence_weight: float,
    prices: pd.DataFrame | None,
    current_dt: pd.Timestamp | None,
    base_weights: dict[str, float] | None,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
    path_action: str = "trim_00631l_to_0050",
) -> dict[str, float]:
    del base_00631l_weight, lambda_drawdown, gamma_turnover, eta_missed_rebound, confidence_weight
    inputs = _row_signal_inputs(row)
    if prices is None or current_dt is None or base_weights is None:
        simulated = None
    else:
        simulated = _simulate_realized_path_value(
            path,
            prices,
            current_dt,
            base_weights,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
            equity_etf_sell_tax=equity_etf_sell_tax,
            path_action=path_action,
        )
    if simulated is None:
        return {
            "utility": -1e9 if path != DEFAULT_PATHS["P0_hold"] else 0.0,
            "terminal_value_delta": 0.0,
            "drawdown_risk": 0.0,
            "turnover": 0.0,
            "transaction_cost": 0.0,
            "missed_rebound": 0.0,
            **inputs,
        }
    return {
        "utility": float(simulated["final_value"]),
        "terminal_value_delta": float(simulated["net_return"]),
        "drawdown_risk": 0.0,
        "turnover": float(simulated["turnover"]),
        "transaction_cost": float(simulated["transaction_cost"]),
        "missed_rebound": 0.0,
        **inputs,
    }


def _score_path_realized_next_day_oracle(
    path: tuple[float, float, float, float],
    row: pd.Series | None,
    *,
    base_00631l_weight: float,
    lambda_drawdown: float,
    gamma_turnover: float,
    eta_missed_rebound: float,
    confidence_weight: float,
    prices: pd.DataFrame | None,
    current_dt: pd.Timestamp | None,
    base_weights: dict[str, float] | None,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
    path_action: str = "trim_00631l_to_0050",
) -> dict[str, float]:
    del base_00631l_weight, lambda_drawdown, gamma_turnover, eta_missed_rebound, confidence_weight
    inputs = _row_signal_inputs(row)
    if prices is None or current_dt is None or base_weights is None or current_dt not in prices.index:
        final_value = 1.0 if path == DEFAULT_PATHS["P0_hold"] else -1e9
        cost = 0.0
        turnover = 0.0
    else:
        start_pos = int(prices.index.get_loc(current_dt))
        if start_pos + 1 >= len(prices):
            final_value = 1.0 if path == DEFAULT_PATHS["P0_hold"] else -1e9
            cost = 0.0
            turnover = 0.0
        else:
            start_price = prices.iloc[start_pos]
            next_price = prices.iloc[start_pos + 1]
            cash = float(base_weights.get("cash", 0.0) or 0.0)
            shares = {
                ticker: float(base_weights.get(ticker, 0.0) or 0.0) / max(float(start_price[ticker]), 1e-12)
                for ticker in TICKERS
            }
            gross_value = cash + sum(shares[ticker] * float(start_price[ticker]) for ticker in TICKERS)
            target_weights = _apply_path_action(base_weights, path[1], path_action)
            current_values = {ticker: shares[ticker] * float(start_price[ticker]) for ticker in TICKERS}
            net_value = gross_value
            cost = 0.0
            turnover = 0.0
            for _iteration in range(3):
                target_values = {ticker: net_value * target_weights.get(ticker, 0.0) for ticker in TICKERS}
                cost, turnover = _trade_cost(
                    current_values,
                    target_values,
                    commission_rate,
                    slippage_rate,
                    equity_etf_sell_tax,
                )
                net_value = max(gross_value - cost, 0.0)
            shares = {
                ticker: net_value * target_weights.get(ticker, 0.0) / max(float(start_price[ticker]), 1e-12)
                for ticker in TICKERS
            }
            cash = net_value * target_weights.get("cash", 0.0)
            final_value = cash + sum(shares[ticker] * float(next_price[ticker]) for ticker in TICKERS)
    return {
        "utility": float(final_value),
        "terminal_value_delta": float(final_value - 1.0),
        "drawdown_risk": 0.0,
        "turnover": float(turnover),
        "transaction_cost": float(cost),
        "missed_rebound": 0.0,
        **inputs,
    }


def _select_path(
    row: pd.Series | None,
    *,
    base_00631l_weight: float,
    paths: dict[str, tuple[float, float, float, float]],
    lambda_drawdown: float,
    gamma_turnover: float,
    eta_missed_rebound: float,
    confidence_weight: float,
    scoring_mode: str = "proxy",
    edge_scale: float = 0.08,
    rebalance_cost_rate: float = 0.003,
    min_utility_edge: float = 0.0,
    prices: pd.DataFrame | None = None,
    current_dt: pd.Timestamp | None = None,
    base_weights: dict[str, float] | None = None,
    commission_rate: float = 0.001425,
    slippage_rate: float = 0.0005,
    equity_etf_sell_tax: float = 0.001,
    path_action: str = "trim_00631l_to_0050",
) -> tuple[str, tuple[float, float, float, float], dict[str, float], dict[str, dict[str, float]]]:
    if scoring_mode == "proxy":
        scorer = _score_path
        extra_kwargs: dict[str, float] = {}
    elif scoring_mode == "path_value":
        scorer = _score_path_value
        extra_kwargs = {
            "edge_scale": float(edge_scale),
            "rebalance_cost_rate": float(rebalance_cost_rate),
        }
    elif scoring_mode in ("realized_oracle", "realized_next_day_oracle"):
        scorer = _score_path_realized_oracle if scoring_mode == "realized_oracle" else _score_path_realized_next_day_oracle
        extra_kwargs = {
            "prices": prices,
            "current_dt": current_dt,
            "base_weights": base_weights,
            "commission_rate": float(commission_rate),
            "slippage_rate": float(slippage_rate),
            "equity_etf_sell_tax": float(equity_etf_sell_tax),
            "path_action": path_action,
        }
    else:
        raise ValueError(
            "--scoring-mode must be 'proxy', 'path_value', 'realized_oracle', or 'realized_next_day_oracle'"
        )
    scored = {
        name: scorer(
            path,
            row,
            base_00631l_weight=base_00631l_weight,
            lambda_drawdown=lambda_drawdown,
            gamma_turnover=gamma_turnover,
            eta_missed_rebound=eta_missed_rebound,
            confidence_weight=confidence_weight,
            **extra_kwargs,
        )
        for name, path in paths.items()
    }
    best_name = max(scored, key=lambda name: (scored[name]["utility"], -_path_turnover(paths[name], base_00631l_weight)))
    if best_name != "P0_hold" and scored[best_name]["utility"] - scored["P0_hold"]["utility"] < float(min_utility_edge):
        best_name = "P0_hold"
    return best_name, paths[best_name], scored[best_name], scored


def _mpc_gate_allows_path_search(
    row: pd.Series | None,
    *,
    ma_gap: float,
    ma_gap_min: float,
    h20_max: float,
    mdd_min: float,
    confidence_min: float,
    risk_mode: str = "any",
) -> tuple[bool, dict[str, float | bool]]:
    if row is None:
        row = pd.Series(dtype=float)
    p20 = _clamp_prob(row.get("prob_up_h20"))
    mdd = _clamp_prob(row.get("prob_fwd_mdd_gt5_h20"), default=max(0.0, 0.5 - p20) * 2.0)
    confidence = _clamp_prob(row.get("confidence"), default=0.0)
    ma_gap_ok = float(ma_gap) >= float(ma_gap_min)
    h20_ok = p20 <= float(h20_max)
    mdd_ok = mdd >= float(mdd_min)
    if risk_mode == "all":
        risk_ok = h20_ok and mdd_ok
    elif risk_mode == "any":
        risk_ok = h20_ok or mdd_ok
    else:
        raise ValueError("--gate-risk-mode must be 'any' or 'all'")
    confidence_ok = confidence >= float(confidence_min)
    allowed = bool(ma_gap_ok and risk_ok and confidence_ok)
    return allowed, {
        "allowed": allowed,
        "ma_gap": float(ma_gap),
        "ma_gap_min": float(ma_gap_min),
        "ma_gap_ok": ma_gap_ok,
        "prob_up_h20": float(p20),
        "h20_max": float(h20_max),
        "h20_ok": h20_ok,
        "prob_fwd_mdd_gt5_h20": float(mdd),
        "mdd_min": float(mdd_min),
        "mdd_ok": mdd_ok,
        "risk_mode": risk_mode,
        "risk_ok": risk_ok,
        "confidence": float(confidence),
        "confidence_min": float(confidence_min),
        "confidence_ok": confidence_ok,
    }


def _simulate_daily_target_weights(
    prices: pd.DataFrame,
    target_weights: pd.DataFrame,
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> tuple[pd.Series, dict[str, Any]]:
    shares = {ticker: 0.0 for ticker in TICKERS}
    cash = float(initial_value)
    current_key: tuple[float, ...] | None = None
    values: list[float] = []
    total_cost = 0.0
    total_turnover = 0.0
    rebalance_count = 0

    for dt, price_row in prices.iterrows():
        gross_value = cash + sum(shares[ticker] * float(price_row[ticker]) for ticker in TICKERS)
        weights = _normalize(target_weights.loc[dt].to_dict())
        next_key = tuple(round(float(weights.get(key, 0.0)), 8) for key in (*TICKERS, "cash"))
        if next_key != current_key:
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
            current_key = next_key
        values.append(gross_value)

    return pd.Series(values, index=prices.index, dtype=float), {
        "transaction_cost": float(total_cost),
        "turnover_value": float(total_turnover),
        "rebalance_count": int(rebalance_count),
    }


def _rebalance_state(
    *,
    gross_value: float,
    current_values: dict[str, float],
    price_row: pd.Series,
    target_weights: dict[str, float],
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> tuple[dict[str, float], float, float, float, float]:
    net_value = float(gross_value)
    cost = 0.0
    turnover = 0.0
    for _iteration in range(3):
        target_values = {ticker: net_value * target_weights.get(ticker, 0.0) for ticker in TICKERS}
        cost, turnover = _trade_cost(
            current_values,
            target_values,
            commission_rate,
            slippage_rate,
            equity_etf_sell_tax,
        )
        net_value = max(float(gross_value) - cost, 0.0)
    shares = {
        ticker: net_value * target_weights.get(ticker, 0.0) / max(float(price_row[ticker]), 1e-12)
        for ticker in TICKERS
    }
    cash = net_value * target_weights.get("cash", 0.0)
    return shares, float(cash), float(net_value), float(cost), float(turnover)


def _simulate_stateful_next_day_oracle(
    frame: pd.DataFrame,
    report: dict[str, Any],
    panel_631l: pd.DataFrame | None,
    prices: pd.DataFrame,
    *,
    initial_value: float,
    paths: dict[str, tuple[float, float, float, float]],
    path_action: str,
    min_utility_edge: float,
    cooldown_days: int,
    gate_ma_gap_min: float,
    gate_h20_max: float,
    gate_mdd_min: float,
    gate_confidence_min: float,
    gate_risk_mode: str,
    gate_blocked_action: str,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> tuple[pd.Series, dict[str, Any], pd.DataFrame]:
    base_weights = {key: _normalize(dict(value)) for key, value in report["base_weights"].items()}
    golden = base_weights["golden1"]
    shares = {ticker: 0.0 for ticker in TICKERS}
    cash = float(initial_value)
    values: list[float] = []
    decision_rows: list[dict[str, Any]] = []
    total_cost = 0.0
    total_turnover = 0.0
    rebalance_count = 0
    current_key: tuple[float, ...] | None = None
    cooldown_remaining = 0

    for pos, (dt, row) in enumerate(frame.iterrows()):
        price_row = prices.loc[dt]
        gross_value = cash + sum(shares[ticker] * float(price_row[ticker]) for ticker in TICKERS)
        current_values = {ticker: shares[ticker] * float(price_row[ticker]) for ticker in TICKERS}
        baseline_regime = str(row["execution_regime"])
        base_regime = str(row.get("base_regime", baseline_regime))
        panel_row = panel_631l.loc[dt] if panel_631l is not None and dt in panel_631l.index else pd.Series(dtype=float)
        inputs = _row_signal_inputs(panel_row)
        gate_allowed = False
        gate: dict[str, Any] = {}
        all_scores: dict[str, dict[str, float]] = {}

        if base_regime == "golden1" and panel_631l is not None and dt in panel_631l.index:
            gate_allowed, gate = _mpc_gate_allows_path_search(
                panel_row,
                ma_gap=float(row.get("ma_gap", 0.0) or 0.0),
                ma_gap_min=gate_ma_gap_min,
                h20_max=gate_h20_max,
                mdd_min=gate_mdd_min,
                confidence_min=gate_confidence_min,
                risk_mode=gate_risk_mode,
            )
        cooldown_active = cooldown_remaining > 0
        if base_regime == "golden1" and gate_allowed and not cooldown_active and pos + 1 < len(prices):
            next_price = prices.iloc[pos + 1]
            best_name = "P0_hold"
            best_path = paths["P0_hold"]
            best_target = _apply_path_action(golden, best_path[1], path_action)
            best_utility = -1e18
            for name, path in paths.items():
                target = _apply_path_action(golden, path[1], path_action)
                trial_shares, trial_cash, net_value, cost, turnover = _rebalance_state(
                    gross_value=gross_value,
                    current_values=current_values,
                    price_row=price_row,
                    target_weights=target,
                    commission_rate=commission_rate,
                    slippage_rate=slippage_rate,
                    equity_etf_sell_tax=equity_etf_sell_tax,
                )
                next_value = trial_cash + sum(trial_shares[ticker] * float(next_price[ticker]) for ticker in TICKERS)
                utility = float(next_value)
                all_scores[name] = {
                    "utility": utility / max(gross_value, 1e-12),
                    "terminal_value_delta": (next_value - gross_value) / max(gross_value, 1e-12),
                    "drawdown_risk": 0.0,
                    "turnover": float(turnover / max(gross_value, 1e-12)),
                    "transaction_cost": float(cost / max(gross_value, 1e-12)),
                    "missed_rebound": 0.0,
                    **inputs,
                }
                if utility > best_utility:
                    best_name = name
                    best_path = path
                    best_target = target
                    best_utility = utility
            p0_utility = all_scores["P0_hold"]["utility"]
            best_score = all_scores[best_name]
            if best_name != "P0_hold" and best_score["utility"] - p0_utility < float(min_utility_edge):
                best_name = "P0_hold"
                best_path = paths["P0_hold"]
                best_target = _apply_path_action(golden, best_path[1], path_action)
                best_score = all_scores[best_name]
            weights = best_target
        elif base_regime == "golden1" and panel_631l is not None and dt in panel_631l.index:
            best_name = f"{gate_blocked_action}_gate_blocked"
            best_path = paths["P0_hold"]
            best_score = {
                "utility": 0.0,
                "terminal_value_delta": 0.0,
                "drawdown_risk": 0.0,
                "turnover": 0.0,
                "transaction_cost": 0.0,
                "missed_rebound": 0.0,
                **inputs,
            }
            all_scores = {"P0_hold": best_score}
            if gate_blocked_action == "baseline":
                weights = base_weights.get(baseline_regime, base_weights.get("group_a_plus_defensive", golden))
            elif gate_blocked_action == "hold":
                weights = _apply_path_action(golden, best_path[1], path_action)
            else:
                raise ValueError("--gate-blocked-action must be 'hold' or 'baseline'")
        else:
            best_name = "baseline_non_golden_or_no_panel"
            best_path = paths["P0_hold"]
            best_score = {
                "utility": 0.0,
                "terminal_value_delta": 0.0,
                "drawdown_risk": 0.0,
                "turnover": 0.0,
                "transaction_cost": 0.0,
                "missed_rebound": 0.0,
                "p1": None,
                "p5": None,
                "p20": None,
                "mdd": None,
                "gain": None,
                "confidence": None,
            }
            weights = base_weights.get(baseline_regime, base_weights.get("group_a_plus_defensive", golden))

        next_key = tuple(round(float(weights.get(key, 0.0)), 8) for key in (*TICKERS, "cash"))
        if next_key != current_key:
            shares, cash, gross_value, cost, turnover = _rebalance_state(
                gross_value=gross_value,
                current_values=current_values,
                price_row=price_row,
                target_weights=weights,
                commission_rate=commission_rate,
                slippage_rate=slippage_rate,
                equity_etf_sell_tax=equity_etf_sell_tax,
            )
            total_cost += cost
            total_turnover += turnover
            rebalance_count += 1
            current_key = next_key
        values.append(gross_value)
        if float(best_path[1]) != 1.0:
            cooldown_remaining = max(int(cooldown_days), 0)
        elif cooldown_remaining > 0:
            cooldown_remaining -= 1
        decision_rows.append(
            {
                "date": dt,
                "base_regime": base_regime,
                "baseline_execution_regime": baseline_regime,
                "selected_path": best_name,
                "first_step_multiplier": float(best_path[1]),
                "utility": best_score["utility"],
                "terminal_value_delta": best_score["terminal_value_delta"],
                "drawdown_risk": best_score["drawdown_risk"],
                "turnover_penalty_input": best_score["turnover"],
                "transaction_cost_input": best_score.get("transaction_cost", 0.0),
                "missed_rebound": best_score["missed_rebound"],
                "prob_up_h1": best_score.get("p1"),
                "prob_up_h5": best_score.get("p5"),
                "prob_up_h20": best_score.get("p20"),
                "prob_fwd_mdd_gt5_h20": best_score.get("mdd"),
                "prob_fwd_gain_gt5_h20": best_score.get("gain"),
                "confidence": best_score.get("confidence"),
                "gate_allowed": bool(gate_allowed),
                "cooldown_active": bool(cooldown_active),
                "cooldown_remaining": int(cooldown_remaining),
                "gate": gate,
                "all_path_utilities": {name: score["utility"] for name, score in all_scores.items()},
            }
        )

    curve = pd.Series(values, index=prices.index, dtype=float)
    execution = {
        "transaction_cost": float(total_cost),
        "turnover_value": float(total_turnover),
        "rebalance_count": int(rebalance_count),
        "stateful_selection": True,
    }
    decisions = pd.DataFrame(decision_rows).set_index("date")
    return curve, execution, decisions


def _score_committed_realized_path_from_state(
    *,
    path: tuple[float, float, float, float],
    prices: pd.DataFrame,
    start_pos: int,
    shares: dict[str, float],
    cash: float,
    base_weights: dict[str, float],
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
    path_action: str,
    offsets: tuple[int, int, int, int] = (0, 1, 5, 20),
) -> float | None:
    if start_pos + offsets[-1] >= len(prices):
        return None
    trial_shares = dict(shares)
    trial_cash = float(cash)
    for offset, multiplier in zip(offsets[:-1], path[1:]):
        price_row = prices.iloc[start_pos + offset]
        gross_value = trial_cash + sum(trial_shares[ticker] * float(price_row[ticker]) for ticker in TICKERS)
        current_values = {ticker: trial_shares[ticker] * float(price_row[ticker]) for ticker in TICKERS}
        target_weights = _apply_path_action(base_weights, multiplier, path_action)
        trial_shares, trial_cash, _net_value, _cost, _turnover = _rebalance_state(
            gross_value=gross_value,
            current_values=current_values,
            price_row=price_row,
            target_weights=target_weights,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
            equity_etf_sell_tax=equity_etf_sell_tax,
        )
    final_price = prices.iloc[start_pos + offsets[-1]]
    return float(trial_cash + sum(trial_shares[ticker] * float(final_price[ticker]) for ticker in TICKERS))


def _simulate_stateful_committed_oracle(
    frame: pd.DataFrame,
    report: dict[str, Any],
    panel_631l: pd.DataFrame | None,
    prices: pd.DataFrame,
    *,
    initial_value: float,
    paths: dict[str, tuple[float, float, float, float]],
    path_action: str,
    min_utility_edge: float,
    gate_ma_gap_min: float,
    gate_h20_max: float,
    gate_mdd_min: float,
    gate_confidence_min: float,
    gate_risk_mode: str,
    gate_blocked_action: str,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> tuple[pd.Series, dict[str, Any], pd.DataFrame]:
    base_weights = {key: _normalize(dict(value)) for key, value in report["base_weights"].items()}
    golden = base_weights["golden1"]
    shares = {ticker: 0.0 for ticker in TICKERS}
    cash = float(initial_value)
    values: list[float] = []
    decision_rows: list[dict[str, Any]] = []
    total_cost = 0.0
    total_turnover = 0.0
    rebalance_count = 0
    current_key: tuple[float, ...] | None = None
    active_plan: list[float] = []
    active_plan_name = ""

    for pos, (dt, row) in enumerate(frame.iterrows()):
        price_row = prices.loc[dt]
        gross_value = cash + sum(shares[ticker] * float(price_row[ticker]) for ticker in TICKERS)
        current_values = {ticker: shares[ticker] * float(price_row[ticker]) for ticker in TICKERS}
        baseline_regime = str(row["execution_regime"])
        base_regime = str(row.get("base_regime", baseline_regime))
        panel_row = panel_631l.loc[dt] if panel_631l is not None and dt in panel_631l.index else pd.Series(dtype=float)
        inputs = _row_signal_inputs(panel_row)
        gate_allowed = False
        gate: dict[str, Any] = {}
        all_scores: dict[str, dict[str, float]] = {}

        if active_plan:
            multiplier = float(active_plan.pop(0))
            best_name = f"commit_{active_plan_name}"
            best_path = (1.0, multiplier, multiplier, multiplier)
            best_score = {"utility": 0.0, "terminal_value_delta": 0.0, "drawdown_risk": 0.0, "turnover": 0.0, "missed_rebound": 0.0, **inputs}
            weights = _apply_path_action(golden, multiplier, path_action)
        elif base_regime == "golden1" and panel_631l is not None and dt in panel_631l.index:
            gate_allowed, gate = _mpc_gate_allows_path_search(
                panel_row,
                ma_gap=float(row.get("ma_gap", 0.0) or 0.0),
                ma_gap_min=gate_ma_gap_min,
                h20_max=gate_h20_max,
                mdd_min=gate_mdd_min,
                confidence_min=gate_confidence_min,
                risk_mode=gate_risk_mode,
            )
            if gate_allowed:
                best_name = "P0_hold"
                best_path = paths["P0_hold"]
                best_utility = -1e18
                for name, path in paths.items():
                    value = _score_committed_realized_path_from_state(
                        path=path,
                        prices=prices,
                        start_pos=pos,
                        shares=shares,
                        cash=cash,
                        base_weights=golden,
                        commission_rate=commission_rate,
                        slippage_rate=slippage_rate,
                        equity_etf_sell_tax=equity_etf_sell_tax,
                        path_action=path_action,
                    )
                    utility = -1e18 if value is None else value
                    all_scores[name] = {"utility": utility / max(gross_value, 1e-12), "terminal_value_delta": (utility - gross_value) / max(gross_value, 1e-12), "drawdown_risk": 0.0, "turnover": 0.0, "missed_rebound": 0.0, **inputs}
                    if utility > best_utility:
                        best_name = name
                        best_path = path
                        best_utility = utility
                p0_utility = all_scores["P0_hold"]["utility"]
                best_score = all_scores[best_name]
                if best_name != "P0_hold" and best_score["utility"] - p0_utility < float(min_utility_edge):
                    best_name = "P0_hold"
                    best_path = paths["P0_hold"]
                    best_score = all_scores[best_name]
                active_plan = list(best_path[2:])
                active_plan_name = best_name
                weights = _apply_path_action(golden, best_path[1], path_action)
            else:
                best_name = f"{gate_blocked_action}_gate_blocked"
                best_path = paths["P0_hold"]
                best_score = {"utility": 0.0, "terminal_value_delta": 0.0, "drawdown_risk": 0.0, "turnover": 0.0, "missed_rebound": 0.0, **inputs}
                all_scores = {"P0_hold": best_score}
                weights = (
                    base_weights.get(baseline_regime, base_weights.get("group_a_plus_defensive", golden))
                    if gate_blocked_action == "baseline"
                    else _apply_path_action(golden, 1.0, path_action)
                )
        else:
            best_name = "baseline_non_golden_or_no_panel"
            best_path = paths["P0_hold"]
            best_score = {"utility": 0.0, "terminal_value_delta": 0.0, "drawdown_risk": 0.0, "turnover": 0.0, "missed_rebound": 0.0, "p1": None, "p5": None, "p20": None, "mdd": None, "gain": None, "confidence": None}
            weights = base_weights.get(baseline_regime, base_weights.get("group_a_plus_defensive", golden))

        next_key = tuple(round(float(weights.get(key, 0.0)), 8) for key in (*TICKERS, "cash"))
        if next_key != current_key:
            shares, cash, gross_value, cost, turnover = _rebalance_state(
                gross_value=gross_value,
                current_values=current_values,
                price_row=price_row,
                target_weights=weights,
                commission_rate=commission_rate,
                slippage_rate=slippage_rate,
                equity_etf_sell_tax=equity_etf_sell_tax,
            )
            total_cost += cost
            total_turnover += turnover
            rebalance_count += 1
            current_key = next_key
        values.append(gross_value)
        decision_rows.append(
            {
                "date": dt,
                "base_regime": base_regime,
                "baseline_execution_regime": baseline_regime,
                "selected_path": best_name,
                "first_step_multiplier": float(best_path[1]),
                "utility": best_score["utility"],
                "terminal_value_delta": best_score["terminal_value_delta"],
                "drawdown_risk": best_score["drawdown_risk"],
                "turnover_penalty_input": best_score.get("turnover", 0.0),
                "missed_rebound": best_score["missed_rebound"],
                "prob_up_h1": best_score.get("p1"),
                "prob_up_h5": best_score.get("p5"),
                "prob_up_h20": best_score.get("p20"),
                "prob_fwd_mdd_gt5_h20": best_score.get("mdd"),
                "prob_fwd_gain_gt5_h20": best_score.get("gain"),
                "confidence": best_score.get("confidence"),
                "gate_allowed": bool(gate_allowed),
                "committed_plan_remaining": int(len(active_plan)),
                "gate": gate,
                "all_path_utilities": {name: score["utility"] for name, score in all_scores.items()},
            }
        )

    return pd.Series(values, index=prices.index, dtype=float), {
        "transaction_cost": float(total_cost),
        "turnover_value": float(total_turnover),
        "rebalance_count": int(rebalance_count),
        "stateful_committed_selection": True,
    }, pd.DataFrame(decision_rows).set_index("date")


def _build_mpc_targets(
    frame: pd.DataFrame,
    report: dict[str, Any],
    panel_631l: pd.DataFrame | None,
    prices: pd.DataFrame | None,
    *,
    paths: dict[str, tuple[float, float, float, float]],
    lambda_drawdown: float,
    gamma_turnover: float,
    eta_missed_rebound: float,
    confidence_weight: float,
    scoring_mode: str,
    edge_scale: float,
    rebalance_cost_rate: float,
    min_utility_edge: float,
    path_action: str,
    gate_ma_gap_min: float,
    gate_h20_max: float,
    gate_mdd_min: float,
    gate_confidence_min: float,
    gate_risk_mode: str,
    gate_blocked_action: str,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    base_weights = {key: _normalize(dict(value)) for key, value in report["base_weights"].items()}
    golden = base_weights["golden1"]
    base_00631l_weight = float(golden.get("00631L.TW", 0.0) or 0.0)
    target_rows: list[dict[str, float]] = []
    decision_rows: list[dict[str, Any]] = []

    for dt, row in frame.iterrows():
        baseline_regime = str(row["execution_regime"])
        base_regime = str(row.get("base_regime", baseline_regime))
        # This shadow is meant to replace A21.18's H20/H5 overlay, so the
        # decision point is the pre-overlay A21.11/base golden1 state, not the
        # already-modified A21.18 execution_regime.
        if base_regime == "golden1" and panel_631l is not None and dt in panel_631l.index and base_00631l_weight > 0:
            panel_row = panel_631l.loc[dt]
            gate_allowed, gate = _mpc_gate_allows_path_search(
                panel_row,
                ma_gap=float(row.get("ma_gap", 0.0) or 0.0),
                ma_gap_min=gate_ma_gap_min,
                h20_max=gate_h20_max,
                mdd_min=gate_mdd_min,
                confidence_min=gate_confidence_min,
                risk_mode=gate_risk_mode,
            )
            if gate_allowed:
                best_name, best_path, best_score, all_scores = _select_path(
                    panel_row,
                    base_00631l_weight=base_00631l_weight,
                    paths=paths,
                    lambda_drawdown=lambda_drawdown,
                    gamma_turnover=gamma_turnover,
                    eta_missed_rebound=eta_missed_rebound,
                    confidence_weight=confidence_weight,
                    scoring_mode=scoring_mode,
                    edge_scale=edge_scale,
                    rebalance_cost_rate=rebalance_cost_rate,
                    min_utility_edge=min_utility_edge,
                    prices=prices,
                    current_dt=dt,
                    base_weights=golden,
                    commission_rate=commission_rate,
                    slippage_rate=slippage_rate,
                    equity_etf_sell_tax=equity_etf_sell_tax,
                    path_action=path_action,
                )
                weights = _apply_path_action(golden, best_path[1], path_action)
            else:
                best_name = f"{gate_blocked_action}_gate_blocked"
                best_path = DEFAULT_PATHS["P0_hold"]
                best_score = _score_path(
                    best_path,
                    panel_row,
                    base_00631l_weight=base_00631l_weight,
                    lambda_drawdown=lambda_drawdown,
                    gamma_turnover=gamma_turnover,
                    eta_missed_rebound=eta_missed_rebound,
                    confidence_weight=confidence_weight,
                )
                all_scores = {"P0_hold": best_score}
                if gate_blocked_action == "baseline":
                    weights = base_weights.get(baseline_regime, base_weights.get("group_a_plus_defensive", golden))
                elif gate_blocked_action == "hold":
                    weights = _apply_path_action(golden, best_path[1], path_action)
                else:
                    raise ValueError("--gate-blocked-action must be 'hold' or 'baseline'")
            decision_rows.append(
                {
                    "date": dt,
                    "base_regime": base_regime,
                    "baseline_execution_regime": baseline_regime,
                    "selected_path": best_name,
                    "first_step_multiplier": float(best_path[1]),
                    "utility": best_score["utility"],
                    "terminal_value_delta": best_score["terminal_value_delta"],
                    "drawdown_risk": best_score["drawdown_risk"],
                    "turnover_penalty_input": best_score["turnover"],
                    "missed_rebound": best_score["missed_rebound"],
                    "prob_up_h1": best_score["p1"],
                    "prob_up_h5": best_score["p5"],
                    "prob_up_h20": best_score["p20"],
                    "prob_fwd_mdd_gt5_h20": best_score["mdd"],
                    "prob_fwd_gain_gt5_h20": best_score["gain"],
                    "confidence": best_score["confidence"],
                    "gate_allowed": bool(gate_allowed),
                    "gate": gate,
                    "all_path_utilities": {name: score["utility"] for name, score in all_scores.items()},
                }
            )
        else:
            weights = base_weights.get(baseline_regime, base_weights.get("group_a_plus_defensive", golden))
            decision_rows.append(
                {
                    "date": dt,
                    "base_regime": base_regime,
                    "baseline_execution_regime": baseline_regime,
                    "selected_path": "baseline_non_golden_or_no_panel",
                    "first_step_multiplier": 1.0,
                    "utility": 0.0,
                    "terminal_value_delta": 0.0,
                    "drawdown_risk": 0.0,
                    "turnover_penalty_input": 0.0,
                    "missed_rebound": 0.0,
                    "prob_up_h1": None,
                    "prob_up_h5": None,
                    "prob_up_h20": None,
                    "prob_fwd_mdd_gt5_h20": None,
                    "prob_fwd_gain_gt5_h20": None,
                    "confidence": None,
                    "gate_allowed": False,
                    "gate": {},
                    "all_path_utilities": {},
                }
            )
        target_rows.append({key: float(weights.get(key, 0.0) or 0.0) for key in (*TICKERS, "cash")})

    targets = pd.DataFrame(target_rows, index=frame.index)
    decisions = pd.DataFrame(decision_rows).set_index("date")
    return targets, decisions


def _add_realized_decision_outcomes(
    decisions: pd.DataFrame,
    panel_631l: pd.DataFrame | None,
    prices: pd.DataFrame,
    horizons: tuple[int, ...] = (1, 5, 20),
) -> pd.DataFrame:
    """Attach realized forward outcomes for diagnosis only.

    These fields are intentionally added after path selection. They must not be
    used by _score_path or _select_path.
    """
    out = decisions.copy()
    for column in (
        "forward_gain_h20",
        "forward_mdd_h20",
        "actual_fwd_gain_gt5_h20",
        "actual_fwd_mdd_gt5_h20",
    ):
        if panel_631l is not None and column in panel_631l.columns:
            out[column] = panel_631l[column].reindex(out.index)

    index_positions = {dt: pos for pos, dt in enumerate(prices.index)}
    for horizon in horizons:
        fwd_0050: list[float | None] = []
        fwd_00631l: list[float | None] = []
        for dt in out.index:
            pos = index_positions.get(dt)
            if pos is None or pos + horizon >= len(prices):
                fwd_0050.append(None)
                fwd_00631l.append(None)
                continue
            current = prices.iloc[pos]
            future = prices.iloc[pos + horizon]
            fwd_0050.append(float(future["0050.TW"] / current["0050.TW"] - 1.0))
            fwd_00631l.append(float(future["00631L.TW"] / current["00631L.TW"] - 1.0))
        out[f"fwd_0050_ret_{horizon}d"] = fwd_0050
        out[f"fwd_00631l_ret_{horizon}d"] = fwd_00631l
        out[f"00631l_minus_0050_{horizon}d"] = out[f"fwd_00631l_ret_{horizon}d"] - out[f"fwd_0050_ret_{horizon}d"]
        out[f"hedge_would_help_{horizon}d"] = out[f"fwd_0050_ret_{horizon}d"] > out[f"fwd_00631l_ret_{horizon}d"]
    return out


def _safe_mean(series: pd.Series) -> float | None:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return None
    return float(clean.mean())


def _summarize_changed_decisions(changed: pd.DataFrame) -> dict[str, Any]:
    if changed.empty:
        return {
            "count": 0,
            "hedge_help_rate_5d": None,
            "hedge_help_rate_1d": None,
            "hedge_help_rate_20d": None,
            "mean_00631l_minus_0050_1d": None,
            "mean_00631l_minus_0050_5d": None,
            "mean_00631l_minus_0050_20d": None,
            "mean_forward_gain_h20": None,
            "mean_forward_mdd_h20": None,
            "by_path": {},
        }
    summary = {
        "count": int(len(changed)),
        "hedge_help_rate_1d": _safe_mean(changed["hedge_would_help_1d"].astype(float)),
        "hedge_help_rate_5d": _safe_mean(changed["hedge_would_help_5d"].astype(float)),
        "hedge_help_rate_20d": _safe_mean(changed["hedge_would_help_20d"].astype(float)),
        "mean_00631l_minus_0050_1d": _safe_mean(changed["00631l_minus_0050_1d"]),
        "mean_00631l_minus_0050_5d": _safe_mean(changed["00631l_minus_0050_5d"]),
        "mean_00631l_minus_0050_20d": _safe_mean(changed["00631l_minus_0050_20d"]),
        "mean_forward_gain_h20": _safe_mean(changed.get("forward_gain_h20", pd.Series(dtype=float))),
        "mean_forward_mdd_h20": _safe_mean(changed.get("forward_mdd_h20", pd.Series(dtype=float))),
        "mean_predicted_mdd": _safe_mean(changed["prob_fwd_mdd_gt5_h20"]),
        "mean_predicted_gain": _safe_mean(changed["prob_fwd_gain_gt5_h20"]),
        "by_path": {},
    }
    for path, group in changed.groupby("selected_path"):
        summary["by_path"][str(path)] = {
            "count": int(len(group)),
            "hedge_help_rate_1d": _safe_mean(group["hedge_would_help_1d"].astype(float)),
            "hedge_help_rate_20d": _safe_mean(group["hedge_would_help_20d"].astype(float)),
            "mean_00631l_minus_0050_1d": _safe_mean(group["00631l_minus_0050_1d"]),
            "mean_00631l_minus_0050_20d": _safe_mean(group["00631l_minus_0050_20d"]),
            "mean_forward_gain_h20": _safe_mean(group.get("forward_gain_h20", pd.Series(dtype=float))),
            "mean_forward_mdd_h20": _safe_mean(group.get("forward_mdd_h20", pd.Series(dtype=float))),
        }
    return summary


def _summarize_warning_days(warnings: pd.DataFrame) -> dict[str, Any]:
    summary = _summarize_changed_decisions(warnings)
    if warnings.empty:
        summary.update(
            {
                "mean_prob_up_h20": None,
                "mean_prob_fwd_mdd_gt5_h20": None,
                "mean_prob_fwd_gain_gt5_h20": None,
                "mean_confidence": None,
            }
        )
        return summary
    summary.update(
        {
            "mean_prob_up_h20": _safe_mean(warnings["prob_up_h20"]),
            "mean_prob_fwd_mdd_gt5_h20": _safe_mean(warnings["prob_fwd_mdd_gt5_h20"]),
            "mean_prob_fwd_gain_gt5_h20": _safe_mean(warnings["prob_fwd_gain_gt5_h20"]),
            "mean_confidence": _safe_mean(warnings["confidence"]),
        }
    )
    return summary


def _records_for_json(frame: pd.DataFrame, limit: int | None = None) -> list[dict[str, Any]]:
    if limit is not None:
        frame = frame.head(limit)
    records = frame.reset_index().assign(date=lambda df: df["date"].astype(str)).to_dict(orient="records")
    for record in records:
        for key, value in list(record.items()):
            if pd.isna(value) if not isinstance(value, (dict, list, tuple)) else False:
                record[key] = None
    return records


def _curve_diff_summary(
    baseline_curve: pd.Series,
    candidate_curve: pd.Series,
    decisions: pd.DataFrame,
    *,
    event_window_days: int = 3,
) -> dict[str, Any]:
    aligned = pd.DataFrame({"baseline": baseline_curve, "candidate": candidate_curve}).dropna()
    if aligned.empty:
        return {}
    aligned["diff"] = aligned["candidate"] - aligned["baseline"]
    aligned["diff_pct"] = aligned["diff"] / aligned["baseline"].replace(0.0, pd.NA)
    changed_dates = list(
        decisions.index[
            (decisions["base_regime"].astype(str) == "golden1")
            & (decisions["first_step_multiplier"].astype(float) != 1.0)
        ]
    )
    event_samples: list[dict[str, Any]] = []
    for dt in changed_dates[:10]:
        if dt not in aligned.index:
            continue
        pos = aligned.index.get_loc(dt)
        start = max(0, int(pos) - event_window_days)
        stop = min(len(aligned), int(pos) + event_window_days + 1)
        rows = aligned.iloc[start:stop].reset_index().rename(columns={"dt": "date", "index": "date"})
        rows["date"] = rows["date"].astype(str)
        event_samples.append(
            {
                "event_date": str(dt.date()),
                "selected_path": str(decisions.loc[dt, "selected_path"]),
                "first_step_multiplier": float(decisions.loc[dt, "first_step_multiplier"]),
                "rows": rows.to_dict(orient="records"),
            }
        )
    return {
        "final_diff": float(aligned["diff"].iloc[-1]),
        "final_diff_pct": float(aligned["diff_pct"].iloc[-1]),
        "min_diff": float(aligned["diff"].min()),
        "min_diff_date": str(aligned["diff"].idxmin().date()),
        "max_diff": float(aligned["diff"].max()),
        "max_diff_date": str(aligned["diff"].idxmax().date()),
        "positive_diff_days": int((aligned["diff"] > 0.0).sum()),
        "negative_diff_days": int((aligned["diff"] < 0.0).sum()),
        "event_samples": event_samples,
    }


def evaluate_window(
    *,
    label: str,
    start: str,
    end: str,
    bucket: str,
    db_path: Path,
    initial_value: float,
    ncf_panel_631l: str | None,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
    lambda_drawdown: float,
    gamma_turnover: float,
    eta_missed_rebound: float,
    confidence_weight: float,
    scoring_mode: str,
    edge_scale: float,
    rebalance_cost_rate: float,
    min_utility_edge: float,
    path_set: str,
    path_action: str,
    cooldown_days: int,
    gate_ma_gap_min: float,
    gate_h20_max: float,
    gate_mdd_min: float,
    gate_confidence_min: float,
    gate_risk_mode: str,
    gate_blocked_action: str,
) -> dict[str, Any]:
    end = _resolve_end_date(db_path, end)
    report, frame = run_a2118(
        start=start,
        end=end,
        initial_value=initial_value,
        db=db_path,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
        ncf_panel_631l_path=ncf_panel_631l,
        h20_max=0.33,
        conf_min=0.55,
        h5_reentry_min=0.55,
        chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
        risk_score_lookback_days=RISK_SCORE_LOOKBACK_DAYS,
        momentum_fast_exit_min=MOMENTUM_FAST_EXIT_MIN,
        momentum_fast_exit_ma_gap_min=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
        exclude_zero_volume_rows=True,
    )
    panel = _load_panel(ncf_panel_631l)
    prices, dividend_coverage = _load_total_return_prices(db_path, frame.index)
    paths = _path_set(path_set)
    if scoring_mode == "stateful_next_day_oracle":
        curve, execution, decisions = _simulate_stateful_next_day_oracle(
            frame,
            report,
            panel,
            prices,
            initial_value=initial_value,
            paths=paths,
            path_action=path_action,
            min_utility_edge=min_utility_edge,
            cooldown_days=cooldown_days,
            gate_ma_gap_min=gate_ma_gap_min,
            gate_h20_max=gate_h20_max,
            gate_mdd_min=gate_mdd_min,
            gate_confidence_min=gate_confidence_min,
            gate_risk_mode=gate_risk_mode,
            gate_blocked_action=gate_blocked_action,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
            equity_etf_sell_tax=equity_etf_sell_tax,
        )
    elif scoring_mode == "stateful_committed_oracle":
        curve, execution, decisions = _simulate_stateful_committed_oracle(
            frame,
            report,
            panel,
            prices,
            initial_value=initial_value,
            paths=paths,
            path_action=path_action,
            min_utility_edge=min_utility_edge,
            gate_ma_gap_min=gate_ma_gap_min,
            gate_h20_max=gate_h20_max,
            gate_mdd_min=gate_mdd_min,
            gate_confidence_min=gate_confidence_min,
            gate_risk_mode=gate_risk_mode,
            gate_blocked_action=gate_blocked_action,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
            equity_etf_sell_tax=equity_etf_sell_tax,
        )
    else:
        targets, decisions = _build_mpc_targets(
            frame,
            report,
            panel,
            prices,
            paths=paths,
            lambda_drawdown=lambda_drawdown,
            gamma_turnover=gamma_turnover,
            eta_missed_rebound=eta_missed_rebound,
            confidence_weight=confidence_weight,
            scoring_mode=scoring_mode,
            edge_scale=edge_scale,
            rebalance_cost_rate=rebalance_cost_rate,
            min_utility_edge=min_utility_edge,
            path_action=path_action,
            gate_ma_gap_min=gate_ma_gap_min,
            gate_h20_max=gate_h20_max,
            gate_mdd_min=gate_mdd_min,
            gate_confidence_min=gate_confidence_min,
            gate_risk_mode=gate_risk_mode,
            gate_blocked_action=gate_blocked_action,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
            equity_etf_sell_tax=equity_etf_sell_tax,
        )
        curve, execution = _simulate_daily_target_weights(
            prices,
            targets,
            initial_value,
            commission_rate,
            slippage_rate,
            equity_etf_sell_tax,
        )
    decisions = _add_realized_decision_outcomes(decisions, panel, prices)
    candidate_metrics = _metrics(curve, initial_value)
    baseline_metrics = report["metrics"]
    baseline_curve = pd.to_numeric(frame["portfolio_value"], errors="coerce")
    path_counts = {
        str(key): int(value)
        for key, value in decisions["selected_path"].value_counts().sort_index().items()
    }
    changed_golden_days = decisions[
        (decisions["base_regime"].astype(str) == "golden1")
        & (decisions["first_step_multiplier"].astype(float) != 1.0)
    ]
    warning_days = decisions[
        (decisions["base_regime"].astype(str) == "golden1")
        & (decisions["gate_allowed"] == True)
    ]
    gate_allowed_days = int((decisions["gate_allowed"] == True).sum())
    return {
        "label": label,
        "bucket": bucket,
        "window": report["window"],
        "baseline_strategy": report["strategy"],
        "baseline_metrics": baseline_metrics,
        "candidate_metrics": candidate_metrics,
        "delta_vs_baseline": _metric_delta(candidate_metrics, baseline_metrics),
        "candidate_execution": execution,
        "baseline_execution": report.get("execution", {}),
        "curve_diff_summary": _curve_diff_summary(baseline_curve, curve, decisions),
        "path_counts": path_counts,
        "gate_allowed_days": gate_allowed_days,
        "warning_days": int(len(warning_days)),
        "warning_day_fraction": float(len(warning_days) / max((decisions["base_regime"] == "golden1").sum(), 1)),
        "warning_day_outcome_summary": _summarize_warning_days(warning_days),
        "warning_decisions": _records_for_json(warning_days, limit=200),
        "changed_golden_days": int(len(changed_golden_days)),
        "changed_golden_fraction": float(len(changed_golden_days) / max((decisions["base_regime"] == "golden1").sum(), 1)),
        "changed_decision_outcome_summary": _summarize_changed_decisions(changed_golden_days),
        "changed_decisions": _records_for_json(changed_golden_days),
        "sample_decisions": _records_for_json(decisions[
            decisions["selected_path"].astype(str) != "baseline_non_golden_or_no_panel"
        ], limit=20),
        "dividend_coverage": dividend_coverage,
        "ncf_panel": ncf_panel_631l,
    }


def _parse_windows(raw: str | None) -> list[tuple[str, str, str, str | None, str]]:
    if not raw:
        return list(DEFAULT_WINDOWS)
    out: list[tuple[str, str, str, str | None, str]] = []
    for item in raw.split(","):
        parts = [part.strip() for part in item.split(":")]
        if len(parts) not in (3, 4, 5):
            raise ValueError("--windows items must be label:start:end[:panel[:bucket]]")
        label, start, end = parts[:3]
        panel = parts[3] if len(parts) >= 4 and parts[3] else PANEL_2025_2026
        bucket = parts[4] if len(parts) >= 5 and parts[4] else "custom"
        out.append((label, start, end, panel, bucket))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--lambda-drawdown", type=float, default=0.35)
    parser.add_argument("--gamma-turnover", type=float, default=2.0)
    parser.add_argument("--eta-missed-rebound", type=float, default=0.30)
    parser.add_argument("--confidence-weight", type=float, default=0.50)
    parser.add_argument(
        "--scoring-mode",
        choices=(
            "proxy",
            "path_value",
            "realized_oracle",
            "realized_next_day_oracle",
            "stateful_next_day_oracle",
            "stateful_committed_oracle",
        ),
        default="proxy",
    )
    parser.add_argument("--edge-scale", type=float, default=0.08)
    parser.add_argument("--rebalance-cost-rate", type=float, default=0.003)
    parser.add_argument("--min-utility-edge", type=float, default=0.0)
    parser.add_argument("--path-set", choices=("default", "conservative", "disaster"), default="default")
    parser.add_argument(
        "--path-action",
        choices=("trim_00631l_to_0050", "trim_0050_to_cash"),
        default="trim_00631l_to_0050",
    )
    parser.add_argument("--cooldown-days", type=int, default=0)
    parser.add_argument("--gate-ma-gap-min", type=float, default=0.10)
    parser.add_argument("--gate-h20-max", type=float, default=0.33)
    parser.add_argument("--gate-mdd-min", type=float, default=0.60)
    parser.add_argument("--gate-confidence-min", type=float, default=0.55)
    parser.add_argument("--gate-risk-mode", choices=("any", "all"), default="any")
    parser.add_argument("--gate-blocked-action", choices=("hold", "baseline"), default="hold")
    parser.add_argument("--windows", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    db_path = _resolve(args.db)
    windows = _parse_windows(args.windows)
    results = [
        evaluate_window(
            label=label,
            start=start,
            end=end,
            bucket=bucket,
            db_path=db_path,
            initial_value=float(args.initial_value),
            ncf_panel_631l=panel,
            commission_rate=float(args.commission_rate),
            slippage_rate=float(args.slippage_rate),
            equity_etf_sell_tax=float(args.equity_etf_sell_tax),
            lambda_drawdown=float(args.lambda_drawdown),
            gamma_turnover=float(args.gamma_turnover),
            eta_missed_rebound=float(args.eta_missed_rebound),
            confidence_weight=float(args.confidence_weight),
            scoring_mode=str(args.scoring_mode),
            edge_scale=float(args.edge_scale),
            rebalance_cost_rate=float(args.rebalance_cost_rate),
            min_utility_edge=float(args.min_utility_edge),
            path_set=str(args.path_set),
            path_action=str(args.path_action),
            cooldown_days=int(args.cooldown_days),
            gate_ma_gap_min=float(args.gate_ma_gap_min),
            gate_h20_max=float(args.gate_h20_max),
            gate_mdd_min=float(args.gate_mdd_min),
            gate_confidence_min=float(args.gate_confidence_min),
            gate_risk_mode=str(args.gate_risk_mode),
            gate_blocked_action=str(args.gate_blocked_action),
        )
        for label, start, end, panel, bucket in windows
    ]
    passed = [
        item
        for item in results
        if item["delta_vs_baseline"]["delta_final_value"] >= 0
        and item["delta_vs_baseline"]["delta_sharpe_ratio"] >= 0
        and item["delta_vs_baseline"]["delta_max_drawdown"] >= 0
    ]
    if str(args.scoring_mode) in (
        "realized_oracle",
        "realized_next_day_oracle",
        "stateful_next_day_oracle",
        "stateful_committed_oracle",
    ):
        lookahead_policy = "Realized-oracle modes use future prices and are diagnostic upper bounds only."
    else:
        lookahead_policy = (
            "Path selection uses prob_up_h1/h5/h20, prob_fwd_mdd_gt5_h20, "
            "prob_fwd_gain_gt5_h20, and confidence. Realized forward labels "
            "are not used for path selection."
        )
    payload = {
        "report_type": "a2118_mpc_path_shadow",
        "status": "research_only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "method": {
            "policy": "finite_path_mpc_first_step_only",
            "path_multipliers_relative_to_golden1_00631l": _path_set(str(args.path_set)),
            "utility": (
                "terminal_value_delta - lambda_drawdown * expected_drawdown "
                "- gamma_turnover * turnover - eta_missed_rebound * missed_rebound"
            ),
            "no_lookahead_policy": lookahead_policy,
            "params": {
                "lambda_drawdown": float(args.lambda_drawdown),
                "gamma_turnover": float(args.gamma_turnover),
                "eta_missed_rebound": float(args.eta_missed_rebound),
                "confidence_weight": float(args.confidence_weight),
                "scoring_mode": str(args.scoring_mode),
                "edge_scale": float(args.edge_scale),
                "rebalance_cost_rate": float(args.rebalance_cost_rate),
                "min_utility_edge": float(args.min_utility_edge),
                "path_set": str(args.path_set),
                "path_action": str(args.path_action),
                "cooldown_days": int(args.cooldown_days),
                "gate_ma_gap_min": float(args.gate_ma_gap_min),
                "gate_h20_max": float(args.gate_h20_max),
                "gate_mdd_min": float(args.gate_mdd_min),
                "gate_confidence_min": float(args.gate_confidence_min),
                "gate_risk_mode": str(args.gate_risk_mode),
                "gate_blocked_action": str(args.gate_blocked_action),
            },
        },
        "summary": {
            "windows": len(results),
            "triple_pass_windows": len(passed),
            "all_windows_triple_pass": len(passed) == len(results),
            "tuning_windows": sum(1 for item in results if item["bucket"] == "tuning_window"),
            "out_of_sample_windows": sum(1 for item in results if item["bucket"] == "out_of_sample"),
        },
        "results": results,
    }
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"JSON: {output}")
    print(
        "Triple-pass windows: "
        f"{payload['summary']['triple_pass_windows']}/{payload['summary']['windows']}"
    )
    for item in results:
        delta = item["delta_vs_baseline"]
        print(
            f"{item['label']}: "
            f"Δfinal={delta['delta_final_value']:,.0f}, "
            f"Δsharpe={delta['delta_sharpe_ratio']:.4f}, "
            f"Δmdd={delta['delta_max_drawdown']:.4f}, "
            f"changed_golden_days={item['changed_golden_days']}"
        )


if __name__ == "__main__":
    main()
