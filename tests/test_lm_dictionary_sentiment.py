from __future__ import annotations

import json
from pathlib import Path

from group_a_plus.integrations.lm_dictionary_sentiment import (
    build_lm_dictionary_snapshot,
    load_dictionaries,
    score_texts,
)


def _write_dictionary_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "LoughranMcDonald_Positive.csv").write_text("GAIN\nGROWTH\nSTRONG\n", encoding="utf-8")
    (path / "LoughranMcDonald_Negative.csv").write_text("LOSS\nRISK\nWEAK\n", encoding="utf-8")
    (path / "LoughranMcDonald_Uncertainty.csv").write_text("UNCERTAIN\n", encoding="utf-8")
    (path / "LoughranMcDonald_Litigious.csv").write_text("CLAIM\n", encoding="utf-8")


def test_score_texts_counts_loughran_mcdonald_words(tmp_path: Path) -> None:
    _write_dictionary_dir(tmp_path)
    dictionaries = load_dictionaries(tmp_path)

    result = score_texts(["Strong growth but risk of loss remains uncertain."], dictionaries)

    assert result["positive_count"] == 2
    assert result["negative_count"] == 2
    assert result["uncertainty_count"] == 1
    assert result["dictionary_hit_count"] == 5
    assert result["sentiment_score"] == 0.0
    assert result["risk_score"] == 0.5


def test_build_snapshot_reads_watchlist_news_text(tmp_path: Path) -> None:
    dictionary_dir = tmp_path / "dict"
    _write_dictionary_dir(dictionary_dir)
    news_path = tmp_path / "watchlist_news.json"
    news_path.write_text(
        json.dumps(
            {
                "source": "unit",
                "signal_date": "2026-07-01",
                "articles": [
                    {
                        "title": "Market risk and weak growth",
                        "snippet": "Loss risk remains high.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    snapshot = build_lm_dictionary_snapshot(
        "2026-07-01",
        watchlist_news_path=news_path,
        dictionary_dir=dictionary_dir,
    )

    assert snapshot["status"] == "ok"
    assert snapshot["active_allocation_impact"] == "none"
    assert snapshot["positive_count"] == 1
    assert snapshot["negative_count"] == 4
    assert snapshot["risk_score"] > 0.5
