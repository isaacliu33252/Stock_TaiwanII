"""NCF (Next Close Forecast) integration for Group A+.

Loads ncf_00631l / ncf_00632r daily JSON outputs and derives a composite
downside signal that modulates the 00631L allocation within the golden1 regime.

Signal interpretation
---------------------
ncf_00631l (2x bull ETF):
  - calibrated_prob_up < 0.5  → bearish for 00631L → reduce 00631L weight
  - calibrated_prob_up > 0.5  → bullish for 00631L → maintain weight
  - confidence [0.1–1.0]      → scales the adjustment magnitude

ncf_00632r (1x inverse ETF):
  - calibrated_prob_up > 0.5  → 00632R rises → 0050/00631L falls → bearish
  - calibrated_prob_up < 0.5  → 00632R falls → 0050/00631L rises → bullish

Combined downside signal [0.0–1.0]:
  ncf_downside = 0.6 × l_bear + 0.4 × r_bull
  where:
    l_bear = max(0, 0.5 − prob_up_631l) × 2 × conf_631l
    r_bull = max(0, prob_up_632r − 0.5) × 2 × conf_632r

Regime-gated signal (updated 2026-06-26):
  The ma_gap_bull_threshold suppression parameter was originally added on the
  assumption that NCF is less reliable in strong bull (ma_gap > 15%). This
  assumption was proven WRONG by retraining with late-bull calibration:
    H=5  AUC in late-bull (ma_gap > 15%): 0.7020  ← HIGHER than near-MA bull
    H=20 AUC in late-bull (ma_gap > 15%): 0.8469  ← MUCH higher
  The default ma_gap_bull_threshold is now 0.40 (effectively disabled for
  normal late-bull conditions). Runners do not pass ma_gap to these functions,
  so live behavior is unchanged; this parameter is retained for backward
  compatibility and test coverage only.

  For the late-bull targeted strategy, see group_a_plus.runners.a2118 which
  uses a purpose-built regime overlay instead of this continuous suppression.

Golden1 weight adjustment:
  00631L reduced by up to 50% of its base allocation (capped to avoid full exit)
  freed budget → cash
  Neither 0050 nor 00679B is touched by NCF overlay.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from group_a_plus.integrations.tbrain_features import direction_magnitude_gate


DEFAULT_HORIZON_AUC_PRIORS: dict[str, dict[str, float]] = {
    # Multi-year OOS AUC, 2022-2026.
    # 00631L source: NCF_00631L_HANDOFF_CLAUDE_20260627.md.
    # 00632R source: results/ncf_multiyear_wf_00632r.json / NCF_00632R_HANDOFF_20260625.md.
    "00631L.TW": {"1": 0.5731, "5": 0.6322, "20": 0.6807},
    "00632R.TW": {"1": 0.5915, "5": 0.6323, "20": 0.6959},
}


def _auc_weight_map(aucs: dict[str, float | None]) -> dict[str, float]:
    raw = {
        str(h): max(0.0, float(auc) - 0.5)
        for h, auc in aucs.items()
        if auc is not None
    }
    total = sum(raw.values())
    if total <= 0.0:
        keys = sorted(str(k) for k in aucs)
        return {k: 1.0 / len(keys) for k in keys} if keys else {}
    return {k: v / total for k, v in raw.items()}


def load_ncf_signal(path: Path) -> dict[str, Any]:
    """Load a single NCF JSON file and extract the key trading signals.

    Returns a dict with:
      ticker, date, direction, calibrated_prob_up, confidence, weighted_return,
      tail_reward_risk_score, prob_fwd_mdd_gt5_h20, prob_fwd_gain_gt5_h20
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    ensemble = payload["horizon_ensemble"]
    horizons = payload.get("horizons", {}) or {}
    horizon_prob_up = {
        str(h): float(block["classification"]["probability_up"])
        for h, block in horizons.items()
        if isinstance(block, dict)
        and isinstance(block.get("classification"), dict)
        and block["classification"].get("probability_up") is not None
    }
    horizon_val_auc = {
        str(h): float(block["classification"]["val_auc"])
        for h, block in horizons.items()
        if isinstance(block, dict)
        and isinstance(block.get("classification"), dict)
        and block["classification"].get("val_auc") is not None
    }

    fwd_mdd = payload.get("forward_drawdown_risk") or {}
    fwd_gain = payload.get("forward_upside_reward") or {}

    _gate = direction_magnitude_gate(
        probability_up=float(ensemble["calibrated_probability_up"]),
        predicted_return=float(ensemble["weighted_return"]),
    )
    return {
        "ticker": payload["ticker"],
        "date": payload["last_close_date"],
        "direction": ensemble["direction"],
        "calibrated_prob_up": float(ensemble["calibrated_probability_up"]),
        "confidence": float(ensemble["confidence"]),
        "weighted_return": float(ensemble["weighted_return"]),
        "votes_up": int(ensemble["votes_up"]),
        "raw_combined_prob_up": float(ensemble["combined_probability_up"]),
        "horizon_prob_up": horizon_prob_up,
        "horizon_val_auc": horizon_val_auc,
        "direction_weights": {
            str(k): float(v)
            for k, v in (ensemble.get("direction_weights") or {}).items()
        },
        "direction_magnitude_gate": _gate,
        # True when direction (from prob) and return_side (from weighted_return) contradict.
        # A conflicted signal should not contribute to the directional overlay.
        "direction_conflict": (
            _gate["return_side"] not in {"FLAT"} and _gate["return_side"] != _gate["direction"]
        ),
        # tail reward / risk fields (v5+ only; None when absent)
        "tail_reward_risk_score": (
            float(payload["tail_reward_risk_score"])
            if "tail_reward_risk_score" in payload
            else None
        ),
        "prob_fwd_mdd_gt5_h20": (
            float(fwd_mdd["probability"]) if fwd_mdd.get("available") else None
        ),
        "prob_fwd_gain_gt5_h20": (
            float(fwd_gain["probability"]) if fwd_gain.get("available") else None
        ),
    }


