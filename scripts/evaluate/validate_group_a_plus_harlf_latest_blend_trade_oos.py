#!/usr/bin/env python3
"""Trade-level OOS validation readiness for the HARLF/latest blend.

The monthly HARLF/latest blend can improve return without worsening drawdown,
but promotion requires trade-level evidence. This validator checks whether the
candidate has enough executable target-weight history to run that validation.
It is intentionally conservative and creates no orders.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BLEND = PROJECT_ROOT / "report/group_a_plus/latest/harlf_latest_blend_sweep.json"
DEFAULT_BRANCH = PROJECT_ROOT / "report/group_a_plus/latest/harlf_branch_ablation_shadow.json"
DEFAULT_META = PROJECT_ROOT / "report/group_a_plus/latest/harlf_compound_defensive_meta_agent_shadow.json"
DEFAULT_COMPARISON = PROJECT_ROOT / "report/group_a_plus/latest/harlf_compound_vs_latest_strategy_comparison.json"
DEFAULT_MAPPED_SHADOW = PROJECT_ROOT / "report/group_a_plus/latest/harlf_etf_mapped_shadow.json"
DEFAULT_LATEST_TARGET_WEIGHTS = PROJECT_ROOT / "report/group_a_plus/latest/latest_strategy_historical_target_weights.json"
DEFAULT_TRADE_REPLAY = PROJECT_ROOT / "report/group_a_plus/latest/harlf_latest_blend_trade_replay.json"
DEFAULT_TEMPORAL_OOS = PROJECT_ROOT / "report/group_a_plus/latest/harlf_blend_temporal_oos_validation.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/harlf_latest_blend_trade_oos_validation.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/harlf_latest_blend_trade_oos_validation/history"
GROUP_A_PLUS_TRADABLE = {"0050", "00631L", "00632R", "00679B", "cash"}


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _selected_branch_weights(branch_report: dict[str, Any], meta_report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = branch_report.get("branch_returns") or []
    lookup = {
        (str(row.get("month")), str(row.get("branch"))): dict(row.get("weights") or {})
        for row in rows
    }
    out: list[dict[str, Any]] = []
    for decision in meta_report.get("monthly_decisions") or []:
        month = str(decision.get("month"))
        branch = str(decision.get("selected_branch"))
        weights = lookup.get((month, branch), {})
        out.append({"month": month, "selected_branch": branch, "weights": weights})
    return out


def _turnover(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prev: dict[str, float] | None = None
    out: list[dict[str, Any]] = []
    for row in rows:
        weights = {str(k): float(v or 0.0) for k, v in (row.get("weights") or {}).items()}
        if prev is None:
            turnover = None
        else:
            keys = set(prev) | set(weights)
            turnover = 0.5 * sum(abs(weights.get(key, 0.0) - prev.get(key, 0.0)) for key in keys)
        out.append({**row, "turnover": turnover})
        prev = weights
    return out


def build_validation(
    *,
    blend_report: dict[str, Any],
    branch_report: dict[str, Any],
    meta_report: dict[str, Any],
    comparison_report: dict[str, Any],
    latest_target_weights_report: dict[str, Any] | None = None,
    trade_replay_report: dict[str, Any] | None = None,
    temporal_oos_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    blend_decision = blend_report.get("decision") or {}
    best = blend_report.get("best_viable_blend") or {}
    harlf_weight = best.get("harlf_weight")
    latest_weight = best.get("latest_weight")
    if blend_decision.get("found_blend_ready_for_latest_strategy_review") is not True:
        blockers.append("missing_viable_harlf_latest_blend")
    if harlf_weight is None or latest_weight is None:
        blockers.append("missing_blend_weights")

    selected = _selected_branch_weights(branch_report, meta_report)
    selected_with_turnover = _turnover(selected)
    used_assets = sorted(
        {
            str(asset)
            for row in selected
            for asset, weight in (row.get("weights") or {}).items()
            if float(weight or 0.0) > 1e-12
        }
    )
    non_tradable = sorted(set(used_assets) - GROUP_A_PLUS_TRADABLE)
    if non_tradable:
        blockers.append("harlf_uses_assets_outside_group_a_plus_tradable_universe")
    if not selected:
        blockers.append("missing_harlf_selected_branch_weight_history")
    if any(not row.get("weights") for row in selected):
        blockers.append("missing_selected_branch_weights_for_some_months")

    comparison_decision = comparison_report.get("decision") or {}
    if comparison_decision.get("changes_latest_strategy") is True:
        warnings.append("comparison_unexpectedly_changes_latest_strategy")
    if comparison_decision.get("changes_golden01_0531") is True:
        warnings.append("comparison_unexpectedly_changes_golden01_0531")

    latest_target_weights_report = latest_target_weights_report or {}
    latest_trade_weight_history_available = (
        latest_target_weights_report.get("decision", {}).get("historical_target_weight_series_available") is True
    )
    if not latest_trade_weight_history_available:
        blockers.append("missing_latest_strategy_historical_target_weight_series")
    trade_replay_report = trade_replay_report or {}
    trade_replay_available = (
        trade_replay_report.get("decision", {}).get("trade_level_execution_cost_replay_available") is True
    )
    if not trade_replay_available:
        blockers.append("missing_trade_level_execution_cost_replay_for_blend")
    temporal_oos_report = temporal_oos_report or {}
    oos_window_available = temporal_oos_report.get("decision", {}).get("oos_window_available") is True
    temporal_oos_passed = temporal_oos_report.get("decision", {}).get("temporal_oos_passed") is True
    if not oos_window_available:
        blockers.append("missing_oos_window_beyond_blend_selection_window")
    elif not temporal_oos_passed:
        blockers.append("harlf_temporal_oos_validation_not_passed")

    turnovers = [row["turnover"] for row in selected_with_turnover if row.get("turnover") is not None]
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_harlf_latest_blend_trade_oos_validation",
        "status": "blocked" if blockers else "available",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_trade_oos_validation_no_weight_change",
        "candidate": {
            "harlf_weight": harlf_weight,
            "latest_weight": latest_weight,
            "blend_ready_for_latest_strategy_review": blend_decision.get("found_blend_ready_for_latest_strategy_review"),
        },
        "tradability": {
            "group_a_plus_tradable_universe": sorted(GROUP_A_PLUS_TRADABLE),
            "harlf_used_assets": used_assets,
            "non_tradable_assets": non_tradable,
        },
        "trade_history_readiness": {
            "harlf_selected_branch_weight_months": len(selected),
            "latest_strategy_historical_target_weight_series_available": latest_trade_weight_history_available,
            "latest_strategy_target_weight_rows": latest_target_weights_report.get("row_count"),
            "latest_strategy_target_weight_window": latest_target_weights_report.get("date_window") or {},
            "trade_level_execution_cost_replay_available": trade_replay_available,
            "trade_replay_window": trade_replay_report.get("window") or {},
            "trade_replay_metrics": trade_replay_report.get("metrics") or {},
            "trade_replay_cost_summary": trade_replay_report.get("cost_summary") or {},
            "temporal_oos_window_available": oos_window_available,
            "temporal_oos_passed": temporal_oos_passed,
            "temporal_oos_blocking_reasons": temporal_oos_report.get("blocking_reasons") or [],
            "temporal_oos_train_best_viable_blend": temporal_oos_report.get("train_best_viable_blend"),
            "temporal_oos_holdout_window": temporal_oos_report.get("holdout_window") or {},
            "mean_harlf_branch_turnover": None if not turnovers else sum(turnovers) / len(turnovers),
            "max_harlf_branch_turnover": None if not turnovers else max(turnovers),
            "selected_branch_weight_preview": selected_with_turnover[:20],
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "decision": {
            "creates_orders": False,
            "changes_golden01_0531": False,
            "changes_latest_strategy": False,
            "trade_level_oos_validation_passed": False,
            "promotion_ready": False,
        },
        "next_required_work": _next_required_work(blockers),
    }


def branch_report_from_mapped_shadow(mapped_shadow: dict[str, Any], mode: str) -> dict[str, Any]:
    variant = (mapped_shadow.get("variants") or {}).get(mode) or {}
    return {
        "status": mapped_shadow.get("status"),
        "report_type": "group_a_plus_harlf_branch_ablation_shadow_from_etf_mapped_shadow",
        "mapping_mode": mode,
        "branch_returns": variant.get("branch_returns") or [],
    }


def _next_required_work(blockers: list[str]) -> list[str]:
    items: list[str] = []
    blocker_set = set(blockers)
    if "harlf_uses_assets_outside_group_a_plus_tradable_universe" in blocker_set:
        items.append("Map or remove non-ETF asset 2330 from HARLF branch weights before Group A+ execution.")
    if "missing_latest_strategy_historical_target_weight_series" in blocker_set:
        items.append("Export historical latest-strategy target weights, not only portfolio_value.")
    if "missing_trade_level_execution_cost_replay_for_blend" in blocker_set:
        items.append("Replay monthly blend rebalances with commissions, slippage, tax, lot rounding, and turnover caps.")
    if "missing_oos_window_beyond_blend_selection_window" in blocker_set:
        items.append("Validate on an OOS window not used to choose the 8% HARLF blend.")
    if "harlf_temporal_oos_validation_not_passed" in blocker_set:
        items.append("Do not promote; redesign the HARLF sleeve because temporal OOS failed the train-selection gate.")
    return items


def _write(report: dict[str, Any], output: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d")
        (history_dir / f"harlf_latest_blend_trade_oos_validation_{stamp}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blend", default=str(DEFAULT_BLEND))
    parser.add_argument("--branch", default=str(DEFAULT_BRANCH))
    parser.add_argument("--meta", default=str(DEFAULT_META))
    parser.add_argument("--comparison", default=str(DEFAULT_COMPARISON))
    parser.add_argument("--latest-target-weights", default=str(DEFAULT_LATEST_TARGET_WEIGHTS))
    parser.add_argument("--trade-replay", default=str(DEFAULT_TRADE_REPLAY))
    parser.add_argument("--temporal-oos", default=str(DEFAULT_TEMPORAL_OOS))
    parser.add_argument("--mapped-shadow", default="")
    parser.add_argument("--mapped-mode", default="")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    branch_report = _load_json(_resolve(args.branch))
    mapped_shadow_path = str(args.mapped_shadow).strip()
    mapped_mode = str(args.mapped_mode).strip()
    if mapped_shadow_path and mapped_mode:
        branch_report = branch_report_from_mapped_shadow(_load_json(_resolve(mapped_shadow_path)), mapped_mode)
    report = build_validation(
        blend_report=_load_json(_resolve(args.blend)),
        branch_report=branch_report,
        meta_report=_load_json(_resolve(args.meta)),
        comparison_report=_load_json(_resolve(args.comparison)),
        latest_target_weights_report=_load_json(_resolve(args.latest_target_weights)),
        trade_replay_report=_load_json(_resolve(args.trade_replay)),
        temporal_oos_report=_load_json(_resolve(args.temporal_oos)),
    )
    report["inputs"] = {
        "blend": str(_resolve(args.blend)),
        "branch": str(_resolve(args.branch)),
        "meta": str(_resolve(args.meta)),
        "comparison": str(_resolve(args.comparison)),
        "latest_target_weights": str(_resolve(args.latest_target_weights)),
        "trade_replay": str(_resolve(args.trade_replay)),
        "temporal_oos": str(_resolve(args.temporal_oos)),
        "mapped_shadow": str(_resolve(mapped_shadow_path)) if mapped_shadow_path else None,
        "mapped_mode": mapped_mode or None,
    }
    _write(report, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(
        json.dumps(
            {
                "status": report["status"],
                "blocking_reasons": report.get("blocking_reasons"),
                "decision": report.get("decision"),
                "output": str(_resolve(args.output)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
