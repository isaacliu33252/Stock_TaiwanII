from scripts.evaluate.build_group_a_plusplus_2609_04917_staged_reentry_confirmatory_tracker import build_tracker


def _spec() -> dict:
    return {
        "candidate": {"name": "staged_reentry"},
        "confirmatory_window_rule": {
            "start_after": "2026-09-09",
            "minimum_active_events": 2,
            "required_forward_horizons": ["5d", "10d"],
            "minimum_resolved_rows_per_horizon": 2,
            "minimum_positive_rate_per_horizon": 0.5,
            "minimum_mean_edge_per_horizon": 0.0,
            "maximum_worst_edge_per_horizon": -0.01,
        },
    }


def test_tracker_excludes_pre_freeze_events_from_confirmatory_counts() -> None:
    event_study = {
        "events": [
            {"actual_data_date": "2026-08-24", "forward": {"edge_5d": 0.01, "edge_10d": 0.01}},
            {"actual_data_date": "2026-09-10", "forward": {"edge_5d": 0.01, "edge_10d": 0.01}},
        ]
    }

    report = build_tracker(spec=_spec(), event_study=event_study)

    assert report["pre_freeze_event_count"] == 1
    assert report["confirmatory_event_count"] == 1
    assert report["confirmatory_events_missing"] == 1
    assert report["horizon_progress"]["5d"]["resolved_rows"] == 1
    assert report["status"] == "collecting_confirmatory_evidence"


def test_tracker_passes_only_after_post_freeze_horizons_clear() -> None:
    event_study = {
        "events": [
            {"actual_data_date": "2026-09-10", "forward": {"edge_5d": 0.01, "edge_10d": 0.02}},
            {"actual_data_date": "2026-09-11", "forward": {"edge_5d": 0.00, "edge_10d": 0.01}},
        ]
    }

    report = build_tracker(spec=_spec(), event_study=event_study)

    assert report["status"] == "confirmatory_passed_for_human_review"
    assert report["decision"]["promotion_allowed"] is False
    assert report["horizon_progress"]["10d"]["passed"] is True


def test_tracker_blocks_missing_inputs() -> None:
    report = build_tracker(spec={}, event_study={})

    assert report["status"] == "collecting_confirmatory_evidence"
    assert "missing_frozen_confirmatory_spec" in report["blocking_reasons"]
    assert "missing_staged_reentry_event_study" in report["blocking_reasons"]
