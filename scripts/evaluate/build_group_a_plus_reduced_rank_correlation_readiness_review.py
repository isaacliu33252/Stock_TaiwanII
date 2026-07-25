#!/usr/bin/env python3
"""Build a research-only reduced-rank correlation readiness review.

Inspired by arXiv 2107.09048. This checks whether GroupA+ can import the
paper's reduced-rank correlation market-state precursor idea. It never changes
live weights or promotes a crash predictor.
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
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/reduced_rank_correlation_readiness_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/reduced_rank_correlation_readiness/history"
SOURCE_PAPER = "C:/Users/isaac/Downloads/2107.09048.pdf"

RELATED_ARTIFACTS = {
    "reduced_rank_correlation_proxy": PROJECT_ROOT / "report/group_a_plus/latest/reduced_rank_correlation_proxy.json",
    "reduced_rank_correlation_proxy_param_sweep": (
        PROJECT_ROOT / "report/group_a_plus/latest/reduced_rank_correlation_proxy_param_sweep.json"
    ),
    "reduced_rank_correlation_crash_window_backtest": (
        PROJECT_ROOT / "report/group_a_plus/latest/reduced_rank_correlation_crash_window_backtest.json"
    ),
    "reduced_rank_confirmation_overlap_backtest": (
        PROJECT_ROOT / "report/group_a_plus/latest/reduced_rank_confirmation_overlap_backtest.json"
    ),
    "cross_market_graph_shadow": PROJECT_ROOT / "report/group_a_plus/latest/cross_market_graph_shadow.json",
    "trigate_vol_memory_shadow": PROJECT_ROOT / "report/group_a_plus/latest/trigate_vol_memory_shadow.json",
    "systemic_bubble_time_at_risk_review": (
        PROJECT_ROOT / "report/group_a_plus/latest/systemic_bubble_time_at_risk_review.json"
    ),
    "illiquidity_network_readiness_review": (
        PROJECT_ROOT / "report/group_a_plus/latest/illiquidity_network_readiness_review.json"
    ),
    "speculative_influence_network_readiness_review": (
        PROJECT_ROOT / "report/group_a_plus/latest/speculative_influence_network_readiness_review.json"
    ),
}

SECTOR_TABLE_CANDIDATES = ("ticker_metadata", "stock_sector_style", "stock_industry_mapping")


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_optional(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _table_counts(conn: duckdb.DuckDBPyConnection, tables: list[str]) -> dict[str, int | None]:
    counts: dict[str, int | None] = {}
    for table in tables:
        try:
            counts[table] = int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] or 0)
        except Exception:
            counts[table] = None
    return counts


def _db_summary(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        return {"db_exists": False, "tables": [], "table_counts": {}, "price_universe": {}}
    with duckdb.connect(str(db_path), read_only=True) as conn:
        tables = sorted(row[0] for row in conn.execute("SHOW TABLES").fetchall())
        counts = _table_counts(conn, tables)
        price_universe: dict[str, Any] = {}
        if "ohlcv" in tables:
            row = conn.execute("SELECT COUNT(DISTINCT ticker), MIN(dt), MAX(dt), COUNT(*) FROM ohlcv").fetchone()
            price_universe["ohlcv"] = {
                "distinct_tickers": int(row[0] or 0),
                "min_dt": str(row[1]) if row[1] is not None else None,
                "max_dt": str(row[2]) if row[2] is not None else None,
                "rows": int(row[3] or 0),
            }
        if "external_market_ohlcv" in tables:
            row = conn.execute(
                "SELECT COUNT(DISTINCT ticker), MIN(dt), MAX(dt), COUNT(*) FROM external_market_ohlcv"
            ).fetchone()
            price_universe["external_market_ohlcv"] = {
                "distinct_tickers": int(row[0] or 0),
                "min_dt": str(row[1]) if row[1] is not None else None,
                "max_dt": str(row[2]) if row[2] is not None else None,
                "rows": int(row[3] or 0),
            }
    return {"db_exists": True, "tables": tables, "table_counts": counts, "price_universe": price_universe}


def _related_artifacts() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, path in RELATED_ARTIFACTS.items():
        payload = _load_optional(path)
        out[name] = {
            "path": str(path),
            "exists": bool(payload),
            "status": payload.get("status") if isinstance(payload, dict) else None,
            "policy": payload.get("policy") if isinstance(payload, dict) else None,
        }
    return out


def build_review(*, db_path: Path = DEFAULT_DB, as_of: str | None = "2026-07-20") -> dict[str, Any]:
    summary = _db_summary(db_path)
    tables = set(summary.get("tables", []))
    counts = summary.get("table_counts", {})
    price = summary.get("price_universe", {})
    ohlcv = price.get("ohlcv") or {}
    external = price.get("external_market_ohlcv") or {}
    local_ticker_count = int(ohlcv.get("distinct_tickers") or 0)
    external_ticker_count = int(external.get("distinct_tickers") or 0)
    sector_tables = sorted(tables & set(SECTOR_TABLE_CANDIDATES))
    populated_sector_tables = [table for table in sector_tables if (counts.get(table) or 0) > 0]
    broad_sector_universe_ready = local_ticker_count >= 100 and bool(populated_sector_tables)
    weak_proxy_ready = local_ticker_count + external_ticker_count >= 20
    rolling_window_ready = bool(ohlcv.get("max_dt")) and bool(ohlcv.get("min_dt"))

    blockers: list[str] = []
    warnings: list[str] = []
    if not summary.get("db_exists"):
        blockers.append("stock_database_missing")
    if local_ticker_count < 100:
        blockers.append("broad_stock_universe_below_reduced_rank_requirement")
    if not populated_sector_tables:
        blockers.append("sector_metadata_missing")
    if not rolling_window_ready:
        blockers.append("rolling_42_day_price_windows_unavailable")
    blockers.extend(
        [
            "reduced_rank_correlation_matrix_not_implemented",
            "averaged_distance_transition_monitor_not_implemented",
            "kmeans_market_state_snapshot_not_implemented",
            "taiwan_crash_window_walkforward_validation_missing",
            "crash_predictor_not_allowed_for_live_execution",
        ]
    )
    if weak_proxy_ready:
        warnings.append("weak_cross_market_proxy_possible_but_not_paper_equivalent")
    else:
        blockers.append("weak_cross_market_proxy_unavailable")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_reduced_rank_correlation_readiness_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "actual_data_end": ohlcv.get("max_dt"),
        "status": "blocked",
        "policy": "research_only_reduced_rank_correlation_no_crash_predictor_no_weight_change",
        "source_paper": {
            "path": SOURCE_PAPER,
            "title": (
                "A New Attempt to Identify Long-term Precursors for Endogenous Financial Crises "
                "in the Market Correlation Structures"
            ),
            "arxiv": "2107.09048v2",
            "imported_concepts": [
                "largest_eigenvalue_market_mode_subtraction",
                "reduced_rank_correlation_matrix",
                "averaged_distance_transition_monitor",
                "kmeans_market_state_snapshots",
                "systemic_fragility_manual_review_warning",
            ],
            "not_imported": [
                "automatic_crash_prediction",
                "execution_gate",
                "target_weight_change",
                "automatic_rebalance",
            ],
        },
        "data_readiness": {
            "db_path": str(db_path),
            "db_exists": summary.get("db_exists"),
            "price_universe": price,
            "sector_table_candidates": list(SECTOR_TABLE_CANDIDATES),
            "matched_sector_tables": sector_tables,
            "populated_sector_tables": populated_sector_tables,
            "minimum_broad_stock_tickers": 100,
            "local_ticker_count": local_ticker_count,
            "external_ticker_count": external_ticker_count,
            "broad_sector_universe_ready": broad_sector_universe_ready,
            "weak_cross_market_proxy_ready": weak_proxy_ready,
            "rolling_window_length_trading_days": 42,
            "rolling_window_ready": rolling_window_ready,
        },
        "related_group_a_plus_artifacts": _related_artifacts(),
        "validation_readiness": {
            "reduced_rank_correlation_matrix_implemented": False,
            "averaged_distance_monitor_implemented": False,
            "kmeans_market_state_snapshots_implemented": False,
            "taiwan_crash_window_walkforward_validated": False,
            "false_positive_audit_completed": False,
            "paper_equivalent_sector_breadth": False,
        },
        "candidate_next_work": [
            "Build a weak cross-market reduced-rank correlation proxy as shadow-only.",
            "Add sector metadata and broad Taiwan stock universe before paper-equivalent implementation.",
            "Validate on Taiwan 2015, 2018, 2020, 2022, and 2026 stress windows.",
            "Compare incremental warning value against systemic bubble, SIN-lite, and tri-gate volatility memory.",
        ],
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "decision": {
            "reduced_rank_correlation_ready": False,
            "weak_proxy_ready_for_research": weak_proxy_ready,
            "paper_equivalent_ready": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def _history_path(history_dir: Path, as_of: str | None, actual_data_end: str | None) -> Path:
    stamp = str(as_of or actual_data_end or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"reduced_rank_correlation_readiness_{stamp}.json"


def write_review(review: dict[str, Any], output_path: Path, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, review.get("as_of"), review.get("actual_data_end")).write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--as-of", default="2026-07-20")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(db_path=_resolve(args.db), as_of=args.as_of)
    history_dir = None if args.no_history else _resolve(args.history_dir)
    write_review(review, _resolve(args.output), history_dir)
    print(f"Reduced-rank correlation readiness review: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "local_ticker_count": review["data_readiness"]["local_ticker_count"],
                "weak_proxy_ready_for_research": review["decision"]["weak_proxy_ready_for_research"],
                "allow_00631l_add": review["decision"]["allow_00631l_add"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
