from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_2606_09104_00631l_4pct_extreme_only_promotion_readiness import (
    build_readiness,
    write_readiness,
)


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _shadow(path: Path, *, state: str = "EXTREME") -> Path:
    return _write_json(
        path,
        {
            "as_of": "2026-08-25",
            "latest_state": {"risk_aversion_state": state, "date": "2026-08-25"},
            "extreme_only_active_event_summary": {
                "event_count": 80,
                "hit_rate_micro_beats_guarded": 0.78,
                "mean_micro_minus_guarded_20d": 0.0038,
                "mean_es_extra_loss": -0.0022,
            },
            "decision": {"extreme_only_has_historical_value": True},
        },
    )


def test_extreme_only_promotion_readiness_ready_only_for_extreme_and_fresh_holdings(tmp_path: Path) -> None:
    report = build_readiness(
        extreme_shadow_path=_shadow(tmp_path / "shadow.json", state="EXTREME"),
        live_signal_path=_write_json(tmp_path / "live.json", {"data": {"actual_data_date": "2026-08-25"}}),
        holdings_snapshot_path=_write_json(tmp_path / "holdings.json", {"as_of": "2026-08-25"}),
    )

    assert report["status"] == "ready_for_manual_promotion_review"
    assert report["decision"]["requires_signed_manual_approval"] is True
    assert report["decision"]["target_weight_change_allowed"] is False


def test_extreme_only_promotion_readiness_blocks_latest_high(tmp_path: Path) -> None:
    report = build_readiness(
        extreme_shadow_path=_shadow(tmp_path / "shadow.json", state="HIGH"),
        live_signal_path=_write_json(tmp_path / "live.json", {"data": {"actual_data_date": "2026-08-25"}}),
        holdings_snapshot_path=_write_json(tmp_path / "holdings.json", {"as_of": "2026-08-25"}),
    )

    assert report["status"] == "blocked"
    assert "latest_state_not_extreme" in report["blocking_reasons"]
    assert report["decision"]["target_weight_change_allowed"] is False


def test_write_extreme_only_promotion_readiness_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    report = {
        "report_type": "group_a_plus_2606_09104_00631l_4pct_extreme_only_promotion_readiness",
        "as_of": "2026-08-25",
        "decision": {"target_weight_change_allowed": False},
    }

    write_readiness(report, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert (history / "2606_09104_00631l_4pct_extreme_only_promotion_readiness_20260825.json").exists()
