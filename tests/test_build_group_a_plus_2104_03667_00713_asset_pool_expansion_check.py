from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate.build_group_a_plus_2104_03667_00713_asset_pool_expansion_check import (
    build_comparison,
    write_comparison,
)

TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO", "00713.TW")


def _seed_db(path: Path, n_days: int = 900) -> None:
    idx = pd.bdate_range("2022-01-03", periods=n_days)
    prices = {t: 100.0 for t in TICKERS}
    rows = []
    for i, dt in enumerate(idx):
        stress = (i % 90) < 15
        base_ret = (-0.012 - 0.001 * (i % 5)) if stress else (0.0025 if i % 2 == 0 else -0.0008)
        rets = {
            "0050.TW": base_ret,
            "00631L.TW": base_ret * 2.0,
            "00632R.TW": -base_ret * 0.9,
            "00679B.TWO": 0.0003 if stress else 0.0001,
            "00713.TW": base_ret * 0.6,
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


def test_comparison_runs_and_reports_both_directions(tmp_path: Path) -> None:
    db = tmp_path / "stock.db"
    _seed_db(db)

    result = build_comparison(db_path=db, baseline_report_path=tmp_path / "missing_baseline.json")

    assert result["status"] == "closed"
    assert result["target_weight_change_allowed"] is False
    assert result["replace_a2118"] is False
    assert result["train_vlstar_now"] is False

    c = result["comparison"]
    assert c["expanded_tickers"] == list(TICKERS)
    assert "00713.TW" not in c["baseline_tickers"]
    assert "expansion_helps_test_a" in c
    assert "expansion_helps_test_b" in c
    assert isinstance(c["expansion_helps_test_a"], bool)
    assert isinstance(c["expansion_helps_test_b"], bool)


def test_write_comparison_roundtrips(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    result = {"paper": "arXiv:2104.03667", "status": "closed"}

    write_comparison(result, output)

    assert json.loads(output.read_text(encoding="utf-8")) == result
