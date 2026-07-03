#!/usr/bin/env python3
"""Tests for balanced GroupA+ watchlist news selection."""

from __future__ import annotations

import json
from pathlib import Path

from group_a_plus.integrations.watchlist_news import build_watchlist_news_summary


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def _write_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "symbols": [
                    {"symbol": "0050.TW", "label": "台灣50", "keywords": ["台股", "台積電"]},
                    {"symbol": "00679B.TWO", "label": "美債", "keywords": ["美債", "殖利率"]},
                ],
                "market_fallback_keywords": ["聯準會"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_watchlist_news_selects_articles_round_robin(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "watchlist.json"
    news_dir = tmp_path / "news"
    _write_config(config)
    _write_jsonl(
        news_dir / "ltn_mainstream_test.jsonl",
        [
            {"date": "2026-06-29", "source": "自由時報", "title": "台股收漲 台積電領軍", "url": "u1", "category": "財經", "snippet": "台股強勢"},
            {"date": "2026-06-29", "source": "自由時報", "title": "美債殖利率下滑", "url": "u2", "category": "財經", "snippet": "美債反彈"},
            {"date": "2026-06-28", "source": "自由時報", "title": "台股電子股續強", "url": "u3", "category": "財經", "snippet": "台股"},
            {"date": "2026-06-28", "source": "自由時報", "title": "美債買盤回溫", "url": "u4", "category": "財經", "snippet": "殖利率"},
        ],
    )
    monkeypatch.setattr("group_a_plus.integrations.watchlist_news.PROJECT_ROOT", tmp_path)

    summary = build_watchlist_news_summary(
        signal_date="2026-06-29",
        config_path=config,
        news_glob="news/*.jsonl",
        per_symbol_limit=2,
        max_articles=4,
    )

    assert [article["match_scope"] for article in summary["articles"]] == [
        "0050.TW",
        "00679B.TWO",
        "0050.TW",
        "00679B.TWO",
    ]
    assert summary["article_count"] == 4


def test_watchlist_news_uses_market_fallback_when_symbol_news_is_short(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "watchlist.json"
    news_dir = tmp_path / "news"
    _write_config(config)
    _write_jsonl(
        news_dir / "ltn_mainstream_test.jsonl",
        [
            {"date": "2026-06-29", "source": "自由時報", "title": "台股收漲", "url": "u1", "category": "財經", "snippet": "台股"},
            {"date": "2026-06-29", "source": "自由時報", "title": "聯準會官員談話", "url": "u2", "category": "財經", "snippet": "利率"},
        ],
    )
    monkeypatch.setattr("group_a_plus.integrations.watchlist_news.PROJECT_ROOT", tmp_path)

    summary = build_watchlist_news_summary(
        signal_date="2026-06-29",
        config_path=config,
        news_glob="news/*.jsonl",
        per_symbol_limit=1,
        max_articles=2,
    )

    assert summary["fallback_used"] is True
    assert summary["articles"][-1]["match_scope"] == "market_fallback"
