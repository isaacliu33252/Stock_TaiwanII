#!/usr/bin/env python3
"""Backtest a regime selector overlay for Group A + 00679B."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = PROJECT_ROOT / "results" / "group_a_tdcc_latest_backtest_20240101_20260605.json"
DEFAULT_DB = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_selector_overlay_20240102_20260604.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-backtest", default=str(DEFAULT_SOURCE))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--normal-bond-weight", type=float, default=0.00)
    parser.add_argument("--caution-bond-weight", type=float, default=0.05)
    parser.add_argument("--risk-off-bond-weight", type=float, default=0.10)
    parser.add_argument("--severe-bond-weight", type=float, default=0.15)
    parser.add_argument("--caution-drawdown", type=float, default=-0.06)
    parser.add_argument("--risk-off-drawdown", type=float, default=-0.12)
    parser.add_argument("--severe-drawdown", type=float, default=-0.20)
    parser.add_argument("--caution-momentum21", type=float, default=-0.03)
    parser.add_argument("--risk-off-momentum21", type=float, default=-0.08)
    parser.add_argument("--severe-momentum21", type=float, default=-0.15)
    parser.add_argument("--calendar-rebalance", choices=["quarterly", "monthly", "none"], default="quarterly")
    parser.add_argument("--drift-threshold", type=float, default=0.05)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--etf-sell-tax-rate", type=float, default=0.001)
    return parser.parse_args()


def _resolve(path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    return candidate


def _load_group_curve(path: Path) -> pd.Series:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload["latest_tdcc_overlay_replay"]["equity_curve"]
    return pd.Series(
        [float(row["value"]) for row in rows],
        index=pd.to_datetime([row["date"] for row in rows]),
        dtype=float,
    ).sort_index()


def _load_00679b(db_path: Path, start: str, end: str) -> pd.Series:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT dt, close
            FROM ohlcv
            WHERE ticker = '00679B.TWO' AND dt BETWEEN ? AND ?
            ORDER BY dt
            """,
            [start, end],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        raise RuntimeError(f"No 00679B rows between {start} and {end}")
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows.set_index("dt")["close"].astype(float).sort_index()


def _metrics(values: pd.Series, *, rebalances: int, total_cost: float) -> dict[str, Any]:
    daily = values.pct_change().dropna()
    years = max((values.index[-1] - values.index[0]).days / 365.25, 1e-9)
    return {
        "final_value": float(values.iloc[-1]),
        "total_return": float(values.iloc[-1] / values.iloc[0] - 1.0),
        "annual_return": float((values.iloc[-1] / values.iloc[0]) ** (1.0 / years) - 1.0),
        "sharpe_ratio": (
            float((daily.mean() / daily.std()) * math.sqrt(252))
            if len(daily) > 1 and daily.std() > 0
            else 0.0
        ),
        "max_drawdown": float((values / values.cummax() - 1.0).min()),
        "volatility": float(daily.std() * math.sqrt(252)) if len(daily) > 1 else 0.0,
        "num_rebalances": int(rebalances),
        "total_cost": float(total_cost),
    }


def _calendar_due(date: pd.Timestamp, previous_date: pd.Timestamp | None, mode: str) -> bool:
    if previous_date is None:
        return True
    if mode == "none":
        return False
    if mode == "monthly":
        return date.year != previous_date.year or date.month != previous_date.month
    if mode == "quarterly":
        return date.year != previous_date.year or (date.month - 1) // 3 != (previous_date.month - 1) // 3
    raise ValueError(f"Unsupported calendar mode: {mode}")


def _target_for_state(row: pd.Series, args: argparse.Namespace) -> tuple[float, str]:
    drawdown = float(row["group_drawdown_lag1"])
    momentum21 = float(row["group_momentum21_lag1"])
    if drawdown <= float(args.severe_drawdown) or momentum21 <= float(args.severe_momentum21):
        return float(args.severe_bond_weight), "severe"
    if drawdown <= float(args.risk_off_drawdown) or momentum21 <= float(args.risk_off_momentum21):
        return float(args.risk_off_bond_weight), "risk_off"
    if drawdown <= float(args.caution_drawdown) or momentum21 <= float(args.caution_momentum21):
        return float(args.caution_bond_weight), "caution"
    return float(args.normal_bond_weight), "normal"


