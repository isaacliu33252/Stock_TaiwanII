from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate.build_group_a_plus_2104_03667_regime_clustering_review import (
    build_review,
    write_review,
)


CORE_TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO")


def _seed_db(path: Path, n_days: int = 900) -> None:
    idx = pd.bdate_range("2022-01-03", periods=n_days)
    prices = {t: 100.0 for t in CORE_TICKERS}
    rows = []
    for i, dt in enumerate(idx):
        stress = (i % 90) < 15  # recurring stress blocks so both regimes are populated
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


def _seed_regime_csv(path: Path, n_days: int = 900) -> None:
    idx = pd.bdate_range("2022-01-03", periods=n_days)
    rows = [
        {"dt": str(dt.date()), "regime": "group_a_plus_defensive" if (i % 90) < 15 else "golden1"}
        for i, dt in enumerate(idx)
    ]
    pd.DataFrame(rows).to_csv(path, index=False)


def test_regime_clustering_review_runs_and_produces_shadow_only_decision(tmp_path: Path) -> None:
    db = tmp_path / "stock.db"
    curve = tmp_path / "curve.csv"
    regime = tmp_path / "regime.csv"
    _seed_db(db)
    _seed_switch_curve(curve)
    _seed_regime_csv(regime)

    review = build_review(
        db_path=db,
        switch_curve_path=curve,
        regime_csv_path=regime,
        core_tickers=CORE_TICKERS,
        min_months_for_first_fit=3,
        vlstar_lite_min_window=60,
    )

    assert review["paper"] == "arXiv:2104.03667"
    assert review["status"] == "available_for_shadow_monitoring"
    assert review["target_weight_change_allowed"] is False
    assert review["replace_a2118"] is False
    assert review["train_vlstar_now"] is False

    assert 0.0 <= review["cluster_regime_volatile_share"] <= 1.0
    assert 0.0 <= review["vlstar_lite_regime_volatile_share"] <= 1.0

    momentum = review["paper_momentum_validation"]
    for key in ("naive_momentum_unfiltered", "naive_momentum_cluster_filtered", "naive_momentum_vlstar_lite_filtered"):
        assert key in momentum
        assert "sharpe" in momentum[key]
        assert "mdd" in momentum[key]

    switch_check = review["group_a_plus_switch_check"]
    assert "golden1_alone" in switch_check["full_window"]
    assert "switch_ma80_dd11_rule" in switch_check["full_window"]
    assert "cluster_regime" in switch_check["agreement_with_existing_switch_rule"]
    assert "vlstar_lite_regime" in switch_check["agreement_with_existing_switch_rule"]


def test_regime_clustering_review_blocks_insufficient_history(tmp_path: Path) -> None:
    db = tmp_path / "tiny.db"
    _seed_db(db, n_days=40)

    review = build_review(db_path=db, core_tickers=CORE_TICKERS)

    assert review["status"] == "blocked"
    assert "insufficient_price_history" in review["blocking_reasons"]
    assert review["target_weight_change_allowed"] is False
    assert review["replace_a2118"] is False
    assert review["train_vlstar_now"] is False


def test_write_review_roundtrips(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    review = {"paper": "arXiv:2104.03667", "status": "available_for_shadow_monitoring"}

    write_review(review, output)

    assert json.loads(output.read_text(encoding="utf-8")) == review
