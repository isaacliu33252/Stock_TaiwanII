#!/usr/bin/env python3
"""Multi-ticker coverage smoke for the accepted LLM state/reward proposal."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import (
    ACCEPTED_PROPOSAL_ID,
    DEFAULT_DB,
    DEFAULT_VALIDATION,
    _accepted_proposals,
    _feature_frame,
    _finite_summary,
    _load_json,
    _load_ohlcv_from_db,
    _proposal_columns,
    _resolve,
    _window_summary,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_multi_ticker_smoke_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_interface_multi_ticker_smoke/history"
DEFAULT_TICKERS = [
    "0050.TW",
    "00631L.TW",
    "00632R.TW",
    "0056.TW",
    "00713.TW",
    "00878.TW",
    "00679B.TWO",
    "00751B.TWO",
]


def _ticker_smoke(
    db_path: Path,
    ticker: str,
    *,
    start: str,
    min_rows: int,
    min_end_date: str,
    proposal_id: str,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    df = _load_ohlcv_from_db(db_path, ticker=ticker, start=start)
    if df.empty:
        return {
            "ticker": ticker,
            "status": "blocked",
            "data_range": {},
            "finite_summary": {},
            "window_summary": {},
            "blocking_reasons": ["missing_ohlcv_data"],
            "warning_reasons": [],
        }

    frame = _feature_frame(df, proposal_id=proposal_id)
    columns = _proposal_columns(proposal_id)
    feature_columns = columns["feature_columns"]
    reward_columns = columns["reward_columns"]
    finite_summary = _finite_summary(frame, feature_columns + reward_columns)
    windows = _window_summary(frame, feature_columns=feature_columns)
    data_range = {
        "start": df["date"].min().date().isoformat(),
        "end": df["date"].max().date().isoformat(),
        "rows": int(len(df)),
    }

    if len(df) < min_rows:
        blockers.append(f"rows_below_min:{len(df)}<{min_rows}")
    if data_range["end"] < min_end_date:
        blockers.append(f"end_date_before_min:{data_range['end']}<{min_end_date}")

    for column in feature_columns + reward_columns:
        column_summary = (finite_summary.get("columns") or {}).get(column)
        if not column_summary or column_summary.get("finite_count", 0) <= 0:
            blockers.append(f"no_finite_values:{column}")

    reward_col = frame["reward_proxy"]
    if reward_col.min() < -0.25 or reward_col.max() > 0.0:
        blockers.append("reward_proxy_not_bounded")
    if windows and not windows.get("all_windows_have_min_rows"):
        warnings.append("some_yearly_windows_have_less_than_120_feature_ready_rows")

    return {
        "ticker": ticker,
        "status": "blocked" if blockers else "available_for_manual_offline_review",
        "data_range": data_range,
        "finite_summary": finite_summary,
        "window_summary": windows,
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
    }


def build_review(
    *,
    validation_path: Path = DEFAULT_VALIDATION,
    db_path: Path = DEFAULT_DB,
    tickers: list[str] | None = None,
    start: str = "2016-01-01",
    min_rows: int = 240,
    min_end_date: str = "2026-07-17",
    proposal_id: str = ACCEPTED_PROPOSAL_ID,
    as_of: str = "2026-07-20",
) -> dict[str, Any]:
    validation = _load_json(validation_path)
    accepted_ids = _accepted_proposals(validation)
    selected_tickers = tickers or list(DEFAULT_TICKERS)

    blockers: list[str] = []
    if not validation:
        blockers.append("missing_proposal_validation_review")
    if proposal_id not in accepted_ids:
        blockers.append("accepted_sample_proposal_missing")
    if not db_path.exists():
        blockers.append("missing_duckdb")

    ticker_results = [
        _ticker_smoke(
            db_path,
            ticker,
            start=start,
            min_rows=min_rows,
            min_end_date=min_end_date,
            proposal_id=proposal_id,
        )
        for ticker in selected_tickers
    ] if db_path.exists() else []

    blocked_tickers = [row["ticker"] for row in ticker_results if row["status"] == "blocked"]
    if blocked_tickers:
        blockers.append(f"blocked_tickers:{','.join(blocked_tickers)}")

    available_count = sum(1 for row in ticker_results if row["status"] == "available_for_manual_offline_review")
    latest_end = max((row.get("data_range") or {}).get("end", "") for row in ticker_results) if ticker_results else None
    earliest_end = min((row.get("data_range") or {}).get("end", "") for row in ticker_results) if ticker_results else None

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_interface_multi_ticker_smoke_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "available_for_manual_offline_review",
        "policy": "multi_ticker_offline_smoke_only_no_model_training_no_live_action",
        "inputs": {
            "validation_review": str(validation_path),
            "db": str(db_path),
            "tickers": selected_tickers,
            "start": start,
            "min_rows": min_rows,
            "min_end_date": min_end_date,
            "accepted_proposal_id": proposal_id,
            "accepted_proposal_found": proposal_id in accepted_ids,
        },
        "summary": {
            "ticker_count": len(selected_tickers),
            "available_for_manual_offline_review_count": available_count,
            "blocked_tickers": blocked_tickers,
            "earliest_end": earliest_end,
            "latest_end": latest_end,
        },
        "ticker_results": ticker_results,
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(
            {
                warning
                for row in ticker_results
                for warning in row.get("warning_reasons", [])
            }
        ),
        "decision": {
            "available_for_manual_offline_review": not blockers,
            "model_training_allowed": False,
            "ppo_training_allowed": False,
            "outputs_actions": False,
            "outputs_target_weights": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"llm_state_reward_interface_multi_ticker_smoke_{stamp}.json"


def write_review(review: dict[str, Any], output_path: Path, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, review.get("as_of")).write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default="2026-07-20")
    parser.add_argument("--validation", default=str(DEFAULT_VALIDATION))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--ticker", action="append", default=[], help="Ticker to include; default uses ETF universe.")
    parser.add_argument("--start", default="2016-01-01")
    parser.add_argument("--min-rows", type=int, default=240)
    parser.add_argument("--min-end-date", default="2026-07-17")
    parser.add_argument("--proposal-id", default=ACCEPTED_PROPOSAL_ID)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        validation_path=_resolve(args.validation),
        db_path=_resolve(args.db),
        tickers=args.ticker or None,
        start=args.start,
        min_rows=args.min_rows,
        min_end_date=args.min_end_date,
        proposal_id=args.proposal_id,
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward multi-ticker smoke review: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "ticker_count": review["summary"]["ticker_count"],
                "available": review["summary"]["available_for_manual_offline_review_count"],
                "blocked_tickers": review["summary"]["blocked_tickers"],
                "earliest_end": review["summary"]["earliest_end"],
                "promote_to_live": review["decision"]["promote_to_live"],
                "allow_00631l_add": review["decision"]["allow_00631l_add"],
                "allow_00632r_open": review["decision"]["allow_00632r_open"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
