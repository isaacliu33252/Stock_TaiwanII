"""Fine-grained market state classification for GroupA+ live signals."""

from __future__ import annotations

from typing import Any


STATE_PROFILES: dict[str, dict[str, Any]] = {
    "bull_acceleration": {
        "bucket": "bull_trend",
        "label_zh": "多頭加速",
        "allocation_bias": "00631L high weight",
        "risk_level": "risk_on",
    },
    "bull_trend": {
        "bucket": "bull_trend",
        "label_zh": "多頭趨勢",
        "allocation_bias": "00631L high weight",
        "risk_level": "risk_on",
    },
    "late_bull_overheat": {
        "bucket": "bull_trend",
        "label_zh": "多頭末段過熱",
        "allocation_bias": "0050 core with reduced 00631L",
        "risk_level": "medium",
    },
    "bull_pullback_shallow": {
        "bucket": "bull_pullback",
        "label_zh": "多頭淺回檔",
        "allocation_bias": "0050 plus small 00631L",
        "risk_level": "medium",
    },
    "bull_pullback_deep": {
        "bucket": "bull_pullback",
        "label_zh": "多頭深回檔",
        "allocation_bias": "0050 core, keep cash buffer",
        "risk_level": "medium_high",
    },
    "recovery_early": {
        "bucket": "recovery",
        "label_zh": "復甦初期",
        "allocation_bias": "gradual ramp from cash to 0050",
        "risk_level": "medium",
    },
    "recovery_confirmed": {
        "bucket": "recovery",
        "label_zh": "復甦確認",
        "allocation_bias": "gradual ramp up; add 00631L only after confirmation",
        "risk_level": "medium",
    },
    "choppy_range_low_risk": {
        "bucket": "choppy_range",
        "label_zh": "低風險盤整",
        "allocation_bias": "0050 with cash buffer",
        "risk_level": "medium",
    },
    "choppy_range_high_risk": {
        "bucket": "choppy_range",
        "label_zh": "高風險盤整",
        "allocation_bias": "cash first, small 0050 only",
        "risk_level": "medium_high",
    },
    "bear_breakdown": {
        "bucket": "bear_breakdown",
        "label_zh": "空頭跌破",
        "allocation_bias": "cash",
        "risk_level": "risk_off",
    },
    "crash_risk": {
        "bucket": "crash_risk",
        "label_zh": "崩跌風險",
        "allocation_bias": "00632R hedge or full defense",
        "risk_level": "severe",
    },
}


def _num(features: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(features.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def classify_market_state(
    execution_regime: str,
    latest_features: dict[str, Any],
    *,
    signal_alignment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify the live regime into a finer action-oriented market state.

    The coarse execution regimes stay untouched. This classifier only adds
    explainable state metadata for reporting, alerting, and future allocation
    gates.
    """
    regime = str(execution_regime)
    ma_gap = _num(latest_features, "ma_gap")
    drawdown = _num(latest_features, "drawdown")
    exit_momentum = _num(latest_features, "exit_momentum_5d", _num(latest_features, "exit_momentum"))
    total_risk_score = int(_num(latest_features, "total_risk_score"))
    tail_risk_score = int(_num(latest_features, "tail_risk_score"))
    alignment = (signal_alignment or {}).get("alignment")
    dominant = (signal_alignment or {}).get("dominant_direction")

    reasons: list[str] = [
        f"execution_regime={regime}",
        f"ma_gap={ma_gap:.4f}",
        f"drawdown={drawdown:.4f}",
        f"exit_momentum_5d={exit_momentum:.4f}",
        f"total_risk_score={total_risk_score}",
        f"tail_risk_score={tail_risk_score}",
    ]
    if alignment:
        reasons.append(f"signal_alignment={alignment}")
    if dominant:
        reasons.append(f"dominant_direction={dominant}")

    if (
        tail_risk_score >= 2
        or (total_risk_score >= 9 and drawdown <= -0.05)
        or (ma_gap <= -0.08 and exit_momentum <= -0.03)
    ):
        state = "crash_risk"
    elif regime in {"group_a_plus_severe", "group_a_plus_defensive"}:
        state = "bear_breakdown" if total_risk_score >= 7 or ma_gap < -0.02 else "choppy_range_high_risk"
    elif regime == "group_a_plus_recovery":
        state = "recovery_confirmed" if ma_gap >= 0.01 and exit_momentum > 0 else "recovery_early"
    elif ma_gap >= 0.12 or (regime.startswith("ncf_late_bull") and total_risk_score >= 6):
        state = "late_bull_overheat"
    elif ma_gap >= 0.04 and drawdown > -0.03 and total_risk_score <= 4 and dominant != "bearish":
        state = "bull_acceleration"
    elif ma_gap >= 0.02 and drawdown > -0.05 and total_risk_score <= 6:
        state = "bull_trend"
    elif ma_gap >= 0.0 and drawdown > -0.06:
        state = "bull_pullback_shallow"
    elif ma_gap >= -0.03 and drawdown > -0.10:
        state = "bull_pullback_deep" if exit_momentum < 0 else "choppy_range_low_risk"
    elif total_risk_score >= 7 or dominant == "bearish":
        state = "choppy_range_high_risk"
    else:
        state = "choppy_range_low_risk"

    profile = STATE_PROFILES[state]
    return {
        "state": state,
        "bucket": profile["bucket"],
        "label_zh": profile["label_zh"],
        "allocation_bias": profile["allocation_bias"],
        "risk_level": profile["risk_level"],
        "inputs": {
            "execution_regime": regime,
            "ma_gap": ma_gap,
            "drawdown": drawdown,
            "exit_momentum_5d": exit_momentum,
            "total_risk_score": total_risk_score,
            "tail_risk_score": tail_risk_score,
            "signal_alignment": alignment,
            "dominant_direction": dominant,
        },
        "reason": "; ".join(reasons),
    }
