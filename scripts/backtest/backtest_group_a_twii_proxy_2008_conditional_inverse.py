#!/usr/bin/env python3
"""Replay Group A 2008 TWII proxy events with conditional 00632R caps."""

from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backtest_group_a_twii_proxy_2008 import DEFAULT_END, DEFAULT_START
from train_dual_group_2024_2026 import _align_panel
from twii_proxy_utils import build_group_a_twii_proxy_data


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = PROJECT_ROOT / "results" / "group_a_twii_proxy_2008_inverse_sweep_20070701_20101231.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_twii_proxy_2008_conditional_inverse.json"
TICKERS = ["0050.TW", "00631L.TW", "00632R.TW"]
DEFAULT_COMMISSION_RATE = 0.001425
DEFAULT_ETF_SELL_TAX_RATE = 0.001


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--commission-rate", type=float, default=DEFAULT_COMMISSION_RATE)
    parser.add_argument("--sell-tax-rate", type=float, default=DEFAULT_ETF_SELL_TAX_RATE)
    return parser.parse_args()


def _resolve(path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    return candidate


def _metrics(values: pd.Series, *, initial_cash: float, contributions: float, fees: float, trades: int) -> dict[str, Any]:
    returns = values.pct_change().dropna()
    years = max((values.index[-1] - values.index[0]).days / 365.25, 1e-9)
    total_return = float(values.iloc[-1] / values.iloc[0] - 1.0)
    annual_return = float((values.iloc[-1] / values.iloc[0]) ** (1.0 / years) - 1.0)
    volatility = float(returns.std() * math.sqrt(252)) if len(returns) > 1 else 0.0
    sharpe = float((returns.mean() / returns.std()) * math.sqrt(252)) if len(returns) > 1 and returns.std() > 0 else 0.0
    max_drawdown = float((values / values.cummax() - 1.0).min())
    invested = initial_cash + contributions
    return {
        "final_value": float(values.iloc[-1]),
        "total_return": total_return,
        "annual_return": annual_return,
        "sharpe": sharpe,
        "volatility": volatility,
        "max_drawdown": max_drawdown,
        "num_trades": int(trades),
        "fees_paid_estimate": float(fees),
        "dca_total_contributions": float(contributions),
        "total_invested_capital": float(invested),
        "net_profit": float(values.iloc[-1] - invested),
        "contribution_return": float((values.iloc[-1] - invested) / max(invested, 1.0)),
    }


def _event_frame(source: dict[str, Any]) -> list[dict[str, Any]]:
    result = source["detailed_results"]["baseline_payload"]["result"]
    events = []
    for item in result.get("pva_sigmoid_history", []):
        events.append(
            {
                "date": item["date"],
                "step_idx": int(item.get("step_idx", 0)),
                "source": "pva_sigmoid",
                "target_weights": dict(item["target_weights"]),
            }
        )
    for item in result.get("inverse_forced_exit_history", []):
        events.append(
            {
                "date": item["date"],
                "step_idx": int(item.get("step_idx", 0)),
                "source": f"inverse_forced_exit_{item.get('reason', 'unknown')}",
                "target_weights": dict(item["target_weights"]),
            }
        )
    return sorted(events, key=lambda row: (pd.Timestamp(row["date"]), int(row["step_idx"])))


def _price_panel(start: str, end: str) -> pd.DataFrame:
    stock_data, _ = build_group_a_twii_proxy_data(start, end)
    return _align_panel(stock_data, TICKERS, start, end)


def _baseline_signal_frame(panel: pd.DataFrame, baseline_curve: pd.Series) -> pd.DataFrame:
    frame = pd.DataFrame(index=pd.to_datetime(panel["date"]))
    close = pd.Series(panel["0050.TW_close"].astype(float).to_numpy(), index=frame.index)
    frame["0050_ma60_lag1"] = close.rolling(60).mean().shift(1)
    frame["0050_mom21_lag1"] = close.pct_change(21).shift(1)
    frame["0050_below_ma60_lag1"] = close.shift(1) < frame["0050_ma60_lag1"]
    aligned_curve = baseline_curve.reindex(frame.index).ffill()
    frame["group_drawdown_lag1"] = (aligned_curve / aligned_curve.cummax() - 1.0).shift(1).fillna(0.0)
    return frame.fillna(False)


def _condition_active(condition: str, signals: pd.DataFrame, dt: pd.Timestamp) -> bool:
    if condition == "always":
        return True
    if dt not in signals.index:
        return False
    below_ma60 = bool(signals.loc[dt, "0050_below_ma60_lag1"])
    negative_mom21 = float(signals.loc[dt, "0050_mom21_lag1"]) < 0.0
    group_dd10 = float(signals.loc[dt, "group_drawdown_lag1"]) <= -0.10
    if condition == "stress_any":
        return below_ma60 or negative_mom21 or group_dd10
    if condition == "stress_strict":
        return below_ma60 and (negative_mom21 or group_dd10)
    if condition == "stress_price_only":
        return below_ma60 or negative_mom21
    if condition == "below_ma60":
        return below_ma60
    if condition == "negative_mom21":
        return negative_mom21
    if condition == "group_dd10":
        return group_dd10
    raise ValueError(f"Unsupported condition: {condition}")


def _adjust_weights(weights: dict[str, float], spec: dict[str, Any], signals: pd.DataFrame, dt: pd.Timestamp) -> tuple[dict[str, float], dict[str, Any]]:
    adjusted = {ticker: float(weights.get(ticker, 0.0)) for ticker in TICKERS}
    prior = float(adjusted.get("00632R.TW", 0.0))
    if spec["type"] == "baseline":
        allowed_cap = prior
        active = True
    elif spec["type"] == "static_cap":
        active = True
        allowed_cap = float(spec["cap"])
    elif spec["type"] == "conditional_cap":
        active = _condition_active(str(spec["condition"]), signals, dt)
        allowed_cap = float(spec["cap"]) if active else 0.0
    else:
        raise ValueError(f"Unsupported variant type: {spec['type']}")

    capped = min(prior, allowed_cap)
    released = prior - capped
    adjusted["00632R.TW"] = capped
    if released > 1e-12:
        release_to = str(spec.get("release_to", "0050.TW"))
        if release_to in adjusted:
            adjusted[release_to] = float(adjusted.get(release_to, 0.0)) + released
    return adjusted, {
        "stress_active": bool(active),
        "allowed_cap": float(allowed_cap),
        "prior_00632r": prior,
        "after_00632r": capped,
        "released_00632r": released,
    }


def _rebalance(
    shares: np.ndarray,
    cash: float,
    prices: np.ndarray,
    target_weights: np.ndarray,
    *,
    commission_rate: float,
    sell_tax_rate: float,
) -> tuple[np.ndarray, float, float]:
    value_before = cash + float(np.dot(shares, prices))
    current_values = shares * prices
    target_values = value_before * target_weights
    deltas = target_values - current_values
    fees = 0.0
    shares = shares.copy()

    for idx, delta in enumerate(deltas):
        if delta >= 0:
            continue
        sell_value = min(-float(delta), float(shares[idx] * prices[idx]))
        if sell_value <= 0:
            continue
        fee_rate = commission_rate + sell_tax_rate
        fees += sell_value * fee_rate
        cash += sell_value * (1.0 - fee_rate)
        shares[idx] -= sell_value / prices[idx]

    for idx, delta in enumerate(deltas):
        if delta <= 0:
            continue
        buy_value = min(float(delta), cash / (1.0 + commission_rate))
        if buy_value <= 0:
            continue
        fees += buy_value * commission_rate
        cash -= buy_value * (1.0 + commission_rate)
        shares[idx] += buy_value / prices[idx]

    return shares, cash, float(fees)


def _replay_variant(
    panel: pd.DataFrame,
    events: list[dict[str, Any]],
    dca_history: list[dict[str, Any]],
    signals: pd.DataFrame,
    spec: dict[str, Any],
    *,
    initial_cash: float,
    commission_rate: float,
    sell_tax_rate: float,
) -> dict[str, Any]:
    dates = pd.to_datetime(panel["date"])
    open_prices = panel[[f"{ticker}_open" for ticker in TICKERS]].astype(float).to_numpy()
    close_prices = panel[[f"{ticker}_close" for ticker in TICKERS]].astype(float).to_numpy()
    event_by_date: dict[pd.Timestamp, list[dict[str, Any]]] = {}
    for event in events:
        event_by_date.setdefault(pd.Timestamp(event["date"]).normalize(), []).append(event)
    dca_by_date = {pd.Timestamp(item["date"]).normalize(): item for item in dca_history}

    cash = float(initial_cash)
    shares = np.zeros(len(TICKERS), dtype=float)
    fees_paid = 0.0
    contributions = 0.0
    trade_count = 0
    inverse_events = 0
    inverse_max = 0.0
    diagnostics = []
    equity = []

    for idx, dt in enumerate(dates):
        normalized = pd.Timestamp(dt).normalize()
        for event in event_by_date.get(normalized, []):
            adjusted, detail = _adjust_weights(dict(event["target_weights"]), spec, signals, normalized)
            target = np.array([float(adjusted.get(ticker, 0.0)) for ticker in TICKERS], dtype=float)
            shares, cash, fees = _rebalance(
                shares,
                cash,
                open_prices[idx],
                target,
                commission_rate=commission_rate,
                sell_tax_rate=sell_tax_rate,
            )
            if fees > 0:
                trade_count += 1
                fees_paid += fees
            inv_weight = float(adjusted.get("00632R.TW", 0.0))
            if inv_weight > 1e-12:
                inverse_events += 1
            inverse_max = max(inverse_max, inv_weight)
            diagnostics.append({"date": str(normalized.date()), "source": event["source"], **detail, "target_weights": adjusted})

        if normalized in dca_by_date:
            item = dca_by_date[normalized]
            amount = float(item.get("total_contribution", 0.0))
            if amount > 0:
                contributions += amount
                cash += amount
                price = float(open_prices[idx, 0])
                buy_value = cash if cash < amount else amount / (1.0 + commission_rate)
                fee = buy_value * commission_rate
                fees_paid += fee
                cash -= buy_value + fee
                shares[0] += buy_value / price

        equity.append(cash + float(np.dot(shares, close_prices[idx])))

    curve = pd.Series(equity, index=dates, dtype=float)
    metrics = _metrics(curve, initial_cash=initial_cash, contributions=contributions, fees=fees_paid, trades=trade_count)
    return {
        "variant": spec["name"],
        "settings": spec,
        "metrics": metrics,
        "inverse_nonzero_events": int(inverse_events),
        "inverse_max_weight": float(inverse_max),
        "diagnostics": diagnostics,
        "equity_curve": [{"date": str(idx.date()), "value": float(value)} for idx, value in curve.items()],
    }


def _variant_specs() -> list[dict[str, Any]]:
    return [
        {"name": "baseline_event_replay", "type": "baseline"},
        {"name": "disable_00632r_to_0050_replay", "type": "static_cap", "cap": 0.0, "release_to": "0050.TW"},
        {"name": "static_cap10_to_0050_replay", "type": "static_cap", "cap": 0.10, "release_to": "0050.TW"},
        {"name": "static_cap05_to_0050_replay", "type": "static_cap", "cap": 0.05, "release_to": "0050.TW"},
        {"name": "conditional_stress_any_cap10_to_0050_replay", "type": "conditional_cap", "condition": "stress_any", "cap": 0.10, "release_to": "0050.TW"},
        {"name": "conditional_stress_price_only_cap10_to_0050_replay", "type": "conditional_cap", "condition": "stress_price_only", "cap": 0.10, "release_to": "0050.TW"},
        {"name": "conditional_stress_strict_cap10_to_0050_replay", "type": "conditional_cap", "condition": "stress_strict", "cap": 0.10, "release_to": "0050.TW"},
        {"name": "conditional_stress_any_full_to_0050_replay", "type": "conditional_cap", "condition": "stress_any", "cap": 1.0, "release_to": "0050.TW"},
    ]


def main() -> None:
    args = _parse_args()
    source_path = _resolve(args.source)
    output = _resolve(args.output)
    source = json.loads(source_path.read_text(encoding="utf-8"))
    baseline_result = source["detailed_results"]["baseline_payload"]["result"]
    initial_cash = float(source.get("detailed_results", {}).get("baseline_payload", {}).get("result", {}).get("total_invested_capital", 1_000_000.0)) - float(baseline_result.get("dca_total_contributions", 0.0))
    panel = _price_panel(args.start, args.end)
    events = _event_frame(source)
    baseline_curve = pd.Series(
        baseline_result["equity_curve"],
        index=pd.to_datetime(panel["date"]).iloc[: len(baseline_result["equity_curve"])],
        dtype=float,
    )
    signals = _baseline_signal_frame(panel, baseline_curve)
    dca_history = list(baseline_result.get("dca_purchase_history", []))

    rows = []
    detailed = {}
    curves = pd.DataFrame(index=pd.to_datetime(panel["date"]))
    for spec in _variant_specs():
        result = _replay_variant(
            panel,
            events,
            dca_history,
            signals,
            spec,
            initial_cash=initial_cash,
            commission_rate=float(args.commission_rate),
            sell_tax_rate=float(args.sell_tax_rate),
        )
        metrics = result["metrics"]
        row = {
            "variant": spec["name"],
            "family": spec["type"],
            **metrics,
            "inverse_nonzero_events": result["inverse_nonzero_events"],
            "inverse_max_weight": result["inverse_max_weight"],
        }
        rows.append(row)
        detailed[spec["name"]] = result
        curves[spec["name"]] = pd.Series(
            [item["value"] for item in result["equity_curve"]],
            index=pd.to_datetime([item["date"] for item in result["equity_curve"]]),
        )
        print(
            f"{spec['name']}: final={metrics['final_value']:.2f}, sharpe={metrics['sharpe']:.4f}, "
            f"mdd={metrics['max_drawdown']:.4%}, inv_events={result['inverse_nonzero_events']}, "
            f"inv_max={result['inverse_max_weight']:.2%}",
            flush=True,
        )

    baseline = next(row for row in rows if row["variant"] == "baseline_event_replay")
    for row in rows:
        row["delta_final_value"] = row["final_value"] - baseline["final_value"]
        row["delta_sharpe"] = row["sharpe"] - baseline["sharpe"]
        row["delta_max_drawdown"] = row["max_drawdown"] - baseline["max_drawdown"]

    output.parent.mkdir(parents=True, exist_ok=True)
    csv_path = output.with_suffix(".csv")
    curve_path = output.with_name(output.stem + "_curve.csv")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    curves.index.name = "date"
    curves.to_csv(curve_path, encoding="utf-8-sig")
    report = {
        "experiment": "group_a_twii_proxy_2008_conditional_inverse_event_replay",
        "method_note": (
            "Post-target event replay using baseline 2008 TWII proxy target events. "
            "This is a conditional policy stress check, not a full PPO environment rerun."
        ),
        "source": str(source_path.resolve()),
        "window": {"start": str(pd.Timestamp(panel["date"].min()).date()), "end": str(pd.Timestamp(panel["date"].max()).date()), "rows": int(len(panel))},
        "baseline_full_env_metrics": source["baseline"],
        "baseline_event_replay": baseline,
        "best": {
            "best_final": max(rows, key=lambda row: row["final_value"]),
            "best_sharpe": max(rows, key=lambda row: row["sharpe"]),
            "best_mdd": max(rows, key=lambda row: row["max_drawdown"]),
        },
        "results": rows,
        "detailed_results": detailed,
        "outputs": {"json": str(output), "csv": str(csv_path), "curve_csv": str(curve_path)},
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"JSON: {output}")
    print(f"CSV:  {csv_path}")
    print(f"Curve CSV: {curve_path}")


if __name__ == "__main__":
    main()
