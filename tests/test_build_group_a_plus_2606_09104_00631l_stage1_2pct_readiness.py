from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_2606_09104_00631l_stage1_2pct_readiness import (
    build_readiness,
    write_readiness,
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
    regime = _write_json(
        tmp_path / "regime.json",
        {"latest_state": {"date": "2026-08-25", "risk_aversion_state": state}},
    )
    return {"live_snapshot": live_snapshot, "live_signal": live_signal, "holdings": holdings, "regime": regime}


def test_stage1_2pct_readiness_builds_turnover_light_target(tmp_path: Path) -> None:
    paths = _inputs(tmp_path, state="EXTREME")

    report = build_readiness(
        live_snapshot_path=paths["live_snapshot"],
        live_signal_path=paths["live_signal"],
        holdings_snapshot_path=paths["holdings"],
        regime_split_path=paths["regime"],
        stage_cap=0.02,
    )

    assert report["stage"]["target_weights"]["0050.TW"] == 0.24
    assert report["stage"]["target_weights"]["00631L.TW"] == 0.02
    assert round(report["stage"]["target_weights"]["cash"], 3) == 0.739
    assert report["stage"]["turnover_review"]["execution_cost_state"] == "LOW_COST"
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["decision"]["allow_stage1_00631l_add"] is False


def test_stage1_2pct_readiness_blocks_latest_high(tmp_path: Path) -> None:
    paths = _inputs(tmp_path, state="HIGH")

    report = build_readiness(
        live_snapshot_path=paths["live_snapshot"],
        live_signal_path=paths["live_signal"],
        holdings_snapshot_path=paths["holdings"],
        regime_split_path=paths["regime"],
        stage_cap=0.02,
    )

    assert report["status"] == "blocked"
    assert "latest_state_not_extreme" in report["blocking_reasons"]
    assert report["decision"]["target_weight_change_allowed"] is False


def test_write_stage1_2pct_readiness_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    report = {
        "report_type": "group_a_plus_2606_09104_00631l_stage1_2pct_readiness",
        "as_of": "2026-08-25",
        "decision": {"target_weight_change_allowed": False},
    }

    write_readiness(report, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert (history / "2606_09104_00631l_stage1_2pct_readiness_20260825.json").exists()
