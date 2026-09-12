#!/usr/bin/env python3
"""Sweep defensive fallback thresholds for the HARLF meta-agent candidate."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.evaluate_group_a_plus_harlf_meta_agent_shadow import build_meta_agent_shadow
from scripts.evaluate.evaluate_group_a_plus_harlf_stress_shadow import build_stress_report

DEFAULT_BRANCH_ABLATION = PROJECT_ROOT / "report/group_a_plus/latest/harlf_branch_ablation_shadow.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/harlf_defensive_meta_agent_param_sweep.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/harlf_defensive_meta_agent_param_sweep/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def build_sweep(
    *,
    branch_report: dict[str, Any],
    thresholds: tuple[float, ...] = (2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0),
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for threshold in thresholds:
        meta = build_meta_agent_shadow(
            branch_report=branch_report,
            defensive_sentiment_score_threshold=threshold,
        )
        stress = build_stress_report(branch_report=branch_report, meta_report=meta)
        meta_metrics = meta.get("meta_agent_metrics") or {}
        meta_decision = meta.get("decision") or {}
        stress_decision = stress.get("decision") or {}
        rows.append(
            {
                "threshold": threshold,
                "net_total_return": meta_metrics.get("total_return"),
                "net_sharpe": meta_metrics.get("annualized_sharpe"),
                "max_drawdown": meta_metrics.get("max_drawdown"),
                "selected_branch_counts": meta.get("selected_branch_counts") or {},
                "beats_equal_weight_total_return": meta_decision.get("beats_equal_weight_total_return"),
                "beats_static_combined_total_return": meta_decision.get("beats_static_combined_total_return"),
                "stress_ready_for_latest_strategy_comparison": stress_decision.get(
                    "latest_strategy_candidate_ready_for_comparison"
                ),
                "weak_market_months_not_worse_than_equal_weight": stress_decision.get(
                    "weak_market_months_not_worse_than_equal_weight"
                ),
                "beats_equal_weight_under_3x_cost": stress_decision.get("beats_equal_weight_under_3x_cost"),
                "sentiment_dropout_to_combined_positive": stress_decision.get(
                    "sentiment_dropout_to_combined_positive"
                ),
            }
        )

    viable = [
        row
        for row in rows
        if row["beats_static_combined_total_return"] is True
        and row["stress_ready_for_latest_strategy_comparison"] is True
    ]
    best = max(viable, key=lambda row: row.get("net_total_return") or -999.0) if viable else None
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_harlf_defensive_meta_agent_param_sweep",
        "status": "available" if rows else "blocked",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_harlf_defensive_sweep_no_weight_change",
        "thresholds": list(thresholds),
        "rows": rows,
        "best_viable_threshold": best,
        "decision": {
            "creates_orders": False,
            "changes_golden01_0531": False,
            "changes_latest_strategy": False,
            "found_threshold_ready_for_latest_strategy_comparison": best is not None,
            "promotion_ready": False,
        },
    }


def _write(report: dict[str, Any], output: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d")
        (history_dir / f"harlf_defensive_meta_agent_param_sweep_{stamp}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--branch-ablation", default=str(DEFAULT_BRANCH_ABLATION))
    parser.add_argument("--thresholds", default="2.0,2.5,3.0,3.5,4.0,4.5,5.0")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    thresholds = tuple(float(part.strip()) for part in args.thresholds.split(",") if part.strip())
    report = build_sweep(branch_report=_load_json(_resolve(args.branch_ablation)), thresholds=thresholds)
    report["inputs"] = {"branch_ablation": str(_resolve(args.branch_ablation))}
    _write(report, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(
        json.dumps(
            {
                "status": report["status"],
                "best_viable_threshold": report.get("best_viable_threshold"),
                "decision": report.get("decision"),
                "output": str(_resolve(args.output)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
