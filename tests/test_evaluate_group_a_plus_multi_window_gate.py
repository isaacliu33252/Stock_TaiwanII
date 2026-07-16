from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.evaluate_group_a_plus_multi_window_gate import evaluate_multi_window


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_multi_window_gate_blocks_candidate_with_mixed_window_results(tmp_path: Path) -> None:
    first = _write_json(
        tmp_path / "fold_1.json",
        {
            "experiment": "garch_fold",
            "fold": {
                "test_window": ["2008-01-01", "2008-12-31"],
                "test_final_value": {"static_best_frozen": 100.0, "selector": 105.0},
                "test_sharpe": {"static_best_frozen": 0.10, "selector": 0.20},
                "test_mdd": {"static_best_frozen": -0.30, "selector": -0.25},
            },
        },
    )
    second = _write_json(
        tmp_path / "fold_2.json",
        {
            "experiment": "garch_fold",
            "fold": {
                "test_window": ["2020-01-01", "2020-12-31"],
                "test_final_value": {"static_best_frozen": 100.0, "selector": 104.0},
                "test_sharpe": {"static_best_frozen": 0.50, "selector": 0.45},
                "test_mdd": {"static_best_frozen": -0.20, "selector": -0.19},
            },
        },
    )

    report = evaluate_multi_window([first, second])

    assert report["decision"] == "research_only_no_multi_window_pass"
    assert report["candidate_count"] == 1
    candidate = report["candidates"][0]
    assert candidate["candidate"] == "selector"
    assert candidate["pass_count"] == 1
    assert candidate["decision"] == "research_only_multi_window_unstable"
    assert candidate["rows"][1]["window_fail_reasons"] == ["sharpe_delta"]


def test_multi_window_gate_extracts_shadow_verify_schema(tmp_path: Path) -> None:
    shadow = _write_json(
        tmp_path / "shadow_verify.json",
        {
            "report_type": "shadow_verify",
            "window": {"start": "2025-01-02", "end": "2026-07-02"},
            "current_active_metrics": {
                "final_value": 100.0,
                "sharpe_ratio": 1.0,
                "max_drawdown": -0.20,
            },
            "shadow_2008_candidate_metrics": {
                "final_value": 101.0,
                "sharpe_ratio": 1.1,
                "max_drawdown": -0.18,
            },
        },
    )

    report = evaluate_multi_window([shadow])

    assert report["decision"] == "candidate_available"
    candidate = report["candidates"][0]
    assert candidate["candidate"] == "shadow_2008_candidate"
    assert candidate["decision"] == "multi_window_pass"
    assert candidate["rows"][0]["window"] == "2025-01-02_2026-07-02"


def test_multi_window_gate_ignores_garch_fold_benchmarks(tmp_path: Path) -> None:
    fold = _write_json(
        tmp_path / "fold.json",
        {
            "experiment": "garch_fold",
            "fold": {
                "test_window": ["2008-01-01", "2008-12-31"],
                "test_final_value": {
                    "static_best_frozen": 100.0,
                    "a207": 90.0,
                    "ma20": 100.0,
                    "garch_selector_frozen": 105.0,
                },
                "test_sharpe": {
                    "static_best_frozen": 0.10,
                    "a207": 0.05,
                    "ma20": 0.10,
                    "garch_selector_frozen": 0.20,
                },
                "test_mdd": {
                    "static_best_frozen": -0.30,
                    "a207": -0.35,
                    "ma20": -0.30,
                    "garch_selector_frozen": -0.25,
                },
            },
        },
    )

    report = evaluate_multi_window([fold])

    assert [candidate["candidate"] for candidate in report["candidates"]] == ["garch_selector_frozen"]
