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


def load_ncf_signal(path: Path) -> dict[str, Any]:
    """Load a single NCF JSON file and extract the key trading signals.

    Returns a dict with:
      ticker, date, direction, calibrated_prob_up, confidence, weighted_return,
      tail_reward_risk_score, prob_fwd_mdd_gt5_h20, prob_fwd_gain_gt5_h20
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    ensemble = payload["horizon_ensemble"]

    fwd_mdd = payload.get("forward_drawdown_risk") or {}
    fwd_gain = payload.get("forward_upside_reward") or {}

    return {
        "ticker": payload["ticker"],
        "date": payload["last_close_date"],
        "direction": ensemble["direction"],
        "calibrated_prob_up": float(ensemble["calibrated_probability_up"]),
        "confidence": float(ensemble["confidence"]),
        "weighted_return": float(ensemble["weighted_return"]),
        "votes_up": int(ensemble["votes_up"]),
        "raw_combined_prob_up": float(ensemble["combined_probability_up"]),
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


def ncf_downside_signal(
    ncf_00631l: dict[str, Any],
    ncf_00632r: dict[str, Any],
    *,
    ma_gap: float | None = None,
    ma_gap_bull_threshold: float = 0.40,
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
    l_bear = max(0.0, (0.5 - l_prob)) * 2.0 * l_conf

    r_prob = ncf_00632r["calibrated_prob_up"]
    r_conf = ncf_00632r["confidence"]
    r_bull = max(0.0, (r_prob - 0.5)) * 2.0 * r_conf

    raw = float(min(max(0.6 * l_bear + 0.4 * r_bull, 0.0), 1.0))

    if ma_gap is not None and ma_gap > ma_gap_bull_threshold:
        suppression = min(1.0, (ma_gap - ma_gap_bull_threshold) / ma_gap_bull_threshold)
        raw *= 1.0 - suppression

    return raw


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
    l_bull = max(0.0, (l_prob - 0.5)) * 2.0 * l_conf

    r_prob = ncf_00632r["calibrated_prob_up"]
    r_conf = ncf_00632r["confidence"]
    r_bear = max(0.0, (0.5 - r_prob)) * 2.0 * r_conf

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
    raw_down = ncf_downside_signal(ncf_00631l, ncf_00632r)
    raw_up = ncf_upside_signal(ncf_00631l, ncf_00632r)

    suppression = 0.0
    if ma_gap is not None and ma_gap > ma_gap_bull_threshold:
        suppression = min(1.0, (ma_gap - ma_gap_bull_threshold) / ma_gap_bull_threshold)

    gated_down = round(raw_down * (1.0 - suppression), 4)

    return {
        "raw_downside_signal": round(raw_down, 4),
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

    if regime == "golden1":
        adjusted = adjust_golden1_weights(base_golden1_weights, down)
        action = "reduce_00631l" if down > 0.2 else "hold"
    else:
        adjusted = base_golden1_weights
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
        },
        "ncf_00632r": {
            "direction": ncf_00632r["direction"],
            "calibrated_prob_up": ncf_00632r["calibrated_prob_up"],
            "confidence": ncf_00632r["confidence"],
            "votes_up": ncf_00632r["votes_up"],
            "tail_reward_risk_score": ncf_00632r.get("tail_reward_risk_score"),
            "prob_fwd_mdd_gt5_h20": ncf_00632r.get("prob_fwd_mdd_gt5_h20"),
            "prob_fwd_gain_gt5_h20": ncf_00632r.get("prob_fwd_gain_gt5_h20"),
        },
        "composite_downside_signal": round(gated["raw_downside_signal"], 4),
        "gated_downside_signal": round(down, 4),
        "composite_upside_signal": round(up, 4),
        "bull_suppression": gated["bull_suppression"],
        "bull_suppression_applied": gated["bull_suppression_applied"],
        "ma_gap": ma_gap,
        "current_regime": regime,
        "action": action,
        "base_golden1_weights": base_golden1_weights,
        "adjusted_golden1_weights": adjusted,
        "00631l_reduction": round(
            base_golden1_weights.get("00631L.TW", 0.0) - adjusted.get("00631L.TW", 0.0), 4
        ),
    }
