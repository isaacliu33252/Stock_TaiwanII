from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_2605_17307_sac_global_rl_readiness_review import (
    build_review,
    write_review,
)


def test_review_blocks_full_sac_and_keeps_latest_strategy(tmp_path: Path) -> None:
    strategy = tmp_path / "strategy.json"
    strategy.write_text(
        json.dumps(
            {
                "active_strategy": {
                    "id": "a2118_a2111_ncf_late_bull_deleverage",
                    "runner": "group_a_plus.runners.a2118",
                    "status": "active",
                }
            }
        ),
        encoding="utf-8",
    )

    report = build_review(strategy_path=strategy)

    assert report["report_type"] == "group_a_plus_2605_17307_sac_global_rl_readiness_review"
    assert report["decision"]["train_sac_now"] is False
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["decision"]["latest_strategy_remains"] == "a2118_a2111_ncf_late_bull_deleverage"
    assert "train_full_sac_actor_critic_now" in report["rejected_imports"]


def test_review_keeps_reusable_concepts_separate_from_rejected_imports(tmp_path: Path) -> None:
    report = build_review(strategy_path=tmp_path / "missing.json")

    concepts = {item["concept"] for item in report["reusable_concepts"]}

    assert "hierarchical_equity_cash_decision" in concepts
    assert "cash_allowed_flexible_exposure" in concepts
    assert report["decision"]["allow_rl_generated_target_weights"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    report = {
        "report_type": "group_a_plus_2605_17307_sac_global_rl_readiness_review",
        "decision": {"target_weight_change_allowed": False},
    }

    write_review(report, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert list(history.glob("2605_17307_sac_global_rl_readiness_review_*.json"))
