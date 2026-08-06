from __future__ import annotations

import json

import pandas as pd

from group_a_plus.portfolio.price_loader import load_prices_from_ohlcv_freshness, load_prices_json


def test_load_prices_json_accepts_plain_object(tmp_path) -> None:
    path = tmp_path / "prices.json"
    path.write_text(json.dumps({"0050.TW": 101.5}), encoding="utf-8")

    assert load_prices_json(path) == {"0050.TW": 101.5}


def test_load_prices_json_accepts_latest_prices_wrapper(tmp_path) -> None:
    path = tmp_path / "prices.json"
    path.write_text(json.dumps({"latest_prices": {"0050.TW": 101.5}}), encoding="utf-8")

    assert load_prices_json(path) == {"0050.TW": 101.5}


def test_load_prices_from_ohlcv_freshness_reads_target_date(tmp_path) -> None:
    parquet_path = tmp_path / "0056.parquet"
    pd.DataFrame(
        [
            {"date": "2026-07-24", "close": 49.5, "adj close": 49.5},
            {"date": "2026-07-27", "close": 50.0, "adj close": 50.0},
        ]
    ).to_parquet(parquet_path)
    freshness_path = tmp_path / "freshness.json"
    freshness_path.write_text(
        json.dumps(
            {
                "target_date": "2026-07-27",
                "tickers": [
                    {
                        "ticker": "0056.TW",
                        "target_date": "2026-07-27",
                        "raw_cache": {"path": str(parquet_path), "exists": True},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert load_prices_from_ohlcv_freshness(freshness_path) == {"0056.TW": 50.0}