def _simulate(group_curve: pd.Series, bond_prices: pd.Series, args: argparse.Namespace) -> tuple[pd.Series, list[dict[str, Any]], pd.DataFrame]:
    frame = pd.DataFrame({"group_value": group_curve}).join(bond_prices.rename("bond_price"), how="inner")
    frame["group_return"] = frame["group_value"].pct_change().fillna(0.0)
    frame["bond_return"] = frame["bond_price"].pct_change().fillna(0.0)
    group_peak = frame["group_value"].cummax()
    frame["group_drawdown_lag1"] = (frame["group_value"] / group_peak - 1.0).shift(1).fillna(0.0)
    frame["group_momentum21_lag1"] = frame["group_value"].pct_change(21).shift(1).fillna(0.0)
    targets = frame.apply(lambda row: _target_for_state(row, args), axis=1)
    frame["target_bond_weight"] = [float(item[0]) for item in targets]
    frame["regime"] = [str(item[1]) for item in targets]

    first_bond_weight = float(frame["target_bond_weight"].iloc[0])
    group_value = 1_000_000.0 * (1.0 - first_bond_weight)
    bond_value = 1_000_000.0 * first_bond_weight
    last_target_bond = first_bond_weight
    previous_date: pd.Timestamp | None = None
    curve = []
    events: list[dict[str, Any]] = []

    for date, row in frame.iterrows():
        group_value *= 1.0 + float(row["group_return"])
        bond_value *= 1.0 + float(row["bond_return"])
        total = group_value + bond_value
        current_bond_weight = bond_value / total if total > 0 else 0.0
        target_bond = float(row["target_bond_weight"])
        target_changed = abs(target_bond - last_target_bond) > 1e-12
        calendar_triggered = _calendar_due(date, previous_date, str(args.calendar_rebalance))
        drift_triggered = abs(current_bond_weight - target_bond) >= float(args.drift_threshold)
        if target_changed or calendar_triggered or drift_triggered:
            target_group_value = total * (1.0 - target_bond)
            target_bond_value = total * target_bond
            group_trade = target_group_value - group_value
            bond_trade = target_bond_value - bond_value
            traded = abs(group_trade) + abs(bond_trade)
            sell_tax = max(-bond_trade, 0.0) * float(args.etf_sell_tax_rate)
            cost = traded * float(args.commission_rate) + sell_tax
            total_after_cost = total - cost
            group_value = total_after_cost * (1.0 - target_bond)
            bond_value = total_after_cost * target_bond
            total = total_after_cost
            reason = "target_change" if target_changed else ("calendar" if calendar_triggered else "drift")
            events.append(
                {
                    "date": str(date.date()),
                    "reason": reason,
                    "regime": str(row["regime"]),
                    "pre_bond_weight": float(current_bond_weight),
                    "target_bond_weight": float(target_bond),
                    "traded_notional": float(traded),
                    "cost": float(cost),
                }
            )
            last_target_bond = target_bond
        curve.append((date, total))
        previous_date = date

    values = pd.Series([value for _, value in curve], index=[date for date, _ in curve], dtype=float)
    return values, events, frame


def main() -> None:
    args = _parse_args()
    source = _resolve(args.source_backtest)
    db_path = _resolve(args.db)
    group_curve = _load_group_curve(source)
    bond_prices = _load_00679b(db_path, str(group_curve.index[0].date()), str(group_curve.index[-1].date()))
    values, events, frame = _simulate(group_curve, bond_prices, args)
    total_cost = sum(float(event["cost"]) for event in events)
    metrics = _metrics(values, rebalances=len(events), total_cost=total_cost)

    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    csv_path = output.with_suffix(".csv")
    curve_path = output.with_name(output.stem + "_curve.csv")
    report = {
        "experiment": "group_a_selector_overlay",
        "method_note": (
            "No PPO retraining. Uses previous-day Group A drawdown and 21-day momentum "
            "to choose a 00679B sleeve, then applies quarterly/calendar/drift rebalancing."
        ),
        "source_backtest": str(source.resolve()),
        "window": {
            "start": str(values.index[0].date()),
            "end": str(values.index[-1].date()),
            "rows": int(len(values)),
        },
        "settings": {
            "normal_bond_weight": float(args.normal_bond_weight),
            "caution_bond_weight": float(args.caution_bond_weight),
            "risk_off_bond_weight": float(args.risk_off_bond_weight),
            "severe_bond_weight": float(args.severe_bond_weight),
            "caution_drawdown": float(args.caution_drawdown),
            "risk_off_drawdown": float(args.risk_off_drawdown),
            "severe_drawdown": float(args.severe_drawdown),
            "caution_momentum21": float(args.caution_momentum21),
            "risk_off_momentum21": float(args.risk_off_momentum21),
            "severe_momentum21": float(args.severe_momentum21),
            "calendar_rebalance": str(args.calendar_rebalance),
            "drift_threshold": float(args.drift_threshold),
            "commission_rate": float(args.commission_rate),
            "etf_sell_tax_rate": float(args.etf_sell_tax_rate),
        },
        "metrics": metrics,
        "regime_counts": {str(k): int(v) for k, v in frame["regime"].value_counts().to_dict().items()},
        "rebalance_events": events,
        "outputs": {"json": str(output), "csv": str(csv_path), "curve_csv": str(curve_path)},
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame([{"strategy": "group_a_selector_overlay", **metrics}]).to_csv(csv_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(
        {
            "date": values.index.date.astype(str),
            "value": values.values,
            "target_bond_weight": frame["target_bond_weight"].values,
            "regime": frame["regime"].values,
            "group_drawdown_lag1": frame["group_drawdown_lag1"].values,
            "group_momentum21_lag1": frame["group_momentum21_lag1"].values,
        }
    ).to_csv(curve_path, index=False, encoding="utf-8-sig")

    print(f"JSON: {output}")
    print(f"CSV:  {csv_path}")
    print(f"Curve CSV: {curve_path}")
    print(
        f"Selector: final={metrics['final_value']:.2f}, annual={metrics['annual_return']:.4%}, "
        f"sharpe={metrics['sharpe_ratio']:.4f}, mdd={metrics['max_drawdown']:.4%}, "
        f"rebalances={metrics['num_rebalances']}, cost={metrics['total_cost']:.2f}"
    )
    print(f"Regime counts: {report['regime_counts']}")


if __name__ == "__main__":
    main()
