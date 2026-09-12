"""Adaptive quantile risk gate for GroupA+.

Research/shadow translation of arXiv:2605.24345
("Evolving Robustness-Exploration Trade-off in Online Reinforcement Learning
via Quantile Bayesian Risk MDPs"). The paper's useful production lesson is
not a new trading model: it is an adaptive risk posture under epistemic
uncertainty. This module therefore produces a diagnostic quantile posture and
pre-trade policy suggestions only. It must not feed target weights, target
shares, execution_regime, or base_regime without a separate out-of-sample
promotion evaluation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


POSTURES = (
    "pessimistic_0.20",
    "defensive_0.35",
    "neutral_0.50",
    "controlled_exploration_0.65",
)


def _status(payload: dict[str, Any] | None, key: str) -> str:
    section = (payload or {}).get(key)
    if not isinstance(section, dict):
        return "unknown"
    return str(section.get("status") or "unknown")


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _forecast_error_penalty(yesterday_review: dict[str, Any] | None) -> tuple[float, dict[str, Any], list[str]]:
    """Convert yesterday-vs-actual review into a small uncertainty penalty.

    Accepted shapes are intentionally loose so the gate can read future daily
    review artifacts without creating a hard schema dependency.
    """
    if not isinstance(yesterday_review, dict):
        return 0.0, {"status": "missing"}, ["yesterday_review_missing"]

    pnl_pct = yesterday_review.get("latest_strategy_return_pct")
    if pnl_pct is None:
        pnl_pct = yesterday_review.get("actual_return_pct")
    if pnl_pct is None:
        pnl_pct = yesterday_review.get("return_pct")
    pnl = _as_float(pnl_pct, 0.0)

    miss = bool(
        yesterday_review.get("direction_miss")
        or yesterday_review.get("forecast_miss")
        or yesterday_review.get("latest_strategy_direction_miss")
    )

    penalty = 0.0
    reasons: list[str] = []
    if pnl <= -0.01:
        penalty += 0.12
        reasons.append("yesterday_loss_ge_1pct")
    elif pnl <= -0.003:
        penalty += 0.06
        reasons.append("yesterday_loss_ge_0_3pct")
    if miss:
        penalty += 0.08
        reasons.append("yesterday_direction_miss")

    return min(penalty, 0.20), {"status": "available", "return_pct": pnl, "direction_miss": miss}, reasons


def classify_adaptive_quantile_risk_gate(
    live_signal: dict[str, Any],
    *,
    ops_health: dict[str, Any] | None = None,
    strategy_trust: dict[str, Any] | None = None,
    yesterday_review: dict[str, Any] | None = None,
    regime_analog_count: int | None = None,
) -> dict[str, Any]:
    """Classify today's GroupA+ signal into an adaptive quantile posture.

    The output is advisory-only. The quantile language mirrors the paper:
    lower-tail quantiles represent robustness under uncertainty, while a
    modest upper-tail quantile is allowed only when data are fresh and model
    diagnostics agree.
    """
    execution_allowed = live_signal.get("execution_allowed")
    business_stale_days = int(_as_float(live_signal.get("business_stale_days"), 0.0))
    calendar_stale_days = int(_as_float(live_signal.get("calendar_stale_days"), 0.0))
    target_weights = live_signal.get("target_weights") or {}
    ncf_overlay = live_signal.get("ncf_live_overlay") or {}
    signal_alignment = live_signal.get("signal_alignment") or {}
    tail_conformal = live_signal.get("tail_conformal") or {}
    garch_gate = ((live_signal.get("garch_regime_shadow") or {}).get("volatility_gate") or {})
    leverage_suitability = signal_alignment.get("leverage_suitability") or {}

    uncertainty = 0.0
    exploration_credit = 0.0
    reasons: list[str] = []

    if execution_allowed is False:
        uncertainty += 0.22
        reasons.append("execution_guard_not_satisfied")
    elif execution_allowed is True:
        exploration_credit += 0.08
        reasons.append("execution_guard_satisfied")
    else:
        uncertainty += 0.06
        reasons.append("execution_allowed_unknown")

    if business_stale_days >= 2:
        uncertainty += min(0.08 + 0.04 * (business_stale_days - 1), 0.20)
        reasons.append(f"business_stale_days={business_stale_days}")
    elif business_stale_days == 1:
        uncertainty += 0.04
        reasons.append("business_stale_days=1")
    else:
        exploration_credit += 0.05
        reasons.append("business_fresh")

    ncf_status = str(ncf_overlay.get("status") or "unknown")
    if ncf_status in {"stale", "unavailable", "missing"}:
        uncertainty += 0.12
        reasons.append(f"ncf_live_overlay_{ncf_status}")
    elif ncf_status in {"applied", "not_applicable"}:
        exploration_credit += 0.04
        reasons.append(f"ncf_live_overlay_{ncf_status}")

    data_quality_problem = any(
        _status(ops_health, key) in {"warning", "degraded", "error", "critical"}
        for key in ("module_health", "feature_table_sync", "external_data_freshness")
    )
    if data_quality_problem:
        uncertainty += 0.12
        reasons.append("ops_health_data_quality_problem")

    trust_level = str((strategy_trust or {}).get("trust_level") or "unknown")
    if trust_level == "ABSTAIN":
        uncertainty += 0.14
        reasons.append("strategy_trust_abstain")
    elif trust_level == "SHADOW_ONLY":
        uncertainty += 0.08
        reasons.append("strategy_trust_shadow_only")
    elif trust_level == "TRUST":
        exploration_credit += 0.04
        reasons.append("strategy_trust_trust")

    alignment = str(signal_alignment.get("alignment") or "")
    divergent_sources = signal_alignment.get("divergent_sources") or []
    if alignment in {"wide_divergence", "mixed", "conflicted", "divergent"} or divergent_sources:
        uncertainty += 0.10
        reasons.append(f"signal_alignment_disagreement={alignment}")
    elif alignment in {"bullish_alignment", "aligned"}:
        exploration_credit += 0.04
        reasons.append(f"signal_alignment={alignment}")

    tail_state = str(tail_conformal.get("state") or "")
    if tail_conformal.get("allow_00631l_add") is False or tail_state not in {"", "TAIL_RISK_NORMAL"}:
        uncertainty += 0.10
        reasons.append(f"tail_conformal_state={tail_state or 'unknown'}")

    if garch_gate.get("high_vol_gate") is True:
        uncertainty += 0.08
        reasons.append("garch_high_vol_gate")

    tier = leverage_suitability.get("tier")
    if tier is not None and _as_float(tier) <= 1:
        uncertainty += 0.06
        reasons.append(f"leverage_suitability_tier={tier}")

    if regime_analog_count is not None:
        if regime_analog_count < 20:
            uncertainty += 0.08
            reasons.append(f"regime_analog_count_low={regime_analog_count}")
        elif regime_analog_count >= 60:
            exploration_credit += 0.05
            reasons.append(f"regime_analog_count_sufficient={regime_analog_count}")

    forecast_penalty, forecast_components, forecast_reasons = _forecast_error_penalty(yesterday_review)
    uncertainty += forecast_penalty
    reasons.extend(forecast_reasons)

    uncertainty = _clip(uncertainty, 0.0, 1.0)
    exploration_credit = _clip(exploration_credit, 0.0, 0.30)
    raw_quantile = _clip(0.50 - 0.35 * uncertainty + 0.20 * exploration_credit, 0.20, 0.65)

    if raw_quantile <= 0.28:
        posture = "pessimistic_0.20"
        quantile_level = 0.20
        max_00631l_weight = 0.0
        min_cash_weight = 0.45
    elif raw_quantile <= 0.42:
        posture = "defensive_0.35"
        quantile_level = 0.35
        max_00631l_weight = 0.0
        min_cash_weight = 0.30
    elif raw_quantile <= 0.55:
        posture = "neutral_0.50"
        quantile_level = 0.50
        max_00631l_weight = 0.10
        min_cash_weight = 0.20
    else:
        posture = "controlled_exploration_0.65"
        quantile_level = 0.65
        max_00631l_weight = 0.20
        min_cash_weight = 0.10

    current_00631l_weight = _as_float(target_weights.get("00631L.TW"), 0.0)
    current_cash_weight = _as_float(target_weights.get("cash"), 0.0)

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_adaptive_quantile_risk_gate_shadow",
        "policy": "shadow_only_no_target_weight_change",
        "paper_source": {
            "arxiv_id": "2605.24345",
            "title": "Evolving Robustness-Exploration Trade-off in Online Reinforcement Learning via Quantile Bayesian Risk MDPs",
            "mapping": "lower-tail quantile means robust under epistemic uncertainty; upper-tail quantile means controlled exploration only after data quality improves",
        },
        "quantile_level": quantile_level,
        "raw_quantile_score": round(raw_quantile, 4),
        "risk_posture": posture,
        "uncertainty_score": round(uncertainty, 4),
        "exploration_credit": round(exploration_credit, 4),
        "reason_codes": sorted(set(reasons)),
        "recommended_shadow_limits": {
            "max_00631l_weight": max_00631l_weight,
            "min_cash_weight": min_cash_weight,
            "allow_new_leverage_long": max_00631l_weight > 0 and execution_allowed is True,
            "allow_00632r_hedge": posture in {"pessimistic_0.20", "defensive_0.35", "neutral_0.50"},
            "hedge_policy": "manual_review_when_execution_guard_blocked" if execution_allowed is False else "normal_pretrade_guards_apply",
        },
        "current_signal_reference": {
            "actual_data_date": live_signal.get("actual_data_date"),
            "business_stale_days": business_stale_days,
            "calendar_stale_days": calendar_stale_days,
            "execution_allowed": execution_allowed,
            "execution_regime": live_signal.get("execution_regime"),
            "base_regime": live_signal.get("base_regime"),
            "target_00631l_weight": current_00631l_weight,
            "target_cash_weight": current_cash_weight,
            "target_exceeds_shadow_00631l_limit": current_00631l_weight > max_00631l_weight,
            "target_cash_below_shadow_floor": current_cash_weight < min_cash_weight,
        },
        "components": {
            "ncf_live_overlay_status": ncf_status,
            "signal_alignment": alignment,
            "signal_divergent_sources": divergent_sources,
            "strategy_trust_level": trust_level,
            "ops_health_data_quality_problem": data_quality_problem,
            "tail_conformal_state": tail_state,
            "tail_conformal_allow_00631l_add": tail_conformal.get("allow_00631l_add"),
            "garch_high_vol_gate": garch_gate.get("high_vol_gate"),
            "leverage_suitability_tier": tier,
            "regime_analog_count": regime_analog_count,
            "yesterday_forecast_review": forecast_components,
        },
        "decision": {
            "shadow_ready": True,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "promote_to_live": False,
            "requires_walk_forward_before_promotion": True,
        },
    }


def append_adaptive_quantile_risk_gate_shadow_log(
    log_path: Path,
    result: dict[str, Any],
    *,
    date: str,
) -> None:
    """Append one day's adaptive quantile posture, idempotent per date."""
    row = {
        "date": date,
        "risk_posture": result.get("risk_posture"),
        "quantile_level": result.get("quantile_level"),
        "uncertainty_score": result.get("uncertainty_score"),
        "exploration_credit": result.get("exploration_credit"),
        "reason_codes": result.get("reason_codes"),
        "recommended_shadow_limits": result.get("recommended_shadow_limits"),
        "current_signal_reference": result.get("current_signal_reference"),
        "components": result.get("components"),
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
            if existing.get("date") != row["date"]:
                rows.append(existing)
    rows.append(row)
    rows.sort(key=lambda r: r.get("date", ""))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
