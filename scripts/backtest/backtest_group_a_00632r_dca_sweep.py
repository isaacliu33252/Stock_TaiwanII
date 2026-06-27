#!/usr/bin/env python3
"""Sweep Group A 00632R and DCA overlays without PPO retraining."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

import pandas as pd

import backtest_group_a_tdcc_latest as latest_module
from backtest_group_a_tdcc_improvement_sweep import (
    _cached_raw_tdcc_state,
    _load_base_from_source,
    _load_prices,
    _resolve,
)
from backtest_group_a_tdcc_latest import DEFAULT_DB, _simulate_tdcc_overlay


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE_BACKTEST = PROJECT_ROOT / "results" / "group_a_tdcc_latest_backtest_20240101_20260605.json"
DEFAULT_CONFIG = PROJECT_ROOT / "group_a_tdcc_improved_config_destination_primary.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_00632r_dca_sweep_20240102_20260604.json"
TICKERS = ["0050.TW", "00631L.TW", "00632R.TW"]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-backtest", default=str(DEFAULT_SOURCE_BACKTEST))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--fee-rate", type=float, default=0.001425)
    return parser.parse_args()


def _metrics_row(name: str, result: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    metrics = result["metrics"]
    events = result.get("events", [])
    inverse_events = [
        event for event in events
        if float(event.get("target_weights", {}).get("00632R.TW", 0.0)) > 1e-12
    ]
    return {
        "variant": name,
        "family": meta.get("family", ""),
        "final_value": float(metrics["final_value"]),
        "annual_return": float(metrics["annual_return"]),
        "sharpe_ratio": float(metrics["sharpe_ratio"]),
        "max_drawdown": float(metrics["max_drawdown"]),
        "volatility": float(metrics["volatility"]),
        "num_rebalances": int(metrics["num_rebalances"]),
        "fees_paid_estimate": float(metrics["fees_paid_estimate"]),
        "dca_total_contributions": float(metrics["dca_total_contributions"]),
        "total_invested_capital": float(metrics["total_invested_capital"]),
        "net_profit": float(metrics["net_profit"]),
        "contribution_return": float(metrics["contribution_return"]),
        "inverse_nonzero_events": int(len(inverse_events)),
        "inverse_max_weight": max(
            [float(event.get("target_weights", {}).get("00632R.TW", 0.0)) for event in events] or [0.0]
        ),
        "settings": meta,
    }


def _price_signals(prices: pd.DataFrame, group_curve: pd.Series) -> pd.DataFrame:
    frame = pd.DataFrame(index=prices.index)
    close = prices["0050.TW"].astype(float)
    frame["0050_ma60_lag1"] = close.rolling(60).mean().shift(1)
    frame["0050_mom21_lag1"] = close.pct_change(21).shift(1)
    frame["0050_below_ma60_lag1"] = close.shift(1) < frame["0050_ma60_lag1"]
    aligned_group = group_curve.reindex(prices.index).ffill()
    frame["group_drawdown_lag1"] = (aligned_group / aligned_group.cummax() - 1.0).shift(1).fillna(0.0)
    return frame.fillna(False)


def _release_inverse(
    weights: dict[str, float],
    *,
    cap: float,
    release_to: str,
) -> dict[str, float]:
    adjusted = dict(weights)
    prior = float(adjusted.get("00632R.TW", 0.0))
    capped = min(prior, cap)
    released = prior - capped
    adjusted["00632R.TW"] = capped
    if released > 0:
        if release_to == "primary":
            adjusted["0050.TW"] = float(adjusted.get("0050.TW", 0.0)) + released
        elif release_to == "leverage":
            adjusted["00631L.TW"] = float(adjusted.get("00631L.TW", 0.0)) + released
        else:
            # Leaving the released weight out of ticker weights turns it into cash
            # because the TDCC replay derives cash as 1 - sum(target_weights).
            pass
    return adjusted


def _inverse_allowed(condition: str, signals: pd.DataFrame, date: pd.Timestamp) -> bool:
    if condition == "always":
        return True
    if date not in signals.index:
        return False
    below_ma60 = bool(signals.loc[date, "0050_below_ma60_lag1"])
    negative_mom21 = float(signals.loc[date, "0050_mom21_lag1"]) < 0.0
    group_dd10 = float(signals.loc[date, "group_drawdown_lag1"]) <= -0.10
    if condition == "below_ma60":
        return below_ma60
    if condition == "negative_mom21":
        return negative_mom21
    if condition == "group_dd10":
        return group_dd10
    if condition == "stress_any":
        return below_ma60 or negative_mom21 or group_dd10
    if condition == "stress_strict":
        return below_ma60 and (negative_mom21 or group_dd10)
    if condition == "stress_price_only":
        return below_ma60 or negative_mom21
    raise ValueError(f"Unsupported condition: {condition}")


def _apply_inverse_policy(
    base_events: list[dict[str, Any]],
    prices: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    cap: float | None = None,
    release_to: str = "primary",
    condition: str = "always",
) -> list[dict[str, Any]]:
    adjusted = []
    for event in base_events:
        item = copy.deepcopy(event)
        date = pd.Timestamp(item["date"]).normalize()
        weights = {str(k): float(v) for k, v in item["target_weights"].items()}
        prior = float(weights.get("00632R.TW", 0.0))
        allowed = _inverse_allowed(condition, signals, date)
        target_cap = 0.0 if not allowed else (prior if cap is None else cap)
        item["target_weights"] = _release_inverse(weights, cap=target_cap, release_to=release_to)
        adjusted.append(item)
    return adjusted


def _apply_hold_limit(
    base_events: list[dict[str, Any]],
    prices: pd.DataFrame,
    signals: pd.DataFrame | None = None,
    *,
    max_days: int,
    release_to: str,
    stress_condition: str | None = None,
) -> list[dict[str, Any]]:
    adjusted: list[dict[str, Any]] = []
    position_start: pd.Timestamp | None = None
    for event in base_events:
        item = copy.deepcopy(event)
        date = pd.Timestamp(item["date"]).normalize()
        weights = {str(k): float(v) for k, v in item["target_weights"].items()}
        inverse = float(weights.get("00632R.TW", 0.0))
        stress_allowed = (
            False
            if stress_condition is None or signals is None
            else _inverse_allowed(stress_condition, signals, date)
        )
        if inverse <= 1e-12:
            position_start = None
        elif position_start is None:
            position_start = date
        elif (date - position_start).days > max_days and not stress_allowed:
            weights = _release_inverse(weights, cap=0.0, release_to=release_to)
        item["target_weights"] = weights
        adjusted.append(item)
    return adjusted


def _apply_dca_policy(
    dca_history: list[dict[str, Any]],
    signals: pd.DataFrame,
    *,
    policy: str,
) -> list[dict[str, Any]]:
    adjusted = []
    for item in dca_history:
        row = copy.deepcopy(item)
        date = pd.Timestamp(row["date"]).normalize()
        amount = float(row.get("total_contribution", 0.0))
        multiplier = 1.0
        if policy == "base":
            multiplier = 1.0
        elif policy == "pause_group_dd10":
            multiplier = 0.0 if date in signals.index and float(signals.loc[date, "group_drawdown_lag1"]) <= -0.10 else 1.0
        elif policy == "double_group_dd10":
            multiplier = 2.0 if date in signals.index and float(signals.loc[date, "group_drawdown_lag1"]) <= -0.10 else 1.0
        elif policy == "double_below_ma60":
            multiplier = 2.0 if date in signals.index and bool(signals.loc[date, "0050_below_ma60_lag1"]) else 1.0
        elif policy == "pause_negative_mom21":
            multiplier = 0.0 if date in signals.index and float(signals.loc[date, "0050_mom21_lag1"]) < 0.0 else 1.0
        else:
            raise ValueError(f"Unsupported DCA policy: {policy}")
        new_amount = amount * multiplier
        row["total_contribution"] = new_amount
        if new_amount <= 0.0:
            row["fees"] = 0.0
            row["purchases"] = {}
        else:
            purchase = row.get("purchases", {}).get("0050.TW", {})
            if purchase:
                scale = new_amount / max(amount, 1e-12)
                purchase["cash_contribution"] = new_amount
                purchase["buy_value"] = float(purchase.get("buy_value", 0.0)) * scale
                purchase["fee"] = float(purchase.get("fee", 0.0)) * scale
                purchase["shares_bought"] = float(purchase.get("shares_bought", 0.0)) * scale
                row["fees"] = float(row.get("fees", 0.0)) * scale
                row["purchases"] = {"0050.TW": purchase}
        adjusted.append(row)
    return adjusted


def _variant_specs() -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = [
        {"name": "baseline_destination_primary", "family": "baseline", "inverse_policy": {"condition": "always", "cap": None, "release_to": "primary"}, "dca_policy": "base"},
        {"name": "disable_00632r_to_cash", "family": "ablation", "inverse_policy": {"condition": "always", "cap": 0.0, "release_to": "cash"}, "dca_policy": "base"},
        {"name": "disable_00632r_to_0050", "family": "ablation", "inverse_policy": {"condition": "always", "cap": 0.0, "release_to": "primary"}, "dca_policy": "base"},
    ]
    for cap in [0.05, 0.10, 0.15, 0.20]:
        specs.append({"name": f"cap_00632r_{int(cap*100):02d}_to_0050", "family": "cap", "inverse_policy": {"condition": "always", "cap": cap, "release_to": "primary"}, "dca_policy": "base"})
    for condition in ["below_ma60", "negative_mom21", "group_dd10", "stress_any", "stress_strict", "stress_price_only"]:
        specs.append({"name": f"conditional_00632r_{condition}_to_0050", "family": "conditional", "inverse_policy": {"condition": condition, "cap": None, "release_to": "primary"}, "dca_policy": "base"})
        specs.append({"name": f"conditional_00632r_{condition}_cap10_to_0050", "family": "conditional_cap", "inverse_policy": {"condition": condition, "cap": 0.10, "release_to": "primary"}, "dca_policy": "base"})
    for days in [5, 10, 20]:
        specs.append({"name": f"hold_limit_00632r_{days}d_to_0050", "family": "hold_limit", "hold_limit": {"max_days": days, "release_to": "primary"}, "dca_policy": "base"})
    for days in [5, 10, 20]:
        for condition in ["stress_any", "stress_strict", "stress_price_only"]:
            specs.append({
                "name": f"hold_limit_00632r_{days}d_unless_{condition}_to_0050",
                "family": "stress_aware_hold_limit",
                "hold_limit": {"max_days": days, "release_to": "primary", "stress_condition": condition},
                "dca_policy": "base",
            })
    for policy in ["pause_group_dd10", "double_group_dd10", "double_below_ma60", "pause_negative_mom21"]:
        specs.append({"name": f"dca_{policy}", "family": "dca", "inverse_policy": {"condition": "always", "cap": None, "release_to": "primary"}, "dca_policy": policy})
    for inverse_name, inverse_policy in [
        ("disable_00632r_to_0050", {"condition": "always", "cap": 0.0, "release_to": "primary"}),
        ("disable_00632r_to_cash", {"condition": "always", "cap": 0.0, "release_to": "cash"}),
        ("cap_00632r_10_to_0050", {"condition": "always", "cap": 0.10, "release_to": "primary"}),
        ("conditional_00632r_below_ma60_to_0050", {"condition": "below_ma60", "cap": None, "release_to": "primary"}),
    ]:
        for policy in ["double_group_dd10", "double_below_ma60"]:
            specs.append({
                "name": f"{inverse_name}_dca_{policy}",
                "family": "combo",
                "inverse_policy": inverse_policy,
                "dca_policy": policy,
            })
    return specs


def main() -> None:
    args = _parse_args()
    latest_module._raw_tdcc_state = _cached_raw_tdcc_state
    source = _resolve(args.source_backtest)
    config_path = _resolve(args.config)
    db_path = _resolve(args.db)
    output = _resolve(args.output)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    base, base_events, dates, initial_cash = _load_base_from_source(source)
    prices = _load_prices(db_path, dates)
    group_curve = pd.Series(
        [float(row["value"]) for row in json.loads(source.read_text(encoding="utf-8"))["latest_tdcc_overlay_replay"]["equity_curve"]],
        index=pd.to_datetime([row["date"] for row in json.loads(source.read_text(encoding="utf-8"))["latest_tdcc_overlay_replay"]["equity_curve"]]),
        dtype=float,
    )
    signals = _price_signals(prices, group_curve)

    rows: list[dict[str, Any]] = []
    detailed: dict[str, Any] = {}
    curves = pd.DataFrame(index=prices.index)
    for spec in _variant_specs():
        name = str(spec["name"])
        if "hold_limit" in spec:
            events = _apply_hold_limit(base_events, prices, signals, **dict(spec["hold_limit"]))
        else:
            events = _apply_inverse_policy(base_events, prices, signals, **dict(spec["inverse_policy"]))
        dca_history = _apply_dca_policy(base["dca_purchase_history"], signals, policy=str(spec["dca_policy"]))
        result = _simulate_tdcc_overlay(
            prices,
            events,
            config,
            db_path,
            initial_cash=initial_cash,
            fee_rate=float(args.fee_rate),
            dca_history=dca_history,
        )
        row = _metrics_row(name, result, spec)
        rows.append(row)
        detailed[name] = {"settings": spec, **result}
        curves[name] = pd.Series([item["value"] for item in result["equity_curve"]], index=pd.to_datetime([item["date"] for item in result["equity_curve"]]))
        print(
            f"{name}: final={row['final_value']:.2f}, sharpe={row['sharpe_ratio']:.4f}, "
            f"mdd={row['max_drawdown']:.4%}, inv_events={row['inverse_nonzero_events']}, "
            f"inv_max={row['inverse_max_weight']:.2%}, dca={row['dca_total_contributions']:.0f}",
            flush=True,
        )

    baseline = next(row for row in rows if row["variant"] == "baseline_destination_primary")
    for row in rows:
        row["delta_final_value"] = row["final_value"] - baseline["final_value"]
        row["delta_sharpe_ratio"] = row["sharpe_ratio"] - baseline["sharpe_ratio"]
        row["delta_max_drawdown"] = row["max_drawdown"] - baseline["max_drawdown"]
        row["delta_contribution_return"] = row["contribution_return"] - baseline["contribution_return"]

    best_final = max(rows, key=lambda row: row["final_value"])
    best_sharpe = max(rows, key=lambda row: row["sharpe_ratio"])
    best_mdd_with_98pct_final_floor = max(
        [row for row in rows if row["final_value"] >= baseline["final_value"] * 0.98],
        key=lambda row: row["max_drawdown"],
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    csv_path = output.with_suffix(".csv")
    curve_path = output.with_name(output.stem + "_curve.csv")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    curves.index.name = "date"
    curves.to_csv(curve_path, encoding="utf-8-sig")
    report = {
        "experiment": "group_a_00632r_dca_sweep",
        "method_note": "No PPO retraining. Uses Group A destination_primary TDCC config and rewrites 00632R target events / DCA history before replay.",
        "source_backtest": str(source.resolve()),
        "config": str(config_path.resolve()),
        "window": {"start": str(prices.index[0].date()), "end": str(prices.index[-1].date()), "rows": int(len(prices))},
        "baseline": baseline,
        "best": {
            "best_final": best_final,
            "best_sharpe": best_sharpe,
            "best_mdd_with_98pct_final_floor": best_mdd_with_98pct_final_floor,
        },
        "results": rows,
        "detailed_results": detailed,
        "outputs": {"json": str(output), "csv": str(csv_path), "curve_csv": str(curve_path)},
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"JSON: {output}")
    print(f"CSV:  {csv_path}")
    print(f"Curve CSV: {curve_path}")
    print(f"Best final: {best_final['variant']} {best_final['final_value']:.2f}")
    print(f"Best sharpe: {best_sharpe['variant']} {best_sharpe['sharpe_ratio']:.4f}")
    print(f"Best MDD with 98% final floor: {best_mdd_with_98pct_final_floor['variant']} {best_mdd_with_98pct_final_floor['max_drawdown']:.4%}")


if __name__ == "__main__":
    main()
