from __future__ import annotations

from pathlib import Path

import pytest

from scripts.evaluate.build_group_a_plus_2606_26625_rolling_tail_no_add_gate import (
    _tail_gap,
    _variants,
    _weights,
    write_markdown,
)


def test_weights_normalize_live_signal_payload() -> None:
    weights = _weights(
        {
            "target_weights": {
                "0050.TW": 0.47,
                "00631L.TW": 0.10,
                "00632R.TW": 0.16,
                "cash": 0.27,
            }
        }
    )

    assert sum(weights.values()) == pytest.approx(1.0)
    assert weights["00679B.TWO"] == 0.0


def test_variants_move_removed_letf_exposure_to_cash() -> None:
    latest = {
        "0050.TW": 0.47,
        "00631L.TW": 0.10,
        "00632R.TW": 0.16,
        "00679B.TWO": 0.0,
        "cash": 0.27,
    }

    variants = _variants(latest)

    assert variants["no_00631l_to_cash"]["00631L.TW"] == 0.0
    assert variants["no_00631l_to_cash"]["cash"] == pytest.approx(0.37)
    assert variants["no_00632r_to_cash"]["00632R.TW"] == 0.0
    assert variants["no_00632r_to_cash"]["cash"] == pytest.approx(0.43)
    assert variants["no_letf_to_cash"]["00631L.TW"] == 0.0
    assert variants["no_letf_to_cash"]["00632R.TW"] == 0.0
    assert variants["no_letf_to_cash"]["cash"] == pytest.approx(0.53)


def test_tail_gap_flags_worse_es_and_mdd() -> None:
    gap = _tail_gap(
        {"expected_shortfall_loss_95": 0.02, "max_drawdown": -0.20},
        {"expected_shortfall_loss_95": 0.01, "max_drawdown": -0.10},
    )

    assert gap["latest_worse_es95"] is True
    assert gap["latest_worse_mdd"] is True
    assert gap["es95_delta_vs_reference"] == pytest.approx(0.01)
    assert gap["mdd_delta_vs_reference"] == pytest.approx(-0.10)


def test_write_markdown_renders_gate_summary(tmp_path: Path) -> None:
    output = tmp_path / "gate.md"
    report = {
        "status": "available_for_shadow_monitoring",
        "as_of": "2026-08-31",
        "policy": "research_only_rolling_tail_no_add_gate_no_weight_change",
        "decision": {"allow_00631l_add": False, "allow_00632r_open": True},
        "rolling_windows": {
            "63": {
                "latest_hill_95": {"hill_xi": 0.3},
                "window_gate": {"block_00631l_add": True, "block_00632r_open": False},
                "metrics": {
                    "latest_strategy": {"expected_shortfall_loss_95": 0.02},
                    "no_00631l_to_cash": {"expected_shortfall_loss_95": 0.01},
                    "no_00632r_to_cash": {"expected_shortfall_loss_95": 0.02},
                    "no_letf_to_cash": {"expected_shortfall_loss_95": 0.01},
                },
            }
        },
    }

    write_markdown(report, output)

    text = output.read_text(encoding="utf-8")
    assert "2606.26625 Rolling Tail No-Add Gate" in text
    assert "00631L add" in text
    assert "`blocked`" in text
