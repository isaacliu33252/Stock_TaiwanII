#!/usr/bin/env python3
"""Build HARLF readiness review for Group A+.

Inspired by arXiv:2507.18560. This imports only the paper's governance ideas:
separate market/sentiment branches, hierarchical aggregation, and mandatory
ablation/OOS checks before any RL allocator. It never changes weights or orders.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MARKET_SENTIMENT = PROJECT_ROOT / "report/group_a_plus/latest/market_aligned_sentiment_shadow.json"
DEFAULT_LLM_READINESS = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_readiness_review.json"
DEFAULT_RESEARCH_SNAPSHOT = PROJECT_ROOT / "report/group_a_plus/latest/research_shadow_decision_snapshot.json"
DEFAULT_BRANCH_ABLATION = PROJECT_ROOT / "report/group_a_plus/latest/harlf_branch_ablation_shadow.json"
DEFAULT_META_AGENT = PROJECT_ROOT / "report/group_a_plus/latest/harlf_compound_defensive_meta_agent_shadow.json"
DEFAULT_STRESS = PROJECT_ROOT / "report/group_a_plus/latest/harlf_compound_defensive_stress_shadow.json"
DEFAULT_COMPARISON = PROJECT_ROOT / "report/group_a_plus/latest/harlf_compound_vs_latest_strategy_comparison.json"
DEFAULT_BLEND = PROJECT_ROOT / "report/group_a_plus/latest/harlf_latest_blend_sweep.json"
DEFAULT_TRADE_OOS = PROJECT_ROOT / "report/group_a_plus/latest/harlf_latest_blend_trade_oos_validation.json"
DEFAULT_TRADE_OOS_ETF_MAPPED = PROJECT_ROOT / "report/group_a_plus/latest/harlf_latest_blend_trade_oos_validation_etf_mapped.json"
DEFAULT_SENTIMENT_DIR = PROJECT_ROOT / "FinRL/data/sentiment"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/harlf_readiness_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/harlf_readiness/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _decision(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("decision")
    return value if isinstance(value, dict) else {}


def _sentiment_inventory(path: Path) -> dict[str, Any]:
    files = sorted(p.name for p in path.glob("*") if p.is_file()) if path.exists() else []
    return {
        "path": str(path),
        "exists": path.exists(),
        "files": files,
        "has_finbert_daily": "finbert_market_sentiment_daily.csv" in files,
        "has_llm_market_daily": "llm_market_sentiment_daily.csv" in files,
        "has_monthly_asset_sentiment_panel": any("monthly" in name and "sentiment" in name for name in files),
    }


def _non_tradable_assets(payload: dict[str, Any]) -> list[Any]:
    return (payload.get("tradability") or {}).get("non_tradable_assets") or payload.get("non_tradable_assets") or []


def build_review(
    *,
    market_sentiment_path: Path = DEFAULT_MARKET_SENTIMENT,
    llm_readiness_path: Path = DEFAULT_LLM_READINESS,
    research_snapshot_path: Path = DEFAULT_RESEARCH_SNAPSHOT,
    branch_ablation_path: Path = DEFAULT_BRANCH_ABLATION,
    meta_agent_path: Path = DEFAULT_META_AGENT,
    stress_path: Path = DEFAULT_STRESS,
    comparison_path: Path = DEFAULT_COMPARISON,
    blend_path: Path = DEFAULT_BLEND,
    trade_oos_path: Path = DEFAULT_TRADE_OOS,
    trade_oos_etf_mapped_path: Path = DEFAULT_TRADE_OOS_ETF_MAPPED,
    sentiment_dir: Path = DEFAULT_SENTIMENT_DIR,
    as_of: str = "2026-08-08",
) -> dict[str, Any]:
    market_sentiment = _load(market_sentiment_path)
    llm_readiness = _load(llm_readiness_path)
    research_snapshot = _load(research_snapshot_path)
    branch_ablation = _load(branch_ablation_path)
    meta_agent = _load(meta_agent_path)
    stress = _load(stress_path)
    comparison = _load(comparison_path)
    blend = _load(blend_path)
    trade_oos = _load(trade_oos_path)
    trade_oos_etf_mapped = _load(trade_oos_etf_mapped_path)
    trade_oos_for_decision = trade_oos_etf_mapped or trade_oos
    inventory = _sentiment_inventory(sentiment_dir)
    llm_decision = _decision(llm_readiness)
    research_decision = _decision(research_snapshot)

    blockers: list[str] = []
    warnings: list[str] = []
    if not market_sentiment:
        blockers.append("missing_market_aligned_sentiment_shadow")
    if not inventory["has_finbert_daily"]:
        blockers.append("missing_finbert_daily_sentiment")
    if not inventory["has_monthly_asset_sentiment_panel"]:
        blockers.append("missing_monthly_asset_level_sentiment_panel")
    if not llm_readiness:
        blockers.append("missing_llm_state_reward_interface_readiness")
    if llm_readiness.get("status") == "blocked":
        blockers.append("llm_state_reward_interface_blocked")
    if llm_decision.get("live_llm_trading_allowed") is True:
        warnings.append("llm_readiness_unexpectedly_allows_live_llm_trading")
    if llm_decision.get("target_weight_change_allowed") is True:
        warnings.append("llm_readiness_unexpectedly_allows_target_weight_change")
    if not research_snapshot:
        warnings.append("missing_research_shadow_decision_snapshot")
    if research_snapshot.get("status") == "blocked":
        warnings.append("research_shadow_snapshot_blocked")

    # HARLF-specific missing evidence. These are intentionally blockers for a
    # live/super-agent import, but do not block keeping the checklist itself.
    branch_decision = _decision(branch_ablation)
    if branch_decision.get("market_only_base_agent_oos_backtest_available") is not True:
        blockers.append("missing_market_only_base_agent_oos_backtest")
    if branch_decision.get("sentiment_only_base_agent_oos_backtest_available") is not True:
        blockers.append("missing_sentiment_only_base_agent_oos_backtest")
    if branch_decision.get("combined_ablation_available") is not True:
        blockers.append("missing_super_agent_ablation_against_equal_weight_and_latest_strategy")
    meta_decision = _decision(meta_agent)
    if meta_decision.get("hierarchical_meta_agent_oos_backtest_available") is not True:
        blockers.append("missing_hierarchical_meta_agent_oos_backtest")
    stress_decision = _decision(stress)
    if stress_decision.get("stress_test_available") is not True:
        blockers.append("missing_transaction_cost_and_stress_test_for_harlf")
    elif stress_decision.get("latest_strategy_candidate_ready_for_comparison") is not True:
        blockers.append("harlf_stress_test_not_ready_for_latest_strategy_comparison")
    comparison_decision = _decision(comparison)
    blend_decision = _decision(blend)
    if (
        comparison_decision.get("candidate_ready_for_latest_strategy_review") is not True
        and blend_decision.get("found_blend_ready_for_latest_strategy_review") is not True
    ):
        blockers.append("harlf_latest_strategy_comparison_not_ready")
    trade_oos_decision = _decision(trade_oos_for_decision)
    if trade_oos_decision.get("trade_level_oos_validation_passed") is not True:
        blockers.append("harlf_trade_level_oos_validation_not_passed")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_harlf_readiness_review",
        "status": "blocked" if blockers else "research_ready",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "policy": "research_only_harlf_readiness_no_weight_change",
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2507.18560.pdf",
            "title": "HARLF: Hierarchical Reinforcement Learning and Lightweight LLM-Driven Sentiment Integration for Financial Portfolio Optimization",
            "arxiv": "2507.18560v1",
            "date_in_pdf": "2025-07-24",
            "imported_concepts": [
                "separate_market_metrics_and_sentiment_branches",
                "hierarchical_aggregation_readiness",
                "market_only_vs_sentiment_only_vs_super_agent_ablation",
                "lightweight_financial_sentiment_before_large_llm",
                "no_live_import_without_transaction_cost_and_stress_testing",
            ],
            "not_imported": [
                "stable_baselines3_live_allocator",
                "harlf_super_agent_live_weights",
                "google_news_scraping_as_live_dependency",
                "paper_roi_26pct_as_group_a_plus_evidence",
                "monthly_rebalance_live_override",
            ],
        },
        "inputs": {
            "market_sentiment_shadow": str(market_sentiment_path),
            "llm_state_reward_readiness": str(llm_readiness_path),
            "research_shadow_snapshot": str(research_snapshot_path),
            "branch_ablation_shadow": str(branch_ablation_path),
            "meta_agent_shadow": str(meta_agent_path),
            "stress_shadow": str(stress_path),
            "comparison_shadow": str(comparison_path),
            "blend_sweep": str(blend_path),
            "trade_level_oos_validation": str(trade_oos_path),
            "trade_level_oos_validation_etf_mapped": str(trade_oos_etf_mapped_path),
            "sentiment_dir": str(sentiment_dir),
        },
        "component_readiness": {
            "sentiment_inventory": inventory,
            "market_aligned_sentiment_shadow_exists": bool(market_sentiment),
            "llm_state_reward_status": llm_readiness.get("status"),
            "research_shadow_status": research_snapshot.get("status"),
            "research_allow_00631l_add": research_decision.get("allow_00631l_add"),
            "branch_ablation_status": branch_ablation.get("status"),
            "branch_ablation_available": bool(branch_ablation),
            "branch_ablation_ranked_branches": branch_ablation.get("ranked_branches") or [],
            "meta_agent_status": meta_agent.get("status"),
            "meta_agent_metrics": meta_agent.get("meta_agent_metrics") or {},
            "meta_agent_decision": meta_agent.get("decision") or {},
            "stress_status": stress.get("status"),
            "stress_decision": stress.get("decision") or {},
            "stress_scenario_metrics": stress.get("scenario_metrics") or {},
            "comparison_status": comparison.get("status"),
            "comparison_decision": comparison.get("decision") or {},
            "comparison_metrics": comparison.get("metrics") or {},
            "blend_status": blend.get("status"),
            "blend_decision": blend.get("decision") or {},
            "blend_best_viable": blend.get("best_viable_blend"),
            "trade_level_oos_status": trade_oos.get("status"),
            "trade_level_oos_decision": trade_oos.get("decision") or {},
            "trade_level_oos_blocking_reasons": trade_oos.get("blocking_reasons") or [],
            "trade_level_oos_non_tradable_assets": _non_tradable_assets(trade_oos),
            "trade_level_oos_etf_mapped_status": trade_oos_etf_mapped.get("status"),
            "trade_level_oos_etf_mapped_decision": trade_oos_etf_mapped.get("decision") or {},
            "trade_level_oos_etf_mapped_blocking_reasons": trade_oos_etf_mapped.get("blocking_reasons") or [],
            "trade_level_oos_etf_mapped_non_tradable_assets": _non_tradable_assets(trade_oos_etf_mapped),
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "recommendation": {
            "summary": (
                "HARLF is useful as a readiness checklist for cross-modal sentiment/RL hierarchy. "
                "Group A+ now has an asset-level monthly sentiment panel, branch ablation, a "
                "compound defensive hierarchical meta-agent shadow router, and a passing stress "
                "report, latest-strategy comparison, and a HARLF/latest blend sweep. The standalone "
                "HARLF candidate has too much drawdown, and the small HARLF sleeve is blocked from "
                "promotion until trade-level OOS validation passes."
            ),
            "next_shadow_step": (
                "Use the ETF-only drop_2330_renormalize mapping, export latest-strategy historical "
                "target weights, and replay the 8% HARLF / 92% latest blend with execution costs, "
                "lot rounding, turnover caps, and a true OOS window while keeping golden01_0531 fixed."
            ),
        },
        "decision": {
            "harlf_readiness_imported_as_review": True,
            "ready_for_hierarchical_rl_backtest": False,
            "live_harlf_super_agent_allowed": False,
            "live_llm_trading_allowed": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "creates_orders": False,
            "keep_golden1_0531_unchanged": True,
            "promotion_ready": False,
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"harlf_readiness_{stamp}.json"


def write_review(report: dict[str, Any], output: Path, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, report.get("as_of")).write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market-sentiment", default=str(DEFAULT_MARKET_SENTIMENT))
    parser.add_argument("--llm-readiness", default=str(DEFAULT_LLM_READINESS))
    parser.add_argument("--research-snapshot", default=str(DEFAULT_RESEARCH_SNAPSHOT))
    parser.add_argument("--branch-ablation", default=str(DEFAULT_BRANCH_ABLATION))
    parser.add_argument("--meta-agent", default=str(DEFAULT_META_AGENT))
    parser.add_argument("--stress", default=str(DEFAULT_STRESS))
    parser.add_argument("--comparison", default=str(DEFAULT_COMPARISON))
    parser.add_argument("--blend", default=str(DEFAULT_BLEND))
    parser.add_argument("--trade-oos", default=str(DEFAULT_TRADE_OOS))
    parser.add_argument("--trade-oos-etf-mapped", default=str(DEFAULT_TRADE_OOS_ETF_MAPPED))
    parser.add_argument("--sentiment-dir", default=str(DEFAULT_SENTIMENT_DIR))
    parser.add_argument("--as-of", default="2026-08-08")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_review(
        market_sentiment_path=_resolve(args.market_sentiment),
        llm_readiness_path=_resolve(args.llm_readiness),
        research_snapshot_path=_resolve(args.research_snapshot),
        branch_ablation_path=_resolve(args.branch_ablation),
        meta_agent_path=_resolve(args.meta_agent),
        stress_path=_resolve(args.stress),
        comparison_path=_resolve(args.comparison),
        blend_path=_resolve(args.blend),
        trade_oos_path=_resolve(args.trade_oos),
        trade_oos_etf_mapped_path=_resolve(args.trade_oos_etf_mapped),
        sentiment_dir=_resolve(args.sentiment_dir),
        as_of=args.as_of,
    )
    write_review(report, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(
        json.dumps(
            {
                "status": report["status"],
                "blocking_reasons": report["blocking_reasons"],
                "output": str(_resolve(args.output)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
