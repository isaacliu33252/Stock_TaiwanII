from __future__ import annotations

import json
from pathlib import Path

import duckdb

from scripts.evaluate.sweep_group_a_plus_2604_02126_robust_hedge import (
    build_sweep,
    render_markdown,
    write_sweep,
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
        inverse = 30.0
        for idx in range(260):
            dt = f"2026-{(idx // 28) % 12 + 1:02d}-{idx % 28 + 1:02d}"
            ret = 0.002 if idx % 4 else -0.005
            if idx % 41 == 0:
                ret -= 0.01
            asset *= 1.0 + ret
            inverse *= 1.0 - 0.95 * ret - 0.0001
            for ticker, close in (("0050.TW", asset), ("00632R.TW", inverse)):
                rows.append((ticker, dt, close, close, close, close, 1000, 0.0, 0.0, "test", "2026-12-31 00:00:00"))
        conn.executemany("INSERT INTO ohlcv VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_build_sweep_stays_research_only(tmp_path: Path) -> None:
    db = tmp_path / "stock_data.db"
    _make_db(db)

    sweep = build_sweep(
        db_path=db,
        as_of="2026-10-08",
        start="2026-01-01",
        windows=[20, 40],
        uncertainty_windows=[20, 40],
        caps=[0.1, 0.2],
        letf_readiness_path=_write(tmp_path / "letf.json", {"decision": {"allow_00632r_open": False}}),
        latest_strategy_path=_write(tmp_path / "latest.json", {"data": {"target_weights": {"00632R.TW": 0.12}}}),
    )

    assert sweep["report_type"] == "group_a_plus_2604_02126_robust_hedge_sweep"
    assert sweep["grid"]["parameter_count"] == 8
    assert sweep["decision"]["sweep_complete"] is True
    assert sweep["decision"]["promote_to_live"] is False
    assert sweep["decision"]["target_weight_change_allowed"] is False
    assert sweep["decision"]["auto_rebalance_allowed"] is False
    assert sweep["decision"]["allow_00632r_open"] is False
    assert "research_only_parameter_sweep" in sweep["blocking_reasons"]
    assert len(sweep["best_rows"]) > 0


def test_render_markdown_contains_decision(tmp_path: Path) -> None:
    sweep = {
        "generated_at": "2026-08-29T00:00:00",
        "as_of": "2026-08-28",
        "status": "blocked_for_live_promotion",
        "grid": {"parameter_count": 1},
        "eligible_parameter_count": 0,
        "best_rows": [
            {
                "window": 20,
                "uncertainty_window": 20,
                "max_hedge_weight": 0.1,
                "score": 0.0,
                "robust_latest_exposure": 0.1,
                "robust_turnover_reduction_vs_standard": -0.1,
                "robust_exposure_std_reduction_vs_standard": -0.2,
                "robust_conditional_he": 0.1,
                "standard_conditional_he": 0.2,
                "passes_shadow_filter": False,
            }
        ],
        "blocking_reasons": ["research_only_parameter_sweep"],
    }

    markdown = render_markdown(sweep)

    assert "Do not open or increase `00632R.TW`" in markdown
    assert "| 20 | 20 | 0.10 |" in markdown


def test_write_sweep_writes_outputs(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "sweep.json"
    output_md = tmp_path / "latest" / "sweep.md"
    history = tmp_path / "history"
    sweep = {
        "report_type": "group_a_plus_2604_02126_robust_hedge_sweep",
        "generated_at": "2026-08-29T00:00:00",
        "as_of": "2026-08-28",
        "status": "blocked_for_live_promotion",
        "grid": {"parameter_count": 0},
        "eligible_parameter_count": 0,
        "best_rows": [],
        "blocking_reasons": [],
    }

    write_sweep(sweep, output, output_md, history)

    assert json.loads(output.read_text(encoding="utf-8")) == sweep
    assert "2604.02126 Robust Hedge Parameter Sweep" in output_md.read_text(encoding="utf-8")
    history_file = history / "2604_02126_robust_hedge_sweep_20260828.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == sweep
