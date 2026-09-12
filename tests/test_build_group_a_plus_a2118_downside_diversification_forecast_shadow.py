from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate.build_group_a_plus_a2118_downside_diversification_forecast_shadow import (
    build_shadow,
    write_shadow,
)


def _seed_db(path: Path) -> None:
    idx = pd.bdate_range("2024-01-01", periods=260)
    prices = {
        "0050.TW": 100.0,
        "00679B.TWO": 100.0,
        "0056.TW": 100.0,
        "00713.TW": 100.0,
    }
    rows = []
    for i, dt in enumerate(idx):
        base_stress = i % 10 in {0, 1, 2}
        base_ret = (-0.012 - 0.001 * (i % 3)) if base_stress else 0.004
        bad_regime = i >= 80
        rets = {
            "0050.TW": base_ret,
            "00679B.TWO": 0.001 if base_stress else (-0.0005 if i % 7 == 0 else 0.0004),
            "0056.TW": base_ret * 0.95 if bad_regime and base_stress else 0.003,
            "00713.TW": 0.004 if base_stress else (-0.001 if i % 4 == 0 else 0.0005),
        }
        for ticker, ret in rets.items():
            prices[ticker] *= 1.0 + ret
            rows.append({"dt": str(dt.date()), "ticker": ticker, "close": prices[ticker]})

    con = duckdb.connect(str(path))
    try:
        con.execute("CREATE TABLE ohlcv (dt DATE, ticker VARCHAR, close DOUBLE)")
        con.register("rows", pd.DataFrame(rows))
        con.execute("INSERT INTO ohlcv SELECT * FROM rows")
    finally:
        con.close()


def test_downside_diversification_forecast_shadow_detects_oos_bucket_value(tmp_path: Path) -> None:
    db = tmp_path / "stock.db"
    _seed_db(db)

    shadow = build_shadow(
        db_path=db,
        start="2024-01-01",
        end="2024-12-31",
        fifth_candidates=("0056.TW", "00713.TW"),
        windows=(20, 60),
        forecast_horizon=20,
        min_history=80,
        good_threshold=0.25,
        failed_threshold=0.55,
    )

    assert shadow["report_type"] == "a2118_downside_diversification_forecast_shadow"
    assert shadow["status"] == "available_for_shadow_monitoring"
    assert shadow["method_scope"]["target_weight_change_allowed"] is False
    assert shadow["method_scope"]["parameter_sweep_allowed"] is False
    assert shadow["decision"]["target_weight_change_allowed"] is False
    assert shadow["decision"]["replace_a2118"] is False
    assert shadow["coverage"]["prediction_rows"] > 0

    assert any(row["model"] == "shrinkage" for row in shadow["model_comparison"])
    assert any(row["bucket_ordering_pass"] for row in shadow["model_comparison"])
    failed_signals = [
        row
        for row in shadow["economic_filter_review"]
        if row["pair"] == "0050.TW_0056.TW" and row["failed_signal_count"] > 0
    ]
    assert failed_signals
    assert any(row["net_filter_value"] is not None for row in failed_signals)


def test_downside_diversification_forecast_shadow_blocks_missing_database(tmp_path: Path) -> None:
    shadow = build_shadow(db_path=tmp_path / "missing.db", end="2024-12-31")

    assert shadow["status"] == "blocked"
    assert "stock_database_missing" in shadow["blocking_reasons"]
    assert shadow["decision"]["target_weight_change_allowed"] is False
    assert shadow["decision"]["advance_to_transformer_research"] is False


def test_write_downside_diversification_forecast_shadow_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    shadow = {
        "report_type": "a2118_downside_diversification_forecast_shadow",
        "as_of": "2026-08-24",
        "decision": {"target_weight_change_allowed": False},
    }

    write_shadow(shadow, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == shadow
    assert (history / "a2118_downside_diversification_forecast_shadow_20260824.json").exists()
