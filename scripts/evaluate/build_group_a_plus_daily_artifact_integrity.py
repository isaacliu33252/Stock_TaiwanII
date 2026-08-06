#!/usr/bin/env python3
"""Build a daily integrity report for production-sensitive Group A+ artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus.core.point_in_time_store import (  # noqa: E402
    DEFAULT_ARTIFACT_SNAPSHOT_ROOT,
    list_json_artifact_snapshots,
)


DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "live_signal.json"
DEFAULT_EXECUTION_PLAN = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "execution_plan.json"
DEFAULT_PANEL_REFRESH_RECOMMENDATION = (
    PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "ncf_panel_refresh_recommendation.json"
)
DEFAULT_NCF_DECISION_CALIBRATION = PROJECT_ROOT / "results" / "ncf_decision_calibration_shadow_latest.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "daily_artifact_integrity.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "daily_artifact_integrity.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report" / "group_a_plus" / "daily_artifact_integrity" / "history"
DEFAULT_GOLDEN1_RELEASE_ASOF = "2026-05-31"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _unwrap_standard_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    if payload.get("success") is True and isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def _first_string(payload: dict[str, Any] | None, *keys: str) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return None


def _check(status: str, message: str, **details: Any) -> dict[str, Any]:
    return {"status": status, "message": message, **details}


def _append_issue(checks: list[dict[str, Any]], issue: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    checks.append(issue)
    if issue["status"] == "error":
        errors.append(issue["message"])
    elif issue["status"] == "warning":
        warnings.append(issue["message"])


def _pit_snapshot_check(
    *,
    artifact_name: str,
    artifact_asof: str | None,
    pit_root: Path,
    required: bool,
) -> dict[str, Any]:
    if not artifact_asof:
        return _check(
            "error" if required else "warning",
            f"{artifact_name} PIT snapshot asof is unavailable",
            artifact_name=artifact_name,
            artifact_asof=artifact_asof,
            snapshot_count=0,
            snapshots=[],
        )
    snapshots = list_json_artifact_snapshots(artifact_name, artifact_asof, root=pit_root)
    status = "ok" if snapshots else ("error" if required else "warning")
    message = (
        f"{artifact_name} PIT snapshot available"
        if snapshots
        else f"{artifact_name} PIT snapshot missing for {artifact_asof}"
    )
    return _check(
        status,
        message,
        artifact_name=artifact_name,
        artifact_asof=artifact_asof,
        snapshot_count=len(snapshots),
        snapshots=[str(path) for path in snapshots[-5:]],
    )


def build_daily_artifact_integrity(
    *,
    check_date: str,
    live_signal_path: str | Path = DEFAULT_LIVE_SIGNAL,
    execution_plan_path: str | Path = DEFAULT_EXECUTION_PLAN,
    panel_refresh_recommendation_path: str | Path = DEFAULT_PANEL_REFRESH_RECOMMENDATION,
    ncf_decision_calibration_path: str | Path = DEFAULT_NCF_DECISION_CALIBRATION,
    pit_root: str | Path = DEFAULT_ARTIFACT_SNAPSHOT_ROOT,
    golden1_release_asof: str = DEFAULT_GOLDEN1_RELEASE_ASOF,
) -> dict[str, Any]:
    live_path = _resolve(live_signal_path)
    plan_path = _resolve(execution_plan_path)
    refresh_path = _resolve(panel_refresh_recommendation_path)
    calibration_path = _resolve(ncf_decision_calibration_path)
    pit_root_path = _resolve(pit_root)

    live_signal = _unwrap_standard_payload(_read_json(live_path))
    execution_plan = _unwrap_standard_payload(_read_json(plan_path))
    refresh_recommendation = _unwrap_standard_payload(_read_json(refresh_path))
    calibration = _unwrap_standard_payload(_read_json(calibration_path))

    checks: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []

    live_actual_date = _first_string(live_signal, "actual_data_date", "signal_asof", "as_of")
    plan_actual_date = _first_string(execution_plan, "actual_data_date", "signal_asof", "as_of")

    if live_signal is None:
        _append_issue(checks, _check("error", "live_signal artifact missing", path=str(live_path)), errors, warnings)
    elif not live_actual_date:
        _append_issue(checks, _check("error", "live_signal actual_data_date missing", path=str(live_path)), errors, warnings)
    else:
        _append_issue(
            checks,
            _check("ok", "live_signal artifact available", path=str(live_path), actual_data_date=live_actual_date),
            errors,
            warnings,
        )

    if execution_plan is None:
        _append_issue(
            checks,
            _check("error", "execution_plan artifact missing", path=str(plan_path)),
            errors,
            warnings,
        )
    elif not plan_actual_date:
        _append_issue(
            checks,
            _check("error", "execution_plan actual_data_date missing", path=str(plan_path)),
            errors,
            warnings,
        )
    elif live_actual_date and plan_actual_date != live_actual_date:
        _append_issue(
            checks,
            _check(
                "error",
                "execution_plan actual_data_date does not match live_signal",
                path=str(plan_path),
                live_signal_actual_data_date=live_actual_date,
                execution_plan_actual_data_date=plan_actual_date,
            ),
            errors,
            warnings,
        )
    else:
        _append_issue(
            checks,
            _check("ok", "execution_plan artifact date aligned", path=str(plan_path), actual_data_date=plan_actual_date),
            errors,
            warnings,
        )

    _append_issue(
        checks,
        _pit_snapshot_check(
            artifact_name="execution_plan",
            artifact_asof=plan_actual_date,
            pit_root=pit_root_path,
            required=True,
        ),
        errors,
        warnings,
    )
    _append_issue(
        checks,
        _pit_snapshot_check(
            artifact_name="golden1_0531_release",
            artifact_asof=golden1_release_asof,
            pit_root=pit_root_path,
            required=True,
        ),
        errors,
        warnings,
    )

    recommendation = None
    if isinstance(refresh_recommendation, dict):
        summary = refresh_recommendation.get("summary") if isinstance(refresh_recommendation.get("summary"), dict) else {}
        recommendation = summary.get("recommendation")
    if refresh_recommendation is None:
        _append_issue(
            checks,
            _check("warning", "NCF panel refresh recommendation artifact missing", path=str(refresh_path)),
            errors,
            warnings,
        )
    elif not recommendation:
        _append_issue(
            checks,
            _check("warning", "NCF panel refresh recommendation missing summary.recommendation", path=str(refresh_path)),
            errors,
            warnings,
        )
    else:
        _append_issue(
            checks,
            _check(
                "ok",
                "NCF panel refresh recommendation available",
                path=str(refresh_path),
                recommendation=str(recommendation),
            ),
            errors,
            warnings,
        )

    readiness = None
    if isinstance(calibration, dict):
        readiness = calibration.get("calibration_pair_readiness")
    if calibration is None:
        _append_issue(
            checks,
            _check("warning", "NCF decision calibration artifact missing", path=str(calibration_path)),
            errors,
            warnings,
        )
    elif not isinstance(readiness, dict):
        _append_issue(
            checks,
            _check("warning", "NCF decision calibration readiness block missing", path=str(calibration_path)),
            errors,
            warnings,
        )
    elif readiness.get("status") != "available":
        _append_issue(
            checks,
            _check(
                "warning",
                "NCF decision calibration realized labels are not fully available",
                path=str(calibration_path),
                readiness_status=readiness.get("status"),
            ),
            errors,
            warnings,
        )
    else:
        _append_issue(
            checks,
            _check(
                "ok",
                "NCF decision calibration realized labels available",
                path=str(calibration_path),
                readiness_status=readiness.get("status"),
                realized_label_rows=readiness.get("realized_label_rows"),
                total_pairs=readiness.get("total_pairs"),
            ),
            errors,
            warnings,
        )

    status = "error" if errors else ("warning" if warnings else "ok")
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_daily_artifact_integrity",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "check_date": check_date,
        "status": status,
        "policy": "diagnostic_only_no_strategy_change_no_weight_change",
        "inputs": {
            "live_signal": str(live_path),
            "execution_plan": str(plan_path),
            "panel_refresh_recommendation": str(refresh_path),
            "ncf_decision_calibration": str(calibration_path),
            "pit_root": str(pit_root_path),
        },
        "dates": {
            "live_signal_actual_data_date": live_actual_date,
            "execution_plan_actual_data_date": plan_actual_date,
        },
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
        "decision": {
            "target_weight_change_allowed": False,
            "creates_orders": False,
            "recommended_action": "investigate_artifact_integrity" if errors else "record_and_continue",
        },
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Group A+ Daily Artifact Integrity",
        "",
        f"- Status: `{report['status']}`",
        f"- Check date: `{report['check_date']}`",
        f"- Policy: `{report['policy']}`",
        "",
        "## Checks",
        "",
    ]
    for check in report.get("checks") or []:
        lines.append(f"- `{check['status']}` {check['message']}")
    if report.get("errors"):
        lines.extend(["", "## Errors", ""])
        lines.extend(f"- {item}" for item in report["errors"])
    if report.get("warnings"):
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {item}" for item in report["warnings"])
    lines.extend(
        [
            "",
            "## Decision Boundary",
            "",
            f"- Target weight change allowed: `{report['decision']['target_weight_change_allowed']}`",
            f"- Creates orders: `{report['decision']['creates_orders']}`",
        ]
    )
    return "\n".join(lines) + "\n"


def _history_path(history_dir: Path, check_date: str) -> Path:
    stamp = check_date.replace("-", "")
    return history_dir / f"group_a_plus_daily_artifact_integrity_{stamp}.json"


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
        _history_path(history_dir, str(report["check_date"])).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-date", required=True)
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--execution-plan", default=str(DEFAULT_EXECUTION_PLAN))
    parser.add_argument("--panel-refresh-recommendation", default=str(DEFAULT_PANEL_REFRESH_RECOMMENDATION))
    parser.add_argument("--ncf-decision-calibration", default=str(DEFAULT_NCF_DECISION_CALIBRATION))
    parser.add_argument("--pit-root", default=str(DEFAULT_ARTIFACT_SNAPSHOT_ROOT))
    parser.add_argument("--golden1-release-asof", default=DEFAULT_GOLDEN1_RELEASE_ASOF)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    report = build_daily_artifact_integrity(
        check_date=args.check_date,
        live_signal_path=args.live_signal,
        execution_plan_path=args.execution_plan,
        panel_refresh_recommendation_path=args.panel_refresh_recommendation,
        ncf_decision_calibration_path=args.ncf_decision_calibration,
        pit_root=args.pit_root,
        golden1_release_asof=args.golden1_release_asof,
    )
    write_outputs(
        report,
        output=_resolve(args.output),
        output_md=_resolve(args.output_md),
        history_dir=None if args.no_history else _resolve(args.history_dir),
    )
    print(f"Group A+ daily artifact integrity: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": report["status"],
                "errors": report["errors"],
                "warnings": report["warnings"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
