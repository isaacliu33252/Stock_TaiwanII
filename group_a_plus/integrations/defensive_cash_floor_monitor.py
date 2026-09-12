"""Monitoring and rollback checks for the defensive cash-floor candidate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


CORE_TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO")
UNDERPERFORM_THRESHOLD = -0.005
MDD_WORSE_THRESHOLD = -0.0025


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_candidate_log(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _weights(section: dict[str, Any] | None) -> dict[str, float]:
    raw = (section or {}).get("target_weights") if isinstance(section, dict) else {}
    raw = raw if isinstance(raw, dict) else {}
    return {ticker: max(0.0, _as_float(raw.get(ticker), 0.0)) for ticker in CORE_TICKERS} | {
        "cash": max(0.0, _as_float(raw.get("cash"), 0.0))
    }


def _portfolio_return(weights: dict[str, float], returns: dict[str, float]) -> float:
    return sum(weights.get(ticker, 0.0) * returns.get(ticker, 0.0) for ticker in CORE_TICKERS)


def _mdd_from_returns(returns: list[float]) -> float:
    equity = 1.0
    peak = 1.0
    mdd = 0.0
    for ret in returns:
        equity *= 1.0 + ret
        peak = max(peak, equity)
        mdd = min(mdd, equity / peak - 1.0)
    return mdd


def _next_returns_for_dates(price_frame: pd.DataFrame, dates: list[str]) -> dict[str, dict[str, Any]]:
    if price_frame.empty or not dates:
        return {}
    frame = price_frame.copy()
    frame["dt"] = pd.to_datetime(frame["dt"])
    close = frame.pivot(index="dt", columns="ticker", values="close").sort_index()
    close = close[[ticker for ticker in CORE_TICKERS if ticker in close.columns]].astype(float)
    pct = close.pct_change(fill_method=None)
    lookup: dict[str, dict[str, Any]] = {}
    for raw_date in dates:
        dt = pd.Timestamp(raw_date)
        future_index = close.index[close.index > dt]
        if len(future_index) == 0:
            lookup[raw_date] = {"status": "pending_next_close", "next_date": None, "returns": {}}
            continue
        next_dt = future_index[0]
        ret_row = pct.loc[next_dt]
        lookup[raw_date] = {
            "status": "available",
            "next_date": str(next_dt.date()),
            "returns": {
                ticker: float(ret_row[ticker])
                for ticker in close.columns
                if pd.notna(ret_row.get(ticker))
            },
        }
    return lookup


def build_defensive_cash_floor_monitor(
    *,
    candidate_log_rows: list[dict[str, Any]],
    price_frame: pd.DataFrame,
    as_of: str,
    first_n_triggers: int = 10,
    underperform_threshold: float = UNDERPERFORM_THRESHOLD,
    mdd_worse_threshold: float = MDD_WORSE_THRESHOLD,
) -> dict[str, Any]:
    trigger_rows = [
        row
        for row in candidate_log_rows
        if row.get("triggered") is True and row.get("changed") is True and row.get("can_apply_to_formal_target") is True
    ]
    trigger_rows.sort(key=lambda row: str(row.get("date") or ""))
    next_returns = _next_returns_for_dates(price_frame, [str(row.get("date")) for row in trigger_rows])
    evaluated: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for row in trigger_rows:
        date = str(row.get("date"))
        lookup = next_returns.get(date, {"status": "pending_next_close", "returns": {}})
        if lookup.get("status") != "available":
            pending.append({"date": date, "reason": lookup.get("status")})
            continue
        raw_weights = _weights(row.get("formal_reference"))
        candidate_weights = _weights(row.get("candidate"))
        returns = lookup.get("returns") if isinstance(lookup.get("returns"), dict) else {}
        raw_ret = _portfolio_return(raw_weights, returns)
        candidate_ret = _portfolio_return(candidate_weights, returns)
        evaluated.append(
            {
                "date": date,
                "next_date": lookup.get("next_date"),
                "raw_return": raw_ret,
                "candidate_return": candidate_ret,
                "delta": candidate_ret - raw_ret,
                "raw_weights": raw_weights,
                "candidate_weights": candidate_weights,
            }
        )

    first_slice = evaluated[:first_n_triggers]
    raw_returns = [row["raw_return"] for row in first_slice]
    candidate_returns = [row["candidate_return"] for row in first_slice]
    cumulative_delta = 1.0
    raw_equity = 1.0
    candidate_equity = 1.0
    for raw_ret, candidate_ret in zip(raw_returns, candidate_returns):
        raw_equity *= 1.0 + raw_ret
        candidate_equity *= 1.0 + candidate_ret
    cumulative_delta = candidate_equity / raw_equity - 1.0 if raw_equity else 0.0
    raw_mdd = _mdd_from_returns(raw_returns)
    candidate_mdd = _mdd_from_returns(candidate_returns)
    mdd_delta = candidate_mdd - raw_mdd

    rollback_reasons: list[str] = []
    first_window_complete = len(first_slice) >= first_n_triggers
    if first_window_complete and cumulative_delta < underperform_threshold:
        rollback_reasons.append("first_10_trigger_days_variant_underperforms_raw_by_more_than_0_50pct_cumulative")
    if first_window_complete and mdd_delta < mdd_worse_threshold:
        rollback_reasons.append("variant_max_drawdown_worse_than_raw_by_more_than_0_25pct_on_trigger_window")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_defensive_cash_floor_guarded_monitor",
        "policy": "monitor_only_no_target_weight_change_no_orders",
        "as_of": as_of,
        "candidate_id": "defensive_cash_floor_high_risk_state",
        "variant": "cash55_risk7_tail1",
        "input_counts": {
            "log_rows": len(candidate_log_rows),
            "trigger_rows": len(trigger_rows),
            "evaluated_trigger_rows": len(evaluated),
            "pending_trigger_rows": len(pending),
            "first_n_triggers": first_n_triggers,
        },
        "first_trigger_window": {
            "complete": first_window_complete,
            "evaluated_count": len(first_slice),
            "raw_cumulative_return": raw_equity - 1.0,
            "candidate_cumulative_return": candidate_equity - 1.0,
            "cumulative_delta": cumulative_delta,
            "raw_max_drawdown": raw_mdd,
            "candidate_max_drawdown": candidate_mdd,
            "max_drawdown_delta": mdd_delta,
            "underperform_threshold": underperform_threshold,
            "mdd_worse_threshold": mdd_worse_threshold,
        },
        "evaluated_events": evaluated[:50],
        "pending_events": pending[:50],
        "rollback": {
            "disable_candidate": bool(rollback_reasons),
            "reasons": rollback_reasons,
        },
        "decision": {
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "allow_broker_order_output": False,
            "promote_to_live": False,
        },
        "summary": {
            "status": "rollback_required" if rollback_reasons else "monitoring",
            "no_trigger_yet": len(trigger_rows) == 0,
            "needs_more_trigger_history": len(first_slice) < first_n_triggers,
        },
    }
