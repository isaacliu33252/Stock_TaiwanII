"""Read-only operational health report for GroupA+ daily automation.

Inspired by Ajenti's dashboard/plugin health patterns, but intentionally kept
as a JSON report only. This module must not start/stop services, mutate files,
or influence active allocation.
"""

from __future__ import annotations

import argparse
import glob
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from group_a_plus.paths import PROJECT_ROOT
from tw_output_standard import OutputStandardizer, write_standard_output


DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "report/group_a_plus/latest/ops_health.json"

REQUIRED_ARTIFACTS = {
    "strategy_manifest": "report/group_a_plus/latest/strategy.json",
    "live_signal": "report/group_a_plus/latest/live_signal.json",
    "execution_plan": "report/group_a_plus/latest/execution_plan.json",
    "strategy_env_health": "report/group_a_plus/latest/strategy_env_health.json",
    "ncf_00631l_panel": "results/ncf_00631l_panel_latest_20260630.csv",
}

SCHEDULER_FILES = {
    "run_daily_bat": "run_daily.bat",
    "run_fetch_bat": "run_fetch.bat",
    "task_scheduler_xml": "task_scheduler_setup.xml",
}

MODULE_OUTPUT_PATTERNS = {
    "ncf_00631l": "results/ncf_00631l_latest_*.json",
    "ncf_00632r": "results/ncf_00632r_latest_*.json",
    "factor_lens": "results/group_a_plus_factor_lens_*.json",
    "daily_pipeline": "results/ncf_daily_pipeline_*.json",
    "alphagen_lite_feature_pool": "results/alphagen_lite_feature_pool_latest_*.json",
    "alphagen_lite_shadow": "results/alphagen_lite_shadow_latest_*.json",
}


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _path_check(root: Path, label: str, rel_path: str, *, required: bool) -> dict[str, Any]:
    path = root / rel_path
    exists = path.exists()
    return {
        "label": label,
        "path": str(path),
        "relative_path": rel_path,
        "required": required,
        "exists": exists,
        "size_bytes": int(path.stat().st_size) if exists and path.is_file() else None,
        "modified_at": _iso(path.stat().st_mtime) if exists else None,
        "status": "ok" if exists else ("missing" if required else "not_found"),
    }


def _latest_match(root: Path, pattern: str) -> Path | None:
    matches = [Path(p) for p in glob.glob(str(root / pattern))]
    matches = [p for p in matches if p.is_file()]
    return max(matches, key=lambda p: p.stat().st_mtime) if matches else None


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _status_from_warnings(errors: list[str], warnings: list[str]) -> str:
    if errors:
        return "error"
    if warnings:
        return "warning"
    return "ok"


