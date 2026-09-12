from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

from scripts.evaluate.train_group_a_plus_ncf_2330_torch_ptq_shadow import (
    FEATURE_COLUMNS,
    LABEL_COLUMN,
    build_shadow,
)


def _panel(path: Path, rows: int = 160) -> Path:
    rng = np.random.default_rng(7)
    dates = pd.bdate_range("2025-01-02", periods=rows)
    frame = pd.DataFrame({"date": dates})
    signal = np.linspace(-2.0, 2.0, rows) + rng.normal(0.0, 0.6, rows)
    prob = 1.0 / (1.0 + np.exp(-signal))
    labels = (prob + rng.normal(0.0, 0.08, rows) > 0.52).astype(float)
    for i, col in enumerate(FEATURE_COLUMNS):
        frame[col] = np.clip(prob + rng.normal(0.0, 0.05 + i * 0.002, rows), 0.0, 1.0)
    frame[LABEL_COLUMN] = labels
    frame["is_live"] = False
    frame.to_csv(path, index=False)
    return path


def test_torch_ptq_shadow_builds_checkpoint_and_quantized_results(tmp_path: Path) -> None:
    panel = _panel(tmp_path / "panel.csv")
    checkpoint = tmp_path / "shadow.pt"

    payload = build_shadow(
        as_of="2026-08-21",
        panel_path=panel,
        checkpoint_path=checkpoint,
        seed=3,
        epochs=20,
        hidden_dim=8,
    )

    assert checkpoint.exists()
    assert payload["model_framework"] == "torch"
    assert payload["quantization_applicability"]["torch_ptq_applicable"] is True
    assert payload["full_precision_metric"] >= 0.5
    assert set(payload["quantized_results"]) == {"W8A8", "W4_weight_only", "W4A4"}
    assert payload["quantized_results"]["W4A4"]["percentile_sweep_tested"] is True
    assert payload["quantized_results"]["W4A4"]["layerwise_exception_reviewed"] is True
    assert payload["decision"]["target_weight_change_allowed"] is False
    assert payload["decision"]["allow_00631l_add"] is False
    assert payload["decision"]["allow_00632r_open"] is False
