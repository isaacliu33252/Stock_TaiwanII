#!/usr/bin/env python3
"""Audit Golden1 signal weight drift and backtest replay assumptions."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_policy_signal import TICKERS, _normalize, _weights_from_group_a
from group_a_plus.paths import PROJECT_ROOT
from group_a_plus.runners.a2111 import _resolve_golden_signal_path


DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "golden1_weight_drift_latest.json"
DEFAULT_CSV_OUTPUT = PROJECT_ROOT / "results" / "golden1_weight_drift_latest.csv"


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _signal_timestamp(path: Path, payload: dict[str, Any]) -> pd.Timestamp | None:
    for key in ("actual_data_date", "requested_as_of_date", "as_of_date", "date", "signal_date"):
        raw = payload.get(key)
        if raw:
            ts = pd.to_datetime(raw, errors="coerce")
            if pd.notna(ts):
                return pd.Timestamp(ts).normalize()
    match = re.search(r"(20\d{6})", path.name)
    if match:
        ts = pd.to_datetime(match.group(1), format="%Y%m%d", errors="coerce")
        if pd.notna(ts):
            return pd.Timestamp(ts).normalize()
    return None


def _candidate_signal_files(results_dir: Path) -> list[Path]:
    files = []
    files.extend(results_dir.glob("signal_group_a_*.json"))
    latest = results_dir / "group_a_combined_live_latest.json"
    if latest.exists():
        files.append(latest)
    return sorted({path.resolve() for path in files})


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def load_weight_history(results_dir: Path) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for path in _candidate_signal_files(results_dir):
        if "tdcc" in path.name.lower() or "shareholding" in path.name.lower():
            continue
        payload = _load_json(path)
        if not payload:
            continue
        weights = _normalize(_weights_from_group_a(payload))
        if sum(weights.get(ticker, 0.0) for ticker in TICKERS) <= 0.0 and weights.get("cash", 0.0) >= 1.0:
            continue
        ts = _signal_timestamp(path, payload)
        if ts is None:
            continue
        rows.append(
            {
                "date": ts,
                "file": _display_path(path),
                "modified_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
                "0050.TW": weights.get("0050.TW", 0.0),
                "00631L.TW": weights.get("00631L.TW", 0.0),
                "00632R.TW": weights.get("00632R.TW", 0.0),
                "00679B.TWO": weights.get("00679B.TWO", 0.0),
                "cash": weights.get("cash", 0.0),
                "latest_action": payload.get("latest_action"),
                "signal_status": payload.get("signal_status"),
                "signal_reason": payload.get("signal_reason"),
                "actual_data_date": payload.get("actual_data_date"),
                "requested_as_of_date": payload.get("requested_as_of_date"),
            }
        )
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows).sort_values(["date", "modified_at", "file"])
    return frame.drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)


def _load_prices(db_path: Path, start: str, end: str) -> pd.DataFrame:
    tickers = list(TICKERS)
    placeholders = ", ".join(["?"] * len(tickers))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            f"""
            SELECT dt, ticker, close
            FROM ohlcv
            WHERE ticker IN ({placeholders}) AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [*tickers, start, end],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        raise RuntimeError(f"No OHLCV rows between {start} and {end}")
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows.pivot(index="dt", columns="ticker", values="close").sort_index().dropna(subset=tickers)


def _metrics(values: pd.Series, initial_value: float) -> dict[str, float]:
    returns = values.pct_change().dropna()
    years = max((values.index[-1] - values.index[0]).days / 365.25, 1e-9)
    total_return = float(values.iloc[-1] / initial_value - 1.0)
    annual_return = float((values.iloc[-1] / initial_value) ** (1.0 / years) - 1.0)
    sharpe = float((returns.mean() / returns.std()) * math.sqrt(252)) if len(returns) > 1 and returns.std() > 0 else 0.0
    max_drawdown = float((values / values.cummax() - 1.0).min())
    return {
        "final_value": float(values.iloc[-1]),
        "total_return": total_return,
        "annual_return": annual_return,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_drawdown,
    }


def _static_curve(prices: pd.DataFrame, weights: dict[str, float], initial_value: float) -> pd.Series:
    weights = _normalize(weights)
    first = prices.iloc[0]
    values = pd.Series(initial_value * weights.get("cash", 0.0), index=prices.index, dtype=float)
    for ticker in TICKERS:
        weight = float(weights.get(ticker, 0.0))
        if weight > 0.0:
            values += float(initial_value) * weight * prices[ticker].astype(float) / float(first[ticker])
    return values


