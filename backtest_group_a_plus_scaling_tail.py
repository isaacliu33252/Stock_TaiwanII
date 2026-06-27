#!/usr/bin/env python3
"""Scaling / power-law tail proxy tests for GroupA+.

Research-only implementation inspired by scaling in financial time series.  It
uses rolling Hill-style left-tail index and multi-horizon tail breaches as
possible A20.7 confirmation/guard overlays.
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


def _hill_left_tail_alpha(losses: pd.Series, tail_count: int) -> float:
    values = losses.dropna()
    values = values[values > 0.0].sort_values(ascending=False)
    if len(values) <= tail_count or tail_count < 2:
        return 0.0
    top = values.iloc[:tail_count]
    threshold = float(values.iloc[tail_count])
    if threshold <= 0:
        return 0.0
    hill_inv = float((top / threshold).map(math.log).mean())
    return float(1.0 / hill_inv) if hill_inv > 0 else 0.0


def _hill_left_tail_alpha_array(values: np.ndarray, tail_count: int) -> float:
    positive = values[np.isfinite(values) & (values > 0.0)]
    if len(positive) <= tail_count or tail_count < 2:
        return 0.0
    ordered = np.sort(positive)[::-1]
    top = ordered[:tail_count]
    threshold = float(ordered[tail_count])
    if threshold <= 0:
        return 0.0
    hill_inv = float(np.log(top / threshold).mean())
    return float(1.0 / hill_inv) if hill_inv > 0 else 0.0


def _rolling_hill_alpha(losses: pd.Series, window: int, tail_count: int) -> pd.Series:
    return losses.rolling(window, min_periods=max(60, window // 2)).apply(
        lambda values: _hill_left_tail_alpha_array(values, tail_count),
        raw=True,
    ).fillna(0.0)


def _scaling_tail_features(prices: pd.DataFrame, window: int, tail_count: int, quantile: float) -> pd.DataFrame:
    close = prices["0050.TW"].astype(float)
    ret_1d = close.pct_change().fillna(0.0)
    ret_2d = close.pct_change(2).fillna(0.0)
    ret_4d = close.pct_change(4).fillna(0.0)
    losses = (-ret_1d).clip(lower=0.0)
    hill_alpha = _rolling_hill_alpha(losses, window, tail_count)
    alpha_base = hill_alpha.rolling(252, min_periods=60).median().replace(0.0, math.nan)
    alpha_ratio = (hill_alpha / alpha_base).replace([math.inf, -math.inf], math.nan).fillna(1.0)
    var_1d = ret_1d.rolling(window, min_periods=max(40, window // 3)).quantile(quantile).fillna(0.0)
    var_2d = ret_2d.rolling(window, min_periods=max(40, window // 3)).quantile(quantile).fillna(0.0)
    var_4d = ret_4d.rolling(window, min_periods=max(40, window // 3)).quantile(quantile).fillna(0.0)
    breach_1d = ret_1d <= var_1d
    breach_2d = ret_2d <= var_2d
    breach_4d = ret_4d <= var_4d
    multi_scale_breach_score = breach_1d.astype(int) + breach_2d.astype(int) + breach_4d.astype(int)
    tail_breach_cluster = breach_1d.astype(float).rolling(20, min_periods=5).sum().fillna(0.0)
    return pd.DataFrame(
        {
            "return_0050_1d": ret_1d,
            "return_0050_2d": ret_2d,
            "return_0050_4d": ret_4d,
            "return_0050_5d": close.pct_change(5).fillna(0.0),
            "hill_left_tail_alpha": hill_alpha,
            "hill_alpha_ratio": alpha_ratio,
            "var_1d": var_1d,
            "var_2d": var_2d,
            "var_4d": var_4d,
            "breach_1d": breach_1d.astype(int),
            "breach_2d": breach_2d.astype(int),
            "breach_4d": breach_4d.astype(int),
            "multi_scale_breach_score": multi_scale_breach_score,
            "tail_breach_cluster_20d": tail_breach_cluster,
        },
        index=prices.index,
    ).fillna(0.0)


def _selector_regime(
    features: pd.DataFrame,
    a207_regime: pd.Series,
    ma20_regime: pd.Series,
    min_score: int,
    max_alpha: float,
    min_cluster: int,
    require_negative_5d: bool,
) -> pd.DataFrame:
    stress = (
        (features["multi_scale_breach_score"] >= min_score)
        & ((features["hill_left_tail_alpha"] <= max_alpha) | (features["hill_left_tail_alpha"] == 0.0))
        & (features["tail_breach_cluster_20d"] >= min_cluster)
    )
    if require_negative_5d:
        stress = stress & (features["return_0050_5d"] < 0.0)
    frame = features.copy()
    frame["scaling_tail_trigger"] = stress.astype(int)
    frame["regime"] = a207_regime.copy()
    frame.loc[stress, "regime"] = ma20_regime.loc[stress]
    return frame


def _guard_regime(
    features: pd.DataFrame,
    a207_regime: pd.Series,
    min_score: int,
    max_alpha: float,
    min_cluster: int,
    min_hold_days: int,
) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    in_guard = False
    hold_days = 0
    regimes: list[str] = []
    events: list[dict[str, Any]] = []
    for dt, row in features.iterrows():
        stress = (
            int(row["multi_scale_breach_score"]) >= min_score
            and (float(row["hill_left_tail_alpha"]) <= max_alpha or float(row["hill_left_tail_alpha"]) == 0.0)
            and int(row["tail_breach_cluster_20d"]) >= min_cluster
            and float(row["return_0050_5d"]) < 0.0
        )
        exit_ = int(row["multi_scale_breach_score"]) == 0 and float(row["return_0050_5d"]) >= 0.0
        if in_guard:
            hold_days += 1
            if hold_days >= min_hold_days and exit_:
                in_guard = False
                hold_days = 0
                events.append(
                    {
                        "date": str(dt.date()),
                        "action": "exit_scaling_tail_guard",
                        "hill_left_tail_alpha": float(row["hill_left_tail_alpha"]),
                        "multi_scale_breach_score": int(row["multi_scale_breach_score"]),
                        "tail_breach_cluster_20d": int(row["tail_breach_cluster_20d"]),
                    }
                )
        elif stress:
            in_guard = True
            hold_days = 1
            events.append(
                {
                    "date": str(dt.date()),
                    "action": "enter_scaling_tail_guard",
                    "hill_left_tail_alpha": float(row["hill_left_tail_alpha"]),
                    "multi_scale_breach_score": int(row["multi_scale_breach_score"]),
                    "tail_breach_cluster_20d": int(row["tail_breach_cluster_20d"]),
                }
            )
        regimes.append("group_a_plus_defensive" if in_guard else str(a207_regime.loc[dt]))
    frame = features.copy()
    frame["regime"] = regimes
    return events, frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision-pointer", default=str(DEFAULT_DECISION_POINTER))
    parser.add_argument("--golden-signal", default=str(DEFAULT_GOLDEN_SIGNAL))
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-06-18")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--windows", default="126,252,378")
    parser.add_argument("--tail-counts", default="8,12,16")
    parser.add_argument("--quantiles", default="0.03,0.05,0.10")
    parser.add_argument("--min-scores", default="1,2,3")
    parser.add_argument("--max-alphas", default="2.2,2.6,3.0,3.5")
    parser.add_argument("--min-clusters", default="1,2,3")
    parser.add_argument("--output-prefix", default="results/group_a_plus_scaling_tail_20260619")
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

    selector_rows: list[dict[str, Any]] = []
    guard_rows: list[dict[str, Any]] = []
    guard_events: dict[str, list[dict[str, Any]]] = {}
    frames: dict[str, pd.DataFrame] = {}
    for window in _parse_int_list(args.windows):
        for tail_count in _parse_int_list(args.tail_counts):
            for quantile in _parse_float_list(args.quantiles):
                features = _scaling_tail_features(prices, window, tail_count, quantile)
                for min_score in _parse_int_list(args.min_scores):
                    for max_alpha in _parse_float_list(args.max_alphas):
                        for min_cluster in _parse_int_list(args.min_clusters):
                            for require_negative in (True, False):
                                label = (
                                    f"scaling_selector_w{window}_k{tail_count}_q{int(quantile*100):02d}"
                                    f"_s{min_score}_a{int(max_alpha*10):02d}_c{min_cluster}"
                                    f"_{'neg5d' if require_negative else 'any'}"
                                )
                                frame = _selector_regime(
                                    features,
                                    a207_frame["regime"],
                                    ma20_frame["regime"],
                                    min_score,
                                    max_alpha,
                                    min_cluster,
                                    require_negative,
                                )
                                curve = _simulate_regime_curve(prices, frame["regime"], weights_by_regime, args.initial_value)
                                frames[label] = frame
                                selector_rows.append(
                                    {
                                        "variant": label,
                                        **_metrics(curve, args.initial_value),
                                        "window": window,
                                        "tail_count": tail_count,
                                        "quantile": quantile,
                                        "min_score": min_score,
                                        "max_alpha": max_alpha,
                                        "min_cluster": min_cluster,
                                        "require_negative_5d": require_negative,
                                        "trigger_days": int(frame["scaling_tail_trigger"].sum()),
                                        "defense_days": int((frame["regime"] == "group_a_plus_defensive").sum()),
                                    }
                                )
                            guard_label = (
                                f"scaling_guard_w{window}_k{tail_count}_q{int(quantile*100):02d}"
                                f"_s{min_score}_a{int(max_alpha*10):02d}_c{min_cluster}"
                            )
                            events, guard_frame = _guard_regime(
                                features,
                                a207_frame["regime"],
                                min_score,
                                max_alpha,
                                min_cluster,
                                min_hold_days=5,
                            )
                            guard_curve = _simulate_regime_curve(
                                prices,
                                guard_frame["regime"],
                                weights_by_regime,
                                args.initial_value,
                            )
                            frames[guard_label] = guard_frame
                            guard_events[guard_label] = events
                            guard_rows.append(
                                    {
                                        "variant": guard_label,
                                        **_metrics(guard_curve, args.initial_value),
                                    "window": window,
                                    "tail_count": tail_count,
                                    "quantile": quantile,
                                    "min_score": min_score,
                                    "max_alpha": max_alpha,
                                    "min_cluster": min_cluster,
                                    "event_count": len(events),
                                    "defense_days": int((guard_frame["regime"] == "group_a_plus_defensive").sum()),
                                }
                            )

    summary = {name: _metrics(curve, args.initial_value) for name, curve in base_curves.items()}
    rows = selector_rows + guard_rows
    ranked = sorted(rows, key=lambda row: (row["sharpe_ratio"], row["max_drawdown"], row["final_value"]), reverse=True)
    best = ranked[0]
    report = {
        "experiment": "group_a_plus_scaling_tail_proxy",
        "method_note": (
            "Rolling Hill-style left-tail alpha and multi-horizon tail breaches approximate power-law/scaling stress. "
            "This is a deterministic screening proxy, not a fitted multifractal model."
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
        "events": {"a207": a207_events, "ma20": ma20_events, "scaling_guard": guard_events},
        "summary": summary,
        "selector_rows": selector_rows,
        "guard_rows": guard_rows,
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
        f"mdd={best['max_drawdown']:.2%}"
    )


if __name__ == "__main__":
    main()
