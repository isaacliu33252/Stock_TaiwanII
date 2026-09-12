from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate.build_group_a_plus_2411_19649_semicovariance_review import build_review, write_review


def _seed_db(path: Path) -> None:
    idx = pd.bdate_range("2025-01-01", periods=320)
    prices = {
        "0050.TW": 100.0,
        "00631L.TW": 100.0,
        "00632R.TW": 100.0,
        "00679B.TWO": 100.0,
        "0056.TW": 100.0,
        "00713.TW": 100.0,
    }
    rows = []
    for i, dt in enumerate(idx):
        stress = i % 32 == 0
        base_ret = (-0.015 - 0.001 * (i % 5)) if stress else (0.004 if i % 2 == 0 else -0.001)
        rets = {
            "0050.TW": base_ret,
            "00631L.TW": base_ret * 2.0,
            "00632R.TW": -base_ret * 0.8,
            "00679B.TWO": 0.0004 if stress else 0.0002,
            # Looks mixed on ordinary days but fails exactly when 0050 is down hard.
            "0056.TW": (base_ret * 0.9) if stress else (-base_ret + (0.002 if i % 3 == 0 else -0.002)),
            "00713.TW": 0.004 if stress else 0.0003,
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


def test_semicovariance_review_is_diagnostic_and_flags_stress_failure(tmp_path: Path) -> None:
    db = tmp_path / "stock.db"
    _seed_db(db)

    review = build_review(
        db_path=db,
        start="2025-01-01",
        end="2026-03-31",
        fifth_candidates=("0056.TW", "00713.TW"),
        lookback_days=320,
        min_history=200,
        min_conditional_rows=6,
        low_ordinary_corr_threshold=0.60,
        high_downside_corr_threshold=0.60,
    )

    assert review["report_type"] == "group_a_plus_2411_19649_semicovariance_review"
    assert review["status"] == "available_for_shadow_monitoring"
    assert review["guardrails"]["unconstrained_minimum_semicovariance_optimizer_allowed"] is False
    assert review["guardrails"]["forbid_simultaneous_00631l_00632r_offset"] is True
    assert review["decision"]["target_weight_change_allowed"] is False
    assert review["decision"]["replace_a2118_optimizer"] is False

    by_asset = {row["asset"]: row for row in review["fifth_asset_candidate_ranking"]}
    assert by_asset["0056.TW"]["diversification_disappears_in_stress"] is True
    assert "ordinary_corr_low_but_downside_corr_high" in by_asset["0056.TW"]["warning_reasons"]
    assert by_asset["00713.TW"]["diversification_disappears_in_stress"] is False

    golden = review["regime_constraint_reviews"]["golden1"]
    assert golden["contains_forbidden_leverage_inverse_offset"] is False
    assert "00632R.TW" in golden["forbidden_assets"]


def test_semicovariance_review_blocks_missing_database(tmp_path: Path) -> None:
    review = build_review(db_path=tmp_path / "missing.db", end="2026-03-31")

    assert review["status"] == "blocked"
    assert "stock_database_missing" in review["blocking_reasons"]
    assert review["decision"]["target_weight_change_allowed"] is False
    assert review["decision"]["replace_a2118_optimizer"] is False


def test_write_semicovariance_review_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_2411_19649_semicovariance_review",
        "as_of": "2026-08-24",
        "decision": {"target_weight_change_allowed": False},
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    assert (history / "2411_19649_semicovariance_review_20260824.json").exists()
