#!/usr/bin/env python3
"""Replay static Group A + 00679B sleeves from an existing Group A backtest.

This is a research overlay harness. It does not retrain the PPO model. It takes
the completed Group A daily equity curve as one sleeve, combines it with 00679B
close-to-close returns, and evaluates both ideal daily rebalancing and a more
practical monthly/drift rebalance rule with transaction costs.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = PROJECT_ROOT / "results" / "group_a_tdcc_latest_backtest_20240101_20260604.json"
DEFAULT_DB = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_00679b_overlay_sweep_20240102_20260604.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-backtest", default=str(DEFAULT_SOURCE))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument(
        "--weights",
        default="0.05,0.075,0.10,0.125,0.15,0.20",
        help="Comma-separated 00679B sleeve weights to evaluate.",
    )
    parser.add_argument("--drift-threshold", type=float, default=0.05)
    parser.add_argument(
        "--calendar-rebalance",
        default="monthly",
        choices=["monthly", "quarterly", "none"],
        help="Calendar rebalance schedule used in practical mode.",
    )
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--etf-sell-tax-rate", type=float, default=0.001)
    parser.add_argument(
        "--base-key",
        default="base_exact_backtest",
        choices=["base_exact_backtest", "latest_tdcc_overlay_replay"],
        help="Which source equity curve to use as the Group A sleeve.",
    )
    return parser.parse_args()


def _resolve(path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    return candidate


def _load_source_curve(path: Path, base_key: str) -> tuple[pd.Series, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if base_key == "latest_tdcc_overlay_replay":
        source = payload[base_key]
        metrics = source["metrics"]
        curve_rows = source["equity_curve"]
        curve = pd.Series(
            [float(row["value"]) for row in curve_rows],
            index=pd.to_datetime([row["date"] for row in curve_rows]),
            dtype=float,
        )
        return curve, metrics

    source = payload[base_key]
    actual_start = str(source["actual_start"])
    actual_end = str(source["actual_end"])
    values = [float(value) for value in source["equity_curve"]]
    return pd.Series(values, dtype=float), {
        "actual_start": actual_start,
        "actual_end": actual_end,
        "rows": len(values),
    }


def _load_prices(db_path: Path, start: str, end: str) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT dt, ticker, close
            FROM ohlcv
            WHERE ticker IN ('0050.TW', '00679B.TWO') AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [start, end],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        raise RuntimeError(f"No OHLCV rows between {start} and {end}")
    prices = rows.pivot(index="dt", columns="ticker", values="close").sort_index()
    prices.index = pd.to_datetime(prices.index)
    return prices.dropna(subset=["0050.TW", "00679B.TWO"])


def _attach_dates_if_needed(curve: pd.Series, prices: pd.DataFrame, source_meta: dict[str, Any]) -> pd.Series:
    if isinstance(curve.index, pd.DatetimeIndex):
        return curve.sort_index()
    start = str(source_meta["actual_start"])
    end = str(source_meta["actual_end"])
    dates = prices.loc[pd.Timestamp(start) : pd.Timestamp(end)].index
    if len(dates) < len(curve):
        raise RuntimeError(f"Not enough price dates for source curve: prices={len(dates)}, curve={len(curve)}")
    out = curve.copy()
    out.index = dates[: len(curve)]
    return out


def _metrics(values: pd.Series, rebalances: int = 0, total_cost: float = 0.0) -> dict[str, Any]:
    daily = values.pct_change().dropna()
    years = max((values.index[-1] - values.index[0]).days / 365.25, 1e-9)
    total_return = float(values.iloc[-1] / values.iloc[0] - 1.0)
    annual_return = float((values.iloc[-1] / values.iloc[0]) ** (1.0 / years) - 1.0)
    volatility = float(daily.std() * math.sqrt(252)) if len(daily) > 1 else 0.0
    sharpe = float((daily.mean() / daily.std()) * math.sqrt(252)) if len(daily) > 1 and daily.std() > 0 else 0.0
    downside = daily[daily < 0]
    sortino = (
        float((daily.mean() / downside.std()) * math.sqrt(252))
        if len(downside) > 1 and downside.std() > 0
        else 0.0
    )
    max_drawdown = float((values / values.cummax() - 1.0).min())
    return {
        "final_value": float(values.iloc[-1]),
        "total_return": total_return,
        "annual_return": annual_return,
        "volatility": volatility,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "max_drawdown": max_drawdown,
        "num_rebalances": int(rebalances),
        "total_cost": float(total_cost),
    }


def _daily_rebalanced_curve(group_returns: pd.Series, bond_returns: pd.Series, bond_weight: float) -> pd.Series:
    returns = (1.0 - bond_weight) * group_returns + bond_weight * bond_returns
    return 1_000_000.0 * (1.0 + returns).cumprod()


def _is_calendar_rebalance(
    date: pd.Timestamp,
    previous_date: pd.Timestamp | None,
    calendar_rebalance: str,
) -> bool:
    if previous_date is None:
        return True
    if calendar_rebalance == "none":
        return False
    if calendar_rebalance == "monthly":
        return date.month != previous_date.month or date.year != previous_date.year
    if calendar_rebalance == "quarterly":
        current_quarter = (date.month - 1) // 3
        previous_quarter = (previous_date.month - 1) // 3
        return current_quarter != previous_quarter or date.year != previous_date.year
    raise ValueError(f"Unsupported calendar rebalance mode: {calendar_rebalance}")


def _monthly_drift_curve(
    group_returns: pd.Series,
    bond_returns: pd.Series,
    *,
    bond_weight: float,
    drift_threshold: float,
    calendar_rebalance: str,
    commission_rate: float,
    etf_sell_tax_rate: float,
) -> tuple[pd.Series, list[dict[str, Any]]]:
    target_group = 1.0 - bond_weight
    group_value = 1_000_000.0 * target_group
    bond_value = 1_000_000.0 * bond_weight
    curve = []
    events: list[dict[str, Any]] = []
    previous_date: pd.Timestamp | None = None

    for date in group_returns.index:
        group_value *= 1.0 + float(group_returns.loc[date])
        bond_value *= 1.0 + float(bond_returns.loc[date])
        total = group_value + bond_value
        current_bond_weight = bond_value / total if total > 0 else 0.0
        calendar_triggered = _is_calendar_rebalance(date, previous_date, calendar_rebalance)
        drift_triggered = abs(current_bond_weight - bond_weight) >= drift_threshold
        should_rebalance = calendar_triggered or drift_triggered
        if should_rebalance:
            target_group_value = total * target_group
            target_bond_value = total * bond_weight
            group_trade = target_group_value - group_value
            bond_trade = target_bond_value - bond_value
            traded = abs(group_trade) + abs(bond_trade)
            sell_tax = max(-bond_trade, 0.0) * etf_sell_tax_rate
            cost = traded * commission_rate + sell_tax
            total_after_cost = total - cost
            group_value = total_after_cost * target_group
            bond_value = total_after_cost * bond_weight
            events.append(
                {
                    "date": str(date.date()),
                    "reason": "calendar" if calendar_triggered else "drift",
                    "pre_bond_weight": float(current_bond_weight),
                    "target_bond_weight": float(bond_weight),
                    "traded_notional": float(traded),
                    "cost": float(cost),
                }
            )
            total = total_after_cost
        curve.append((date, total))
        previous_date = date

    out = pd.Series([value for _, value in curve], index=[date for date, _ in curve], dtype=float)
    return out, events


def _parse_weights(value: str) -> list[float]:
    weights = sorted({float(item.strip()) for item in value.split(",") if item.strip()})
    for weight in weights:
        if not 0.0 <= weight <= 1.0:
            raise ValueError("--weights entries must be between 0 and 1")
    return weights


def main() -> None:
    args = _parse_args()
    source_path = _resolve(args.source_backtest)
    db_path = _resolve(args.db)
    raw_curve, source_meta = _load_source_curve(source_path, args.base_key)
    start = str(source_meta.get("actual_start") or raw_curve.index.min().date())
    end = str(source_meta.get("actual_end") or raw_curve.index.max().date())
    prices = _load_prices(db_path, start, end)
    group_curve = _attach_dates_if_needed(raw_curve, prices, source_meta)
    prices = prices.reindex(group_curve.index).dropna(subset=["00679B.TWO"])
    group_curve = group_curve.reindex(prices.index)
    group_returns = group_curve.pct_change().fillna(0.0)
    bond_returns = prices["00679B.TWO"].pct_change().fillna(0.0)

    rows = []
    curves = pd.DataFrame(index=group_curve.index)
    curves["group_a_value"] = group_curve
    summaries: dict[str, Any] = {
        "100pct_group_a": _metrics(group_curve),
    }
    rows.append({"variant": "100pct_group_a", "mode": "source", "00679b_weight": 0.0, **summaries["100pct_group_a"]})

    practical_events: dict[str, list[dict[str, Any]]] = {}
    for bond_weight in _parse_weights(args.weights):
        label = f"{100 - int(round(bond_weight * 100)):02d}_{int(round(bond_weight * 100)):02d}"
        daily_name = f"{label}_daily_rebalanced"
        daily_curve = _daily_rebalanced_curve(group_returns, bond_returns, bond_weight)
        daily_metrics = _metrics(daily_curve)
        summaries[daily_name] = daily_metrics
        rows.append({"variant": daily_name, "mode": "daily_rebalanced", "00679b_weight": bond_weight, **daily_metrics})
        curves[f"value_{daily_name}"] = daily_curve

        practical_name = f"{label}_{args.calendar_rebalance}_or_drift_fee"
        practical_curve, events = _monthly_drift_curve(
            group_returns,
            bond_returns,
            bond_weight=bond_weight,
            drift_threshold=float(args.drift_threshold),
            calendar_rebalance=str(args.calendar_rebalance),
            commission_rate=float(args.commission_rate),
            etf_sell_tax_rate=float(args.etf_sell_tax_rate),
        )
        practical_metrics = _metrics(
            practical_curve,
            rebalances=len(events),
            total_cost=sum(float(event["cost"]) for event in events),
        )
        summaries[practical_name] = practical_metrics
        practical_events[practical_name] = events
        rows.append({"variant": practical_name, "mode": f"{args.calendar_rebalance}_or_drift_fee", "00679b_weight": bond_weight, **practical_metrics})
        curves[f"value_{practical_name}"] = practical_curve

    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    csv_path = output.with_suffix(".csv")
    curve_path = output.with_name(output.stem + "_curve.csv")
    report = {
        "experiment": "group_a_00679b_overlay_sweep",
        "method_note": (
            "Research replay only. Uses an existing Group A daily equity curve as one sleeve "
            "and 00679B close-to-close returns as the defensive sleeve. Practical mode "
            "rebalances on month starts or target-weight drift and estimates commission/tax."
        ),
        "source_backtest": str(source_path.resolve()),
        "source_base_key": args.base_key,
        "window": {
            "start": str(group_curve.index[0].date()),
            "end": str(group_curve.index[-1].date()),
            "rows": int(len(group_curve)),
        },
        "settings": {
            "weights": _parse_weights(args.weights),
            "drift_threshold": float(args.drift_threshold),
            "calendar_rebalance": str(args.calendar_rebalance),
            "commission_rate": float(args.commission_rate),
            "etf_sell_tax_rate": float(args.etf_sell_tax_rate),
        },
        "summary": summaries,
        "practical_rebalance_events": practical_events,
        "outputs": {
            "json": str(output),
            "csv": str(csv_path),
            "curve_csv": str(curve_path),
        },
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    curves.to_csv(curve_path, encoding="utf-8-sig")

    print(f"JSON: {output}")
    print(f"CSV:  {csv_path}")
    print(f"Curve CSV: {curve_path}")
    print(f"Window: {group_curve.index[0].date()} ~ {group_curve.index[-1].date()} ({len(group_curve)} rows)")
    for row in rows:
        if row["mode"] == "source" or str(row["mode"]).endswith("_or_drift_fee"):
            print(
                f"{row['variant']}: final={row['final_value']:.2f}, "
                f"sharpe={row['sharpe_ratio']:.4f}, mdd={row['max_drawdown']:.4%}, "
                f"rebalances={row['num_rebalances']}, cost={row['total_cost']:.2f}"
            )


if __name__ == "__main__":
    main()
