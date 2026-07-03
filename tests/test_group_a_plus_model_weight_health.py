from __future__ import annotations

from pathlib import Path

import pytest

from group_a_plus.operations.model_weight_health import (
    analyze_state_dict,
    analyze_weight_matrix,
    build_model_weight_health,
)


torch = pytest.importorskip("torch")


def test_analyze_weight_matrix_reports_core_metrics() -> None:
    weight = torch.tensor(
        [
            [1.0, 0.2, 0.0],
            [0.1, 0.9, 0.3],
            [0.0, 0.4, 0.8],
        ]
    )

    row = analyze_weight_matrix("layer.weight", weight)

    assert row is not None
    assert row["name"] == "layer.weight"
    assert row["stable_rank"] is not None
    assert row["log_norm"] is not None
    assert row["rank"] == 3


def test_analyze_state_dict_skips_biases_and_returns_shadow_status() -> None:
    state = {
        "net.0.weight": torch.eye(4),
        "net.0.bias": torch.zeros(4),
        "net.2.weight": torch.ones(3, 4),
    }

    report = analyze_state_dict(state)

    assert report["status"] in {"ok", "warning"}
    assert report["layer_count"] >= 1
    assert "summary" in report


def test_build_model_weight_health_handles_missing_model(tmp_path: Path) -> None:
    report = build_model_weight_health(tmp_path / "missing.zip")

    assert report["status"] == "unavailable"
    assert report["reason"] == "model_path_not_found"
    assert report["active_allocation_impact"] == "none"
