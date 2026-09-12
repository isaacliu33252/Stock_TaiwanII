from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_2606_09104_00631l_staged_ladder_readiness import (
    build_ladder,
    write_ladder,
)


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _inputs(tmp_path: Path, *, state: str = "HIGH") -> dict[str, Path]:
    live_snapshot = _write_json(
        tmp_path / "snapshot.json",
        {
            "as_of": "2026-08-25",
            "portfolio_state": {
                "weights": {"0050.TW": 0.24, "00631L.TW": 0.01, "00632R.TW": 0.0, "00679B.TWO": 0.001},
                "cash_weight": 0.749,
            },
        },
    )
    live_signal = _write_json(tmp_path / "live.json", {"data": {"actual_data_date": "2026-08-25"}})
    holdings = _write_json(tmp_path / "holdings.json", {"as_of": "2026-08-25"})
    regime = _write_json(tmp_path / "regime.json", {"latest_state": {"risk_aversion_state": state}})
    return {"live_snapshot": live_snapshot, "live_signal": live_signal, "holdings": holdings, "regime": regime}


def test_staged_ladder_reviews_fixed_caps(tmp_path: Path) -> None:
    paths = _inputs(tmp_path, state="EXTREME")

    report = build_ladder(
        live_snapshot_path=paths["live_snapshot"],
        live_signal_path=paths["live_signal"],
        holdings_snapshot_path=paths["holdings"],
        regime_split_path=paths["regime"],
        stage_caps=(0.02, 0.03, 0.04),
    )

    assert report["report_type"] == "group_a_plus_2606_09104_00631l_staged_ladder_readiness"
    assert [stage["stage_cap_00631l"] for stage in report["stage_reviews"]] == [0.02, 0.03, 0.04]
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["decision"]["allow_staged_00631l_add"] is False


def test_staged_ladder_blocks_latest_high(tmp_path: Path) -> None:
    paths = _inputs(tmp_path, state="HIGH")

    report = build_ladder(
        live_snapshot_path=paths["live_snapshot"],
        live_signal_path=paths["live_signal"],
        holdings_snapshot_path=paths["holdings"],
        regime_split_path=paths["regime"],
        stage_caps=(0.02, 0.03),
    )

    assert report["status"] == "blocked"
    assert "latest_state_not_extreme" in report["blocking_reasons"]
    assert report["decision"]["latest_state_allows_stage"] is False


def test_write_staged_ladder_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    report = {
        "report_type": "group_a_plus_2606_09104_00631l_staged_ladder_readiness",
        "as_of": "2026-08-25",
        "decision": {"target_weight_change_allowed": False},
    }

    write_ladder(report, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert (history / "2606_09104_00631l_staged_ladder_readiness_20260825.json").exists()
