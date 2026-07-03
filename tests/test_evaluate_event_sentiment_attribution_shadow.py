from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


def _load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "evaluate" / "evaluate_event_sentiment_attribution_shadow.py"
    spec = importlib.util.spec_from_file_location("_test_event_sentiment_attribution", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _prices() -> pd.DataFrame:
    idx = pd.date_range("2026-01-02", periods=8, freq="B")
    return pd.DataFrame(
        {
            "0050.TW": [100, 101, 102, 103, 104, 105, 106, 107],
            "00631L.TW": [50, 52, 53, 54, 55, 56, 57, 58],
            "00679B.TWO": [30, 29.8, 29.7, 29.9, 30.1, 30.2, 30.4, 30.5],
        },
        index=idx,
        dtype=float,
    )


def test_forward_return_uses_next_available_trade_date() -> None:
    module = _load_module()
    result = module._forward_return(
        _prices(),
        symbol="00631L.TW",
        event_date=pd.Timestamp("2026-01-03"),
        horizon=1,
    )

    assert result["status"] == "ok"
    assert result["event_trade_date"] == "2026-01-05"
    assert result["target_trade_date"] == "2026-01-06"
    assert result["return"] == pytest.approx(53 / 52 - 1)


def test_forward_return_marks_unmatured_horizon() -> None:
    module = _load_module()
    result = module._forward_return(
        _prices(),
        symbol="00631L.TW",
        event_date=pd.Timestamp("2026-01-12"),
        horizon=5,
    )

    assert result["status"] == "immature"
    assert result["available_rows_after_event"] < 5


def test_build_article_attributions_scores_sentiment_and_relative_returns() -> None:
    module = _load_module()
    articles = [
        {
            "date": "2026-01-02",
            "title": "台股強勢 AI 買盤回溫",
            "snippet": "台股上漲",
            "match_scope": "00631L.TW",
            "url": "u1",
        },
        {
            "date": "2026-01-02",
            "title": "台股強勢 AI 買盤回溫",
            "snippet": "台股上漲",
            "match_scope": "00631L.TW",
            "url": "u2",
        },
    ]

    records = module.build_article_attributions(
        articles,
        _prices(),
        benchmark="0050.TW",
        horizons=(1, 5),
        default_symbol="0050.TW",
    )
    aggregate = module.aggregate_attributions(records, (1, 5))

    assert len(records) == 2
    assert records[0]["duplicate_content_hash"] is False
    assert records[1]["duplicate_content_hash"] is True
    assert records[0]["horizons"]["h1"]["relative_return"] == pytest.approx((52 / 50 - 1) - (101 / 100 - 1))
    assert aggregate["duplicate_content_hash_count"] == 1
    assert aggregate["h1"]["matured_count"] == 2
    assert aggregate["active_allocation_impact"] == "none"
