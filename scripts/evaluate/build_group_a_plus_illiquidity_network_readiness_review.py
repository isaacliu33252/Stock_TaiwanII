#!/usr/bin/env python3
"""Build a research-only illiquidity-network readiness review for GroupA+.

Inspired by arXiv 2004.01917. The paper requires high-frequency bid/ask and
market-wide stock failure data; this review checks whether GroupA+ has those
inputs before any illiquidity-network crash-warning idea can be promoted.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/illiquidity_network_readiness_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/illiquidity_network_readiness/history"
SOURCE_PAPER = "C:/Users/isaac/Downloads/2004.01917.pdf"

REQUIRED_TABLES = {
    "high_frequency_bid_ask": (
        "intraday_bid_ask_quotes",
        "order_book_quotes",
        "twse_best_bid_ask",
    ),
    "intraday_minute_liquidity": (
        "intraday_minute_illiquidity",
        "intraday_minute_quotes",
    ),
    "market_wide_failure_events": (
        "limit_down_events",
        "no_bid_no_quote_events",
        "stock_failure_events",
    ),
    "stock_sector_style_mapping": (
        "stock_sector_style",
        "stock_industry_mapping",
        "ticker_metadata",
    ),
}


def _data_backfill_plan() -> dict[str, Any]:
    return {
        "current_decision": {
            "high_frequency_backfill": "deferred",
            "decision_date": "2026-07-19",
            "reason": "High-frequency full-market bid/ask data is too large for the current phase.",
            "allowed_next_step": "daily_ohlcv_volume_proxy_only_research_dashboard",
            "live_strategy_effect": "none",
        },
        "priority": [
            "stock_sector_style_mapping",
            "daily_ohlcv_volume_proxy",
            "market_wide_failure_events_proxy",
            "high_frequency_bid_ask_deferred",
            "intraday_minute_liquidity_deferred",
        ],
        "minimum_viable_tables": {
            "intraday_bid_ask_quotes": {
                "purpose": "Build bid-ask spread or weighted-spread illiquidity at intraday frequency.",
                "minimum_columns": [
                    "ticker",
                    "dt",
                    "timestamp",
                    "best_bid_price",
                    "best_bid_volume",
                    "best_ask_price",
                    "best_ask_volume",
                ],
                "preferred_columns": [
                    "bid_price_1_to_5",
                    "bid_volume_1_to_5",
                    "ask_price_1_to_5",
                    "ask_volume_1_to_5",
                ],
                "minimum_frequency": "1min_or_better",
                "required_universe": "Taiwan listed stocks, not only GroupA+ ETFs",
            },
            "intraday_minute_illiquidity": {
                "purpose": "Cache derived minute-level spread or weighted-spread illiquidity.",
                "minimum_columns": [
                    "ticker",
                    "dt",
                    "minute",
                    "spread_pct",
                    "weighted_spread_pct",
                    "source",
                ],
                "dependency": "intraday_bid_ask_quotes",
            },
            "stock_failure_events": {
                "purpose": "Identify systemic liquidity-failure intervals used by the five-day warning candidate.",
                "minimum_columns": [
                    "ticker",
                    "dt",
                    "timestamp",
                    "event_type",
                    "limit_down_price",
                    "last_price",
                    "no_bid_flag",
                    "no_quote_flag",
                ],
                "event_types": [
                    "limit_down_touch",
                    "limit_down_lock",
                    "no_bid",
                    "no_quote",
                ],
            },
            "ticker_metadata": {
                "purpose": "Inspect sector/style concentration of critical liquidity-stress nodes.",
                "minimum_columns": [
                    "ticker",
                    "name",
                    "market",
                    "sector",
                    "industry",
                    "market_cap_bucket",
                    "is_financial_sector",
                ],
            },
        },
        "validation_requirements": [
            "Build shadow-only signal first; no live target-weight effect.",
            "Validate on Taiwan crash/stress windows including 2015, 2020, 2022, and 2026.",
            "Measure one-day-ahead hit rate, false-positive rate, and overlap with SRR-lite crash watch.",
            "Run randomization/null tests before treating network links as non-spurious.",
            "Keep China 2015 thresholds separate from Taiwan-calibrated thresholds.",
        ],
        "proxies_allowed_now": {
            "daily_ohlcv_volume_proxy": {
                "allowed": True,
                "use": "coarse monitoring only",
                "paper_equivalent": False,
                "reason": "Daily OHLCV cannot identify no-bid/no-quote timing or intraday systemic failures.",
            },
            "etf_only_universe": {
                "allowed": True,
                "use": "sanity-check dashboard only",
                "paper_equivalent": False,
                "reason": "The paper's network relies on a broad stock universe, not a few ETFs.",
            },
        },
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


def _float_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if pd.notna(number) else None


PROXY_STATE_THRESHOLDS = {
    "normal_lt": 0.10,
    "watch_gte": 0.10,
    "elevated_gte": 0.20,
    "stress_gte": 0.35,
}


def _daily_proxy_state(stress_score: float | None, component_counts: dict[str, int]) -> dict[str, Any]:
    if stress_score is None:
        return {
            "stress_state": "unavailable",
            "manual_review_required": False,
            "state_reasons": ["stress_score_unavailable"],
        }
    if stress_score >= PROXY_STATE_THRESHOLDS["stress_gte"]:
        state = "stress"
    elif stress_score >= PROXY_STATE_THRESHOLDS["elevated_gte"]:
        state = "elevated"
    elif stress_score >= PROXY_STATE_THRESHOLDS["watch_gte"]:
        state = "watch"
    else:
        state = "normal"

    reasons = [
        f"{name}_count:{count}"
        for name, count in sorted(component_counts.items())
        if count
    ]
    if not reasons:
        reasons = ["no_active_daily_ohlcv_stress_components"]
    return {
        "stress_state": state,
        "manual_review_required": state in {"elevated", "stress"},
        "state_reasons": reasons,
    }


def _daily_ohlcv_liquidity_stress_proxy(db_path: Path, as_of: str | None) -> dict[str, Any]:
    if not db_path.exists():
        return {"status": "unavailable", "reason": "db_missing", "paper_equivalent": False}
    where = "WHERE dt <= ?" if as_of else ""
    params = [as_of] if as_of else []
    with duckdb.connect(str(db_path), read_only=True) as conn:
        tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
        if "ohlcv" not in tables:
            return {"status": "unavailable", "reason": "ohlcv_missing", "paper_equivalent": False}
        frame = conn.execute(
            f"""
            SELECT ticker, dt, open, high, low, close, volume
            FROM ohlcv
            {where}
            ORDER BY ticker, dt
            """,
            params,
        ).fetchdf()
    if frame.empty:
        return {"status": "unavailable", "reason": "ohlcv_empty", "paper_equivalent": False}

    frame["dt"] = pd.to_datetime(frame["dt"])
    frame = frame.sort_values(["ticker", "dt"]).copy()
    grouped = frame.groupby("ticker", group_keys=False)
    frame["prev_close"] = grouped["close"].shift(1)
    frame["daily_return"] = frame["close"] / frame["prev_close"] - 1.0
    frame["range_pct"] = (frame["high"] - frame["low"]) / frame["prev_close"]
    trailing_volume = grouped["volume"].rolling(20, min_periods=10).median().shift(1).reset_index(level=0, drop=True)
    trailing_range_p95 = grouped["range_pct"].rolling(252, min_periods=60).quantile(0.95).shift(1).reset_index(level=0, drop=True)
    frame["volume_ratio_20d"] = frame["volume"] / trailing_volume
    frame["range_p95_252d"] = trailing_range_p95
    frame["volume_drought_flag"] = frame["volume_ratio_20d"] < 0.50
    frame["range_spike_flag"] = frame["range_pct"] > frame["range_p95_252d"]
    frame["negative_return_flag"] = frame["daily_return"] <= -0.03
    frame["limit_down_proxy_flag"] = (frame["daily_return"] <= -0.095) | (frame["low"] <= frame["prev_close"] * 0.905)
    latest_dt = frame["dt"].max()
    latest = frame[frame["dt"] == latest_dt].copy()
    coverage = int(latest["ticker"].nunique())

    def _count(column: str) -> int:
        return int(latest[column].fillna(False).sum())

    component_counts = {
        "volume_drought": _count("volume_drought_flag"),
        "range_spike": _count("range_spike_flag"),
        "negative_return": _count("negative_return_flag"),
        "limit_down_proxy": _count("limit_down_proxy_flag"),
    }
    if coverage > 0:
        stress_score = (
            0.30 * component_counts["volume_drought"]
            + 0.25 * component_counts["range_spike"]
            + 0.25 * component_counts["negative_return"]
            + 0.20 * component_counts["limit_down_proxy"]
        ) / coverage
    else:
        stress_score = None
    state_payload = _daily_proxy_state(_float_or_none(stress_score), component_counts)

    daily_scores = []
    for dt, rows in frame.groupby("dt"):
        n = int(rows["ticker"].nunique())
        if n <= 0:
            continue
        score = (
            0.30 * int(rows["volume_drought_flag"].fillna(False).sum())
            + 0.25 * int(rows["range_spike_flag"].fillna(False).sum())
            + 0.25 * int(rows["negative_return_flag"].fillna(False).sum())
            + 0.20 * int(rows["limit_down_proxy_flag"].fillna(False).sum())
        ) / n
        daily_scores.append({"dt": str(dt.date()), "stress_score": float(score), "coverage_tickers": n})

    latest_rows = []
    for _, row in latest.sort_values("ticker").iterrows():
        latest_rows.append(
            {
                "ticker": str(row["ticker"]),
                "daily_return": _float_or_none(row.get("daily_return")),
                "range_pct": _float_or_none(row.get("range_pct")),
                "volume_ratio_20d": _float_or_none(row.get("volume_ratio_20d")),
                "volume_drought_flag": bool(row.get("volume_drought_flag")) if pd.notna(row.get("volume_drought_flag")) else False,
                "range_spike_flag": bool(row.get("range_spike_flag")) if pd.notna(row.get("range_spike_flag")) else False,
                "negative_return_flag": bool(row.get("negative_return_flag")) if pd.notna(row.get("negative_return_flag")) else False,
                "limit_down_proxy_flag": bool(row.get("limit_down_proxy_flag")) if pd.notna(row.get("limit_down_proxy_flag")) else False,
            }
        )

    return {
        "status": "available_research_proxy" if coverage >= 3 else "insufficient_proxy_coverage",
        "paper_equivalent": False,
        "policy": "daily_ohlcv_proxy_only_no_live_weight_change",
        "live_strategy_effect": "none",
        "actual_data_end": str(latest_dt.date()),
        "coverage_tickers": coverage,
        "stress_score": _float_or_none(stress_score),
        "stress_state": state_payload["stress_state"],
        "state_thresholds": PROXY_STATE_THRESHOLDS,
        "state_reasons": state_payload["state_reasons"],
        "manual_review_required": state_payload["manual_review_required"],
        "component_counts": component_counts,
        "latest_rows": latest_rows,
        "recent_daily_scores": daily_scores[-10:],
        "limitations": [
            "Daily OHLCV cannot observe bid/ask spread.",
            "Daily OHLCV cannot observe no-bid/no-quote intervals.",
            "ETF-only or small-universe coverage cannot reproduce paper-level market-wide network contagion.",
            "This proxy is for research dashboard use only.",
        ],
    }


def build_review(*, db_path: Path = DEFAULT_DB, as_of: str | None = None) -> dict[str, Any]:
    summary = _table_summary(db_path)
    requirements = _requirement_status(summary.get("tables", []), summary.get("table_counts", {}))
    missing = [name for name, item in requirements.items() if not item["available"]]

    blockers = [
        f"missing_{name}" for name in missing
    ]
    blockers.extend(
        [
            "nmi_illiquidity_network_not_implemented",
            "five_day_systemic_failure_signal_not_validated_for_taiwan",
            "china_2015_parameters_not_portable_to_group_a_plus",
            "crash_warning_not_allowed_to_change_live_weights",
        ]
    )
    ohlcv = summary.get("ohlcv") or {}
    if not ohlcv:
        blockers.append("ohlcv_summary_unavailable")
    daily_proxy = _daily_ohlcv_liquidity_stress_proxy(db_path, as_of)

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_illiquidity_network_readiness_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "actual_data_end": ohlcv.get("max_dt"),
        "source_paper": {
            "path": SOURCE_PAPER,
            "title": "The illiquidity network of stocks in China's market crash",
            "imported_concept": (
                "illiquidity comovement network, systemic liquidity-failure early warning, "
                "finance-sector and low-degree trigger inspection"
            ),
        },
        "policy": "research_only_illiquidity_network_readiness_no_crash_guard_no_weight_change",
        "status": "blocked",
        "data": {
            "db_path": str(db_path),
            "db_exists": summary.get("db_exists"),
            "available_tables": summary.get("tables", []),
            "table_counts": summary.get("table_counts", {}),
            "ohlcv_summary": ohlcv,
            "requirements": requirements,
        },
        "candidate_imports": {
            "liquidity_contagion_watch": "possible only after high-frequency bid/ask or reliable intraday spread data exists",
            "five_day_systemic_failure_count": "paper idea retained, not implemented as live signal",
            "finance_sector_core_watch": "concept maps to Taiwan finance-heavy systemic-risk watch, but sector/style metadata is missing",
            "low_degree_trigger_watch": "research-only; requires full universe graph and limit-down/no-bid failure timing",
        },
        "daily_ohlcv_liquidity_stress_proxy": daily_proxy,
        "data_backfill_plan": _data_backfill_plan(),
        "blocking_reasons": sorted(set(blockers)),
        "decision": {
            "illiquidity_network_ready": False,
            "daily_ohlcv_liquidity_stress_proxy_available": daily_proxy.get("status") == "available_research_proxy",
            "high_frequency_liquidity_data_ready": False,
            "systemic_failure_signal_ready": False,
            "promote_to_live": False,
            "crash_guard_allowed": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def _history_path(history_dir: Path, as_of: str | None, actual_data_end: str | None) -> Path:
    stamp = str(as_of or actual_data_end or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"illiquidity_network_readiness_{stamp}.json"


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
    print(f"Illiquidity-network readiness review: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "actual_data_end": review["actual_data_end"],
                "illiquidity_network_ready": review["decision"]["illiquidity_network_ready"],
                "blocking_reasons": review["blocking_reasons"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
