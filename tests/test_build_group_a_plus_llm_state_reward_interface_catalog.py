from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_llm_state_reward_interface_catalog import build_catalog, write_catalog


def test_build_catalog_keeps_research_allowlist_live_blocked(tmp_path: Path) -> None:
    readiness = tmp_path / "readiness.json"
    readiness.write_text(
        json.dumps(
            {
                "status": "blocked",
                "blocking_reasons": ["rl_governance_blocked"],
                "decision": {"llm_state_reward_interface_ready": False},
            }
        ),
        encoding="utf-8",
    )

    catalog = build_catalog(readiness_path=readiness, as_of="2026-07-20")

    assert catalog["report_type"] == "group_a_plus_llm_state_reward_interface_catalog"
    assert catalog["status"] == "research_catalog_available_live_blocked"
    assert catalog["readiness_input"]["blocked"] is True
    assert sorted(catalog["feature_allowlist"]) == [
        "bucket_active_pain",
        "downside_risk",
        "liquidity",
        "mean_reversion",
        "momentum",
        "trend_strength",
        "volatility",
    ]
    assert sorted(catalog["reward_allowlist"]) == [
        "active_bucket_drawdown_penalty",
        "cash_defense_bonus",
        "concentration_penalty",
        "drawdown_penalty",
        "letf_tail_decay_cost",
        "turnover_penalty",
        "volatility_scaling",
    ]
    assert catalog["proposal_validation_rules"]["must_not_output_actions"] is True
    assert catalog["proposal_validation_rules"]["must_not_output_target_weights"] is True
    assert catalog["proposal_validation_rules"]["test_time_llm_queries_allowed"] is False
    assert catalog["proposal_validation_rules"]["generated_code_live_execution_allowed"] is False
    assert "llm_target_weight_output" in catalog["explicit_rejections"]
    assert catalog["decision"]["catalog_available_for_research_review"] is True
    assert catalog["decision"]["llm_state_reward_interface_ready"] is False
    assert catalog["decision"]["live_llm_trading_allowed"] is False
    assert catalog["decision"]["live_ppo_allocator_allowed"] is False
    assert catalog["decision"]["promote_to_live"] is False
    assert catalog["decision"]["target_weight_change_allowed"] is False
    assert catalog["decision"]["auto_rebalance_allowed"] is False
    assert catalog["decision"]["allow_00631l_add"] is False
    assert catalog["decision"]["allow_00632r_open"] is False


def test_write_catalog_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "catalog.json"
    history = tmp_path / "history"
    catalog = {
        "report_type": "group_a_plus_llm_state_reward_interface_catalog",
        "as_of": "2026-07-20",
    }

    write_catalog(catalog, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == catalog
    history_file = history / "llm_state_reward_interface_catalog_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == catalog
