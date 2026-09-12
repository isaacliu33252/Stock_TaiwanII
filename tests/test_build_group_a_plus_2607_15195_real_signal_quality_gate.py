from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.evaluate.build_group_a_plus_2607_15195_real_signal_quality_gate import build_gate, write_gate


def _seed_db(path: Path, panel_path: Path) -> None:
    idx = pd.bdate_range("2025-01-01", periods=180)
    rows = []
    for i, dt in enumerate(idx[:140]):
        cycle = i % 20
        future = 0.06 - cycle * 0.008
        prob = 0.8 if future > 0 else 0.2
        rows.append(
            {
                "date": str(dt.date()),
                "prob_up_h20": prob,
                "ensemble_prob_up": prob,
                "prob_up_h5": prob,
                "prob_up_h1": prob,
                "confidence": 0.7,
                "future_return_h20": future,
                "future_mdd_h20": -0.02 if future > 0 else -0.08,
                "is_live": False,
            }
        )
    pd.DataFrame(rows).to_csv(panel_path, index=False)


def test_real_signal_quality_gate_passes_good_real_signal(tmp_path: Path) -> None:
    db = tmp_path / "stock.db"
    panel = tmp_path / "panel.csv"
    _seed_db(db, panel)

    gate = build_gate(
        panel_path=panel,
        db_path=tmp_path / "missing.db",
        min_rows=80,
        min_rank_ic=0.05,
        min_direction_accuracy=0.52,
        h20_max=0.33,
        conf_min=0.55,
        min_trigger_events=5,
        min_net_filter_value=0.001,
    )

    assert gate["report_type"] == "group_a_plus_2607_15195_real_signal_quality_gate"
    assert gate["status"] == "pass"
    assert gate["decision"]["real_signal_quality_sufficient_for_sciphyrl_optimizer_research"] is True
    assert gate["decision"]["allow_oracle_signal_assumption"] is False
    assert gate["decision"]["target_weight_change_allowed"] is False


def test_real_signal_quality_gate_blocks_missing_panel(tmp_path: Path) -> None:
    gate = build_gate(panel_path=tmp_path / "missing.csv", db_path=tmp_path / "missing.db")

    assert gate["status"] == "blocked"
    assert "signal_panel_unavailable" in gate["blocking_reasons"]
    assert gate["decision"]["train_sciphyrl_or_pinn_optimizer_now"] is False


def test_write_real_signal_quality_gate_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    gate = {
        "report_type": "group_a_plus_2607_15195_real_signal_quality_gate",
        "as_of": "2026-08-24",
        "decision": {"target_weight_change_allowed": False},
    }

    write_gate(gate, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == gate
    assert (history / "2607_15195_real_signal_quality_gate_20260824.json").exists()
