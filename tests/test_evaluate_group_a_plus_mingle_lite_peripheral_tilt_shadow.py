from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.evaluate.evaluate_group_a_plus_mingle_lite_peripheral_tilt_shadow import _tilt_weights, write_report


def test_tilt_weights_preserves_cash_and_does_not_open_prohibited_asset() -> None:
    base = {"0050.TW": 0.5, "00631L.TW": 0.1, "00632R.TW": 0.0, "00679B.TWO": 0.0, "cash": 0.4}
    peripheral = pd.Series({"0050.TW": 0.1, "00631L.TW": 0.1, "00632R.TW": 10.0, "00679B.TWO": 0.8})

    tilted = _tilt_weights(base, peripheral, tilt_fraction=0.2, prohibited_assets={"00632R.TW"})

    assert tilted["00632R.TW"] == 0.0
    assert abs(tilted["cash"] - 0.4) < 1e-12
    assert round(sum(tilted.values()), 10) == 1.0
    assert tilted["00679B.TWO"] > 0.0


def test_write_report_writes_latest_markdown_and_history(tmp_path: Path) -> None:
    payload = {
        "report_type": "group_a_plus_mingle_lite_peripheral_tilt_shadow",
        "summaries": [
            {
                "tilt_fraction": 0.1,
                "delta_final_value_sum": 100.0,
                "delta_sharpe_sum": 0.1,
                "delta_max_drawdown_sum": 0.0,
                "positive_final_value_windows": 1,
                "non_worse_drawdown_windows": 1,
            }
        ],
        "best_by_final_value": {"tilt_fraction": 0.1},
        "blocking_reasons": ["research_only_no_live_weight_change"],
        "decision": {"promotion_allowed": False, "allow_00632r_open": False},
    }
    output = tmp_path / "latest" / "tilt.json"
    output_md = tmp_path / "latest" / "tilt.md"
    history = tmp_path / "history"

    write_report(payload, output, output_md, history)

    assert json.loads(output.read_text(encoding="utf-8"))["report_type"] == "group_a_plus_mingle_lite_peripheral_tilt_shadow"
    assert "MINGLE-lite Peripheral Tilt Shadow" in output_md.read_text(encoding="utf-8")
    assert list(history.glob("mingle_lite_peripheral_tilt_shadow_*.json"))
