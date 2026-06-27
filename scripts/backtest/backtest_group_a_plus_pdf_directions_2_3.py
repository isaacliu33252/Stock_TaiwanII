#!/usr/bin/env python3
"""Research tests for PDF directions 2 and 3.

Direction 2: transaction-cost-aware no-trade band / turnover cap.
Direction 3: volatility-regime selector between A20.7 and short-cycle defense.
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
    _mark_to_market,
    _metrics,
    _rebalance,
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


def _current_weights(value: float, price_row: pd.Series, shares: dict[str, float], cash: float) -> dict[str, float]:
    if value <= 0:
        return {ticker: 0.0 for ticker in TICKERS} | {"cash": 1.0}
    weights = {
        ticker: float(shares.get(ticker, 0.0) or 0.0) * float(price_row[ticker]) / value
        for ticker in TICKERS
    }
    weights["cash"] = float(cash) / value
    return _normalize(weights)


def _simulate_cost_aware_curve(
    prices: pd.DataFrame,
    regimes: pd.Series,
    weights_by_regime: dict[str, dict[str, float]],
    initial_value: float,
    no_trade_band: float,
    turnover_cap: float | None,
    commission_rate: float,
    etf_sell_tax_rate: float,
    slippage_rate: float,
) -> tuple[pd.Series, list[dict[str, Any]], float, float]:
    values: list[float] = []
    trades: list[dict[str, Any]] = []
    total_cost = 0.0
    total_turnover = 0.0
    current_regime = str(regimes.iloc[0])
    shares, cash = _rebalance(initial_value, prices.iloc[0], weights_by_regime[current_regime])
    for dt, price_row in prices.iterrows():
        value = _mark_to_market(price_row, shares, cash)
        next_regime = str(regimes.loc[dt])
        if next_regime != current_regime:
            current_weights = _current_weights(value, price_row, shares, cash)
            target = _normalize(weights_by_regime[next_regime])
            diff = {key: float(target.get(key, 0.0)) - float(current_weights.get(key, 0.0)) for key in [*TICKERS, "cash"]}
            turnover = sum(abs(diff[ticker]) for ticker in TICKERS)
            if turnover >= no_trade_band:
                scale = 1.0
                if turnover_cap is not None and turnover > turnover_cap:
                    scale = turnover_cap / turnover
                executable = {
                    key: float(current_weights.get(key, 0.0)) + float(diff.get(key, 0.0)) * scale
                    for key in [*TICKERS, "cash"]
                }
                executable = _normalize(executable)
                buy_notional = 0.0
                sell_notional = 0.0
                for ticker in TICKERS:
                    delta_weight = executable[ticker] - current_weights[ticker]
                    if delta_weight > 0:
                        buy_notional += value * delta_weight
                    else:
                        sell_notional += value * abs(delta_weight)
                traded = buy_notional + sell_notional
                cost = traded * (commission_rate + slippage_rate) + sell_notional * etf_sell_tax_rate
                after_cost = max(value - cost, 0.0)
                shares = {
                    ticker: after_cost * float(executable.get(ticker, 0.0)) / max(float(price_row[ticker]), 1e-12)
                    for ticker in TICKERS
                }
                cash = after_cost * float(executable.get("cash", 0.0))
                value = _mark_to_market(price_row, shares, cash)
                total_cost += cost
                total_turnover += traded
                trades.append(
                    {
                        "date": str(dt.date()),
                        "from_regime": current_regime,
                        "to_regime": next_regime,
                        "turnover_ratio": float(turnover),
                        "turnover_scale": float(scale),
                        "traded_notional": float(traded),
                        "sell_notional": float(sell_notional),
                        "cost": float(cost),
                    }
                )
            current_regime = next_regime
        values.append(value)
    return pd.Series(values, index=prices.index, dtype=float), trades, float(total_cost), float(total_turnover)


def _volatility_selector_regime(
    prices: pd.DataFrame,
    chip_features: pd.DataFrame,
    a207_regime: pd.Series,
    ma20_regime: pd.Series,
    threshold: float,
    require_negative_5d: bool,
) -> pd.DataFrame:
    features = _regime_features(prices, A207_RULE, chip_features)
    close = prices["0050.TW"].astype(float)
    returns = close.pct_change().fillna(0.0)
    ewma_vol = returns.pow(2).ewm(alpha=0.06, adjust=False, min_periods=20).mean().pow(0.5) * math.sqrt(252)
    ewma_base = ewma_vol.rolling(126, min_periods=40).median()
    ewma_ratio = (ewma_vol / ewma_base.replace(0.0, math.nan)).replace([math.inf, -math.inf], math.nan).fillna(1.0)
    ret_5d = close.pct_change(5).fillna(0.0)
    high_vol = ewma_ratio >= threshold
    if require_negative_5d:
        high_vol = high_vol & (ret_5d < 0.0)
    selected_rule = pd.Series("a207", index=prices.index)
    selected_rule.loc[high_vol] = "ma20"
    regime = a207_regime.copy()
    regime.loc[high_vol] = ma20_regime.loc[high_vol]
    return pd.DataFrame(
        {
            "selected_rule": selected_rule,
            "regime": regime,
            "ewma_vol_0050": ewma_vol,
            "ewma_vol_ratio": ewma_ratio,
            "realized_vol_ratio_20_60": features["realized_vol_ratio_20_60"],
            "return_0050_5d": ret_5d,
        },
        index=prices.index,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision-pointer", default=str(DEFAULT_DECISION_POINTER))
    parser.add_argument("--golden-signal", default=str(DEFAULT_GOLDEN_SIGNAL))
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-06-18")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--etf-sell-tax-rate", type=float, default=0.001)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--output-prefix", default="results/group_a_plus_pdf_directions_2_3_20260619")
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
    curves["a207_no_cost"] = _simulate_regime_curve(prices, a207_frame["regime"], weights_by_regime, args.initial_value)
    curves["ma20_no_cost"] = _simulate_regime_curve(prices, ma20_frame["regime"], weights_by_regime, args.initial_value)

    cost_rows: list[dict[str, Any]] = []
    cost_trade_logs: dict[str, list[dict[str, Any]]] = {}
    for band in (0.0, 0.05, 0.10, 0.15, 0.20):
        for cap in (None, 0.20, 0.10):
            cap_label = "none" if cap is None else f"{int(cap * 100):02d}"
            label = f"a207_cost_band{int(band * 100):02d}_cap{cap_label}"
            curve, trades, total_cost, total_turnover = _simulate_cost_aware_curve(
                prices,
                a207_frame["regime"],
                weights_by_regime,
                args.initial_value,
                band,
                cap,
                args.commission_rate,
                args.etf_sell_tax_rate,
                args.slippage_rate,
            )
            curves[label] = curve
            cost_trade_logs[label] = trades
            cost_rows.append(
                {
                    "variant": label,
                    **_metrics(curve, args.initial_value),
                    "no_trade_band": band,
                    "turnover_cap": cap,
                    "trade_count": len(trades),
                    "total_cost": total_cost,
                    "total_turnover": total_turnover,
                }
            )

    vol_rows: list[dict[str, Any]] = []
    vol_frames: dict[str, pd.DataFrame] = {}
    for threshold in (1.05, 1.10, 1.15, 1.20, 1.30):
        for require_negative in (True, False):
            label = f"vol_selector_ewma{int(threshold * 100):03d}_{'neg5d' if require_negative else 'any'}"
            frame = _volatility_selector_regime(
                prices,
                chip_features,
                a207_frame["regime"],
                ma20_frame["regime"],
                threshold,
                require_negative,
            )
            curves[label] = _simulate_regime_curve(prices, frame["regime"], weights_by_regime, args.initial_value)
            vol_frames[label] = frame
            vol_rows.append(
                {
                    "variant": label,
                    **_metrics(curves[label], args.initial_value),
                    "threshold": threshold,
                    "require_negative_5d": require_negative,
                    "ma20_days": int((frame["selected_rule"] == "ma20").sum()),
                    "defense_days": int((frame["regime"] == "group_a_plus_defensive").sum()),
                }
            )

    summary = {name: _metrics(curves[name], args.initial_value) for name in curves.columns}
    cost_ranked = sorted(cost_rows, key=lambda row: (row["final_value"], row["sharpe_ratio"], row["max_drawdown"]), reverse=True)
    vol_ranked = sorted(vol_rows, key=lambda row: (row["sharpe_ratio"], row["max_drawdown"], row["final_value"]), reverse=True)
    report = {
        "experiment": "group_a_plus_pdf_directions_2_3",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "requested_window": {"start": args.start, "end": args.end},
        "actual_window": {"start": str(prices.index[0].date()), "end": str(prices.index[-1].date()), "rows": int(len(prices))},
        "inputs": {
            "policy_signal": str(policy_signal_path.relative_to(PROJECT_ROOT)),
            "golden_signal": str(golden_signal_path.relative_to(PROJECT_ROOT)),
        },
        "cost_assumptions": {
            "commission_rate": args.commission_rate,
            "etf_sell_tax_rate": args.etf_sell_tax_rate,
            "slippage_rate": args.slippage_rate,
        },
        "weights": {
            "golden1_0531_1m": _normalize(golden_weights),
            "group_a_plus_defensive_1m": _normalize(defensive_weights),
        },
        "rules": {"a207": asdict(A207_RULE), "ma20": asdict(MA20_RULE)},
        "events": {"a207": a207_events, "ma20": ma20_events},
        "summary": summary,
        "direction_2_cost_no_trade": {"rows": cost_rows, "best_by_final": cost_ranked[:5]},
        "direction_3_volatility_selector": {"rows": vol_rows, "best_by_sharpe": vol_ranked[:5]},
    }

    prefix = Path(args.output_prefix)
    if not prefix.is_absolute():
        prefix = (PROJECT_ROOT / prefix).resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = prefix.with_suffix(".json")
    csv_path = prefix.with_suffix(".csv")
    curve_path = prefix.with_name(prefix.name + "_curve.csv")
    cost_path = prefix.with_name(prefix.name + "_cost_rows.csv")
    vol_path = prefix.with_name(prefix.name + "_vol_rows.csv")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame([{"variant": name, **metrics} for name, metrics in summary.items()]).to_csv(
        csv_path,
        index=False,
        encoding="utf-8-sig",
    )
    curves.to_csv(curve_path, encoding="utf-8-sig")
    pd.DataFrame(cost_rows).to_csv(cost_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(vol_rows).to_csv(vol_path, index=False, encoding="utf-8-sig")
    for name, frame in vol_frames.items():
        frame.to_csv(prefix.with_name(prefix.name + f"_{name}.csv"), encoding="utf-8-sig")

    print(f"JSON: {json_path}")
    print(f"CSV: {csv_path}")
    print(f"Cost rows: {cost_path}")
    print(f"Vol rows: {vol_path}")
    print(f"Window: {report['actual_window']['start']} ~ {report['actual_window']['end']} ({report['actual_window']['rows']} rows)")
    for name in ("a207_no_cost", "ma20_no_cost"):
        metrics = summary[name]
        print(
            f"{name}: final={metrics['final_value']:,.0f}, sharpe={metrics['sharpe_ratio']:.3f}, "
            f"sortino={metrics['sortino_ratio']:.3f}, mdd={metrics['max_drawdown']:.2%}, starr={metrics['starr_ratio_5pct']:.4f}"
        )
    best_cost = cost_ranked[0]
    print(
        f"Best direction 2: {best_cost['variant']} final={best_cost['final_value']:,.0f}, "
        f"cost={best_cost['total_cost']:,.0f}, trades={best_cost['trade_count']}"
    )
    best_vol = vol_ranked[0]
    print(
        f"Best direction 3 by Sharpe: {best_vol['variant']} final={best_vol['final_value']:,.0f}, "
        f"sharpe={best_vol['sharpe_ratio']:.3f}, mdd={best_vol['max_drawdown']:.2%}, ma20_days={best_vol['ma20_days']}"
    )


if __name__ == "__main__":
    main()
