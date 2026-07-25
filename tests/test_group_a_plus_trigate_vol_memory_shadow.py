from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.evaluate.evaluate_group_a_plus_trigate_vol_memory_shadow import build_shadow, write_report


def test_build_shadow_is_research_only() -> None:
    dates = pd.date_range("2020-01-01", periods=360, freq="B")
    close = pd.DataFrame(
        {
            "0050.TW": 100.0 * np.cumprod(np.full(len(dates), 1.0004)),
            "00631L.TW": 50.0 * np.cumprod(np.full(len(dates), 1.0007)),
        },
        index=dates,
    )
    volume = pd.DataFrame(
        {
            "0050.TW": np.full(len(dates), 1_000_000.0),
            "00631L.TW": np.full(len(dates), 2_000_000.0),
        },
        index=dates,
    )
    panel = pd.concat({"close": close, "volume": volume}, axis=1)

    report = build_shadow(panel)

    assert report["report_type"] == "group_a_plus_trigate_vol_memory_shadow"
    assert report["decision"]["allow_00631l_add"] is False
    assert report["decision"]["promote_to_live"] is False
    assert "level_gate_active" in report["tri_gate_state"]


def test_write_report_writes_output_and_latest(tmp_path: Path) -> None:
    output = tmp_path / "result.json"
    latest = tmp_path / "latest.json"
    report = {"report_type": "x", "decision": {"allow_00631l_add": False}}

    write_report(report, output, latest)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert json.loads(latest.read_text(encoding="utf-8")) == report
