import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_data_freshness_gate import build_gate


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_data_freshness_gate_passes_aligned_inputs(tmp_path: Path) -> None:
    live = _write(
        tmp_path / "live.json",
        {
            "requested_as_of_date": "2026-09-08",
            "actual_data_date": "2026-09-08",
            "business_stale_days": 0,
            "execution_guard_reasons": [],
        },
    )
    explain = _write(
        tmp_path / "explain.json",
        {
            "status": "available",
            "strategy_identity": {"date_window": {"end": "2026-09-08"}},
            "warning_reasons": [],
        },
    )
    ohlcv = _write(tmp_path / "ohlcv.json", {"target_date": "2026-09-08", "overall_status": "ok"})

    report = build_gate(
        live_signal_path=live,
        explain_snapshot_path=explain,
        ohlcv_freshness_path=ohlcv,
        as_of="2026-09-08",
    )

    assert report["status"] == "passed"
    assert report["blockers"] == []
    assert report["decision"]["data_fresh_enough_for_unqualified_execution"] is True


def test_data_freshness_gate_blocks_ohlcv_error(tmp_path: Path) -> None:
    live = _write(tmp_path / "live.json", {"actual_data_date": "2026-09-08", "business_stale_days": 0})
    explain = _write(tmp_path / "explain.json", {"strategy_identity": {"date_window": {"end": "2026-09-08"}}})
    ohlcv = _write(tmp_path / "ohlcv.json", {"target_date": "2026-09-08", "overall_status": "error"})

    report = build_gate(
        live_signal_path=live,
        explain_snapshot_path=explain,
        ohlcv_freshness_path=ohlcv,
        as_of="2026-09-08",
    )

    assert report["status"] == "blocked"
    assert "ohlcv_freshness_report_error" in report["blockers"]


def test_data_freshness_gate_blocks_stale_latest_strategy_explain_window(tmp_path: Path) -> None:
    live = _write(tmp_path / "live.json", {"actual_data_date": "2026-09-08", "business_stale_days": 0})
    explain = _write(
        tmp_path / "explain.json",
        {"strategy_identity": {"date_window": {"end": "2026-08-07"}}, "warning_reasons": []},
    )
    ohlcv = _write(tmp_path / "ohlcv.json", {"target_date": "2026-09-08", "overall_status": "ok"})

    report = build_gate(
        live_signal_path=live,
        explain_snapshot_path=explain,
        ohlcv_freshness_path=ohlcv,
        as_of="2026-09-08",
    )

    assert report["status"] == "blocked"
    assert "latest_strategy_explain_target_weight_window_lags_live_signal" in report["blockers"]
    assert report["decision"]["data_fresh_enough_for_unqualified_execution"] is False
