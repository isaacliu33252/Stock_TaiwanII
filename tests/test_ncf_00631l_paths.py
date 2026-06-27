from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_ncf_00631l_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "misc" / "ncf_00631l.py"
    spec = importlib.util.spec_from_file_location("_test_ncf_00631l", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ncf_00631l_uses_repo_root_for_default_outputs() -> None:
    root = Path(__file__).resolve().parents[1]
    module = _load_ncf_00631l_module()

    assert module.PROJECT_ROOT == root
    assert module.DEFAULT_OUTPUT.parent == root / "results"
