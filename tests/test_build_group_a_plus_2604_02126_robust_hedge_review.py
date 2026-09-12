from __future__ import annotations

import json
from pathlib import Path

import duckdb

from scripts.evaluate.build_group_a_plus_2604_02126_robust_hedge_review import (
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
        asset = 100.0
        inverse = 20.0
        for idx in range(320):
            year = 2026 if idx < 220 else 2027
            day = idx % 28 + 1
            month = idx // 28 % 12 + 1
            dt = f"{year}-{month:02d}-{day:02d}"
            ret = 0.0015 if idx % 5 else -0.006
            if idx % 37 == 0:
                ret -= 0.012
            asset *= 1.0 + ret
            inverse *= 1.0 - 0.92 * ret - 0.00015
            for ticker, close in (("0050.TW", asset), ("00632R.TW", inverse)):
                rows.append((ticker, dt, close, close, close, close, 1000, 0.0, 0.0, "test", "2027-01-01 00:00:00"))
        conn.executemany("INSERT INTO ohlcv VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_build_review_keeps_robust_hedge_shadow_only(tmp_path: Path) -> None:
    db = tmp_path / "stock_data.db"
    _make_db(db)
    letf = _write(tmp_path / "letf.json", {"decision": {"allow_00632r_open": False}})
    latest = _write(
        tmp_path / "latest.json",
        {"data": {"target_weights": {"0050.TW": 0.47, "00632R.TW": 0.16}}},
    )

    review = build_review(
        db_path=db,
        as_of="2027-10-12",
        start="2026-01-01",
        window=40,
        uncertainty_window=40,
        letf_readiness_path=letf,
        latest_strategy_path=latest,
    )

    assert review["report_type"] == "group_a_plus_2604_02126_robust_hedge_review"
    assert review["status"] == "blocked_for_live_promotion"
    assert review["assessment"]["paper_advantage_importable_as_shadow"] is True
    assert review["assessment"]["best_import_candidate"] == "robust_variance_only_hedge_ratio"
    assert review["decision"]["robust_hedge_review_complete"] is True
    assert review["decision"]["promote_to_live"] is False
    assert review["decision"]["target_weight_change_allowed"] is False
    assert review["decision"]["auto_rebalance_allowed"] is False
    assert review["decision"]["allow_00632r_open"] is False
    assert "letf_readiness_blocks_00632r_open" in review["blocking_reasons"]

    methods = review["hedge_review"]["method_comparison"]
    assert methods["standard"]["hedge_ratio_summary"]["count"] > 0
    assert methods["robust_variance_only"]["hedge_ratio_summary"]["count"] > 0
    assert methods["robust_full_box"]["hedge_ratio_summary"]["count"] > 0
    assert review["latest_strategy_context"]["latest_strategy_00632r_target_weight"] == 0.16
    assert review["latest_strategy_context"]["advisory_is_cap_only_diagnostic"] is True


def test_build_review_blocks_when_data_missing(tmp_path: Path) -> None:
    db = tmp_path / "empty.db"
    with duckdb.connect(str(db)) as conn:
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

    review = build_review(
        db_path=db,
        start="2026-01-01",
        window=40,
        uncertainty_window=40,
        letf_readiness_path=tmp_path / "missing_letf.json",
        latest_strategy_path=tmp_path / "missing_latest.json",
    )

    assert review["decision"]["robust_hedge_review_complete"] is False
    assert "missing_required_ohlcv" in review["blocking_reasons"]
    assert review["decision"]["allow_00632r_open"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "review.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_2604_02126_robust_hedge_review",
        "as_of": "2026-08-28",
        "actual_data_end": "2026-08-28",
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "2604_02126_robust_hedge_review_20260828.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
