from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate.build_group_a_plus_2607_15195_expectile_utility_shadow import (
    build_shadow,
    write_shadow,
)


def _seed_db(path: Path) -> None:
    dates = pd.bdate_range("2025-01-02", periods=90)
    prices = {
        "0050.TW": 100.0,
        "00631L.TW": 30.0,
        "00632R.TW": 10.0,
        "00679B.TWO": 25.0,
    }
    rows = []
    for idx, dt in enumerate(dates):
        if idx % 30 == 20:
            r_0050 = -0.006
            r_00631l = -0.055
        else:
            r_0050 = 0.001
            r_00631l = 0.010
        prices["0050.TW"] *= 1.0 + r_0050
        prices["00631L.TW"] *= 1.0 + r_00631l
        prices["00632R.TW"] *= 1.0 - r_0050
        prices["00679B.TWO"] *= 1.0001
        for ticker, close in prices.items():
            rows.append({"dt": str(dt.date()), "ticker": ticker, "close": close})
    con = duckdb.connect(str(path))
    try:
        con.execute("CREATE TABLE ohlcv (dt DATE, ticker VARCHAR, close DOUBLE)")
        con.register("rows", pd.DataFrame(rows))
        con.execute("INSERT INTO ohlcv SELECT * FROM rows")
    finally:
        con.close()


def _write_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    live = tmp_path / "live.json"
    forward = tmp_path / "forward.json"
    soft_budget = tmp_path / "soft_budget.json"
    live.write_text(
        json.dumps(
            {
                "as_of": "2025-05-07",
                "portfolio_state": {
                    "weights": {"0050.TW": 0.30, "00631L.TW": 0.0, "00632R.TW": 0.0, "00679B.TWO": 0.0},
                    "cash_weight": 0.70,
                },
                "target_weights_for_action": {"0050.TW": 0.70, "00631L.TW": 0.30, "00632R.TW": 0.0, "00679B.TWO": 0.0},
            }
        ),
        encoding="utf-8",
    )
    forward.write_text(
        json.dumps(
            {
                "as_of": "2025-05-07",
                "live_signal": {
                    "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
                    "target_weights": {
                        "0050.TW": 0.30,
                        "00631L.TW": 0.0,
                        "00632R.TW": 0.0,
                        "00679B.TWO": 0.0,
                        "cash": 0.70,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    soft_budget.write_text(
        json.dumps(
            {
                "decision": {
                    "guarded_live_target_best_shadow_fraction": 0.25,
                    "raw_a2118_best_shadow_fraction": 0.75,
                }
            }
        ),
        encoding="utf-8",
    )
    return live, forward, soft_budget


def test_expectile_utility_shadow_penalizes_raw_downside_tail(tmp_path: Path) -> None:
    db = tmp_path / "stock.db"
    _seed_db(db)
    live, forward, soft_budget = _write_inputs(tmp_path)

    report = build_shadow(
        db_path=db,
        live_snapshot_path=live,
        forward_monitor_path=forward,
        soft_budget_shadow_path=soft_budget,
        start="2025-01-02",
        end="2025-05-07",
        horizon=20,
        expectile_tau=0.90,
        min_observations=30,
    )

    assert report["report_type"] == "group_a_plus_2607_15195_expectile_utility_shadow"
    assert report["status"] == "available_for_reward_review"
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["decision"]["train_reward_model_now"] is False
    reviews = {row["target_name"]: row for row in report["target_reviews"]}
    assert (
        reviews["raw_a2118_seed_ensemble_target"]["expectile_asymmetric_loss"]
        > reviews["guarded_live_target"]["expectile_asymmetric_loss"]
    )
    assert report["rankings"]["expectile_asymmetric_loss_lower_is_better"][0]["target_name"] in {
        "current_live_weights",
        "guarded_live_target",
        "soft_budget_best_guarded_partial",
    }


def test_expectile_utility_shadow_blocks_missing_inputs(tmp_path: Path) -> None:
    report = build_shadow(
        db_path=tmp_path / "missing.db",
        live_snapshot_path=tmp_path / "missing_live.json",
        forward_monitor_path=tmp_path / "missing_forward.json",
        soft_budget_shadow_path=tmp_path / "missing_soft_budget.json",
    )

    assert report["status"] == "blocked"
    assert "ohlcv_db_missing" in report["blocking_reasons"]
    assert "candidate_targets_missing" in report["blocking_reasons"]
    assert report["decision"]["target_weight_change_allowed"] is False


def test_write_expectile_utility_shadow_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    report = {
        "report_type": "group_a_plus_2607_15195_expectile_utility_shadow",
        "as_of": "2026-08-24",
        "decision": {"target_weight_change_allowed": False},
    }

    write_shadow(report, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert (history / "2607_15195_expectile_utility_shadow_20260824.json").exists()
