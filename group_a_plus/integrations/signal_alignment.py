"""Multi-source signal alignment summary for GroupA+ live signals."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_LIVE_SIGNAL_PATH = Path("report/group_a_plus/latest/live_signal.json")
DEFAULT_OUTPUT_PATH = Path("report/group_a_plus/latest/signal_alignment.json")


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _unwrap_standard_json(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("success") is True and isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def _source(name: str, direction: str, strength: float, reason: str, *, available: bool = True) -> dict[str, Any]:
    strength = max(0.0, min(float(strength), 1.0))
    return {
        "name": name,
        "available": bool(available),
        "direction": direction if direction in {"bullish", "bearish", "neutral"} else "neutral",
        "strength": round(strength, 4),
        "reason": reason,
    }


def _direction_from_prob_up(prob_up: float, *, bearish_below: float = 0.45, bullish_above: float = 0.55) -> str:
    if prob_up <= bearish_below:
        return "bearish"
    if prob_up >= bullish_above:
        return "bullish"
    return "neutral"


def _strength_from_prob_up(prob_up: float) -> float:
    return min(abs(prob_up - 0.5) * 2.0, 1.0)


def _ncf_sources(live_signal: dict[str, Any]) -> list[dict[str, Any]]:
    overlay = live_signal.get("ncf_live_overlay") or {}
    out: list[dict[str, Any]] = []

    ncf_631 = overlay.get("ncf_00631l") or {}
    prob_631 = _as_float(ncf_631.get("calibrated_prob_up"), 0.5)
    out.append(
        _source(
            "ncf_00631l",
            _direction_from_prob_up(prob_631),
            max(_strength_from_prob_up(prob_631), _as_float(ncf_631.get("confidence"), 0.0) * 0.5),
            f"00631L calibrated_prob_up={prob_631:.4f}, direction={ncf_631.get('direction', '?')}",
            available=bool(ncf_631),
        )
    )

    ncf_632r = overlay.get("ncf_00632r") or {}
    prob_632r = _as_float(ncf_632r.get("calibrated_prob_up"), 0.5)
    # 00632R is inverse exposure: high probability is bearish for the long-risk portfolio.
    # When direction_conflict is True (prob says UP but predicted_return is DOWN), the
    # directional vote is unreliable — treat as neutral with low strength.
    r_conflict = bool(ncf_632r.get("direction_conflict", False))
    if r_conflict:
        inverse_direction = "neutral"
        r_strength = 0.10
    else:
        inverse_direction = _direction_from_prob_up(1.0 - prob_632r)
        r_strength = max(_strength_from_prob_up(prob_632r), _as_float(ncf_632r.get("confidence"), 0.0) * 0.5)
    out.append(
        _source(
            "ncf_00632r_inverse",
            inverse_direction,
            r_strength,
            f"00632R calibrated_prob_up={prob_632r:.4f}, inverse_direction={inverse_direction}"
            + (", direction_conflict=True→neutral" if r_conflict else ""),
            available=bool(ncf_632r),
        )
    )

    consistency = overlay.get("cross_ticker_consistency") or {}
    market_prob = _as_float(consistency.get("market_probability_up"), 0.5)
    out.append(
        _source(
            "ncf_cross_ticker",
            _direction_from_prob_up(market_prob),
            max(_strength_from_prob_up(market_prob), _as_float(consistency.get("agreement_score"), 0.0) * 0.5),
            f"market_probability_up={market_prob:.4f}, agreement={_as_float(consistency.get('agreement_score'), 0.0):.4f}",
            available=bool(consistency),
        )
    )
    return out


def _finbert_source(live_signal: dict[str, Any]) -> dict[str, Any]:
    finbert = live_signal.get("finbert_sentiment") or {}
    risk = _as_float(finbert.get("risk_score"), 0.0)
    if risk >= 0.55:
        direction = "bearish"
    elif risk <= 0.35 and finbert.get("status") == "ok":
        direction = "bullish"
    else:
        direction = "neutral"
    return _source(
        "finbert_sentiment",
        direction,
        min(abs(risk - 0.45) * 2.0, 1.0),
        f"finbert_risk_score={risk:.4f}, status={finbert.get('status', 'unknown')}",
        available=bool(finbert) and finbert.get("status") in {"ok", "stale"},
    )


def _lm_dictionary_source(live_signal: dict[str, Any]) -> dict[str, Any]:
    lm = live_signal.get("lm_dictionary_sentiment") or {}
    status = str(lm.get("status") or "unknown")
    risk = _as_float(lm.get("risk_score"), 0.0)
    if status == "ok" and risk >= 0.60:
        direction = "bearish"
    elif status == "ok" and risk <= 0.35:
        direction = "bullish"
    else:
        direction = "neutral"
    hit_count = int(_as_float(lm.get("dictionary_hit_count"), 0.0))
    coverage_strength = min(hit_count / 20.0, 1.0)
    directional_strength = min(abs(risk - 0.50) * 2.0, 1.0)
    strength = 0.5 * coverage_strength * directional_strength
    return _source(
        "lm_dictionary_sentiment",
        direction,
        strength,
        (
            f"lm_status={status}, risk_score={risk:.4f}, "
            f"pos={lm.get('positive_count', 0)}, neg={lm.get('negative_count', 0)}, "
            f"hits={hit_count}"
        ),
        available=status == "ok",
    )


def _risk_score_source(live_signal: dict[str, Any]) -> dict[str, Any]:
    features = live_signal.get("latest_features") or {}
    score = int(_as_float(features.get("total_risk_score"), 0.0))
    if score >= 6:
        direction = "bearish"
    elif score <= 2:
        direction = "bullish"
    else:
        direction = "neutral"
    return _source(
        "composite_risk_score",
        direction,
        min(score / 10.0, 1.0),
        f"total_risk_score={score}, chip={features.get('chip_score')}, derivative={features.get('derivative_score')}",
        available=bool(features),
    )


def _factor_lens_stale_days(gate: dict[str, Any], signal_date_str: str | None) -> int:
    """Return how many calendar days the factor lens report is behind the signal date."""
    if not signal_date_str:
        return 0
    generated_at = gate.get("report_generated_at")
    if not generated_at:
        return 0
    try:
        from datetime import date
        report_date = date.fromisoformat(str(generated_at)[:10])
        sig_date = date.fromisoformat(str(signal_date_str)[:10])
        return max(int((sig_date - report_date).days), 0)
    except Exception:
        return 0


def _factor_lens_source(live_signal: dict[str, Any]) -> dict[str, Any]:
    gate = live_signal.get("factor_lens_gate") or {}
    factors = gate.get("factors") or {}
    available = bool(factors)
    passed = [bool(v.get("passed")) for v in factors.values() if isinstance(v, dict)]
    warnings = [bool(v.get("ic_20d_warning")) for v in factors.values() if isinstance(v, dict)]
    if available and passed and all(passed) and not any(warnings):
        direction = "bullish"
        strength = 0.55
    elif available and any(warnings):
        direction = "bearish"
        strength = 0.45
    elif available:
        direction = "neutral"
        strength = 0.25
    else:
        direction = "neutral"
        strength = 0.0

    # Apply staleness penalty: stale reports should not carry full directional weight.
    stale_days = _factor_lens_stale_days(gate, live_signal.get("actual_data_date"))
    staleness_note = ""
    if stale_days >= 2:
        # 2+ days stale → effectively unknown, treat as neutral
        direction = "neutral"
        strength = 0.10
        staleness_note = f", stale={stale_days}d→neutral"
    elif stale_days == 1:
        # 1 day stale → half weight, direction preserved
        strength *= 0.5
        staleness_note = f", stale={stale_days}d→halved"

    return _source(
        "factor_lens",
        direction,
        strength,
        (
            f"all_key_factors_pass={gate.get('all_key_factors_pass')}, "
            f"ic_20d_warnings={sum(1 for item in warnings if item)}"
            f"{staleness_note}"
        ),
        available=available,
    )


def _tbrain_source(live_signal: dict[str, Any]) -> dict[str, Any]:
    """Derive a direction signal from TBrain KDJ features in tbrain_shadow.

    Primary signal: fast KDJ (9,3,3)
      - (J < 0.30 OR J <= historical low quantile) AND K < D  → bearish
      - (J > 0.70 OR J >= historical high quantile) AND K > D → bullish
      - otherwise                                              → neutral
    The quantile band (``tbrain_kdj_j_9_3_3_q_low/q_high``) is an expanding
    historical quantile of J itself, adapted from StockTradebyZ's
    ``KDJQuantileFilter`` — it lets the threshold adapt to this ticker's own
    regime instead of relying solely on a fixed absolute cutoff that can
    drift stale over a multi-year trend. Falls back to the fixed cutoffs
    alone when the quantile band is unavailable (older snapshots).
    Confirmation: slow KDJ (5,21,11). When fast and slow disagree, strength is halved.
    """
    shadow = live_signal.get("tbrain_shadow") or {}
    if shadow.get("status") != "available":
        return _source("tbrain_kdj", "neutral", 0.0, "tbrain_shadow unavailable", available=False)

    features = shadow.get("features") or {}
    k_fast = _as_float(features.get("tbrain_kdj_k_9_3_3"), 0.5)
    d_fast = _as_float(features.get("tbrain_kdj_d_9_3_3"), 0.5)
    j_fast = _as_float(features.get("tbrain_kdj_j_9_3_3"), 0.5)
    k_slow = _as_float(features.get("tbrain_kdj_k_5_21_11"), 0.5)
    d_slow = _as_float(features.get("tbrain_kdj_d_5_21_11"), 0.5)
    j_q_low = features.get("tbrain_kdj_j_9_3_3_q_low")
    j_q_high = features.get("tbrain_kdj_j_9_3_3_q_high")

    fast_bearish = (j_fast < 0.30 or (j_q_low is not None and j_fast <= _as_float(j_q_low, 0.30))) and k_fast < d_fast
    fast_bullish = (j_fast > 0.70 or (j_q_high is not None and j_fast >= _as_float(j_q_high, 0.70))) and k_fast > d_fast
    slow_bearish = k_slow < d_slow
    slow_bullish = k_slow > d_slow

    if fast_bearish:
        direction = "bearish"
        strength = min((0.30 - j_fast) / 0.30 + (d_fast - k_fast), 1.0)
        if not slow_bearish:
            strength *= 0.5
    elif fast_bullish:
        direction = "bullish"
        strength = min((j_fast - 0.70) / 0.30 + (k_fast - d_fast), 1.0)
        if not slow_bullish:
            strength *= 0.5
    else:
        direction = "neutral"
        strength = 0.15

    q_note = ""
    if j_q_low is not None and j_q_high is not None:
        q_note = f", J_q_low={_as_float(j_q_low):.3f}, J_q_high={_as_float(j_q_high):.3f}"

    return _source(
        "tbrain_kdj",
        direction,
        max(0.0, round(strength, 4)),
        f"J={j_fast:.3f}, K={k_fast:.3f}, D={d_fast:.3f} (fast); K_slow={k_slow:.3f}, D_slow={d_slow:.3f}{q_note}",
        available=True,
    )


def _weekly_ma_source(live_signal: dict[str, Any]) -> dict[str, Any]:
    """Weekly MA short/mid/long bullish-alignment — multi-timeframe confirmation.

    Adapted from StockTradebyZ's ``WeeklyMABullFilter``: an orthogonal,
    higher-timeframe (weekly close) trend-structure check alongside the
    daily-frequency sources above.
    """
    shadow = live_signal.get("tbrain_shadow") or {}
    weekly = shadow.get("weekly_ma") or {}
    if weekly.get("status") != "available":
        return _source("weekly_ma_bull", "neutral", 0.0, "weekly_ma unavailable", available=False)

    ma_short = _as_float(weekly.get("ma_short"))
    ma_mid = _as_float(weekly.get("ma_mid"))
    ma_long = _as_float(weekly.get("ma_long"))
    bull = bool(weekly.get("bull_aligned"))
    bear = bool(weekly.get("bear_aligned"))

    if bull:
        direction = "bullish"
        spread = (ma_short - ma_long) / ma_long if ma_long else 0.0
        strength = min(max(spread, 0.0) * 5.0, 0.6)
    elif bear:
        direction = "bearish"
        spread = (ma_long - ma_short) / ma_long if ma_long else 0.0
        strength = min(max(spread, 0.0) * 5.0, 0.6)
    else:
        direction = "neutral"
        strength = 0.15

    return _source(
        "weekly_ma_bull",
        direction,
        round(strength, 4),
        f"weekly MA short={ma_short:.2f}, mid={ma_mid:.2f}, long={ma_long:.2f}, bull_aligned={bull}",
        available=True,
    )


def _execution_regime_source(live_signal: dict[str, Any]) -> dict[str, Any]:
    regime = str(live_signal.get("execution_regime") or "")
    if regime in {"ncf_late_bull_hedge", "group_a_plus_defensive"}:
        direction = "bearish"
        strength = 0.65
    elif regime == "group_a_plus_recovery":
        direction = "neutral"
        strength = 0.35
    else:
        direction = "bullish"
        strength = 0.35
    return _source("execution_regime", direction, strength, f"execution_regime={regime}", available=bool(regime))


def build_signal_alignment(live_signal: dict[str, Any]) -> dict[str, Any]:
    """Build a compact agreement/divergence summary from existing live-signal fields."""

    sources = [
        *_ncf_sources(live_signal),
        _finbert_source(live_signal),
        _lm_dictionary_source(live_signal),
        _risk_score_source(live_signal),
        _factor_lens_source(live_signal),
        _tbrain_source(live_signal),
        _weekly_ma_source(live_signal),
        _execution_regime_source(live_signal),
    ]
    available_sources = [item for item in sources if item.get("available")]
    direction_counts = {
        "bullish": sum(1 for item in available_sources if item["direction"] == "bullish"),
        "bearish": sum(1 for item in available_sources if item["direction"] == "bearish"),
        "neutral": sum(1 for item in available_sources if item["direction"] == "neutral"),
    }
    weighted = {"bullish": 0.0, "bearish": 0.0, "neutral": 0.0}
    for item in available_sources:
        weighted[item["direction"]] += float(item.get("strength", 0.0))
    total_weight = sum(weighted.values()) or 1.0
    weighted_share = {key: round(value / total_weight, 4) for key, value in weighted.items()}

    dominant_direction = max(("bullish", "bearish", "neutral"), key=lambda key: (weighted[key], direction_counts[key]))
    opposing = "bearish" if dominant_direction == "bullish" else "bullish"
    if direction_counts["bullish"] > 0 and direction_counts["bearish"] > 0:
        if min(weighted_share["bullish"], weighted_share["bearish"]) >= 0.25:
            alignment = "wide_divergence"
        else:
            alignment = "mixed"
    elif dominant_direction == "bearish" and weighted_share["bearish"] >= 0.60:
        alignment = "bearish_alignment"
    elif dominant_direction == "bullish" and weighted_share["bullish"] >= 0.60:
        alignment = "bullish_alignment"
    elif direction_counts["neutral"] == len(available_sources):
        alignment = "neutral"
    else:
        alignment = "mixed"

    divergent_sources = [
        item["name"]
        for item in available_sources
        if dominant_direction in {"bullish", "bearish"} and item["direction"] == opposing
    ]
    confidence_penalty = 0.0
    if alignment == "wide_divergence":
        confidence_penalty = 0.25
    elif alignment == "mixed":
        confidence_penalty = 0.10
    if len(available_sources) < 4:
        confidence_penalty += 0.10

    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "strategy_id": live_signal.get("strategy_id"),
        "signal_date": live_signal.get("actual_data_date"),
        "alignment": alignment,
        "dominant_direction": dominant_direction,
        "direction_counts": direction_counts,
        "weighted_share": weighted_share,
        "available_sources": len(available_sources),
        "total_sources": len(sources),
        "divergent_sources": divergent_sources,
        "confidence_penalty": round(min(confidence_penalty, 0.5), 4),
        "sources": sources,
    }


def build_signal_alignment_from_file(
    live_signal_path: Path = DEFAULT_LIVE_SIGNAL_PATH,
    *,
    output_path: Path | None = None,
) -> dict[str, Any]:
    payload = json.loads(live_signal_path.read_text(encoding="utf-8-sig"))
    live_signal = _unwrap_standard_json(payload)
    result = build_signal_alignment(live_signal)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result
