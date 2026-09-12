from __future__ import annotations

from group_a_plus.integrations.moira_execution_guard_backtest import build_execution_guard_hard_stop_backtest


def _record(date: str, *, allowed: bool, close_0050: float, close_631l: float, close_632r: float, weights: dict):
    return {
        "date": date,
        "path": f"{date}.json",
        "signal": {
            "actual_data_date": date,
            "execution_allowed": allowed,
            "latest_prices": {"0050.TW": close_0050, "00631L.TW": close_631l, "00632R.TW": close_632r, "00679B.TWO": 25.0},
            "target_weights": weights,
        },
    }


def test_execution_guard_backtest_caps_new_risk_when_guard_false() -> None:
    records = [
        _record(
            "2026-08-01",
            allowed=True,
            close_0050=100.0,
            close_631l=30.0,
            close_632r=10.0,
            weights={"0050.TW": 0.5, "00631L.TW": 0.0, "00632R.TW": 0.0, "cash": 0.5},
        ),
        _record(
            "2026-08-02",
            allowed=False,
            close_0050=101.0,
            close_631l=31.0,
            close_632r=9.9,
            weights={"0050.TW": 0.3, "00631L.TW": 0.2, "00632R.TW": 0.2, "cash": 0.3},
        ),
        _record(
            "2026-08-03",
            allowed=True,
            close_0050=100.0,
            close_631l=29.0,
            close_632r=10.2,
            weights={"0050.TW": 0.3, "00631L.TW": 0.0, "00632R.TW": 0.0, "cash": 0.7},
        ),
    ]

    report = build_execution_guard_hard_stop_backtest(signal_records=records, as_of="2026-08-03", min_trigger_count=1)

    assert report["schema_version"] == 2
    assert report["input_coverage"]["general_trigger_count"] == 1
    assert report["input_coverage"]["strict_actionable_trigger_count"] == 1
    assert report["input_coverage"]["trigger_count"] == 1
    assert report["trigger_taxonomy"]["general_trigger_count"] == 1
    assert report["trigger_taxonomy"]["strict_actionable_trigger_count"] == 1
    row = report["trigger_rows"][0]
    assert row["date"] == "2026-08-02"
    assert row["actions"] == ["cap_new_00631L.TW", "cap_new_00632R.TW"]
    assert row["guarded_weights"]["00631L.TW"] == 0.0
    assert row["guarded_weights"]["00632R.TW"] == 0.0
    assert report["summary"]["ready_for_manual_review"] is True
    assert report["promotion_checklist"]["checks"]["manual_review_min_strict_triggers_20"] is False
    assert report["promotion_checklist"]["checks"]["signed_approval_present"] is False
    assert report["promotion_checklist"]["manual_review_allowed"] is False
    assert report["promotion_checklist"]["guarded_candidate_allowed"] is False
    assert report["summary"]["promotion_checklist_manual_review_allowed"] is False
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["decision"]["guarded_candidate_allowed"] is False


def test_execution_guard_backtest_reports_insufficient_trigger_history() -> None:
    records = [
        _record(
            "2026-08-01",
            allowed=True,
            close_0050=100.0,
            close_631l=30.0,
            close_632r=10.0,
            weights={"0050.TW": 0.5, "cash": 0.5},
        ),
        _record(
            "2026-08-02",
            allowed=True,
            close_0050=101.0,
            close_631l=31.0,
            close_632r=9.9,
            weights={"0050.TW": 0.5, "cash": 0.5},
        ),
    ]

    report = build_execution_guard_hard_stop_backtest(signal_records=records, min_trigger_count=1)

    assert report["input_coverage"]["general_trigger_count"] == 0
    assert report["input_coverage"]["strict_actionable_trigger_count"] == 0
    assert report["input_coverage"]["trigger_count"] == 0
    assert report["summary"]["recommendation"] == "needs_more_trigger_history"
    assert report["decision"]["creates_orders"] is False


def test_execution_guard_backtest_separates_general_from_strict_trigger() -> None:
    records = [
        _record(
            "2026-08-01",
            allowed=True,
            close_0050=100.0,
            close_631l=30.0,
            close_632r=10.0,
            weights={"0050.TW": 0.5, "00631L.TW": 0.2, "cash": 0.3},
        ),
        _record(
            "2026-08-02",
            allowed=False,
            close_0050=101.0,
            close_631l=31.0,
            close_632r=9.9,
            weights={"0050.TW": 0.5, "00631L.TW": 0.1, "cash": 0.4},
        ),
        _record(
            "2026-08-03",
            allowed=True,
            close_0050=102.0,
            close_631l=32.0,
            close_632r=9.8,
            weights={"0050.TW": 0.5, "cash": 0.5},
        ),
    ]

    report = build_execution_guard_hard_stop_backtest(signal_records=records, min_trigger_count=1)

    assert report["input_coverage"]["general_trigger_count"] == 1
    assert report["input_coverage"]["strict_actionable_trigger_count"] == 0
    assert report["trigger_taxonomy"]["general_trigger_rows"][0]["strict_actionable"] is False
    assert report["summary"]["ready_for_manual_review"] is False
