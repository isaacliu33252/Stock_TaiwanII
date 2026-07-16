#!/usr/bin/env python3
"""Forward-return audit for GroupA+ specialist-routing shadow logs.

Research-only. Reads results/specialist_routing_shadow_log.jsonl and measures
what happened after each route. It does not modify strategy manifests, live
signals, or allocation weights.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH


DEFAULT_LOG = PROJECT_ROOT / "results" / "specialist_routing_shadow_log.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_specialist_routing_shadow_latest.json"
DEFAULT_TICKERS = ("0050.TW", "00631L.TW", "00632R.TW")
DEFAULT_HORIZONS = (1, 5, 20)


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def _read_jsonl(path: Path) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return pd.DataFrame()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
    return frame.sort_values("date").drop_duplicates("date", keep="last").set_index("date")


def _load_prices(db_path: Path, tickers: tuple[str, ...], start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT ticker, dt, close
            FROM ohlcv
            WHERE ticker IN ({placeholders})
              AND dt BETWEEN ? AND ?
              AND close IS NOT NULL
            ORDER BY dt, ticker
            """.format(placeholders=", ".join(["?"] * len(tickers))),
            [*tickers, str(start.date()), str(end.date())],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        return pd.DataFrame()
    rows["date"] = pd.to_datetime(rows["dt"]).dt.normalize()
    return rows.pivot(index="date", columns="ticker", values="close").sort_index()


def _forward_return(close: pd.Series, horizon: int) -> pd.Series:
    return close.shift(-int(horizon)) / close - 1.0


def _forward_drawdown(close: pd.Series, horizon: int) -> pd.Series:
    values: list[float | None] = []
    arr = close.to_numpy(dtype=float)
    for idx, start_price in enumerate(arr):
        end = min(idx + int(horizon), len(arr) - 1)
        if idx >= end or start_price <= 0:
            values.append(None)
            continue
        window = arr[idx + 1 : end + 1]
        values.append(float((window / start_price - 1.0).min()))
    return pd.Series(values, index=close.index, dtype=float)


