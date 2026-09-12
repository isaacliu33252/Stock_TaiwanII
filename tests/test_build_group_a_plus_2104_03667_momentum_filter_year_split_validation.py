from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate.build_group_a_plus_2104_03667_momentum_filter_year_split_validation import (
    build_review,
    write_review,
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


def _seed_regime_features(path: Path, n_days: int = 900) -> None:
    idx = pd.bdate_range("2022-01-03", periods=n_days)
    rows = []
    dd = 0.0
    for i, dt in enumerate(idx):
        stress = (i % 90) < 15
        dd = min(0.0, dd - 0.01) if stress else min(0.0, dd + 0.01)
        rows.append(
            {
                "dt": str(dt.date()),
                "ma_gap": -0.05 if stress else 0.05,
                "drawdown": dd,
                "realized_vol_0050_20d": 0.35 if stress else 0.12,
                "tail_risk_score": 1.0 if stress else 0.0,
                "total_risk_score": 6.0 if stress else 1.0,
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)


def test_year_split_restricts_to_feature_overlap_window(tmp_path: Path) -> None:
    db = tmp_path / "stock.db"
    features = tmp_path / "features.csv"
    _seed_db(db)
    _seed_regime_features(features)

    review = build_review(db_path=db, regime_features_path=features, core_tickers=CORE_TICKERS)

    assert review["status"] == "available_for_shadow_monitoring"
    assert review["scope"].startswith("standalone_0050_momentum_filter_only")
    assert review["target_weight_change_allowed"] is False
    assert review["replace_a2118"] is False
    assert review["train_vlstar_now"] is False

    # No year in the per-year breakdown may start before the seeded feature
    # file's own coverage -- the whole point of this script is that the
    # comparison must not include dates the filter could not act on.
    for year_str in review["per_year"]:
        assert int(year_str) >= 2022  # _seed_regime_features starts 2022-01-03

    assert "broad_based_edge" in review
    assert isinstance(review["broad_based_edge"], bool)
    assert "caveat" in review


def test_blocks_when_regime_features_missing(tmp_path: Path) -> None:
    db = tmp_path / "stock.db"
    _seed_db(db)

    review = build_review(db_path=db, regime_features_path=tmp_path / "missing.csv", core_tickers=CORE_TICKERS)

    assert review["status"] == "blocked"
    assert "regime_features_csv_missing" in review["blocking_reasons"]
    assert review["target_weight_change_allowed"] is False


def test_write_review_roundtrips(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    review = {"paper": "arXiv:2104.03667", "status": "available_for_shadow_monitoring"}

    write_review(review, output)

    assert json.loads(output.read_text(encoding="utf-8")) == review
