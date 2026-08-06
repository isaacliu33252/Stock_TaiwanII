"""Canonical output paths and report envelope helpers for GroupA+ artifacts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from group_a_plus.paths import PROJECT_ROOT

OUTPUTS_ROOT = PROJECT_ROOT / "outputs"
GROUP_A_PLUS_OUTPUTS = OUTPUTS_ROOT / "group_a_plus"
LATEST_OUTPUTS = GROUP_A_PLUS_OUTPUTS / "latest"
HISTORY_OUTPUTS = GROUP_A_PLUS_OUTPUTS / "history"
SHADOW_OUTPUTS = GROUP_A_PLUS_OUTPUTS / "shadow"
LEGACY_REPORT_ROOT = PROJECT_ROOT / "report"
LEGACY_RESULTS_ROOT = PROJECT_ROOT / "results"

ArtifactKind = Literal["backtest", "signal", "validation", "dashboard", "portfolio", "research", "pipeline"]
RunMode = Literal["production", "shadow", "research"]


def output_path(
    artifact_name: str,
    *,
    kind: ArtifactKind,
    run_mode: RunMode = "production",
    latest: bool = False,
    suffix: str = ".json",
    outputs_root: Path = OUTPUTS_ROOT,
) -> Path:
    """Return the canonical path for a new output artifact.

    Existing legacy paths are intentionally not redirected here. Callers should
    adopt this helper when writing new outputs or when migrating one script at a
    time with compatibility copies left in place.
    """
    safe_name = artifact_name.strip().replace("/", "_").replace("\\", "_")
    if not safe_name:
        raise ValueError("artifact_name must not be blank")
    if not suffix.startswith("."):
        raise ValueError("suffix must start with '.'")

    base = outputs_root / "group_a_plus"
    if latest:
        return base / "latest" / f"{safe_name}{suffix}"
    return base / run_mode / kind / f"{safe_name}{suffix}"


def report_envelope(
    *,
    artifact_name: str,
    kind: ArtifactKind,
    run_mode: RunMode,
    payload: dict[str, Any],
    schema_version: int = 1,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Wrap a report payload in the common output schema."""
    if schema_version < 1:
        raise ValueError("schema_version must be >= 1")
    return {
        "schema_version": schema_version,
        "artifact_name": artifact_name,
        "artifact_kind": kind,
        "run_mode": run_mode,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }


def write_json_report(
    path: Path,
    *,
    artifact_name: str,
    kind: ArtifactKind,
    run_mode: RunMode,
    payload: dict[str, Any],
    schema_version: int = 1,
    generated_at: str | None = None,
) -> Path:
    """Write a canonical enveloped JSON report and return its path."""
    envelope = report_envelope(
        artifact_name=artifact_name,
        kind=kind,
        run_mode=run_mode,
        payload=payload,
        schema_version=schema_version,
        generated_at=generated_at,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
