"""Environment and artifact health checks for GroupA+ daily operations."""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from group_a_plus.governance.latest import resolve_ncf_00631l_panel_path
from group_a_plus.paths import PROJECT_ROOT


DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "report/group_a_plus/latest/strategy_env_health.json"

REQUIRED_FILES = {
    "strategy_manifest": "report/group_a_plus/latest/strategy.json",
    "live_signal": "report/group_a_plus/latest/live_signal.json",
    "watchlist_config": "config/group_a_plus_watchlist.json",
}

# Fallback only, matching resolve_ncf_00631l_panel_path's default -- see
# build_strategy_env_health for how the live panel/json paths are resolved.
FALLBACK_NCF_00631L_PANEL = "results/ncf_00631l_panel_latest_20260630.csv"

REQUIRED_DIRS = {
    "results": "results",
    "latest_report": "report/group_a_plus/latest",
    "news": "news",
}

OPTIONAL_ENV = {
    "MINIMAX_API_KEY": "MiniMax commentary provider",
    "ANTHROPIC_API_KEY": "Anthropic commentary provider",
    "NCF_EXTERNAL_ALLOW_DOWNLOAD": "Allow NCF external feature downloads",
}


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return value[:4] + "***" + value[-4:]


def _file_check(root: Path, label: str, rel_path: str) -> dict[str, Any]:
    path = root / rel_path
    exists = path.exists()
    return {
        "label": label,
        "path": str(path),
        "exists": exists,
        "size_bytes": int(path.stat().st_size) if exists and path.is_file() else None,
        "status": "ok" if exists else "missing",
    }


def _dir_check(root: Path, label: str, rel_path: str) -> dict[str, Any]:
    path = root / rel_path
    exists = path.exists() and path.is_dir()
    writable = os.access(path, os.W_OK) if exists else False
    status = "ok" if exists and writable else ("not_writable" if exists else "missing")
    return {
        "label": label,
        "path": str(path),
        "exists": exists,
        "writable": writable,
        "status": status,
    }


def build_strategy_env_health(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    """Build a compact preflight report for scheduled strategy runs."""

    root = root.resolve()
    # Fable audit (2026-07-08, #4): these two used to be hardcoded to a fixed
    # snapshot filename (independently of ops_health.py's already-fixed
    # resolver), so this preflight check kept watching a stale file after
    # strategy.json moved on. The json output shares the panel csv's date
    # stamp (run_ncf_daily_pipeline.py writes both from the same `stamp`).
    panel_path = resolve_ncf_00631l_panel_path(root, fallback=FALLBACK_NCF_00631L_PANEL)
    ncf_json_path = panel_path.replace("_panel_latest_", "_latest_").replace(".csv", ".json")
    file_checks = [_file_check(root, label, rel_path) for label, rel_path in REQUIRED_FILES.items()]
    file_checks.append(_file_check(root, "ncf_panel_00631l", panel_path))
    file_checks.append(_file_check(root, "ncf_00631l", ncf_json_path))
    dir_checks = [_dir_check(root, label, rel_path) for label, rel_path in REQUIRED_DIRS.items()]
    venv_python = root / ".venv/bin/python"
    python_status = {
        "current_executable": sys.executable,
        "venv_python": str(venv_python),
        "venv_python_exists": venv_python.exists(),
        "running_inside_project_venv": Path(sys.executable).resolve() == venv_python.resolve() if venv_python.exists() else False,
    }
    env_checks = {
        key: {
            "description": description,
            "present": bool(os.environ.get(key)),
            "masked_value": _mask(os.environ.get(key, "")),
        }
        for key, description in OPTIONAL_ENV.items()
    }

    missing_files = [item["label"] for item in file_checks if item["status"] != "ok"]
    bad_dirs = [item["label"] for item in dir_checks if item["status"] != "ok"]
    warnings: list[str] = []
    if not python_status["venv_python_exists"]:
        warnings.append("project_venv_missing")
    elif not python_status["running_inside_project_venv"]:
        warnings.append("not_running_inside_project_venv")

    status = "error" if missing_files or bad_dirs else ("warning" if warnings else "ok")
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "root": str(root),
        "status": status,
        "missing_files": missing_files,
        "bad_dirs": bad_dirs,
        "warnings": warnings,
        "python": python_status,
        "files": file_checks,
        "directories": dir_checks,
        "optional_env": env_checks,
    }
