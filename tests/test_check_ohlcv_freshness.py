from __future__ import annotations

import importlib.util
from pathlib import Path

import duckdb
import pandas as pd


def _load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "misc" / "check_ohlcv_freshness.py"
    spec = importlib.util.spec_from_file_location("_test_check_ohlcv_freshness", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_db(path: Path, ticker: str = "00631L.TW", dt: str = "2026-06-25") -> None:
    with duckdb.connect(str(path)) as con:
        con.execute(
            """
            CREATE TABLE ohlcv (
                ticker TEXT,
                dt DATE,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume BIGINT
            )
            """
        )
        con.execute(
            "INSERT INTO ohlcv VALUES (?, ?, 10, 11, 9, 10.5, 1000)",
            [ticker, dt],
        )


def test_invalid_target_close_is_warning_not_error(tmp_path: Path) -> None:
    module = _load_module()
    db_path = tmp_path / "stock.duckdb"
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    _create_db(db_path)
    pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-06-25", "2026-06-26"]),
            "open": [38.9, 36.95],
            "high": [38.9, 37.14],
            "low": [37.58, 35.10],
            "close": [38.16, pd.NA],
            "adj close": [38.16, pd.NA],
            "volume": [248435529, 662725508],
        }
    ).to_parquet(cache_dir / "00631L_TW_20200101_20260626_1d_raw_v1.parquet", index=False)

    result = module.check_ticker(
        "00631L.TW",
        "2026-06-26",
        db_path=db_path,
        cache_dir=cache_dir,
        max_db_lag_days=3,
    )

    assert result["status"] == "warning"
    assert result["db_max_date"] == "2026-06-25"
    assert result["db_lag_days"] == 1
    assert result["raw_cache"]["has_target_date"] is True
    assert result["raw_cache"]["target_ohlv_valid"] is True
    assert result["raw_cache"]["target_close_valid"] is False
    assert result["warnings"] == ["raw_target_close_invalid"]
    assert result["errors"] == []


def test_db_lag_beyond_threshold_is_error(tmp_path: Path) -> None:
    module = _load_module()
    db_path = tmp_path / "stock.duckdb"
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    _create_db(db_path, dt="2026-06-20")
    pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-06-26"]),
            "open": [36.95],
            "high": [37.14],
            "low": [35.10],
            "close": [36.5],
            "adj close": [36.5],
            "volume": [662725508],
        }
    ).to_parquet(cache_dir / "00631L_TW_20200101_20260626_1d_raw_v1.parquet", index=False)

    result = module.check_ticker(
        "00631L.TW",
        "2026-06-26",
        db_path=db_path,
        cache_dir=cache_dir,
        max_db_lag_days=3,
    )

    assert result["status"] == "error"
    assert result["errors"] == ["db_ohlcv_stale"]
