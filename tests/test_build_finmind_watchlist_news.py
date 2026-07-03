from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


def _load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "run" / "build_finmind_watchlist_news.py"
    spec = importlib.util.spec_from_file_location("_test_build_finmind_watchlist_news", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load_module()


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_build_summary_filters_by_lookback_window_and_trusts_match_scope(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mod, "PROJECT_ROOT", tmp_path)
    _write_jsonl(
        tmp_path / "news" / "finmind_stock_news_test.jsonl",
        [
            {"date": "2026-06-29", "source": "s1", "title": "in range", "url": "https://x/1", "category": "finmind_stock_news", "snippet": "", "match_scope": "0050.TW"},
            {"date": "2026-01-01", "source": "s1", "title": "too old", "url": "https://x/2", "category": "finmind_stock_news", "snippet": "", "match_scope": "0050.TW"},
        ],
    )

    summary = mod.build_finmind_watchlist_news_summary(
        signal_date="2026-06-30", lookback_days=7, news_glob="news/finmind_stock_news_*.jsonl"
    )

    assert summary["article_count"] == 1
    assert summary["articles"][0]["title"] == "in range"
    assert summary["articles"][0]["match_scope"] == "0050.TW"
    assert summary["source"] == "finmind_stock_news"


def test_build_summary_dedupes_by_url_and_respects_per_symbol_limit(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mod, "PROJECT_ROOT", tmp_path)
    rows = [
        {"date": "2026-06-29", "source": "s", "title": f"a{i}", "url": f"https://x/{i}", "category": "finmind_stock_news", "snippet": "", "match_scope": "0050.TW"}
        for i in range(5)
    ]
    rows.append(dict(rows[0]))  # duplicate url
    _write_jsonl(tmp_path / "news" / "finmind_stock_news_test.jsonl", rows)

    summary = mod.build_finmind_watchlist_news_summary(
        signal_date="2026-06-30",
        lookback_days=7,
        per_symbol_limit=2,
        max_articles=10,
        news_glob="news/finmind_stock_news_*.jsonl",
    )

    assert summary["article_count"] == 2
    assert summary["watchlist"] == [{"symbol": "0050.TW", "matched_count": 2}]
