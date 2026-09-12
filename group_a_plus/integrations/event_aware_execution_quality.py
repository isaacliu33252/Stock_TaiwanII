"""Event-aware execution quality checklist for GroupA+ ETF legs.

This adapts Moira's execution-critic idea into deterministic shadow checks for
00631L/00632R entries, exits, and re-entries. It is review-only and cannot
create orders or target weights.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ETF_TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO")


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


def _target_weights(signal: dict[str, Any]) -> dict[str, float]:
    raw = signal.get("target_weights") or {}
    return {
        "0050.TW": _as_float(raw.get("0050.TW"), 0.0),
        "00631L.TW": _as_float(raw.get("00631L.TW"), 0.0),
        "00632R.TW": _as_float(raw.get("00632R.TW"), 0.0),
        "00679B.TWO": _as_float(raw.get("00679B.TWO"), 0.0),
        "cash": _as_float(raw.get("cash"), 0.0),
    }


def _current_weights(plan: dict[str, Any]) -> dict[str, float]:
    total = _as_float(plan.get("current_total_assets") or plan.get("current_holdings_market_value"), 0.0)
    prices = plan.get("current_prices") if isinstance(plan.get("current_prices"), dict) else {}
    shares = plan.get("current_holdings") if isinstance(plan.get("current_holdings"), dict) else {}
    out: dict[str, float] = {}
    for ticker in ETF_TICKERS:
        out[ticker] = (
            _as_float(shares.get(ticker), 0.0) * _as_float(prices.get(ticker), 0.0) / total
            if total > 0
            else 0.0
        )
    cash = _as_float(plan.get("current_cash_input"), 0.0)
    out["cash"] = cash / total if total > 0 else 0.0
    return out


def _staged_buy_tickers(plan: dict[str, Any]) -> set[str]:
    tickers: set[str] = set()
    for row in plan.get("staged_buys") or []:
        if isinstance(row, dict) and row.get("ticker"):
            tickers.add(str(row["ticker"]))
    return tickers


def _guard_names(plan: dict[str, Any]) -> tuple[list[str], list[str]]:
    summary = plan.get("guard_impact_summary") if isinstance(plan.get("guard_impact_summary"), dict) else {}
    active = [str(item) for item in summary.get("active_guard_names") or []]
    blocked = [str(item) for item in summary.get("blocked_guard_names") or []]
    return active, blocked


def build_event_aware_execution_quality(
    live_signal: dict[str, Any],
    execution_plan: dict[str, Any] | None = None,
    relative_exposure_thesis: dict[str, Any] | None = None,
    liquidity_feedback_backtest: dict[str, Any] | None = None,
    *,
    as_of: str | None = None,
) -> dict[str, Any]:
    signal = _unwrap(live_signal)
    plan = _unwrap(execution_plan or {})
    thesis = relative_exposure_thesis or {}
    liquidity = _unwrap(liquidity_feedback_backtest or {})
    features = signal.get("latest_features") if isinstance(signal.get("latest_features"), dict) else {}
    market_state = signal.get("market_state") if isinstance(signal.get("market_state"), dict) else {}
    target = _target_weights(signal)
    current = _current_weights(plan) if plan else {ticker: 0.0 for ticker in (*ETF_TICKERS, "cash")}
    staged = _staged_buy_tickers(plan)
    active_guards, blocked_guards = _guard_names(plan)

    total_risk = _as_int(features.get("total_risk_score"), 0)
    tail_risk = _as_int(features.get("tail_risk_score"), 0)
    ma_gap = _as_float(features.get("ma_gap"), 0.0)
    drawdown = _as_float(features.get("drawdown"), 0.0)
    momentum_5d = _as_float(features.get("exit_momentum_5d"), 0.0)
    stale_days = _as_int(signal.get("business_stale_days"), 0)
    execution_allowed = signal.get("execution_allowed")
    thesis_class = str(thesis.get("thesis_class") or "")

    checks: list[dict[str, Any]] = []
    blockers: list[str] = []
    warnings: list[str] = []
    supports: list[str] = []

    def add_check(name: str, passed: bool, severity: str, value: Any = None, threshold: Any = None) -> None:
        checks.append(
            {
                "name": name,
                "passed": bool(passed),
                "severity": severity,
                "value": value,
                "threshold": threshold,
            }
        )
        if passed:
            supports.append(name)
        elif severity == "blocker":
            blockers.append(name)
        else:
            warnings.append(name)

    add_check("execution_guard_satisfied", execution_allowed is not False, "blocker", execution_allowed, True)
    add_check("source_fresh_enough", stale_days < 2, "blocker", stale_days, "<2")
    add_check("tail_risk_allows_new_risk", tail_risk == 0, "blocker", tail_risk, 0)
    add_check("total_risk_not_extreme", total_risk < 7, "blocker", total_risk, "<7")

    add_00631l = target["00631L.TW"] > current.get("00631L.TW", 0.0) + 0.01
    add_00632r = target["00632R.TW"] > current.get("00632R.TW", 0.0) + 0.01
    reduce_0050 = target["0050.TW"] < current.get("0050.TW", 0.0) - 0.05
    extended_up = ma_gap >= 0.08 and momentum_5d >= 0.08
    deep_drawdown = drawdown <= -0.08

    add_check("no_00631l_add_when_extended", not (add_00631l and extended_up), "warning", add_00631l, "no add if extended")
    add_check(
        "00631l_add_has_reentry_context",
        not add_00631l or deep_drawdown or thesis_class == "leverage_expansion_thesis_supported",
        "warning",
        {"add_00631l": add_00631l, "drawdown": drawdown, "thesis_class": thesis_class},
        "deep drawdown or supported thesis",
    )
    add_check(
        "00632r_open_is_review_gated",
        not add_00632r or thesis_class == "short_term_inverse_hedge_review_only",
        "blocker",
        {"add_00632r": add_00632r, "thesis_class": thesis_class},
        "short_term_inverse_hedge_review_only",
    )
    add_check(
        "no_large_00632r_chase_without_staging",
        not (add_00632r and target["00632R.TW"] >= 0.20 and "00632R.TW" not in staged),
        "warning",
        {"add_00632r": add_00632r, "target_00632r": target["00632R.TW"], "staged": sorted(staged)},
        "stage large hedge add",
    )
    liquidity_summary = liquidity.get("summary") if isinstance(liquidity.get("summary"), dict) else {}
    liquidity_metrics = liquidity.get("event_metrics") if isinstance(liquidity.get("event_metrics"), dict) else {}
    inverse_metrics = liquidity_metrics.get("00632R.TW") if isinstance(liquidity_metrics.get("00632R.TW"), dict) else {}
    inverse_20d = inverse_metrics.get("fwd_return_20d") if isinstance(inverse_metrics.get("fwd_return_20d"), dict) else {}
    inverse_negative_rate = _as_float(inverse_20d.get("negative_rate"), 0.0)
    liquidity_review_ready = liquidity_summary.get("ready_for_manual_review") is True
    add_check(
        "large_00632r_add_respects_liquidity_feedback_watch",
        not (add_00632r and target["00632R.TW"] >= 0.20 and liquidity_review_ready and inverse_negative_rate >= 0.70),
        "warning",
        {
            "add_00632r": add_00632r,
            "target_00632r": target["00632R.TW"],
            "liquidity_feedback_ready": liquidity_review_ready,
            "historical_00632r_20d_negative_rate_after_trigger": inverse_negative_rate,
        },
        "large inverse hedge add should be staged/manual-review when liquidity feedback watch is validated",
    )
    add_check(
        "0050_reduction_not_aggressive_in_low_risk_bullish_state",
        not (reduce_0050 and total_risk <= 2 and tail_risk == 0 and momentum_5d > 0),
        "warning",
        {"reduce_0050": reduce_0050, "total_risk": total_risk, "tail_risk": tail_risk, "momentum_5d": momentum_5d},
        "avoid aggressive beta reduction in low-risk bullish tape",
    )
    add_check("no_blocked_pretrade_guards", not blocked_guards, "blocker", blocked_guards, [])

    if active_guards:
        warnings.append("active_pretrade_guards_present")
    if market_state.get("state"):
        supports.append(f"market_state={market_state.get('state')}")

    failed = len(blockers) + len(warnings)
    quality = max(0.0, min(1.0, 1.0 - 0.18 * len(blockers) - 0.08 * len(warnings)))
    if blockers:
        status = "blocked_review_only"
    elif warnings:
        status = "caution_review_only"
    else:
        status = "acceptable_review_only"

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_event_aware_execution_quality_shadow",
        "policy": "shadow_only_no_target_weight_change",
        "as_of": as_of or str(signal.get("actual_data_date") or signal.get("requested_as_of_date") or ""),
        "paper_source": {
            "arxiv_id": "2605.01954",
            "title": "Moira: Language-driven Hierarchical Reinforcement Learning for Pair Trading",
            "mapping": "Adapt event-aware trader critique into deterministic ETF execution-quality checks.",
        },
        "status": status,
        "quality_score": round(quality, 4),
        "checks": checks,
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "supporting_evidence": sorted(set(supports)),
        "inputs": {
            "requested_as_of_date": signal.get("requested_as_of_date"),
            "actual_data_date": signal.get("actual_data_date"),
            "business_stale_days": stale_days,
            "execution_allowed": execution_allowed,
            "execution_regime": signal.get("execution_regime"),
            "market_state": market_state.get("state"),
            "total_risk_score": total_risk,
            "tail_risk_score": tail_risk,
            "ma_gap": ma_gap,
            "drawdown": drawdown,
            "exit_momentum_5d": momentum_5d,
            "current_weights": current,
            "target_weights": target,
            "staged_buy_tickers": sorted(staged),
            "active_pretrade_guards": active_guards,
            "blocked_pretrade_guards": blocked_guards,
            "relative_exposure_thesis_class": thesis_class,
            "liquidity_feedback_backtest_ready": liquidity_review_ready,
            "liquidity_feedback_00632r_20d_negative_rate": inverse_negative_rate,
        },
        "decision": {
            "creates_orders": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "promote_to_live": False,
            "requires_backtest_before_guarded_candidate": True,
        },
    }


def append_event_aware_execution_quality_log(log_path: Path, report: dict[str, Any], *, date: str) -> None:
    row = {
        "date": date,
        "status": report.get("status"),
        "quality_score": report.get("quality_score"),
        "blockers": report.get("blockers"),
        "warnings": report.get("warnings"),
        "inputs": report.get("inputs"),
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
