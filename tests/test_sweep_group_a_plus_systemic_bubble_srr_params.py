from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.evaluate.sweep_group_a_plus_systemic_bubble_srr_params import run_sweep, write_sweep


def _write_frame(path: Path) -> None:
    dates = pd.bdate_range("2026-01-01", periods=70)
    rows = []
    for i, dt in enumerate(dates):
        event = 20 <= i <= 30
        strict = 18 <= i <= 24
        rows.append(
            {
                "date": str(dt.date()),
                "srr_no_add_active": i in {19, 20},
                "no_add_label_h10": event,
                "systemic_time_at_risk_days_60": 22 if strict else 3,
                "systemic_00631l_vol20_percentile_252d": 0.88 if strict else 0.3,
                "systemic_0050_ma120_gap": 0.11 if strict else 0.01,
                "systemic_etf_coupling_score": 0.78 if strict else 0.45,
                "systemic_etf_coupling_percentile_252d": 0.84 if strict else 0.3,
                "systemic_reflexivity_proxy_percentile_252d": 0.9 if 25 <= i <= 34 else 0.2,
                "systemic_00631l_volume_z_60d": 2.1 if 25 <= i <= 34 else 0.0,
                "systemic_00631l_abs_return_z_60d": 2.1 if 25 <= i <= 34 else 0.0,
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)


def test_run_sweep_keeps_results_research_only(tmp_path: Path) -> None:
    frame = tmp_path / "frame.csv"
    _write_frame(frame)

    payload = run_sweep(frame, as_of="2026-07-20", min_active_for_promotion=20)

    assert payload["report_type"] == "group_a_plus_systemic_bubble_param_sweep"
    assert payload["status"] == "blocked"
    assert payload["decision"]["promotion_allowed"] is False
    assert payload["candidate_count"] > 0
    assert payload["best_candidate"]["h10_confusion"]["active_days"] > 0
    assert "no_live_weight_change_allowed" in payload["blocking_reasons"]


def test_write_sweep_writes_output_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "sweep.json"
    history = tmp_path / "history"
    payload = {
        "as_of": "2026-07-20",
        "report_type": "group_a_plus_systemic_bubble_param_sweep",
        "decision": {"promotion_allowed": False},
    }

    write_sweep(payload, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == payload
    assert (history / "systemic_bubble_param_sweep_20260720.json").exists()
