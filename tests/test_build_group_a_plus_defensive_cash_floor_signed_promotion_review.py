from __future__ import annotations

from pathlib import Path

from scripts.evaluate.build_group_a_plus_defensive_cash_floor_signed_promotion_review import (
    build_review,
    write_markdown,
)


def test_build_review_ready_but_does_not_authorize_live_actions(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    source.write_text("{}", encoding="utf-8")
    sweep = {
        "status": "ok",
        "top_variants": [
            {
                "variant": "cash55_risk7_tail1",
                "cash_floor": 0.55,
                "total_risk_min": 7,
                "tail_risk_min": 1,
                "changed_days": 27,
                "active_days": 27,
                "delta_total_return_delta": 0.052,
                "delta_sharpe_delta": 0.007,
                "delta_max_drawdown_delta": 0.028,
                "delta_worst_day_delta": 0.009,
            }
        ],
    }
    validation = {
        "status": "ok",
        "variant": "cash55_risk7_tail1",
        "summary": {"evaluable_changed_window_count": 5, "pass_count": 5, "fail_windows": []},
        "decision": {"promotion_decision": "shadow_candidate_for_fold_ablation"},
    }
    ablation = {
        "status": "ok",
        "candidate": "cash55_risk7_tail1",
        "summary": {
            "evaluable_changed_fold_count": 4,
            "candidate_pass_count": 4,
            "same_family_train_selection_count": 4,
            "fail_folds": [],
        },
        "decision": {"promotion_decision": "shadow_candidate_for_signed_review"},
    }

    review = build_review(
        sweep=sweep,
        validation=validation,
        ablation=ablation,
        source_paths={"sweep": source, "validation": source, "ablation": source},
        as_of="2026-08-06",
    )

    assert review["status"] == "manual_signature_pending"
    assert review["decision"]["signed_review_ready"] is True
    assert review["decision"]["manual_signature_valid"] is False
    assert review["decision"]["target_weight_change_allowed"] is False
    assert review["decision"]["auto_rebalance_allowed"] is False
    assert review["candidate"]["does_not_add_00631l"] is True


def test_build_review_blocks_when_ablation_not_ready(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    source.write_text("{}", encoding="utf-8")

    review = build_review(
        sweep={"status": "ok", "top_variants": [{"variant": "cash55_risk7_tail1"}]},
        validation={"status": "ok", "summary": {"fail_windows": []}},
        ablation={"status": "ok", "decision": {"promotion_decision": "do_not_promote"}, "summary": {"fail_folds": []}},
        source_paths={"sweep": source, "validation": source, "ablation": source},
        as_of="2026-08-06",
    )

    assert review["status"] == "blocked"
    assert review["decision"]["signed_review_ready"] is False
    assert review["decision"]["promote_to_live"] is False


def test_write_markdown_outputs_review_summary(tmp_path: Path) -> None:
    review = {
        "status": "manual_signature_pending",
        "as_of": "2026-08-06",
        "candidate": {"variant": "cash55_risk7_tail1", "rule": "raise cash"},
        "decision": {
            "signed_review_ready": True,
            "manual_signature_valid": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
        },
        "evidence": {
            "sweep": {
                "total_return_delta": 0.052,
                "max_drawdown_delta": 0.028,
                "worst_day_delta": 0.009,
                "changed_days": 27,
            },
            "window_validation": {"pass_count": 5, "evaluable_changed_window_count": 5},
            "fold_ablation": {
                "candidate_pass_count": 4,
                "evaluable_changed_fold_count": 4,
                "same_family_train_selection_count": 4,
            },
        },
        "limitations": ["sparse evidence"],
    }
    output = tmp_path / "review.md"

    write_markdown(review, output)

    text = output.read_text(encoding="utf-8")
    assert "cash55_risk7_tail1" in text
    assert "target_weight_change_allowed: `False`" in text
