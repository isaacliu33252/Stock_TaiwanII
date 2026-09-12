from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd


def _load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "evaluate" / "sweep_group_a_plus_aegis_lite_shadow.py"
    spec = importlib.util.spec_from_file_location("_aegis_lite_sweep", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_variant_grid_includes_vam_sortino_and_combined() -> None:
    module = _load_module()

    names = {row["name"] for row in module._variant_grid()}

    assert "vam_only_126d" in names
    assert "sortino_only_63d_monthly" in names
    assert "vam126_sortino63_monthly" in names


def test_write_markdown_renders_ranked_variants(tmp_path: Path) -> None:
    module = _load_module()
    frame = pd.DataFrame(
        [
            {
                "name": "unit",
                "delta_final_value": 1.0,
                "delta_sortino_ratio": 0.1,
                "delta_sharpe_ratio": 0.2,
                "delta_max_drawdown": 0.0,
                "promotion_ready": False,
            }
        ]
    )
    report = {
        "generated_at": "2026-08-13T00:00:00",
        "inputs": {"window": {"start": "2025-01-02", "end": "2026-08-13"}},
        "policy": "research_only_no_active_weight_change",
        "decision": {"promotion_ready": False},
    }

    out = tmp_path / "sweep.md"
    module._write_markdown(report, frame, out)

    text = out.read_text(encoding="utf-8")
    assert "GroupA+ AEGIS-lite Shadow Sweep" in text
    assert "`unit`" in text


def test_score_penalizes_large_final_value_loss() -> None:
    module = _load_module()
    weak = {
        "delta_sortino_ratio": 0.1,
        "delta_sharpe_ratio": 0.1,
        "delta_max_drawdown": 0.01,
        "delta_final_value": -300_000,
        "baseline_final_value": 1_000_000,
    }
    strong = {
        "delta_sortino_ratio": 0.1,
        "delta_sharpe_ratio": 0.1,
        "delta_max_drawdown": 0.01,
        "delta_final_value": 10_000,
        "baseline_final_value": 1_000_000,
    }

    assert module._score(strong) > module._score(weak)
