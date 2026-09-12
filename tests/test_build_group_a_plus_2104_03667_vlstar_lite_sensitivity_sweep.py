from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate.build_group_a_plus_2104_03667_vlstar_lite_sensitivity_sweep import (
    run_sweep,
    write_sweep,
)

CORE_TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO")


def _seed_db(path: Path, n_days: int = 900) -> None:
    idx = pd.bdate_range("2022-01-03", periods=n_days)
    prices = {t: 100.0 for t in CORE_TICKERS}
    rows = []
    for i, dt in enumerate(idx):
        stress = (i % 90) < 15
        base_ret = (-0.012 - 0.001 * (i % 5)) if stress else (0.0025 if i % 2 == 0 else -0.0008)
        rets = {
            "0050.TW": base_ret,
            "00631L.TW": base_ret * 2.0,
            "00632R.TW": -base_ret * 0.9,
            "00679B.TWO": 0.0003 if stress else 0.0001,
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


def _seed_switch_curve(path: Path, n_days: int = 900) -> None:
    idx = pd.bdate_range("2022-01-03", periods=n_days)
    golden = 1_000_000.0
    defensive = 1_000_000.0
    switch = 1_000_000.0
    rows = []
    for i, dt in enumerate(idx):
        stress = (i % 90) < 15
        golden *= 1.0 + (-0.01 if stress else 0.0015)
        defensive *= 1.0 + (-0.002 if stress else 0.0006)
        switch *= 1.0 + (-0.003 if stress else 0.0012)
        rows.append(
            {
                "dt": str(dt.date()),
                "golden1_0531_1m": golden,
                "group_a_plus_defensive_1m": defensive,
                "switch_risk_ma80_dd11_total6_hold5_eg015_xg015": switch,
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)


def test_sweep_covers_full_grid_and_stays_shadow_only(tmp_path: Path) -> None:
    db = tmp_path / "stock.db"
    curve = tmp_path / "curve.csv"
    _seed_db(db)
    _seed_switch_curve(curve)

    result = run_sweep(
        db_path=db,
        switch_curve_path=curve,
        core_tickers=CORE_TICKERS,
        gamma_scale_grid=(1.0, 3.0),
        threshold_grid=(0.5, 0.7, 0.9),
        min_hold_days=5,
    )

    assert result["status"] == "available_for_shadow_monitoring"
    assert result["n_combinations"] == 6
    assert len(result["sweep_results"]) == 6
    assert result["target_weight_change_allowed"] is False
    assert result["replace_a2118"] is False
    assert result["train_vlstar_now"] is False

    for row in result["sweep_results"]:
        assert 0.0 <= row["volatile_share"] <= 1.0
        assert "sharpe" in row["test_a_momentum_filter"]
        assert "test_b_switch_blend" in row  # curve was provided


def test_sweep_blocks_on_insufficient_history(tmp_path: Path) -> None:
    db = tmp_path / "tiny.db"
    _seed_db(db, n_days=10)

    result = run_sweep(db_path=db, core_tickers=CORE_TICKERS)

    # Either blocked outright, or every combo degenerates safely -- either way
    # governance decisions must never flip to allow a live weight change.
    assert result["target_weight_change_allowed"] is False


def test_write_sweep_roundtrips(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    result = {"paper": "arXiv:2104.03667", "status": "available_for_shadow_monitoring"}

    write_sweep(result, output)

    assert json.loads(output.read_text(encoding="utf-8")) == result
