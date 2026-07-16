"""Regime-aware specialist routing for GroupA+ diagnostics.

This module turns existing diagnostics into one explicit advisory routing
decision. It intentionally does not compute portfolio weights; promotion to a
weight-changing rule must happen in a separate walk-forward/backtest step.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _tsmc_health_state(ncf_live_overlay: dict[str, Any] | None) -> str | None:
    health = (ncf_live_overlay or {}).get("tsmc_0050_health") or {}
    if health.get("status") != "available":
        return None
    state = health.get("state")
    return str(state) if state is not None else None


def route_specialist(
    *,
    volatility_gate: dict[str, Any] | None = None,
    market_state: dict[str, Any] | None = None,
    ncf_live_overlay: dict[str, Any] | None = None,
    signal_alignment: dict[str, Any] | None = None,
    latest_features: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Choose which specialist family deserves priority today.

    Priority is deliberately asymmetric:
    crash risk overrides everything; semiconductor/TSMC concentration risk
    overrides normal trend following; high volatility suppresses return
    prediction; low volatility allows trend/momentum participation.
    """
    volatility_gate = volatility_gate or {}
    market_state = market_state or {}
    latest_features = latest_features or {}
    signal_alignment = signal_alignment or {}
    tsmc_state = _tsmc_health_state(ncf_live_overlay)

    total_risk_score = int(_num(latest_features.get("total_risk_score"), 0.0))
    tail_risk_score = int(_num(latest_features.get("tail_risk_score"), 0.0))
    drawdown = _num(latest_features.get("drawdown"), 0.0)
    market_state_name = str(market_state.get("state") or "")

    crash_risk = (
        market_state_name == "crash_risk"
        or tail_risk_score >= 2
        or (total_risk_score >= 9 and drawdown <= -0.05)
    )
    high_vol = bool(volatility_gate.get("high_vol_gate"))
    low_vol = bool(volatility_gate.get("low_vol_gate"))
    semiconductor_risk = tsmc_state in {
        "tsmc_weak_confirmed",
        "tsmc_false_breakout",
        "tsmc_led_narrow",
    }

    if crash_risk:
        route = "crash_deleverage"
        trusted = ["risk_control", "drawdown_control"]
        reliability = "do_not_forecast_returns"
        action = "reduce_leverage"
        allow_return_prediction = False
        allow_00631l_add = False
        level = "high"
        rationale = "Crash-risk conditions override return forecasts; priority is leverage reduction."
    elif semiconductor_risk:
        route = "semiconductor_risk"
        trusted = ["tsmc_0050_health", "ncf_2330", "soxx_risk_proxy"]
        reliability = "gate_leveraged_exposure"
        action = "avoid_00631l_add"
        allow_return_prediction = False
        guidance = ((ncf_live_overlay or {}).get("tsmc_0050_health") or {}).get("reference_guidance") or {}
        allow_00631l_add = bool(guidance.get("allow_00631l_add", False))
        level = "medium"
        rationale = f"TSMC/semiconductor concentration state is {tsmc_state}; avoid treating broad ETF strength as clean market breadth."
    elif high_vol:
        route = "high_volatility"
        trusted = ["volatility_model", "drawdown_model"]
        reliability = "suppress_return_prediction"
        action = "defensive_review"
        allow_return_prediction = False
        allow_00631l_add = False
        level = "medium"
        rationale = "High-volatility gate is active; trend/momentum forecasts should not add leveraged exposure."
    elif low_vol:
        route = "low_volatility"
        trusted = ["trend_model", "momentum_model"]
        reliability = "allow_return_prediction"
        action = "allow_participation"
        allow_return_prediction = True
        allow_00631l_add = True
        level = "low"
        rationale = "Low-volatility regime; trend and momentum models are the primary specialists."
    else:
        route = "neutral"
        trusted = ["calibrated_ensemble", "risk_score"]
        reliability = "calibrate_thresholds"
        action = "hold_or_align"
        allow_return_prediction = True
        allow_00631l_add = True
        level = "low"
        rationale = "No dominant specialist regime; use the active calibrated strategy and normal risk gates."

    return {
        "status": "available",
        "policy": "advisory_only_no_weight_change",
        "route": route,
        "risk_level": level,
        "trusted_specialists": trusted,
        "signal_reliability": reliability,
        "recommended_action": action,
        "allow_return_prediction": allow_return_prediction,
        "allow_00631l_add": allow_00631l_add,
        "inputs": {
            "volatility_gate": volatility_gate.get("gate"),
            "high_vol_gate": high_vol,
            "low_vol_gate": low_vol,
            "market_state": market_state_name or None,
            "market_state_bucket": market_state.get("bucket"),
            "tsmc_0050_health_state": tsmc_state,
            "signal_alignment": signal_alignment.get("alignment"),
            "dominant_direction": signal_alignment.get("dominant_direction"),
            "total_risk_score": total_risk_score,
            "tail_risk_score": tail_risk_score,
            "drawdown": round(drawdown, 6),
        },
        "rationale": rationale,
    }


def append_specialist_routing_shadow_log(
    log_path: Path,
    routing: dict[str, Any],
    *,
    date: str,
    execution_regime: str | None = None,
) -> None:
    """Append one day's specialist route to a JSON-lines log.

    Measurement-only and idempotent per date. The log is for later
    forward-return evaluation; it must not feed live weight calculation.
    """
    if routing.get("status") != "available":
        return
    row = {
        "date": date,
        "route": routing.get("route"),
        "risk_level": routing.get("risk_level"),
        "trusted_specialists": routing.get("trusted_specialists"),
        "signal_reliability": routing.get("signal_reliability"),
        "recommended_action": routing.get("recommended_action"),
        "allow_return_prediction": routing.get("allow_return_prediction"),
        "allow_00631l_add": routing.get("allow_00631l_add"),
        "logged_execution_regime": execution_regime,
        "inputs": routing.get("inputs"),
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
