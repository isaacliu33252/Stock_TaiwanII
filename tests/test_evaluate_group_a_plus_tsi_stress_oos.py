from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.evaluate.evaluate_group_a_plus_tsi_stress_oos import build_oos_report, write_report


def _price_panel() -> pd.DataFrame:
    dates = pd.bdate_range("2026-01-01", periods=140)
    rng = np.random.default_rng(7)
    tickers = ["0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO", "^TWII", "2330.TW"]
    returns = pd.DataFrame(rng.normal(0.0005, 0.006, size=(len(dates), len(tickers))), index=dates, columns=tickers)
    stress = (dates >= pd.Timestamp("2026-03-02")) & (dates <= pd.Timestamp("2026-03-31"))
    common = np.linspace(-0.018, -0.004, int(stress.sum()))
    for idx, ticker in enumerate(tickers):
        returns.loc[stress, ticker] = common * (1.0 + idx * 0.04)
    prices = 100.0 * (1.0 + returns).cumprod()
    return prices


def test_tsi_stress_oos_report_is_research_only() -> None:
    payload = build_oos_report(
        prices=_price_panel(),
        as_of="2026-07-17",
        start="2026-01-01",
        end="2026-07-17",
        windows=[{"name": "fixture_stress", "start": "2026-03-02", "end": "2026-03-31", "type": "stress_window"}],
        thresholds=(0.80, 0.90),
        horizons=(5,),
        target_tickers=("0050.TW", "00631L.TW"),
        window_days=12,
        min_observations=8,
        primary_threshold=0.80,
    )

    assert payload["report_type"] == "group_a_plus_tsi_stress_oos"
    assert payload["status"] == "research_only"
    assert payload["decision"]["promotion_allowed"] is False
    assert payload["decision"]["target_weight_change_allowed"] is False
    assert payload["decision"]["keep_golden1_0531_unchanged"] is True
    assert payload["threshold_summaries"][0]["status"] == "available"
    assert payload["threshold_summaries"][0]["alert_days"] > 0
    assert payload["windows"][0]["status"] == "available"


def test_write_report_writes_latest_markdown_and_history(tmp_path: Path) -> None:
    payload = {
        "report_type": "group_a_plus_tsi_stress_oos",
        "status": "research_only",
        "as_of": "2026-07-17",
        "actual_data_start": "2026-01-01",
        "actual_data_end": "2026-07-17",
        "policy": "research_only_tsi_stress_oos_no_weight_change",
        "method": {"primary_threshold": 0.9},
        "threshold_summaries": [
            {
                "threshold": 0.9,
                "alert_days": 3,
                "stress_window_alert_rate": 0.5,
                "non_window_alert_rate": 0.1,
            }
        ],
        "decision": {"promotion_allowed": False, "target_weight_change_allowed": False},
    }
    output = tmp_path / "latest" / "tsi_stress_oos.json"
    output_md = tmp_path / "latest" / "tsi_stress_oos.md"
    history = tmp_path / "history"

    write_report(payload, output, output_md, history)

    assert json.loads(output.read_text(encoding="utf-8"))["report_type"] == "group_a_plus_tsi_stress_oos"
    assert "Threshold Sweep" in output_md.read_text(encoding="utf-8")
    assert (history / "tsi_stress_oos_20260717.json").exists()
