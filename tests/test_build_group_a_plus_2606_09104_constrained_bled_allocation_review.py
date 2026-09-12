from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate.build_group_a_plus_2606_09104_constrained_bled_allocation_review import (
    build_review,
    write_review,
)


def _seed_db(path: Path) -> None:
    dates = pd.bdate_range("2025-01-02", periods=320)
    prices = {"0050.TW": 100.0, "00631L.TW": 100.0, "00632R.TW": 100.0, "00679B.TWO": 100.0}
    rows = []
    for i, dt in enumerate(dates):
        shock = i % 50 == 0
        r_0050 = -0.02 if shock else 0.001
        rets = {
            "0050.TW": r_0050,
            "00631L.TW": r_0050 * 2.2 if shock else 0.002,
            "00632R.TW": -r_0050 * 0.8,
            "00679B.TWO": 0.0002,
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


def _inputs(tmp_path: Path) -> tuple[Path, Path]:
    live = tmp_path / "live.json"
    forward = tmp_path / "forward.json"
    live.write_text(
        json.dumps(
            {
                "portfolio_state": {
                    "weights": {"0050.TW": 0.3, "00631L.TW": 0.0, "00632R.TW": 0.0, "00679B.TWO": 0.0},
                    "cash_weight": 0.7,
                },
                "target_weights_for_action": {"0050.TW": 0.7, "00631L.TW": 0.3, "00632R.TW": 0.0, "00679B.TWO": 0.0},
            }
        ),
        encoding="utf-8",
    )
    forward.write_text(
        json.dumps(
            {
                "live_signal": {
                    "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
                    "target_weights": {"0050.TW": 0.3, "cash": 0.7},
                    "market_state": {"state": "bull_pullback_deep"},
                }
            }
        ),
        encoding="utf-8",
    )
    return live, forward


def test_constrained_bled_allocation_review_is_review_only(tmp_path: Path) -> None:
    db = tmp_path / "stock.db"
    _seed_db(db)
    live, forward = _inputs(tmp_path)

    report = build_review(
        db_path=db,
        start="2025-01-02",
        end="2026-03-25",
        live_snapshot_path=live,
        forward_monitor_path=forward,
    )

    assert report["report_type"] == "group_a_plus_2606_09104_constrained_bled_allocation_review"
    assert report["status"] == "available_for_shadow_review"
    assert report["guardrails"]["short_selling_allowed"] is False
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["decision"]["allow_00631l_add_from_this_review"] is False
    assert any(row["target_name"] == "candidate_00631l_cap_5pct" for row in report["candidate_reviews"])


def test_constrained_bled_allocation_review_blocks_missing_db(tmp_path: Path) -> None:
    report = build_review(db_path=tmp_path / "missing.db")

    assert report["status"] == "blocked"
    assert "stock_database_missing" in report["blocking_reasons"]
    assert report["decision"]["target_weight_change_allowed"] is False


def test_write_constrained_bled_allocation_review_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    report = {
        "report_type": "group_a_plus_2606_09104_constrained_bled_allocation_review",
        "as_of": "2026-08-24",
        "decision": {"target_weight_change_allowed": False},
    }

    write_review(report, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert (history / "2606_09104_constrained_bled_allocation_review_20260824.json").exists()
