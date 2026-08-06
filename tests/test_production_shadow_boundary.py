from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BOUNDARY_DOC = PROJECT_ROOT / "docs" / "PRODUCTION_SHADOW_BOUNDARY.md"
ACTIVE_MANIFEST = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "strategy.json"
RESERVED_SHADOW_PREFIXES = ("research/", "experiments/", "handoff/", "archive/")


def _walk_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        out: list[str] = []
        for item in value.values():
            out.extend(_walk_strings(item))
        return out
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(_walk_strings(item))
        return out
    return []


def _looks_like_repo_path(value: str) -> bool:
    text = value.strip().replace("\\", "/")
    return "/" in text or text.endswith((".json", ".csv", ".md", ".py", ".xlsx", ".db"))


def test_boundary_document_and_reserved_directories_exist() -> None:
    assert BOUNDARY_DOC.exists()
    for dirname in ("research", "experiments", "handoff", "archive"):
        assert (PROJECT_ROOT / dirname / "README.md").exists()


def test_active_strategy_manifest_does_not_read_shadow_only_directories() -> None:
    manifest = json.loads(ACTIVE_MANIFEST.read_text(encoding="utf-8"))
    active = manifest["active_strategy"]
    path_like_strings = [
        item.strip().replace("\\", "/")
        for item in _walk_strings(active)
        if _looks_like_repo_path(item)
    ]

    violations = [
        item
        for item in path_like_strings
        if item.startswith(RESERVED_SHADOW_PREFIXES)
    ]

    assert violations == []

