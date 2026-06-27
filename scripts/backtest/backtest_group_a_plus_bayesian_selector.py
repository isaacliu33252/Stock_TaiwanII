#!/usr/bin/env python3
"""Bayesian-style selector for GroupA+ switch rules.

The selector treats each switch rule as a model.  On each day it scores models
with only prior rolling returns, then uses the highest posterior-like score to
choose that day's Golden1/GroupA+ defensive regime.
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

DEFAULT_RULES = {
    "ma20_dd7_hold5": SwitchRule("ma20_dd7_hold5", 20, -0.03, 0.01, 20, -0.07, 5, 5),
    "risk_ma90_dd12_total6_hold5": SwitchRule(
        "risk_ma90_dd12_total6_hold5",
        90,
        -0.02,
        0.01,
        90,
        -0.12,
        5,
        5,
        0,
        None,
        0,
        None,
        6,
        6,
    ),
    "risk_ma75_dd11_total6_hold5_eg0175_xg020": SwitchRule(
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
    ),
}


def _score_window(returns: pd.Series) -> float:
    returns = returns.dropna()
    if len(returns) < 20:
        return 0.0
    annual_return = float(returns.mean() * 252)
    downside = returns[returns < 0.0]
    downside_deviation = float(math.sqrt(downside.pow(2).mean()) * math.sqrt(252)) if len(downside) else 0.0
    sortino = annual_return / downside_deviation if downside_deviation > 0 else 0.0
    curve = (1.0 + returns).cumprod()
    max_drawdown = float((curve / curve.cummax() - 1.0).min())
    var_5 = float(returns.quantile(0.05))
    etl_5 = float(returns[returns <= var_5].mean()) if len(returns[returns <= var_5]) else 0.0
    return float(sortino + 1.2 * annual_return + 2.0 * max_drawdown + 6.0 * etl_5)


def _posterior_scores(candidate_returns: pd.DataFrame, lookback: int, temperature: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    score_rows: list[dict[str, float]] = []
    weight_rows: list[dict[str, float]] = []
    for idx in range(len(candidate_returns)):
        if idx == 0:
            scores = {name: 0.0 for name in candidate_returns.columns}
        else:
            start = max(0, idx - lookback)
            window = candidate_returns.iloc[start:idx]
            scores = {name: _score_window(window[name]) for name in candidate_returns.columns}
        max_score = max(scores.values()) if scores else 0.0
        exp_scores = {
            name: math.exp((score - max_score) / max(float(temperature), 1e-9))
            for name, score in scores.items()
        }
        denom = sum(exp_scores.values()) or 1.0
        score_rows.append(scores)
        weight_rows.append({name: value / denom for name, value in exp_scores.items()})
    scores_df = pd.DataFrame(score_rows, index=candidate_returns.index)
    weights_df = pd.DataFrame(weight_rows, index=candidate_returns.index)
    return scores_df, weights_df


def _selector_regime(
    regime_by_rule: dict[str, pd.Series],
    scores: pd.DataFrame,
    posterior_weights: pd.DataFrame,
    default_rule: str,
    min_history: int,
    switch_score_edge: float,
) -> pd.DataFrame:
    dates = posterior_weights.index
    selected_rules: list[str] = []
    selected_regimes: list[str] = []
    defensive_probs: list[float] = []
    for idx, dt in enumerate(dates):
        if idx < min_history:
            selected_rule = default_rule
        else:
            best_rule = str(posterior_weights.loc[dt].idxmax())
            best_score = float(scores.loc[dt, best_rule])
            default_score = float(scores.loc[dt, default_rule])
            selected_rule = best_rule if best_score >= default_score + switch_score_edge else default_rule
        defensive_prob = 0.0
        for name, regimes in regime_by_rule.items():
            if str(regimes.loc[dt]) == "group_a_plus_defensive":
                defensive_prob += float(posterior_weights.loc[dt, name])
        selected_rules.append(selected_rule)
        selected_regimes.append(str(regime_by_rule[selected_rule].loc[dt]))
        defensive_probs.append(defensive_prob)
    return pd.DataFrame(
        {
            "selected_rule": selected_rules,
            "regime": selected_regimes,
            "posterior_defensive_probability": defensive_probs,
        },
        index=dates,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision-pointer", default=str(DEFAULT_DECISION_POINTER))
    parser.add_argument("--golden-signal", default=str(DEFAULT_GOLDEN_SIGNAL))
    parser.add_argument("--start", default="2020-01-02")
    parser.add_argument("--end", default="2026-06-18")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--lookback", type=int, default=126)
    parser.add_argument("--min-history", type=int, default=126)
    parser.add_argument("--temperature", type=float, default=0.35)
    parser.add_argument(
        "--switch-score-edge",
        type=float,
        default=0.0,
        help="Require the best alternative score to exceed the default rule by this amount before switching models.",
    )
    parser.add_argument(
        "--default-rule",
        default="risk_ma75_dd11_total6_hold5_eg0175_xg020",
        choices=sorted(DEFAULT_RULES),
    )
    parser.add_argument("--output-prefix", default="results/group_a_plus_bayesian_selector_20260619")
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

    curves = pd.DataFrame(index=prices.index)
    regimes: dict[str, pd.Series] = {}
    events_by_rule: dict[str, list[dict[str, Any]]] = {}
    for name, rule in DEFAULT_RULES.items():
        events, regime_frame = _switch_returns(prices, chip_features, rule)
        events_by_rule[name] = events
        regimes[name] = regime_frame["regime"]
        curves[f"switch_{name}"] = _simulate_regime_curve(
            prices,
            regime_frame["regime"],
            weights_by_regime,
            args.initial_value,
        )

    curves["golden1_0531_1m"] = _simulate_regime_curve(
        prices,
        pd.Series("golden1", index=prices.index),
        weights_by_regime,
        args.initial_value,
    )
    curves["group_a_plus_defensive_1m"] = _simulate_regime_curve(
        prices,
        pd.Series("group_a_plus_defensive", index=prices.index),
        weights_by_regime,
        args.initial_value,
    )

    candidate_returns = pd.DataFrame(
        {name: curves[f"switch_{name}"].pct_change().fillna(0.0) for name in DEFAULT_RULES},
        index=prices.index,
    )
    scores, posterior_weights = _posterior_scores(candidate_returns, args.lookback, args.temperature)
    selector_frame = _selector_regime(
        regimes,
        scores,
        posterior_weights,
        args.default_rule,
        args.min_history,
        args.switch_score_edge,
    )
    curves["bayesian_selector_map"] = _simulate_regime_curve(
        prices,
        selector_frame["regime"],
        weights_by_regime,
        args.initial_value,
    )

    selected_changes = selector_frame["selected_rule"].ne(selector_frame["selected_rule"].shift()).fillna(True)
    selector_events = [
        {
            "date": str(dt.date()),
            "selected_rule": str(row["selected_rule"]),
            "regime": str(row["regime"]),
            "posterior_defensive_probability": float(row["posterior_defensive_probability"]),
        }
        for dt, row in selector_frame[selected_changes].iterrows()
    ]

    summary = {name: _metrics(curves[name], args.initial_value) for name in curves.columns}
    report = {
        "experiment": "group_a_plus_bayesian_style_selector",
        "method_note": (
            "Each switch rule is treated as a model. Posterior-like weights are computed from prior rolling "
            "Sortino, annual return, drawdown, and ETL utility; the MAP rule supplies the daily regime."
        ),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "requested_window": {"start": args.start, "end": args.end},
        "actual_window": {"start": str(prices.index[0].date()), "end": str(prices.index[-1].date()), "rows": int(len(prices))},
        "parameters": {
            "lookback": int(args.lookback),
            "min_history": int(args.min_history),
            "temperature": float(args.temperature),
            "default_rule": args.default_rule,
            "switch_score_edge": float(args.switch_score_edge),
        },
        "inputs": {
            "policy_signal": str(policy_signal_path.relative_to(PROJECT_ROOT)),
            "golden_signal": str(golden_signal_path.relative_to(PROJECT_ROOT)),
        },
        "weights": {
            "golden1_0531_1m": _normalize(golden_weights),
            "group_a_plus_defensive_1m": _normalize(defensive_weights),
        },
        "rules": {name: asdict(rule) for name, rule in DEFAULT_RULES.items()},
        "events_by_rule": events_by_rule,
        "selector_events": selector_events,
        "summary": summary,
        "recommended": {
            "variant": "bayesian_selector_map",
            "metrics": summary["bayesian_selector_map"],
            "rule_usage_days": selector_frame["selected_rule"].value_counts().to_dict(),
            "defense_days": int((selector_frame["regime"] == "group_a_plus_defensive").sum()),
            "defense_day_ratio": float((selector_frame["regime"] == "group_a_plus_defensive").mean()),
        },
    }

    prefix = Path(args.output_prefix)
    if not prefix.is_absolute():
        prefix = (PROJECT_ROOT / prefix).resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = prefix.with_suffix(".json")
    csv_path = prefix.with_suffix(".csv")
    curve_path = prefix.with_name(prefix.name + "_curve.csv")
    selector_path = prefix.with_name(prefix.name + "_selector.csv")
    weights_path = prefix.with_name(prefix.name + "_posterior_weights.csv")
    scores_path = prefix.with_name(prefix.name + "_scores.csv")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame([{"variant": name, **metrics} for name, metrics in summary.items()]).to_csv(
        csv_path,
        index=False,
        encoding="utf-8-sig",
    )
    curves.to_csv(curve_path, encoding="utf-8-sig")
    selector_frame.to_csv(selector_path, encoding="utf-8-sig")
    posterior_weights.to_csv(weights_path, encoding="utf-8-sig")
    scores.to_csv(scores_path, encoding="utf-8-sig")

    print(f"JSON: {json_path}")
    print(f"CSV: {csv_path}")
    print(f"Selector CSV: {selector_path}")
    print(f"Posterior weights CSV: {weights_path}")
    print(f"Window: {report['actual_window']['start']} ~ {report['actual_window']['end']} ({report['actual_window']['rows']} rows)")
    for name in ("golden1_0531_1m", "group_a_plus_defensive_1m", "switch_ma20_dd7_hold5", "switch_risk_ma75_dd11_total6_hold5_eg0175_xg020", "bayesian_selector_map"):
        metrics = summary[name]
        print(
            f"{name}: final={metrics['final_value']:,.0f}, return={metrics['total_return']:.2%}, "
            f"sharpe={metrics['sharpe_ratio']:.3f}, sortino={metrics['sortino_ratio']:.3f}, "
            f"mdd={metrics['max_drawdown']:.2%}, starr={metrics['starr_ratio_5pct']:.4f}"
        )
    print(f"Rule usage: {report['recommended']['rule_usage_days']}")


if __name__ == "__main__":
    main()
