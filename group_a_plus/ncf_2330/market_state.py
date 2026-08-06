"""TSMC market-state classifier for 2330.TW NCF diagnostics."""

from __future__ import annotations


def _risk_probability(result: dict, default: float | None = None) -> float | None:
    if not result.get("available"):
        return default
    value = result.get("probability")
    return float(value) if value is not None else default


def _classify_tsmc_market_state(
    all_results: dict,
    combined_prob: float,
    calibrated_prob: float,
    confidence: float,
    weighted_return: float,
    drawdown_risk: dict,
    severe_drawdown_risk: dict,
    upside_reward: dict,
) -> dict:
    """Classify TSMC leadership phase for advisory diagnostics."""
    h1 = all_results.get(1, {})
    h5 = all_results.get(5, {})
    h20 = all_results.get(20, {})

    h1_prob = float(h1.get("ens_proba", 0.5))
    h5_prob = float(h5.get("ens_proba", 0.5))
    h20_prob = float(h20.get("ens_proba", 0.5))
    h1_ret = float(h1.get("ens_ret", 0.0))
    h5_ret = float(h5.get("ens_ret", 0.0))
    h20_ret = float(h20.get("ens_ret", 0.0))
    h1_dir = str(h1.get("direction", "NEUTRAL"))
    h5_dir = str(h5.get("direction", "NEUTRAL"))
    h20_dir = str(h20.get("direction", "NEUTRAL"))

    tail5 = _risk_probability(drawdown_risk)
    tail8 = _risk_probability(severe_drawdown_risk)
    upside5 = _risk_probability(upside_reward)
    tail_reward_score = (
        upside5 - tail5
        if upside5 is not None and tail5 is not None
        else None
    )

    low_severe_risk = tail8 is None or tail8 <= 0.15
    high_tail_risk = (tail5 is not None and tail5 >= 0.48) or (tail8 is not None and tail8 >= 0.22)
    elevated_tail_risk = (tail5 is not None and tail5 >= 0.40) or (tail8 is not None and tail8 >= 0.16)
    upside_healthy = upside5 is None or upside5 >= 0.45
    upside_weak = upside5 is not None and upside5 <= 0.35

    reasons: list[str] = []

    if (
        h5_dir == "UP"
        and h20_dir == "UP"
        and h5_prob >= 0.56
        and h20_prob >= 0.65
        and calibrated_prob >= 0.58
        and weighted_return >= 0.005
        and upside_healthy
        and low_severe_risk
        and confidence >= 0.45
    ):
        state = 1
        label = "強勢領漲"
        bias = "bullish_leadership"
        reasons.extend([
            "H5/H20 both UP with strong H20 probability",
            "weighted return is positive and upside reward is healthy",
            "severe drawdown risk is low",
        ])
    elif (
        (h5_dir == "DOWN" and h20_dir == "DOWN")
        or (
            calibrated_prob <= 0.48
            and h20_prob <= 0.50
            and (high_tail_risk or weighted_return <= -0.005)
        )
    ):
        state = 5
        label = "趨勢轉弱"
        bias = "bearish"
        reasons.extend([
            "medium/long horizon direction has weakened",
            "calibrated probability is below neutral",
        ])
        if high_tail_risk:
            reasons.append("tail risk is high")
    elif (
        h20_dir == "UP"
        and h20_prob >= 0.58
        and h1_dir == "DOWN"
        and weighted_return <= 0.002
        and (elevated_tail_risk or upside_weak or (tail_reward_score is not None and tail_reward_score <= 0.0))
    ):
        state = 3
        label = "假突破"
        bias = "failed_breakout_risk"
        reasons.extend([
            "H20 remains UP, but short horizon turned DOWN",
            "weighted return is flat or weak",
        ])
        if elevated_tail_risk:
            reasons.append("drawdown risk is elevated")
        if upside_weak or (tail_reward_score is not None and tail_reward_score <= 0.0):
            reasons.append("upside reward does not compensate tail risk")
    elif (
        h20_dir == "UP"
        and (h5_dir == "DOWN" or h1_ret < -0.006 or h5_ret < -0.003)
        and not high_tail_risk
    ):
        state = 4
        label = "拉回整理"
        bias = "pullback_in_uptrend"
        reasons.extend([
            "H20 is still UP",
            "short/medium horizon is pulling back",
            "tail risk is not high enough to confirm trend weakening",
        ])
    else:
        state = 2
        label = "高檔震盪"
        bias = "neutral_bullish"
        reasons.extend([
            "direction remains constructive but not strong enough for leadership",
            "expected return is flat or signals are mixed",
        ])
        if tail8 is not None and tail8 <= 0.15:
            reasons.append("severe drawdown risk remains contained")

    return {
        "state": state,
        "label_zh": label,
        "bias": bias,
        "policy": "diagnostic_only_no_weight_change",
        "rule_version": "tsmc_market_state_v1",
        "reasons": reasons,
        "inputs": {
            "h1_direction": h1_dir,
            "h5_direction": h5_dir,
            "h20_direction": h20_dir,
            "h1_probability_up": round(h1_prob, 6),
            "h5_probability_up": round(h5_prob, 6),
            "h20_probability_up": round(h20_prob, 6),
            "h1_return": round(h1_ret, 6),
            "h5_return": round(h5_ret, 6),
            "h20_return": round(h20_ret, 6),
            "combined_probability_up": round(float(combined_prob), 6),
            "calibrated_probability_up": round(float(calibrated_prob), 6),
            "confidence": round(float(confidence), 6),
            "weighted_return": round(float(weighted_return), 6),
            "prob_fwd_mdd_gt5_h20": round(float(tail5), 6) if tail5 is not None else None,
            "prob_fwd_mdd_gt8_h20": round(float(tail8), 6) if tail8 is not None else None,
            "prob_fwd_gain_gt5_h20": round(float(upside5), 6) if upside5 is not None else None,
            "tail_reward_risk_score": round(float(tail_reward_score), 6) if tail_reward_score is not None else None,
        },
        "state_map": {
            "1": "強勢領漲",
            "2": "高檔震盪",
            "3": "假突破",
            "4": "拉回整理",
            "5": "趨勢轉弱",
        },
    }
