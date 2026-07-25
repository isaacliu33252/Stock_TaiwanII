from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate.build_group_a_plus_00632r_effective_fee_proxy_validation_review import (
    build_review,
    write_review,
)


def _tail_gate(path: Path) -> Path:
    path.write_text(
        json.dumps({"decision": {"gate_split_recommended": True, "allow_00632r_open": False}}),
        encoding="utf-8",
    )
    return path


def _db(path: Path, rows: int = 220) -> Path:
    dates = pd.bdate_range("2025-01-01", periods=rows)
    ref = 100.0
    inv = 30.0
    payload = []
    for idx, dt in enumerate(dates):
        ret = 0.004 if idx % 5 else -0.006
        ref *= 1.0 + ret
        inv *= 1.0 - ret + 0.0001
        for ticker, close in [("0050.TW", ref), ("00632R.TW", inv)]:
            payload.append(
                {
                    "ticker": ticker,
                    "dt": dt.date(),
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "volume": 1_000_000,
                }
            )
    con = duckdb.connect(str(path))
    try:
        con.execute(
            """
            CREATE TABLE ohlcv (
                ticker TEXT,
                dt DATE,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume BIGINT
            )
            """
        )
        df = pd.DataFrame(payload)
        con.register("df", df)
        con.execute("INSERT INTO ohlcv SELECT * FROM df")
        con.unregister("df")
    finally:
        con.close()
    return path


def test_build_review_validates_proxy_for_manual_review_only(tmp_path: Path) -> None:
    review = build_review(
        db_path=_db(tmp_path / "stock_data.db"),
        tail_gate_path=_tail_gate(tmp_path / "tail.json"),
        as_of="2026-07-20",
        start="2025-01-01",
        horizons=[5, 10],
        correlation_floor=0.90,
        sign_agreement_floor=0.70,
        tail_overlap_floor=0.60,
    )

    assert review["report_type"] == "group_a_plus_00632r_effective_fee_proxy_validation_review"
    assert review["status"] == "validated_for_manual_review_only"
    assert review["summary"]["proxy_validated_for_manual_review"] is True
    assert review["summary"]["failed_horizons"] == []
    assert review["decision"]["effective_fee_proxy_validated_for_manual_review"] is True
    assert review["decision"]["effective_fee_proxy_validated_for_live"] is False
    assert review["decision"]["manual_hedge_discussion_allowed"] is False
    assert review["decision"]["allow_00632r_open"] is False
    assert review["decision"]["target_weight_change_allowed"] is False


def test_build_review_blocks_missing_tail_gate(tmp_path: Path) -> None:
    review = build_review(
        db_path=_db(tmp_path / "stock_data.db"),
        tail_gate_path=tmp_path / "missing_tail.json",
        as_of="2026-07-20",
        start="2025-01-01",
        horizons=[5],
        correlation_floor=0.90,
        sign_agreement_floor=0.70,
        tail_overlap_floor=0.60,
    )

    assert review["status"] == "blocked"
    assert "missing_tail_tracking_error_gate_review" in review["blocking_reasons"]
    assert review["decision"]["allow_00632r_open"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "effective_fee.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_00632r_effective_fee_proxy_validation_review",
        "as_of": "2026-07-20",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "00632r_effective_fee_proxy_validation_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