def collect_system_resources(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    disk = shutil.disk_usage(root)
    disk_free_ratio = disk.free / disk.total if disk.total else 0.0

    payload: dict[str, Any] = {
        "disk": {
            "root": str(root),
            "total_bytes": disk.total,
            "used_bytes": disk.used,
            "free_bytes": disk.free,
            "free_ratio": round(float(disk_free_ratio), 4),
            "status_policy": "informational_only",
        }
    }

    try:
        import psutil  # type: ignore

        memory = psutil.virtual_memory()
        memory_available_ratio = memory.available / memory.total if memory.total else 0.0
        if memory_available_ratio < 0.05:
            errors.append("memory_available_below_5pct")
        elif memory_available_ratio < 0.15:
            warnings.append("memory_available_below_15pct")
        payload["cpu"] = {
            "percent": psutil.cpu_percent(interval=0),
            "count": psutil.cpu_count(),
        }
        payload["memory"] = {
            "total_bytes": memory.total,
            "available_bytes": memory.available,
            "used_bytes": memory.total - memory.available,
            "available_ratio": round(float(memory_available_ratio), 4),
        }
    except Exception as exc:  # noqa: BLE001
        warnings.append("psutil_unavailable")
        payload["cpu"] = {"status": "unavailable", "reason": repr(exc)}
        payload["memory"] = {"status": "unavailable", "reason": repr(exc)}

    payload["warnings"] = warnings
    payload["errors"] = errors
    payload["status"] = _status_from_warnings(errors, warnings)
    return payload


def collect_artifact_health(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    required = [
        _path_check(root, label, rel_path, required=True)
        for label, rel_path in REQUIRED_ARTIFACTS.items()
    ]
    scheduler = [
        _path_check(root, label, rel_path, required=False)
        for label, rel_path in SCHEDULER_FILES.items()
    ]
    daily_log = _path_check(root, "daily_log", "logs/daily.log", required=False)
    errors = [item["label"] for item in required if item["status"] != "ok"]
    warnings = [item["label"] for item in scheduler if item["status"] != "ok"]
    if daily_log["status"] != "ok":
        warnings.append("daily_log")
    return {
        "status": _status_from_warnings(errors, warnings),
        "missing_required": errors,
        "missing_optional": warnings,
        "required": required,
        "scheduler_files": scheduler,
        "daily_log": daily_log,
    }


def collect_pipeline_health(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    manifest = _latest_match(root, "results/ncf_daily_pipeline_*.json")
    if manifest is None:
        return {
            "status": "warning",
            "latest_manifest": None,
            "warnings": ["pipeline_manifest_missing"],
            "outputs": {},
            "signals": {},
        }

    payload = _read_json(manifest)
    if payload is None:
        return {
            "status": "error",
            "latest_manifest": str(manifest),
            "latest_manifest_modified_at": _iso(manifest.stat().st_mtime),
            "errors": ["pipeline_manifest_unreadable"],
            "outputs": {},
            "signals": {},
        }

    outputs = payload.get("outputs") or {}
    output_checks = {
        name: _path_check(root, name, str(Path(path)), required=False)
        for name, path in outputs.items()
    }
    missing_outputs = [name for name, item in output_checks.items() if item["status"] != "ok"]
    warnings = list(missing_outputs)
    return {
        "status": _status_from_warnings([], warnings),
        "latest_manifest": str(manifest),
        "latest_manifest_modified_at": _iso(manifest.stat().st_mtime),
        "date_stamp": payload.get("date_stamp"),
        "missing_outputs": missing_outputs,
        "outputs": output_checks,
        "signals": payload.get("signals") or {},
    }


def collect_module_health(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    modules: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    for name, pattern in MODULE_OUTPUT_PATTERNS.items():
        path = _latest_match(root, pattern)
        if path is None:
            modules[name] = {
                "status": "missing",
                "pattern": pattern,
                "latest_path": None,
            }
            warnings.append(name)
            continue
        modules[name] = {
            "status": "ok",
            "pattern": pattern,
            "latest_path": str(path),
            "modified_at": _iso(path.stat().st_mtime),
            "size_bytes": int(path.stat().st_size),
        }

    live_signal = _read_json(root / "report/group_a_plus/latest/live_signal.json")
    tbrain_status = None
    finbert_status = None
    factor_lens_status = None
    if live_signal:
        data = live_signal.get("data") if live_signal.get("success") is True else live_signal
        tbrain_status = (data.get("tbrain_shadow") or {}).get("status")
        finbert_status = (data.get("finbert_sentiment") or {}).get("status")
        factor_lens_status = (data.get("factor_lens_gate") or {}).get("status")
    modules["tbrain_shadow"] = {"status": tbrain_status or "unknown", "source": "live_signal"}
    modules["finbert_sentiment"] = {"status": finbert_status or "unknown", "source": "live_signal"}
    modules["factor_lens_gate"] = {"status": factor_lens_status or "unknown", "source": "live_signal"}

    for name in ("tbrain_shadow", "finbert_sentiment", "factor_lens_gate"):
        if modules[name]["status"] not in {"ok", "available"}:
            warnings.append(name)

    return {
        "status": _status_from_warnings([], warnings),
        "warnings": warnings,
        "modules": modules,
    }


def build_ops_health(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    root = root.resolve()
    system = collect_system_resources(root)
    artifacts = collect_artifact_health(root)
    pipeline = collect_pipeline_health(root)
    modules = collect_module_health(root)
    sections = {
        "system_resources": system,
        "artifact_health": artifacts,
        "pipeline_health": pipeline,
        "module_health": modules,
    }
    errors = [name for name, section in sections.items() if section.get("status") == "error"]
    warnings = [name for name, section in sections.items() if section.get("status") == "warning"]
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_ops_health",
        "generated_at": _utc_now().isoformat().replace("+00:00", "Z"),
        "root": str(root),
        "status": _status_from_warnings(errors, warnings),
        "errors": errors,
        "warnings": warnings,
        "active_allocation_impact": "none",
        "source_inspiration": "Ajenti read-only dashboard/plugin health patterns",
        **sections,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(PROJECT_ROOT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    args = parser.parse_args()

    std = OutputStandardizer("group_a_plus.operations.ops_health")
    try:
        report = build_ops_health(Path(args.root))
        payload = std.success(report)
    except Exception as exc:  # noqa: BLE001
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"Ops health: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