def ncf_dynamic_horizon_signal(
    ncf_signal: dict[str, Any],
    *,
    auc_priors: dict[str, dict[str, float]] | None = None,
    blend_live_auc: float = 0.35,
) -> dict[str, Any]:
    """Recompute one ticker's probability using multi-year OOS AUC priors.

    The daily NCF JSON already contains live validation AUC weights, but those
    can be dominated by the latest validation period. This function blends them
    with multi-year OOS priors so weak horizons, such as 00632R H1 in 2026, do
    not over-influence advisory signals.
    """
    ticker = str(ncf_signal.get("ticker", ""))
    probs = {str(k): float(v) for k, v in (ncf_signal.get("horizon_prob_up") or {}).items()}
    if not probs:
        prob = float(ncf_signal["calibrated_prob_up"])
        return {
            "probability_up": prob,
            "direction": "UP" if prob > 0.5 else "DOWN",
            "confidence": abs(prob - 0.5) * 2.0 * float(ncf_signal.get("confidence", 1.0)),
            "weights": {},
            "source": "ensemble_fallback",
        }

    auc_priors = auc_priors or DEFAULT_HORIZON_AUC_PRIORS
    prior_aucs = {
        h: auc_priors.get(ticker, {}).get(h)
        for h in probs
    }
    live_aucs = {
        h: (ncf_signal.get("horizon_val_auc") or {}).get(h)
        for h in probs
    }
    prior_w = _auc_weight_map(prior_aucs)
    live_w = _auc_weight_map(live_aucs)

    blend_live_auc = min(max(float(blend_live_auc), 0.0), 1.0)
    raw_w = {
        h: (1.0 - blend_live_auc) * prior_w.get(h, 0.0) + blend_live_auc * live_w.get(h, 0.0)
        for h in probs
    }
    total = sum(raw_w.values())
    weights = {h: (w / total if total > 0.0 else 1.0 / len(probs)) for h, w in raw_w.items()}
    prob_up = sum(weights[h] * probs[h] for h in probs)
    prob_up = float(min(max(prob_up, 0.0), 1.0))
    direction = "UP" if prob_up > 0.5 else "DOWN"
    confidence = abs(prob_up - 0.5) * 2.0 * float(ncf_signal.get("confidence", 1.0))

    return {
        "probability_up": round(prob_up, 4),
        "direction": direction,
        "confidence": round(float(min(max(confidence, 0.0), 1.0)), 4),
        "weights": {h: round(float(weights[h]), 4) for h in sorted(weights, key=int)},
        "prior_weights": {h: round(float(prior_w.get(h, 0.0)), 4) for h in sorted(probs, key=int)},
        "live_weights": {h: round(float(live_w.get(h, 0.0)), 4) for h in sorted(probs, key=int)},
        "source": "multi_year_auc_blend",
    }


