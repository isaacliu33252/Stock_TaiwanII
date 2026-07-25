from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_llm_state_reward_interface_frozen_manifest import (
    build_manifest,
    write_manifest,
)


def _comparison(path: Path, dgr_path: Path) -> Path:
    dgr_path.write_text(json.dumps({"status": "available_for_manual_offline_review"}), encoding="utf-8")
    path.write_text(
        json.dumps(
            {
                "status": "available_for_manual_offline_review",
                "ranked_candidates": [
                    {
                        "label": "v2_tuned_downside_tail_decay",
                        "source": str(dgr_path),
                        "proposal_id": "gift_research_downside_vol_letf_tail_decay_v1",
                        "params": {
                            "drawdown_weight": 0.3,
                            "volatility_weight": 0.5,
                            "tail_decay_weight": 0.1,
                            "volatility_scale": 4.0,
                            "tail_decay_scale": 4.0,
                        },
                        "reward_alignment_objective": "future_downside_alignment",
                        "objective_alignment": -0.09,
                        "objective_abs_alignment": 0.09,
                        "mean_reward_snr": 2.7,
                        "finite_reward_min_ratio": 1.0,
                        "reward_alignment_grade": "green",
                        "ppo_training_queue_candidate": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_build_manifest_freezes_best_candidate_without_live_effects(tmp_path: Path) -> None:
    manifest = build_manifest(
        comparison_path=_comparison(tmp_path / "comparison.json", tmp_path / "dgr.json"),
        as_of="2026-07-20",
    )

    assert manifest["report_type"] == "group_a_plus_llm_state_reward_interface_frozen_manifest"
    assert manifest["status"] == "frozen_for_manual_offline_review"
    assert manifest["freeze"]["selected_label"] == "v2_tuned_downside_tail_decay"
    assert manifest["freeze"]["proposal_id"] == "gift_research_downside_vol_letf_tail_decay_v1"
    assert manifest["freeze"]["state_columns"] == [
        "downside_deviation",
        "realized_volatility",
        "drawdown_depth",
        "ema_cross_strength",
    ]
    assert len(manifest["freeze"]["frozen_manifest_sha256"]) == 64
    assert manifest["decision"]["offline_feature_reward_export_allowed"] is True
    assert manifest["decision"]["offline_walk_forward_design_allowed"] is True
    assert manifest["decision"]["model_training_allowed"] is False
    assert manifest["decision"]["ppo_training_allowed"] is False
    assert manifest["decision"]["outputs_actions"] is False
    assert manifest["decision"]["outputs_target_weights"] is False
    assert manifest["decision"]["promote_to_live"] is False
    assert manifest["decision"]["allow_00631l_add"] is False
    assert manifest["decision"]["allow_00632r_open"] is False


def test_build_manifest_blocks_missing_comparison(tmp_path: Path) -> None:
    manifest = build_manifest(comparison_path=tmp_path / "missing.json", as_of="2026-07-20")

    assert manifest["status"] == "blocked"
    assert "missing_proposal_comparison_review" in manifest["blocking_reasons"]
    assert manifest["decision"]["offline_feature_reward_export_allowed"] is False
    assert manifest["decision"]["promote_to_live"] is False


def test_write_manifest_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "manifest.json"
    history = tmp_path / "history"
    manifest = {
        "report_type": "group_a_plus_llm_state_reward_interface_frozen_manifest",
        "as_of": "2026-07-20",
    }

    write_manifest(manifest, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == manifest
    history_file = history / "llm_state_reward_interface_frozen_manifest_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == manifest
