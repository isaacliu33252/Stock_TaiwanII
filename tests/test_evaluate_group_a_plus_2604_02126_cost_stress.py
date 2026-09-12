from __future__ import annotations

import json
from pathlib import Path

import duckdb

from scripts.evaluate.evaluate_group_a_plus_2604_02126_cost_stress import (
    build_cost_stress,
    render_markdown,
    write_report,
)


def _make_db(path: Path) -> None:
    with duckdb.connect(str(path)) as conn:
        conn.execute(
            """
            CREATE TABLE ohlcv (
                ticker VARCHAR,
                dt DATE,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume BIGINT,
                dividends DOUBLE,
                stock_splits DOUBLE,
                source_file VARCHAR,
                updated_at TIMESTAMP
            )
            """
        )
        rows = []
        asset = 100.0
        inverse = 22.0
        for idx in range(240):
            dt = f"2026-{(idx // 28) % 12 + 1:02d}-{idx % 28 + 1:02d}"
            ret = 0.001 if idx % 4 else -0.005
            if idx % 43 == 0:
                ret -= 0.01
            asset *= 1.0 + ret
            inverse *= 1.0 - 0.9 * ret - 0.0001
            for ticker, close in (("0050.TW", asset), ("00632R.TW", inverse)):
                rows.append((ticker, dt, close, close, close, close, 1000, 0.0, 0.0, "test", "2026-12-31 00:00:00"))
        conn.executemany("INSERT INTO ohlcv VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)


def test_cost_stress_stays_blocked(tmp_path: Path) -> None:
    db = tmp_path / "stock_data.db"
    _make_db(db)

    report = build_cost_stress(
        db_path=db,
        as_of="2026-09-01",
        start="2026-01-01",
        models=["rolling_mean", "ar1"],
        cost_bps_values=[0.0, 10.0],
        window=40,
        uncertainty_window=40,
        cap=0.2,
    )

    assert report["report_type"] == "group_a_plus_2604_02126_cost_stress"
    assert report["status"] == "blocked_for_live_promotion"
    assert report["grid"]["scenario_count"] == 4
    assert report["decision"]["cost_stress_complete"] is True
    assert report["decision"]["promote_to_live"] is False
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["decision"]["allow_00632r_open"] is False
    assert "research_only_transaction_cost_stress" in report["blocking_reasons"]


def test_render_markdown_contains_cost_rows() -> None:
    report = {
        "generated_at": "2026-08-29T00:00:00",
        "as_of": "2026-08-28",
        "status": "blocked_for_live_promotion",
        "rows": [
            {
                "model": "rolling_mean",
                "cost_bps": 10.0,
                "robust_minus_standard": {
                    "total_log_return": -0.1,
                    "annualized_sharpe": -0.2,
                    "max_drawdown": -0.03,
                },
                "passes_cost_filter": False,
            }
        ],
        "blocking_reasons": ["research_only_transaction_cost_stress"],
    }

    markdown = render_markdown(report)

    assert "2604.02126 Cost Stress" in markdown
    assert "| rolling_mean | 10.0 |" in markdown
    assert "Do not open or increase `00632R.TW`" in markdown


def test_write_report_writes_outputs(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "cost.json"
    output_md = tmp_path / "latest" / "cost.md"
    history = tmp_path / "history"
    report = {
        "report_type": "group_a_plus_2604_02126_cost_stress",
        "generated_at": "2026-08-29T00:00:00",
        "as_of": "2026-08-28",
        "status": "blocked_for_live_promotion",
        "rows": [],
        "blocking_reasons": [],
    }

    write_report(report, output, output_md, history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert "2604.02126 Cost Stress" in output_md.read_text(encoding="utf-8")
    history_file = history / "2604_02126_cost_stress_20260828.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == report
