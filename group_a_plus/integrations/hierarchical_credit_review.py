"""Hierarchical forecast-vs-actual credit review for GroupA+.

This is a shadow-only diagnostic inspired by Moira's selector/trader split.
It compares a prior forecast signal with a later actual/updated signal and
attributes disagreement across data freshness, strategy selection, execution
guard, risk guard, and market noise layers. It never emits target weights.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO")


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


def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def _weights(signal: dict[str, Any]) -> dict[str, float]:
    raw = signal.get("target_weights") or signal.get("planned_target_weights") or {}
    return {ticker: _as_float(raw.get(ticker), 0.0) for ticker in TICKERS} | {
        "cash": _as_float(raw.get("cash", signal.get("target_cash_weight")), 0.0)
    }


def _prices(signal: dict[str, Any]) -> dict[str, float]:
    raw = signal.get("latest_prices") or signal.get("prices") or signal.get("current_prices") or {}
    return {ticker: _as_float(raw.get(ticker), 0.0) for ticker in TICKERS}


def _features(signal: dict[str, Any]) -> dict[str, Any]:
    raw = signal.get("latest_features")
    return raw if isinstance(raw, dict) else {}


def _alignment(signal: dict[str, Any]) -> tuple[str, str]:
    value = signal.get("signal_alignment")
    if isinstance(value, dict):
        return str(value.get("alignment") or ""), str(value.get("dominant_direction") or "")
    market_inputs = signal.get("market_state", {}).get("inputs", {}) if isinstance(signal.get("market_state"), dict) else {}
    return str(value or market_inputs.get("signal_alignment") or ""), str(
        signal.get("dominant_direction") or market_inputs.get("dominant_direction") or ""
    )


def _price_returns(before: dict[str, float], after: dict[str, float]) -> dict[str, float | None]:
    returns: dict[str, float | None] = {}
    for ticker in TICKERS:
        start = before.get(ticker, 0.0)
        end = after.get(ticker, 0.0)
        returns[ticker] = (end / start - 1.0) if start > 0 and end > 0 else None
    return returns


def _target_return(weights: dict[str, float], returns: dict[str, float | None]) -> float | None:
    total = 0.0
    used = False
    for ticker in TICKERS:
        ret = returns.get(ticker)
        if ret is None:
            continue
        total += weights.get(ticker, 0.0) * ret
        used = True
    return total if used else None


def _posture(weights: dict[str, float]) -> str:
    leverage = weights.get("00631L.TW", 0.0)
    inverse = weights.get("00632R.TW", 0.0)
    beta = weights.get("0050.TW", 0.0) + 2.0 * leverage - inverse
    if inverse >= 0.05 and beta < 0.45:
        return "inverse_hedged"
    if leverage >= 0.10:
        return "leveraged_bullish"
    if beta >= 0.35:
        return "unlevered_bullish"
    return "cash_defensive"


def build_hierarchical_credit_review(
    forecast_signal: dict[str, Any],
    actual_signal: dict[str, Any],
    *,
    as_of: str | None = None,
) -> dict[str, Any]:
    forecast = _unwrap(forecast_signal)
    actual = _unwrap(actual_signal)
    forecast_weights = _weights(forecast)
    before_prices = _prices(forecast)
    after_prices = _prices(actual)
    returns = _price_returns(before_prices, after_prices)
    realized_target_return = _target_return(forecast_weights, returns)
    ret_0050 = returns.get("0050.TW")
    posture = _posture(forecast_weights)
    forecast_features = _features(forecast)
    actual_features = _features(actual)
    forecast_alignment, forecast_direction = _alignment(forecast)
    actual_alignment, actual_direction = _alignment(actual)
    forecast_stale = _as_int(forecast.get("business_stale_days"), 0)
    actual_stale = _as_int(actual.get("business_stale_days"), 0)
    forecast_exec_allowed = forecast.get("execution_allowed")
    actual_exec_allowed = actual.get("execution_allowed")
    forecast_tail = _as_int(forecast_features.get("tail_risk_score"), 0)
    actual_tail = _as_int(actual_features.get("tail_risk_score"), 0)
    forecast_total_risk = _as_int(forecast_features.get("total_risk_score"), 0)
    actual_total_risk = _as_int(actual_features.get("total_risk_score"), 0)

    layer_scores = {
        "data_freshness_error": 0.0,
        "execution_error": 0.0,
        "selection_error": 0.0,
        "risk_guard_error": 0.0,
        "market_noise": 0.0,
    }
    evidence: list[str] = []

    if forecast_stale >= 2 or actual_stale >= 2:
        layer_scores["data_freshness_error"] += 0.45
        evidence.append(f"stale_data_forecast={forecast_stale}_actual={actual_stale}")
    if forecast_exec_allowed is False or actual_exec_allowed is False:
        layer_scores["execution_error"] += 0.35
        evidence.append("execution_guard_not_satisfied")
    if forecast_tail != actual_tail or abs(actual_total_risk - forecast_total_risk) >= 3:
        layer_scores["risk_guard_error"] += 0.25
        evidence.append("risk_score_changed_materially")
    if forecast_alignment and actual_alignment and forecast_alignment != actual_alignment:
        layer_scores["selection_error"] += 0.20
        evidence.append(f"signal_alignment_changed={forecast_alignment}->{actual_alignment}")

    if ret_0050 is not None:
        if posture in {"leveraged_bullish", "unlevered_bullish"} and ret_0050 < -0.005:
            layer_scores["selection_error"] += 0.25
            evidence.append("bullish_posture_met_negative_0050_return")
        elif posture == "inverse_hedged" and ret_0050 > 0.005:
            layer_scores["selection_error"] += 0.20
            evidence.append("inverse_hedge_met_positive_0050_return")
        elif abs(ret_0050) < 0.006:
            layer_scores["market_noise"] += 0.25
            evidence.append("0050_move_small")
    if realized_target_return is not None and abs(realized_target_return) < 0.003:
        layer_scores["market_noise"] += 0.15
        evidence.append("target_return_small")

    if max(layer_scores.values()) == 0.0:
        layer_scores["market_noise"] = 0.25
        evidence.append("no_material_layer_break_detected")

    primary = max(layer_scores.items(), key=lambda item: item[1])[0]
    secondary = [key for key, value in sorted(layer_scores.items(), key=lambda item: item[1], reverse=True) if value > 0 and key != primary]
    confidence = min(0.90, 0.45 + layer_scores[primary])

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_hierarchical_credit_review_shadow",
        "policy": "shadow_only_no_target_weight_change",
        "as_of": as_of or str(actual.get("actual_data_date") or actual.get("requested_as_of_date") or ""),
        "paper_source": {
            "arxiv_id": "2605.01954",
            "title": "Moira: Language-driven Hierarchical Reinforcement Learning for Pair Trading",
            "mapping": "Use hierarchical credit assignment to classify forecast-vs-actual misses; not an LLM order generator.",
        },
        "primary_attribution": primary,
        "secondary_attributions": secondary,
        "confidence": round(confidence, 4),
        "layer_scores": {key: round(value, 4) for key, value in layer_scores.items()},
        "evidence": sorted(set(evidence)),
        "forecast": {
            "requested_as_of_date": forecast.get("requested_as_of_date"),
            "actual_data_date": forecast.get("actual_data_date"),
            "business_stale_days": forecast_stale,
            "execution_allowed": forecast_exec_allowed,
            "execution_regime": forecast.get("execution_regime"),
            "signal_alignment": forecast_alignment,
            "dominant_direction": forecast_direction,
            "total_risk_score": forecast_total_risk,
            "tail_risk_score": forecast_tail,
            "posture": posture,
            "target_weights": forecast_weights,
        },
        "actual": {
            "requested_as_of_date": actual.get("requested_as_of_date"),
            "actual_data_date": actual.get("actual_data_date"),
            "business_stale_days": actual_stale,
            "execution_allowed": actual_exec_allowed,
            "execution_regime": actual.get("execution_regime"),
            "signal_alignment": actual_alignment,
            "dominant_direction": actual_direction,
            "total_risk_score": actual_total_risk,
            "tail_risk_score": actual_tail,
        },
        "realized": {
            "price_returns": returns,
            "forecast_target_return_proxy": realized_target_return,
            "benchmark_0050_return": ret_0050,
        },
        "decision": {
            "creates_orders": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "requires_human_review": True,
        },
    }


def append_hierarchical_credit_review_log(log_path: Path, report: dict[str, Any], *, date: str) -> None:
    row = {
        "date": date,
        "primary_attribution": report.get("primary_attribution"),
        "secondary_attributions": report.get("secondary_attributions"),
        "confidence": report.get("confidence"),
        "layer_scores": report.get("layer_scores"),
        "evidence": report.get("evidence"),
        "realized": report.get("realized"),
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
