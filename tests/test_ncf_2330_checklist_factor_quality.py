from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd

from scripts.evaluate.evaluate_ncf_2330_checklist_factor_quality import (
    _load_2330_close,
    build_factor_frame,
    evaluate_factors,
)
from tests.test_ncf_2330_checklist import _make_fixture


def test_build_factor_frame_excludes_latest_ncf_snapshot_by_default() -> None:
    with tempfile.TemporaryDirectory() as tmp_name:
        db_path, results_dir, project_root = _make_fixture(Path(tmp_name))
        close = _load_2330_close(db_path, "2026-01-01", "2026-07-30")
        dates = pd.DatetimeIndex(close.index[80:100])

        frame = build_factor_frame(
            dates,
            db_path=db_path,
            results_dir=results_dir,
            project_root=project_root,
            mode="daily",
        )

    assert not frame.empty
    assert "technical.signal_score" in frame.columns
    assert "valuation.pe" in frame.columns
    assert not any(col.startswith("ncf_2330.") for col in frame.columns)


def test_evaluate_factors_returns_ic_metrics() -> None:
    with tempfile.TemporaryDirectory() as tmp_name:
        db_path, results_dir, project_root = _make_fixture(Path(tmp_name))
        close = _load_2330_close(db_path, "2026-01-01", "2026-07-30")
        dates = pd.DatetimeIndex(close.index[40:110])
        frame = build_factor_frame(
            dates,
            db_path=db_path,
            results_dir=results_dir,
            project_root=project_root,
            mode="daily",
        )

        result = evaluate_factors(
            frame,
            close,
            horizons=(5, 20),
            mdd_horizon=20,
            mdd_threshold=0.05,
        )

    assert "technical.close_vs_ma20" in result
    assert result["technical.close_vs_ma20"]["usable"] is True
    assert "ic_return_h5" in result["technical.close_vs_ma20"]
    assert "ic_mdd_h20" in result["technical.close_vs_ma20"]
