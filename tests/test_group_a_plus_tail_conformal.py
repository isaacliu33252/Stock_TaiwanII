from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from group_a_plus.integrations.tail_conformal import compute_tail_conformal_diagnostic


def _write_631l_ohlcv(db_path: Path) -> None:
    dates = pd.bdate_range("2025-01-02", "2026-07-10")
    con = duckdb.connect(str(db_path))
    try:
        con.execute("CREATE TABLE ohlcv (ticker TEXT, dt DATE, open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume DOUBLE)")
        price = 100.0
        for i, dt in enumerate(dates):
            if i % 47 == 0:
                price *= 0.91
            elif i % 19 == 0:
                price *= 1.035
            else:
                price *= 1.001
            con.execute(
                "INSERT INTO ohlcv VALUES (?, ?, ?, ?, ?, ?, ?)",
                ["00631L.TW", str(dt.date()), price, price, price, price, 1000.0],
            )
    finally:
        con.close()


def test_tail_conformal_outputs_lower_bounds_and_warning_policy(tmp_path: Path) -> None:
    db_path = tmp_path / "market.duckdb"
    _write_631l_ohlcv(db_path)

    result = compute_tail_conformal_diagnostic(
        db_path=db_path,
        actual_date=pd.Timestamp("2026-07-10"),
        latest_features={"total_risk_score": 9, "tail_risk_score": 2},
    )

    assert result["status"] == "ok"
    assert result["policy"] == "diagnostic_warning_only_no_weight_change"
    assert result["auto_reduce_00631l"] is False
    assert result["ticker"] == "00631L.TW"
    assert "h5" in result["diagnostics"]
    assert "h10" in result["diagnostics"]
    assert result["diagnostics"]["h5"]["lower_tail_confidence_bound"] is not None
    assert result["diagnostics"]["h10"]["prob_mdd_lt_8pct"] is not None
