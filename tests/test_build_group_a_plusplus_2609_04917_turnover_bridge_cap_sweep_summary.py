import json
from pathlib import Path

from scripts.evaluate.build_group_a_plusplus_2609_04917_turnover_bridge_cap_sweep_summary import build_report


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_summary_prefers_clean_full_00679b_exit(tmp_path: Path) -> None:
    cap45 = _write(
        tmp_path / "cap45.json",
        {
            "status": "shadow_bridge_available_for_manual_review",
            "limits": {"max_turnover": 0.45},
            "computed": {"bridge_turnover": 0.45},
            "bridge_target_shares": {"00679B.TWO": 100, "00713.TW": 0, "00631L.TW": 0},
            "bridge_trades": [{}],
        },
    )
    cap465 = _write(
        tmp_path / "cap465.json",
        {
            "status": "shadow_bridge_available_for_manual_review",
            "limits": {"max_turnover": 0.465},
            "computed": {"bridge_turnover": 0.465},
            "bridge_target_shares": {"00679B.TWO": 0, "00713.TW": 0, "00631L.TW": 0},
            "bridge_trades": [{}],
        },
    )
    cap47 = _write(
        tmp_path / "cap47.json",
        {
            "status": "shadow_bridge_available_for_manual_review",
            "limits": {"max_turnover": 0.47},
            "computed": {"bridge_turnover": 0.47},
            "bridge_target_shares": {"00679B.TWO": 0, "00713.TW": 1, "00631L.TW": 0},
            "bridge_trades": [{}, {}],
        },
    )

    report = build_report([cap45, cap465, cap47])

    assert report["status"] == "available"
    assert report["recommended_cap"] == 0.465
    assert report["recommended_path"].endswith("cap465.json")
    assert report["decision"]["live_execution_allowed"] is False


def test_summary_blocks_without_feasible_rows(tmp_path: Path) -> None:
    bad = _write(
        tmp_path / "bad.json",
        {
            "status": "blocked",
            "limits": {"max_turnover": 0.60},
            "computed": {"bridge_turnover": 0.60},
            "bridge_target_shares": {"00631L.TW": 10},
        },
    )

    report = build_report([bad])

    assert report["status"] == "blocked"
    assert report["recommended_cap"] is None
