from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_llm_state_reward_interface_proposal_comparison_review import (
    build_review,
    write_review,
)


def _dgr(
    path: Path,
    *,
    proposal_id: str,
    objective: str,
    grade: str,
    return_alignment: float,
    downside_alignment: float,
    snr: float,
    queue: bool,
    params: dict[str, float] | None = None,
) -> Path:
    payload = {
        "status": "available_for_manual_offline_review",
        "inputs": {
            "accepted_proposal_id": proposal_id,
            "downside_tail_decay_params": params,
        },
        "summary": {
            "reward_alignment_objective": objective,
            "reward_alignment_grade": grade,
            "return_alignment_grade": "yellow",
            "downside_alignment_grade": grade,
            "return_alignment_abs": abs(return_alignment),
            "downside_alignment_abs": abs(downside_alignment),
            "mean_reward_future_return_alignment": return_alignment,
            "mean_reward_future_downside_alignment": downside_alignment,
            "mean_reward_snr": snr,
            "finite_reward_min_ratio": 1.0,
            "downside_alignment_direction": "negative_reward_vs_positive_downside",
            "downside_alignment_risk_sensitive_useful": True,
        },
        "warning_reasons": ["sample_warning"],
        "blocking_reasons": [],
        "decision": {
            "ppo_training_queue_allowed_by_dgr": queue,
            "promote_to_live": False,
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _sweep(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "status": "available_for_manual_offline_review",
                "summary": {
                    "green_candidate_count": 7,
                    "best_params": {
                        "drawdown_weight": 0.3,
                        "volatility_weight": 0.5,
                        "tail_decay_weight": 0.1,
                        "volatility_scale": 4.0,
                        "tail_decay_scale": 4.0,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_build_review_ranks_tuned_candidate_without_live_effects(tmp_path: Path) -> None:
    tuned_params = {
        "drawdown_weight": 0.3,
        "volatility_weight": 0.5,
        "tail_decay_weight": 0.1,
        "volatility_scale": 4.0,
        "tail_decay_scale": 4.0,
    }
    review = build_review(
        v1_dgr_path=_dgr(
            tmp_path / "v1.json",
            proposal_id="gift_research_momentum_vol_drawdown_turnover_v1",
            objective="future_return_alignment",
            grade="red",
            return_alignment=-0.01,
            downside_alignment=-0.03,
            snr=1.0,
            queue=False,
        ),
        v2_dgr_path=_dgr(
            tmp_path / "v2.json",
            proposal_id="gift_research_downside_vol_letf_tail_decay_v1",
            objective="future_downside_alignment",
            grade="green",
            return_alignment=-0.03,
            downside_alignment=-0.06,
            snr=2.4,
            queue=True,
        ),
        v2_tuned_dgr_path=_dgr(
            tmp_path / "v2_tuned.json",
            proposal_id="gift_research_downside_vol_letf_tail_decay_v1",
            objective="future_downside_alignment",
            grade="green",
            return_alignment=-0.04,
            downside_alignment=-0.09,
            snr=2.7,
            queue=True,
            params=tuned_params,
        ),
        sweep_path=_sweep(tmp_path / "sweep.json"),
        as_of="2026-07-20",
    )

    assert review["report_type"] == "group_a_plus_llm_state_reward_interface_proposal_comparison_review"
    assert review["status"] == "available_for_manual_offline_review"
    assert review["summary"]["best_label"] == "v2_tuned_downside_tail_decay"
    assert review["summary"]["best_objective_alignment"] == -0.09
    assert review["summary"]["best_ppo_training_queue_candidate"] is True
    assert review["ranked_candidates"][0]["params"] == tuned_params
    assert review["decision"]["best_candidate_for_next_offline_experiment"] is True
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["ppo_training_allowed"] is False
    assert review["decision"]["outputs_actions"] is False
    assert review["decision"]["outputs_target_weights"] is False
    assert review["decision"]["promote_to_live"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False


def test_build_review_blocks_missing_inputs(tmp_path: Path) -> None:
    review = build_review(
        v1_dgr_path=tmp_path / "missing_v1.json",
        v2_dgr_path=tmp_path / "missing_v2.json",
        v2_tuned_dgr_path=tmp_path / "missing_v2_tuned.json",
        sweep_path=tmp_path / "missing_sweep.json",
        as_of="2026-07-20",
    )

    assert review["status"] == "blocked"
    assert "missing_dgr:v1_default" in review["blocking_reasons"]
    assert "missing_param_sweep" in review["blocking_reasons"]
    assert review["decision"]["best_candidate_for_next_offline_experiment"] is False
    assert review["decision"]["promote_to_live"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "comparison.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_llm_state_reward_interface_proposal_comparison_review",
        "as_of": "2026-07-20",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "llm_state_reward_interface_proposal_comparison_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
