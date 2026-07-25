from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_llm_state_reward_high_dividend_active_pain_frozen_manifest import (
    PROPOSAL_ID,
    build_manifest,
    write_manifest,
)


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _dgr(path: Path, *, passed: bool = True) -> Path:
    return _write(
        path,
        {
            "status": "available_for_manual_offline_review",
            "proposal_id": PROPOSAL_ID,
            "summary": {
                "redesigned_reward_alignment_to_future_high_dividend_active_pain": -0.13,
                "reward_snr_abs_mean_over_std": 2.2,
            },
            "decision": {"high_dividend_active_pain_dgr_passed": passed, "promote_to_live": False},
        },
    )


def _smoke(path: Path, *, passed: bool = True) -> Path:
    return _write(
        path,
        {
            "status": "available_for_manual_offline_review",
            "proposal_id": PROPOSAL_ID,
            "inputs": {
                "active_penalty_scale": 20.0,
                "drawdown_scale": 1.0,
                "return_pain_scale": 4.0,
                "concentration_scale": 0.1,
            },
            "summary": {
                "high_dividend_active_pain_offline_smoke": {
                    "positive_final_value_folds": 4,
                    "positive_sharpe_folds": 4,
                    "non_worse_drawdown_folds": 3,
                }
            },
            "decision": {"high_dividend_active_pain_offline_smoke_passed": passed, "promote_to_live": False},
        },
    )


def test_build_manifest_freezes_v3_without_live_effects(tmp_path: Path) -> None:
    manifest = build_manifest(
        dgr_path=_dgr(tmp_path / "dgr.json"),
        smoke_path=_smoke(tmp_path / "smoke.json"),
        as_of="2026-07-21",
    )

    assert manifest["report_type"] == "group_a_plus_llm_state_reward_interface_high_dividend_active_pain_frozen_manifest"
    assert manifest["status"] == "frozen_for_manual_offline_review"
    assert manifest["freeze"]["proposal_id"] == PROPOSAL_ID
    assert manifest["freeze"]["selected_label"] == "v3_high_dividend_active_pain_tuned"
    assert "high_dividend_active_pain" in manifest["freeze"]["state_columns"]
    assert "redesigned_reward_proxy" in manifest["freeze"]["reward_columns"]
    assert len(manifest["freeze"]["frozen_manifest_sha256"]) == 64
    assert manifest["decision"]["offline_walk_forward_panel_export_allowed"] is True
    assert manifest["decision"]["model_training_allowed"] is False
    assert manifest["decision"]["ppo_training_allowed"] is False
    assert manifest["decision"]["outputs_target_weights"] is False
    assert manifest["decision"]["promote_to_live"] is False
    assert manifest["decision"]["allow_00631l_add"] is False
    assert manifest["decision"]["allow_00632r_open"] is False


def test_build_manifest_blocks_failed_smoke(tmp_path: Path) -> None:
    manifest = build_manifest(
        dgr_path=_dgr(tmp_path / "dgr.json"),
        smoke_path=_smoke(tmp_path / "smoke.json", passed=False),
        as_of="2026-07-21",
    )

    assert manifest["status"] == "blocked"
    assert "offline_smoke_not_passed" in manifest["blocking_reasons"]
    assert manifest["decision"]["offline_walk_forward_panel_export_allowed"] is False
    assert manifest["decision"]["promote_to_live"] is False


def test_write_manifest_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "manifest.json"
    history = tmp_path / "history"
    manifest = {
        "report_type": "group_a_plus_llm_state_reward_interface_high_dividend_active_pain_frozen_manifest",
        "as_of": "2026-07-21",
    }

    write_manifest(manifest, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == manifest
    history_file = history / "llm_state_reward_interface_high_dividend_active_pain_frozen_manifest_20260721.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == manifest
