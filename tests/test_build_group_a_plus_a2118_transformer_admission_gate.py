from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_a2118_transformer_admission_gate import build_gate, write_gate


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_transformer_admission_gate_blocks_tiny_dcc_improvement(tmp_path: Path) -> None:
    stage2 = tmp_path / "stage2.json"
    stage3 = tmp_path / "stage3.json"
    _write(
        stage2,
        {
            "as_of": "2026-08-24",
            "model_comparison": [{"model": "ewma", "window": 120, "rank_ic_mean": 0.600, "qlike_like_semicov": 1.0}],
            "economic_filter_review": [{"pair": "0050.TW_00679B.TWO", "net_filter_value": 0.015, "failed_signal_count": 20}],
        },
    )
    _write(
        stage3,
        {
            "as_of": "2026-08-24",
            "model_comparison": [{"model": "downside_dcc", "window": 60, "rank_ic_mean": 0.604, "qlike_like_semicov": 3.0}],
            "economic_filter_review": [{"pair": "0050.TW_00679B.TWO", "net_filter_value": 0.025, "failed_signal_count": 6}],
        },
    )

    gate = build_gate(stage2_path=stage2, stage3_path=stage3)

    assert gate["status"] == "blocked"
    assert gate["decision"]["admit_transformer_research"] is False
    assert gate["decision"]["target_weight_change_allowed"] is False
    assert "dcc_rank_ic_improvement_not_material" in gate["blocking_reasons"]
    assert "dcc_positive_filter_signal_count_too_small" in gate["blocking_reasons"]
    assert "dcc_qlike_like_loss_worse_than_best_simple" in gate["blocking_reasons"]


def test_transformer_admission_gate_passes_material_dcc_evidence(tmp_path: Path) -> None:
    stage2 = tmp_path / "stage2.json"
    stage3 = tmp_path / "stage3.json"
    _write(
        stage2,
        {
            "as_of": "2026-08-24",
            "model_comparison": [{"model": "ewma", "window": 120, "rank_ic_mean": 0.40, "qlike_like_semicov": 1.2}],
            "economic_filter_review": [{"pair": "0050.TW_00679B.TWO", "net_filter_value": 0.006, "failed_signal_count": 25}],
        },
    )
    _write(
        stage3,
        {
            "as_of": "2026-08-24",
            "model_comparison": [{"model": "downside_dcc", "window": 60, "rank_ic_mean": 0.45, "qlike_like_semicov": 1.0}],
            "economic_filter_review": [{"pair": "0050.TW_00679B.TWO", "net_filter_value": 0.010, "failed_signal_count": 30}],
        },
    )

    gate = build_gate(stage2_path=stage2, stage3_path=stage3)

    assert gate["status"] == "pass"
    assert gate["decision"]["admit_transformer_research"] is True
    assert gate["decision"]["promote_to_live_weights"] is False


def test_write_transformer_admission_gate_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    gate = {
        "report_type": "a2118_transformer_admission_gate",
        "as_of": "2026-08-24",
        "decision": {"target_weight_change_allowed": False},
    }

    write_gate(gate, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == gate
    assert (history / "a2118_transformer_admission_gate_20260824.json").exists()
