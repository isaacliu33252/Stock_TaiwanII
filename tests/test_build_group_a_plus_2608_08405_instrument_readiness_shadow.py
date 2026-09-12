from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate import build_group_a_plus_2608_08405_instrument_readiness_shadow as module


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_instrument_readiness_blocks_without_first_stage_or_event_panel(tmp_path: Path) -> None:
    lending = tmp_path / "lending.json"
    assigned = tmp_path / "assigned.json"
    _write_json(
        lending,
        {
            "as_of": "2026-09-04",
            "status": "db_snapshot_only",
            "summary": {
                "latest_available_dt": "2026-09-01",
                "db_lagged_after_query": True,
            },
        },
    )
    _write_json(assigned, {"status": "blocked"})

    report = module.build_report(
        securities_lending_status_path=lending,
        assigned_realized_path=assigned,
        index_event_panel_path=None,
        exclusion_protocol_path=None,
    )

    assert report["status"] == "blocked_shadow_only"
    assert report["decision"]["instrument_promotable"] is False
    assert report["decision"]["latest_strategy_change_allowed"] is False
    assert "securities_lending_source_stale_or_missing_for_instrument" in report["blocking_reasons"]
    assert "index_reconstitution_event_panel_missing" in report["blocking_reasons"]
    assert "first_stage_not_reported" in report["blocking_reasons"]
    assert "exclusion_restriction_not_documented" in report["blocking_reasons"]
    assert report["checks"]["realized_deployment_logged"] is False


def test_instrument_readiness_stays_shadow_even_with_candidate_inputs(tmp_path: Path) -> None:
    lending = tmp_path / "lending.json"
    assigned = tmp_path / "assigned.json"
    events = tmp_path / "events.json"
    protocol = tmp_path / "protocol.json"
    _write_json(
        lending,
        {
            "as_of": "2026-09-04",
            "status": "available",
            "summary": {"latest_available_dt": "2026-09-04", "db_lagged_after_query": False},
            "first_stage": {"f_stat": 15.0},
        },
    )
    _write_json(assigned, {"status": "ready_for_capacity_shadow_review"})
    _write_json(events, {"events": [{"date": "2026-06-30", "ticker": "0050.TW"}]})
    _write_json(protocol, {"pre_registered_exclusion_restriction": True})

    report = module.build_report(
        securities_lending_status_path=lending,
        assigned_realized_path=assigned,
        index_event_panel_path=events,
        exclusion_protocol_path=protocol,
    )
    markdown = module._markdown(report)

    assert report["checks"]["first_stage_reported"] is True
    assert report["checks"]["exclusion_restriction_pre_registered"] is True
    assert report["checks"]["index_event_panel_available"] is True
    assert report["decision"]["capacity_claim_allowed"] is False
    assert report["blocking_reasons"] == ["natural_experiment_not_promotable_without_manual_causal_review"]
    assert "## Candidates" in markdown
