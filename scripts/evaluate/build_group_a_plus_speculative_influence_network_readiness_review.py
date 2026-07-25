#!/usr/bin/env python3
"""Build a research-only speculative-influence-network readiness review.

Inspired by arXiv 1510.08162. The paper requires broad sector/firm coverage,
HMM bubble-state probabilities, and transfer-entropy influence networks before
any speculative influence signal can be considered for GroupA+.
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
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/speculative_influence_network_readiness_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/speculative_influence_network_readiness/history"
SOURCE_PAPER = "C:/Users/isaac/Downloads/1510.08162.pdf"

REQUIRED_TABLES = {
    "sector_or_style_mapping": ("ticker_metadata", "stock_sector_style", "stock_industry_mapping"),
    "sector_index_history": ("sector_index_ohlcv", "twse_sector_indices", "industry_index_ohlcv"),
    "hmm_bubble_state_probabilities": ("hmm_bubble_state_probabilities", "bubble_state_probabilities"),
    "transfer_entropy_network": ("transfer_entropy_network", "speculative_influence_network", "nsii_network"),
    "crash_maxloss_validation": ("crash_window_maxloss_labels", "maxloss_validation_labels"),
}


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _table_summary(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        return {"db_exists": False, "tables": [], "ohlcv": {}}
    with duckdb.connect(str(db_path), read_only=True) as conn:
        tables = sorted(row[0] for row in conn.execute("SHOW TABLES").fetchall())
        table_counts = {}
        for table in tables:
            try:
                table_counts[table] = int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] or 0)
            except Exception:
                table_counts[table] = None
        ohlcv: dict[str, Any] = {}
        if "ohlcv" in tables:
            row = conn.execute("SELECT COUNT(DISTINCT ticker), MIN(dt), MAX(dt), COUNT(*) FROM ohlcv").fetchone()
            ohlcv = {
                "distinct_tickers": int(row[0] or 0),
                "min_dt": str(row[1]) if row[1] is not None else None,
                "max_dt": str(row[2]) if row[2] is not None else None,
                "rows": int(row[3] or 0),
            }
    return {"db_exists": True, "tables": tables, "table_counts": table_counts, "ohlcv": ohlcv}


def _requirement_status(tables: list[str], table_counts: dict[str, int | None]) -> dict[str, Any]:
    table_set = set(tables)
    out: dict[str, Any] = {}
    for requirement, aliases in REQUIRED_TABLES.items():
        matched = sorted(table_set & set(aliases))
        populated = [table for table in matched if (table_counts.get(table) or 0) > 0]
        out[requirement] = {
            "required_any_of": list(aliases),
            "matched_tables": matched,
            "matched_table_counts": {table: table_counts.get(table) for table in matched},
            "populated_tables": populated,
            "available": bool(populated),
        }
    return out


def _data_backfill_plan() -> dict[str, Any]:
    return {
        "priority": [
            "sector_or_style_mapping",
            "broad_taiwan_stock_ohlcv_universe",
            "sector_index_history",
            "hmm_bubble_state_probabilities",
            "transfer_entropy_network",
            "crash_maxloss_validation_labels",
        ],
        "minimum_viable_tables": {
            "ticker_metadata": {
                "purpose": "Map stocks to sector, industry, financial/non-financial group, and market-cap bucket.",
                "minimum_columns": ["ticker", "name", "sector", "industry", "is_financial_sector", "market_cap_bucket"],
            },
            "sector_index_ohlcv": {
                "purpose": "Build sector-level bubble-state nodes comparable to the paper's sector indices.",
                "minimum_columns": ["sector", "dt", "open", "high", "low", "close", "volume"],
            },
            "hmm_bubble_state_probabilities": {
                "purpose": "Cache per-node probability of speculative bubble state.",
                "minimum_columns": ["node_id", "node_type", "dt", "bubble_probability", "model_version"],
            },
            "transfer_entropy_network": {
                "purpose": "Store directional speculative influence among bubble-qualified nodes.",
                "minimum_columns": ["source_node", "target_node", "window_start", "window_end", "transfer_entropy", "nsii"],
            },
            "crash_window_maxloss_labels": {
                "purpose": "Validate whether influence metrics predict later maximum loss.",
                "minimum_columns": ["node_id", "window_start", "window_end", "max_loss", "label_source"],
            },
        },
        "validation_requirements": [
            "Use shadow-only review first; no live target-weight effect.",
            "Validate separately on Taiwan 2015, 2018, 2020, 2022, and 2026 stress windows.",
            "Compare incremental value against SRR-lite and systemic bubble time-at-risk review.",
            "Reject thresholds that improve recall only by raising false positives materially.",
            "Keep China 2006-2008 findings separate from Taiwan-calibrated thresholds.",
        ],
    }


def build_review(*, db_path: Path = DEFAULT_DB, as_of: str | None = None) -> dict[str, Any]:
    summary = _table_summary(db_path)
    requirements = _requirement_status(summary.get("tables", []), summary.get("table_counts", {}))
    ohlcv = summary.get("ohlcv") or {}
    broad_universe_ready = int(ohlcv.get("distinct_tickers") or 0) >= 50
    missing = [name for name, item in requirements.items() if not item["available"]]
    blockers = [f"missing_{name}" for name in missing]
    if not broad_universe_ready:
        blockers.append("broad_stock_universe_insufficient_for_sin")
    blockers.extend(
        [
            "sornette_andersen_hmm_not_implemented",
            "transfer_entropy_sin_not_implemented",
            "nsii_maxloss_validation_missing_for_taiwan",
            "china_2006_2008_parameters_not_portable_to_group_a_plus",
            "speculative_influence_signal_not_allowed_to_change_live_weights",
        ]
    )

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_speculative_influence_network_readiness_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "actual_data_end": ohlcv.get("max_dt"),
        "source_paper": {
            "path": SOURCE_PAPER,
            "title": "Speculative Influence Network during financial bubbles: application to Chinese Stock Markets",
            "imported_concept": (
                "HMM bubble-state probability, transfer-entropy speculative influence network, "
                "net speculative influence intensity, maximum-loss validation"
            ),
        },
        "policy": "research_only_speculative_influence_network_readiness_no_weight_change",
        "status": "blocked",
        "data": {
            "db_path": str(db_path),
            "db_exists": summary.get("db_exists"),
            "available_tables": summary.get("tables", []),
            "table_counts": summary.get("table_counts", {}),
            "ohlcv_summary": ohlcv,
            "broad_universe_min_tickers": 50,
            "broad_universe_ready": broad_universe_ready,
            "requirements": requirements,
        },
        "candidate_imports": {
            "bubble_state_probability": "concept overlaps with systemic bubble time-at-risk; not implemented as HMM live signal",
            "speculative_influence_network": "possible only after sector/firm universe and transfer entropy validation exist",
            "nsii_ranked_maxloss_validation": "useful validation design; no current Taiwan labels",
            "finance_vs_industry_asymmetry_check": "research-only sector diagnostic after metadata backfill",
        },
        "data_backfill_plan": _data_backfill_plan(),
        "blocking_reasons": sorted(set(blockers)),
        "decision": {
            "speculative_influence_network_ready": False,
            "hmm_bubble_state_ready": False,
            "transfer_entropy_network_ready": False,
            "maxloss_validation_ready": False,
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
    return history_dir / f"speculative_influence_network_readiness_{stamp}.json"


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
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(db_path=_resolve(args.db), as_of=args.as_of)
    history_dir = None if args.no_history else _resolve(args.history_dir)
    write_review(review, _resolve(args.output), history_dir)
    print(f"Speculative-influence-network readiness review: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "actual_data_end": review["actual_data_end"],
                "speculative_influence_network_ready": review["decision"]["speculative_influence_network_ready"],
                "blocking_reasons": review["blocking_reasons"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