def build_forward_frame(
    log_frame: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> pd.DataFrame:
    if log_frame.empty or prices.empty:
        return pd.DataFrame()
    out = log_frame.copy()
    for ticker in prices.columns:
        close = prices[ticker].astype(float)
        for horizon in horizons:
            out[f"{ticker}_fwd_ret_{horizon}d"] = _forward_return(close, horizon).reindex(out.index)
            out[f"{ticker}_fwd_mdd_{horizon}d"] = _forward_drawdown(close, horizon).reindex(out.index)
    return out


def _summarize_numeric(series: pd.Series) -> dict[str, Any]:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return {"count": 0}
    return {
        "count": int(clean.count()),
        "mean": round(float(clean.mean()), 6),
        "median": round(float(clean.median()), 6),
        "win_rate": round(float((clean > 0.0).mean()), 6),
        "min": round(float(clean.min()), 6),
        "max": round(float(clean.max()), 6),
    }


def summarize_routes(
    forward_frame: pd.DataFrame,
    *,
    tickers: tuple[str, ...] = DEFAULT_TICKERS,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> dict[str, Any]:
    if forward_frame.empty:
        return {"route_count": 0, "routes": {}}
    routes: dict[str, Any] = {}
    for route, group in forward_frame.groupby("route", dropna=False):
        route_key = str(route)
        metrics: dict[str, Any] = {
            "row_count": int(len(group)),
            "risk_levels": group.get("risk_level", pd.Series(dtype=object)).value_counts(dropna=False).to_dict(),
            "logged_execution_regimes": group.get("logged_execution_regime", pd.Series(dtype=object)).value_counts(dropna=False).to_dict(),
            "tickers": {},
        }
        for ticker in tickers:
            ticker_metrics: dict[str, Any] = {}
            for horizon in horizons:
                ret_col = f"{ticker}_fwd_ret_{horizon}d"
                mdd_col = f"{ticker}_fwd_mdd_{horizon}d"
                ticker_metrics[f"fwd_ret_{horizon}d"] = _summarize_numeric(group.get(ret_col, pd.Series(dtype=float)))
                ticker_metrics[f"fwd_mdd_{horizon}d"] = _summarize_numeric(group.get(mdd_col, pd.Series(dtype=float)))
            metrics["tickers"][ticker] = ticker_metrics
        routes[route_key] = metrics
    return {"route_count": len(routes), "routes": routes}


def build_shadow_scorecard(
    forward_frame: pd.DataFrame,
    *,
    tickers: tuple[str, ...] = DEFAULT_TICKERS,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    lookbacks: tuple[int, ...] = (20, 60, 120),
) -> dict[str, Any]:
    if forward_frame.empty or "route" not in forward_frame:
        return {"status": "empty", "reason": "no forward rows"}
    latest_date = forward_frame.index.max()
    latest_route = str(forward_frame.loc[latest_date, "route"])
    route_frame = forward_frame[forward_frame["route"].astype(str) == latest_route].sort_index()
    out: dict[str, Any] = {
        "status": "available",
        "latest_date": str(pd.Timestamp(latest_date).date()),
        "latest_route": latest_route,
        "route_total_rows": int(len(route_frame)),
        "lookbacks": {},
    }
    for lookback in lookbacks:
        sample = route_frame.tail(int(lookback))
        payload: dict[str, Any] = {
            "rows": int(len(sample)),
            "data_sufficiency": "ok" if len(sample) >= min(int(lookback), 20) else "thin",
            "tickers": {},
        }
        for ticker in tickers:
            ticker_metrics: dict[str, Any] = {}
            for horizon in horizons:
                ret_col = f"{ticker}_fwd_ret_{horizon}d"
                mdd_col = f"{ticker}_fwd_mdd_{horizon}d"
                ticker_metrics[f"fwd_ret_{horizon}d"] = _summarize_numeric(sample.get(ret_col, pd.Series(dtype=float)))
                ticker_metrics[f"fwd_mdd_{horizon}d"] = _summarize_numeric(sample.get(mdd_col, pd.Series(dtype=float)))
            payload["tickers"][ticker] = ticker_metrics
        out["lookbacks"][str(int(lookback))] = payload
    return out


def build_report(
    *,
    log_path: Path,
    db_path: Path,
    tickers: tuple[str, ...] = DEFAULT_TICKERS,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> dict[str, Any]:
    log_frame = _read_jsonl(log_path)
    if log_frame.empty:
        return {
            "report_type": "group_a_plus_specialist_routing_shadow",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "status": "empty",
            "reason": "specialist routing shadow log has no rows",
            "log_path": str(log_path),
        }
    max_horizon = max(horizons)
    prices = _load_prices(
        db_path,
        tickers,
        log_frame.index.min() - pd.Timedelta(days=5),
        log_frame.index.max() + pd.Timedelta(days=max_horizon * 2 + 10),
    )
    forward = build_forward_frame(log_frame, prices, horizons=horizons)
    summary = summarize_routes(forward, tickers=tickers, horizons=horizons)
    scorecard = build_shadow_scorecard(forward, tickers=tickers, horizons=horizons)
    evaluated_rows = int(forward[[f"{tickers[0]}_fwd_ret_{h}d" for h in horizons if f"{tickers[0]}_fwd_ret_{h}d" in forward]].notna().any(axis=1).sum()) if not forward.empty else 0
    return {
        "report_type": "group_a_plus_specialist_routing_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "available",
        "active_allocation_impact": "none",
        "policy": "shadow_forward_return_audit_only",
        "log_path": str(log_path),
        "db_path": str(db_path),
        "row_count": int(len(log_frame)),
        "evaluated_rows": evaluated_rows,
        "date_range": {
            "start": str(log_frame.index.min().date()),
            "end": str(log_frame.index.max().date()),
        },
        "tickers": list(tickers),
        "horizons": list(horizons),
        "summary": summary,
        "scorecard": scorecard,
        "promotion_note": (
            "Do not promote route-level weight changes until each promoted route has "
            "enough forward rows across multiple regimes and passes a separate costed backtest."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", default=str(DEFAULT_LOG))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS))
    parser.add_argument("--horizons", default=",".join(str(h) for h in DEFAULT_HORIZONS))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tickers = tuple(item.strip() for item in args.tickers.split(",") if item.strip())
    horizons = tuple(int(item.strip()) for item in args.horizons.split(",") if item.strip())
    report = build_report(
        log_path=_resolve(args.log),
        db_path=_resolve(args.db),
        tickers=tickers,
        horizons=horizons,
    )
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Output: {output}")
    print(f"Status: {report.get('status')} rows={report.get('row_count', 0)} evaluated={report.get('evaluated_rows', 0)}")


if __name__ == "__main__":
    main()
