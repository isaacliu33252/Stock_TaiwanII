from __future__ import annotations

import json
from pathlib import Path

import duckdb

from scripts.evaluate.evaluate_group_a_plus_2604_02126_forecast_variants import (
    build_forecast_variant_review,
    render_markdown,
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
        inverse = 18.0
        for idx in range(260):
            dt = f"2026-{(idx // 28) % 12 + 1:02d}-{idx % 28 + 1:02d}"
            ret = 0.002 if idx % 4 else -0.006
            if idx % 53 == 0:
                ret -= 0.012
            asset *= 1.0 + ret
            inverse *= 1.0 - 0.9 * ret - 0.0001
            for ticker, close in (("0050.TW", asset), ("00632R.TW", inverse)):
                rows.append((ticker, dt, close, close, close, close, 1000, 0.0, 0.0, "test", "2026-12-31 00:00:00"))
        conn.executemany("INSERT INTO ohlcv VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_forecast_variant_review_stays_blocked(tmp_path: Path) -> None:
    db = tmp_path / "stock_data.db"
    _make_db(db)

    review = build_forecast_variant_review(
        db_path=db,
        as_of="2026-09-08",
        start="2026-01-01",
        models=["rolling_mean", "ar1", "har_lite"],
        window=40,
        uncertainty_window=40,
        letf_readiness_path=_write(tmp_path / "letf.json", {"decision": {"allow_00632r_open": False}}),
        latest_strategy_path=_write(tmp_path / "latest.json", {"data": {"target_weights": {"00632R.TW": 0.1}}}),
    )

    assert review["report_type"] == "group_a_plus_2604_02126_forecast_variants"
    assert review["status"] == "blocked_for_live_promotion"
    assert [row["model"] for row in review["results"]] == ["rolling_mean", "ar1", "har_lite"]
    assert review["decision"]["forecast_variant_review_complete"] is True
    assert review["decision"]["promote_to_live"] is False
    assert review["decision"]["target_weight_change_allowed"] is False
    assert review["decision"]["allow_00632r_open"] is False
    assert "research_only_forecast_variant_review" in review["blocking_reasons"]


def test_render_markdown_contains_models() -> None:
    review = {
        "generated_at": "2026-08-29T00:00:00",
        "as_of": "2026-08-28",
        "status": "blocked_for_live_promotion",
        "blocking_reasons": ["research_only_forecast_variant_review"],
        "results": [
            {
                "model": "ar1",
                "observation_count": 10,
                "passes_shadow_filter": False,
                "robust_variance_only": {
                    "latest_exposure": 0.1,
                    "turnover_reduction_vs_standard": -0.2,
                    "exposure_std_reduction_vs_standard": -0.3,
                    "effectiveness": {"conditional_hedge_effectiveness": 0.1},
                },
                "standard": {"effectiveness": {"conditional_hedge_effectiveness": 0.2}},
            }
        ],
    }

    markdown = render_markdown(review)

    assert "Forecast Variant Review" in markdown
    assert "| ar1 | 10 |" in markdown
    assert "Do not open or increase `00632R.TW`" in markdown


def test_write_review_writes_outputs(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "forecast.json"
    output_md = tmp_path / "latest" / "forecast.md"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_2604_02126_forecast_variants",
        "generated_at": "2026-08-29T00:00:00",
        "as_of": "2026-08-28",
        "status": "blocked_for_live_promotion",
        "blocking_reasons": [],
        "results": [],
    }

    write_review(review, output, output_md, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    assert "2604.02126 Forecast Variant Review" in output_md.read_text(encoding="utf-8")
    history_file = history / "2604_02126_forecast_variants_20260828.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
