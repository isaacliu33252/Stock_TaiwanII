from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.evaluate.sweep_group_a_plus_ncf_2330_torch_ptq_robustness import build_sweep
from scripts.evaluate.train_group_a_plus_ncf_2330_torch_ptq_shadow import FEATURE_COLUMNS, LABEL_COLUMN


def _write_panel(path: Path, rows: int = 150) -> Path:
    rng = np.random.default_rng(11)
    dates = pd.bdate_range("2025-01-02", periods=rows)
    latent = np.linspace(-1.5, 1.5, rows) + rng.normal(0.0, 0.7, rows)
    prob = 1.0 / (1.0 + np.exp(-latent))
    frame = pd.DataFrame({"date": dates})
    for i, col in enumerate(FEATURE_COLUMNS):
        frame[col] = np.clip(prob + rng.normal(0.0, 0.04 + i * 0.001, rows), 0.0, 1.0)
    frame[LABEL_COLUMN] = (prob + rng.normal(0.0, 0.1, rows) > 0.50).astype(float)
    frame["is_live"] = False
    frame.to_csv(path, index=False)
    return path


def _write_original(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "horizons": {
                    "1": {"classification": {"val_auc": 0.7}},
                    "5": {"classification": {"val_auc": 0.65}},
                    "20": {"classification": {"val_auc": 0.6}},
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def test_ptq_robustness_sweep_blocks_live_even_when_research_runs(tmp_path: Path) -> None:
    payload = build_sweep(
        as_of="2026-08-21",
        panel_path=_write_panel(tmp_path / "panel.csv"),
        original_ncf_path=_write_original(tmp_path / "original.json"),
        seeds=[1, 2],
        n_windows=2,
        train_rows=70,
        calib_rows=25,
        test_rows=25,
        epochs=12,
        hidden_dim=8,
    )

    assert payload["decision"]["research_robustness_complete"] is True
    assert payload["decision"]["quantized_inference_allowed"] is False
    assert payload["decision"]["target_weight_change_allowed"] is False
    assert payload["aggregate"]["fp32"]["mean_auc"] >= 0.5
    assert "test_rows_below_live_minimum" in payload["decision"]["live_blocking_reasons"]
    assert "production_quantized_inference_path_not_integrated_or_latency_validated" in payload["decision"][
        "live_blocking_reasons"
    ]
