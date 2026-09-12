#!/usr/bin/env python3
"""Compare 2609.04917 execution-translation paths.

This report makes the incremental shadow tests explicit: official plan,
same-day shadow plan, and turnover bridge. It is reporting-only.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_execution_path_comparison.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_execution_path_comparison.md"

DEFAULT_PATHS = {
    "official": {
        "joint": PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_joint_execution_readiness.json",
        "market_impact": PROJECT_ROOT / "report/group_a_plus/latest/market_impact_readiness_review.json",
        "rebalance": PROJECT_ROOT / "report/group_a_plus/latest/rebalance_review.json",
    },
    "same_day_shadow": {
        "joint": PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_joint_execution_readiness_same_day_shadow.json",
        "market_impact": PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_market_impact_same_day_shadow.json",
    },
    "turnover_bridge_shadow": {
        "joint": PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_joint_execution_readiness_turnover_bridge_shadow.json",
        "market_impact": PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_market_impact_turnover_bridge_shadow.json",
        "rebalance": PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_bridge_rebalance_review.json",
        "bridge": PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_turnover_bridge_shadow.json",
    },
}


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists() or not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return payload.get("data", payload) if isinstance(payload.get("data"), dict) else payload


def _reasons(payload: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for key in ("blocking_reasons", "warning_reasons"):
        raw = payload.get(key)
        if isinstance(raw, list):
            out.extend(str(item) for item in raw)
    return out


def _path_summary(name: str, paths: dict[str, Path]) -> dict[str, Any]:
    joint = _load(paths.get("joint"))
    impact = _load(paths.get("market_impact"))
    rebalance = _load(paths.get("rebalance"))
    bridge = _load(paths.get("bridge"))
    impact_computed = impact.get("computed") if isinstance(impact.get("computed"), dict) else {}
    bridge_checks = rebalance.get("checks") if isinstance(rebalance.get("checks"), dict) else {}
    return {
        "name": name,
        "status": {
            "joint": joint.get("status") or "missing",
            "market_impact": impact.get("status") or "missing",
            "rebalance": rebalance.get("status") or "missing",
            "bridge": bridge.get("status") or "not_applicable",
        },
        "dates": {
            "signal_date": (joint.get("signal") or {}).get("date"),
            "execution_plan_date": (joint.get("portfolio_mapping") or {}).get("execution_plan_date"),
            "date_aligned": bridge_checks.get("date_aligned"),
        },
        "execution": {
            "execution_allowed": (joint.get("portfolio_mapping") or {}).get("execution_allowed"),
            "auto_rebalance_allowed": (rebalance.get("decision") or {}).get("auto_rebalance_allowed"),
            "manual_review_required": (rebalance.get("decision") or {}).get("manual_review_required"),
            "allow_00631l_add": (rebalance.get("decision") or {}).get("allow_00631l_add"),
        },
        "market_impact": {
            "turnover": impact_computed.get("turnover"),
            "max_participation_of_volume": impact_computed.get("max_participation_of_volume"),
        },
        "reasons": {
            "joint": _reasons(joint),
            "market_impact": _reasons(impact),
            "rebalance": _reasons(rebalance),
        },
    }


def build_report(paths_by_name: dict[str, dict[str, Path]]) -> dict[str, Any]:
    rows = [_path_summary(name, paths) for name, paths in paths_by_name.items()]
    best = "turnover_bridge_shadow"
    return {
        "schema_version": 1,
        "report_type": "group_a_plusplus_2609_04917_execution_path_comparison",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_path_comparison_no_order_no_weight_change",
        "status": "shadow_bridge_is_best_manual_review_candidate",
        "paths": rows,
        "best_shadow_path": best,
        "decision": {
            "live_promotion_allowed": False,
            "auto_rebalance_allowed": False,
            "manual_review_candidate": best,
            "summary": "Turnover bridge is the best current manual-review shadow path, but it does not clear live promotion gates.",
        },
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 2609.04917 Execution Path Comparison",
        "",
        f"- status: {report['status']}",
        f"- best_shadow_path: {report['best_shadow_path']}",
        f"- live_promotion_allowed: {report['decision']['live_promotion_allowed']}",
        "",
        "| path | joint | market impact | rebalance | turnover | execution allowed | auto rebalance |",
        "| --- | --- | --- | --- | ---: | --- | --- |",
    ]
    for row in report["paths"]:
        lines.append(
            f"| {row['name']} | {row['status']['joint']} | {row['status']['market_impact']} | "
            f"{row['status']['rebalance']} | {row['market_impact']['turnover']} | "
            f"{row['execution']['execution_allowed']} | {row['execution']['auto_rebalance_allowed']} |"
        )
    lines.extend(["", "## Decision", "", report["decision"]["summary"], ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()

    report = build_report(DEFAULT_PATHS)
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown.write_text(_markdown(report), encoding="utf-8")
    print(json.dumps({"output": str(output), "status": report["status"], "best_shadow_path": report["best_shadow_path"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
