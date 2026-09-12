#!/usr/bin/env python3
"""Build a PPO runtime/compression governance review for GroupA+.

This is intentionally conservative. It does not quantize, retrain, or replace
Last PPO; it only records whether compression work is worth pursuing.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "report/group_a_plus/latest/ppo_runtime_compression_review.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/ppo_runtime_compression_review.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/ppo_runtime_compression_review/history"

MODEL_CANDIDATES = [
    PROJECT_ROOT / "models/portfolio/last_ppo_group_a_100k.zip",
    PROJECT_ROOT / "models/portfolio/last_ppo_group_a_500k.zip",
    PROJECT_ROOT / "models/portfolio/last_ppo_group_a_1000k.zip",
    PROJECT_ROOT / "models/portfolio/group_a_production_2020_2025_100k.zip",
]


def _artifact(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else None,
    }


def build_review(*, as_of: str) -> dict[str, Any]:
    artifacts = [_artifact(path) for path in MODEL_CANDIDATES]
    blockers = [
        "runtime_bottleneck_not_demonstrated",
        "ppo_strategy_quality_not_improved_by_compression",
        "last_ppo_production_model_must_not_be_replaced",
        "prior_step_count_and_hnn_experiments_show_oos_tradeoff_risk",
        "no_latency_baseline_or_quantized_backend_benchmark",
    ]
    warnings = []
    if not any(item["exists"] and "last_ppo_group_a_100k.zip" in item["path"] for item in artifacts):
        warnings.append("last_ppo_group_a_100k_not_found")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_ppo_runtime_compression_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked",
        "policy": "runtime_governance_only_no_training_no_quantization_no_weight_change",
        "artifacts": artifacts,
        "prior_context": [
            "docs/HANDOFF_LAST_PPO_INTRODUCTION_AND_STEP_COUNT_ABLATION_20260814.md",
            "docs/HANDOFF_GROUPA_PLUS_INVERSE_GATE_RETRAINING_SHADOW_20260815.md",
            "group_a_plus/research_semantic_registry.json",
        ],
        "decision": {
            "compression_work_allowed": False,
            "latency_measurement_allowed": True,
            "retraining_allowed": False,
            "replace_last_ppo_allowed": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "recommended_use": "only_revisit_if_runtime_latency_becomes_measured_bottleneck",
        },
        "blocking_reasons": blockers,
        "warning_reasons": warnings,
    }


def _write_md(payload: dict[str, Any], path: Path) -> None:
    lines = [
        "# PPO Runtime/Compression Review",
        "",
        f"- Generated: `{payload['generated_at']}`",
        f"- Status: `{payload['status']}`",
        f"- Policy: `{payload['policy']}`",
        f"- Compression work allowed: `{payload['decision']['compression_work_allowed']}`",
        f"- Target weight change allowed: `{payload['decision']['target_weight_change_allowed']}`",
        "",
        "## Blocking Reasons",
        "",
    ]
    lines.extend(f"- `{reason}`" for reason in payload["blocking_reasons"])
    lines.extend(["", "## Artifacts", ""])
    lines.extend(f"- `{item['path']}` exists=`{item['exists']}` size=`{item['size_bytes']}`" for item in payload["artifacts"])
    lines.extend(
        [
            "",
            "## Decision",
            "",
            "- Do not quantize or replace Last PPO.",
            "- Runtime measurement is allowed only if latency becomes a measured bottleneck.",
            "- No live strategy, target weight, rebalance, or order file was changed.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_review(payload: dict[str, Any], output_json: Path, output_md: Path, history_dir: Path | None) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_md(payload, output_md)
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = str(payload["as_of"]).replace("-", "")
        (history_dir / f"ppo_runtime_compression_review_{stamp}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default=datetime.now().date().isoformat())
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_review(as_of=args.as_of)
    write_review(
        payload,
        Path(args.output_json),
        Path(args.output_md),
        None if args.no_history else Path(args.history_dir),
    )
    print(f"PPO runtime/compression review: {Path(args.output_json)}")
    print(json.dumps({"status": payload["status"], "decision": payload["decision"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
