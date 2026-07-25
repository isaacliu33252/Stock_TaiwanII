from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.evaluate.build_group_a_plus_broker_holdings_time_series_sample import (
    build_sample,
    write_sample,
)


def test_build_sample_from_transaction_xlsx_marks_incomplete_positions(tmp_path: Path) -> None:
    source = tmp_path / "transactions.xlsx"
    pd.DataFrame(
        [
            {
                "成交日期": "2925-06-13",
                "交易類別": "現股買進",
                "股票名稱": "元大台灣50正2",
                "成交股數": 100,
                "成交單價": 40.0,
                "成交價金": 4000,
                "手續費": 5,
                "交易稅": 0,
                "淨收付金額": -4005,
            },
            {
                "成交日期": "2026-07-17",
                "交易類別": "現股賣出",
                "股票名稱": "元大台灣50",
                "成交股數": 200,
                "成交單價": 100.0,
                "成交價金": 20000,
                "手續費": 28,
                "交易稅": 60,
                "淨收付金額": 19912,
            },
        ]
    ).to_excel(source, index=False)

    sample = build_sample(input_path=source)

    assert sample["status"] == "sample_available"
    assert sample["authoritative_broker_export"] is False
    assert sample["coverage"]["first_transaction_date"] == "2025-06-13"
    assert sample["coverage"]["last_transaction_date"] == "2026-07-17"
    assert sample["latest_positions"]["00631L.TW"] == 100
    assert sample["latest_positions"]["0050.TW"] == -200
    assert sample["negative_positions"] == {"0050.TW": -200}


def test_write_sample_writes_output_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history_dir = tmp_path / "history"
    sample = {
        "report_type": "group_a_plus_broker_holdings_time_series_sample",
        "coverage": {"last_transaction_date": "2026-07-17"},
    }

    write_sample(sample, output, history_dir)

    assert json.loads(output.read_text(encoding="utf-8")) == sample
    assert json.loads((history_dir / "20260717.json").read_text(encoding="utf-8")) == sample
