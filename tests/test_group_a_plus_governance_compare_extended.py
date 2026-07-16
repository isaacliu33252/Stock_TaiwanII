from __future__ import annotations

import json
from pathlib import Path

from group_a_plus.governance.compare import compare_candidates


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_compare_candidates_reads_embedded_baseline_metrics_and_summary_bests(tmp_path: Path) -> None:
    baseline = _write_json(
        tmp_path / "baseline.json",
        {"baseline": {"metrics": {"final_value": 100.0, "sharpe_ratio": 1.0, "max_drawdown": -0.20}}},
    )
    candidate = _write_json(
        tmp_path / "candidate.json",
        {
            "experiment": "summary_candidate",
            "summary": {
                "best_by_sharpe": {
                    "metrics": {
                        "final_value": 101.0,
                        "sharpe_ratio": 1.1,
                        "sortino_ratio": 1.2,
                        "max_drawdown": -0.19,
                    },
                    "trigger_days": 2,
                }
            },
        },
    )

    report = compare_candidates(baseline, [candidate])

    assert report["candidate_row_count"] == 1
    assert report["formal_upgrade_pass_count"] == 1
    assert report["rows"][0]["variant"] == "best_by_sharpe"
    assert report["rows"][0]["formal_upgrade_pass"] is True


def test_compare_candidates_allows_same_file_with_embedded_baseline_and_candidates(tmp_path: Path) -> None:
    combined = _write_json(
        tmp_path / "combined.json",
        {
            "baseline": {"metrics": {"final_value": 100.0, "sharpe_ratio": 1.0, "max_drawdown": -0.20}},
            "summary": {
                "best_by_final_value": {
                    "metrics": {
                        "final_value": 101.0,
                        "sharpe_ratio": 1.1,
                        "sortino_ratio": 1.2,
                        "max_drawdown": -0.19,
                    },
                    "trigger_days": 2,
                }
            },
        },
    )

    report = compare_candidates(combined, [combined])

    assert report["candidate_row_count"] == 1
    assert report["formal_upgrade_pass_count"] == 1


def test_compare_candidates_ranks_final_value_floor_before_sharpe(tmp_path: Path) -> None:
    baseline = _write_json(
        tmp_path / "baseline.json",
        {"metrics": {"final_value": 100.0, "sharpe_ratio": 1.0, "max_drawdown": -0.20}},
    )
    candidate = _write_json(
        tmp_path / "candidate.json",
        {
            "experiment": "objective_candidate",
            "rows": [
                {
                    "name": "high_sharpe_value_drag",
                    "final_value": 94.0,
                    "sharpe_ratio": 1.8,
                    "sortino_ratio": 2.0,
                    "max_drawdown": -0.18,
                    "trigger_days": 4,
                },
                {
                    "name": "lower_sharpe_value_safe",
                    "final_value": 99.0,
                    "sharpe_ratio": 1.1,
                    "sortino_ratio": 1.2,
                    "max_drawdown": -0.19,
                    "trigger_days": 4,
                },
            ],
        },
    )

    report = compare_candidates(baseline, [candidate])

    assert report["top_candidates"][0]["variant"] == "lower_sharpe_value_safe"
    assert report["top_candidates"][0]["promotion_objective_status"] == "pass"
    assert report["top_candidates"][1]["variant"] == "high_sharpe_value_drag"
    assert report["top_candidates"][1]["final_value_floor_pass"] is False
