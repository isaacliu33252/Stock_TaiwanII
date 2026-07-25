from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.evaluate.evaluate_group_a_plus_finstressts_baseline_compare_shadow import (
    evaluate_baselines,
    write_report,
)


def test_evaluate_baselines_stays_research_only() -> None:
    dates = pd.date_range("2020-01-01", periods=320, freq="B")
    close = pd.DataFrame(
        {
            "0050.TW": 100.0 * np.cumprod(np.full(len(dates), 1.0005)),
            "00631L.TW": 50.0 * np.cumprod(np.full(len(dates), 1.0008)),
        },
        index=dates,
    )

    report = evaluate_baselines(close)

    assert report["report_type"] == "group_a_plus_finstressts_baseline_compare_shadow"
    assert report["decision"]["promote_to_live"] is False
    assert report["decision"]["allow_00631l_add"] is False
    assert "combined_vol_trend_gate" in report["wins_vs_no_00631l"]


def test_write_report_writes_output_and_latest(tmp_path: Path) -> None:
    output = tmp_path / "result.json"
    latest = tmp_path / "latest.json"
    report = {"report_type": "x", "decision": {"allow_00631l_add": False}}

    write_report(report, output, latest)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert json.loads(latest.read_text(encoding="utf-8")) == report
