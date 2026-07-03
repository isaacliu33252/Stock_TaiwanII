from __future__ import annotations

import json
from pathlib import Path

from group_a_plus.operations.ops_health import build_ops_health


def _write(path: Path, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _minimal_live_signal() -> str:
    return json.dumps(
        {
            "success": True,
            "data": {
                "tbrain_shadow": {"status": "available"},
                "finbert_sentiment": {"status": "ok"},
                "factor_lens_gate": {"status": "available"},
            },
        }
    )


def test_ops_health_reports_no_active_allocation_impact(tmp_path: Path) -> None:
    _write(tmp_path / "report/group_a_plus/latest/strategy.json", "{}")
    _write(tmp_path / "report/group_a_plus/latest/live_signal.json", _minimal_live_signal())
    _write(tmp_path / "report/group_a_plus/latest/execution_plan.json", "{}")
    _write(tmp_path / "report/group_a_plus/latest/strategy_env_health.json", "{}")
    _write(tmp_path / "results/ncf_00631l_panel_latest_20260630.csv", "date,value\n")
    _write(tmp_path / "logs/daily.log", "ok\n")
    _write(tmp_path / "run_daily.bat", "echo daily\n")
    _write(tmp_path / "run_fetch.bat", "echo fetch\n")
    _write(tmp_path / "task_scheduler_setup.xml", "<Task />\n")
    _write(tmp_path / "results/ncf_00631l_latest_20260630.json", "{}")
    _write(tmp_path / "results/ncf_00632r_latest_20260630.json", "{}")
    _write(tmp_path / "results/group_a_plus_factor_lens_20260630.json", "{}")
    _write(tmp_path / "results/alphagen_lite_feature_pool_latest_20260701.json", "{}")
    _write(tmp_path / "results/alphagen_lite_shadow_latest_20260701.json", "{}")
    _write(
        tmp_path / "results/ncf_daily_pipeline_20260630.json",
        json.dumps(
            {
                "date_stamp": "20260630",
                "outputs": {
                    "live_signal": "report/group_a_plus/latest/live_signal.json",
                    "factor_lens": "results/group_a_plus_factor_lens_20260630.json",
                },
                "signals": {"00631L": {"direction": "DOWN"}},
            }
        ),
    )

    report = build_ops_health(tmp_path)

    assert report["active_allocation_impact"] == "none"
    assert report["status"] in {"ok", "warning"}
    assert report["artifact_health"]["missing_required"] == []
    assert report["pipeline_health"]["date_stamp"] == "20260630"
    assert report["module_health"]["modules"]["finbert_sentiment"]["status"] == "ok"


def test_ops_health_errors_when_required_artifacts_are_missing(tmp_path: Path) -> None:
    (tmp_path / "results").mkdir(parents=True)
    (tmp_path / "report/group_a_plus/latest").mkdir(parents=True)

    report = build_ops_health(tmp_path)

    assert report["status"] == "error"
    assert "artifact_health" in report["errors"]
    assert "live_signal" in report["artifact_health"]["missing_required"]
