#!/usr/bin/env python3
"""Sweep multi-ticker execution overlays for the latest Group A payload."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from compare_group_a_0050_only_2025_20260611 import (
    COMMISSION_RATE,
    ETF_SELL_TAX_RATE,
    INITIAL_CASH,
    LATEST_PAYLOAD,
    PROJECT_ROOT,
    START,
    END,
    _capture_events,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_latest_multiticker_overlay_sweep_20250102_20260611.json"


def _parse_float_list(value: str) -> list[float | None]:
    items: list[float | None] = []
    for raw in value.split(","):
        text = raw.strip().lower()
        if not text:
            continue
        if text in {"none", "off", "null"}:
            items.append(None)
        else:
            items.append(float(text))
    if not items:
        raise ValueError("list must contain at least one value")
    return items


def _parse_int_list(value: str) -> list[int | None]:
    items: list[int | None] = []
    for raw in value.split(","):
        text = raw.strip().lower()
        if not text:
            continue
        if text in {"none", "off", "null"}:
            items.append(None)
        else:
            items.append(int(text))
    if not items:
        raise ValueError("list must contain at least one value")
    return items


def _metrics(series: pd.Series, *, rebalances: int, total_cost: float, contributions: float) -> dict[str, float]:
    returns = series.pct_change().dropna()
    years = max(len(returns) / 252.0, 1 / 252.0)
    total_return = float(series.iloc[-1] / INITIAL_CASH - 1.0)
    annual_return = float((series.iloc[-1] / INITIAL_CASH) ** (1.0 / years) - 1.0)
    vol = float(returns.std(ddof=0) * math.sqrt(252)) if len(returns) else 0.0
    sharpe = float((returns.mean() / returns.std(ddof=0)) * math.sqrt(252)) if len(returns) and returns.std(ddof=0) > 0 else 0.0
    peak = series.cummax()
    mdd = float((series / peak - 1.0).min())
    invested = INITIAL_CASH + contributions
    return {
        "final_value": float(series.iloc[-1]),
        "total_return": total_return,
        "annual_return": annual_return,
        "volatility": vol,
        "sharpe_ratio": sharpe,
        "max_drawdown": mdd,
        "num_rebalances": int(rebalances),
        "total_cost": float(total_cost),
        "dca_total_contributions": float(contributions),
        "total_invested_capital": float(invested),
        "net_profit": float(series.iloc[-1] - invested),
        "contribution_return": float((series.iloc[-1] - invested) / invested),
    }


def _apply_dca(
    dt: pd.Timestamp,
    prices: pd.Series,
    shares: dict[str, float],
    cash: float,
    dca_map: dict[pd.Timestamp, list[dict[str, Any]]],
) -> tuple[float, float, float]:
    fees = 0.0
    contributions = 0.0
    for item in dca_map.get(dt, []):
        amount = float(item.get("total_contribution", 0.0))
        if amount <= 0:
            continue
        contributions += amount
        purchases = dict(item.get("purchases", {}) or {})
        if not purchases:
            cash += amount
            continue
        for ticker, purchase in purchases.items():
            cash_contribution = float(purchase.get("cash_contribution", 0.0))
            if cash_contribution <= 0:
                continue
            if ticker not in shares or ticker not in prices or float(prices[ticker]) <= 0:
                cash += cash_contribution
                continue
            fee = cash_contribution * COMMISSION_RATE / (1.0 + COMMISSION_RATE)
            buy_value = cash_contribution - fee
            shares[ticker] += buy_value / float(prices[ticker])
            fees += fee
    return cash, fees, contributions


def _overlay_events(
    captured: dict[str, Any],
    *,
    max_0050_step: float | None,
    step_mode: str,
    step_active_max_ma_ratio: float | None,
    min_0050_delta: float,
    ma_window: int | None,
    ma_ratio: float,
    ma_0050_cap: float | None,
    ma_00631l_cap: float | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    prices = captured["prices"]
    close_0050 = prices["0050.TW"]
    ma_series = None
    if ma_window is not None and ma_window > 0 and (
        step_active_max_ma_ratio is not None or ma_0050_cap is not None or ma_00631l_cap is not None
    ):
        ma_series = close_0050.rolling(int(ma_window), min_periods=max(5, int(ma_window) // 3)).mean()

    adjusted_events: list[dict[str, Any]] = []
    last_0050: float | None = None
    changed = 0
    skipped = 0
    brake_events = 0
    leverage_cap_events = 0
    for event in captured["events"]:
        dt = pd.Timestamp(event["date"]).normalize()
        raw = {ticker: float(weight) for ticker, weight in dict(event["target_weights"]).items()}
        target = dict(raw)
        raw_0050 = float(target.get("0050.TW", 0.0))
        target_0050 = raw_0050

        step_active = True
        if step_active_max_ma_ratio is not None and ma_series is not None:
            price = close_0050.get(dt)
            ma_value = ma_series.get(dt)
            if pd.notna(price) and pd.notna(ma_value):
                step_active = bool(float(price) <= float(ma_value) * float(step_active_max_ma_ratio))
        if last_0050 is not None and max_0050_step is not None and step_active:
            step = float(max_0050_step)
            raw_delta = raw_0050 - last_0050
            if step_mode == "buy_only" and raw_delta <= 0.0:
                target_0050 = raw_0050
            else:
                downside_step = step if step_mode == "both" else abs(raw_delta)
                target_0050 = last_0050 + max(min(raw_delta, step), -downside_step)
        if last_0050 is not None and abs(target_0050 - last_0050) < float(min_0050_delta):
            target_0050 = last_0050
            skipped += 1
        target["0050.TW"] = max(min(target_0050, 1.0), 0.0)

        ma_triggered = False
        if ma_series is not None:
            price = close_0050.get(dt)
            ma_value = ma_series.get(dt)
            ma_triggered = bool(pd.notna(price) and pd.notna(ma_value) and float(price) <= float(ma_value) * float(ma_ratio))
        if ma_triggered:
            if ma_0050_cap is not None and target.get("0050.TW", 0.0) > float(ma_0050_cap):
                target["0050.TW"] = float(ma_0050_cap)
                brake_events += 1
            if ma_00631l_cap is not None and target.get("00631L.TW", 0.0) > float(ma_00631l_cap):
                target["00631L.TW"] = float(ma_00631l_cap)
                leverage_cap_events += 1

        total_weight = sum(max(float(v), 0.0) for v in target.values())
        if total_weight > 1.0:
            scale = 1.0 / total_weight
            target = {ticker: max(float(weight), 0.0) * scale for ticker, weight in target.items()}
        if any(abs(float(target.get(ticker, 0.0)) - float(raw.get(ticker, 0.0))) > 1e-12 for ticker in set(target) | set(raw)):
            changed += 1
        adjusted = dict(event)
        adjusted["raw_target_weights"] = raw
        adjusted["target_weights"] = target
        adjusted["target_cash_weight"] = max(0.0, 1.0 - sum(float(v) for v in target.values()))
        adjusted_events.append(adjusted)
        last_0050 = float(target.get("0050.TW", 0.0))

    return adjusted_events, {
        "max_0050_step": max_0050_step,
        "step_mode": step_mode,
        "step_active_max_ma_ratio": step_active_max_ma_ratio,
        "min_0050_delta": float(min_0050_delta),
        "ma_window": ma_window,
        "ma_ratio": float(ma_ratio),
        "ma_0050_cap": ma_0050_cap,
        "ma_00631l_cap": ma_00631l_cap,
        "changed_events": int(changed),
        "skipped_0050_delta_events": int(skipped),
        "ma_0050_cap_events": int(brake_events),
        "ma_00631l_cap_events": int(leverage_cap_events),
    }


def _replay_multiticker(captured: dict[str, Any], *, overlay: dict[str, Any] | None = None) -> dict[str, Any]:
    prices = captured["prices"].copy()
    tickers = list(captured["tickers"])
    if overlay:
        events, overlay_report = _overlay_events(captured, **overlay)
    else:
        events = list(captured["events"])
        overlay_report = {"enabled": False}
    event_map = {pd.Timestamp(event["date"]).normalize(): event for event in events}
    dca_map: dict[pd.Timestamp, list[dict[str, Any]]] = {}
    for item in captured["dca_purchase_history"]:
        dca_map.setdefault(pd.Timestamp(item["date"]).normalize(), []).append(item)

    cash = INITIAL_CASH
    shares = {ticker: 0.0 for ticker in tickers}
    total_cost = 0.0
    contributions = 0.0
    rebalances = 0
    values: list[tuple[pd.Timestamp, float]] = []
    trade_log: list[dict[str, Any]] = []

    for dt, row in prices.iterrows():
        cash, dca_fees, dca_contrib = _apply_dca(dt, row, shares, cash, dca_map)
        total_cost += dca_fees
        contributions += dca_contrib
        total = cash + sum(shares[ticker] * float(row[ticker]) for ticker in tickers)

        if dt in event_map and total > 0:
            event = event_map[dt]
            target_weights = {ticker: float(event["target_weights"].get(ticker, 0.0)) for ticker in tickers}
            current_values = {ticker: shares[ticker] * float(row[ticker]) for ticker in tickers}
            target_values = {ticker: total * max(target_weights[ticker], 0.0) for ticker in tickers}

            fee = 0.0
            # Sells first to fund buys.
            for ticker in tickers:
                delta_value = target_values[ticker] - current_values[ticker]
                if delta_value >= 0:
                    continue
                sell_value = min(-delta_value, current_values[ticker])
                if sell_value <= 0:
                    continue
                fee_part = sell_value * (COMMISSION_RATE + ETF_SELL_TAX_RATE)
                shares[ticker] -= sell_value / float(row[ticker])
                cash += sell_value - fee_part
                fee += fee_part

            buy_orders: list[tuple[str, float]] = []
            for ticker in tickers:
                current_value = shares[ticker] * float(row[ticker])
                delta_value = target_values[ticker] - current_value
                if delta_value > 0:
                    buy_orders.append((ticker, delta_value))
            required_cash = sum(value * (1.0 + COMMISSION_RATE) for _, value in buy_orders)
            scale = min(1.0, cash / required_cash) if required_cash > 0 else 1.0
            for ticker, value in buy_orders:
                buy_value = value * scale
                if buy_value <= 0:
                    continue
                fee_part = buy_value * COMMISSION_RATE
                shares[ticker] += buy_value / float(row[ticker])
                cash -= buy_value + fee_part
                fee += fee_part

            total_cost += fee
            rebalances += 1
            total = cash + sum(shares[ticker] * float(row[ticker]) for ticker in tickers)
            trade_log.append({"date": str(dt.date()), "fee": float(fee), "value": float(total), "target_weights": target_weights})
        values.append((dt, cash + sum(shares[ticker] * float(row[ticker]) for ticker in tickers)))

    series = pd.Series([value for _, value in values], index=[dt for dt, _ in values], dtype=float)
    final_prices = prices.iloc[-1]
    final_value = float(series.iloc[-1])
    return {
        "metrics": _metrics(series, rebalances=rebalances, total_cost=total_cost, contributions=contributions),
        "final_weights": {
            ticker: float(shares[ticker] * float(final_prices[ticker]) / max(final_value, 1.0))
            for ticker in tickers
        },
        "final_cash_weight": float(cash / max(final_value, 1.0)),
        "overlay": overlay_report,
        "trade_log": trade_log,
        "equity_curve": [{"date": str(dt.date()), "value": float(value)} for dt, value in values],
    }


def _score(row: dict[str, Any], baseline: dict[str, Any]) -> float:
    final_delta_pct = float(row["final_value"]) / max(float(baseline["final_value"]), 1.0) - 1.0
    sharpe_delta = float(row["sharpe_ratio"]) - float(baseline["sharpe_ratio"])
    mdd_improvement = float(row["max_drawdown"]) - float(baseline["max_drawdown"])
    cost_delta_pct = (float(row["total_cost"]) - float(baseline["total_cost"])) / max(float(baseline["final_value"]), 1.0)
    return float(final_delta_pct + 0.10 * sharpe_delta + 0.50 * mdd_improvement - 0.25 * cost_delta_pct)


def _variant_name(
    step: float | None,
    step_mode: str,
    step_active_max_ma_ratio: float | None,
    ma_window: int | None,
    ma_0050_cap: float | None,
    ma_00631l_cap: float | None,
) -> str:
    step_part = "step_off" if step is None else f"step{int(round(step * 10000)):04d}bp"
    mode_part = step_mode
    step_gate = "stepgate_off" if step_active_max_ma_ratio is None else f"stepgate{int(round(step_active_max_ma_ratio * 100)):03d}"
    ma_part = "ma_off" if ma_window is None else f"ma{ma_window}"
    cap_0050 = "0050off" if ma_0050_cap is None else f"0050cap{int(round(ma_0050_cap * 100)):02d}"
    cap_631l = "631loff" if ma_00631l_cap is None else f"631lcap{int(round(ma_00631l_cap * 100)):02d}"
    return f"{step_part}_{mode_part}_{step_gate}_{ma_part}_{cap_0050}_{cap_631l}"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=START)
    parser.add_argument("--end", default=END)
    parser.add_argument("--payload", default=str(LATEST_PAYLOAD))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--steps", default="none,0.024,0.026,0.03,0.032,0.036")
    parser.add_argument("--step-modes", default="both")
    parser.add_argument("--step-active-max-ma-ratios", default="none")
    parser.add_argument("--ma-windows", default="none,60")
    parser.add_argument("--ma-ratio", type=float, default=1.0)
    parser.add_argument("--ma-0050-caps", default="none,0.30,0.38")
    parser.add_argument("--ma-00631l-caps", default="none,0.00,0.05,0.10")
    parser.add_argument("--min-0050-delta", type=float, default=0.0)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    payload_path = Path(args.payload)
    if not payload_path.is_absolute():
        payload_path = (PROJECT_ROOT / payload_path).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = (PROJECT_ROOT / output).resolve()

    captured = _capture_events("latest_group_a", payload_path, args.start, args.end)
    baseline_result = _replay_multiticker(captured)
    baseline = baseline_result["metrics"]
    rows = [{"variant": "latest_group_a_raw", **baseline, "score": 0.0}]
    details = {"latest_group_a_raw": baseline_result}

    step_modes = [item.strip() for item in args.step_modes.split(",") if item.strip()]
    unknown_modes = [item for item in step_modes if item not in {"both", "buy_only"}]
    if unknown_modes:
        raise ValueError(f"Unknown --step-modes: {unknown_modes}")

    for step in _parse_float_list(args.steps):
        for step_mode in step_modes:
            for step_active_max_ma_ratio in _parse_float_list(args.step_active_max_ma_ratios):
                for ma_window in _parse_int_list(args.ma_windows):
                    for ma_0050_cap in _parse_float_list(args.ma_0050_caps):
                        for ma_00631l_cap in _parse_float_list(args.ma_00631l_caps):
                            if ma_window is None and (ma_0050_cap is not None or ma_00631l_cap is not None):
                                continue
                            if ma_window is None and step_active_max_ma_ratio is not None:
                                continue
                            overlay = {
                                "max_0050_step": step,
                                "step_mode": step_mode,
                                "step_active_max_ma_ratio": step_active_max_ma_ratio,
                                "min_0050_delta": float(args.min_0050_delta),
                                "ma_window": ma_window,
                                "ma_ratio": float(args.ma_ratio),
                                "ma_0050_cap": ma_0050_cap,
                                "ma_00631l_cap": ma_00631l_cap,
                            }
                            name = _variant_name(
                                step,
                                step_mode,
                                step_active_max_ma_ratio,
                                ma_window,
                                ma_0050_cap,
                                ma_00631l_cap,
                            )
                            result = _replay_multiticker(captured, overlay=overlay)
                            report = result["overlay"]
                            row = {
                                "variant": name,
                                "max_0050_step": step,
                                "step_mode": step_mode,
                                "step_active_max_ma_ratio": step_active_max_ma_ratio,
                                "ma_window": ma_window,
                                "ma_0050_cap": ma_0050_cap,
                                "ma_00631l_cap": ma_00631l_cap,
                                **result["metrics"],
                                "changed_events": int(report.get("changed_events", 0)),
                                "ma_0050_cap_events": int(report.get("ma_0050_cap_events", 0)),
                                "ma_00631l_cap_events": int(report.get("ma_00631l_cap_events", 0)),
                            }
                            row["score"] = _score(row, baseline)
                            rows.append(row)
                            details[name] = result

    ranked = sorted(rows, key=lambda item: (float(item["score"]), float(item["sharpe_ratio"]), float(item["final_value"])), reverse=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    csv_path = output.with_suffix(".csv")
    payload = {
        "experiment": "group_a_latest_multiticker_overlay_sweep",
        "method": "Replay latest Group A full ETF target weights. Sweep 0050 step plus MA-triggered 0050/00631L caps.",
        "payload": str(payload_path),
        "requested_window": {"start": args.start, "end": args.end},
        "actual_window": {"start": captured["actual_start"], "end": captured["actual_end"]},
        "baseline": "latest_group_a_raw",
        "top_variants": ranked[:20],
        "rows": rows,
        "details": {item["variant"]: details[item["variant"]] for item in ranked[:10]},
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(rows).sort_values("score", ascending=False).to_csv(csv_path, index=False, encoding="utf-8-sig")

    print(f"JSON: {output}")
    print(f"CSV:  {csv_path}")
    print("Top variants:")
    for row in ranked[:10]:
        print(
            f"{row['variant']}: score={row['score']:.5f}, final={row['final_value']:.2f}, "
            f"sharpe={row['sharpe_ratio']:.4f}, mdd={row['max_drawdown']:.4%}, cost={row['total_cost']:.2f}"
        )


if __name__ == "__main__":
    main()
