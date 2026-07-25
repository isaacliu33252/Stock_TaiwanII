#!/usr/bin/env python3
"""Build a manifest for an NCF same-method shadow baseline."""

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


def _path_exists(path: str | Path) -> bool:
    return _resolve(path).exists()


def _focus_passes(drift_audit: dict[str, Any]) -> dict[str, Any]:
    summary = drift_audit.get("column_summary") or {}
    columns = {}
    for column, limit in LIMITS.items():
        info = summary.get(column) or {}
        value = float(info.get("max_abs_delta") or 0.0)
        columns[column] = {
            "max_abs_delta": value,
            "max_abs_delta_date": info.get("max_abs_delta_date"),
            "limit": limit,
            "passes_limit": value <= limit,
        }
    return columns


def _permissions() -> dict[str, bool]:
    return {
        "use_for_shadow_drift_comparison": True,
        "use_for_promotion_gate_baseline": False,
        "promotion_allowed": False,
        "training_allowed": False,
        "target_weight_change_allowed": False,
        "auto_rebalance_allowed": False,
        "model_training_allowed": False,
        "ppo_training_allowed": False,
        "promote_to_live": False,
        "allow_00631l_add": False,
        "allow_00632r_open": False,
        "keep_golden1_0531_unchanged": True,
    }


def build_manifest(
    *,
    original_baseline_panel: str | Path,
    same_method_baseline_panel: str | Path,
    same_method_baseline_signal: str | Path,
    validation_drift_audit: str | Path,
    isolation_report: str | Path,
) -> dict[str, Any]:
    drift = _load_json(validation_drift_audit)
    isolation = _load_json(isolation_report)
    focused = _focus_passes(drift)
    same_method_passes = all(item["passes_limit"] for item in focused.values())
    isolation_ok = bool(
        (isolation.get("conclusion") or {}).get("same_method_no_tabnet_passes_configured_limits") is True
    )
    files_exist = all(
        _path_exists(path)
        for path in [
            original_baseline_panel,
            same_method_baseline_panel,
            same_method_baseline_signal,
            validation_drift_audit,
            isolation_report,
        ]
    )
    valid = bool(files_exist and same_method_passes and isolation_ok)
    return {
        "report_type": "ncf_panel_same_method_baseline_manifest",
        "status": "valid_shadow_baseline" if valid else "blocked",
        "original_baseline_panel": str(_resolve(original_baseline_panel)),
        "same_method_baseline_panel": str(_resolve(same_method_baseline_panel)),
        "same_method_baseline_signal": str(_resolve(same_method_baseline_signal)),
        "validation_drift_audit": str(_resolve(validation_drift_audit)),
        "isolation_report": str(_resolve(isolation_report)),
        "reason": "no-TabNet same-method baseline isolates original TabNet/model-method mismatch",
        "checks": {
            "files_exist": files_exist,
            "same_method_validation_passes_limits": same_method_passes,
            "model_set_isolation_passed": isolation_ok,
            "focused_columns": focused,
        },
        "permissions": _permissions(),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-baseline-panel", required=True)
    parser.add_argument("--same-method-baseline-panel", required=True)
    parser.add_argument("--same-method-baseline-signal", required=True)
    parser.add_argument("--validation-drift-audit", required=True)
    parser.add_argument("--isolation-report", required=True)
    parser.add_argument("--output", default="results/ncf_panel_same_method_baseline_manifest_latest.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = build_manifest(
        original_baseline_panel=args.original_baseline_panel,
        same_method_baseline_panel=args.same_method_baseline_panel,
        same_method_baseline_signal=args.same_method_baseline_signal,
        validation_drift_audit=args.validation_drift_audit,
        isolation_report=args.isolation_report,
    )
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"NCF same-method baseline manifest: {output}")
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "use_for_shadow_drift_comparison": manifest["permissions"]["use_for_shadow_drift_comparison"],
                "use_for_promotion_gate_baseline": manifest["permissions"]["use_for_promotion_gate_baseline"],
                "promotion_allowed": manifest["permissions"]["promotion_allowed"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
