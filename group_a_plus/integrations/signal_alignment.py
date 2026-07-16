"""Multi-source signal alignment summary for GroupA+ live signals."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backtest_group_a_plus_switch_policy import _chip_data_is_stale
from group_a_plus.runners.a2118 import CHIP_DATA_FALLBACK_MAX_STALE_DAYS


def _chip_data_stale_from_features(features: dict[str, Any]) -> bool:
    """True when chip/derivative source tables have had no real data for at
    least CHIP_DATA_FALLBACK_MAX_STALE_DAYS trading days -- the same
    condition a2118's own defensive switch bypasses its chip/derivative/
    total-risk gates for (see the 2026-07-04 chip-data-outage fix). Reused
    here because total_risk_score/chip_score read as 0 during such an
    outage, indistinguishable from a genuinely calm market.
    """
    return _chip_data_is_stale(
        int(_as_float(features.get("chip_data_core_days_since_source_update"), 0.0)),
        CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    )


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


def _aligned_confidence(ncf_signal: dict[str, Any]) -> float:
    """Prefer the panel-aligned confidence (walk-forward-consistent, does not
    drift when the model is periodically retrained on more data) over the
    composite `confidence` field, which is computed from this run's own
    validation-set AUC weights across horizons -- see the 2026-07-02 Fable 5
    audit Option A fix and its 2026-07-09 port to ncf_00632r.py. Falls back
    to the raw `confidence` for signals generated before this field existed.
    """
    aligned = ncf_signal.get("confidence_panel_aligned")
    if aligned is not None:
        return _as_float(aligned, 0.0)
    return _as_float(ncf_signal.get("confidence"), 0.0)


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
            max(_strength_from_prob_up(prob_631), _aligned_confidence(ncf_631) * 0.5),
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
        r_strength = max(_strength_from_prob_up(prob_632r), _aligned_confidence(ncf_632r) * 0.5)
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


def _tsmc_0050_source(live_signal: dict[str, Any]) -> dict[str, Any]:
    overlay = live_signal.get("ncf_live_overlay") or {}
    health = overlay.get("tsmc_0050_health") or {}
    if health.get("status") != "available":
        return _source(
            "ncf_2330_tsmc",
            "neutral",
            0.0,
            f"tsmc_0050_health unavailable: {health.get('reason', health.get('status', 'unknown'))}",
            available=False,
        )

    state = str(health.get("state") or "mixed")
    if state == "tsmc_weak_confirmed":
        direction = "bearish"
        strength = 0.55
    elif state == "healthy_leadership":
        direction = "bullish"
        strength = 0.45
    elif state == "tsmc_false_breakout":
        direction = "neutral"
        strength = 0.35
    elif state == "tsmc_led_narrow":
        direction = "neutral"
        strength = 0.25
    else:
        direction = "neutral"
        strength = 0.15

    prob = _as_float(health.get("ncf_2330_h20_prob_up"), _as_float(health.get("ncf_2330_calibrated_prob_up"), 0.5))
    tail = health.get("ncf_2330_prob_fwd_mdd_gt5_h20")
    severe_tail = health.get("ncf_2330_prob_fwd_mdd_gt8_h20")
    market_state = health.get("ncf_2330_market_state") or {}
    returns = health.get("returns") or {}
    tsmc_5d = (returns.get("2330.TW") or {}).get("5d")
    ex_5d = (returns.get("0050_ex_tsmc_proxy") or {}).get("5d")
    return _source(
        "ncf_2330_tsmc",
        direction,
        strength,
        (
            f"state={state}, 2330_h20_prob_up={prob:.4f}, "
            f"2330_tail_risk={tail}, 2330_severe_tail={severe_tail}, "
            f"2330_market_state={market_state.get('state')}, "
            f"2330_5d={tsmc_5d}, 0050_ex_tsmc_5d={ex_5d}"
        ),
        available=True,
    )


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
    result = _source(
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
    # 2026-07-07 Fable audit: this source English-tokenizes watchlist_news.json,
    # which is Chinese-language TW news (LTN/FinMind) -- status is structurally
    # never "ok" (occasional English tokens are proper nouns like source names,
    # never real financial-sentiment words). This is a known, permanent
    # limitation, not a daily failure -- flagged separately from `available` so
    # build_signal_alignment can exclude it from total_sources instead of
    # perpetually reporting e.g. "10/11 available" as if something regressed.
    result["structural_limitation"] = "english_only_dictionary_vs_chinese_news_source"
    return result


def _risk_score_source(live_signal: dict[str, Any]) -> dict[str, Any]:
    features = live_signal.get("latest_features") or {}
    score = int(_as_float(features.get("total_risk_score"), 0.0))
    # total_risk_score is entirely chip/derivative-score derived, so it reads
    # as 0 -- "bullish" below -- during a chip-data outage, which is exactly
    # backwards: unknown risk should not vote bullish. Exclude this source
    # from the alignment vote instead of guessing a direction from missing data.
    chip_data_stale = _chip_data_stale_from_features(features)
    if chip_data_stale:
        return _source(
            "composite_risk_score",
            "neutral",
            0.0,
            f"total_risk_score unavailable: chip/derivative data stale "
            f"(chip_data_core_days_since_source_update="
            f"{features.get('chip_data_core_days_since_source_update')})",
            available=False,
        )
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
    # M7 (2026-07-02 Fable 5 audit): "ncf_late_bull_hedge" (and its soft
    # variant) is *derived from* the ncf_00631l signal (a2118's late-bull
    # trigger reads h20_prob/confidence from that same source) -- voting
    # bearish here on top of the ncf_00631l/ncf_00632r_inverse/
    # ncf_cross_ticker sources double-counts one NCF reading as up to four
    # "independent" bearish votes, inflating weighted_share["bearish"] and
    # making it easier to cross the bearish_alignment/wide_divergence
    # thresholds that _apply_bearish_high_risk_trim (daily_signal.py) uses
    # to apply an *additional* 00631L cut on top of a2118's own hedge for
    # the same underlying signal. "group_a_plus_defensive" is a genuinely
    # independent (MA/price-derived) technical signal and still votes.
    if regime in {"ncf_late_bull_hedge", "ncf_late_bull_hedge_soft"}:
        return _source(
            "execution_regime",
            "neutral",
            0.0,
            f"execution_regime={regime} (excluded from vote: derived from ncf_00631l, already counted there)",
            available=False,
        )
    if regime == "group_a_plus_defensive":
        direction = "bearish"
        strength = 0.65
    elif regime == "group_a_plus_recovery":
        direction = "neutral"
        strength = 0.35
    else:
        direction = "bullish"
        strength = 0.35
    return _source("execution_regime", direction, strength, f"execution_regime={regime}", available=bool(regime))


def _source_by_name(sources: list[dict[str, Any]], name: str) -> dict[str, Any]:
    for source in sources:
        if source.get("name") == name:
            return source
    return {}


def _leverage_suitability(
    live_signal: dict[str, Any],
    *,
    alignment: str,
    dominant_direction: str,
    weighted_share: dict[str, float],
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    """Translate GroupA+ + ncf_2330 context into a 0-3 00631L suitability tier.

    This is advisory metadata only. It intentionally does not alter target
    weights, because ncf_2330 production-weight overlays were previously
    backtested and rejected.
    """
    regime = str(live_signal.get("execution_regime") or "")
    features = live_signal.get("latest_features") or {}
    total_risk_score = int(_as_float(features.get("total_risk_score"), 0.0))
    tail_risk_score = int(_as_float(features.get("tail_risk_score"), 0.0))
    # See _chip_data_stale_from_features: total_risk_score reads as 0 during
    # a chip-data outage, so treat "chip data stale" as if the high-risk
    # thresholds below were met -- don't let a data outage silently look
    # like a calm, high-suitability market.
    chip_data_stale = _chip_data_stale_from_features(features)
    overlay = live_signal.get("ncf_live_overlay") or {}
    tsmc_health = overlay.get("tsmc_0050_health") or {}
    tsmc_state = str(tsmc_health.get("state") or "unavailable")
    tsmc_guidance = (tsmc_health.get("reference_guidance") or {}).get("reference_action")
    ncf_631_payload = overlay.get("ncf_00631l") or {}
    ncf_631_prob = _as_float(ncf_631_payload.get("calibrated_prob_up"), 0.5)
    ncf_631_tail = ncf_631_payload.get("prob_fwd_mdd_gt5_h20")
    ncf_631_tail_value = _as_float(ncf_631_tail, 0.0) if ncf_631_tail is not None else 0.0
    ncf_2330_tail = tsmc_health.get("ncf_2330_prob_fwd_mdd_gt5_h20")
    ncf_2330_tail_value = _as_float(ncf_2330_tail, 0.0) if ncf_2330_tail is not None else 0.0
    ncf_2330_severe_tail = tsmc_health.get("ncf_2330_prob_fwd_mdd_gt8_h20")
    ncf_2330_severe_tail_value = (
        _as_float(ncf_2330_severe_tail, 0.0)
        if ncf_2330_severe_tail is not None
        else 0.0
    )
    ncf_2330_market_state = tsmc_health.get("ncf_2330_market_state") or {}
    ncf_2330_market_state_id = ncf_2330_market_state.get("state")

    ncf_631 = _source_by_name(sources, "ncf_00631l")
    ncf_cross = _source_by_name(sources, "ncf_cross_ticker")
    ncf_631_bullish = ncf_631.get("available") and ncf_631.get("direction") == "bullish"
    ncf_cross_bullish = ncf_cross.get("available") and ncf_cross.get("direction") == "bullish"
    # Research calibration: scripts/misc/evaluate_ncf_2330_00631l_tier.py
    # found that ncf_2330 weakness alone is too noisy. A tier-0 leverage veto
    # needs 00631L's own model to agree.
    l631_weak = ncf_631_prob <= 0.50 or ncf_631_tail_value >= 0.60
    l631_bull_confirmed = ncf_631_prob >= 0.56 and (
        ncf_631_tail is None or ncf_631_tail_value <= 0.40
    )
    tsmc_tail_elevated = ncf_2330_tail is not None and ncf_2330_tail_value >= 0.45
    tsmc_severe_tail_elevated = (
        ncf_2330_severe_tail is not None and ncf_2330_severe_tail_value >= 0.16
    )
    tsmc_trend_weak = ncf_2330_market_state_id == 5

    if (
        regime == "group_a_plus_defensive"
        or (
            (
                tsmc_state == "tsmc_weak_confirmed"
                or tsmc_guidance == "manual_review"
                or tsmc_tail_elevated
                or tsmc_severe_tail_elevated
                or tsmc_trend_weak
            )
            and l631_weak
        )
        or ((total_risk_score >= 9 or chip_data_stale) and l631_weak)
        or (alignment == "bearish_alignment" and weighted_share.get("bearish", 0.0) >= 0.65)
    ):
        tier = 0
        label = "不利 00631L"
        action = "avoid_00631l"
        reason = "defensive/high-risk or ncf_2330 TSMC weakness context"
    elif (
        tsmc_state == "tsmc_led_narrow"
        or tsmc_state == "tsmc_false_breakout"
        or tsmc_guidance == "avoid_add_00631l"
        or total_risk_score >= 6
        or chip_data_stale
        or tail_risk_score >= 2
        or l631_weak
        or (dominant_direction == "bearish" and weighted_share.get("bearish", 0.0) >= 0.50)
    ):
        tier = 1
        label = "只適合 0050"
        action = "0050_only"
        reason = "risk is elevated or TSMC-led breadth is narrow; do not add leverage"
    elif (
        regime in {"golden1", "group_a_plus_recovery"}
        and tsmc_state == "healthy_leadership"
        and total_risk_score <= 2
        and not chip_data_stale
        and alignment == "bullish_alignment"
        and ncf_631_bullish
        and l631_bull_confirmed
        and ncf_cross_bullish
    ):
        tier = 3
        label = "適合提高 00631L"
        action = "raise_00631l"
        reason = "GroupA+ is risk-on, ncf_2330 leadership is healthy, and NCF breadth is bullish"
    else:
        tier = 2
        label = "可持有 0050 + 小 00631L"
        action = "hold_0050_small_00631l"
        reason = "risk-on context is not strong enough to raise leverage, but no hard 00631L veto is active"

    checklist = overlay.get("ncf_2330_checklist") or {}
    factor_quality = checklist.get("factor_quality_overlay") or {}
    fq_risk_score = _as_float(factor_quality.get("risk_score"), 0.0)
    fq_net_score = _as_float(factor_quality.get("net_score"), 0.0)
    fq_signal = str(factor_quality.get("signal") or "")
    shadow_momentum_candidate = (
        tier == 2
        and fq_risk_score >= 4.0
        and fq_net_score <= -2.0
    )
    shadow_note = (
        "shadow_momentum_confirm: factor-quality overlay is high-risk/high-momentum; "
        "daily shadow favored tier2->tier3, but sample is small so production tier is unchanged"
        if shadow_momentum_candidate
        else None
    )

    return {
        "schema_version": 1,
        "tier": tier,
        "label_zh": label,
        "action": action,
        "policy": "advisory_only_no_weight_change",
        "reason": reason,
        "shadow_momentum_candidate": shadow_momentum_candidate,
        "shadow_momentum_note": shadow_note,
        "inputs": {
            "execution_regime": regime,
            "alignment": alignment,
            "dominant_direction": dominant_direction,
            "weighted_share": weighted_share,
            "total_risk_score": total_risk_score,
            "chip_data_stale": chip_data_stale,
            "tail_risk_score": tail_risk_score,
            "ncf_2330_tsmc_state": tsmc_state,
            "ncf_2330_reference_action": tsmc_guidance,
            "ncf_2330_market_state": ncf_2330_market_state,
            "ncf_00631l_direction": ncf_631.get("direction"),
            "ncf_00631l_prob_up": ncf_631_prob,
            "ncf_00631l_prob_fwd_mdd_gt5_h20": ncf_631_tail,
            "ncf_2330_prob_fwd_mdd_gt5_h20": ncf_2330_tail,
            "ncf_2330_prob_fwd_mdd_gt8_h20": ncf_2330_severe_tail,
            "ncf_cross_ticker_direction": ncf_cross.get("direction"),
            "ncf_2330_factor_quality_signal": fq_signal or None,
            "ncf_2330_factor_quality_risk_score": fq_risk_score if factor_quality else None,
            "ncf_2330_factor_quality_net_score": fq_net_score if factor_quality else None,
        },
        "tier_map": {
            "0": "不利 00631L",
            "1": "只適合 0050",
            "2": "可持有 0050 + 小 00631L",
            "3": "適合提高 00631L",
        },
    }


def build_signal_alignment(
    live_signal: dict[str, Any],
    *,
    extra_sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a compact agreement/divergence summary from existing live-signal fields.

    `extra_sources` defaults to None (zero behavior change for every existing
    caller). Fable audit (2026-07-16, combination opportunities #8): the 9
    production sources below have never included trough_nowcast,
    compounding_regime, or crash_risk_alert, even though all three are already
    computed daily. This hook lets
    group_a_plus/integrations/signal_alignment_shadow_variant.py append those
    as additional `_source(...)`-shaped votes and reuse this exact
    weighted_share/alignment/leverage_suitability computation for a
    shadow-only comparison, instead of forking the aggregation logic.
    """

    sources = [
        *_ncf_sources(live_signal),
        _tsmc_0050_source(live_signal),
        _finbert_source(live_signal),
        _lm_dictionary_source(live_signal),
        _risk_score_source(live_signal),
        _factor_lens_source(live_signal),
        _tbrain_source(live_signal),
        _weekly_ma_source(live_signal),
        _execution_regime_source(live_signal),
        *(extra_sources or []),
    ]
    countable_sources = [item for item in sources if not item.get("structural_limitation")]
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
        "total_sources": len(countable_sources),
        "divergent_sources": divergent_sources,
        "confidence_penalty": round(min(confidence_penalty, 0.5), 4),
        "leverage_suitability": _leverage_suitability(
            live_signal,
            alignment=alignment,
            dominant_direction=dominant_direction,
            weighted_share=weighted_share,
            sources=sources,
        ),
        "sources": sources,
    }


def append_signal_alignment_shadow_log(log_path: Path, alignment: dict[str, Any]) -> None:
    """Append one day's alignment classification to a JSON-lines log for
    later forward-return evaluation.

    Fable audit (2026-07-08, #10): alignment drives real production
    behavior -- it's a direct input to _apply_bearish_high_risk_trim,
    signal_alerts (signal_wide_divergence, leverage_suitability_tierN), and
    market_state classification -- but unlike garch_regime_shadow (which
    logs daily for exactly this purpose), no one has ever recorded whether
    e.g. wide_divergence actually predicts anything before or after acting
    on it. This is measurement-only, mirroring
    garch_regime_shadow.append_garch_regime_shadow_log's idempotent-per-date
    pattern: it does not change target_weights or execution_regime.
    """
    signal_date = alignment.get("signal_date")
    if not signal_date:
        return
    row = {
        "date": signal_date,
        "strategy_id": alignment.get("strategy_id"),
        "alignment": alignment.get("alignment"),
        "dominant_direction": alignment.get("dominant_direction"),
        "weighted_share": alignment.get("weighted_share"),
        "confidence_penalty": alignment.get("confidence_penalty"),
        "leverage_suitability_tier": (alignment.get("leverage_suitability") or {}).get("tier"),
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
