"""Tests for the ADD_0050_INSTEAD pure-logging daily shadow accumulator."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from group_a_plus.integrations.add_0050_instead_shadow_log import (
    append_shadow_log_row,
    build_shadow_log_row,
)


def _targets(dates: list[str], weights_631l: list[float]) -> pd.DataFrame:
    index = pd.DatetimeIndex(dates)
    return pd.DataFrame(
        {
            "0050.TW": [0.3] * len(dates),
            "00631L.TW": weights_631l,
            "00632R.TW": [0.0] * len(dates),
            "00679B.TWO": [0.0] * len(dates),
            "cash": [0.7 - w for w in weights_631l],
        },
        index=index,
    )


def test_would_trigger_when_narrow_lead_and_631l_increasing():
    targets = _targets(["2026-08-06", "2026-08-07"], [0.1, 0.2])
    narrow_lead = pd.Series([False, True], index=targets.index)

    row = build_shadow_log_row(target_weights=targets, narrow_lead=narrow_lead)

    assert row["status"] == "available"
    assert row["date"] == "2026-08-07"
    assert row["narrow_lead"] is True
    assert row["00631l_target_weight_increasing"] is True
    assert row["would_trigger_add_0050_instead"] is True
    assert row["would_be_redirect_amount"] == pytest.approx(0.1)


def test_no_trigger_when_narrow_lead_but_631l_not_increasing():
    targets = _targets(["2026-08-06", "2026-08-07"], [0.2, 0.1])
    narrow_lead = pd.Series([False, True], index=targets.index)

    row = build_shadow_log_row(target_weights=targets, narrow_lead=narrow_lead)

    assert row["00631l_target_weight_increasing"] is False
    assert row["would_trigger_add_0050_instead"] is False
    assert row["would_be_redirect_amount"] == 0.0


def test_no_trigger_when_increasing_but_not_narrow_lead():
    targets = _targets(["2026-08-06", "2026-08-07"], [0.1, 0.2])
    narrow_lead = pd.Series([False, False], index=targets.index)

    row = build_shadow_log_row(target_weights=targets, narrow_lead=narrow_lead)

    assert row["narrow_lead"] is False
    assert row["would_trigger_add_0050_instead"] is False


def test_insufficient_history_is_unavailable():
    targets = _targets(["2026-08-07"], [0.2])
    narrow_lead = pd.Series([True], index=targets.index)

    row = build_shadow_log_row(target_weights=targets, narrow_lead=narrow_lead)

    assert row["status"] == "unavailable"
    assert row["reason"] == "insufficient_target_weight_history"


def test_append_shadow_log_row_dedupes_by_date(tmp_path):
    log_path = tmp_path / "shadow_log.jsonl"
    row = {"status": "available", "date": "2026-08-07", "would_trigger_add_0050_instead": False}

    assert append_shadow_log_row(row, log_path) is True
    assert append_shadow_log_row(row, log_path) is False

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["date"] == "2026-08-07"


def test_append_shadow_log_row_skips_unavailable_rows(tmp_path):
    log_path = tmp_path / "shadow_log.jsonl"
    row = {"status": "unavailable", "reason": "insufficient_target_weight_history"}

    assert append_shadow_log_row(row, log_path) is False
    assert not log_path.exists()
