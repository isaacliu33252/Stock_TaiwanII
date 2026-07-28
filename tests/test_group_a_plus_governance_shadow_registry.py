from __future__ import annotations

import importlib
from pathlib import Path

from group_a_plus.governance.shadow_registry import SHADOW_MODULE_REGISTRY


INTEGRATIONS_DIR = Path(__file__).resolve().parents[1] / "group_a_plus" / "integrations"


def _discovered_shadow_module_names() -> set[str]:
    return {path.stem for path in INTEGRATIONS_DIR.glob("*shadow*.py")}


def test_registry_covers_every_shadow_module_on_disk() -> None:
    discovered = _discovered_shadow_module_names()
    registered = set(SHADOW_MODULE_REGISTRY)
    missing = discovered - registered
    assert not missing, (
        f"New shadow module(s) added under group_a_plus/integrations/ without a "
        f"group_a_plus.governance.shadow_registry entry: {sorted(missing)}. "
        "Add a review_trigger describing when this module should be revisited."
    )


def test_registry_has_no_stale_entries_for_deleted_modules() -> None:
    discovered = _discovered_shadow_module_names()
    registered = set(SHADOW_MODULE_REGISTRY)
    stale = registered - discovered
    assert not stale, f"shadow_registry entries reference deleted files: {sorted(stale)}"


def test_registry_entries_import_and_have_a_review_trigger() -> None:
    for name, entry in SHADOW_MODULE_REGISTRY.items():
        module_path = entry["module"]
        importlib.import_module(module_path)
        assert entry["review_trigger"].strip(), f"{name} has an empty review_trigger"
