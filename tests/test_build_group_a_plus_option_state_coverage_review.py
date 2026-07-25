from __future__ import annotations

import json
from pathlib import Path

import duckdb

from scripts.evaluate.build_group_a_plus_option_state_coverage_review import build_review, write_review


def test_write_review_writes_latest_and_history_snapshot(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "option_state_coverage_review.json"
    history_dir = tmp_path / "history"
    review = {
        "schema_version": 1,
        "report_type": "group_a_plus_option_state_coverage_review",
        "status": "blocked",
        "as_of": "2026-07-17",
        "blocking_reasons": ["soxx_options_iv_history_lt_20_snapshots"],
    }

    write_review(review, output_path=output, history_dir=history_dir)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_path = history_dir / "20260717.json"
    assert json.loads(history_path.read_text(encoding="utf-8")) == review


def test_write_review_can_disable_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "option_state_coverage_review.json"
    history_dir = tmp_path / "history"
    review = {
        "schema_version": 1,
        "report_type": "group_a_plus_option_state_coverage_review",
        "status": "available",
        "as_of": "2026-07-20",
        "blocking_reasons": [],
    }

    write_review(review, output_path=output, history_dir=None)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    assert not history_dir.exists()


def test_build_review_thresholds_can_be_shadow_tuned(tmp_path: Path) -> None:
    db_path = tmp_path / "stock_data.db"
    con = duckdb.connect(str(db_path))
    try:
        con.execute("CREATE TABLE taifex_options_daily (dt DATE)")
        con.execute("INSERT INTO taifex_options_daily VALUES ('2026-07-16')")
        con.execute(
            """
            CREATE TABLE external_options_iv (
                provider TEXT,
                underlying TEXT,
                dt DATE,
                atm_iv DOUBLE,
                put_call_iv_skew DOUBLE,
                put_call_volume_ratio DOUBLE,
                put_call_oi_ratio DOUBLE,
                contract_count DOUBLE
            )
            """
        )
        con.execute(
            """
            INSERT INTO external_options_iv VALUES
            ('yfinance', 'SOXX', '2026-07-10', 0.001, 0.0, 5.0, NULL, 100),
            ('yfinance', 'SOXX', '2026-07-14', 0.62, 0.1, 6.0, 2.8, 100),
            ('yfinance', 'SOXX', '2026-07-15', 0.002, 0.0, 2.0, NULL, 100),
            ('yfinance', 'SOXX', '2026-07-16', 0.06, 0.0, 1.8, 2.4, 100)
            """
        )
    finally:
        con.close()

    strict = build_review(db_path, "2026-07-17")
    relaxed = build_review(
        db_path,
        "2026-07-17",
        soxx_options_snapshot_rows_min=4,
        soxx_options_valid_atm_iv_rows_min=2,
    )

    assert strict["status"] == "blocked"
    assert strict["blocking_reasons"] == [
        "soxx_options_iv_history_lt_20_snapshots",
        "soxx_options_iv_valid_history_lt_10_snapshots",
    ]
    assert relaxed["status"] == "available"
    assert relaxed["decision"]["option_state_gate_passed"] is True
    assert relaxed["requirements"]["soxx_options_snapshot_rows_min"] == 4
