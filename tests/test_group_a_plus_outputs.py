from __future__ import annotations

import json
from pathlib import Path

import pytest

from group_a_plus.outputs import output_path, report_envelope, write_json_report


def test_output_path_uses_canonical_outputs_tree(tmp_path: Path) -> None:
    path = output_path(
        "daily_status",
        kind="pipeline",
        run_mode="production",
        outputs_root=tmp_path,
    )

    assert path == tmp_path / "group_a_plus" / "production" / "pipeline" / "daily_status.json"


def test_output_path_supports_latest_pointer(tmp_path: Path) -> None:
    path = output_path(
        "strategy",
        kind="signal",
        run_mode="production",
        latest=True,
        outputs_root=tmp_path,
    )

    assert path == tmp_path / "group_a_plus" / "latest" / "strategy.json"


def test_output_path_sanitizes_path_separators(tmp_path: Path) -> None:
    path = output_path(
        "nested/name",
        kind="research",
        run_mode="shadow",
        outputs_root=tmp_path,
    )

    assert path.name == "nested_name.json"


def test_output_path_rejects_blank_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="artifact_name"):
        output_path(" ", kind="signal", outputs_root=tmp_path)


def test_output_path_rejects_suffix_without_dot(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="suffix"):
        output_path("daily_status", kind="pipeline", suffix="json", outputs_root=tmp_path)


def test_report_envelope_adds_common_schema_fields() -> None:
    envelope = report_envelope(
        artifact_name="daily_status",
        kind="pipeline",
        run_mode="production",
        generated_at="2026-07-29T10:00:00+00:00",
        payload={"status": "ok"},
    )

    assert envelope == {
        "schema_version": 1,
        "artifact_name": "daily_status",
        "artifact_kind": "pipeline",
        "run_mode": "production",
        "generated_at": "2026-07-29T10:00:00+00:00",
        "payload": {"status": "ok"},
    }


def test_report_envelope_rejects_invalid_schema_version() -> None:
    with pytest.raises(ValueError, match="schema_version"):
        report_envelope(
            artifact_name="daily_status",
            kind="pipeline",
            run_mode="production",
            schema_version=0,
            payload={},
        )


def test_write_json_report_writes_enveloped_payload(tmp_path: Path) -> None:
    path = write_json_report(
        tmp_path / "outputs/group_a_plus/latest/ops_health.json",
        artifact_name="ops_health",
        kind="pipeline",
        run_mode="production",
        generated_at="2026-07-29T10:00:00+00:00",
        payload={"status": "ok"},
    )

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["artifact_name"] == "ops_health"
    assert saved["artifact_kind"] == "pipeline"
    assert saved["run_mode"] == "production"
    assert saved["payload"] == {"status": "ok"}