def ncf_cross_ticker_consistency(
    ncf_00631l: dict[str, Any],
    ncf_00632r: dict[str, Any],
    *,
    use_dynamic_horizon: bool = True,
) -> dict[str, Any]:
    """Measure whether 00631L and 00632R imply the same market direction.

    Market-up evidence is 00631L up probability and 00632R down probability.
    Market-down evidence is 00631L down probability and 00632R up probability.
    A high agreement score means both tickers point in the same market direction;
    a low score flags conflicting NCF outputs and should reduce advisory weight.
    """
    if use_dynamic_horizon:
        l_sig = ncf_dynamic_horizon_signal(ncf_00631l)
        r_sig = ncf_dynamic_horizon_signal(ncf_00632r)
        l_prob = float(l_sig["probability_up"])
        r_prob = float(r_sig["probability_up"])
        l_conf = float(l_sig["confidence"])
        r_conf = float(r_sig["confidence"])
    else:
        l_prob = float(ncf_00631l["calibrated_prob_up"])
        r_prob = float(ncf_00632r["calibrated_prob_up"])
        l_conf = float(ncf_00631l.get("confidence", 1.0))
        r_conf = float(ncf_00632r.get("confidence", 1.0))

    market_up = 0.6 * l_prob + 0.4 * (1.0 - r_prob)
    market_down = 0.6 * (1.0 - l_prob) + 0.4 * r_prob
    market_prob_up = float(min(max(market_up, 0.0), 1.0))
    direction = "UP" if market_up >= market_down else "DOWN"

    l_side = "UP" if l_prob >= 0.5 else "DOWN"
    r_market_side = "DOWN" if r_prob >= 0.5 else "UP"
    agrees = l_side == r_market_side
    agreement_score = 1.0 - min(1.0, abs(l_prob - (1.0 - r_prob)) * 2.0)
    confidence = abs(market_prob_up - 0.5) * 2.0 * ((l_conf + r_conf) / 2.0)
    if not agrees:
        confidence *= 0.5

    return {
        "market_direction": direction,
        "market_probability_up": round(market_prob_up, 4),
        "agreement_score": round(float(min(max(agreement_score, 0.0), 1.0)), 4),
        "conflict_flag": not agrees,
        "confidence": round(float(min(max(confidence, 0.0), 1.0)), 4),
        "00631l_probability_up": round(l_prob, 4),
        "00632r_probability_up": round(r_prob, 4),
    }


