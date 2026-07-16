from __future__ import annotations

import json
from pathlib import Path

from scripts.run.build_a2118_dfl_shadow_ensemble_log import (
    append_ensemble_log,
    build_ensemble_snapshot,
    ensemble_level,
)


def _signal(action: str, active: bool) -> dict:
    return {"action": action, "active": active}


def test_ensemble_level_classifies_shadow_states() -> None:
    assert ensemble_level(_signal("KEEP", False), _signal("KEEP", False), _signal("KEEP", False)) == "none"
    assert ensemble_level(_signal("CAP10", True), _signal("KEEP", False), _signal("KEEP", False)) == "watch"
    assert ensemble_level(_signal("KEEP", False), _signal("KEEP", False), _signal("CAP10", True)) == "watch"
    assert ensemble_level(_signal("KEEP", False), _signal("CAP10", True), _signal("CAP10", True)) == "strong_watch"
    assert ensemble_level(_signal("KEEP", False), _signal("NO_ADD", True), _signal("CAP10", True)) == "conflict"


def test_build_ensemble_snapshot_extracts_base_and_selective_variants() -> None:
    payload = {
        "status": "available",
        "as_of": "2026-01-05",
        "action": "KEEP",
        "advisory_active": False,
        "selected_decision": {"predicted_regret": 0.0},
        "selective_variants": {
            "p50": {
                "action": "KEEP",
                "advisory_active": False,
                "selected_decision": {"reliability_error_percentile": None},
            },
            "p70": {
                "action": "CAP10",
                "advisory_active": True,
                "recommended_action": "manual_review_consider_shadow_action",
                "selected_decision": {
                    "predicted_regret": 0.001,
                    "reliability_error_percentile": 0.42,
                    "reliability_gate_pass": True,
                },
            },
        },
    }

    snapshot = build_ensemble_snapshot(payload)

    assert snapshot["ensemble_level"] == "watch"
    assert snapshot["manual_review_required"] is True
    assert snapshot["signals"]["p70"]["reliability_error_percentile"] == 0.42
    assert snapshot["active_allocation_impact"] == "none"


def test_append_ensemble_log_replaces_same_as_of(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    append_ensemble_log({"as_of": "2026-01-05", "ensemble_level": "watch"}, log)
    append_ensemble_log({"as_of": "2026-01-04", "ensemble_level": "none"}, log)
    append_ensemble_log({"as_of": "2026-01-05", "ensemble_level": "strong_watch"}, log)

    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]

    assert [row["as_of"] for row in rows] == ["2026-01-04", "2026-01-05"]
    assert rows[-1]["ensemble_level"] == "strong_watch"
