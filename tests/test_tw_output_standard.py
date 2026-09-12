"""Tests for the production-pointer backup-before-overwrite protection in
tw_output_standard.py (2026-08-09, motivated by a real accidental overwrite
of report/group_a_plus/latest/live_signal.json during a verification run).
"""

from __future__ import annotations

import json

from tw_output_standard import backup_latest_pointer_before_overwrite, write_standard_output


def test_backup_created_for_existing_file_under_latest_dir(tmp_path):
    latest_dir = tmp_path / "report" / "group_a_plus" / "latest"
    latest_dir.mkdir(parents=True)
    target = latest_dir / "live_signal.json"
    target.write_text('{"old": true}', encoding="utf-8")

    backup_latest_pointer_before_overwrite(target)

    backup = latest_dir / "live_signal.json.bak"
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == '{"old": true}'


def test_no_backup_when_file_does_not_exist_yet(tmp_path):
    latest_dir = tmp_path / "report" / "group_a_plus" / "latest"
    latest_dir.mkdir(parents=True)
    target = latest_dir / "brand_new.json"

    backup_latest_pointer_before_overwrite(target)

    assert not (latest_dir / "brand_new.json.bak").exists()


def test_no_backup_outside_latest_dir(tmp_path):
    other_dir = tmp_path / "results"
    other_dir.mkdir()
    target = other_dir / "some_report_20260809.json"
    target.write_text('{"old": true}', encoding="utf-8")

    backup_latest_pointer_before_overwrite(target)

    assert not (other_dir / "some_report_20260809.json.bak").exists()


def test_backup_is_rolling_single_generation(tmp_path):
    latest_dir = tmp_path / "report" / "group_a_plus" / "latest"
    latest_dir.mkdir(parents=True)
    target = latest_dir / "live_signal.json"
    backup = latest_dir / "live_signal.json.bak"

    target.write_text('{"version": 1}', encoding="utf-8")
    backup_latest_pointer_before_overwrite(target)
    assert backup.read_text(encoding="utf-8") == '{"version": 1}'

    target.write_text('{"version": 2}', encoding="utf-8")
    backup_latest_pointer_before_overwrite(target)
    assert backup.read_text(encoding="utf-8") == '{"version": 2}'


def test_write_standard_output_backs_up_existing_latest_pointer(tmp_path):
    latest_dir = tmp_path / "report" / "group_a_plus" / "latest"
    latest_dir.mkdir(parents=True)
    target = latest_dir / "live_signal.json"
    target.write_text('{"stale": true}', encoding="utf-8")

    write_standard_output({"success": True, "data": {"fresh": True}, "error": None}, str(target))

    backup = latest_dir / "live_signal.json.bak"
    assert backup.exists()
    assert json.loads(backup.read_text(encoding="utf-8")) == {"stale": True}
    assert json.loads(target.read_text(encoding="utf-8"))["data"] == {"fresh": True}


def test_write_standard_output_no_backup_on_first_write(tmp_path):
    latest_dir = tmp_path / "report" / "group_a_plus" / "latest"
    latest_dir.mkdir(parents=True)
    target = latest_dir / "brand_new.json"

    write_standard_output({"success": True, "data": {}, "error": None}, str(target))

    assert not (latest_dir / "brand_new.json.bak").exists()
    assert target.exists()
