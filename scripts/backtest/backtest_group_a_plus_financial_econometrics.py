#!/usr/bin/env python3
"""Financial econometrics style GARCH proxy tests for GroupA+.

This is a research-only implementation inspired by conditional
heteroskedasticity/GARCH ideas.  It avoids optional packages and uses a fixed
GARCH(1,1)-style recursion as a volatility-state proxy.
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


def _garch_proxy_vol(
    returns: pd.Series,
    alpha: float = 0.08,
    beta: float = 0.90,
    floor_window: int = 252,
) -> pd.Series:
    returns = returns.fillna(0.0).astype(float)
    unconditional_var = float(returns.rolling(floor_window, min_periods=40).var().median())
    if not math.isfinite(unconditional_var) or unconditional_var <= 0:
        unconditional_var = float(returns.var()) if float(returns.var()) > 0 else 1e-8
    omega = max(unconditional_var * max(1.0 - alpha - beta, 1e-6), 1e-12)
    variance = []
    prev_var = unconditional_var
    prev_ret = 0.0
    for ret in returns:
        next_var = omega + alpha * prev_ret * prev_ret + beta * prev_var
        next_var = max(float(next_var), 1e-12)
        variance.append(next_var)
        prev_var = next_var
        prev_ret = float(ret)
    return pd.Series(variance, index=returns.index).pow(0.5) * math.sqrt(252)


def _garch_proxy_vol_downside(
    returns: pd.Series,
    alpha: float = 0.08,
    beta: float = 0.90,
    floor_window: int = 252,
) -> pd.Series:
    """Downside-only variant of _garch_proxy_vol.

    Follows Wang & Yan (2021, J. Banking & Finance) "Downside risk and the
    performance of volatility-managed portfolios": the shock term only fires
    on negative-return days, so up days only decay the variance state toward
    baseline rather than reinforcing it -- the same asymmetry as their daily
    exponential-smoothing downside volatility estimator (Section 3.5.4),
    adapted to this module's existing GARCH(1,1)-style recursion so it plugs
    into the same ratio/percentile/regime-gate plumbing as the symmetric
    proxy. Research-only; not wired into any selector/guard/gate yet.
    """
    returns = returns.fillna(0.0).astype(float)
    unconditional_var = float(returns.rolling(floor_window, min_periods=40).var().median())
    if not math.isfinite(unconditional_var) or unconditional_var <= 0:
        unconditional_var = float(returns.var()) if float(returns.var()) > 0 else 1e-8
    omega = max(unconditional_var * max(1.0 - alpha - beta, 1e-6), 1e-12)
    variance = []
    prev_var = unconditional_var
    prev_ret = 0.0
    for ret in returns:
        shock = alpha * prev_ret * prev_ret if prev_ret < 0.0 else 0.0
        next_var = omega + shock + beta * prev_var
        next_var = max(float(next_var), 1e-12)
        variance.append(next_var)
        prev_var = next_var
        prev_ret = float(ret)
    return pd.Series(variance, index=returns.index).pow(0.5) * math.sqrt(252)


def _garch_features(prices: pd.DataFrame, chip_features: pd.DataFrame) -> pd.DataFrame:
    base_features = _regime_features(prices, A207_RULE, chip_features)
    close = prices["0050.TW"].astype(float)
    returns = close.pct_change().fillna(0.0)
    garch_vol = _garch_proxy_vol(returns)
    garch_base = garch_vol.rolling(252, min_periods=60).median()
    garch_ratio = (garch_vol / garch_base.replace(0.0, math.nan)).replace([math.inf, -math.inf], math.nan).fillna(1.0)
    garch_percentile = garch_vol.rolling(252, min_periods=60).rank(pct=True).fillna(0.5)
    garch_vol_downside = _garch_proxy_vol_downside(returns)
    garch_downside_base = garch_vol_downside.rolling(252, min_periods=60).median()
    garch_downside_ratio = (
        (garch_vol_downside / garch_downside_base.replace(0.0, math.nan))
        .replace([math.inf, -math.inf], math.nan)
        .fillna(1.0)
    )
    garch_downside_percentile = garch_vol_downside.rolling(252, min_periods=60).rank(pct=True).fillna(0.5)
    frame = pd.DataFrame(
        {
            "return_0050_1d": returns,
            "return_0050_5d": close.pct_change(5).fillna(0.0),
            "garch_proxy_vol_0050": garch_vol,
            "garch_proxy_vol_ratio": garch_ratio,
            "garch_proxy_vol_percentile": garch_percentile,
            "garch_proxy_vol_downside_0050": garch_vol_downside,
            "garch_proxy_vol_downside_ratio": garch_downside_ratio,
            "garch_proxy_vol_downside_percentile": garch_downside_percentile,
            "ma_gap": base_features["ma_gap"],
            "drawdown": base_features["drawdown"],
            "exit_momentum": base_features["exit_momentum"],
            "total_risk_score": base_features["total_risk_score"],
            "chip_score": base_features["chip_score"],
            "derivative_score": base_features["derivative_score"],
        },
        index=prices.index,
    )
    return frame.fillna(0.0)


def _garch_selector_regime(
    prices: pd.DataFrame,
    chip_features: pd.DataFrame,
    a207_regime: pd.Series,
    ma20_regime: pd.Series,
    ratio_threshold: float,
    percentile_threshold: float,
    require_negative_5d: bool,
) -> pd.DataFrame:
    features = _garch_features(prices, chip_features)
    high_vol = (
        (features["garch_proxy_vol_ratio"] >= ratio_threshold)
        | (features["garch_proxy_vol_percentile"] >= percentile_threshold)
    )
    if require_negative_5d:
        high_vol = high_vol & (features["return_0050_5d"] < 0.0)
    selected_rule = pd.Series("a207", index=prices.index)
    selected_rule.loc[high_vol] = "ma20"
    regime = a207_regime.copy()
    regime.loc[high_vol] = ma20_regime.loc[high_vol]
    frame = features.copy()
    frame["selected_rule"] = selected_rule
    frame["regime"] = regime
    return frame


def _garch_guard_regime(
    prices: pd.DataFrame,
    chip_features: pd.DataFrame,
    a207_regime: pd.Series,
    ratio_threshold: float,
    percentile_threshold: float,
    min_hold_days: int,
    exit_ratio: float,
    require_total_risk_score: int,
) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    features = _garch_features(prices, chip_features)
    in_guard = False
    hold_days = 0
    regimes: list[str] = []
    events: list[dict[str, Any]] = []
    for dt, row in features.iterrows():
        high_vol = (
            float(row["garch_proxy_vol_ratio"]) >= ratio_threshold
            or float(row["garch_proxy_vol_percentile"]) >= percentile_threshold
        )
        enter = (
            high_vol
            and float(row["return_0050_5d"]) < 0.0
            and int(row["total_risk_score"]) >= require_total_risk_score
        )
        exit_ = (
            float(row["garch_proxy_vol_ratio"]) <= exit_ratio
            and float(row["return_0050_5d"]) >= 0.0
        )
        if in_guard:
            hold_days += 1
            if hold_days >= min_hold_days and exit_:
                in_guard = False
                hold_days = 0
                events.append(
                    {
                        "date": str(dt.date()),
                        "action": "exit_garch_guard",
                        "garch_proxy_vol_ratio": float(row["garch_proxy_vol_ratio"]),
                        "garch_proxy_vol_percentile": float(row["garch_proxy_vol_percentile"]),
                        "return_0050_5d": float(row["return_0050_5d"]),
                        "total_risk_score": int(row["total_risk_score"]),
                    }
                )
        elif enter:
            in_guard = True
            hold_days = 1
            events.append(
                {
                    "date": str(dt.date()),
                    "action": "enter_garch_guard",
                    "garch_proxy_vol_ratio": float(row["garch_proxy_vol_ratio"]),
                    "garch_proxy_vol_percentile": float(row["garch_proxy_vol_percentile"]),
                    "return_0050_5d": float(row["return_0050_5d"]),
                    "total_risk_score": int(row["total_risk_score"]),
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
    parser.add_argument("--output-prefix", default="results/group_a_plus_financial_econometrics_garch_20260619")
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
    for ratio in (1.05, 1.10, 1.20, 1.30):
        for percentile in (0.70, 0.80, 0.90):
            for require_negative in (True, False):
                label = f"garch_selector_r{int(ratio * 100):03d}_p{int(percentile * 100):02d}_{'neg5d' if require_negative else 'any'}"
                frame = _garch_selector_regime(
                    prices,
                    chip_features,
                    a207_frame["regime"],
                    ma20_frame["regime"],
                    ratio,
                    percentile,
                    require_negative,
                )
                curves[label] = _simulate_regime_curve(prices, frame["regime"], weights_by_regime, args.initial_value)
                selector_frames[label] = frame
                selector_rows.append(
                    {
                        "variant": label,
                        **_metrics(curves[label], args.initial_value),
                        "ratio_threshold": ratio,
                        "percentile_threshold": percentile,
                        "require_negative_5d": require_negative,
                        "ma20_days": int((frame["selected_rule"] == "ma20").sum()),
                        "defense_days": int((frame["regime"] == "group_a_plus_defensive").sum()),
                    }
                )

    guard_rows: list[dict[str, Any]] = []
    guard_events: dict[str, list[dict[str, Any]]] = {}
    guard_frames: dict[str, pd.DataFrame] = {}
    for ratio in (1.05, 1.10, 1.20):
        for percentile in (0.70, 0.80, 0.90):
            for risk_score in (0, 4, 6):
                label = f"garch_guard_r{int(ratio * 100):03d}_p{int(percentile * 100):02d}_risk{risk_score}"
                events, frame = _garch_guard_regime(
                    prices,
                    chip_features,
                    a207_frame["regime"],
                    ratio,
                    percentile,
                    min_hold_days=5,
                    exit_ratio=1.00,
                    require_total_risk_score=risk_score,
                )
                curves[label] = _simulate_regime_curve(prices, frame["regime"], weights_by_regime, args.initial_value)
                guard_events[label] = events
                guard_frames[label] = frame
                guard_rows.append(
                    {
                        "variant": label,
                        **_metrics(curves[label], args.initial_value),
                        "ratio_threshold": ratio,
                        "percentile_threshold": percentile,
                        "require_total_risk_score": risk_score,
                        "event_count": len(events),
                        "defense_days": int((frame["regime"] == "group_a_plus_defensive").sum()),
                    }
                )

    summary = {name: _metrics(curves[name], args.initial_value) for name in curves.columns}
    selector_ranked = sorted(selector_rows, key=lambda row: (row["sharpe_ratio"], row["max_drawdown"], row["final_value"]), reverse=True)
    guard_ranked = sorted(guard_rows, key=lambda row: (row["sharpe_ratio"], row["max_drawdown"], row["final_value"]), reverse=True)
    report = {
        "experiment": "group_a_plus_financial_econometrics_garch_proxy",
        "method_note": (
            "Fixed-parameter GARCH(1,1)-style recursion is used as a local volatility-state proxy "
            "because optional arch/statsmodels packages are unavailable."
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
        "events": {"a207": a207_events, "ma20": ma20_events, "garch_guard": guard_events},
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
    best_frame_name = selector_ranked[0]["variant"] if selector_ranked else ""
    if best_frame_name:
        selector_frames[best_frame_name].to_csv(prefix.with_name(prefix.name + "_best_selector_frame.csv"), encoding="utf-8-sig")
    best_guard_name = guard_ranked[0]["variant"] if guard_ranked else ""
    if best_guard_name:
        guard_frames[best_guard_name].to_csv(prefix.with_name(prefix.name + "_best_guard_frame.csv"), encoding="utf-8-sig")

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
