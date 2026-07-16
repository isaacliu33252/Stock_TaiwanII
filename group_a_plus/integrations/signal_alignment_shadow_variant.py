"""Shadow-only signal_alignment variant that adds three new-generation sources.

Fable audit (2026-07-16, combination opportunities #8): signal_alignment.py's
9 production sources have never included trough_nowcast, compounding_regime,
or crash_risk_alert, even though group_a_plus.operations.daily_signal already
computes all three every day (trough_nowcast is embedded directly in
live_signal.json; compounding_regime and crash_risk_alert are separate daily
artifacts). This module appends them as three additional votes via
build_signal_alignment's `extra_sources` hook and reuses its exact
weighted_share/alignment/leverage_suitability computation, so the comparison
is apples-to-apples with the production alignment -- not a different metric.

Shadow-only: this never changes the production
report/group_a_plus/latest/signal_alignment.json, target weights, or
execution guards. It exists so the daily shadow log
(signal_alignment_shadow_variant_log.jsonl) can accumulate real forward-OOS
samples; there is not yet enough history to say whether adding these sources
actually improves anything (see scripts/evaluate/build_group_a_plus_shadow_log_unified_join.py).
"""

from __future__ import annotations

from typing import Any

from group_a_plus.integrations.leveraged_compounding_regime import MEAN_REVERTING, TRANSITIONAL, TREND_PERSISTENT
from group_a_plus.integrations.signal_alignment import _as_float, _source, build_signal_alignment
from group_a_plus.integrations.trough_nowcast import TROUGH_STATES


def _trough_nowcast_source(trough_nowcast: dict[str, Any] | None) -> dict[str, Any]:
    trough_nowcast = trough_nowcast or {}
    state = str(trough_nowcast.get("state") or "NO_TROUGH")
    if state not in TROUGH_STATES or state == "NO_TROUGH":
        return _source(
            "trough_nowcast",
            "neutral",
            0.0,
            f"trough_nowcast state={state} (no active crash/re-entry context)",
            available=False,
        )
    reentry_score = int(_as_float(trough_nowcast.get("reentry_confirmation_score"), 0.0))
    capitulation_score = int(_as_float(trough_nowcast.get("capitulation_score"), 0.0))
    if state == "CAPITULATION_WARNING":
        # Crash context active but re-entry not yet confirmed -- still bearish.
        strength = min(0.3 + 0.1 * capitulation_score, 1.0)
        return _source("trough_nowcast", "bearish", strength, f"trough_nowcast state={state}, capitulation_score={capitulation_score}")
    # PARTIAL_REENTRY / FULL_REENTRY.
    strength = min(0.3 + 0.1 * reentry_score, 1.0)
    return _source("trough_nowcast", "bullish", strength, f"trough_nowcast state={state}, reentry_confirmation_score={reentry_score}")


def _compounding_regime_source(compounding_regime_latest: dict[str, Any] | None) -> dict[str, Any]:
    latest = compounding_regime_latest or {}
    regime = str(latest.get("compounding_regime") or "")
    if regime not in {TREND_PERSISTENT, MEAN_REVERTING, TRANSITIONAL}:
        return _source("compounding_regime", "neutral", 0.0, "compounding_regime unavailable", available=False)
    trend_score = int(_as_float(latest.get("trend_score"), 0.0))
    mean_reversion_score = int(_as_float(latest.get("mean_reversion_score"), 0.0))
    if regime == TREND_PERSISTENT:
        strength = min(0.3 + 0.1 * trend_score, 1.0)
        return _source("compounding_regime", "bullish", strength, f"compounding_regime={regime}, trend_score={trend_score}")
    if regime == MEAN_REVERTING:
        strength = min(0.3 + 0.1 * mean_reversion_score, 1.0)
        return _source("compounding_regime", "bearish", strength, f"compounding_regime={regime}, mean_reversion_score={mean_reversion_score}")
    return _source("compounding_regime", "neutral", 0.15, f"compounding_regime={regime}")


def _crash_risk_alert_source(crash_risk_alert: dict[str, Any] | None) -> dict[str, Any]:
    crash_risk_alert = crash_risk_alert or {}
    if crash_risk_alert.get("status") != "available":
        return _source("crash_risk_alert", "neutral", 0.0, "crash_risk_alert unavailable", available=False)
    score = int(_as_float(crash_risk_alert.get("category_score"), 0.0))
    if score <= 0:
        return _source("crash_risk_alert", "neutral", 0.0, "crash_risk_alert category_score=0")
    return _source(
        "crash_risk_alert",
        "bearish",
        score / 3.0,
        f"crash_risk_alert category_score={score}/3, watch_level={crash_risk_alert.get('watch_level')}",
    )


def build_signal_alignment_shadow_variant(
    live_signal: dict[str, Any],
    *,
    trough_nowcast: dict[str, Any] | None = None,
    compounding_regime_latest: dict[str, Any] | None = None,
    crash_risk_alert: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Shadow-only: same aggregation as build_signal_alignment plus 3 new sources.

    `trough_nowcast` defaults to live_signal["trough_nowcast"] when not passed
    explicitly, since daily_signal.py already embeds it there.
    """
    if trough_nowcast is None:
        trough_nowcast = live_signal.get("trough_nowcast")
    extra_sources = [
        _trough_nowcast_source(trough_nowcast),
        _compounding_regime_source(compounding_regime_latest),
        _crash_risk_alert_source(crash_risk_alert),
    ]
    result = build_signal_alignment(live_signal, extra_sources=extra_sources)
    result["variant"] = "shadow_plus_trough_compounding_crash_alert"
    result["research_only"] = True
    result["production_effect"] = "none"
    return result