def _dynamic_daily_curve(prices: pd.DataFrame, weight_history: pd.DataFrame, initial_value: float) -> tuple[pd.Series, pd.DataFrame]:
    hist = weight_history.set_index("date")[list(TICKERS) + ["cash"]].sort_index()
    weights = hist.reindex(prices.index, method="ffill").dropna(how="all")
    prices = prices.reindex(weights.index)
    values = [float(initial_value)]
    for i in range(1, len(prices)):
        prev_weights = _normalize(weights.iloc[i - 1].to_dict())
        daily_return = prev_weights.get("cash", 0.0)
        daily_return += sum(
            prev_weights.get(ticker, 0.0) * float(prices.iloc[i][ticker]) / float(prices.iloc[i - 1][ticker])
            for ticker in TICKERS
        )
        values.append(values[-1] * daily_return)
    return pd.Series(values, index=prices.index, dtype=float), weights


def build_report(
    *,
    results_dir: Path,
    db_path: Path,
    start: str,
    end: str,
    initial_value: float,
) -> tuple[dict[str, Any], pd.DataFrame]:
    history = load_weight_history(results_dir)
    if history.empty:
        raise RuntimeError("No Golden1 signal weights found")

    active_path = _resolve_golden_signal_path()
    active_payload = _load_json(active_path) or {}
    active_weights = _normalize(_weights_from_group_a(active_payload))

    cols = list(TICKERS) + ["cash"]
    summary = history[cols].agg(["min", "max", "mean", "std"]).fillna(0.0).to_dict()
    history["00631L_change"] = history["00631L.TW"].diff().fillna(0.0)
    history["weight_turnover_vs_prev"] = history[cols].diff().abs().sum(axis=1).fillna(0.0)

    prices = _load_prices(db_path, start, end)
    static_latest = _static_curve(prices, active_weights, initial_value)
    overlap_start = max(prices.index[0], history["date"].min())
    overlap_prices = prices.loc[overlap_start:]
    dynamic_curve, replay_weights = _dynamic_daily_curve(overlap_prices, history, initial_value)
    static_overlap = _static_curve(overlap_prices, active_weights, initial_value)

    report = {
        "schema_version": 1,
        "report_type": "golden1_weight_drift_audit",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "active_golden_signal": {
            "path": str(active_path.relative_to(PROJECT_ROOT)),
            "weights": active_weights,
        },
        "history": {
            "signal_count": int(len(history)),
            "first_date": str(history["date"].min().date()),
            "last_date": str(history["date"].max().date()),
            "weight_summary": summary,
            "latest_history_row": history.iloc[-1].where(pd.notna(history.iloc[-1]), None).to_dict(),
            "largest_00631l_changes": history.reindex(history["00631L_change"].abs().sort_values(ascending=False).index)
            .head(10)
            .where(pd.notna(history), None)
            .to_dict(orient="records"),
            "largest_weight_turnover_days": history.reindex(history["weight_turnover_vs_prev"].sort_values(ascending=False).index)
            .head(10)
            .where(pd.notna(history), None)
            .to_dict(orient="records"),
        },
        "replay": {
            "static_latest_window": {
                "start": str(prices.index[0].date()),
                "end": str(prices.index[-1].date()),
                "metrics": _metrics(static_latest, initial_value),
            },
            "overlap_window": {
                "start": str(overlap_prices.index[0].date()),
                "end": str(overlap_prices.index[-1].date()),
                "rows": int(len(overlap_prices)),
                "static_latest_metrics": _metrics(static_overlap, initial_value),
                "historical_weight_metrics": _metrics(dynamic_curve, initial_value),
                "final_value_delta_historical_minus_static": float(dynamic_curve.iloc[-1] - static_overlap.iloc[-1]),
            },
            "method_note": (
                "Historical-weight replay uses one-day lagged daily target weights from available signal files "
                "with no transaction costs. It audits weight drift, not full A21.18 regime/cost behavior."
            ),
        },
        "assessment": {
            "active_00631l_weight": active_weights.get("00631L.TW", 0.0),
            "why_a2126_caps_collapsed": (
                "Caps above the active 00631L weight are no-ops. If active 00631L is near 10%, "
                "cap=14/15/16% produces identical behavior."
            ),
        },
    }
    return report, history


def _json_default(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", default=str(PROJECT_ROOT / "results"))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2026-06-30")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--csv-output", default=str(DEFAULT_CSV_OUTPUT))
    args = parser.parse_args()

    report, history = build_report(
        results_dir=Path(args.results_dir),
        db_path=Path(args.db),
        start=args.start,
        end=args.end,
        initial_value=args.initial_value,
    )
    output = Path(args.output)
    csv_output = Path(args.csv_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    csv_output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    history.to_csv(csv_output, index=False, encoding="utf-8-sig")
    print(f"Golden1 drift JSON: {output.resolve()}")
    print(f"Golden1 drift CSV:  {csv_output.resolve()}")


if __name__ == "__main__":
    main()