def ncf_downside_signal(
    ncf_00631l: dict[str, Any],
    ncf_00632r: dict[str, Any],
    *,
    ma_gap: float | None = None,
    ma_gap_bull_threshold: float = 0.40,
    include_tail_risk: bool = True,
) -> float:
    """Compute composite downside signal in [0.0, 1.0].

    High value means both NCF models agree the market is heading down:
      00631L (bull) expected to fall  AND  00632R (inverse) expected to rise.

    Weights: 00631L 60%, 00632R 40% (direct model weighted higher).

    Args:
        ma_gap: Optional price / MA100 - 1 (e.g. 0.20 = 20% above MA100).
            When provided and above ma_gap_bull_threshold, the signal is
            suppressed. NOTE: NCF H20 AUC is HIGHER in late-bull (ma_gap>15%),
            so suppression at 0.15 was incorrect. Default raised to 0.40.
            Runners do not pass ma_gap, so live behavior is unaffected.
        ma_gap_bull_threshold: suppression starts here (default 0.40, effectively
            disabled for normal late-bull). Retained for backward compatibility.
    """
    l_prob = ncf_00631l["calibrated_prob_up"]
    l_conf = ncf_00631l["confidence"]
    # Zero out 00631L bearish contribution when direction/return conflict (prob says DOWN, return says UP)
    l_conflict = bool(ncf_00631l.get("direction_conflict", False))
    l_bear = 0.0 if l_conflict else max(0.0, (0.5 - l_prob)) * 2.0 * l_conf

    r_prob = ncf_00632r["calibrated_prob_up"]
    r_conf = ncf_00632r["confidence"]
    # Zero out 00632R bearish contribution when direction/return conflict (prob says UP, return says DOWN)
    r_conflict = bool(ncf_00632r.get("direction_conflict", False))
    r_bull = 0.0 if r_conflict else max(0.0, (r_prob - 0.5)) * 2.0 * r_conf

    directional = float(min(max(0.6 * l_bear + 0.4 * r_bull, 0.0), 1.0))
    raw = directional
    if include_tail_risk and ncf_has_tail_downside_inputs(ncf_00631l, ncf_00632r):
        tail = ncf_tail_downside_signal(ncf_00631l, ncf_00632r)
        raw = float(min(max(0.75 * directional + 0.25 * tail, 0.0), 1.0))

    if ma_gap is not None and ma_gap > ma_gap_bull_threshold:
        suppression = min(1.0, (ma_gap - ma_gap_bull_threshold) / ma_gap_bull_threshold)
        raw *= 1.0 - suppression

    return raw


def ncf_has_tail_downside_inputs(
    ncf_00631l: dict[str, Any],
    ncf_00632r: dict[str, Any],
) -> bool:
    return any(
        signal.get(key) is not None
        for signal, key in (
            (ncf_00631l, "prob_fwd_mdd_gt5_h20"),
            (ncf_00631l, "tail_reward_risk_score"),
            (ncf_00632r, "prob_fwd_gain_gt5_h20"),
            (ncf_00632r, "tail_reward_risk_score"),
        )
    )


def ncf_tail_downside_signal(
    ncf_00631l: dict[str, Any],
    ncf_00632r: dict[str, Any],
) -> float:
    """Compute auxiliary downside risk from NCF tail/drawdown heads.

    Directional probabilities remain the primary signal. This helper only
    contributes when v5+ NCF outputs expose forward drawdown/gain or tail
    reward-risk scores.
    """
    components: list[float] = []

    mdd_631l = ncf_00631l.get("prob_fwd_mdd_gt5_h20")
    if mdd_631l is not None:
        components.append(max(0.0, float(mdd_631l) - 0.5) * 2.0)

    gain_632r = ncf_00632r.get("prob_fwd_gain_gt5_h20")
    if gain_632r is not None:
        components.append(max(0.0, float(gain_632r) - 0.5) * 2.0)

    tail_631l = ncf_00631l.get("tail_reward_risk_score")
    if tail_631l is not None:
        components.append(max(0.0, -float(tail_631l)))

    tail_632r = ncf_00632r.get("tail_reward_risk_score")
    if tail_632r is not None:
        components.append(max(0.0, float(tail_632r)))

    if not components:
        return 0.0
    return float(min(max(sum(components) / len(components), 0.0), 1.0))


def ncf_upside_signal(
    ncf_00631l: dict[str, Any],
    ncf_00632r: dict[str, Any],
) -> float:
    """Compute composite upside signal in [0.0, 1.0].

    High value means both NCF models agree the market is heading up:
      00631L (bull) expected to rise  AND  00632R (inverse) expected to fall.
    """
    l_prob = ncf_00631l["calibrated_prob_up"]
    l_conf = ncf_00631l["confidence"]
    l_conflict = bool(ncf_00631l.get("direction_conflict", False))
    l_bull = 0.0 if l_conflict else max(0.0, (l_prob - 0.5)) * 2.0 * l_conf

    r_prob = ncf_00632r["calibrated_prob_up"]
    r_conf = ncf_00632r["confidence"]
    r_conflict = bool(ncf_00632r.get("direction_conflict", False))
    r_bear = 0.0 if r_conflict else max(0.0, (0.5 - r_prob)) * 2.0 * r_conf

    combined = 0.6 * l_bull + 0.4 * r_bear
    return float(min(max(combined, 0.0), 1.0))


