from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.evaluate.import_group_a_plus_authoritative_workbook_snapshot import (
    build_authoritative_outputs,
    parse_flat_workbook_holdings,
)


def _write_workbook(path: Path) -> Path:
    frame = pd.DataFrame(
        [
            ["2026-08-24", None, None, None, None],
            [None, "元大台灣50\n0050", "元大台灣50正2\n00631L", "元大美債20年\n00679B", "元大AAA至A公司債\n00751B"],
            ["即時庫存", 4471, 580, 100, 100],
        ]
    )
    frame.to_excel(path, index=False, header=False)
    return path


def test_parse_flat_workbook_holdings(tmp_path: Path) -> None:
    path = _write_workbook(tmp_path / "holdings.xlsx")

    as_of, holdings = parse_flat_workbook_holdings(path)

    assert as_of == "2026-08-24"
    assert holdings["0050.TW"] == 4471
    assert holdings["00631L.TW"] == 580
    assert holdings["00679B.TWO"] == 100
    assert holdings["00751B.TWO"] == 100


def test_build_authoritative_outputs_marks_user_workbook_as_reconciliation_ready(tmp_path: Path) -> None:
    path = _write_workbook(tmp_path / "holdings.xlsx")

    sample, holdings = build_authoritative_outputs(input_path=path, cash_balance=1_000_000.0, db_path=tmp_path / "missing.db")

    assert sample["status"] == "authoritative_sample_ready"
    assert sample["authoritative_broker_export"] is True
    assert sample["cash_balance"] == 1_000_000.0
    assert sample["latest_positions"]["0050.TW"] == 4471
    assert sample["latest_positions"]["00631L.TW"] == 580
    assert sample["latest_positions"]["00632R.TW"] == 0
    assert sample["warnings"] == [
        "source_is_user_supplied_workbook_not_broker_api_export",
        "excluded_non_group_a_plus_positions_present",
    ]
    assert sample["excluded_non_group_a_plus_positions"] == {"00751B.TWO": 100}
    assert "00751B.TWO" not in holdings["holdings"]
    assert holdings["excluded_non_group_a_plus_positions"] == {"00751B.TWO": 100}
