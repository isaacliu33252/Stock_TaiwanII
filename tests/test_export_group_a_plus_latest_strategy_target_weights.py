from __future__ import annotations

import sys

import duckdb
import pandas as pd

from scripts.evaluate import export_group_a_plus_latest_strategy_target_weights as exporter


def test_latest_strategy_target_weight_export_defaults_to_latest_end(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["export_group_a_plus_latest_strategy_target_weights.py"])

    args = exporter.parse_args()

    assert args.end == "latest"


def test_latest_strategy_target_weight_export_resolves_latest_end(tmp_path) -> None:
    db_path = tmp_path / "stock_data.db"
    con = duckdb.connect(str(db_path))
    con.execute("CREATE TABLE ohlcv (dt DATE, ticker VARCHAR, close DOUBLE)")
    con.execute(
        "INSERT INTO ohlcv VALUES (?, ?, ?), (?, ?, ?), (?, ?, ?)",
        ["2026-09-09", "0050.TW", 1.0, "2026-09-10", "0050.TW", 1.0, "2026-09-11", "00631L.TW", 1.0],
    )
    con.close()

    assert exporter._resolve_latest_end(db_path, "latest") == "2026-09-10"


def test_latest_strategy_target_weight_export_expands_regime_weights() -> None:
    report = {
        "active_strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
        "base_weights": {
            "golden1": {"0050.TW": 0.6, "00631L.TW": 0.2, "00632R.TW": 0.0, "00679B.TWO": 0.1, "cash": 0.1},
            "group_a_plus_defensive": {"0050.TW": 0.4, "00679B.TWO": 0.3, "cash": 0.3},
        },
    }
    frame = pd.DataFrame(
        {"execution_regime": ["golden1", "group_a_plus_defensive"]},
        index=pd.to_datetime(["2026-01-02", "2026-01-05"]),
    )

    export, rows = exporter.build_target_weight_export(latest_report=report, latest_frame=frame)

    assert export["status"] == "available"
    assert export["decision"]["historical_target_weight_series_available"] is True
    assert export["decision"]["creates_orders"] is False
    assert export["decision"]["changes_latest_strategy"] is False
    assert export["row_count"] == 2
    assert rows.loc[0, "target_weight_0050"] == 0.6
    assert rows.loc[0, "target_weight_00631L"] == 0.2
    assert rows.loc[0, "target_weight_00679B"] == 0.1
    assert rows.loc[1, "target_weight_cash"] == 0.3


def test_latest_strategy_target_weight_export_blocks_missing_regime_weight() -> None:
    report = {"base_weights": {"golden1": {"0050.TW": 1.0}}}
    frame = pd.DataFrame(
        {"execution_regime": ["golden1", "missing_regime"]},
        index=pd.to_datetime(["2026-01-02", "2026-01-05"]),
    )

    export, _ = exporter.build_target_weight_export(latest_report=report, latest_frame=frame)

    assert export["status"] == "blocked"
    assert "missing_weights_for_execution_regimes" in export["blocking_reasons"]
    assert export["missing_execution_regimes"] == ["missing_regime"]
