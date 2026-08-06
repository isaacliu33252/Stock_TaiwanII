"""Append-only point-in-time archive for production-sensitive JSON artifacts.

Writes one file per (artifact, as-of date, generated_at, content hash) pair
-- **never overwritten**. This is the specific property the golden1_0531 and
execution_plan overwrite incidents needed and didn't have: a later pipeline
run should become an *additional* point-in-time file, not a replacement of
the only surviving "latest" payload.

This module only writes/reads plain JSON files. It does not touch any
`report/group_a_plus/latest/*` pointer file, and nothing currently reads from
this store in the live decision path -- this is additive recovery/audit
infrastructure, not a live routing mechanism.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from os import PathLike
from pathlib import Path
from typing import Any, TypeAlias

import pandas as pd

from group_a_plus.core.signal_contract import TargetWeightSignal
from group_a_plus.paths import PROJECT_ROOT

DEFAULT_SNAPSHOT_ROOT = PROJECT_ROOT / "results" / "ncf_snapshots"
DEFAULT_ARTIFACT_SNAPSHOT_ROOT = PROJECT_ROOT / "results" / "point_in_time_artifacts"

PathInput: TypeAlias = str | PathLike[str] | Path
SignalDate: TypeAlias = str | pd.Timestamp


def _snapshot_dir(signal_asof: pd.Timestamp, root: PathInput) -> Path:
    root = Path(root)
    return root / f"{signal_asof.year:04d}" / f"{signal_asof.month:02d}" / f"{signal_asof.day:02d}"


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip()).strip("._")
    if not slug:
        raise ValueError("artifact name must not be blank")
    return slug


def _json_hash(payload: Any) -> str:
    import hashlib

    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _timestamp(value: str | pd.Timestamp | datetime) -> pd.Timestamp:
    return pd.Timestamp(value)


def _artifact_snapshot_dir(artifact_name: str, artifact_asof: SignalDate, root: PathInput) -> Path:
    asof = _timestamp(artifact_asof)
    return Path(root) / _safe_slug(artifact_name) / f"{asof.year:04d}" / f"{asof.month:02d}" / f"{asof.day:02d}"


def _artifact_snapshot_filename(artifact_name: str, generated_at: str | pd.Timestamp | datetime, payload_hash: str) -> str:
    stamp = _timestamp(generated_at).strftime("%Y%m%dT%H%M%S")
    return f"{_safe_slug(artifact_name)}_{stamp}_{payload_hash[:12]}.json"


def write_json_artifact_snapshot(
    artifact_name: str,
    payload: Any,
    *,
    artifact_asof: SignalDate,
    generated_at: str | pd.Timestamp | datetime | None = None,
    root: PathInput = DEFAULT_ARTIFACT_SNAPSHOT_ROOT,
) -> Path:
    """Write any JSON-serializable artifact to an append-only PIT archive.

    Idempotent for identical content with the same generated_at/hash; a later
    rerun with different content or generated_at creates a distinct file.
    """
    generated = _timestamp(generated_at or datetime.now())
    payload_hash = _json_hash(payload)
    directory = _artifact_snapshot_dir(artifact_name, artifact_asof, root)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / _artifact_snapshot_filename(artifact_name, generated, payload_hash)
    if not path.exists():
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def archive_json_file(
    path: PathInput,
    *,
    artifact_name: str | None = None,
    artifact_asof: SignalDate,
    generated_at: str | pd.Timestamp | datetime | None = None,
    root: PathInput = DEFAULT_ARTIFACT_SNAPSHOT_ROOT,
) -> Path:
    """Archive an existing JSON file without mutating the source file.

    Use this for protected legacy artifacts such as golden1 release payloads:
    the live pipeline still must not write those files, but a human can archive
    the current bytes into PIT storage before/after audits.
    """
    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    return write_json_artifact_snapshot(
        artifact_name or source.stem,
        payload,
        artifact_asof=artifact_asof,
        generated_at=generated_at,
        root=root,
    )


def list_json_artifact_snapshots(
    artifact_name: str,
    artifact_asof: SignalDate,
    root: PathInput = DEFAULT_ARTIFACT_SNAPSHOT_ROOT,
) -> list[Path]:
    directory = _artifact_snapshot_dir(artifact_name, artifact_asof, root)
    if not directory.exists():
        return []
    return sorted(directory.glob("*.json"))


def read_json_artifact_snapshot(path: PathInput) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _snapshot_filename(signal: TargetWeightSignal) -> str:
    # generated_at (not just signal_asof) makes the filename unique across
    # same-day reruns -- two runs for the same signal_asof produce two
    # files, not one overwritten file.
    stamp = signal.generated_at.strftime("%Y%m%dT%H%M%S")
    return f"{signal.strategy_id}_{stamp}_{signal.data_snapshot_hash[:12]}.json"


def write_snapshot(signal: TargetWeightSignal, root: PathInput = DEFAULT_SNAPSHOT_ROOT) -> Path:
    """Write `signal` as a new, uniquely-named JSON file. Never overwrites
    an existing snapshot -- if the exact same (strategy_id, generated_at,
    hash) combination is written twice, the second write is a no-op
    returning the existing path, since the content would be identical.
    """
    directory = _snapshot_dir(signal.signal_asof, root)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / _snapshot_filename(signal)
    if not path.exists():
        path.write_text(json.dumps(signal.to_json_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return path


def read_snapshot(path: PathInput) -> TargetWeightSignal:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return TargetWeightSignal.from_json_dict(payload)


def list_snapshots_for_date(signal_asof: SignalDate, root: PathInput = DEFAULT_SNAPSHOT_ROOT) -> list[Path]:
    """All snapshot files for a given `signal_asof` date, oldest first.
    Multiple results for the same date is not an error -- it means the
    pipeline ran more than once for that date (a rerun, a backfill, or a
    genuine model/panel change); compare their `data_snapshot_hash` to see
    whether the signal actually changed between runs.
    """
    directory = _snapshot_dir(pd.Timestamp(signal_asof), root)
    if not directory.exists():
        return []
    return sorted(directory.glob("*.json"))


def latest_snapshot_for_date(signal_asof: SignalDate, root: PathInput = DEFAULT_SNAPSHOT_ROOT) -> TargetWeightSignal | None:
    paths = list_snapshots_for_date(signal_asof, root)
    if not paths:
        return None
    return read_snapshot(paths[-1])
