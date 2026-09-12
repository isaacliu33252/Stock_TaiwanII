from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_monthly_asset_sentiment_panel import build_panel


def _jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    return path


def test_build_panel_aggregates_monthly_asset_sentiment_and_dedupes(tmp_path: Path) -> None:
    rows = [
        {"date": "2026-01-05", "finmind_stock_id": "0050", "title": "0050 強勢上漲 利多"},
        {"date": "2026-01-05", "finmind_stock_id": "0050", "title": "0050 強勢上漲 利多 - UDN"},
        {"date": "2026-01-20", "finmind_stock_id": "0050", "title": "0050 利空 下跌"},
        {"date": "2026-02-01", "finmind_stock_id": "00631L", "title": "正2 ETF 表現強勢"},
    ]
    path = _jsonl(tmp_path / "news.jsonl", rows)

    panel, coverage = build_panel(finmind_paths=[path], tickers=["0050", "00631L"])

    assert coverage["status"] == "available"
    assert coverage["raw_records"] == 4
    assert coverage["deduped_records"] == 3
    assert set(panel["ticker"]) == {"0050", "00631L"}
    row = panel[(panel["month"] == "2026-01") & (panel["ticker"] == "0050")].iloc[0]
    assert row["news_intensity"] == 2
    assert "0050" in coverage["by_ticker"]


def test_build_panel_reports_blocked_when_no_rows(tmp_path: Path) -> None:
    path = _jsonl(tmp_path / "news.jsonl", [{"date": "2026-01-05", "finmind_stock_id": "2330", "title": "台積電"}])

    panel, coverage = build_panel(finmind_paths=[path], tickers=["0050"])

    assert panel.empty
    assert coverage["status"] == "blocked"
    assert coverage["reason"] == "no_sentiment_rows"
