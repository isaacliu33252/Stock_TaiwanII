from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_00632r_tail_tracking_error_gate_review import (
    build_review,
    write_review,
)


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _letf(path: Path) -> Path:
    return _write(
        path,
        {
            "decision": {"allow_00632r_open": False},
            "parameter_threshold_review": {
                "checks": {
                    "00632r_30d_p05_tracking_error_floor": {
                        "value": -0.0419,
                        "threshold": -0.03,
                        "passed": False,
                    }
                }
            },
            "tracking_error_summary": {
                "00632R.TW": {
                    "horizon_metrics": {
                        "30": {
                            "tracking_error": {
                                "count": 1000,
                                "mean": 0.02,
                                "p05": -0.0419,
                                "p50": -0.004,
                                "p95": 0.03,
                                "latest": 0.008,
                            },
                            "effective_drag_proxy": {"p05": -0.035, "latest": 0.022},
                            "realized_variance": {"latest": 0.014},
                            "recent_60_observations": {
                                "mean_tracking_error": 0.002,
                                "p05_tracking_error": -0.0108,
                                "mean_effective_drag_proxy": 0.015,
                            },
                        }
                    }
                }
            },
        },
    )


def _manual(path: Path) -> Path:
    return _write(
        path,
        {
            "decision": {
                "manual_hedge_discussion_allowed": False,
                "allow_00632r_open": False,
            }
        },
    )


def test_review_recommends_split_when_recent_tail_passes_but_full_sample_fails(tmp_path: Path) -> None:
    review = build_review(
        letf_tracking_path=_letf(tmp_path / "letf.json"),
        manual_hedge_path=_manual(tmp_path / "manual.json"),
        as_of="2026-07-20",
    )

    assert review["report_type"] == "group_a_plus_00632r_tail_tracking_error_gate_review"
    assert review["status"] == "blocked"
    assert review["assessment"]["full_sample_tail_gate_passed"] is False
    assert review["assessment"]["manual_recent_tail_gate_passed"] is True
    assert review["assessment"]["gate_split_recommended"] is True
    assert "full_sample_00632r_tail_tracking_error_gate_failed" in review["blocking_reasons"]
    assert "manual_hedge_eligibility_still_blocked" in review["blocking_reasons"]
    assert review["decision"]["gate_split_recommended"] is True
    assert review["decision"]["manual_discussion_tail_gate_passed"] is True
    assert review["decision"]["manual_hedge_discussion_allowed"] is False
    assert review["decision"]["allow_00632r_open"] is False
    assert review["decision"]["target_weight_change_allowed"] is False


def test_review_blocks_when_recent_tail_also_fails(tmp_path: Path) -> None:
    letf = json.loads(_letf(tmp_path / "letf.json").read_text(encoding="utf-8"))
    letf["tracking_error_summary"]["00632R.TW"]["horizon_metrics"]["30"]["recent_60_observations"][
        "p05_tracking_error"
    ] = -0.025
    letf_path = _write(tmp_path / "letf_recent_fail.json", letf)

    review = build_review(
        letf_tracking_path=letf_path,
        manual_hedge_path=_manual(tmp_path / "manual.json"),
        as_of="2026-07-20",
    )

    assert review["assessment"]["manual_recent_tail_gate_passed"] is False
    assert review["assessment"]["gate_split_recommended"] is False
    assert "recent_manual_tail_tracking_error_gate_failed" in review["blocking_reasons"]


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "tail.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_00632r_tail_tracking_error_gate_review",
        "as_of": "2026-07-20",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "00632r_tail_tracking_error_gate_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
