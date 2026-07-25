from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from scripts.evaluate.build_group_a_plus_hmm_wj_synthetic_scenario_readiness_review import (
    build_review,
    write_review,
)


def _write_price_db(path: Path) -> None:
    dates = pd.date_range("2020-01-01", periods=1300, freq="B")
    con = duckdb.connect(str(path))
    try:
        con.execute("CREATE TABLE ohlcv (ticker VARCHAR, dt DATE, close DOUBLE)")
        con.execute(
            "CREATE TABLE external_market_ohlcv (provider VARCHAR, ticker VARCHAR, dt DATE, close DOUBLE)"
        )
        for idx, dt in enumerate(dates):
            shock = -0.025 if idx % 97 == 0 else 0.001 * np.sin(idx / 11.0)
            for ticker, start, scale in (
                ("0050.TW", 100.0, 1.0),
                ("00631L.TW", 50.0, 2.0),
                ("00632R.TW", 20.0, -0.8),
            ):
                close = start * (1.0 + 0.0005 * idx + scale * shock)
                con.execute("INSERT INTO ohlcv VALUES (?, ?, ?)", [ticker, str(dt.date()), close])
            tsmc = 600.0 * (1.0 + 0.0007 * idx + 0.8 * shock)
            con.execute(
                "INSERT INTO external_market_ohlcv VALUES ('yfinance', '2330.TW', ?, ?)",
                [str(dt.date()), tsmc],
            )
    finally:
        con.close()


def test_build_review_blocks_until_generator_and_validation_exist(tmp_path: Path) -> None:
    db = tmp_path / "stock_data.db"
    finstressts = tmp_path / "fin.json"
    trigate = tmp_path / "tri.json"
    systemic = tmp_path / "systemic.json"
    _write_price_db(db)
    finstressts.write_text(json.dumps({"status": "blocked", "decision": {"allow_00631l_add": False}}), encoding="utf-8")
    trigate.write_text(
        json.dumps({"tri_gate_state": {"state": "blocked_for_leverage_add", "stress_gate_count": 3}}),
        encoding="utf-8",
    )
    systemic.write_text(
        json.dumps({"states": {"overall_state": "blocked_for_leverage_add", "systemic_score": 2}}),
        encoding="utf-8",
    )

    review = build_review(
        db_path=db,
        finstressts_path=finstressts,
        trigate_path=trigate,
        systemic_bubble_path=systemic,
        min_rows=1000,
        min_tail_obs=50,
    )

    assert review["report_type"] == "group_a_plus_hmm_wj_synthetic_scenario_readiness_review"
    assert review["data_readiness"]["all_required_tickers_ready"] is True
    assert review["status"] == "blocked"
    assert "hmm_wj_generator_not_implemented" in review["blocking_reasons"]
    assert "taiwan_etf_walkforward_validation_missing" in review["blocking_reasons"]
    assert review["decision"]["can_generate_scenarios_for_decision"] is False
    assert review["decision"]["allow_00631l_add"] is False


def test_write_review_writes_output_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_hmm_wj_synthetic_scenario_readiness_review",
        "as_of": "2026-07-17",
        "decision": {"allow_00631l_add": False},
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    assert json.loads((history / "20260717.json").read_text(encoding="utf-8")) == review
