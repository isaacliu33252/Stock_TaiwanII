#!/usr/bin/env python3
"""Summarize churn/cost risk for 2608.15841-inspired auxiliary-head shadows."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY_LIFT = PROJECT_ROOT / "report/group_a_plus/latest/2608_15841_existing_aux_heads_policy_lift_shadow.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2608_15841_auxiliary_churn_shadow.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2608_15841_auxiliary_churn_shadow.md"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _variant_summary(name: str, item: dict[str, Any], *, max_turnover_to_initial: float) -> dict[str, Any]:
    delta = item.get("delta_vs_baseline") if isinstance(item.get("delta_vs_baseline"), dict) else {}
    sim = item.get("simulation") if isinstance(item.get("simulation"), dict) else {}
    behavior = item.get("score_behavior") if isinstance(item.get("score_behavior"), dict) else {}
    initial_value = _float(item.get("initial_value"), 1_000_000.0)
    turnover = _float(sim.get("turnover_value"))
    transaction_cost = _float(sim.get("transaction_cost"))
    turnover_to_initial = turnover / max(initial_value, 1e-12)
    cost_pass = (
        _float(delta.get("final_value")) >= 0.0
        and _float(delta.get("sharpe_ratio")) >= 0.0
        and _float(delta.get("max_drawdown")) >= 0.0
        and turnover_to_initial <= max_turnover_to_initial
    )
    return {
        "variant": name,
        "delta_final_value": delta.get("final_value"),
        "delta_sharpe_ratio": delta.get("sharpe_ratio"),
        "delta_max_drawdown": delta.get("max_drawdown"),
        "transaction_cost": sim.get("transaction_cost"),
        "turnover_value": sim.get("turnover_value"),
        "turnover_to_initial": turnover_to_initial,
        "rebalance_count": sim.get("rebalance_count"),
        "days_score_gt_0": item.get("days_score_gt_0"),
        "golden1_days_score_gt_0": behavior.get("golden1_days_score_gt_0"),
        "golden1_score_change_days": behavior.get("golden1_score_change_days"),
        "golden1_mean_abs_score_change": behavior.get("golden1_mean_abs_score_change"),
        "missed_upside_proxy_days": behavior.get("missed_upside_proxy_days"),
        "mean_forward_gain_h20_when_active": behavior.get("mean_forward_gain_h20_when_active"),
        "mean_forward_gain_h20_when_inactive": behavior.get("mean_forward_gain_h20_when_inactive"),
        "cost_turnover_pass": cost_pass,
    }


def build_report(policy_lift: dict[str, Any], *, max_turnover_to_initial: float = 1.5) -> dict[str, Any]:
    results = policy_lift.get("results") if isinstance(policy_lift.get("results"), dict) else {}
    variants = [
        _variant_summary(name, item, max_turnover_to_initial=max_turnover_to_initial)
        for name, item in results.items()
        if isinstance(item, dict)
    ]
    passed = bool(variants) and all(bool(item["cost_turnover_pass"]) for item in variants)
    blockers: list[str] = []
    if not variants:
        blockers.append("policy_lift_shadow_missing_variants")
    if any(_float(item["delta_final_value"]) < 0.0 for item in variants):
        blockers.append("negative_delta_final_value_after_costs")
    if any(_float(item["delta_sharpe_ratio"]) < 0.0 for item in variants):
        blockers.append("negative_delta_sharpe_ratio")
    if any(_float(item["delta_max_drawdown"]) < 0.0 for item in variants):
        blockers.append("worse_max_drawdown")
    if any(_float(item["turnover_to_initial"]) > max_turnover_to_initial for item in variants):
        blockers.append("turnover_above_limit")
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2608_15841_auxiliary_churn_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": {
            "id": "2608.15841",
            "transferable_use": "transaction_cost_turnover_policy_impact_gate",
        },
        "policy": "research_only_no_weight_change",
        "changes_latest_strategy": False,
        "changes_golden1_0531": False,
        "changes_golden2_0830": False,
        "window": policy_lift.get("window"),
        "thresholds": {"max_turnover_to_initial": max_turnover_to_initial},
        "summary": {
            "multi_window_cost_turnover_passed": passed,
            "promotion_allowed": False,
            "decision": "churn_cost_not_cleared" if not passed else "shadow_passed_but_not_promoted",
            "blockers": blockers,
        },
        "baseline_metrics": policy_lift.get("baseline_metrics"),
        "variants": variants,
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# 2608.15841 Auxiliary Churn Shadow",
        "",
        f"- Policy: `{report['policy']}`",
        f"- Decision: `{report['summary']['decision']}`",
        f"- Promotion allowed: `{report['summary']['promotion_allowed']}`",
        f"- Cost/turnover passed: `{report['summary']['multi_window_cost_turnover_passed']}`",
        f"- Blockers: `{', '.join(report['summary']['blockers']) or 'none'}`",
        "",
        "| variant | dFV | dSharpe | dMDD | cost | turnover | rebalances | score>0 | missed-upside days | pass |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report.get("variants", []):
        lines.append(
            f"| `{item['variant']}` | {item.get('delta_final_value')} | {item.get('delta_sharpe_ratio')} | "
            f"{item.get('delta_max_drawdown')} | {item.get('transaction_cost')} | "
            f"{item.get('turnover_value')} | {item.get('rebalance_count')} | "
            f"{item.get('days_score_gt_0')} | {item.get('missed_upside_proxy_days')} | "
            f"`{item.get('cost_turnover_pass')}` |"
        )
    lines.extend(
        [
            "",
            "This is a research-only gate. It audits whether existing auxiliary heads improve realized portfolio outcomes after costs.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy-lift", default=str(DEFAULT_POLICY_LIFT))
    parser.add_argument("--max-turnover-to-initial", type=float, default=1.5)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()

    policy_lift_path = _resolve(args.policy_lift)
    report = build_report(_load_json(policy_lift_path), max_turnover_to_initial=args.max_turnover_to_initial)
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, markdown)
    print(
        f"decision={report['summary']['decision']} "
        f"cost_turnover_passed={report['summary']['multi_window_cost_turnover_passed']}"
    )
    print("blockers=" + ",".join(report["summary"]["blockers"]))
    print(f"Output: {output}")
    print(f"Markdown: {markdown}")


if __name__ == "__main__":
    main()
