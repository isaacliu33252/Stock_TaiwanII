from __future__ import annotations

import json
from pathlib import Path

import duckdb

from scripts.evaluate.validate_group_a_plus_2604_02126_robust_hedge_temporal_oos import (
    _parse_windows,
    build_temporal_oos,
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
        inverse = 25.0
        for idx in range(260):
            dt = f"2026-{(idx // 28) % 12 + 1:02d}-{idx % 28 + 1:02d}"
            ret = 0.0015 if idx % 3 else -0.004
            if idx % 47 == 0:
                ret -= 0.009
            asset *= 1.0 + ret
            inverse *= 1.0 - 0.9 * ret - 0.0001
            for ticker, close in (("0050.TW", asset), ("00632R.TW", inverse)):
                rows.append((ticker, dt, close, close, close, close, 1000, 0.0, 0.0, "test", "2026-12-31 00:00:00"))
        conn.executemany("INSERT INTO ohlcv VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_parse_windows() -> None:
    assert _parse_windows("a:2020-01-01:2020-12-31") == [
        {"label": "a", "start": "2020-01-01", "end": "2020-12-31"}
    ]


def test_temporal_oos_stays_blocked_and_research_only(tmp_path: Path) -> None:
    db = tmp_path / "stock_data.db"
    _make_db(db)
    sweep = {
        "report_type": "group_a_plus_2604_02126_robust_hedge_sweep",
        "all_rows": [{"window": 20, "uncertainty_window": 20, "max_hedge_weight": 0.1}],
    }

    report = build_temporal_oos(
        sweep=sweep,
        db_path=db,
        windows=[{"label": "sample", "start": "2026-01-01", "end": "2026-10-08"}],
        letf_readiness_path=_write(tmp_path / "letf.json", {"decision": {"allow_00632r_open": False}}),
        latest_strategy_path=_write(tmp_path / "latest.json", {"data": {"target_weights": {"00632R.TW": 0.12}}}),
    )

    assert report["report_type"] == "group_a_plus_2604_02126_robust_hedge_temporal_oos"
    assert report["parameter_count"] == 1
    assert report["decision"]["temporal_oos_complete"] is True
    assert report["decision"]["promote_to_live"] is False
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["decision"]["auto_rebalance_allowed"] is False
    assert report["decision"]["allow_00632r_open"] is False
    assert "research_only_temporal_oos" in report["blocking_reasons"]


def test_temporal_oos_blocks_missing_parameters(tmp_path: Path) -> None:
    report = build_temporal_oos(
        sweep={},
        db_path=tmp_path / "missing.db",
        windows=[{"label": "sample", "start": "2026-01-01", "end": "2026-12-31"}],
        letf_readiness_path=tmp_path / "missing_letf.json",
        latest_strategy_path=tmp_path / "missing_latest.json",
    )

    assert report["parameter_count"] == 0
    assert report["decision"]["temporal_oos_complete"] is False
    assert "no_parameter_set_passed_all_temporal_windows" in report["blocking_reasons"]


def test_render_markdown_contains_blocked_decision() -> None:
    report = {
        "generated_at": "2026-08-29T00:00:00",
        "status": "blocked_for_live_promotion",
        "parameter_count": 1,
        "eligible_parameter_count": 0,
        "best_rows": [
            {
                "window": 20,
                "uncertainty_window": 20,
                "max_hedge_weight": 0.1,
                "valid_window_count": 1,
                "passed_window_count": 0,
                "mean_robust_turnover_reduction": -0.1,
                "mean_robust_conditional_he_delta": -0.2,
                "all_valid_windows_passed": False,
            }
        ],
        "blocking_reasons": ["research_only_temporal_oos"],
    }

    markdown = render_markdown(report)

    assert "Do not open or increase `00632R.TW`" in markdown
    assert "| 20 | 20 | 0.10 |" in markdown


def test_write_report_writes_outputs(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "temporal.json"
    output_md = tmp_path / "latest" / "temporal.md"
    history = tmp_path / "history"
    report = {
        "report_type": "group_a_plus_2604_02126_robust_hedge_temporal_oos",
        "generated_at": "2026-08-29T00:00:00",
        "status": "blocked_for_live_promotion",
        "parameter_count": 0,
        "eligible_parameter_count": 0,
        "best_rows": [],
        "blocking_reasons": [],
    }

    write_report(report, output, output_md, history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert "2604.02126 Robust Hedge Temporal OOS" in output_md.read_text(encoding="utf-8")
    assert list(history.glob("2604_02126_robust_hedge_temporal_oos_*.json"))
