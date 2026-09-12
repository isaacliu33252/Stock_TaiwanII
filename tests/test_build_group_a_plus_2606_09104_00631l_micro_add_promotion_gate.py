from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_2606_09104_00631l_micro_add_promotion_gate import build_gate, write_gate


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _seed_inputs(tmp_path: Path) -> dict[str, Path]:
    cap_sweep = _write_json(
        tmp_path / "cap_sweep.json",
        {
            "as_of": "2026-08-25",
            "cap_reviews": [
                {
                    "cap_00631l": 0.04,
                    "passes_high_extreme_gate": True,
                    "high_extreme_summary": {
                        "mean_return_diff_20d": 0.0017,
                        "hit_rate_micro_beats_guarded": 0.59,
                        "micro_minus_guarded_mdd_extra_loss": -0.0043,
                        "mean_micro_es_20d": -0.012,
                    },
                },
                {"cap_00631l": 0.05, "passes_high_extreme_gate": False},
            ],
            "decision": {"best_cap_for_promotion_review": 0.04},
        },
    )
    risk_gate = _write_json(tmp_path / "risk_gate.json", {"risk_aversion": {"state": "HIGH"}})
    bled_review = _write_json(
        tmp_path / "bled_review.json",
        {
            "target_tail_reviews": [
                {"target_name": "guarded_live_target", "student_t_adjusted_daily_es95": -0.010}
            ]
        },
    )
    live_snapshot = _write_json(
        tmp_path / "live_snapshot.json",
        {
            "as_of": "2026-08-25",
            "portfolio_state": {
                "weights": {"0050.TW": 0.30, "00631L.TW": 0.02, "00632R.TW": 0.0, "00679B.TWO": 0.0},
                "cash_weight": 0.68,
            },
        },
    )
    forward_monitor = _write_json(
        tmp_path / "forward_monitor.json",
        {
            "as_of": "2026-08-25",
            "live_signal": {
                "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
                "target_weights": {"0050.TW": 0.3, "cash": 0.7},
                "market_state": "bull_pullback_deep",
                "execution_regime": "golden1",
            },
        },
    )
    return {
        "cap_sweep": cap_sweep,
        "risk_gate": risk_gate,
        "bled_review": bled_review,
        "live_snapshot": live_snapshot,
        "forward_monitor": forward_monitor,
    }


def test_micro_add_promotion_gate_ready_still_blocks_live_trade(tmp_path: Path) -> None:
    paths = _seed_inputs(tmp_path)

    report = build_gate(
        cap_sweep_path=paths["cap_sweep"],
        risk_gate_path=paths["risk_gate"],
        bled_review_path=paths["bled_review"],
        live_snapshot_path=paths["live_snapshot"],
        forward_monitor_path=paths["forward_monitor"],
        preferred_cap=0.04,
    )

    assert report["report_type"] == "group_a_plus_2606_09104_00631l_micro_add_promotion_gate"
    assert report["status"] == "manual_review_candidate_ready"
    assert report["candidate"]["target_weights"]["00631L.TW"] == 0.04
    assert report["decision"]["candidate_ready_for_manual_promotion_review"] is True
    assert report["decision"]["requires_signed_manual_approval"] is True
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["decision"]["allow_00631l_micro_add"] is False
    assert "current_risk_aversion_high_or_extreme_manual_review_required" in report["warning_reasons"]


def test_micro_add_promotion_gate_blocks_missing_inputs(tmp_path: Path) -> None:
    report = build_gate(
        cap_sweep_path=tmp_path / "missing_cap_sweep.json",
        risk_gate_path=tmp_path / "missing_risk_gate.json",
        bled_review_path=tmp_path / "missing_bled_review.json",
        live_snapshot_path=tmp_path / "missing_live_snapshot.json",
        forward_monitor_path=tmp_path / "missing_forward_monitor.json",
    )

    assert report["status"] == "blocked"
    assert "cap_sweep_missing" in report["blocking_reasons"]
    assert "preferred_cap_review_missing" in report["blocking_reasons"]
    assert report["decision"]["candidate_ready_for_manual_promotion_review"] is False
    assert report["decision"]["target_weight_change_allowed"] is False


def test_write_micro_add_promotion_gate_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    report = {
        "report_type": "group_a_plus_2606_09104_00631l_micro_add_promotion_gate",
        "as_of": "2026-08-25",
        "decision": {"target_weight_change_allowed": False},
    }

    write_gate(report, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert (history / "2606_09104_00631l_micro_add_promotion_gate_20260825.json").exists()
