from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_2609_08106_adoption_matrix import build_report, render_markdown


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _args(tmp_path: Path, **overrides) -> argparse.Namespace:
    values = {
        "review": tmp_path / "review.json",
        "readiness": tmp_path / "readiness.json",
        "robustness": tmp_path / "robustness.json",
        "forward": tmp_path / "forward.json",
        "forward_log": tmp_path / "forward.jsonl",
        "latest_target_replay": tmp_path / "latest_target_replay.json",
        "latest_target_param_sweep": tmp_path / "latest_target_param_sweep.json",
        "latest_strategy": tmp_path / "strategy.json",
        "min_forward_samples": 20,
        "min_triggered_forward_samples": 5,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_adoption_matrix_allows_advisory_but_blocks_live_weights_when_forward_log_is_thin(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "review.json",
        {
            "decision": {"changes_latest_strategy": False},
            "group_a_plus_fit": {"current_watchlist_size": 6},
        },
    )
    _write_json(
        tmp_path / "readiness.json",
        {
            "blockers": [],
            "decision": {"promotion_ready": False, "target_weight_change_allowed": False},
        },
    )
    _write_json(
        tmp_path / "robustness.json",
        {
            "robust_combo_count": 18,
            "decision": {"promotion_ready": False, "target_weight_change_allowed": False},
        },
    )
    _write_json(tmp_path / "forward.json", {"signal": {"triggered": False, "signal_date": "2026-09-10"}})
    _write_json(
        tmp_path / "latest_target_replay.json",
        {
            "event_count": 0,
            "coverage": {"days_with_00631l_weight": 1},
            "delta_sleeve_minus_baseline": {"total_return": 0.0, "sharpe_ratio": 0.0},
            "decision": {"blockers": ["no_sleeve_events_on_latest_target_weights"]},
        },
    )
    _write_json(
        tmp_path / "latest_target_param_sweep.json",
        {"summary": {"grid_count": 100, "positive_core_metric_count": 0, "positive_core_metric_rate": 0.0}},
    )
    _write_json(
        tmp_path / "strategy.json",
        {
            "active_strategy": {
                "id": "a2118_a2111_ncf_late_bull_deleverage",
                "status": "active",
                "runner": "group_a_plus.runners.a2118",
            }
        },
    )
    (tmp_path / "forward.jsonl").write_text(
        json.dumps(
            {
                "signal_date": "2026-09-10",
                "signal": {"triggered": False},
                "realized_next_day": {"available": False},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = build_report(_args(tmp_path))

    assert report["report_type"] == "group_a_plus_2609_08106_adoption_matrix"
    assert report["decision"]["advisory_import_allowed"] is True
    assert report["decision"]["live_weight_change_allowed"] is False
    assert report["decision"]["adopt_into_latest_strategy_now"] is False
    assert report["forward_evidence_gate"]["passed"] is False
    assert report["forward_evidence_gate"]["sample_count"] == 1
    assert report["forward_evidence_gate"]["triggered_count"] == 0

    by_candidate = {row["candidate"]: row for row in report["candidates"]}
    assert by_candidate["cross_asset_complementarity_score"]["verdict"] == "advisory_ready"
    assert by_candidate["cross_asset_complementarity_score"]["advisory_import_allowed"] is True
    assert by_candidate["mom5_gated_bond_sleeve"]["verdict"] == "continue_forward_shadow"
    assert by_candidate["mom5_gated_bond_sleeve"]["live_weight_change_allowed"] is False
    assert by_candidate["mom5_gated_bond_sleeve"]["evidence"]["latest_target_weight_replay"]["event_count"] == 0
    assert by_candidate["graph_or_topk_sparse_masks"]["verdict"] == "reject"
    assert by_candidate["nystrom_attention_replacement"]["verdict"] == "broad_universe_research_only"


def test_adoption_matrix_keeps_positive_latest_replay_shadow_only(tmp_path: Path) -> None:
    _write_json(tmp_path / "review.json", {})
    _write_json(tmp_path / "readiness.json", {"blockers": [], "decision": {"promotion_ready": False}})
    _write_json(tmp_path / "robustness.json", {"robust_combo_count": 18, "decision": {"promotion_ready": False}})
    _write_json(tmp_path / "forward.json", {"signal": {"triggered": False, "signal_date": "2026-09-10"}})
    _write_json(
        tmp_path / "latest_target_replay.json",
        {
            "event_count": 79,
            "coverage": {"days_with_00631l_weight": 287},
            "delta_sleeve_minus_baseline": {"total_return": 0.041, "sharpe_ratio": 0.212},
            "decision": {"blockers": []},
        },
    )
    _write_json(
        tmp_path / "latest_target_param_sweep.json",
        {
            "summary": {
                "grid_count": 100,
                "positive_core_metric_count": 80,
                "positive_core_metric_rate": 0.8,
                "best_by_delta_sharpe": {"delta_sharpe": 0.428},
            }
        },
    )
    _write_json(tmp_path / "strategy.json", {"active_strategy": {"id": "a2118"}})
    (tmp_path / "forward.jsonl").write_text("", encoding="utf-8")

    report = build_report(_args(tmp_path))

    by_candidate = {row["candidate"]: row for row in report["candidates"]}
    mom5 = by_candidate["mom5_gated_bond_sleeve"]
    assert mom5["evidence"]["latest_target_weight_replay"]["event_count"] == 79
    assert mom5["evidence"]["latest_target_weight_param_sweep"]["positive_core_metric_rate"] == 0.8
    assert mom5["live_weight_change_allowed"] is False
    assert "parameter sweep are encouraging" in mom5["reason"]
    assert "no current sleeve events" not in mom5["reason"]
    assert report["decision"]["live_weight_change_allowed"] is False


def test_render_markdown_states_no_live_weight_change(tmp_path: Path) -> None:
    _write_json(tmp_path / "review.json", {})
    _write_json(tmp_path / "readiness.json", {"blockers": [], "decision": {"promotion_ready": False}})
    _write_json(tmp_path / "robustness.json", {"robust_combo_count": 1, "decision": {"promotion_ready": False}})
    _write_json(tmp_path / "forward.json", {"signal": {"triggered": True}})
    _write_json(tmp_path / "latest_target_replay.json", {})
    _write_json(tmp_path / "latest_target_param_sweep.json", {})
    _write_json(tmp_path / "strategy.json", {"active_strategy": {"id": "a2118"}})
    (tmp_path / "forward.jsonl").write_text("", encoding="utf-8")

    markdown = render_markdown(build_report(_args(tmp_path)))

    assert "# 2609.08106 Adoption Matrix" in markdown
    assert "advisory_import_allowed: `True`" in markdown
    assert "live_weight_change_allowed: `False`" in markdown
    assert "Do not change latest GroupA++ target weights" in markdown
