"""Shadow backtest for Moira critic execution-guard hard stop proposal."""

from __future__ import annotations

import math
from typing import Any


RISK_TICKERS = ("00631L.TW", "00632R.TW")
TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO")
MANUAL_REVIEW_STRICT_TRIGGER_MIN = 20
GUARDED_CANDIDATE_STRICT_TRIGGER_MIN = 40
PROMOTION_POSITIVE_RATE_MIN = 0.55


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _weights(signal: dict[str, Any]) -> dict[str, float]:
    raw = signal.get("target_weights") or {}
    out = {ticker: max(_as_float(raw.get(ticker), 0.0), 0.0) for ticker in TICKERS}
    out["cash"] = max(_as_float(raw.get("cash"), 0.0), 0.0)
    total = sum(out.values())
    if total > 1.0:
        out = {key: value / total for key, value in out.items()}
    return out


def _prices(signal: dict[str, Any]) -> dict[str, float]:
    raw = signal.get("latest_prices") or {}
    return {ticker: _as_float(raw.get(ticker), 0.0) for ticker in TICKERS}


def _next_returns(records: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for current, nxt in zip(records, records[1:]):
        current_prices = _prices(current["signal"])
        next_prices = _prices(nxt["signal"])
        returns: dict[str, float] = {}
        for ticker in TICKERS:
            start = current_prices.get(ticker, 0.0)
            end = next_prices.get(ticker, 0.0)
            if start > 0 and end > 0:
                returns[ticker] = end / start - 1.0
        if returns:
            out[current["date"]] = returns
    return out


def _portfolio_return(weights: dict[str, float], returns: dict[str, float]) -> float | None:
    used = False
    total = 0.0
    for ticker in TICKERS:
        if ticker not in returns:
            continue
        total += weights.get(ticker, 0.0) * returns[ticker]
        used = True
    return total if used else None


def _apply_guard(raw: dict[str, float], previous: dict[str, float] | None, execution_allowed: Any) -> tuple[dict[str, float], list[str]]:
    if execution_allowed is not False or previous is None:
        return dict(raw), []
    adjusted = dict(raw)
    actions: list[str] = []
    for ticker in RISK_TICKERS:
        cap = previous.get(ticker, 0.0)
        if adjusted.get(ticker, 0.0) > cap:
            released = adjusted[ticker] - cap
            adjusted[ticker] = cap
            adjusted["cash"] = adjusted.get("cash", 0.0) + released
            actions.append(f"cap_new_{ticker}")
    return adjusted, actions


def _metrics(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for value in values:
        equity *= 1.0 + value
        peak = max(peak, equity)
        max_dd = min(max_dd, equity / peak - 1.0)
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    std = math.sqrt(variance)
    return {
        "n": len(values),
        "total_return": equity - 1.0,
        "mean_return": mean,
        "sharpe_proxy": mean / std * math.sqrt(252) if std > 0 else 0.0,
        "max_drawdown": max_dd,
        "positive_rate": sum(1 for value in values if value > 0) / len(values),
        "worst_return": min(values),
        "best_return": max(values),
    }


def _promotion_checklist(
    *,
    raw_metrics: dict[str, Any],
    guarded_metrics: dict[str, Any],
    strict_trigger_count: int,
    trigger_delta_metrics: dict[str, Any],
) -> dict[str, Any]:
    mean_delta = trigger_delta_metrics.get("mean_return")
    positive_rate = trigger_delta_metrics.get("positive_rate")
    raw_dd = raw_metrics.get("max_drawdown")
    guarded_dd = guarded_metrics.get("max_drawdown")
    checks = {
        "manual_review_min_strict_triggers_20": strict_trigger_count >= MANUAL_REVIEW_STRICT_TRIGGER_MIN,
        "guarded_candidate_min_strict_triggers_40": strict_trigger_count >= GUARDED_CANDIDATE_STRICT_TRIGGER_MIN,
        "mean_trigger_delta_positive": mean_delta is not None and mean_delta > 0,
        "positive_trigger_delta_rate_ge_55pct": positive_rate is not None and positive_rate >= PROMOTION_POSITIVE_RATE_MIN,
        "max_drawdown_not_worse": raw_dd is not None and guarded_dd is not None and guarded_dd >= raw_dd,
        "signed_approval_present": False,
    }
    return {
        "policy": "promotion_checklist_only_no_automatic_upgrade",
        "manual_review_min_strict_trigger_count": MANUAL_REVIEW_STRICT_TRIGGER_MIN,
        "guarded_candidate_min_strict_trigger_count": GUARDED_CANDIDATE_STRICT_TRIGGER_MIN,
        "positive_trigger_delta_rate_min": PROMOTION_POSITIVE_RATE_MIN,
        "checks": checks,
        "manual_review_allowed": all(
            checks[key]
            for key in (
                "manual_review_min_strict_triggers_20",
                "mean_trigger_delta_positive",
                "positive_trigger_delta_rate_ge_55pct",
                "max_drawdown_not_worse",
            )
        ),
        "guarded_candidate_allowed": all(checks.values()),
    }


def build_execution_guard_hard_stop_backtest(
    *,
    signal_records: list[dict[str, Any]],
    as_of: str | None = None,
    min_trigger_count: int = 5,
) -> dict[str, Any]:
    records = sorted(signal_records, key=lambda row: row["date"])
    next_returns = _next_returns(records)
    rows: list[dict[str, Any]] = []
    general_trigger_rows: list[dict[str, Any]] = []
    previous_weights: dict[str, float] | None = None
    raw_values: list[float] = []
    guarded_values: list[float] = []

    for record in records:
        signal = record["signal"]
        date = record["date"]
        returns = next_returns.get(date)
        raw = _weights(signal)
        guarded, actions = _apply_guard(raw, previous_weights, signal.get("execution_allowed"))
        previous_weights = raw
        if not returns:
            continue
        raw_return = _portfolio_return(raw, returns)
        guarded_return = _portfolio_return(guarded, returns)
        if raw_return is None or guarded_return is None:
            continue
        general_trigger = signal.get("execution_allowed") is False
        trigger = bool(actions)
        if general_trigger:
            general_trigger_rows.append(
                {
                    "date": date,
                    "reason": "execution_allowed_false",
                    "strict_actionable": trigger,
                    "actions": actions,
                    "raw_return": raw_return,
                    "guarded_return": guarded_return,
                    "delta_return": guarded_return - raw_return,
                }
            )
        raw_values.append(raw_return)
        guarded_values.append(guarded_return)
        rows.append(
            {
                "date": date,
                "next_returns": returns,
                "execution_allowed": signal.get("execution_allowed"),
                "triggered": trigger,
                "actions": actions,
                "raw_return": raw_return,
                "guarded_return": guarded_return,
                "delta_return": guarded_return - raw_return,
                "raw_weights": raw,
                "guarded_weights": guarded,
            }
        )

    trigger_rows = [row for row in rows if row["triggered"]]
    trigger_deltas = [row["delta_return"] for row in trigger_rows]
    raw_metrics = _metrics(raw_values)
    guarded_metrics = _metrics(guarded_values)
    trigger_delta_metrics = _metrics(trigger_deltas)
    checklist = _promotion_checklist(
        raw_metrics=raw_metrics,
        guarded_metrics=guarded_metrics,
        strict_trigger_count=len(trigger_rows),
        trigger_delta_metrics=trigger_delta_metrics,
    )
    ready = len(trigger_rows) >= min_trigger_count
    return {
        "schema_version": 2,
        "report_type": "group_a_plus_moira_execution_guard_hard_stop_backtest_shadow",
        "policy": "shadow_backtest_only_no_rule_change",
        "as_of": as_of or (records[-1]["date"] if records else ""),
        "proposal_id": "execution_guard_hard_stop_for_new_risk",
        "input_coverage": {
            "signal_record_count": len(records),
            "return_row_count": len(rows),
            "general_trigger_count": len(general_trigger_rows),
            "strict_actionable_trigger_count": len(trigger_rows),
            "trigger_count": len(trigger_rows),
            "date_start": records[0]["date"] if records else None,
            "date_end": records[-1]["date"] if records else None,
            "min_trigger_count": min_trigger_count,
        },
        "trigger_taxonomy": {
            "general_trigger_definition": "execution_allowed is false",
            "strict_actionable_trigger_definition": "execution_allowed is false and target adds 00631L.TW or 00632R.TW above previous target",
            "general_trigger_count": len(general_trigger_rows),
            "strict_actionable_trigger_count": len(trigger_rows),
            "general_trigger_rows": general_trigger_rows,
        },
        "raw_metrics": raw_metrics,
        "guarded_metrics": guarded_metrics,
        "trigger_delta_metrics": trigger_delta_metrics,
        "trigger_rows": trigger_rows,
        "promotion_checklist": checklist,
        "summary": {
            "ready_for_manual_review": ready,
            "promotion_checklist_manual_review_allowed": checklist["manual_review_allowed"],
            "promotion_checklist_guarded_candidate_allowed": checklist["guarded_candidate_allowed"],
            "mean_trigger_delta": sum(trigger_deltas) / len(trigger_deltas) if trigger_deltas else None,
            "positive_trigger_delta_rate": (
                sum(1 for value in trigger_deltas if value > 0) / len(trigger_deltas) if trigger_deltas else None
            ),
            "recommendation": "manual_review_shadow_candidate" if ready else "needs_more_trigger_history",
        },
        "decision": {
            "creates_orders": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "code_change_allowed": False,
            "guarded_candidate_allowed": False,
            "promote_to_live": False,
            "requires_signed_approval_before_any_candidate": True,
        },
    }
