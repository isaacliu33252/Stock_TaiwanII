from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_ncf_0050_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "misc" / "ncf_0050.py"
    spec = importlib.util.spec_from_file_location("_test_ncf_0050", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ncf_0050_uses_repo_root_and_0050_defaults() -> None:
    root = Path(__file__).resolve().parents[1]
    module = _load_ncf_0050_module()

    assert module.PROJECT_ROOT == root
    assert module.TICKER == "0050.TW"
    assert module.DEFAULT_OUTPUT.parent == root / "results"
    assert module.DEFAULT_OUTPUT.name.startswith("ncf_0050_")
