"""Artifact replay validation for Moira policy critic proposals."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


PROPOSAL_IDS = (
    "freshness_first_review_gate",
    "execution_guard_hard_stop_for_new_risk",
    "large_inverse_hedge_staging_review",
    "low_risk_bullish_beta_reduction_cooldown",
    "hedge_thesis_blocker_echo",
)


def _load(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}


def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _date_from_path(path: Path) -> str | None:
    match = re.search(r"(20\d{6})", path.name)
    if not match:
        return None
    stamp = match.group(1)
    return f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}"


def _target_weights(signal: dict[str, Any]) -> dict[str, float]:
    raw = signal.get("target_weights") or {}
    return {
        "0050.TW": _as_float(raw.get("0050.TW"), 0.0),
        "00631L.TW": _as_float(raw.get("00631L.TW"), 0.0),
        "00632R.TW": _as_float(raw.get("00632R.TW"), 0.0),
        "00679B.TWO": _as_float(raw.get("00679B.TWO"), 0.0),
        "cash": _as_float(raw.get("cash"), 0.0),
    }


def _prices(signal: dict[str, Any]) -> dict[str, float]:
    raw = signal.get("latest_prices") or {}
    return {
        "0050.TW": _as_float(raw.get("0050.TW"), 0.0),
        "00632R.TW": _as_float(raw.get("00632R.TW"), 0.0),
    }


def _features(signal: dict[str, Any]) -> dict[str, Any]:
    raw = signal.get("latest_features")
    return raw if isinstance(raw, dict) else {}


def _current_weights(plan: dict[str, Any]) -> dict[str, float]:
    total = _as_float(plan.get("current_total_assets") or plan.get("current_holdings_market_value"), 0.0)
    prices = plan.get("current_prices") if isinstance(plan.get("current_prices"), dict) else {}
    shares = plan.get("current_holdings") if isinstance(plan.get("current_holdings"), dict) else {}
    current: dict[str, float] = {}
    for ticker in ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO"):
        current[ticker] = (
            _as_float(shares.get(ticker), 0.0) * _as_float(prices.get(ticker), 0.0) / total
            if total > 0
            else 0.0
        )
    current["cash"] = _as_float(plan.get("current_cash_input"), 0.0) / total if total > 0 else 0.0
    return current


def _staged_tickers(plan: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for row in plan.get("staged_buys") or []:
        if isinstance(row, dict) and row.get("ticker"):
            out.add(str(row["ticker"]))
    return out


def load_signal_records(paths: list[Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen_dates: set[str] = set()
    for path in sorted(paths):
        payload = _unwrap(_load(path))
        if not payload:
            continue
        date = str(payload.get("actual_data_date") or payload.get("requested_as_of_date") or _date_from_path(path) or "")
        if not date or date in seen_dates:
            continue
        seen_dates.add(date)
        records.append({"date": date, "path": str(path), "signal": payload})
    return sorted(records, key=lambda row: row["date"])


def load_plan_records(paths: list[Path]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for path in sorted(paths):
        payload = _unwrap(_load(path))
        if not payload:
            continue
        date = str(payload.get("actual_data_date") or payload.get("requested_as_of_date") or _date_from_path(path) or "")
        if date and date not in records:
            records[date] = payload
    return records


def _next_0050_returns(records: list[dict[str, Any]]) -> dict[str, float]:
    returns: dict[str, float] = {}
    for current, nxt in zip(records, records[1:]):
        start = _prices(current["signal"]).get("0050.TW", 0.0)
        end = _prices(nxt["signal"]).get("0050.TW", 0.0)
        if start > 0 and end > 0:
            returns[current["date"]] = end / start - 1.0
    return returns


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def build_moira_policy_critic_validation(
    *,
    signal_records: list[dict[str, Any]],
    plan_records: dict[str, dict[str, Any]] | None = None,
    as_of: str | None = None,
    min_trigger_count_for_backtest: int = 5,
) -> dict[str, Any]:
    plan_records = plan_records or {}
    next_returns = _next_0050_returns(signal_records)
    proposal_hits: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in signal_records:
        date = row["date"]
        signal = row["signal"]
        plan = plan_records.get(date, {})
        target = _target_weights(signal)
        current = _current_weights(plan) if plan else {}
        features = _features(signal)
        stale = _as_int(signal.get("business_stale_days"), 0)
        execution_allowed = signal.get("execution_allowed")
        total_risk = _as_int(features.get("total_risk_score"), 0)
        tail_risk = _as_int(features.get("tail_risk_score"), 0)
        momentum_5d = _as_float(features.get("exit_momentum_5d"), 0.0)
        target_00632r = target["00632R.TW"]
        current_00632r = current.get("00632R.TW", 0.0)
        target_0050 = target["0050.TW"]
        current_0050 = current.get("0050.TW", 0.0)
        staged = _staged_tickers(plan)
        next_ret = next_returns.get(date)

        def hit(proposal_id: str, reason: str) -> None:
            proposal_hits[proposal_id].append(
                {
                    "date": date,
                    "reason": reason,
                    "next_0050_return": next_ret,
                    "business_stale_days": stale,
                    "execution_allowed": execution_allowed,
                    "target_0050": target_0050,
                    "current_0050": current_0050,
                    "target_00632r": target_00632r,
                    "current_00632r": current_00632r,
                }
            )

        if stale >= 2:
            hit("freshness_first_review_gate", "business_stale_days_ge_2")
        if execution_allowed is False:
            hit("execution_guard_hard_stop_for_new_risk", "execution_allowed_false")
        if target_00632r - current_00632r >= 0.20 and "00632R.TW" not in staged:
            hit("large_inverse_hedge_staging_review", "large_00632r_increase_without_staging")
        if current_0050 - target_0050 >= 0.05 and total_risk <= 2 and tail_risk == 0 and momentum_5d > 0:
            hit("low_risk_bullish_beta_reduction_cooldown", "large_0050_reduction_low_risk_positive_momentum")
        if target_00632r >= 0.05 and (stale >= 2 or execution_allowed is False):
            hit("hedge_thesis_blocker_echo", "inverse_hedge_target_with_freshness_or_guard_blocker")

    validations: list[dict[str, Any]] = []
    trigger_ledger: dict[str, list[dict[str, Any]]] = {}
    for proposal_id in PROPOSAL_IDS:
        hits = proposal_hits.get(proposal_id, [])
        trigger_ledger[proposal_id] = hits
        returns = [float(row["next_0050_return"]) for row in hits if row.get("next_0050_return") is not None]
        validations.append(
            {
                "proposal_id": proposal_id,
                "trigger_count": len(hits),
                "trigger_dates": [row["date"] for row in hits],
                "sample_next_0050_return_count": len(returns),
                "mean_next_0050_return": _mean(returns),
                "positive_next_0050_return_rate": _mean([1.0 if value > 0 else 0.0 for value in returns]),
                "ready_for_parameter_backtest": len(hits) >= min_trigger_count_for_backtest,
                "status": "needs_more_history" if len(hits) < min_trigger_count_for_backtest else "ready_for_shadow_backtest",
            }
        )

    ready = [row["proposal_id"] for row in validations if row["ready_for_parameter_backtest"]]
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_moira_policy_critic_validation_shadow",
        "policy": "artifact_replay_validation_only_no_rule_change",
        "as_of": as_of or (signal_records[-1]["date"] if signal_records else ""),
        "input_coverage": {
            "signal_record_count": len(signal_records),
            "plan_record_count": len(plan_records),
            "date_start": signal_records[0]["date"] if signal_records else None,
            "date_end": signal_records[-1]["date"] if signal_records else None,
            "next_return_pair_count": len(next_returns),
        },
        "validations": validations,
        "trigger_ledger": trigger_ledger,
        "summary": {
            "ready_for_shadow_backtest": ready,
            "needs_more_history": [row["proposal_id"] for row in validations if not row["ready_for_parameter_backtest"]],
            "min_trigger_count_for_backtest": min_trigger_count_for_backtest,
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


def append_moira_policy_critic_validation_log(log_path: Path, report: dict[str, Any], *, date: str) -> None:
    row = {
        "date": date,
        "input_coverage": report.get("input_coverage"),
        "summary": report.get("summary"),
        "decision": report.get("decision"),
    }
    rows: list[dict[str, Any]] = []
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                existing = json.loads(line)
            except json.JSONDecodeError:
                continue
            if existing.get("date") != date:
                rows.append(existing)
    rows.append(row)
    rows.sort(key=lambda item: str(item.get("date") or ""))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
