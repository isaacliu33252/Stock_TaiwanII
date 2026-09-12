"""Compact daily semantic context summary for GroupA+ shadow reviewers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _top_sources(signal_alignment: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    rows = signal_alignment.get("sources") if isinstance(signal_alignment.get("sources"), list) else []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "name": row.get("name"),
                "available": row.get("available"),
                "direction": row.get("direction"),
                "strength": row.get("strength"),
                "reason": row.get("reason"),
            }
        )
    return sorted(out, key=lambda item: _as_float(item.get("strength")), reverse=True)[:limit]


def _watchlist_summary(watchlist_news: dict[str, Any]) -> dict[str, Any]:
    rows = watchlist_news.get("watchlist") if isinstance(watchlist_news.get("watchlist"), list) else []
    matched = [
        {
            "symbol": row.get("symbol"),
            "label": row.get("label"),
            "matched_count": row.get("matched_count"),
        }
        for row in rows
        if isinstance(row, dict) and int(row.get("matched_count") or 0) > 0
    ]
    return {
        "source": watchlist_news.get("source"),
        "signal_date": watchlist_news.get("signal_date"),
        "lookback_days": watchlist_news.get("lookback_days"),
        "article_count": watchlist_news.get("article_count"),
        "fallback_used": watchlist_news.get("fallback_used"),
        "matched_watchlist": matched[:10],
    }


def build_daily_semantic_context(
    *,
    live_signal: dict[str, Any] | None = None,
    signal_alignment: dict[str, Any] | None = None,
    risk_mechanism: dict[str, Any] | None = None,
    watchlist_news: dict[str, Any] | None = None,
    hierarchical_credit_review: dict[str, Any] | None = None,
    event_execution_quality: dict[str, Any] | None = None,
    relative_exposure_thesis: dict[str, Any] | None = None,
    moira_policy_critic: dict[str, Any] | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    signal = _unwrap(live_signal or {})
    alignment = signal_alignment or {}
    risk = risk_mechanism or {}
    news = watchlist_news or {}
    credit = hierarchical_credit_review or {}
    execution = event_execution_quality or {}
    thesis = relative_exposure_thesis or {}
    critic = moira_policy_critic or {}
    features = signal.get("latest_features") if isinstance(signal.get("latest_features"), dict) else {}
    market_state = signal.get("market_state") if isinstance(signal.get("market_state"), dict) else {}
    proposals = critic.get("proposals") if isinstance(critic.get("proposals"), list) else []

    stale_days = signal.get("business_stale_days")
    execution_allowed = signal.get("execution_allowed")
    hard_blockers: list[str] = []
    if execution_allowed is False:
        hard_blockers.append("execution_guard_false")
    if isinstance(stale_days, (int, float)) and stale_days >= 2:
        hard_blockers.append("source_stale_ge_2_business_days")
    hard_blockers.extend(str(item) for item in execution.get("blockers") or [])
    hard_blockers.extend(str(item) for item in critic.get("blocking_reasons") or [])

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_daily_semantic_context_summary",
        "policy": "context_summary_only_no_target_weight_change",
        "as_of": as_of or str(signal.get("actual_data_date") or signal.get("requested_as_of_date") or ""),
        "market_context": {
            "requested_as_of_date": signal.get("requested_as_of_date"),
            "actual_data_date": signal.get("actual_data_date"),
            "business_stale_days": stale_days,
            "execution_allowed": execution_allowed,
            "execution_regime": signal.get("execution_regime"),
            "market_state": market_state.get("state"),
            "market_state_label": market_state.get("label_zh"),
            "total_risk_score": features.get("total_risk_score"),
            "tail_risk_score": features.get("tail_risk_score"),
            "ma_gap": features.get("ma_gap"),
            "drawdown": features.get("drawdown"),
            "exit_momentum_5d": features.get("exit_momentum_5d"),
        },
        "signal_context": {
            "alignment": alignment.get("alignment"),
            "dominant_direction": alignment.get("dominant_direction"),
            "weighted_share": alignment.get("weighted_share"),
            "available_sources": alignment.get("available_sources"),
            "total_sources": alignment.get("total_sources"),
            "top_sources": _top_sources(alignment),
        },
        "risk_context": {
            "as_of": risk.get("as_of"),
            "mechanism": risk.get("mechanism"),
            "reasons": risk.get("reasons") or [],
        },
        "news_context": _watchlist_summary(news),
        "moira_shadow_context": {
            "credit_primary_attribution": credit.get("primary_attribution"),
            "credit_secondary_attributions": credit.get("secondary_attributions"),
            "relative_exposure_thesis": thesis.get("thesis_class"),
            "relative_exposure_quality": thesis.get("thesis_quality_score"),
            "execution_quality_status": execution.get("status"),
            "execution_quality_score": execution.get("quality_score"),
            "policy_critic_status": critic.get("status"),
            "policy_critic_proposal_count": critic.get("proposal_count"),
            "policy_critic_proposal_ids": [row.get("proposal_id") for row in proposals],
        },
        "compressed_takeaways": {
            "hard_blockers": sorted(set(hard_blockers)),
            "review_focus": [
                "resolve data freshness before live execution review",
                "do not apply policy critic proposals without backtest and signed approval",
                "treat 00632R as short-term hedge review only",
            ],
        },
        "decision": {
            "creates_orders": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "promote_to_live": False,
        },
    }


def append_daily_semantic_context_log(log_path: Path, report: dict[str, Any], *, date: str) -> None:
    row = {
        "date": date,
        "market_context": report.get("market_context"),
        "moira_shadow_context": report.get("moira_shadow_context"),
        "hard_blockers": report.get("compressed_takeaways", {}).get("hard_blockers"),
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
