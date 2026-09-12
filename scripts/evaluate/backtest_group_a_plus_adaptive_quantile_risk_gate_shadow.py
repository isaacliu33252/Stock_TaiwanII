#!/usr/bin/env python3
"""Backtest GroupA+ adaptive quantile risk gate on saved live-signal snapshots.

Research-only. This replays saved `group_a_plus_live_signal_v2_*.json`
snapshots, applies the adaptive quantile shadow limits to each target weight
set, and compares raw vs gated close-to-next-close returns. It does not change
production weights.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus.integrations.adaptive_quantile_risk_gate import (  # noqa: E402
    classify_adaptive_quantile_risk_gate,
)


DB_PATH = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_SIGNALS_GLOB = str(PROJECT_ROOT / "results/group_a_plus_live_signal_v2_*.json")
DEFAULT_OUTPUT = PROJECT_ROOT / "results/group_a_plus_adaptive_quantile_risk_gate_backtest_latest.json"
DEFAULT_TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO")
COMMISSION_RATE = 0.001425
SELL_TAX_RATE = 0.001


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (pd.Timestamp,)):
        return str(value.date())
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return payload.get("data") if isinstance(payload.get("data"), dict) else payload


def _date_of_signal(signal: dict[str, Any]) -> str | None:
    value = signal.get("actual_data_date") or signal.get("signal_date") or signal.get("requested_as_of_date")
    if not value:
        return None
    return str(pd.Timestamp(value).date())


def _load_signals(pattern: str, *, start: str | None, end: str | None) -> list[dict[str, Any]]:
    paths = sorted(Path().glob(pattern) if not Path(pattern).is_absolute() else Path("/").glob(str(Path(pattern))[1:]))
    by_date: dict[str, dict[str, Any]] = {}
    for path in paths:
        try:
            signal = _load_json(path)
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(signal.get("target_weights"), dict):
            continue
        date = _date_of_signal(signal)
        if not date:
            continue
        if start and date < start:
            continue
        if end and date > end:
            continue
        previous = by_date.get(date)
        if previous is None or path.stat().st_mtime >= Path(previous["_source_path"]).stat().st_mtime:
            row = dict(signal)
            row["_source_path"] = str(path)
            by_date[date] = row
    return [by_date[date] for date in sorted(by_date)]


def _load_close(db_path: Path, tickers: tuple[str, ...]) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        frame = con.execute(
            """
            SELECT dt, ticker, close
            FROM ohlcv
            WHERE ticker IN ({})
            ORDER BY dt, ticker
            """.format(",".join(["?"] * len(tickers))),
            list(tickers),
        ).fetchdf()
    finally:
        con.close()
    frame["dt"] = pd.to_datetime(frame["dt"]).dt.normalize()
    pivot = frame.pivot(index="dt", columns="ticker", values="close").sort_index()
    return pivot.astype(float)


def _normalize_weights(weights: dict[str, Any], tickers: tuple[str, ...]) -> dict[str, float]:
    out = {ticker: max(float(weights.get(ticker, 0.0) or 0.0), 0.0) for ticker in tickers}
    cash = max(float(weights.get("cash", 0.0) or 0.0), 0.0)
    total = cash + sum(out.values())
    if total > 1.0:
        scale = 1.0 / total
        out = {ticker: value * scale for ticker, value in out.items()}
        cash *= scale
    out["cash"] = cash
    return out


def _apply_shadow_limits(weights: dict[str, float], gate: dict[str, Any], tickers: tuple[str, ...]) -> tuple[dict[str, float], dict[str, Any]]:
    adjusted = dict(weights)
    limits = gate.get("recommended_shadow_limits") or {}
    max_631l = float(limits.get("max_00631l_weight", adjusted.get("00631L.TW", 0.0)) or 0.0)
    min_cash = float(limits.get("min_cash_weight", adjusted.get("cash", 0.0)) or 0.0)
    actions: list[str] = []

    if adjusted.get("00631L.TW", 0.0) > max_631l:
        released = adjusted["00631L.TW"] - max_631l
        adjusted["00631L.TW"] = max_631l
        adjusted["cash"] = adjusted.get("cash", 0.0) + released
        actions.append("cap_00631l")

    cash_gap = min_cash - adjusted.get("cash", 0.0)
    if cash_gap > 1e-12:
        reducible = [ticker for ticker in tickers if adjusted.get(ticker, 0.0) > 0.0]
        total_risk = sum(adjusted[ticker] for ticker in reducible)
        if total_risk > 0.0:
            take = min(cash_gap, total_risk)
            for ticker in reducible:
                cut = take * adjusted[ticker] / total_risk
                adjusted[ticker] -= cut
            adjusted["cash"] += take
            actions.append("raise_cash_floor")

    adjusted = _normalize_weights(adjusted, tickers)
    return adjusted, {
        "changed": any(abs(adjusted.get(k, 0.0) - weights.get(k, 0.0)) > 1e-10 for k in set(adjusted) | set(weights)),
        "actions": actions,
    }


def _next_return(close: pd.DataFrame, date: str, weights: dict[str, float], tickers: tuple[str, ...]) -> tuple[float | None, str | None]:
    dt = pd.Timestamp(date).normalize()
    if dt not in close.index:
        return None, None
    pos = close.index.get_loc(dt)
    if not isinstance(pos, int) or pos + 1 >= len(close.index):
        return None, None
    next_dt = close.index[pos + 1]
    ret = 0.0
    for ticker in tickers:
        today = close.at[dt, ticker]
        nxt = close.at[next_dt, ticker]
        if pd.isna(today) or pd.isna(nxt) or today <= 0:
            return None, None
        ret += float(weights.get(ticker, 0.0)) * (float(nxt) / float(today) - 1.0)
    return float(ret), str(next_dt.date())


def _turnover_cost(prev_weights: dict[str, float] | None, weights: dict[str, float], tickers: tuple[str, ...]) -> float:
    if prev_weights is None:
        return 0.0
    buy_turnover = 0.0
    sell_turnover = 0.0
    for ticker in tickers:
        delta = weights.get(ticker, 0.0) - prev_weights.get(ticker, 0.0)
        if delta > 0:
            buy_turnover += delta
        else:
            sell_turnover += -delta
    return buy_turnover * COMMISSION_RATE + sell_turnover * (COMMISSION_RATE + SELL_TAX_RATE)


def _metrics(rows: list[dict[str, Any]], column: str) -> dict[str, Any]:
    returns = pd.Series([row[column] for row in rows], dtype=float)
    if returns.empty:
        return {"n": 0}
    equity = (1.0 + returns).cumprod()
    daily_std = returns.std(ddof=0)
    sharpe = float(returns.mean() / daily_std * math.sqrt(252)) if daily_std > 0 else 0.0
    peak = equity.cummax()
    return {
        "n": int(len(returns)),
        "total_return": float(equity.iloc[-1] - 1.0),
        "mean_daily_return": float(returns.mean()),
        "sharpe_ratio": sharpe,
        "max_drawdown": float((equity / peak - 1.0).min()),
        "positive_day_rate": float((returns > 0).mean()),
        "worst_day": float(returns.min()),
        "best_day": float(returns.max()),
    }


def evaluate(
    signals: list[dict[str, Any]],
    close: pd.DataFrame,
    *,
    tickers: tuple[str, ...] = DEFAULT_TICKERS,
    min_samples: int = 20,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    prev_raw: dict[str, float] | None = None
    prev_gated: dict[str, float] | None = None

    for signal in signals:
        date = _date_of_signal(signal)
        if not date:
            continue
        raw_weights = _normalize_weights(signal.get("target_weights") or {}, tickers)
        gate = classify_adaptive_quantile_risk_gate(signal)
        gated_weights, adjustment = _apply_shadow_limits(raw_weights, gate, tickers)
        raw_ret, next_date = _next_return(close, date, raw_weights, tickers)
        gated_ret, _ = _next_return(close, date, gated_weights, tickers)
        if raw_ret is None or gated_ret is None:
            continue

        raw_cost = _turnover_cost(prev_raw, raw_weights, tickers)
        gated_cost = _turnover_cost(prev_gated, gated_weights, tickers)
        raw_net = raw_ret - raw_cost
        gated_net = gated_ret - gated_cost

        rows.append(
            {
                "date": date,
                "next_date": next_date,
                "source_path": signal.get("_source_path"),
                "risk_posture": gate["risk_posture"],
                "quantile_level": gate["quantile_level"],
                "uncertainty_score": gate["uncertainty_score"],
                "raw_return": raw_ret,
                "gated_return": gated_ret,
                "raw_net_return": raw_net,
                "gated_net_return": gated_net,
                "delta_net_return": gated_net - raw_net,
                "changed": adjustment["changed"],
                "actions": adjustment["actions"],
                "raw_00631l_weight": raw_weights.get("00631L.TW", 0.0),
                "gated_00631l_weight": gated_weights.get("00631L.TW", 0.0),
                "raw_cash_weight": raw_weights.get("cash", 0.0),
                "gated_cash_weight": gated_weights.get("cash", 0.0),
                "raw_weights": raw_weights,
                "gated_weights": gated_weights,
                "reason_codes": gate.get("reason_codes"),
            }
        )
        prev_raw = raw_weights
        prev_gated = gated_weights

    raw_metrics = _metrics(rows, "raw_net_return")
    gated_metrics = _metrics(rows, "gated_net_return")
    delta = {
        "total_return_delta": gated_metrics.get("total_return", 0.0) - raw_metrics.get("total_return", 0.0),
        "sharpe_delta": gated_metrics.get("sharpe_ratio", 0.0) - raw_metrics.get("sharpe_ratio", 0.0),
        "max_drawdown_delta": gated_metrics.get("max_drawdown", 0.0) - raw_metrics.get("max_drawdown", 0.0),
        "worst_day_delta": gated_metrics.get("worst_day", 0.0) - raw_metrics.get("worst_day", 0.0),
    }
    changed_rows = [row for row in rows if row["changed"]]
    bad_631l_rows = [
        row
        for row in rows
        if row["raw_00631l_weight"] > row["gated_00631l_weight"] and row["raw_return"] < row["gated_return"]
    ]
    status = "ok" if len(rows) >= min_samples else "insufficient_signal_snapshots"
    decision = "shadow_pass_candidate" if status == "ok" and delta["max_drawdown_delta"] >= 0 and delta["total_return_delta"] >= -0.002 else "do_not_promote"

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_adaptive_quantile_risk_gate_backtest",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "method": "saved live-signal close-to-next-close replay; raw target weights versus adaptive-quantile shadow limits; transaction-cost proxy applied to target-weight turnover",
        "sample": {
            "signal_count_input": len(signals),
            "return_rows": len(rows),
            "start": rows[0]["date"] if rows else None,
            "end": rows[-1]["date"] if rows else None,
            "min_samples": min_samples,
        },
        "raw_metrics": raw_metrics,
        "gated_metrics": gated_metrics,
        "delta": delta,
        "gate_activity": {
            "changed_days": len(changed_rows),
            "changed_day_rate": len(changed_rows) / len(rows) if rows else 0.0,
            "cap_00631l_days": sum("cap_00631l" in row["actions"] for row in rows),
            "raise_cash_floor_days": sum("raise_cash_floor" in row["actions"] for row in rows),
            "avoided_bad_00631l_days": len(bad_631l_rows),
        },
        "posture_counts": dict(pd.Series([row["risk_posture"] for row in rows]).value_counts().sort_index()) if rows else {},
        "decision": {
            "promotion_decision": decision,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "reason": "requires larger true signal replay sample and walk-forward evidence before promotion",
        },
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signals-glob", default=DEFAULT_SIGNALS_GLOB)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2026-08-06")
    parser.add_argument("--min-samples", type=int, default=20)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    signals = _load_signals(args.signals_glob, start=args.start, end=args.end)
    close = _load_close(Path(args.db), DEFAULT_TICKERS)
    result = evaluate(signals, close, min_samples=args.min_samples)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default) + "\n", encoding="utf-8")
    csv_path = output.with_suffix(".csv")
    pd.DataFrame(result["rows"]).to_csv(csv_path, index=False, encoding="utf-8-sig")

    print(f"status={result['status']} rows={result['sample']['return_rows']} window={result['sample']['start']}..{result['sample']['end']}")
    print(
        "raw_total={raw:.4%} gated_total={gated:.4%} delta={delta:.4%}".format(
            raw=result["raw_metrics"].get("total_return", 0.0),
            gated=result["gated_metrics"].get("total_return", 0.0),
            delta=result["delta"].get("total_return_delta", 0.0),
        )
    )
    print(
        "raw_mdd={raw:.4%} gated_mdd={gated:.4%} delta={delta:.4%}".format(
            raw=result["raw_metrics"].get("max_drawdown", 0.0),
            gated=result["gated_metrics"].get("max_drawdown", 0.0),
            delta=result["delta"].get("max_drawdown_delta", 0.0),
        )
    )
    print(f"changed_days={result['gate_activity']['changed_days']} decision={result['decision']['promotion_decision']}")
    print(f"JSON: {output}")
    print(f"CSV:  {csv_path}")


if __name__ == "__main__":
    main()
