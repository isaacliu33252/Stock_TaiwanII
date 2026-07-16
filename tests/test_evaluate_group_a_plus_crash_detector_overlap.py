from __future__ import annotations

import pandas as pd

from scripts.evaluate.evaluate_group_a_plus_crash_detector_overlap import (
    ALERT_ONLY_DETECTORS,
    BLOCKING_DETECTORS,
    _jaccard,
    build_overlap_report,
)


def _synthetic_detectors() -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=10, freq="B")
    # Day 0-1: volatility_gate active (blocking).
    # Day 2-3: crash_risk_alert_2of3 active alone (no blocking guard) -> unique coverage.
    # Day 4: both volatility_gate and crash_risk_alert_2of3 active.
    # Day 5-9: nothing active.
    volatility_gate = pd.Series(False, index=idx)
    volatility_gate.iloc[[0, 1, 4]] = True
    extreme_warning_proxy = pd.Series(False, index=idx)
    compounding_mean_reverting = pd.Series(False, index=idx)
    crash_risk_alert_2of3 = pd.Series(False, index=idx)
    crash_risk_alert_2of3.iloc[[2, 3, 4]] = True
    market_state_crash_like = pd.Series(False, index=idx)
    specialist_router_crash_deleverage = pd.Series(False, index=idx)

    return pd.DataFrame(
        {
            "volatility_gate": volatility_gate,
            "extreme_warning_proxy": extreme_warning_proxy,
            "compounding_mean_reverting": compounding_mean_reverting,
            "crash_risk_alert_2of3": crash_risk_alert_2of3,
            "market_state_crash_like": market_state_crash_like,
            "specialist_router_crash_deleverage": specialist_router_crash_deleverage,
        },
        index=idx,
    )


def test_jaccard_handles_no_active_days() -> None:
    idx = pd.date_range("2026-01-01", periods=3, freq="B")
    empty = pd.Series(False, index=idx)

    assert _jaccard(empty, empty) is None


def test_jaccard_matches_expected_ratio() -> None:
    idx = pd.date_range("2026-01-01", periods=4, freq="B")
    a = pd.Series([True, True, False, False], index=idx)
    b = pd.Series([True, False, True, False], index=idx)

    # union={0,1,2}=3, intersection={0}=1 -> 1/3
    assert _jaccard(a, b) == 1.0 / 3.0


def test_build_overlap_report_active_days_and_unique_coverage() -> None:
    detectors = _synthetic_detectors()
    report = build_overlap_report(detectors)

    assert report["active_days"]["volatility_gate"] == 3
    assert report["active_days"]["crash_risk_alert_2of3"] == 3
    assert report["any_blocking_guard_active_days"] == 3

    coverage = report["alert_only_unique_coverage"]["crash_risk_alert_2of3"]
    assert coverage["active_days"] == 3
    # Days 2,3 have no blocking guard active; day 4 does (volatility_gate).
    assert coverage["days_active_while_no_blocking_guard_active"] == 2


def test_build_overlap_report_pairwise_entries_exist_for_all_pairs() -> None:
    detectors = _synthetic_detectors()
    report = build_overlap_report(detectors)

    names = list(BLOCKING_DETECTORS) + list(ALERT_ONLY_DETECTORS)
    expected_pairs = len(names) * (len(names) - 1) // 2
    assert len(report["pairwise_overlap"]) == expected_pairs

    entry = report["pairwise_overlap"]["volatility_gate__vs__crash_risk_alert_2of3"]
    assert entry["both_active_days"] == 1
    assert entry["only_a_days"] == 2
    assert entry["only_b_days"] == 2
