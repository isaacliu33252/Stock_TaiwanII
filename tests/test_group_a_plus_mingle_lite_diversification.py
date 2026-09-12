from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from group_a_plus.integrations.mingle_lite_diversification import build_mingle_lite_frame, summarize_target_diversification
from scripts.evaluate.build_group_a_plus_mingle_lite_readiness_review import write_report


def test_mingle_lite_frame_builds_exposure_graph_and_peripheral_scores() -> None:
    idx = pd.bdate_range("2026-01-02", periods=80)
    base = np.linspace(100.0, 110.0, len(idx))
    prices = pd.DataFrame(
        {
            "a": base,
            "b": base * 1.01 + np.sin(np.arange(len(idx))) * 0.1,
            "c": 100.0 + np.cos(np.arange(len(idx)) / 5.0),
            "d": 105.0 + np.sin(np.arange(len(idx)) / 7.0),
        },
        index=idx,
    )

    frame = build_mingle_lite_frame(prices, factor_count=2)

    assert frame.exposures.shape == (4, 2)
    assert frame.graph.shape == (4, 4)
    assert frame.peripheral_score.sum() == 1.0
    assert frame.observations == 79


def test_mingle_lite_frame_handles_asynchronous_market_missing_values() -> None:
    idx = pd.bdate_range("2026-01-02", periods=80)
    prices = pd.DataFrame(
        {
            "tw": np.linspace(100.0, 110.0, len(idx)),
            "us": np.linspace(90.0, 120.0, len(idx)),
            "bond": np.linspace(30.0, 31.0, len(idx)),
        },
        index=idx,
    )
    prices.loc[idx[::5], "us"] = np.nan
    prices.loc[idx[::7], "bond"] = np.nan

    frame = build_mingle_lite_frame(prices, factor_count=2)

    assert frame.graph.shape == (3, 3)
    assert frame.observations > 50


def test_summarize_target_diversification_uses_only_available_assets() -> None:
    idx = pd.bdate_range("2026-01-02", periods=80)
    prices = pd.DataFrame(
        {
            "0050.TW": np.linspace(100.0, 110.0, len(idx)),
            "00631L.TW": np.linspace(90.0, 120.0, len(idx)),
            "00632R.TW": np.linspace(80.0, 75.0, len(idx)),
            "00679B.TWO": np.linspace(30.0, 31.0, len(idx)),
        },
        index=idx,
    )
    frame = build_mingle_lite_frame(prices, factor_count=2)

    summary = summarize_target_diversification(frame, {"0050.TW": 0.5, "00631L.TW": 0.1, "cash": 0.4})

    assert summary["risky_weight_sum"] == 0.6
    assert summary["normalized_risky_weights"]["0050.TW"] > summary["normalized_risky_weights"]["00631L.TW"]
    assert summary["exposure_similarity_concentration"] is not None


def test_write_mingle_lite_report_writes_latest_markdown_and_history(tmp_path: Path) -> None:
    payload = {
        "report_type": "group_a_plus_mingle_lite_readiness_review",
        "method": "mingle_lite_pca_exposure_similarity_graph_not_full_admm",
        "available_tickers": ["a", "b", "c"],
        "representation": {
            "observations": 60,
            "sample_condition_number": 100.0,
            "factor_condition_number": 10.0,
            "condition_improvement_ratio": 10.0,
        },
        "target_diversification": {
            "risky_weight_sum": 0.6,
            "exposure_similarity_concentration": 0.5,
            "weighted_graph_degree": 1.0,
            "peripheral_alignment": 0.3,
            "normalized_risky_weights": {"a": 1.0},
        },
        "blocking_reasons": ["research_only_no_live_weight_change"],
        "decision": {"promotion_allowed": False},
    }
    output = tmp_path / "latest" / "mingle.json"
    output_md = tmp_path / "latest" / "mingle.md"
    history = tmp_path / "history"

    write_report(payload, output, output_md, history)

    assert json.loads(output.read_text(encoding="utf-8"))["report_type"] == "group_a_plus_mingle_lite_readiness_review"
    assert "MINGLE-lite Readiness Review" in output_md.read_text(encoding="utf-8")
    assert list(history.glob("mingle_lite_readiness_review_*.json"))
