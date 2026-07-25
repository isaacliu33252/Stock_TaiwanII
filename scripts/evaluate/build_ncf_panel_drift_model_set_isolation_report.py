#!/usr/bin/env python3
"""Summarize model-set isolation drift comparisons for NCF panels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LIMITS = {"ensemble_prob_up": 0.15, "h20_prob_up": 0.15, "confidence": 0.28}


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(_resolve(path).read_text(encoding="utf-8"))


def _focus(audit: dict[str, Any]) -> dict[str, Any]:
    summary = audit.get("column_summary") or {}
    focused = {}
    for column, limit in LIMITS.items():
        info = summary.get(column) or {}
        max_abs = float(info.get("max_abs_delta") or 0.0)
        focused[column] = {
            "max_abs_delta": max_abs,
            "max_abs_delta_date": info.get("max_abs_delta_date"),
            "limit": limit,
            "passes_limit": max_abs <= limit,
        }
    return focused


def build_report(
    *,
    original_vs_today: str | Path,
    original_vs_no_tabnet: str | Path,
    no_tabnet_vs_today: str | Path,
) -> dict[str, Any]:
    original_today = _load_json(original_vs_today)
    model_set = _load_json(original_vs_no_tabnet)
    same_method = _load_json(no_tabnet_vs_today)
    same_method_focus = _focus(same_method)
    same_method_passes = all(item["passes_limit"] for item in same_method_focus.values())
    return {
        "report_type": "ncf_panel_drift_model_set_isolation_report",
        "inputs": {
            "original_vs_today": str(_resolve(original_vs_today)),
            "original_vs_no_tabnet": str(_resolve(original_vs_no_tabnet)),
            "no_tabnet_vs_today": str(_resolve(no_tabnet_vs_today)),
        },
        "status": "model_set_mismatch_isolated" if same_method_passes else "same_method_drift_still_blocks",
        "focused_columns": {
            "original_vs_today": _focus(original_today),
            "original_vs_no_tabnet": _focus(model_set),
            "no_tabnet_vs_today": same_method_focus,
        },
        "conclusion": {
            "same_method_no_tabnet_passes_configured_limits": same_method_passes,
            "model_set_or_baseline_method_mismatch_explains_primary_blocker": same_method_passes,
            "promotion_allowed": False,
            "training_allowed": False,
            "target_weight_change_allowed": False,
            "recommended_next_action": (
                "Use the no-TabNet same-method baseline as a shadow comparison baseline, "
                "then rerun diagnosis/remediation and keep promotion blocked until deployment/GIFT gates also clear."
            )
            if same_method_passes
            else "Continue diagnosing same-method drift before any gate change.",
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-vs-today", required=True)
    parser.add_argument("--original-vs-no-tabnet", required=True)
    parser.add_argument("--no-tabnet-vs-today", required=True)
    parser.add_argument("--output", default="results/ncf_panel_drift_model_set_isolation_report_latest.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(
        original_vs_today=args.original_vs_today,
        original_vs_no_tabnet=args.original_vs_no_tabnet,
        no_tabnet_vs_today=args.no_tabnet_vs_today,
    )
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"NCF panel drift model-set isolation report: {output}")
    print(json.dumps(report["conclusion"], ensure_ascii=False))


if __name__ == "__main__":
    main()
