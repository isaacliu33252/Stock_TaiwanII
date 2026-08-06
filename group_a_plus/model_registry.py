"""Model registry helpers for checkpoint metadata and lineage tracking."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from group_a_plus.paths import PROJECT_ROOT

DEFAULT_MODEL_REGISTRY = PROJECT_ROOT / "models" / "MODEL_REGISTRY.json"
REQUIRED_MODEL_FIELDS = {
    "model_id",
    "status",
    "role",
    "model_path",
    "sha256",
    "size_bytes",
    "modified_at",
    "training",
    "evaluation",
    "lineage",
    "metadata_status",
}


def _resolve(path: str | Path, *, project_root: Path = PROJECT_ROOT) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    return candidate


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_to_project(path: str | Path, *, project_root: Path = PROJECT_ROOT) -> str:
    resolved = _resolve(path, project_root=project_root)
    try:
        return resolved.relative_to(project_root).as_posix()
    except ValueError:
        return resolved.as_posix()


def build_checkpoint_metadata(path: str | Path, *, project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    resolved = _resolve(path, project_root=project_root)
    stat = resolved.stat()
    return {
        "model_path": relative_to_project(resolved, project_root=project_root),
        "sha256": file_sha256(resolved),
        "size_bytes": int(stat.st_size),
        "modified_at": stat.st_mtime_ns,
    }


def load_model_registry(path: str | Path = DEFAULT_MODEL_REGISTRY) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_model_card(card: dict[str, Any], *, project_root: Path = PROJECT_ROOT) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_MODEL_FIELDS - set(card))
    errors.extend(f"missing_field:{field}" for field in missing)
    if missing:
        return errors

    model_path = _resolve(str(card["model_path"]), project_root=project_root)
    if not model_path.exists():
        errors.append(f"model_path_missing:{card['model_path']}")
        return errors

    expected_size = int(card["size_bytes"])
    actual_size = int(model_path.stat().st_size)
    if actual_size != expected_size:
        errors.append(f"size_mismatch:{card['model_id']}:{expected_size}!={actual_size}")

    expected_sha = str(card["sha256"])
    actual_sha = file_sha256(model_path)
    if actual_sha != expected_sha:
        errors.append(f"sha256_mismatch:{card['model_id']}")

    for section in ("training", "evaluation", "lineage"):
        if not isinstance(card.get(section), dict):
            errors.append(f"{section}_not_object:{card['model_id']}")

    metadata_status = str(card.get("metadata_status"))
    if metadata_status not in {"complete", "partial", "stub"}:
        errors.append(f"invalid_metadata_status:{card['model_id']}:{metadata_status}")
    return errors


def validate_model_registry(registry: dict[str, Any], *, project_root: Path = PROJECT_ROOT) -> list[str]:
    errors: list[str] = []
    if registry.get("schema_version") != 1:
        errors.append("schema_version_must_be_1")
    models = registry.get("models")
    if not isinstance(models, list):
        return errors + ["models_not_list"]

    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for card in models:
        if not isinstance(card, dict):
            errors.append("model_card_not_object")
            continue
        model_id = str(card.get("model_id", ""))
        model_path = str(card.get("model_path", ""))
        if model_id in seen_ids:
            errors.append(f"duplicate_model_id:{model_id}")
        if model_path in seen_paths:
            errors.append(f"duplicate_model_path:{model_path}")
        seen_ids.add(model_id)
        seen_paths.add(model_path)
        errors.extend(validate_model_card(card, project_root=project_root))
    return errors

