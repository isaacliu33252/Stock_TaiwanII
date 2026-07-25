from __future__ import annotations

import json
from pathlib import Path

import duckdb

from scripts.evaluate.build_group_a_plus_letf_tracking_error_effective_fee_readiness_review import (
    build_review,
    write_review,
)


def _make_db(path: Path) -> None:
    with duckdb.connect(str(path)) as conn:
        conn.execute(
            """
            CREATE TABLE ohlcv (
                ticker VARCHAR,
                dt DATE,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume BIGINT,
                dividends DOUBLE,
                stock_splits DOUBLE,
                source_file VARCHAR,
                updated_at TIMESTAMP
            )
            """
        )
        rows = []
        ref = 100.0
        l31 = 20.0
        r32 = 15.0
        for idx in range(80):
            daily = 0.002 if idx % 3 else -0.001
            ref *= 1.0 + daily
            l31 *= 1.0 + 2.0 * daily - 0.0004
            r32 *= 1.0 - daily - 0.0002
            dt = f"2026-04-{idx + 1:02d}" if idx < 30 else f"2026-05-{idx - 29:02d}" if idx < 61 else f"2026-06-{idx - 60:02d}"
            for ticker, close in (("0050.TW", ref), ("00631L.TW", l31), ("00632R.TW", r32)):
                rows.append((ticker, dt, close, close, close, close, 1000, 0.0, 0.0, "test", "2026-07-18 00:00:00"))
        conn.executemany(
            "INSERT INTO ohlcv VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )


def test_build_review_blocks_letf_tracking_error_readiness(tmp_path: Path) -> None:
    db = tmp_path / "stock_data.db"
    intervention = tmp_path / "intervention.json"
    _make_db(db)
    intervention.write_text(json.dumps({"status": "blocked"}), encoding="utf-8")

    review = build_review(
        db_path=db,
        as_of="2026-06-19",
        start="2026-04-01",
        horizons=[1, 5, 10],
        intervention_fatigue_path=intervention,
    )

    assert review["report_type"] == "group_a_plus_letf_tracking_error_effective_fee_readiness_review"
    assert review["status"] == "blocked"
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False
    assert "research_only_letf_tracking_error_review" in review["blocking_reasons"]
    assert "realized_effective_fee_proxy_not_validated" in review["blocking_reasons"]
    assert "00632r_hedge_neutrality_not_promoted" in review["blocking_reasons"]
    assert "intervention_fatigue_risk_budget_readiness_blocked" in review["blocking_reasons"]
    assert review["tracking_error_summary"]["00631L.TW"]["horizon_metrics"]["5"]["tracking_error"]["count"] > 0
    assert review["tracking_error_summary"]["00632R.TW"]["horizon_metrics"]["10"]["effective_drag_proxy"]["count"] > 0
    assert review["hedge_neutrality"]["00632R.TW"]["expected_beta"] == -1.0
    threshold_review = review["parameter_threshold_review"]
    assert threshold_review["policy"] == "manual_review_thresholds_only_no_live_unlock"
    assert threshold_review["can_consider_00631l_add_after_manual_review"] is False
    assert threshold_review["can_consider_00632r_open_after_manual_review"] is False
    assert threshold_review["checks"]["effective_fee_proxy_independently_validated"]["passed"] is False
    assert threshold_review["checks"]["live_hedge_policy_validated"]["passed"] is False
    assert "effective_fee_proxy_independently_validated" in threshold_review["failed_checks"]


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "review.json"
    history = tmp_path / "history"
    review = {"as_of": "2026-07-20", "report_type": "group_a_plus_letf_tracking_error_effective_fee_readiness_review"}

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "letf_tracking_error_effective_fee_readiness_20260720.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
