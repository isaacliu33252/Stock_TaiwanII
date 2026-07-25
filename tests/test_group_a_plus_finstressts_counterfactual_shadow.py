from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.evaluate.evaluate_group_a_plus_finstressts_counterfactual_shadow import (
    evaluate_counterfactuals,
    write_report,
)


def test_evaluate_counterfactuals_blocks_live_promotion() -> None:
    dates = pd.date_range("2020-01-01", periods=300, freq="B")
    close = pd.DataFrame(
        {
            "0050.TW": 100.0 * np.cumprod(np.full(len(dates), 1.001)),
            "00631L.TW": 50.0 * np.cumprod(np.full(len(dates), 1.0018)),
        },
        index=dates,
    )

    report = evaluate_counterfactuals(close)

    assert report["report_type"] == "group_a_plus_finstressts_counterfactual_shadow"
    assert report["decision"]["promote_to_live"] is False
    assert report["decision"]["allow_00631l_add"] is False
    assert "heavy_tailed_shocks" in report["scenarios"]


def test_write_report_writes_output_and_latest(tmp_path: Path) -> None:
    output = tmp_path / "result.json"
    latest = tmp_path / "latest.json"
    report = {"report_type": "x", "decision": {"allow_00631l_add": False}}

    write_report(report, output, latest)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert json.loads(latest.read_text(encoding="utf-8")) == report
