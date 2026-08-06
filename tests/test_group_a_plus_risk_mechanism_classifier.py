from __future__ import annotations

import json
import tempfile
from pathlib import Path

from group_a_plus.integrations.risk_mechanism_classifier import (
    DEFAULT_PERSISTENT_MIN_DAYS,
    append_risk_mechanism_shadow_log,
    classify_risk_mechanism,
    load_market_state_history_before,
)


def _market_state(bucket: str, state: str) -> dict:
    return {"state": state, "bucket": bucket, "risk_level": "medium"}


def _drawdown_history(n: int) -> list[dict]:
    return [
        {"date": f"2026-01-{i + 1:02d}", "bucket": "bear_breakdown", "state": "bear_breakdown"}
        for i in range(n)
    ]


def test_normal_when_bull_and_no_crash_alert() -> None:
    result = classify_risk_mechanism(_market_state("bull_trend", "bull_trend"), None, [])
    assert result["mechanism"] == "NORMAL"
    assert result["components"]["persistent_drawdown_days"] == 0


def test_fast_crash_from_market_state_alone_when_crash_alert_unavailable() -> None:
    result = classify_risk_mechanism(_market_state("crash_risk", "crash_risk"), None, [])
    assert result["mechanism"] == "FAST_CRASH"
    assert result["components"]["market_state_crash"] is True
    assert result["components"]["crash_alert_available"] is False


def test_fast_crash_from_crash_alert_even_if_market_state_is_not_crash_risk() -> None:
    crash_alert = {
        "status": "available",
        "alert_active": True,
        "category_score": 3,
        "category_flags": {"options_tail": True, "liquidity_forced_selling": True, "cross_market_shock": True},
    }
    result = classify_risk_mechanism(_market_state("choppy_range_high_risk", "choppy_range_high_risk"), crash_alert, [])
    assert result["mechanism"] == "FAST_CRASH"
    assert result["components"]["crash_alert_active"] is True
    assert result["components"]["crash_alert_category_score"] == 3


def test_drawdown_bucket_alone_stays_normal_until_persistence_threshold() -> None:
    short_history = _drawdown_history(DEFAULT_PERSISTENT_MIN_DAYS - 2)
    result = classify_risk_mechanism(
        _market_state("bear_breakdown", "bear_breakdown"), None, short_history
    )
    assert result["mechanism"] == "NORMAL"
    assert result["components"]["persistent_drawdown_confirmed"] is False
    assert result["components"]["persistent_drawdown_days"] == DEFAULT_PERSISTENT_MIN_DAYS - 1


def test_persistent_drawdown_once_threshold_met() -> None:
    long_history = _drawdown_history(DEFAULT_PERSISTENT_MIN_DAYS - 1)
    result = classify_risk_mechanism(
        _market_state("bear_breakdown", "bear_breakdown"), None, long_history
    )
    assert result["mechanism"] == "PERSISTENT_DRAWDOWN"
    assert result["components"]["persistent_drawdown_days"] == DEFAULT_PERSISTENT_MIN_DAYS
    assert result["components"]["persistent_drawdown_confirmed"] is True


def test_drawdown_streak_broken_by_a_non_drawdown_day_resets() -> None:
    history = _drawdown_history(DEFAULT_PERSISTENT_MIN_DAYS + 5)
    history.append({"date": "2026-02-01", "bucket": "bull_pullback_shallow", "state": "bull_pullback_shallow"})
    result = classify_risk_mechanism(
        _market_state("bear_breakdown", "bear_breakdown"), None, history
    )
    assert result["components"]["persistent_drawdown_days"] == 1
    assert result["mechanism"] == "NORMAL"


def test_fast_crash_wins_over_persistent_drawdown_on_the_same_day() -> None:
    """A crash occurring on top of an already-building drawdown streak must
    surface as FAST_CRASH (the acute event dominates response), but the
    drawdown context must still be visible in components/reasons for event
    attribution -- it is not silently dropped."""
    history = _drawdown_history(DEFAULT_PERSISTENT_MIN_DAYS + 2)
    result = classify_risk_mechanism(
        _market_state("crash_risk", "crash_risk"), None, history
    )
    assert result["mechanism"] == "FAST_CRASH"
    assert result["components"]["persistent_drawdown_days"] == 0
    assert result["components"]["prior_drawdown_streak_days"] >= DEFAULT_PERSISTENT_MIN_DAYS
    assert any("already-building" in reason and "drawdown streak" in reason for reason in result["reasons"])


def test_recovery_when_bucket_is_recovery_and_no_crash() -> None:
    result = classify_risk_mechanism(_market_state("recovery", "recovery_confirmed"), None, [])
    assert result["mechanism"] == "RECOVERY"


def test_crash_alert_unavailable_status_is_treated_as_unavailable_not_inactive() -> None:
    stale_alert = {"status": "unavailable", "alert_active": False}
    result = classify_risk_mechanism(_market_state("bull_trend", "bull_trend"), stale_alert, [])
    assert result["components"]["crash_alert_available"] is False
    assert result["mechanism"] == "NORMAL"


def test_append_risk_mechanism_shadow_log_is_idempotent_per_date() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        log_path = Path(tmp_dir) / "risk_mechanism_shadow_log.jsonl"
        day1 = classify_risk_mechanism(_market_state("crash_risk", "crash_risk"), None, [])
        day2 = classify_risk_mechanism(_market_state("bull_trend", "bull_trend"), None, [])
        day1_rerun = classify_risk_mechanism(_market_state("recovery", "recovery_early"), None, [])

        append_risk_mechanism_shadow_log(log_path, day1, date="2026-07-01")
        append_risk_mechanism_shadow_log(log_path, day2, date="2026-07-02")
        append_risk_mechanism_shadow_log(log_path, day1_rerun, date="2026-07-01")

        lines = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    assert len(lines) == 2
    by_date = {row["date"]: row for row in lines}
    assert by_date["2026-07-01"]["mechanism"] == "RECOVERY"
    assert by_date["2026-07-02"]["mechanism"] == "NORMAL"


def test_load_market_state_history_before_filters_and_sorts() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        log_path = Path(tmp_dir) / "market_state_shadow_log.jsonl"
        rows = [
            {"date": "2026-07-03", "bucket": "bear_breakdown"},
            {"date": "2026-07-01", "bucket": "bull_trend"},
            {"date": "2026-07-02", "bucket": "bear_breakdown"},
        ]
        log_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

        history = load_market_state_history_before(log_path, "2026-07-03")

    assert [row["date"] for row in history] == ["2026-07-01", "2026-07-02"]
