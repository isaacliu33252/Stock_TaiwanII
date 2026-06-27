from __future__ import annotations

import pandas as pd

from run_group_a_shareholding_shadow import _ticker_snapshot, assess_shadow_signal, build_shadow_report


CONFIG = {
    "branch_name": "group_a_shareholding_shadow_v1",
    "status": "research_only",
    "production_release_unchanged": "Golden1_0531",
    "leverage_ticker": "00631L",
    "availability_lag_days": 1,
    "caution": {
        "leverage_minority_percent_change": 4.0,
        "leverage_total_people_change_ratio": 0.35,
    },
    "risk_off": {
        "leverage_minority_percent_change": 6.0,
        "leverage_total_people_change_ratio": 0.5,
    },
}


def test_ticker_snapshot_uses_requested_lookback() -> None:
    features = pd.DataFrame(
        {
            "dt": pd.to_datetime(["2026-04-03", "2026-04-10", "2026-04-17"]),
            "minority_percent": [10.0, 12.0, 17.0],
            "major_percent": [40.0, 39.0, 35.0],
            "total_people": [100_000, 120_000, 170_000],
        }
    )
    snapshot = _ticker_snapshot(features, 2)
    assert snapshot["minority_percent_change"] == 7.0
    assert snapshot["major_percent_change"] == -5.0
    assert snapshot["total_people_change_ratio"] == 0.7


def test_assessment_marks_leverage_etf_crowding_risk_off() -> None:
    assessment = assess_shadow_signal(
        CONFIG,
        {"00631L": {"available": True, "minority_percent_change": 6.1, "total_people_change_ratio": 0.51}},
    )
    assert assessment["state"] == "risk_off"


def test_report_is_advisory_only_and_does_not_publish_targets() -> None:
    report = build_shadow_report(
        CONFIG,
        {"00631L": {"available": True, "minority_percent_change": 0.0, "total_people_change_ratio": 0.0}},
        requested_as_of_date="2026-06-01",
        cutoff_date="2026-05-31",
    )
    assert report["advisory_only"] is True
    assert report["changes_production_target_shares"] is False
    assert "target_shares" not in report