def ncf_regime_gated_signal(
    ncf_00631l: dict[str, Any],
    ncf_00632r: dict[str, Any],
    *,
    ma_gap: float | None = None,
    ma_gap_bull_threshold: float = 0.40,
) -> dict[str, Any]:
    """Return regime-gated downside / upside with suppression metadata.

    Combines the raw NCF signals with a ma_gap bull-suppression filter.
    Use gated_downside_signal (not raw_downside_signal) when deciding
    whether to reduce 00631L in golden1.

    NOTE (2026-06-26): NCF H20 AUC is HIGHER in late-bull (ma_gap>15%),
    so the original 0.15 threshold was incorrect. Default raised to 0.40.

    Returns:
        raw_downside_signal:    unfiltered downside signal [0, 1]
        raw_upside_signal:      unfiltered upside signal [0, 1]
        gated_downside_signal:  downside after regime suppression [0, 1]
        ma_gap:                 passed-in ma_gap value (may be None)
        bull_suppression:       fraction suppressed due to strong bull trend [0, 1]
        bull_suppression_applied: True when any suppression occurred
        tail_score_631l:        tail_reward_risk_score from 00631L NCF (may be None)
        tail_score_632r:        tail_reward_risk_score from 00632R NCF (may be None)
    """
    directional_down = ncf_downside_signal(ncf_00631l, ncf_00632r, include_tail_risk=False)
    tail_down = ncf_tail_downside_signal(ncf_00631l, ncf_00632r)
    raw_down = ncf_downside_signal(ncf_00631l, ncf_00632r)
    raw_up = ncf_upside_signal(ncf_00631l, ncf_00632r)

    suppression = 0.0
    if ma_gap is not None and ma_gap > ma_gap_bull_threshold:
        suppression = min(1.0, (ma_gap - ma_gap_bull_threshold) / ma_gap_bull_threshold)

    gated_down = round(raw_down * (1.0 - suppression), 4)

    return {
        "raw_downside_signal": round(raw_down, 4),
        "directional_downside_signal": round(directional_down, 4),
        "tail_downside_signal": round(tail_down, 4),
        "raw_upside_signal": round(raw_up, 4),
        "gated_downside_signal": gated_down,
        "ma_gap": ma_gap,
        "bull_suppression": round(suppression, 4),
        "bull_suppression_applied": suppression > 0.0,
        "tail_score_631l": ncf_00631l.get("tail_reward_risk_score"),
        "tail_score_632r": ncf_00632r.get("tail_reward_risk_score"),
    }


def adjust_golden1_weights(
    base_weights: dict[str, float],
    downside_signal: float,
    max_reduction_fraction: float = 0.5,
) -> dict[str, float]:
    """Apply NCF downside overlay to golden1 weights.

    Reduces 00631L.TW allocation by up to `max_reduction_fraction` of its
    base weight when downside_signal = 1.0; freed budget moves to cash.
    0050.TW and bond ETFs are not modified — only the 2x leverage ETF is trimmed.

    Args:
        base_weights: e.g. {"0050.TW": 0.6, "00631L.TW": 0.2, "cash": 0.2}
        downside_signal: 0.0 = no change, 1.0 = max reduction
        max_reduction_fraction: how much of 00631L can be freed (default 50%)

    Returns:
        Adjusted weight dict (sum == 1.0 preserved).
    """
    weights = dict(base_weights)
    lever_key = "00631L.TW"
    if lever_key not in weights or weights[lever_key] <= 0.0:
        return weights

    base_lever = weights[lever_key]
    reduction = base_lever * max_reduction_fraction * downside_signal

    weights[lever_key] = base_lever - reduction
    weights["cash"] = weights.get("cash", 0.0) + reduction
    return weights


