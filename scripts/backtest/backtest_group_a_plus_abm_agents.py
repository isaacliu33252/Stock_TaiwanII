#!/usr/bin/env python3
"""Agent-based observable proxy tests for GroupA+.

Research-only implementation inspired by agent-based market models.  It
approximates fundamentalist, momentum, and contrarian agents with observable
price/chip variables, then lets recent agent fitness determine aggregate demand.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
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
from backtest_group_a_plus_switch_policy import (
    DB_PATH,
    SwitchRule,
    _load_chip_features,
    _load_prices,
    _metrics,
    _regime_features,
    _simulate_regime_curve,
    _switch_returns,
)


PROJECT_ROOT = Path(__file__).resolve().parent

A207_RULE = SwitchRule(
    "risk_ma75_dd11_total6_hold5_eg0175_xg020",
    75,
    -0.0175,
    0.02,
    75,
    -0.11,
    5,
    5,
    0,
    None,
    0,
    None,
    6,
    6,
)
MA20_RULE = SwitchRule("ma20_dd7_hold5", 20, -0.03, 0.01, 20, -0.07, 5, 5)


def _parse_float_list(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def _parse_int_list(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def _single_regime_returns(
    prices: pd.DataFrame,
    regime: str,
    weights_by_regime: dict[str, dict[str, float]],
    initial_value: float,
) -> pd.Series:
    curve = _simulate_regime_curve(prices, pd.Series(regime, index=prices.index), weights_by_regime, initial_value)
    return curve.pct_change().fillna(0.0)


def _agent_vote_returns(votes: pd.Series, golden_returns: pd.Series, defensive_returns: pd.Series) -> pd.Series:
    return pd.Series(
        np.where(votes.astype(int) > 0, golden_returns, defensive_returns),
        index=votes.index,
        dtype=float,
    )


def _abm_features(
    prices: pd.DataFrame,
    chip_features: pd.DataFrame,
    risk_threshold: int,
    low_risk_threshold: int,
    momentum_days: int,
    hot_return: float,
    buy_dip_drawdown: float,
    trend_return: float,
) -> pd.DataFrame:
    frame = _regime_features(prices, A207_RULE, chip_features)
    close = prices["0050.TW"].astype(float)
    ret_mom = close.pct_change(momentum_days).fillna(0.0)
    ret_5d = close.pct_change(5).fillna(0.0)
    ret_20d = close.pct_change(20).fillna(0.0)
    frame["return_0050_5d"] = ret_5d
    frame["return_0050_20d"] = ret_20d
    frame["return_0050_mom"] = ret_mom

    fundamental_defense = (
        (frame["total_risk_score"] >= risk_threshold)
        | ((frame["foreign_0050_5d"] < 0.0) & (frame["inst_0050_5d"] < 0.0) & (ret_5d < 0.0))
        | ((frame["foreign_shareholding_0050_ratio_chg_5d"] < 0.0) & (ret_5d < 0.0))
    )
    frame["fundamentalist_vote"] = np.where(fundamental_defense, -1, 1)

    momentum_defense = (ret_mom <= -abs(trend_return)) | (frame["ma_gap"] <= -0.01)
    momentum_golden = (ret_mom >= abs(trend_return)) & (frame["ma_gap"] >= 0.0)
    frame["momentum_vote"] = np.where(momentum_defense, -1, np.where(momentum_golden, 1, 0))

    contrarian_golden = (frame["drawdown"] <= buy_dip_drawdown) & (frame["total_risk_score"] <= low_risk_threshold)
    contrarian_defense = (ret_20d >= hot_return) & (frame["realized_vol_ratio_20_60"] >= 1.10)
    frame["contrarian_vote"] = np.where(contrarian_golden, 1, np.where(contrarian_defense, -1, 0))

    frame["technical_sync"] = (
        (frame["momentum_vote"].abs() + frame["contrarian_vote"].abs() >= 1)
        & (frame["momentum_vote"] + frame["contrarian_vote"]).abs().ge(1)
    ).astype(int)
    return frame


def _softmax_agent_weights(fitness: pd.DataFrame, beta: float) -> pd.DataFrame:
    clipped = fitness.clip(lower=-0.05, upper=0.05).fillna(0.0)
    scaled = clipped * float(beta) * 252.0
    max_scaled = scaled.max(axis=1)
    exp_values = np.exp(scaled.sub(max_scaled, axis=0))
    total = exp_values.sum(axis=1).replace(0.0, math.nan)
    return exp_values.div(total, axis=0).fillna(1.0 / len(fitness.columns))


def _abm_regime(
    features: pd.DataFrame,
    a207_regime: pd.Series,
    golden_returns: pd.Series,
    defensive_returns: pd.Series,
    fitness_window: int,
    beta: float,
    demand_threshold: float,
    min_hold_days: int,
    require_technical_sync: bool,
) -> pd.DataFrame:
    agent_votes = pd.DataFrame(
        {
            "fundamentalist": features["fundamentalist_vote"].replace(0, 1).astype(int),
            "momentum": features["momentum_vote"].replace(0, 1).astype(int),
            "contrarian": features["contrarian_vote"].replace(0, 1).astype(int),
        },
        index=features.index,
    )
    agent_returns = pd.DataFrame(
        {
            agent: _agent_vote_returns(agent_votes[agent], golden_returns, defensive_returns)
            for agent in agent_votes.columns
        },
        index=features.index,
    )
    fitness = agent_returns.rolling(fitness_window, min_periods=max(5, fitness_window // 3)).mean().shift(1).fillna(0.0)
    weights = _softmax_agent_weights(fitness, beta)
    demand = (weights * agent_votes).sum(axis=1)

    regimes: list[str] = []
    abm_actions: list[str] = []
    current_override = ""
    hold_days = 0
    for dt in features.index:
        positive = demand.loc[dt] >= demand_threshold
        negative = demand.loc[dt] <= -demand_threshold
        if require_technical_sync and int(features.loc[dt, "technical_sync"]) <= 0:
            positive = False
            negative = False
        action = "base"
        if current_override:
            hold_days += 1
            if hold_days >= min_hold_days:
                current_override = ""
                hold_days = 0
        if not current_override:
            if negative:
                current_override = "group_a_plus_defensive"
                hold_days = 1
                action = "force_defensive"
            elif positive:
                current_override = "golden1"
                hold_days = 1
                action = "force_golden"
        regimes.append(current_override if current_override else str(a207_regime.loc[dt]))
        abm_actions.append(action)

    out = features.copy()
    out["fitness_fundamentalist"] = fitness["fundamentalist"]
    out["fitness_momentum"] = fitness["momentum"]
    out["fitness_contrarian"] = fitness["contrarian"]
    out["weight_fundamentalist"] = weights["fundamentalist"]
    out["weight_momentum"] = weights["momentum"]
    out["weight_contrarian"] = weights["contrarian"]
    out["abm_demand"] = demand
    out["abm_action"] = abm_actions
    out["regime"] = regimes
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision-pointer", default=str(DEFAULT_DECISION_POINTER))
    parser.add_argument("--golden-signal", default=str(DEFAULT_GOLDEN_SIGNAL))
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-06-18")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--fitness-windows", default="20,40,60")
    parser.add_argument("--betas", default="1.5,3.0,6.0")
    parser.add_argument("--demand-thresholds", default="0.20,0.35,0.50")
    parser.add_argument("--risk-thresholds", default="4,6")
    parser.add_argument("--low-risk-thresholds", default="1,2")
    parser.add_argument("--momentum-days", default="10,20")
    parser.add_argument("--trend-returns", default="0.015,0.025")
    parser.add_argument("--hot-returns", default="0.08,0.12")
    parser.add_argument("--buy-dip-drawdowns", default="-0.06,-0.10")
    parser.add_argument("--min-hold-days", default="0,5")
    parser.add_argument("--output-prefix", default="results/group_a_plus_abm_agents_20260619")
    args = parser.parse_args()

    policy_signal, policy_signal_path = _load_policy_signal(_resolve(args.decision_pointer))
    golden_signal_path = _resolve(args.golden_signal)
    golden_signal = _load(golden_signal_path)
    defensive_weights = _weights_from_group_a_plus(policy_signal)
    golden_weights = _weights_from_group_a(golden_signal)
    prices = _load_prices(_resolve(args.db), list(TICKERS), args.start, args.end)
    chip_features = _load_chip_features(_resolve(args.db), prices.index, args.start, args.end)
    weights_by_regime = {
        "golden1": golden_weights,
        "group_a_plus_defensive": defensive_weights,
    }
    a207_events, a207_frame = _switch_returns(prices, chip_features, A207_RULE)
    ma20_events, ma20_frame = _switch_returns(prices, chip_features, MA20_RULE)
    base_curves = {
        "a207": _simulate_regime_curve(prices, a207_frame["regime"], weights_by_regime, args.initial_value),
        "ma20": _simulate_regime_curve(prices, ma20_frame["regime"], weights_by_regime, args.initial_value),
    }
    golden_returns = _single_regime_returns(prices, "golden1", weights_by_regime, args.initial_value)
    defensive_returns = _single_regime_returns(prices, "group_a_plus_defensive", weights_by_regime, args.initial_value)

    rows: list[dict[str, Any]] = []
    frames: dict[str, pd.DataFrame] = {}
    for risk_threshold in _parse_int_list(args.risk_thresholds):
        for low_risk_threshold in _parse_int_list(args.low_risk_thresholds):
            for momentum_days in _parse_int_list(args.momentum_days):
                for trend_return in _parse_float_list(args.trend_returns):
                    for hot_return in _parse_float_list(args.hot_returns):
                        for buy_dip_drawdown in _parse_float_list(args.buy_dip_drawdowns):
                            features = _abm_features(
                                prices,
                                chip_features,
                                risk_threshold,
                                low_risk_threshold,
                                momentum_days,
                                hot_return,
                                buy_dip_drawdown,
                                trend_return,
                            )
                            for fitness_window in _parse_int_list(args.fitness_windows):
                                for beta in _parse_float_list(args.betas):
                                    for demand_threshold in _parse_float_list(args.demand_thresholds):
                                        for min_hold_days in _parse_int_list(args.min_hold_days):
                                            for require_sync in (True, False):
                                                label = (
                                                    f"abm_fw{fitness_window}_b{int(beta*10):02d}"
                                                    f"_d{int(demand_threshold*100):02d}_r{risk_threshold}"
                                                    f"_lr{low_risk_threshold}_m{momentum_days}"
                                                    f"_tr{int(trend_return*1000):03d}_hot{int(hot_return*100):02d}"
                                                    f"_dip{int(abs(buy_dip_drawdown)*100):02d}"
                                                    f"_h{min_hold_days}_{'sync' if require_sync else 'all'}"
                                                )
                                                frame = _abm_regime(
                                                    features,
                                                    a207_frame["regime"],
                                                    golden_returns,
                                                    defensive_returns,
                                                    fitness_window,
                                                    beta,
                                                    demand_threshold,
                                                    min_hold_days,
                                                    require_sync,
                                                )
                                                curve = _simulate_regime_curve(
                                                    prices,
                                                    frame["regime"],
                                                    weights_by_regime,
                                                    args.initial_value,
                                                )
                                                force_defense_days = int((frame["abm_action"] == "force_defensive").sum())
                                                force_golden_days = int((frame["abm_action"] == "force_golden").sum())
                                                rows.append(
                                                    {
                                                        "variant": label,
                                                        **_metrics(curve, args.initial_value),
                                                        "fitness_window": fitness_window,
                                                        "beta": beta,
                                                        "demand_threshold": demand_threshold,
                                                        "risk_threshold": risk_threshold,
                                                        "low_risk_threshold": low_risk_threshold,
                                                        "momentum_days": momentum_days,
                                                        "trend_return": trend_return,
                                                        "hot_return": hot_return,
                                                        "buy_dip_drawdown": buy_dip_drawdown,
                                                        "min_hold_days": min_hold_days,
                                                        "require_technical_sync": require_sync,
                                                        "force_defense_days": force_defense_days,
                                                        "force_golden_days": force_golden_days,
                                                        "override_days": int((frame["regime"] != a207_frame["regime"]).sum()),
                                                        "defense_days": int((frame["regime"] == "group_a_plus_defensive").sum()),
                                                    }
                                                )
                                                frames[label] = frame

    summary = {name: _metrics(curve, args.initial_value) for name, curve in base_curves.items()}
    ranked = sorted(rows, key=lambda row: (row["sharpe_ratio"], row["max_drawdown"], row["final_value"]), reverse=True)
    best = ranked[0]
    report = {
        "experiment": "group_a_plus_abm_observable_agents",
        "method_note": (
            "Observable proxy for fundamentalist, momentum, and contrarian agents. "
            "Recent trailing agent payoff determines softmax fitness weights and aggregate demand."
        ),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "requested_window": {"start": args.start, "end": args.end},
        "actual_window": {"start": str(prices.index[0].date()), "end": str(prices.index[-1].date()), "rows": int(len(prices))},
        "inputs": {
            "policy_signal": str(policy_signal_path.relative_to(PROJECT_ROOT)),
            "golden_signal": str(golden_signal_path.relative_to(PROJECT_ROOT)),
        },
        "weights": {
            "golden1_0531_1m": _normalize(golden_weights),
            "group_a_plus_defensive_1m": _normalize(defensive_weights),
        },
        "rules": {"a207": asdict(A207_RULE), "ma20": asdict(MA20_RULE)},
        "events": {"a207": a207_events, "ma20": ma20_events},
        "summary": summary,
        "rows": rows,
        "best_by_sharpe": ranked[:10],
        "best": best,
    }

    prefix = Path(args.output_prefix)
    if not prefix.is_absolute():
        prefix = (PROJECT_ROOT / prefix).resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = prefix.with_suffix(".json")
    csv_path = prefix.with_suffix(".csv")
    curve_path = prefix.with_name(prefix.name + "_curve.csv")
    best_frame_path = prefix.with_name(prefix.name + "_best_frame.csv")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(base_curves).to_csv(curve_path, encoding="utf-8-sig")
    frames[best["variant"]].to_csv(best_frame_path, encoding="utf-8-sig")

    print(f"JSON: {json_path}")
    print(f"CSV: {csv_path}")
    print(f"Curve CSV: {curve_path}")
    print(f"Best frame: {best_frame_path}")
    print(f"Window: {report['actual_window']['start']} ~ {report['actual_window']['end']} ({report['actual_window']['rows']} rows)")
    for name in ("a207", "ma20"):
        metrics = summary[name]
        print(
            f"{name}: final={metrics['final_value']:,.0f}, sharpe={metrics['sharpe_ratio']:.3f}, "
            f"sortino={metrics['sortino_ratio']:.3f}, mdd={metrics['max_drawdown']:.2%}, starr={metrics['starr_ratio_5pct']:.4f}"
        )
    print(
        f"Best: {best['variant']} final={best['final_value']:,.0f}, sharpe={best['sharpe_ratio']:.3f}, "
        f"mdd={best['max_drawdown']:.2%}, overrides={best['override_days']}"
    )


if __name__ == "__main__":
    main()
