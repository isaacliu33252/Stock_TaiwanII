#!/usr/bin/env python3
"""Append and summarize GroupA+ same-method external-sensitivity observations."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRIGGER_LIMITS = {"h20_prob_up": 0.15, "confidence": 0.28}
DIAGNOSTIC_LIMITS = {"ensemble_prob_up": 0.15}
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/external_sensitivity_observation_log.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/external_sensitivity_observation_log.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/external_sensitivity_observation_log/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _column(summary: dict[str, Any], column: str, limit: float, tier: str) -> dict[str, Any]:
    info = summary.get(column) if isinstance(summary.get(column), dict) else {}
    value = float(info.get("max_abs_delta") or 0.0)
    return {
        "tier": tier,
        "max_abs_delta": value,
        "max_abs_delta_date": info.get("max_abs_delta_date"),
        "limit": limit,
        "exceeds_limit": value > limit,
    }


def _build_observation(
    *,
    sensitivity_audit_path: Path,
    same_method_baseline_manifest_path: Path,
    observation_date: str,
) -> dict[str, Any]:
    sensitivity = _load(sensitivity_audit_path)
    manifest = _load(same_method_baseline_manifest_path)
    summary = sensitivity.get("column_summary") if isinstance(sensitivity.get("column_summary"), dict) else {}
    trigger = {
        column: _column(summary, column, limit, "trigger_critical")
        for column, limit in TRIGGER_LIMITS.items()
    }
    diagnostic = {
        column: _column(summary, column, limit, "diagnostic")
        for column, limit in DIAGNOSTIC_LIMITS.items()
    }
    trigger_exceeded = [column for column, item in trigger.items() if item["exceeds_limit"]]
    diagnostic_exceeded = [column for column, item in diagnostic.items() if item["exceeds_limit"]]
    baseline_valid = manifest.get("status") == "valid_shadow_baseline"
    audit_available = bool(sensitivity)
    valid = audit_available and baseline_valid
    stable = valid and not trigger_exceeded
    return {
        "observation_date": observation_date,
        "sensitivity_audit": str(sensitivity_audit_path),
        "same_method_baseline_manifest": str(same_method_baseline_manifest_path),
        "audit_available": audit_available,
        "same_method_baseline_valid": baseline_valid,
        "valid_observation": valid,
        "stable_observation": stable,
        "trigger_critical": trigger,
        "diagnostic": diagnostic,
        "trigger_critical_exceeded": trigger_exceeded,
        "diagnostic_exceeded": diagnostic_exceeded,
    }


def build_log(
    *,
    sensitivity_audit_path: Path,
    same_method_baseline_manifest_path: Path,
    observation_date: str | None = None,
    existing_log_path: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    observation_date = observation_date or date.today().isoformat()
    existing = _load(existing_log_path)
    observations = [
        row
        for row in (existing.get("observations") or [])
        if isinstance(row, dict)
    ]
    new_observation = _build_observation(
        sensitivity_audit_path=sensitivity_audit_path,
        same_method_baseline_manifest_path=same_method_baseline_manifest_path,
        observation_date=observation_date,
    )
    key = (new_observation["observation_date"], new_observation["sensitivity_audit"])
    observations = [
        row
        for row in observations
        if (row.get("observation_date"), row.get("sensitivity_audit")) != key
    ]
    observations.append(new_observation)
    observations.sort(key=lambda row: (str(row.get("observation_date") or ""), str(row.get("sensitivity_audit") or "")))
    valid_count = sum(1 for row in observations if row.get("valid_observation") is True)
    stable_count = sum(1 for row in observations if row.get("stable_observation") is True)
    latest = observations[-1] if observations else {}
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_external_sensitivity_observation_log",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "diagnostic_only_no_strategy_change_no_weight_change",
        "active_allocation_impact": "none",
        "summary": {
            "observation_count": len(observations),
            "valid_observation_count": valid_count,
            "stable_observation_count": stable_count,
            "latest_observation_date": latest.get("observation_date"),
            "latest_trigger_critical_exceeded": latest.get("trigger_critical_exceeded") or [],
        },
        "observations": observations,
        "decision": {
            "creates_orders": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "training_allowed": False,
            "model_training_allowed": False,
            "ppo_training_allowed": False,
            "promote_to_live": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def _markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    lines = [
        "# GroupA+ External Sensitivity Observation Log",
        "",
        f"- Observations: `{summary.get('observation_count')}`",
        f"- Valid observations: `{summary.get('valid_observation_count')}`",
        f"- Stable observations: `{summary.get('stable_observation_count')}`",
        f"- Latest trigger-critical exceeded: `{summary.get('latest_trigger_critical_exceeded')}`",
        "",
        "## Decision Boundary",
        "",
        f"- Creates orders: `{report['decision']['creates_orders']}`",
        f"- Target weight change allowed: `{report['decision']['target_weight_change_allowed']}`",
        f"- Auto rebalance allowed: `{report['decision']['auto_rebalance_allowed']}`",
        f"- Golden1_0531 unchanged: `{report['decision']['keep_golden1_0531_unchanged']}`",
    ]
    return "\n".join(lines) + "\n"


def _history_path(history_dir: Path) -> Path:
    return history_dir / f"external_sensitivity_observation_log_{datetime.now().strftime('%Y%m%d')}.json"


def write_outputs(
    report: dict[str, Any],
    *,
    output: Path = DEFAULT_OUTPUT,
    output_md: Path = DEFAULT_OUTPUT_MD,
    history_dir: Path | None = DEFAULT_HISTORY_DIR,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(_markdown(report), encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sensitivity-audit", required=True)
    parser.add_argument("--same-method-baseline-manifest", required=True)
    parser.add_argument("--observation-date", default=None)
    parser.add_argument("--existing-log", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    report = build_log(
        sensitivity_audit_path=_resolve(args.sensitivity_audit),
        same_method_baseline_manifest_path=_resolve(args.same_method_baseline_manifest),
        observation_date=args.observation_date,
        existing_log_path=_resolve(args.existing_log),
    )
    write_outputs(
        report,
        output=_resolve(args.output),
        output_md=_resolve(args.output_md),
        history_dir=None if args.no_history else _resolve(args.history_dir),
    )
    print(f"External sensitivity observation log: {_resolve(args.output)}")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
