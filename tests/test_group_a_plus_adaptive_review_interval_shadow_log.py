"""Tests for the adaptive review interval pure-logging daily shadow accumulator."""

from __future__ import annotations

import json

import pandas as pd

from group_a_plus.integrations.adaptive_review_interval_shadow_log import (
    append_shadow_log_row,
    build_shadow_log_row,
)


def _frame(**overrides) -> pd.DataFrame:
    base = {"execution_regime": "golden1", "ma_gap": 0.05, "drawdown": -0.01, "tail_risk_score": 0.0}
    base.update(overrides)
    return pd.DataFrame([base], index=pd.DatetimeIndex(["2026-08-07"]))


def test_build_shadow_log_row_reports_today_classification():
    frame = _frame()

    row = build_shadow_log_row(frame=frame, review_interval_days=3, review_interval_label="stable_golden1")

    assert row["status"] == "available"
    assert row["date"] == "2026-08-07"
    assert row["execution_regime"] == "golden1"
    assert row["review_interval_days"] == 3
    assert row["review_interval_label"] == "stable_golden1"
    assert row["ma_gap"] == 0.05
    assert row["drawdown"] == -0.01


def test_build_shadow_log_row_cleans_nan_fields():
    frame = _frame(tail_risk_score=float("nan"))

    row = build_shadow_log_row(frame=frame, review_interval_days=1, review_interval_label="crash_or_recovery")

    assert row["tail_risk_score"] is None


def test_build_shadow_log_row_empty_frame_is_unavailable():
    row = build_shadow_log_row(frame=pd.DataFrame(), review_interval_days=0, review_interval_label="")

    assert row["status"] == "unavailable"
    assert row["reason"] == "empty_frame"


def test_append_shadow_log_row_dedupes_by_date(tmp_path):
    log_path = tmp_path / "shadow_log.jsonl"
    row = {"status": "available", "date": "2026-08-07", "review_interval_days": 3}

    assert append_shadow_log_row(row, log_path) is True
    assert append_shadow_log_row(row, log_path) is False

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["date"] == "2026-08-07"


def test_append_shadow_log_row_skips_unavailable_rows(tmp_path):
    log_path = tmp_path / "shadow_log.jsonl"
    row = {"status": "unavailable", "reason": "empty_frame"}

    assert append_shadow_log_row(row, log_path) is False
    assert not log_path.exists()
