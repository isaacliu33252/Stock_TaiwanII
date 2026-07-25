#!/usr/bin/env python3
"""Backfill static ticker metadata for GroupA+ research readiness.

This script intentionally uses a small manually curated seed map. It fills the
minimum sector/style metadata needed by research-only diagnostics without
downloading prices or changing live strategy outputs.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/ticker_metadata_backfill_report.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/ticker_metadata_backfill/history"


SEED_METADATA: tuple[dict[str, Any], ...] = (
    {
        "ticker": "0050.TW",
        "canonical_ticker": "0050.TW",
        "name": "Yuanta Taiwan 50 ETF",
        "asset_type": "equity_etf",
        "market": "Taiwan",
        "exchange": "TWSE",
        "sector": "broad_market",
        "industry": "large_cap_equity",
        "is_financial_sector": False,
        "is_leveraged_etf": False,
        "is_inverse_etf": False,
        "is_bond_etf": False,
        "is_equity_etf": True,
        "is_stock": False,
        "group_a_plus_role": "core_equity",
        "included_in_sin_lite": True,
        "exclusion_reason": None,
    },
    {
        "ticker": "0050",
        "canonical_ticker": "0050.TW",
        "name": "Yuanta Taiwan 50 ETF legacy alias",
        "asset_type": "legacy_alias",
        "market": "Taiwan",
        "exchange": "TWSE",
        "sector": "broad_market",
        "industry": "large_cap_equity",
        "is_financial_sector": False,
        "is_leveraged_etf": False,
        "is_inverse_etf": False,
        "is_bond_etf": False,
        "is_equity_etf": True,
        "is_stock": False,
        "group_a_plus_role": "legacy_duplicate_excluded",
        "included_in_sin_lite": False,
        "exclusion_reason": "legacy_duplicate_of_0050.TW",
    },
    {
        "ticker": "0056.TW",
        "canonical_ticker": "0056.TW",
        "name": "Yuanta Taiwan High Dividend ETF",
        "asset_type": "equity_etf",
        "market": "Taiwan",
        "exchange": "TWSE",
        "sector": "dividend_equity",
        "industry": "high_dividend_equity",
        "is_financial_sector": False,
        "is_leveraged_etf": False,
        "is_inverse_etf": False,
        "is_bond_etf": False,
        "is_equity_etf": True,
        "is_stock": False,
        "group_a_plus_role": "income_equity_watch",
        "included_in_sin_lite": True,
        "exclusion_reason": None,
    },
    {
        "ticker": "00631L.TW",
        "canonical_ticker": "00631L.TW",
        "name": "Yuanta Taiwan 50 Daily 2x ETF",
        "asset_type": "leveraged_equity_etf",
        "market": "Taiwan",
        "exchange": "TWSE",
        "sector": "leveraged_broad_market",
        "industry": "leveraged_large_cap_equity",
        "is_financial_sector": False,
        "is_leveraged_etf": True,
        "is_inverse_etf": False,
        "is_bond_etf": False,
        "is_equity_etf": True,
        "is_stock": False,
        "group_a_plus_role": "leverage_leg",
        "included_in_sin_lite": True,
        "exclusion_reason": None,
    },
    {
        "ticker": "00632R.TW",
        "canonical_ticker": "00632R.TW",
        "name": "Yuanta Taiwan 50 Daily Inverse ETF",
        "asset_type": "inverse_equity_etf",
        "market": "Taiwan",
        "exchange": "TWSE",
        "sector": "inverse_broad_market",
        "industry": "inverse_large_cap_equity",
        "is_financial_sector": False,
        "is_leveraged_etf": False,
        "is_inverse_etf": True,
        "is_bond_etf": False,
        "is_equity_etf": True,
        "is_stock": False,
        "group_a_plus_role": "inverse_hedge_watch",
        "included_in_sin_lite": True,
        "exclusion_reason": None,
    },
    {
        "ticker": "00646.TW",
        "canonical_ticker": "00646.TW",
        "name": "Yuanta S&P 500 ETF",
        "asset_type": "equity_etf",
        "market": "US",
        "exchange": "TWSE",
        "sector": "global_equity",
        "industry": "us_large_cap_equity",
        "is_financial_sector": False,
        "is_leveraged_etf": False,
        "is_inverse_etf": False,
        "is_bond_etf": False,
        "is_equity_etf": True,
        "is_stock": False,
        "group_a_plus_role": "global_equity_watch",
        "included_in_sin_lite": True,
        "exclusion_reason": None,
    },
    {
        "ticker": "00679B.TWO",
        "canonical_ticker": "00679B.TWO",
        "name": "Yuanta US Treasury 20Y ETF",
        "asset_type": "bond_etf",
        "market": "US",
        "exchange": "TPEx",
        "sector": "duration_bond",
        "industry": "us_treasury_long_duration",
        "is_financial_sector": False,
        "is_leveraged_etf": False,
        "is_inverse_etf": False,
        "is_bond_etf": True,
        "is_equity_etf": False,
        "is_stock": False,
        "group_a_plus_role": "bond_defense",
        "included_in_sin_lite": True,
        "exclusion_reason": None,
    },
    {
        "ticker": "00713.TW",
        "canonical_ticker": "00713.TW",
        "name": "Yuanta Taiwan High Dividend Low Volatility ETF",
        "asset_type": "equity_etf",
        "market": "Taiwan",
        "exchange": "TWSE",
        "sector": "defensive_equity",
        "industry": "high_dividend_low_volatility_equity",
        "is_financial_sector": False,
        "is_leveraged_etf": False,
        "is_inverse_etf": False,
        "is_bond_etf": False,
        "is_equity_etf": True,
        "is_stock": False,
        "group_a_plus_role": "defensive_equity_watch",
        "included_in_sin_lite": True,
        "exclusion_reason": None,
    },
    {
        "ticker": "00751B.TWO",
        "canonical_ticker": "00751B.TWO",
        "name": "Yuanta AAA-A Corporate Bond ETF",
        "asset_type": "bond_etf",
        "market": "US",
        "exchange": "TPEx",
        "sector": "credit_bond",
        "industry": "investment_grade_credit",
        "is_financial_sector": False,
        "is_leveraged_etf": False,
        "is_inverse_etf": False,
        "is_bond_etf": True,
        "is_equity_etf": False,
        "is_stock": False,
        "group_a_plus_role": "bond_defense",
        "included_in_sin_lite": True,
        "exclusion_reason": None,
    },
    {
        "ticker": "00878.TW",
        "canonical_ticker": "00878.TW",
        "name": "Cathay Taiwan ESG High Dividend ETF",
        "asset_type": "equity_etf",
        "market": "Taiwan",
        "exchange": "TWSE",
        "sector": "dividend_equity",
        "industry": "esg_high_dividend_equity",
        "is_financial_sector": False,
        "is_leveraged_etf": False,
        "is_inverse_etf": False,
        "is_bond_etf": False,
        "is_equity_etf": True,
        "is_stock": False,
        "group_a_plus_role": "income_equity_watch",
        "included_in_sin_lite": True,
        "exclusion_reason": None,
    },
    {
        "ticker": "2308.TW",
        "canonical_ticker": "2308.TW",
        "name": "Delta Electronics",
        "asset_type": "stock",
        "market": "Taiwan",
        "exchange": "TWSE",
        "sector": "electronics",
        "industry": "electronic_components_power",
        "is_financial_sector": False,
        "is_leveraged_etf": False,
        "is_inverse_etf": False,
        "is_bond_etf": False,
        "is_equity_etf": False,
        "is_stock": True,
        "group_a_plus_role": "large_cap_stock_watch",
        "included_in_sin_lite": True,
        "exclusion_reason": None,
    },
    {
        "ticker": "2317.TW",
        "canonical_ticker": "2317.TW",
        "name": "Hon Hai Precision",
        "asset_type": "stock",
        "market": "Taiwan",
        "exchange": "TWSE",
        "sector": "electronics",
        "industry": "electronics_manufacturing_services",
        "is_financial_sector": False,
        "is_leveraged_etf": False,
        "is_inverse_etf": False,
        "is_bond_etf": False,
        "is_equity_etf": False,
        "is_stock": True,
        "group_a_plus_role": "large_cap_stock_watch",
        "included_in_sin_lite": True,
        "exclusion_reason": None,
    },
    {
        "ticker": "2382.TW",
        "canonical_ticker": "2382.TW",
        "name": "Quanta Computer",
        "asset_type": "stock",
        "market": "Taiwan",
        "exchange": "TWSE",
        "sector": "electronics",
        "industry": "computer_hardware",
        "is_financial_sector": False,
        "is_leveraged_etf": False,
        "is_inverse_etf": False,
        "is_bond_etf": False,
        "is_equity_etf": False,
        "is_stock": True,
        "group_a_plus_role": "large_cap_stock_watch",
        "included_in_sin_lite": True,
        "exclusion_reason": None,
    },
    {
        "ticker": "2454.TW",
        "canonical_ticker": "2454.TW",
        "name": "MediaTek",
        "asset_type": "stock",
        "market": "Taiwan",
        "exchange": "TWSE",
        "sector": "semiconductors",
        "industry": "ic_design",
        "is_financial_sector": False,
        "is_leveraged_etf": False,
        "is_inverse_etf": False,
        "is_bond_etf": False,
        "is_equity_etf": False,
        "is_stock": True,
        "group_a_plus_role": "large_cap_stock_watch",
        "included_in_sin_lite": True,
        "exclusion_reason": None,
    },
    {
        "ticker": "2330.TW",
        "canonical_ticker": "2330.TW",
        "name": "Taiwan Semiconductor Manufacturing",
        "asset_type": "stock",
        "market": "Taiwan",
        "exchange": "TWSE",
        "sector": "semiconductors",
        "industry": "semiconductor_foundry",
        "is_financial_sector": False,
        "is_leveraged_etf": False,
        "is_inverse_etf": False,
        "is_bond_etf": False,
        "is_equity_etf": False,
        "is_stock": True,
        "group_a_plus_role": "tsmc_factor_anchor",
        "included_in_sin_lite": True,
        "exclusion_reason": None,
    },
    {
        "ticker": "wf",
        "canonical_ticker": "wf",
        "name": "Walk-forward fixture artifact",
        "asset_type": "test_artifact",
        "market": "unknown",
        "exchange": "unknown",
        "sector": "excluded",
        "industry": "excluded",
        "is_financial_sector": False,
        "is_leveraged_etf": False,
        "is_inverse_etf": False,
        "is_bond_etf": False,
        "is_equity_etf": False,
        "is_stock": False,
        "group_a_plus_role": "excluded_fixture",
        "included_in_sin_lite": False,
        "exclusion_reason": "non_ticker_walk_forward_artifact",
    },
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS ticker_metadata (
    ticker VARCHAR,
    canonical_ticker VARCHAR,
    name VARCHAR,
    asset_type VARCHAR,
    market VARCHAR,
    exchange VARCHAR,
    sector VARCHAR,
    industry VARCHAR,
    is_financial_sector BOOLEAN,
    is_leveraged_etf BOOLEAN,
    is_inverse_etf BOOLEAN,
    is_bond_etf BOOLEAN,
    is_equity_etf BOOLEAN,
    is_stock BOOLEAN,
    group_a_plus_role VARCHAR,
    included_in_sin_lite BOOLEAN,
    exclusion_reason VARCHAR,
    source VARCHAR,
    updated_at TIMESTAMP
)
"""

