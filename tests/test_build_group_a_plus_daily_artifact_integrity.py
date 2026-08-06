from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from group_a_plus.core.point_in_time_store import write_json_artifact_snapshot


def _load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "evaluate" / "build_group_a_plus_daily_artifact_integrity.py"
    spec = importlib.util.spec_from_file_location("_test_daily_artifact_integrity", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _standard(data: dict) -> dict:
    return {"success": True, "data": data, "metadata": {"timestamp": "2026-07-30T08:00:00"}}


def test_daily_artifact_integrity_ok_when_required_artifacts_and_pit_exist(tmp_path: Path) -> None:
    module = _load_module()
    live_signal = _write_json(
        tmp_path / "live_signal.json",
        _standard({"actual_data_date": "2026-07-27", "generated_at": "2026-07-28T07:13:10"}),
    )
    execution_plan = _write_json(
        tmp_path / "execution_plan.json",
        _standard({"actual_data_date": "2026-07-27", "generated_at": "2026-07-28T07:45:26"}),
    )
    refresh = _write_json(
        tmp_path / "ncf_panel_refresh_recommendation.json",
        {"summary": {"recommendation": "keep_current_pin"}},
    )
    calibration = _write_json(
        tmp_path / "ncf_decision_calibration.json",
        {"calibration_pair_readiness": {"status": "available", "realized_label_rows": 4803, "total_pairs": 4803}},
    )
    pit_root = tmp_path / "pit"
    write_json_artifact_snapshot(
        "execution_plan",
        {"actual_data_date": "2026-07-27"},
        artifact_asof="2026-07-27",
        generated_at="2026-07-28T07:45:26",
        root=pit_root,
    )
    write_json_artifact_snapshot(
        "golden1_0531_release",
        {"release": "golden1_0531"},
        artifact_asof="2026-05-31",
        generated_at="2026-07-30T08:46:00",
        root=pit_root,
    )

    report = module.build_daily_artifact_integrity(
        check_date="2026-07-30",
        live_signal_path=live_signal,
        execution_plan_path=execution_plan,
        panel_refresh_recommendation_path=refresh,
        ncf_decision_calibration_path=calibration,
        pit_root=pit_root,
    )

    assert report["status"] == "ok"
    assert report["errors"] == []
    assert report["warnings"] == []


def test_daily_artifact_integrity_errors_on_stale_execution_plan_and_missing_pit(tmp_path: Path) -> None:
    module = _load_module()
    live_signal = _write_json(tmp_path / "live_signal.json", _standard({"actual_data_date": "2026-07-27"}))
    execution_plan = _write_json(tmp_path / "execution_plan.json", _standard({"actual_data_date": "2026-07-26"}))
    refresh = _write_json(
        tmp_path / "ncf_panel_refresh_recommendation.json",
        {"summary": {"recommendation": "keep_current_pin"}},
    )
    calibration = _write_json(
        tmp_path / "ncf_decision_calibration.json",
        {"calibration_pair_readiness": {"status": "available", "realized_label_rows": 1, "total_pairs": 1}},
    )

    report = module.build_daily_artifact_integrity(
        check_date="2026-07-30",
        live_signal_path=live_signal,
        execution_plan_path=execution_plan,
        panel_refresh_recommendation_path=refresh,
        ncf_decision_calibration_path=calibration,
        pit_root=tmp_path / "pit",
    )

    assert report["status"] == "error"
    assert "execution_plan actual_data_date does not match live_signal" in report["errors"]
    assert "execution_plan PIT snapshot missing for 2026-07-26" in report["errors"]
    assert "golden1_0531_release PIT snapshot missing for 2026-05-31" in report["errors"]


def test_daily_artifact_integrity_warns_when_calibration_labels_missing(tmp_path: Path) -> None:
    module = _load_module()
    live_signal = _write_json(tmp_path / "live_signal.json", _standard({"actual_data_date": "2026-07-27"}))
    execution_plan = _write_json(tmp_path / "execution_plan.json", _standard({"actual_data_date": "2026-07-27"}))
    refresh = _write_json(
        tmp_path / "ncf_panel_refresh_recommendation.json",
        {"summary": {"recommendation": "keep_current_pin"}},
    )
    calibration = _write_json(
        tmp_path / "ncf_decision_calibration.json",
        {"calibration_pair_readiness": {"status": "missing_calibration_pairs"}},
    )
    pit_root = tmp_path / "pit"
    write_json_artifact_snapshot(
        "execution_plan",
        {"actual_data_date": "2026-07-27"},
        artifact_asof="2026-07-27",
        generated_at="2026-07-28T07:45:26",
        root=pit_root,
    )
    write_json_artifact_snapshot(
        "golden1_0531_release",
        {"release": "golden1_0531"},
        artifact_asof="2026-05-31",
        generated_at="2026-07-30T08:46:00",
        root=pit_root,
    )

    report = module.build_daily_artifact_integrity(
        check_date="2026-07-30",
        live_signal_path=live_signal,
        execution_plan_path=execution_plan,
        panel_refresh_recommendation_path=refresh,
        ncf_decision_calibration_path=calibration,
        pit_root=pit_root,
    )

    assert report["status"] == "warning"
    assert report["errors"] == []
    assert "NCF decision calibration realized labels are not fully available" in report["warnings"]
