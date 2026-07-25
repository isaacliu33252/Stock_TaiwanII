from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_external_sensitivity_observation_log import build_log, write_outputs


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_external_sensitivity_observation_log_counts_valid_and_stable_observations(tmp_path: Path) -> None:
    existing = _write(
        tmp_path / "log.json",
        {
            "observations": [
                {
                    "observation_date": "2026-07-21",
                    "sensitivity_audit": "old.json",
                    "valid_observation": True,
                    "stable_observation": True,
                    "trigger_critical_exceeded": [],
                }
            ]
        },
    )
    sensitivity = _write(
        tmp_path / "sensitivity.json",
        {
            "column_summary": {
                "ensemble_prob_up": {"max_abs_delta": 0.45, "max_abs_delta_date": "2025-01-02"},
                "h20_prob_up": {"max_abs_delta": 0.51, "max_abs_delta_date": "2025-01-03"},
                "confidence": {"max_abs_delta": 0.10, "max_abs_delta_date": "2025-01-06"},
            }
        },
    )
    manifest = _write(tmp_path / "manifest.json", {"status": "valid_shadow_baseline"})

    report = build_log(
        sensitivity_audit_path=sensitivity,
        same_method_baseline_manifest_path=manifest,
        observation_date="2026-07-22",
        existing_log_path=existing,
    )

    assert report["summary"]["observation_count"] == 2
    assert report["summary"]["valid_observation_count"] == 2
    assert report["summary"]["stable_observation_count"] == 1
    assert report["summary"]["latest_trigger_critical_exceeded"] == ["h20_prob_up"]
    latest = report["observations"][-1]
    assert latest["valid_observation"] is True
    assert latest["stable_observation"] is False
    assert latest["trigger_critical"]["h20_prob_up"]["exceeds_limit"] is True
    assert latest["diagnostic"]["ensemble_prob_up"]["exceeds_limit"] is True
    assert report["decision"]["creates_orders"] is False
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["decision"]["auto_rebalance_allowed"] is False
    assert report["decision"]["keep_golden1_0531_unchanged"] is True


def test_external_sensitivity_observation_log_upserts_same_date_and_path(tmp_path: Path) -> None:
    sensitivity = _write(
        tmp_path / "sensitivity.json",
        {"column_summary": {"h20_prob_up": {"max_abs_delta": 0.01}, "confidence": {"max_abs_delta": 0.02}}},
    )
    manifest = _write(tmp_path / "manifest.json", {"status": "valid_shadow_baseline"})
    existing = _write(
        tmp_path / "log.json",
        {
            "observations": [
                {
                    "observation_date": "2026-07-22",
                    "sensitivity_audit": str(sensitivity),
                    "valid_observation": False,
                    "stable_observation": False,
                }
            ]
        },
    )

    report = build_log(
        sensitivity_audit_path=sensitivity,
        same_method_baseline_manifest_path=manifest,
        observation_date="2026-07-22",
        existing_log_path=existing,
    )

    assert report["summary"]["observation_count"] == 1
    assert report["summary"]["valid_observation_count"] == 1
    assert report["summary"]["stable_observation_count"] == 1


def test_write_outputs_writes_json_markdown_and_history(tmp_path: Path) -> None:
    report = {
        "summary": {
            "observation_count": 1,
            "valid_observation_count": 1,
            "stable_observation_count": 0,
            "latest_trigger_critical_exceeded": ["h20_prob_up"],
        },
        "observations": [],
        "decision": {
            "creates_orders": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "keep_golden1_0531_unchanged": True,
        },
    }
    output = tmp_path / "latest/external_sensitivity_observation_log.json"
    output_md = tmp_path / "latest/external_sensitivity_observation_log.md"
    history = tmp_path / "history"

    write_outputs(report, output=output, output_md=output_md, history_dir=history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    markdown = output_md.read_text(encoding="utf-8")
    assert "GroupA+ External Sensitivity Observation Log" in markdown
    assert "Golden1_0531 unchanged: `True`" in markdown
    assert list(history.glob("external_sensitivity_observation_log_*.json"))