COLUMNS = (
    "ticker",
    "canonical_ticker",
    "name",
    "asset_type",
    "market",
    "exchange",
    "sector",
    "industry",
    "is_financial_sector",
    "is_leveraged_etf",
    "is_inverse_etf",
    "is_bond_etf",
    "is_equity_etf",
    "is_stock",
    "group_a_plus_role",
    "included_in_sin_lite",
    "exclusion_reason",
    "source",
    "updated_at",
)


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _seed_rows(updated_at: str) -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = []
    for item in SEED_METADATA:
        enriched = dict(item)
        enriched["source"] = "manual_group_a_plus_seed_20260719"
        enriched["updated_at"] = updated_at
        rows.append(tuple(enriched[column] for column in COLUMNS))
    return rows


def backfill_metadata(*, db_path: Path, output_path: Path, history_dir: Path | None) -> dict[str, Any]:
    updated_at = datetime.now().isoformat(timespec="seconds")
    seed_tickers = [item["ticker"] for item in SEED_METADATA]
    placeholders = ",".join(["?"] * len(seed_tickers))
    insert_sql = f"INSERT INTO ticker_metadata ({', '.join(COLUMNS)}) VALUES ({', '.join(['?'] * len(COLUMNS))})"

    with duckdb.connect(str(db_path)) as conn:
        conn.execute(SCHEMA)
        conn.execute(f"DELETE FROM ticker_metadata WHERE ticker IN ({placeholders})", seed_tickers)
        conn.executemany(insert_sql, _seed_rows(updated_at))

        ohlcv_rows = conn.execute(
            """
            SELECT ticker, COUNT(*) AS row_count, MIN(dt), MAX(dt)
            FROM ohlcv
            GROUP BY ticker
            ORDER BY ticker
            """
        ).fetchall()
        external_rows = conn.execute(
            """
            SELECT provider, ticker, COUNT(*) AS row_count, MIN(dt), MAX(dt)
            FROM external_market_ohlcv
            GROUP BY provider, ticker
            ORDER BY provider, ticker
            """
        ).fetchall()
        metadata_rows = conn.execute(
            """
            SELECT ticker, canonical_ticker, asset_type, sector, industry, included_in_sin_lite, exclusion_reason
            FROM ticker_metadata
            ORDER BY ticker
            """
        ).fetchall()

    metadata_tickers = {row[0] for row in metadata_rows}
    ohlcv_tickers = {row[0] for row in ohlcv_rows}
    external_tickers = {row[1] for row in external_rows}
    included_count = sum(1 for row in metadata_rows if bool(row[5]))
    excluded_count = sum(1 for row in metadata_rows if not bool(row[5]))
    report = {
        "schema_version": 1,
        "report_type": "group_a_plus_ticker_metadata_backfill",
        "generated_at": updated_at,
        "db_path": str(db_path),
        "policy": "static_metadata_only_no_price_download_no_weight_change",
        "table": "ticker_metadata",
        "seed_source": "manual_group_a_plus_seed_20260719",
        "inserted_or_replaced_rows": len(SEED_METADATA),
        "metadata_total_rows_after_backfill": len(metadata_rows),
        "sin_lite_included_rows": included_count,
        "sin_lite_excluded_rows": excluded_count,
        "ohlcv_ticker_count": len(ohlcv_tickers),
        "ohlcv_tickers_missing_metadata": sorted(ohlcv_tickers - metadata_tickers),
        "metadata_tickers_without_ohlcv": sorted(metadata_tickers - ohlcv_tickers),
        "external_market_tickers_with_metadata": sorted(external_tickers & metadata_tickers),
        "metadata_rows": [
            {
                "ticker": row[0],
                "canonical_ticker": row[1],
                "asset_type": row[2],
                "sector": row[3],
                "industry": row[4],
                "included_in_sin_lite": bool(row[5]),
                "exclusion_reason": row[6],
            }
            for row in metadata_rows
        ],
        "next_data_gaps": [
            "broad_taiwan_stock_ohlcv_universe_min_50_tickers",
            "sector_index_ohlcv",
            "hmm_bubble_state_probabilities",
            "transfer_entropy_network",
            "crash_window_maxloss_labels",
        ],
        "decision": {
            "metadata_backfilled": True,
            "price_data_changed": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = updated_at[:10].replace("-", "")
        (history_dir / f"ticker_metadata_backfill_{stamp}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    report = backfill_metadata(
        db_path=_resolve(args.db),
        output_path=_resolve(args.output),
        history_dir=None if args.no_history else _resolve(args.history_dir),
    )
    print(f"Ticker metadata backfill report: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "metadata_total_rows_after_backfill": report["metadata_total_rows_after_backfill"],
                "sin_lite_included_rows": report["sin_lite_included_rows"],
                "ohlcv_tickers_missing_metadata": report["ohlcv_tickers_missing_metadata"],
                "metadata_tickers_without_ohlcv": report["metadata_tickers_without_ohlcv"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
