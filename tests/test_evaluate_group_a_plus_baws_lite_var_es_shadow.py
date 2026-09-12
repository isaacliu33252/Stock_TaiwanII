from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd


def _load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "evaluate" / "evaluate_group_a_plus_baws_lite_var_es_shadow.py"
    spec = importlib.util.spec_from_file_location("_baws_lite_shadow", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_quantile_score_is_non_negative() -> None:
    module = _load_module()

    assert module.quantile_score(0.02, 0.03, 0.95) >= 0.0
    assert module.quantile_score(0.05, 0.03, 0.95) >= 0.0


def test_select_baws_window_returns_candidate_window() -> None:
    module = _load_module()
    idx = pd.bdate_range("2025-01-02", periods=180)
    returns = pd.Series(0.001 * np.sin(np.arange(len(idx)) / 5.0), index=idx)
    returns.iloc[90:105] -= 0.025
    losses = -returns

    selected = module.select_baws_window(
        losses,
        pos=150,
        candidate_windows=(20, 40, 80),
        alpha=0.95,
        evaluation_window=30,
        beta=0.90,
        bootstrap_samples=30,
        seed=123,
    )

    assert selected["selected_window"] in {20, 40, 80}
    assert selected["reference_window"] == 20
    assert set(selected["candidate_diagnostics"]) == {"20", "40", "80"}


def test_build_report_is_research_only() -> None:
    module = _load_module()
    idx = pd.bdate_range("2024-01-02", periods=260)
    returns = pd.Series(0.0005 + 0.01 * np.sin(np.arange(len(idx)) / 11.0), index=idx)
    prices = 100.0 * (1.0 + returns).cumprod()
    frame = module.build_forecasts(
        prices.pct_change().dropna(),
        start="2024-06-01",
        candidate_windows=(20, 40, 80),
        alpha=0.95,
        evaluation_window=30,
        beta=0.90,
        bootstrap_samples=20,
        seed=456,
    )
    summary = module._summarize_forecasts(frame, (20, 40, 80), 0.95)

    report = {
        "ticker_summaries": {"0050.TW": summary},
        "aggregate_decision": {
            "changes_latest_strategy": False,
            "changes_golden1_0531": False,
            "creates_orders": False,
        },
    }

    assert not frame.empty
    assert summary["comparison"]["best_fixed_method"] in {"fixed_20", "fixed_40", "fixed_80"}
    assert report["aggregate_decision"]["changes_latest_strategy"] is False
    assert report["aggregate_decision"]["changes_golden1_0531"] is False
    assert report["aggregate_decision"]["creates_orders"] is False
