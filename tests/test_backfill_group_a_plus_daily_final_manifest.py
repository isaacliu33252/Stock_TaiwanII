from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.misc.backfill_group_a_plus_daily_final_manifest import build_manifest, write_manifest


def _write(path: Path, payload: dict | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload or {}), encoding="utf-8")
    return path


def test_backfill_manifest_records_existing_final_governance_outputs_only(tmp_path: Path) -> None:
    manifest = build_manifest(
        date_stamp="20260722",
        live_signal=_write(tmp_path / "results/live.json"),
        promotion_gate=_write(tmp_path / "results/promotion.json"),
        daily_status_final=_write(tmp_path / "results/daily_final.json", {"status_stage": "final"}),
        deployment_summary=_write(tmp_path / "report/latest/deployment_summary.json"),
        daily_status_pointer=_write(tmp_path / "report/latest/daily_status.json"),
    )

    assert manifest["date_stamp"] == "20260722"
    assert manifest["status"] == "backfilled_outputs_only"
    assert manifest["mode"] == "governance_final_outputs_only"
    assert set(manifest["outputs"]) == {
        "live_signal",
        "promotion_gate",
        "daily_status_final",
        "deployment_summary",
        "daily_status_pointer",
    }
    assert manifest["backfill"]["full_pipeline_rerun"] is False
    assert manifest["backfill"]["model_outputs_backfilled"] is False
    assert manifest["backfill"]["creates_orders"] is False
    assert manifest["backfill"]["target_weight_change_allowed"] is False
    assert manifest["backfill"]["auto_rebalance_allowed"] is False
    assert manifest["backfill"]["keep_golden1_0531_unchanged"] is True


def test_backfill_manifest_requires_existing_outputs(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_manifest(
            date_stamp="20260722",
            live_signal=tmp_path / "missing_live.json",
            promotion_gate=_write(tmp_path / "promotion.json"),
            daily_status_final=_write(tmp_path / "daily_final.json"),
            deployment_summary=_write(tmp_path / "deployment_summary.json"),
            daily_status_pointer=_write(tmp_path / "daily_status.json"),
        )


def test_write_manifest_writes_json(tmp_path: Path) -> None:
    output = tmp_path / "results/ncf_daily_pipeline_20260722.json"
    manifest = {
        "date_stamp": "20260722",
        "status": "backfilled_outputs_only",
        "outputs": {},
    }

    write_manifest(manifest, output)

    assert json.loads(output.read_text(encoding="utf-8")) == manifest
