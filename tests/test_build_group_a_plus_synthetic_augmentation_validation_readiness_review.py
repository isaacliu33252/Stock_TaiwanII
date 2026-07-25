from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_synthetic_augmentation_validation_readiness_review import (
    build_review,
    write_review,
)


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_build_review_blocks_synthetic_alpha_without_validation_gates(tmp_path: Path) -> None:
    finstressts = tmp_path / "finstressts.json"
    hmm_wj = tmp_path / "hmm_wj.json"
    dynamic_cvar = tmp_path / "dynamic_cvar.json"
    density = tmp_path / "density.json"
    validation_audit = tmp_path / "validation_audit.json"
    promotion_gate = tmp_path / "promotion_gate.json"
    _write(
        finstressts,
        {
            "status": "blocked",
            "decision": {"allow_00631l_add": False},
            "summary": {"as_of": "2026-07-20"},
        },
    )
    _write(
        hmm_wj,
        {
            "status": "blocked",
            "as_of": "2026-07-20",
            "data_readiness": {"all_required_tickers_ready": True},
            "decision": {"can_generate_scenarios_for_decision": False, "allow_00631l_add": False},
        },
    )
    _write(
        dynamic_cvar,
        {
            "status": "blocked",
            "decision": {
                "tail_cost_readiness_ready": False,
                "dynamic_optimizer_ready": False,
                "allow_00631l_add": False,
            },
        },
    )
    _write(
        density,
        {
            "status": "available",
            "best_heads": {
                "recommended_research_baseline": "gaussian_residual_head",
                "gmm_status": "unstable_across_windows_research_only",
            },
        },
    )
    _write(
        validation_audit,
        {
            "status": "failed",
            "method": {
                "size_matched_null_augmentation_implemented": True,
                "block_permutation_test_implemented": True,
                "walk_forward_oos_panel_used": True,
            },
            "summary": {
                "validation_passed": False,
                "passed_task_count": 0,
                "task_count": 2,
                "directional_synthetic_alpha_tested": False,
                "directional_validation_passed": False,
                "rare_validation_passed": False,
            },
            "decision": {"directional_synthetic_alpha_allowed": False},
        },
    )
    _write(promotion_gate, {"status": "blocked_multi_window"})

    review = build_review(
        finstressts_path=finstressts,
        hmm_wj_path=hmm_wj,
        dynamic_cvar_path=dynamic_cvar,
        density_path=density,
        validation_audit_path=validation_audit,
        promotion_gate_path=promotion_gate,
    )

    assert review["report_type"] == "group_a_plus_synthetic_augmentation_validation_readiness_review"
    assert review["status"] == "blocked"
    assert review["decision"]["synthetic_validation_ready"] is False
    assert review["decision"]["directional_synthetic_alpha_allowed"] is False
    assert review["decision"]["synthetic_generator_promotion_allowed"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["validation_readiness"]["size_matched_null_augmentation_implemented"] is True
    assert review["validation_readiness"]["block_permutation_test_implemented"] is True
    assert review["validation_readiness"]["directional_audit_passed"] is False
    assert review["validation_readiness"]["rare_regime_audit_passed"] is False
    assert "synthetic_augmentation_validation_audit_failed" in review["blocking_reasons"]
    assert "directional_synthetic_alpha_default_blocked" in review["blocking_reasons"]
    assert "density_tail_model_unstable_research_only" in review["blocking_reasons"]
    assert "promotion_gate_blocked_multi_window" in review["blocking_reasons"]


def test_write_review_writes_output_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_synthetic_augmentation_validation_readiness_review",
        "as_of": "2026-07-20",
        "decision": {"allow_00631l_add": False},
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    assert json.loads((history / "20260720.json").read_text(encoding="utf-8")) == review