def ncf_overlay_summary(
    ncf_00631l: dict[str, Any],
    ncf_00632r: dict[str, Any],
    base_golden1_weights: dict[str, float],
    regime: str,
    *,
    ma_gap: float | None = None,
    ma_gap_bull_threshold: float = 0.40,
) -> dict[str, Any]:
    """Generate a human-readable overlay summary for logging / JSON output.

    Uses the regime-gated downside signal so that strong bull trends
    (ma_gap > ma_gap_bull_threshold) suppress the NCF downside overlay.

    Returns a dict suitable for embedding in the runner output under 'ncf_overlay'.
    """
    gated = ncf_regime_gated_signal(
        ncf_00631l,
        ncf_00632r,
        ma_gap=ma_gap,
        ma_gap_bull_threshold=ma_gap_bull_threshold,
    )
    down = gated["gated_downside_signal"]
    up = gated["raw_upside_signal"]
    dynamic_631l = ncf_dynamic_horizon_signal(ncf_00631l)
    dynamic_632r = ncf_dynamic_horizon_signal(ncf_00632r)
    cross_ticker = ncf_cross_ticker_consistency(ncf_00631l, ncf_00632r)

    if regime == "golden1":
        adjusted = adjust_golden1_weights(base_golden1_weights, down)
        reduction = base_golden1_weights.get("00631L.TW", 0.0) - adjusted.get("00631L.TW", 0.0)
        action = "reduce_00631l" if reduction > 0.0005 else "hold"
    else:
        adjusted = base_golden1_weights
        reduction = 0.0
        action = "n/a (defensive/recovery regime)"

    return {
        "date_00631l": ncf_00631l["date"],
        "date_00632r": ncf_00632r["date"],
        "ncf_00631l": {
            "direction": ncf_00631l["direction"],
            "calibrated_prob_up": ncf_00631l["calibrated_prob_up"],
            "confidence": ncf_00631l["confidence"],
            "votes_up": ncf_00631l["votes_up"],
            "tail_reward_risk_score": ncf_00631l.get("tail_reward_risk_score"),
            "prob_fwd_mdd_gt5_h20": ncf_00631l.get("prob_fwd_mdd_gt5_h20"),
            "prob_fwd_gain_gt5_h20": ncf_00631l.get("prob_fwd_gain_gt5_h20"),
            "direction_magnitude_gate": ncf_00631l.get("direction_magnitude_gate"),
            "direction_conflict": ncf_00631l.get("direction_conflict", False),
        },
        "ncf_00632r": {
            "direction": ncf_00632r["direction"],
            "calibrated_prob_up": ncf_00632r["calibrated_prob_up"],
            "confidence": ncf_00632r["confidence"],
            "votes_up": ncf_00632r["votes_up"],
            "tail_reward_risk_score": ncf_00632r.get("tail_reward_risk_score"),
            "prob_fwd_mdd_gt5_h20": ncf_00632r.get("prob_fwd_mdd_gt5_h20"),
            "prob_fwd_gain_gt5_h20": ncf_00632r.get("prob_fwd_gain_gt5_h20"),
            "direction_magnitude_gate": ncf_00632r.get("direction_magnitude_gate"),
            "direction_conflict": ncf_00632r.get("direction_conflict", False),
        },
        "composite_downside_signal": round(gated["raw_downside_signal"], 4),
        "directional_downside_signal": gated["directional_downside_signal"],
        "tail_downside_signal": gated["tail_downside_signal"],
        "gated_downside_signal": round(down, 4),
        "composite_upside_signal": round(up, 4),
        "dynamic_horizon_00631l": dynamic_631l,
        "dynamic_horizon_00632r": dynamic_632r,
        "cross_ticker_consistency": cross_ticker,
        "bull_suppression": gated["bull_suppression"],
        "bull_suppression_applied": gated["bull_suppression_applied"],
        "ma_gap": ma_gap,
        "current_regime": regime,
        "action": action,
        "base_golden1_weights": base_golden1_weights,
        "adjusted_golden1_weights": adjusted,
        "00631l_reduction": round(reduction, 4),
    }
