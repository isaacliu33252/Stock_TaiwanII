from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_intervention_history_from_daily_status import (
    build_history,
    write_history,
)


PROFILE = "a2118_a2111_ncf_late_bull_deleverage"


def _write_daily(path: Path, *, check_date: str, target_00631l: int, blocked_delta: int | None = None) -> None:
    blocked_trades = []
    if blocked_delta is not None:
        blocked_trades.append(
            {
                "ticker": "00631L.TW",
                "side": "buy",
                "current_shares": 0,
                "requested_target_shares": blocked_delta,
                "guarded_target_shares": 0,
                "blocked_delta_shares": blocked_delta,
                "reason": "volatility_gate_no_00631l_add",
            }
        )
    path.write_text(
        json.dumps(
            {
                "generated_at": f"{check_date}T18:00:00",
                "check_date": check_date,
                "profile": PROFILE,
                "signal": {"actual_data_date": check_date},
                "group_a_plus": {
                    "target_shares": {
                        "0050.TW": 1000,
                        "00631L.TW": target_00631l,
                        "00632R.TW": 0,
                    },
                    "pre_trade_guards": [
                        {
                            "name": "volatility_gate_no_00631l_add",
                            "status": "blocked" if blocked_trades else "inactive",
                            "policy": "advisory_no_auto_weight_change",
                            "blocked_trades": blocked_trades,
                        }
                    ],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_build_history_extracts_blocked_trades_and_target_changes(tmp_path: Path) -> None:
    daily_dir = tmp_path / "daily"
    daily_dir.mkdir()
    _write_daily(
        daily_dir / f"daily_status_{PROFILE}_20260714_20260714_180000.json",
        check_date="2026-07-14",
        target_00631l=3000,
        blocked_delta=560,
    )
    _write_daily(
        daily_dir / f"daily_status_{PROFILE}_20260720_20260718_231115.json",
        check_date="2026-07-20",
        target_00631l=6202,
        blocked_delta=668,
    )

    history = build_history(daily_dir=daily_dir, profile=PROFILE)

    assert history["status"] == "available"
    assert history["coverage"]["source_file_count"] == 2
    assert history["coverage"]["blocked_entry_count"] == 2
    assert history["coverage"]["leverage_intervention_count"] == 3
    assert history["coverage"]["first_check_date"] == "2026-07-14"
    assert history["coverage"]["last_check_date"] == "2026-07-20"
    assert any(entry["source"] == "daily_status_target_shares_delta" for entry in history["entries"])
    assert all(entry["filled_trade"] is False for entry in history["entries"])


def test_write_history_writes_latest_and_history_snapshot(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history_dir = tmp_path / "history"
    history = {
        "report_type": "group_a_plus_intervention_history",
        "coverage": {"last_check_date": "2026-07-20"},
    }

    write_history(history, output, history_dir)

    assert json.loads(output.read_text(encoding="utf-8")) == history
    assert json.loads((history_dir / "20260720.json").read_text(encoding="utf-8")) == history
