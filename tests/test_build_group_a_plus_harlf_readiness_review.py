from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_harlf_readiness_review import build_review, write_review


def _write(path: Path, payload: dict | str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_harlf_review_blocks_live_import_when_required_evidence_missing(tmp_path: Path) -> None:
    sentiment_dir = tmp_path / "sentiment"
    _write(sentiment_dir / "finbert_market_sentiment_daily.csv", "date,score\n2026-08-08,0.1\n")
    market = _write(tmp_path / "market.json", {"status": "research_only"})
    llm = _write(
        tmp_path / "llm.json",
        {"status": "blocked", "decision": {"live_llm_trading_allowed": False, "target_weight_change_allowed": False}},
    )
    research = _write(tmp_path / "research.json", {"status": "available", "decision": {"allow_00631l_add": False}})
    branch = _write(tmp_path / "branch.json", {"status": "blocked", "decision": {}})

    review = build_review(
        market_sentiment_path=market,
        llm_readiness_path=llm,
        research_snapshot_path=research,
        branch_ablation_path=branch,
        sentiment_dir=sentiment_dir,
        as_of="2026-08-08",
    )

    assert review["report_type"] == "group_a_plus_harlf_readiness_review"
    assert review["status"] == "blocked"
    assert review["decision"]["harlf_readiness_imported_as_review"] is True
    assert review["decision"]["live_harlf_super_agent_allowed"] is False
    assert review["decision"]["target_weight_change_allowed"] is False
    assert review["decision"]["keep_golden1_0531_unchanged"] is True
    assert "missing_monthly_asset_level_sentiment_panel" in review["blocking_reasons"]
    assert "llm_state_reward_interface_blocked" in review["blocking_reasons"]
    assert "missing_super_agent_ablation_against_equal_weight_and_latest_strategy" in review["blocking_reasons"]


def test_harlf_review_still_requires_ablation_even_with_sentiment_panel(tmp_path: Path) -> None:
    sentiment_dir = tmp_path / "sentiment"
    _write(sentiment_dir / "finbert_market_sentiment_daily.csv", "date,score\n2026-08-08,0.1\n")
    _write(sentiment_dir / "monthly_asset_sentiment_panel.csv", "date,ticker,score\n2026-08-01,0050,0.1\n")
    market = _write(tmp_path / "market.json", {"status": "research_only"})
    llm = _write(
        tmp_path / "llm.json",
        {"status": "research_ready", "decision": {"live_llm_trading_allowed": False, "target_weight_change_allowed": False}},
    )
    research = _write(tmp_path / "research.json", {"status": "available", "decision": {"allow_00631l_add": False}})
    branch = _write(
        tmp_path / "branch.json",
        {
            "status": "available",
            "decision": {
                "market_only_base_agent_oos_backtest_available": True,
                "sentiment_only_base_agent_oos_backtest_available": True,
                "combined_ablation_available": True,
            },
        },
    )

    review = build_review(
        market_sentiment_path=market,
        llm_readiness_path=llm,
        research_snapshot_path=research,
        branch_ablation_path=branch,
        sentiment_dir=sentiment_dir,
        as_of="2026-08-08",
    )

    assert review["component_readiness"]["sentiment_inventory"]["has_monthly_asset_sentiment_panel"] is True
    assert "missing_monthly_asset_level_sentiment_panel" not in review["blocking_reasons"]
    assert "missing_market_only_base_agent_oos_backtest" not in review["blocking_reasons"]
    assert "missing_sentiment_only_base_agent_oos_backtest" not in review["blocking_reasons"]
    assert review["decision"]["ready_for_hierarchical_rl_backtest"] is False


def test_harlf_review_accepts_meta_agent_shadow_but_still_requires_stress(tmp_path: Path) -> None:
    sentiment_dir = tmp_path / "sentiment"
    _write(sentiment_dir / "finbert_market_sentiment_daily.csv", "date,score\n2026-08-08,0.1\n")
    _write(sentiment_dir / "monthly_asset_sentiment_panel.csv", "date,ticker,score\n2026-08-01,0050,0.1\n")
    market = _write(tmp_path / "market.json", {"status": "research_only"})
    llm = _write(
        tmp_path / "llm.json",
        {"status": "research_ready", "decision": {"live_llm_trading_allowed": False, "target_weight_change_allowed": False}},
    )
    research = _write(tmp_path / "research.json", {"status": "available", "decision": {"allow_00631l_add": False}})
    branch = _write(
        tmp_path / "branch.json",
        {
            "status": "available",
            "decision": {
                "market_only_base_agent_oos_backtest_available": True,
                "sentiment_only_base_agent_oos_backtest_available": True,
                "combined_ablation_available": True,
            },
        },
    )
    meta = _write(
        tmp_path / "meta.json",
        {
            "status": "available",
            "decision": {
                "hierarchical_meta_agent_oos_backtest_available": True,
                "candidate_ready_for_stress_test": True,
                "promotion_ready": False,
            },
        },
    )

    review = build_review(
        market_sentiment_path=market,
        llm_readiness_path=llm,
        research_snapshot_path=research,
        branch_ablation_path=branch,
        meta_agent_path=meta,
        stress_path=tmp_path / "missing_stress.json",
        sentiment_dir=sentiment_dir,
        as_of="2026-08-08",
    )

    assert "missing_hierarchical_meta_agent_oos_backtest" not in review["blocking_reasons"]
    assert "missing_transaction_cost_and_stress_test_for_harlf" in review["blocking_reasons"]
    assert review["decision"]["target_weight_change_allowed"] is False


def test_harlf_review_records_failed_stress_as_candidate_blocker(tmp_path: Path) -> None:
    sentiment_dir = tmp_path / "sentiment"
    _write(sentiment_dir / "finbert_market_sentiment_daily.csv", "date,score\n2026-08-08,0.1\n")
    _write(sentiment_dir / "monthly_asset_sentiment_panel.csv", "date,ticker,score\n2026-08-01,0050,0.1\n")
    market = _write(tmp_path / "market.json", {"status": "research_only"})
    llm = _write(
        tmp_path / "llm.json",
        {"status": "research_ready", "decision": {"live_llm_trading_allowed": False, "target_weight_change_allowed": False}},
    )
    research = _write(tmp_path / "research.json", {"status": "available", "decision": {"allow_00631l_add": False}})
    branch = _write(
        tmp_path / "branch.json",
        {
            "status": "available",
            "decision": {
                "market_only_base_agent_oos_backtest_available": True,
                "sentiment_only_base_agent_oos_backtest_available": True,
                "combined_ablation_available": True,
            },
        },
    )
    meta = _write(
        tmp_path / "meta.json",
        {"status": "available", "decision": {"hierarchical_meta_agent_oos_backtest_available": True}},
    )
    stress = _write(
        tmp_path / "stress.json",
        {
            "status": "available",
            "decision": {
                "stress_test_available": True,
                "latest_strategy_candidate_ready_for_comparison": False,
            },
        },
    )

    review = build_review(
        market_sentiment_path=market,
        llm_readiness_path=llm,
        research_snapshot_path=research,
        branch_ablation_path=branch,
        meta_agent_path=meta,
        stress_path=stress,
        sentiment_dir=sentiment_dir,
        as_of="2026-08-08",
    )

    assert "missing_transaction_cost_and_stress_test_for_harlf" not in review["blocking_reasons"]
    assert "harlf_stress_test_not_ready_for_latest_strategy_comparison" in review["blocking_reasons"]


def test_harlf_review_records_failed_latest_strategy_comparison(tmp_path: Path) -> None:
    sentiment_dir = tmp_path / "sentiment"
    _write(sentiment_dir / "finbert_market_sentiment_daily.csv", "date,score\n2026-08-08,0.1\n")
    _write(sentiment_dir / "monthly_asset_sentiment_panel.csv", "date,ticker,score\n2026-08-01,0050,0.1\n")
    market = _write(tmp_path / "market.json", {"status": "research_only"})
    llm = _write(
        tmp_path / "llm.json",
        {"status": "research_ready", "decision": {"live_llm_trading_allowed": False, "target_weight_change_allowed": False}},
    )
    research = _write(tmp_path / "research.json", {"status": "available", "decision": {"allow_00631l_add": False}})
    branch = _write(
        tmp_path / "branch.json",
        {
            "status": "available",
            "decision": {
                "market_only_base_agent_oos_backtest_available": True,
                "sentiment_only_base_agent_oos_backtest_available": True,
                "combined_ablation_available": True,
            },
        },
    )
    meta = _write(tmp_path / "meta.json", {"status": "available", "decision": {"hierarchical_meta_agent_oos_backtest_available": True}})
    stress = _write(
        tmp_path / "stress.json",
        {"status": "available", "decision": {"stress_test_available": True, "latest_strategy_candidate_ready_for_comparison": True}},
    )
    comparison = _write(
        tmp_path / "comparison.json",
        {"status": "available", "decision": {"candidate_ready_for_latest_strategy_review": False}},
    )

    review = build_review(
        market_sentiment_path=market,
        llm_readiness_path=llm,
        research_snapshot_path=research,
        branch_ablation_path=branch,
        meta_agent_path=meta,
        stress_path=stress,
        comparison_path=comparison,
        blend_path=tmp_path / "missing_blend.json",
        sentiment_dir=sentiment_dir,
        as_of="2026-08-08",
    )

    assert "harlf_latest_strategy_comparison_not_ready" in review["blocking_reasons"]
    assert review["decision"]["target_weight_change_allowed"] is False


def test_harlf_review_accepts_viable_latest_blend(tmp_path: Path) -> None:
    sentiment_dir = tmp_path / "sentiment"
    _write(sentiment_dir / "finbert_market_sentiment_daily.csv", "date,score\n2026-08-08,0.1\n")
    _write(sentiment_dir / "monthly_asset_sentiment_panel.csv", "date,ticker,score\n2026-08-01,0050,0.1\n")
    market = _write(tmp_path / "market.json", {"status": "research_only"})
    llm = _write(
        tmp_path / "llm.json",
        {"status": "research_ready", "decision": {"live_llm_trading_allowed": False, "target_weight_change_allowed": False}},
    )
    research = _write(tmp_path / "research.json", {"status": "available", "decision": {"allow_00631l_add": False}})
    branch = _write(
        tmp_path / "branch.json",
        {
            "status": "available",
            "decision": {
                "market_only_base_agent_oos_backtest_available": True,
                "sentiment_only_base_agent_oos_backtest_available": True,
                "combined_ablation_available": True,
            },
        },
    )
    meta = _write(tmp_path / "meta.json", {"status": "available", "decision": {"hierarchical_meta_agent_oos_backtest_available": True}})
    stress = _write(
        tmp_path / "stress.json",
        {"status": "available", "decision": {"stress_test_available": True, "latest_strategy_candidate_ready_for_comparison": True}},
    )
    comparison = _write(
        tmp_path / "comparison.json",
        {"status": "available", "decision": {"candidate_ready_for_latest_strategy_review": False}},
    )
    blend = _write(
        tmp_path / "blend.json",
        {"status": "available", "decision": {"found_blend_ready_for_latest_strategy_review": True}},
    )

    review = build_review(
        market_sentiment_path=market,
        llm_readiness_path=llm,
        research_snapshot_path=research,
        branch_ablation_path=branch,
        meta_agent_path=meta,
        stress_path=stress,
        comparison_path=comparison,
        blend_path=blend,
        sentiment_dir=sentiment_dir,
        as_of="2026-08-08",
    )

    assert "harlf_latest_strategy_comparison_not_ready" not in review["blocking_reasons"]
    assert review["decision"]["target_weight_change_allowed"] is False


def test_harlf_review_requires_trade_level_oos_validation_after_viable_blend(tmp_path: Path) -> None:
    sentiment_dir = tmp_path / "sentiment"
    _write(sentiment_dir / "finbert_market_sentiment_daily.csv", "date,score\n2026-08-08,0.1\n")
    _write(sentiment_dir / "monthly_asset_sentiment_panel.csv", "date,ticker,score\n2026-08-01,0050,0.1\n")
    market = _write(tmp_path / "market.json", {"status": "research_only"})
    llm = _write(
        tmp_path / "llm.json",
        {"status": "research_ready", "decision": {"live_llm_trading_allowed": False, "target_weight_change_allowed": False}},
    )
    research = _write(tmp_path / "research.json", {"status": "available", "decision": {"allow_00631l_add": False}})
    branch = _write(
        tmp_path / "branch.json",
        {
            "status": "available",
            "decision": {
                "market_only_base_agent_oos_backtest_available": True,
                "sentiment_only_base_agent_oos_backtest_available": True,
                "combined_ablation_available": True,
            },
        },
    )
    meta = _write(tmp_path / "meta.json", {"status": "available", "decision": {"hierarchical_meta_agent_oos_backtest_available": True}})
    stress = _write(
        tmp_path / "stress.json",
        {"status": "available", "decision": {"stress_test_available": True, "latest_strategy_candidate_ready_for_comparison": True}},
    )
    comparison = _write(
        tmp_path / "comparison.json",
        {"status": "available", "decision": {"candidate_ready_for_latest_strategy_review": False}},
    )
    blend = _write(
        tmp_path / "blend.json",
        {"status": "available", "decision": {"found_blend_ready_for_latest_strategy_review": True}},
    )
    trade_oos = _write(
        tmp_path / "trade_oos.json",
        {
            "status": "blocked",
            "blocking_reasons": ["harlf_uses_assets_outside_group_a_plus_tradable_universe"],
            "non_tradable_assets": ["2330"],
            "decision": {"trade_level_oos_validation_passed": False, "promotion_ready": False},
        },
    )

    review = build_review(
        market_sentiment_path=market,
        llm_readiness_path=llm,
        research_snapshot_path=research,
        branch_ablation_path=branch,
        meta_agent_path=meta,
        stress_path=stress,
        comparison_path=comparison,
        blend_path=blend,
        trade_oos_path=trade_oos,
        trade_oos_etf_mapped_path=tmp_path / "missing_trade_oos_etf_mapped.json",
        sentiment_dir=sentiment_dir,
        as_of="2026-08-08",
    )

    assert "harlf_latest_strategy_comparison_not_ready" not in review["blocking_reasons"]
    assert "harlf_trade_level_oos_validation_not_passed" in review["blocking_reasons"]
    assert review["component_readiness"]["trade_level_oos_non_tradable_assets"] == ["2330"]
    assert review["decision"]["promotion_ready"] is False


def test_harlf_review_clears_trade_oos_blocker_when_validation_passes(tmp_path: Path) -> None:
    sentiment_dir = tmp_path / "sentiment"
    _write(sentiment_dir / "finbert_market_sentiment_daily.csv", "date,score\n2026-08-08,0.1\n")
    _write(sentiment_dir / "monthly_asset_sentiment_panel.csv", "date,ticker,score\n2026-08-01,0050,0.1\n")
    market = _write(tmp_path / "market.json", {"status": "research_only"})
    llm = _write(
        tmp_path / "llm.json",
        {"status": "research_ready", "decision": {"live_llm_trading_allowed": False, "target_weight_change_allowed": False}},
    )
    research = _write(tmp_path / "research.json", {"status": "available", "decision": {"allow_00631l_add": False}})
    branch = _write(
        tmp_path / "branch.json",
        {
            "status": "available",
            "decision": {
                "market_only_base_agent_oos_backtest_available": True,
                "sentiment_only_base_agent_oos_backtest_available": True,
                "combined_ablation_available": True,
            },
        },
    )
    meta = _write(tmp_path / "meta.json", {"status": "available", "decision": {"hierarchical_meta_agent_oos_backtest_available": True}})
    stress = _write(
        tmp_path / "stress.json",
        {"status": "available", "decision": {"stress_test_available": True, "latest_strategy_candidate_ready_for_comparison": True}},
    )
    comparison = _write(
        tmp_path / "comparison.json",
        {"status": "available", "decision": {"candidate_ready_for_latest_strategy_review": False}},
    )
    blend = _write(
        tmp_path / "blend.json",
        {"status": "available", "decision": {"found_blend_ready_for_latest_strategy_review": True}},
    )
    trade_oos = _write(
        tmp_path / "trade_oos.json",
        {"status": "available", "decision": {"trade_level_oos_validation_passed": True, "promotion_ready": False}},
    )

    review = build_review(
        market_sentiment_path=market,
        llm_readiness_path=llm,
        research_snapshot_path=research,
        branch_ablation_path=branch,
        meta_agent_path=meta,
        stress_path=stress,
        comparison_path=comparison,
        blend_path=blend,
        trade_oos_path=trade_oos,
        trade_oos_etf_mapped_path=tmp_path / "missing_trade_oos_etf_mapped.json",
        sentiment_dir=sentiment_dir,
        as_of="2026-08-08",
    )

    assert "harlf_trade_level_oos_validation_not_passed" not in review["blocking_reasons"]
    assert review["component_readiness"]["trade_level_oos_decision"]["trade_level_oos_validation_passed"] is True


def test_harlf_review_prefers_etf_mapped_trade_oos_for_readiness(tmp_path: Path) -> None:
    sentiment_dir = tmp_path / "sentiment"
    _write(sentiment_dir / "finbert_market_sentiment_daily.csv", "date,score\n2026-08-08,0.1\n")
    _write(sentiment_dir / "monthly_asset_sentiment_panel.csv", "date,ticker,score\n2026-08-01,0050,0.1\n")
    market = _write(tmp_path / "market.json", {"status": "research_only"})
    llm = _write(
        tmp_path / "llm.json",
        {"status": "research_ready", "decision": {"live_llm_trading_allowed": False, "target_weight_change_allowed": False}},
    )
    research = _write(tmp_path / "research.json", {"status": "available", "decision": {"allow_00631l_add": False}})
    branch = _write(
        tmp_path / "branch.json",
        {
            "status": "available",
            "decision": {
                "market_only_base_agent_oos_backtest_available": True,
                "sentiment_only_base_agent_oos_backtest_available": True,
                "combined_ablation_available": True,
            },
        },
    )
    meta = _write(tmp_path / "meta.json", {"status": "available", "decision": {"hierarchical_meta_agent_oos_backtest_available": True}})
    stress = _write(
        tmp_path / "stress.json",
        {"status": "available", "decision": {"stress_test_available": True, "latest_strategy_candidate_ready_for_comparison": True}},
    )
    comparison = _write(
        tmp_path / "comparison.json",
        {"status": "available", "decision": {"candidate_ready_for_latest_strategy_review": False}},
    )
    blend = _write(
        tmp_path / "blend.json",
        {"status": "available", "decision": {"found_blend_ready_for_latest_strategy_review": True}},
    )
    original_trade_oos = _write(
        tmp_path / "trade_oos.json",
        {
            "status": "blocked",
            "blocking_reasons": ["harlf_uses_assets_outside_group_a_plus_tradable_universe"],
            "tradability": {"non_tradable_assets": ["2330"]},
            "decision": {"trade_level_oos_validation_passed": False, "promotion_ready": False},
        },
    )
    mapped_trade_oos = _write(
        tmp_path / "trade_oos_mapped.json",
        {
            "status": "blocked",
            "blocking_reasons": ["missing_latest_strategy_historical_target_weight_series"],
            "tradability": {"non_tradable_assets": []},
            "decision": {"trade_level_oos_validation_passed": False, "promotion_ready": False},
        },
    )

    review = build_review(
        market_sentiment_path=market,
        llm_readiness_path=llm,
        research_snapshot_path=research,
        branch_ablation_path=branch,
        meta_agent_path=meta,
        stress_path=stress,
        comparison_path=comparison,
        blend_path=blend,
        trade_oos_path=original_trade_oos,
        trade_oos_etf_mapped_path=mapped_trade_oos,
        sentiment_dir=sentiment_dir,
        as_of="2026-08-08",
    )

    assert "harlf_trade_level_oos_validation_not_passed" in review["blocking_reasons"]
    assert review["component_readiness"]["trade_level_oos_non_tradable_assets"] == ["2330"]
    assert review["component_readiness"]["trade_level_oos_etf_mapped_non_tradable_assets"] == []
    assert review["component_readiness"]["trade_level_oos_etf_mapped_blocking_reasons"] == [
        "missing_latest_strategy_historical_target_weight_series"
    ]


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "harlf.json"
    history = tmp_path / "history"
    review = {"report_type": "group_a_plus_harlf_readiness_review", "as_of": "2026-08-08"}

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    assert json.loads((history / "harlf_readiness_20260808.json").read_text(encoding="utf-8")) == review
