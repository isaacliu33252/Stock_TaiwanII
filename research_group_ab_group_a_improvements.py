#!/usr/bin/env python3
"""Research four improvement paths for Group A and Group A+B.

The script does not retrain any model. It consumes the latest saved backtest
outputs and runs practical overlays:

1. constrained dynamic Group A/B allocation,
2. approximate Group A component-level risk haircuts,
3. execution threshold sweeps for the A/B allocator,
4. segment diagnostics by calendar year and drawdown phase.
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
DEFAULT_AB_CURVE = PROJECT_ROOT / "results" / "group_ab_latest_no2884_backtest_20240101_20260605_curve.csv"
DEFAULT_GROUP_A = PROJECT_ROOT / "results" / "group_a_tdcc_latest_backtest_20240101_20260605.json"
DEFAULT_DB = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_ab_group_a_improvement_research_20240102_20260604.json"
GROUP_A_TICKERS = ["0050.TW", "00631L.TW", "00632R.TW"]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ab-curve-csv", default=str(DEFAULT_AB_CURVE))
    parser.add_argument("--group-a-json", default=str(DEFAULT_GROUP_A))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--transfer-cost-rate", type=float, default=0.001425)
    return parser.parse_args()


def _resolve(path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    return candidate


def _metrics(values: pd.Series, *, events: int = 0, cost: float = 0.0) -> dict[str, Any]:
    values = values.dropna().astype(float)
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
        "num_events": int(events),
        "total_cost": float(cost),
    }


def _calendar_due(date: pd.Timestamp, prev: pd.Timestamp | None, mode: str) -> bool:
    if prev is None:
        return True
    if mode == "monthly":
        return date.year != prev.year or date.month != prev.month
    if mode == "quarterly":
        return date.year != prev.year or (date.month - 1) // 3 != (prev.month - 1) // 3
    if mode == "none":
        return False
    raise ValueError(mode)


def _load_ab_curve(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig")
    frame["date"] = pd.to_datetime(frame["date"])
    return frame.set_index("date").sort_index()


def _load_group_a(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_prices(db_path: Path, tickers: list[str], start: str, end: str) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT dt, ticker, close
            FROM ohlcv
            WHERE ticker IN (SELECT * FROM UNNEST(?)) AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [tickers, start, end],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        raise RuntimeError(f"No OHLCV rows for {tickers} between {start} and {end}")
    rows["dt"] = pd.to_datetime(rows["dt"])
    prices = rows.pivot(index="dt", columns="ticker", values="close").sort_index()
    return prices.ffill().dropna(how="all")


def _practical_ab_curve(
    a_returns: pd.Series,
    b_returns: pd.Series,
    targets: pd.Series,
    *,
    transfer_cost_rate: float,
    drift_threshold: float = 0.05,
    min_transfer_notional: float = 0.0,
    calendar_rebalance: str = "quarterly",
) -> tuple[pd.Series, list[dict[str, Any]]]:
    first_target = float(targets.iloc[0])
    a_value = 2_000_000.0 * first_target
    b_value = 2_000_000.0 * (1.0 - first_target)
    prev: pd.Timestamp | None = None
    last_target = first_target
    values: list[tuple[pd.Timestamp, float]] = []
    events: list[dict[str, Any]] = []

    for date in a_returns.index:
        a_value *= 1.0 + float(a_returns.loc[date])
        b_value *= 1.0 + float(b_returns.loc[date])
        total = a_value + b_value
        current_a = a_value / total if total > 0 else 0.0
        target_a = float(targets.loc[date])
        target_changed = abs(target_a - last_target) > 1e-12
        calendar = _calendar_due(date, prev, calendar_rebalance)
        drift = abs(current_a - target_a) >= drift_threshold
        transfer = abs(total * target_a - a_value)
        if (target_changed or calendar or drift) and transfer >= min_transfer_notional:
            cost = transfer * transfer_cost_rate
            total -= cost
            a_value = total * target_a
            b_value = total * (1.0 - target_a)
            events.append(
                {
                    "date": str(date.date()),
                    "reason": "target_change" if target_changed else ("calendar" if calendar else "drift"),
                    "pre_group_a_weight": float(current_a),
                    "target_group_a_weight": float(target_a),
                    "transfer_notional": float(transfer),
                    "cost": float(cost),
                }
            )
            last_target = target_a
        values.append((date, total))
        prev = date

    return pd.Series([v for _, v in values], index=[d for d, _ in values], dtype=float), events


def _fixed_targets(index: pd.Index, weight: float) -> pd.Series:
    return pd.Series(float(weight), index=index, dtype=float)


def _rolling_sharpe(ret: pd.Series, lookback: int) -> pd.Series:
    mean = ret.rolling(lookback).mean()
    std = ret.rolling(lookback).std()
    return (mean / std).replace([float("inf"), -float("inf")], 0.0).fillna(0.0) * math.sqrt(252)


def _dynamic_targets(a_returns: pd.Series, b_returns: pd.Series, *, lookback: int, band: float) -> pd.Series:
    a_rel = (1.0 + a_returns).rolling(lookback).apply(lambda x: float(x.prod() - 1.0), raw=False)
    b_rel = (1.0 + b_returns).rolling(lookback).apply(lambda x: float(x.prod() - 1.0), raw=False)
    a_sharpe = _rolling_sharpe(a_returns, lookback)
    b_sharpe = _rolling_sharpe(b_returns, lookback)
    score = (a_rel - b_rel).fillna(0.0) + 0.03 * (a_sharpe - b_sharpe).fillna(0.0)
    lagged = score.shift(1).fillna(0.0)
    target = pd.Series(0.625, index=a_returns.index, dtype=float)
    target[lagged > band] = 0.70
    target[(lagged > band / 2.0) & (lagged <= band)] = 0.65
    target[(lagged < -band / 2.0) & (lagged >= -band)] = 0.60
    target[lagged < -band] = 0.55
    return target


def _hold_targets_until_calendar(index: pd.Index, raw_targets: pd.Series, mode: str) -> pd.Series:
    held = []
    prev: pd.Timestamp | None = None
    current = float(raw_targets.iloc[0])
    for date in index:
        if _calendar_due(pd.Timestamp(date), prev, mode):
            current = float(raw_targets.loc[date])
        held.append(current)
        prev = pd.Timestamp(date)
    return pd.Series(held, index=index, dtype=float)


def _run_ab_dynamic_and_execution(ab: pd.DataFrame, transfer_cost_rate: float) -> tuple[list[dict[str, Any]], dict[str, pd.Series]]:
    a_returns = ab["group_a_value"].pct_change().fillna(0.0)
    b_returns = ab["group_b_value"].pct_change().fillna(0.0)
    rows: list[dict[str, Any]] = []
    curves: dict[str, pd.Series] = {}

    fixed = _fixed_targets(ab.index, 0.625)
    for min_transfer in [0.0, 25_000.0, 50_000.0, 100_000.0, 200_000.0]:
        name = f"fixed_62_5_min_transfer_{int(min_transfer)}"
        curve, events = _practical_ab_curve(
            a_returns,
            b_returns,
            fixed,
            transfer_cost_rate=transfer_cost_rate,
            min_transfer_notional=min_transfer,
        )
        curves[name] = curve
        rows.append({"family": "execution_threshold", "variant": name, **_metrics(curve, events=len(events), cost=sum(e["cost"] for e in events))})

    for lookback in [42, 63, 84, 126]:
        for band in [0.015, 0.03, 0.05, 0.08]:
            targets = _dynamic_targets(a_returns, b_returns, lookback=lookback, band=band)
            targets = _hold_targets_until_calendar(ab.index, targets, "quarterly")
            name = f"dynamic_lb{lookback}_band{band:.3f}"
            curve, events = _practical_ab_curve(
                a_returns,
                b_returns,
                targets,
                transfer_cost_rate=transfer_cost_rate,
                min_transfer_notional=50_000.0,
            )
            curves[name] = curve
            row = {
                "family": "dynamic_ab",
                "variant": name,
                "lookback": lookback,
                "band": band,
                "target_counts": {str(k): int(v) for k, v in targets.value_counts().sort_index().to_dict().items()},
                **_metrics(curve, events=len(events), cost=sum(e["cost"] for e in events)),
            }
            rows.append(row)

    return rows, curves


def _target_weights_by_event(group_a: dict[str, Any], dates: pd.DatetimeIndex) -> pd.DataFrame:
    events = group_a["latest_tdcc_overlay_replay"]["events"]
    event_map = {pd.Timestamp(e["date"]): e["target_weights"] | {"cash": e.get("target_cash_weight", 0.0)} for e in events}
    current = {ticker: 0.0 for ticker in GROUP_A_TICKERS}
    current["cash"] = 1.0
    rows = []
    for date in dates:
        if date in event_map:
            current = {ticker: float(event_map[date].get(ticker, 0.0)) for ticker in GROUP_A_TICKERS}
            current["cash"] = float(event_map[date].get("cash", 0.0))
        rows.append(current.copy())
    return pd.DataFrame(rows, index=dates).fillna(0.0)


def _simulate_group_a_component_overlay(
    group_a: dict[str, Any],
    prices: pd.DataFrame,
    *,
    drawdown_trigger: float,
    momentum_trigger: float,
    haircut: float,
    min_trade_notional: float,
    commission_rate: float = 0.001425,
    sell_tax_rate: float = 0.001,
) -> tuple[pd.Series, list[dict[str, Any]], pd.DataFrame]:
    curve_rows = group_a["latest_tdcc_overlay_replay"]["equity_curve"]
    dates = pd.to_datetime([row["date"] for row in curve_rows])
    prices = prices.reindex(dates).ffill().dropna()
    dates = prices.index
    base_weights = _target_weights_by_event(group_a, pd.DatetimeIndex(dates))
    returns = prices.pct_change().fillna(0.0)
    drawdowns = (prices / prices.cummax() - 1.0).shift(1).fillna(0.0)
    momentum21 = prices.pct_change(21).shift(1).fillna(0.0)

    holdings = {ticker: 0.0 for ticker in GROUP_A_TICKERS}
    cash = 1_000_000.0
    values = []
    events: list[dict[str, Any]] = []
    adjusted_rows = []
    prev_weights: dict[str, float] | None = None

    for date in dates:
        for ticker in GROUP_A_TICKERS:
            holdings[ticker] *= 1.0 + float(returns.loc[date, ticker])
        total = cash + sum(holdings.values())
        target = {ticker: float(base_weights.loc[date, ticker]) for ticker in GROUP_A_TICKERS}
        target["cash"] = float(base_weights.loc[date, "cash"])
        haircut_tickers = []
        for ticker in GROUP_A_TICKERS:
            weak = float(drawdowns.loc[date, ticker]) <= drawdown_trigger and float(momentum21.loc[date, ticker]) <= momentum_trigger
            if weak and target[ticker] > 0:
                released = target[ticker] * (1.0 - haircut)
                target[ticker] *= haircut
                target["cash"] += released
                haircut_tickers.append(ticker)
        total_weight = sum(target.values())
        if total_weight > 0:
            target = {k: v / total_weight for k, v in target.items()}
        changed = prev_weights is None or any(abs(target[k] - prev_weights.get(k, 0.0)) > 1e-12 for k in target)
        trade_notional = sum(abs(total * target[t] - holdings[t]) for t in GROUP_A_TICKERS)
        if changed and trade_notional >= min_trade_notional:
            sells = sum(max(holdings[t] - total * target[t], 0.0) for t in GROUP_A_TICKERS)
            cost = trade_notional * commission_rate + sells * sell_tax_rate
            total_after_cost = total - cost
            holdings = {ticker: total_after_cost * target[ticker] for ticker in GROUP_A_TICKERS}
            cash = total_after_cost * target["cash"]
            total = total_after_cost
            events.append(
                {
                    "date": str(date.date()),
                    "target_weights": target.copy(),
                    "haircut_tickers": haircut_tickers,
                    "trade_notional": float(trade_notional),
                    "cost": float(cost),
                }
            )
            prev_weights = target.copy()
        values.append((date, total))
        adjusted_rows.append({"date": date, **target, "haircut_tickers": ",".join(haircut_tickers)})

    series = pd.Series([v for _, v in values], index=[d for d, _ in values], dtype=float)
    adjusted = pd.DataFrame(adjusted_rows).set_index("date")
    return series, events, adjusted


def _run_group_a_component(group_a: dict[str, Any], db_path: Path) -> tuple[list[dict[str, Any]], dict[str, pd.Series]]:
    curve_rows = group_a["latest_tdcc_overlay_replay"]["equity_curve"]
    start = curve_rows[0]["date"]
    end = curve_rows[-1]["date"]
    prices = _load_prices(db_path, GROUP_A_TICKERS, start, end)
    rows: list[dict[str, Any]] = []
    curves: dict[str, pd.Series] = {}
    for drawdown in [-0.12, -0.18, -0.25]:
        for momentum in [-0.04, -0.08, -0.12]:
            for haircut in [0.5, 0.7]:
                name = f"component_dd{abs(drawdown):.2f}_mom{abs(momentum):.2f}_haircut{haircut:.1f}"
                curve, events, _ = _simulate_group_a_component_overlay(
                    group_a,
                    prices,
                    drawdown_trigger=drawdown,
                    momentum_trigger=momentum,
                    haircut=haircut,
                    min_trade_notional=50_000.0,
                )
                curves[name] = curve
                rows.append(
                    {
                        "family": "group_a_component_risk",
                        "variant": name,
                        "drawdown_trigger": drawdown,
                        "momentum_trigger": momentum,
                        "haircut": haircut,
                        "haircut_event_count": sum(1 for e in events if e["haircut_tickers"]),
                        **_metrics(curve, events=len(events), cost=sum(e["cost"] for e in events)),
                    }
                )
    return rows, curves


def _segment_rows(curves: dict[str, pd.Series]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, curve in curves.items():
        curve = curve.dropna()
        for year, part in curve.groupby(curve.index.year):
            if len(part) > 5:
                rows.append({"family": "segment_year", "variant": name, "segment": str(year), **_metrics(part)})
        drawdown = curve / curve.cummax() - 1.0
        phase = pd.Series("normal", index=curve.index)
        phase[drawdown <= -0.10] = "drawdown_10"
        phase[drawdown <= -0.20] = "drawdown_20"
        for label in ["normal", "drawdown_10", "drawdown_20"]:
            part = curve[phase == label]
            if len(part) > 5:
                rows.append({"family": "segment_drawdown_phase", "variant": name, "segment": label, **_metrics(part)})
    return rows


def main() -> None:
    args = _parse_args()
    ab_path = _resolve(args.ab_curve_csv)
    group_a_path = _resolve(args.group_a_json)
    db_path = _resolve(args.db)
    output = _resolve(args.output)

    ab = _load_ab_curve(ab_path)
    group_a = _load_group_a(group_a_path)
    ab_rows, ab_curves = _run_ab_dynamic_and_execution(ab, float(args.transfer_cost_rate))
    group_a_rows, group_a_curves = _run_group_a_component(group_a, db_path)

    baseline_curves = {
        "group_a_tdcc_latest": ab["group_a_value"],
        "group_b_latest_no2884": ab["group_b_value"],
    }
    fixed_625 = ab_curves["fixed_62_5_min_transfer_0"]
    baseline_curves["ab_fixed_62_5"] = fixed_625
    all_curves = {**baseline_curves, **ab_curves, **group_a_curves}
    segment_rows = _segment_rows(
        {
            "group_a_tdcc_latest": baseline_curves["group_a_tdcc_latest"],
            "group_b_latest_no2884": baseline_curves["group_b_latest_no2884"],
            "ab_fixed_62_5": fixed_625,
            "best_dynamic_ab": max(
                (row for row in ab_rows if row["family"] == "dynamic_ab"),
                key=lambda row: (row["sharpe_ratio"], row["final_value"]),
            )
            and ab_curves[
                max(
                    (row for row in ab_rows if row["family"] == "dynamic_ab"),
                    key=lambda row: (row["sharpe_ratio"], row["final_value"]),
                )["variant"]
            ],
        }
    )

    rows = ab_rows + group_a_rows + segment_rows
    curve_frame = pd.DataFrame({name: curve for name, curve in all_curves.items()})
    curve_frame.index.name = "date"

    output.parent.mkdir(parents=True, exist_ok=True)
    csv_path = output.with_suffix(".csv")
    curve_path = output.with_name(output.stem + "_curve.csv")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    curve_frame.to_csv(curve_path, encoding="utf-8-sig")

    best_dynamic = max((row for row in ab_rows if row["family"] == "dynamic_ab"), key=lambda row: (row["sharpe_ratio"], row["final_value"]))
    best_exec = max((row for row in ab_rows if row["family"] == "execution_threshold"), key=lambda row: (row["sharpe_ratio"], row["final_value"]))
    best_component = max(group_a_rows, key=lambda row: (row["sharpe_ratio"], row["final_value"]))
    report = {
        "experiment": "group_ab_group_a_improvement_research",
        "method_note": (
            "No retraining. A/B overlays use existing group equity curves. Group A component risk is an "
            "approximate event-weight replay because the source JSON does not include full daily shares."
        ),
        "sources": {
            "ab_curve_csv": str(ab_path.resolve()),
            "group_a_json": str(group_a_path.resolve()),
            "db": str(db_path.resolve()),
        },
        "window": {"start": str(ab.index[0].date()), "end": str(ab.index[-1].date()), "rows": int(len(ab))},
        "best": {
            "dynamic_ab": best_dynamic,
            "execution_threshold": best_exec,
            "group_a_component_risk": best_component,
        },
        "outputs": {"json": str(output), "csv": str(csv_path), "curve_csv": str(curve_path)},
        "rows": rows,
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"JSON: {output}")
    print(f"CSV:  {csv_path}")
    print(f"Curve CSV: {curve_path}")
    for label, row in [("Best dynamic A/B", best_dynamic), ("Best execution", best_exec), ("Best Group A component", best_component)]:
        print(
            f"{label}: {row['variant']} final={row['final_value']:.2f}, "
            f"annual={row['annual_return']:.4%}, sharpe={row['sharpe_ratio']:.4f}, "
            f"mdd={row['max_drawdown']:.4%}, events={row['num_events']}, cost={row['total_cost']:.2f}"
        )


if __name__ == "__main__":
    main()
