from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "evaluate" / "sweep_stock_rnn_relative_window_shadow.py"
    spec = importlib.util.spec_from_file_location("_test_stock_rnn_sweep", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_int_list() -> None:
    module = _load_module()

    assert module._parse_int_list("10, 20,30") == [10, 20, 30]


def test_parse_feature_sets_rejects_unknown() -> None:
    module = _load_module()

    with pytest.raises(ValueError, match="Unsupported"):
        module._parse_feature_sets("close,bad")
