#!/usr/bin/env python3
"""Empirical copula tail-dependence tests for GroupA+.

Research-only implementation inspired by Copula Methods in Finance.  It uses
rolling empirical CDF ranks to estimate lower-tail co-movement among GroupA+
ETFs, then tests tail-dependence selectors/guards against A20.7.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

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


def _rolling_percentile_rank(series: pd.Series, window: int) -> pd.Series:
    def rank_last(values: pd.Series) -> float:
        last = float(values.iloc[-1])
        return float((values <= last).mean())

    return series.rolling(window, min_periods=max(40, window // 3)).apply(rank_last, raw=False).fillna(0.5)


def _copula_tail_features(prices: pd.DataFrame, window: int, tail_q: float) -> pd.DataFrame:
    returns = prices[list(TICKERS)].pct_change().fillna(0.0)
    ranks = pd.DataFrame(index=returns.index)
    for ticker in TICKERS:
        ranks[ticker] = _rolling_percentile_rank(returns[ticker], window)

    equity_tickers = ["0050.TW", "00631L.TW", "00632R.TW"]
    lower_tail_count = (ranks[equity_tickers] <= tail_q).sum(axis=1)
    all_equity_tail = lower_tail_count >= 2
    levered_tail = (ranks["0050.TW"] <= tail_q) & (ranks["00631L.TW"] <= tail_q)
    inverse_not_helping = (returns["0050.TW"] < 0.0) & (returns["00631L.TW"] < 0.0) & (returns["00632R.TW"] <= 0.0)
    bond_not_helping = (returns["0050.TW"] < 0.0) & (returns["00679B.TWO"] <= 0.0)
    joint_tail_score = (
        all_equity_tail.astype(int)
        + levered_tail.astype(int)
        + inverse_not_helping.astype(int)
        + bond_not_helping.astype(int)
    )
    joint_tail_intensity = (tail_q - ranks[equity_tickers].min(axis=1)).clip(lower=0.0) / max(tail_q, 1e-9)
    rolling_joint_tail_freq = all_equity_tail.astype(float).rolling(window, min_periods=max(20, window // 4)).mean().fillna(0.0)
    return pd.DataFrame(
        {
            "return_0050_1d": returns["0050.TW"],
            "return_0050_5d": prices["0050.TW"].pct_change(5).fillna(0.0),
            "rank_0050": ranks["0050.TW"],
            "rank_00631l": ranks["00631L.TW"],
            "rank_00632r": ranks["00632R.TW"],
            "rank_00679b": ranks["00679B.TWO"],
            "lower_tail_count": lower_tail_count,
            "all_equity_tail": all_equity_tail.astype(int),
            "levered_tail": levered_tail.astype(int),
            "inverse_not_helping": inverse_not_helping.astype(int),
            "bond_not_helping": bond_not_helping.astype(int),
            "joint_tail_score": joint_tail_score,
            "joint_tail_intensity": joint_tail_intensity,
            "rolling_joint_tail_freq": rolling_joint_tail_freq,
        },
        index=prices.index,
    ).fillna(0.0)


def _copula_selector_regime(
    prices: pd.DataFrame,
    a207_regime: pd.Series,
    ma20_regime: pd.Series,
    window: int,
    tail_q: float,
    min_score: int,
    require_negative_5d: bool,
) -> pd.DataFrame:
    features = _copula_tail_features(prices, window, tail_q)
    stress = features["joint_tail_score"] >= min_score
    if require_negative_5d:
        stress = stress & (features["return_0050_5d"] < 0.0)
    selected_rule = pd.Series("a207", index=prices.index)
    selected_rule.loc[stress] = "ma20"
    regime = a207_regime.copy()
    regime.loc[stress] = ma20_regime.loc[stress]
    frame = features.copy()
    frame["selected_rule"] = selected_rule
    frame["regime"] = regime
    return frame


def _copula_guard_regime(
    prices: pd.DataFrame,
    a207_regime: pd.Series,
    window: int,
    tail_q: float,
    min_score: int,
    min_hold_days: int,
    exit_score: int,
) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    features = _copula_tail_features(prices, window, tail_q)
    in_guard = False
    hold_days = 0
    regimes: list[str] = []
    events: list[dict[str, Any]] = []
    for dt, row in features.iterrows():
        enter = int(row["joint_tail_score"]) >= min_score and float(row["return_0050_5d"]) < 0.0
        exit_ = int(row["joint_tail_score"]) <= exit_score and float(row["return_0050_5d"]) >= 0.0
        if in_guard:
            hold_days += 1
            if hold_days >= min_hold_days and exit_:
                in_guard = False
                hold_days = 0
                events.append(
                    {
                        "date": str(dt.date()),
                        "action": "exit_copula_guard",
                        "joint_tail_score": int(row["joint_tail_score"]),
                        "joint_tail_intensity": float(row["joint_tail_intensity"]),
                        "return_0050_5d": float(row["return_0050_5d"]),
                    }
                )
        elif enter:
            in_guard = True
            hold_days = 1
            events.append(
                {
                    "date": str(dt.date()),
                    "action": "enter_copula_guard",
                    "joint_tail_score": int(row["joint_tail_score"]),
                    "joint_tail_intensity": float(row["joint_tail_intensity"]),
                    "return_0050_5d": float(row["return_0050_5d"]),
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
    parser.add_argument("--output-prefix", default="results/group_a_plus_copula_tail_20260619")
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
    curves = pd.DataFrame(index=prices.index)
    curves["a207"] = _simulate_regime_curve(prices, a207_frame["regime"], weights_by_regime, args.initial_value)
    curves["ma20"] = _simulate_regime_curve(prices, ma20_frame["regime"], weights_by_regime, args.initial_value)

    selector_rows: list[dict[str, Any]] = []
    selector_frames: dict[str, pd.DataFrame] = {}
    for window in (60, 90, 126):
        for tail_q in (0.05, 0.10, 0.15):
            for min_score in (1, 2, 3):
                for require_negative in (True, False):
                    label = f"copula_selector_w{window}_q{int(tail_q * 100):02d}_s{min_score}_{'neg5d' if require_negative else 'any'}"
                    frame = _copula_selector_regime(
                        prices,
                        a207_frame["regime"],
                        ma20_frame["regime"],
                        window,
                        tail_q,
                        min_score,
                        require_negative,
                    )
                    curves[label] = _simulate_regime_curve(prices, frame["regime"], weights_by_regime, args.initial_value)
                    selector_frames[label] = frame
                    selector_rows.append(
                        {
                            "variant": label,
                            **_metrics(curves[label], args.initial_value),
                            "window": window,
                            "tail_q": tail_q,
                            "min_score": min_score,
                            "require_negative_5d": require_negative,
                            "ma20_days": int((frame["selected_rule"] == "ma20").sum()),
                            "defense_days": int((frame["regime"] == "group_a_plus_defensive").sum()),
                        }
                    )

    guard_rows: list[dict[str, Any]] = []
    guard_events: dict[str, list[dict[str, Any]]] = {}
    guard_frames: dict[str, pd.DataFrame] = {}
    for window in (60, 90, 126):
        for tail_q in (0.05, 0.10, 0.15):
            for min_score in (2, 3):
                label = f"copula_guard_w{window}_q{int(tail_q * 100):02d}_s{min_score}"
                events, frame = _copula_guard_regime(
                    prices,
                    a207_frame["regime"],
                    window,
                    tail_q,
                    min_score,
                    min_hold_days=5,
                    exit_score=0,
                )
                curves[label] = _simulate_regime_curve(prices, frame["regime"], weights_by_regime, args.initial_value)
                guard_events[label] = events
                guard_frames[label] = frame
                guard_rows.append(
                    {
                        "variant": label,
                        **_metrics(curves[label], args.initial_value),
                        "window": window,
                        "tail_q": tail_q,
                        "min_score": min_score,
                        "event_count": len(events),
                        "defense_days": int((frame["regime"] == "group_a_plus_defensive").sum()),
                    }
                )

    summary = {name: _metrics(curves[name], args.initial_value) for name in curves.columns}
    selector_ranked = sorted(selector_rows, key=lambda row: (row["sharpe_ratio"], row["max_drawdown"], row["final_value"]), reverse=True)
    guard_ranked = sorted(guard_rows, key=lambda row: (row["sharpe_ratio"], row["max_drawdown"], row["final_value"]), reverse=True)
    report = {
        "experiment": "group_a_plus_copula_tail_dependence",
        "method_note": (
            "Rolling empirical CDF ranks approximate lower-tail copula dependence among GroupA+ ETFs. "
            "No parametric copula is fitted; this is a deterministic proxy suitable for backtest screening."
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
        "events": {"a207": a207_events, "ma20": ma20_events, "copula_guard": guard_events},
        "summary": summary,
        "selector_rows": selector_rows,
        "guard_rows": guard_rows,
        "best_selector_by_sharpe": selector_ranked[:5],
        "best_guard_by_sharpe": guard_ranked[:5],
    }

    prefix = Path(args.output_prefix)
    if not prefix.is_absolute():
        prefix = (PROJECT_ROOT / prefix).resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = prefix.with_suffix(".json")
    csv_path = prefix.with_suffix(".csv")
    curve_path = prefix.with_name(prefix.name + "_curve.csv")
    selector_path = prefix.with_name(prefix.name + "_selector_rows.csv")
    guard_path = prefix.with_name(prefix.name + "_guard_rows.csv")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame([{"variant": name, **metrics} for name, metrics in summary.items()]).to_csv(csv_path, index=False, encoding="utf-8-sig")
    curves.to_csv(curve_path, encoding="utf-8-sig")
    pd.DataFrame(selector_rows).to_csv(selector_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(guard_rows).to_csv(guard_path, index=False, encoding="utf-8-sig")
    if selector_ranked:
        selector_frames[selector_ranked[0]["variant"]].to_csv(prefix.with_name(prefix.name + "_best_selector_frame.csv"), encoding="utf-8-sig")
    if guard_ranked:
        guard_frames[guard_ranked[0]["variant"]].to_csv(prefix.with_name(prefix.name + "_best_guard_frame.csv"), encoding="utf-8-sig")

    print(f"JSON: {json_path}")
    print(f"CSV: {csv_path}")
    print(f"Selector rows: {selector_path}")
    print(f"Guard rows: {guard_path}")
    print(f"Window: {report['actual_window']['start']} ~ {report['actual_window']['end']} ({report['actual_window']['rows']} rows)")
    for name in ("a207", "ma20"):
        metrics = summary[name]
        print(
            f"{name}: final={metrics['final_value']:,.0f}, sharpe={metrics['sharpe_ratio']:.3f}, "
            f"sortino={metrics['sortino_ratio']:.3f}, mdd={metrics['max_drawdown']:.2%}, starr={metrics['starr_ratio_5pct']:.4f}"
        )
    best_selector = selector_ranked[0]
    print(
        f"Best selector: {best_selector['variant']} final={best_selector['final_value']:,.0f}, "
        f"sharpe={best_selector['sharpe_ratio']:.3f}, mdd={best_selector['max_drawdown']:.2%}, ma20_days={best_selector['ma20_days']}"
    )
    best_guard = guard_ranked[0]
    print(
        f"Best guard: {best_guard['variant']} final={best_guard['final_value']:,.0f}, "
        f"sharpe={best_guard['sharpe_ratio']:.3f}, mdd={best_guard['max_drawdown']:.2%}, events={best_guard['event_count']}"
    )


if __name__ == "__main__":
    main()
