#!/usr/bin/env python3
"""Tests for A21.18 DFL advisory snapshot builder."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.run.build_a2118_dfl_advisory import build_advisory


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_dfl_advisory_returns_keep_when_no_matching_non_keep_date(tmp_path: Path) -> None:
    result = tmp_path / "dfl.json"
    live = tmp_path / "live.json"
    _write_json(
        result,
        {
            "status": "research_only",
            "method": {"actions": ["KEEP", "CAP10"], "target": "action_regret"},
            "summary": {"all_windows_triple_pass": True},
            "results": [
                {
                    "label": "active",
                    "bucket": "tuning",
                    "non_keep_decisions": [{"date": "2026-01-05", "action": "CAP10", "predicted_regret": 0.001}],
                }
            ],
        },
    )
    _write_json(live, {"success": True, "data": {"actual_data_date": "2026-01-06"}})

    payload = build_advisory(input_path=result, live_signal_path=live)

    assert payload["status"] == "available"
    assert payload["action"] == "KEEP"
    assert payload["advisory_active"] is False
    assert payload["active_allocation_impact"] == "none"


def test_dfl_advisory_surfaces_matching_non_keep_as_manual_review_only(tmp_path: Path) -> None:
    result = tmp_path / "dfl.json"
    live = tmp_path / "live.json"
    _write_json(
        result,
        {
            "status": "research_only",
            "method": {
                "actions": ["KEEP", "NO_ADD", "CAP10", "REENTER"],
                "target": "action_regret = Utility(action) - Utility(KEEP)",
                "stabilizers": {"regret_clip": 0.02, "turnover_cap": 0.05},
            },
            "summary": {"all_windows_triple_pass": True},
            "results": [
                {
                    "label": "active",
                    "bucket": "tuning",
                    "non_keep_decisions": [
                        {
                            "date": "2026-01-05",
                            "action": "CAP10",
                            "predicted_regret": 0.001,
                            "base_00631l_weight": 0.126,
                            "final_00631l_weight": 0.10,
                        }
                    ],
                }
            ],
        },
    )
    _write_json(live, {"success": True, "data": {"actual_data_date": "2026-01-05"}})

    payload = build_advisory(input_path=result, live_signal_path=live)

    assert payload["action"] == "CAP10"
    assert payload["advisory_active"] is True
    assert payload["recommended_action"] == "manual_review_consider_shadow_action"
    assert payload["policy"] == "advisory_only_no_auto_weight_change"
    assert payload["selected_decision"]["predicted_regret"] == 0.001


def test_dfl_advisory_missing_shadow_result_is_unavailable(tmp_path: Path) -> None:
    live = tmp_path / "live.json"
    _write_json(live, {"success": True, "data": {"actual_data_date": "2026-01-05"}})

    payload = build_advisory(input_path=tmp_path / "missing.json", live_signal_path=live)

    assert payload["status"] == "unavailable"
    assert payload["reason"] == "dfl_shadow_result_missing"


def test_dfl_advisory_includes_selective_variants(tmp_path: Path) -> None:
    base = tmp_path / "base.json"
    p50 = tmp_path / "p50.json"
    p70 = tmp_path / "p70.json"
    live = tmp_path / "live.json"
    common = {
        "status": "research_only",
        "method": {
            "actions": ["KEEP", "CAP10"],
            "target": "action_regret",
            "stabilizers": {"selective_reliability": True},
        },
        "summary": {"all_windows_triple_pass": True},
    }
    _write_json(
        base,
        {
            **common,
            "results": [
                {"label": "base", "bucket": "tuning", "non_keep_decisions": []},
            ],
        },
    )
    _write_json(
        p50,
        {
            **common,
            "results": [
                {
                    "label": "p50",
                    "bucket": "tuning",
                    "non_keep_decisions": [
                        {
                            "date": "2026-01-05",
                            "action": "CAP10",
                            "predicted_regret": 0.001,
                            "reliability_error_percentile": 0.4,
                        }
                    ],
                }
            ],
        },
    )
    _write_json(
        p70,
        {
            **common,
            "results": [
                {
                    "label": "p70",
                    "bucket": "tuning",
                    "non_keep_decisions": [
                        {
                            "date": "2026-01-04",
                            "action": "CAP10",
                            "predicted_regret": 0.001,
                            "reliability_error_percentile": 0.6,
                        }
                    ],
                }
            ],
        },
    )
    _write_json(live, {"success": True, "data": {"actual_data_date": "2026-01-05"}})

    payload = build_advisory(
        input_path=base,
        live_signal_path=live,
        selective_inputs={"p50": p50, "p70": p70},
    )

    assert payload["action"] == "KEEP"
    assert payload["selective_variants"]["p50"]["action"] == "CAP10"
    assert payload["selective_variants"]["p50"]["advisory_active"] is True
    assert payload["selective_variants"]["p70"]["action"] == "KEEP"
    assert "selective_variants" not in payload["selective_variants"]["p50"]
