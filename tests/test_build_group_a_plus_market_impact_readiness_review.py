from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_market_impact_readiness_review import write_review


def test_write_review_writes_latest_and_history_snapshot(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "market_impact_readiness_review.json"
    history_dir = tmp_path / "history"
    review = {
        "schema_version": 1,
        "report_type": "group_a_plus_market_impact_readiness_review",
        "status": "blocked",
        "as_of": "2026-07-20",
        "blocking_reasons": ["turnover_exceeds_limit"],
    }

    write_review(review, output_path=output, history_dir=history_dir)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_path = history_dir / "20260720.json"
    assert json.loads(history_path.read_text(encoding="utf-8")) == review


def test_write_review_can_disable_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "market_impact_readiness_review.json"
    history_dir = tmp_path / "history"
    review = {
        "schema_version": 1,
        "report_type": "group_a_plus_market_impact_readiness_review",
        "status": "available_for_manual_review",
        "as_of": "2026-07-20",
        "blocking_reasons": [],
    }

    write_review(review, output_path=output, history_dir=None)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    assert not history_dir.exists()
