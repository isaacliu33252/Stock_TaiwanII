from __future__ import annotations

import json
from pathlib import Path

import duckdb

from scripts.evaluate.build_group_a_plus_securities_lending_source_status import build_status, write_outputs


def test_securities_lending_status_records_provider_no_rows(tmp_path: Path) -> None:
    db = tmp_path / "stock_data.db"
    con = duckdb.connect(str(db))
    con.execute(
        """
        CREATE TABLE securities_lending_data (
            ticker TEXT,
            dt DATE,
            volume DOUBLE
        )
        """
    )
    con.execute("INSERT INTO securities_lending_data VALUES ('0050.TW', DATE '2026-07-17', 5000.0)")
    con.close()

    status = build_status(
        db_path=db,
        ticker="0050.TW",
        query_start="2026-07-18",
        query_end="2026-07-22",
        provider_rows_written=0,
        provider_message="FinMind securities_lending 0050: no rows",
        as_of="2026-07-23",
    )

    assert status["status"] == "provider_no_rows"
    assert status["summary"]["provider_no_rows_confirmed"] is True
    assert status["summary"]["latest_available_dt"] == "2026-07-17"
    assert status["summary"]["db_lagged_after_query"] is True
    assert status["decision"]["blocks_deployment"] is False
    assert status["decision"]["target_weight_change_allowed"] is False
    assert status["decision"]["keep_golden1_0531_unchanged"] is True


def test_write_outputs_writes_json_markdown_and_history(tmp_path: Path) -> None:
    status = {
        "as_of": "2026-07-23",
        "status": "provider_no_rows",
        "ticker": "0050.TW",
        "query_window": {"start": "2026-07-18", "end": "2026-07-22"},
        "provider_observation": {"rows_written": 0, "message": "no rows"},
        "database_observation": {"latest_dt": "2026-07-17"},
        "summary": {
            "provider_no_rows_confirmed": True,
            "db_lagged_after_query": True,
            "soft_source": True,
            "keep_golden1_0531_unchanged": True,
        },
        "decision": {"blocks_deployment": False},
    }
    output = tmp_path / "latest" / "status.json"
    output_md = tmp_path / "latest" / "status.md"
    history = tmp_path / "history"

    write_outputs(status, output=output, output_md=output_md, history_dir=history)

    assert json.loads(output.read_text(encoding="utf-8")) == status
    assert "Provider no rows confirmed" in output_md.read_text(encoding="utf-8")
    assert (history / "securities_lending_0050_source_status_20260723.json").exists()
