from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_2606_09104_00631l_4pct_high_exclusion_gate import build_gate, write_gate


def _write_split(path: Path, *, latest_state: str) -> Path:
    payload = {
        "as_of": "2026-08-25",
        "latest_state": {"date": "2026-08-25", "risk_aversion_state": latest_state},
        "state_split_summary": {
            "HIGH": {
                "event_count": 100,
                "hit_rate_micro_beats_guarded": 0.47,
                "mean_micro_minus_guarded_20d": 0.0005,
                "mean_es_extra_loss": -0.0023,
            },
            "EXTREME": {
                "event_count": 80,
                "hit_rate_micro_beats_guarded": 0.78,
                "mean_micro_minus_guarded_20d": 0.0038,
                "mean_es_extra_loss": -0.0022,
            },
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_high_exclusion_gate_blocks_latest_high(tmp_path: Path) -> None:
    split = _write_split(tmp_path / "split.json", latest_state="HIGH")

    report = build_gate(regime_split_path=split)

    assert report["status"] == "blocked"
    assert "latest_state_high_excluded" in report["blocking_reasons"]
    assert report["decision"]["skip_high_regime"] is True
    assert report["decision"]["candidate_active_today"] is False
    assert report["decision"]["target_weight_change_allowed"] is False


def test_high_exclusion_gate_allows_extreme_shadow_candidate(tmp_path: Path) -> None:
    split = _write_split(tmp_path / "split.json", latest_state="EXTREME")

    report = build_gate(regime_split_path=split)

    assert report["status"] == "extreme_only_shadow_candidate_active"
    assert report["eligibility_review"]["extreme_passes_high_exclusion_gate"] is True
    assert report["decision"]["candidate_active_today"] is True
    assert report["decision"]["allow_00631l_micro_add_from_high_exclusion_gate"] is False
    assert report["decision"]["target_weight_change_allowed"] is False


def test_write_high_exclusion_gate_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    report = {
        "report_type": "group_a_plus_2606_09104_00631l_4pct_high_exclusion_gate",
        "as_of": "2026-08-25",
        "decision": {"target_weight_change_allowed": False},
    }

    write_gate(report, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert (history / "2606_09104_00631l_4pct_high_exclusion_gate_20260825.json").exists()
