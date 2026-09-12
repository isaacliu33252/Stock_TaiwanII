#!/usr/bin/env python3
"""Build monthly asset-level sentiment panel for Group A+ HARLF shadow.

Uses existing FinMind JSONL news and the deterministic FinBERT proxy already
used by market_aligned_sentiment_shadow. Research-only; no live LLM queries and
no trading effect.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from build_finbert_sentiment_features import score_text_finbert_proxy  # noqa: E402
from scripts.evaluate.build_market_aligned_sentiment_shadow import (  # noqa: E402
    DEFAULT_FINMIND_PATHS,
    DEFAULT_TICKERS,
    dedupe_headlines,
    load_finmind_records,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "FinRL/data/sentiment/monthly_asset_sentiment_panel.csv"
DEFAULT_REPORT = PROJECT_ROOT / "report/group_a_plus/latest/monthly_asset_sentiment_panel_coverage.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/monthly_asset_sentiment_panel_coverage/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _score_records(records: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for rec in records:
        title = str(rec.get("title") or "")
        score = score_text_finbert_proxy(title)["finbert_sentiment_score"]
        rows.append(
            {
                "date": rec.get("date"),
                "ticker": rec.get("finmind_stock_id"),
                "score": score,
                "headline": title,
            }
        )
    if not rows:
        return pd.DataFrame(columns=["month", "ticker", "sentiment_score", "news_intensity", "positive_rate", "negative_rate"])
    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date", "ticker"])
    frame["month"] = frame["date"].dt.to_period("M").astype(str)
    frame["positive"] = frame["score"] > 0
    frame["negative"] = frame["score"] < 0
    grouped = (
        frame.groupby(["month", "ticker"], as_index=False)
        .agg(
            sentiment_score=("score", "mean"),
            sentiment_median=("score", "median"),
            news_intensity=("score", "count"),
            positive_rate=("positive", "mean"),
            negative_rate=("negative", "mean"),
        )
        .sort_values(["month", "ticker"])
    )
    return grouped


def build_panel(
    *,
    finmind_paths: list[Path] | None = None,
    tickers: list[str] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    finmind_paths = finmind_paths or DEFAULT_FINMIND_PATHS
    tickers = tickers or DEFAULT_TICKERS
    raw = load_finmind_records(finmind_paths, tickers)
    deduped = dedupe_headlines(raw)
    panel = _score_records(deduped)
    coverage: dict[str, Any] = {}
    if panel.empty:
        coverage = {
            "status": "blocked",
            "reason": "no_sentiment_rows",
            "raw_records": len(raw),
            "deduped_records": len(deduped),
            "tickers": tickers,
        }
    else:
        by_ticker = {}
        for ticker, group in panel.groupby("ticker"):
            by_ticker[str(ticker)] = {
                "months": int(len(group)),
                "first_month": str(group["month"].min()),
                "last_month": str(group["month"].max()),
                "total_news_intensity": int(group["news_intensity"].sum()),
                "mean_monthly_news_intensity": float(group["news_intensity"].mean()),
            }
        coverage = {
            "status": "available",
            "raw_records": int(len(raw)),
            "deduped_records": int(len(deduped)),
            "row_count": int(len(panel)),
            "tickers": tickers,
            "by_ticker": by_ticker,
            "month_start": str(panel["month"].min()),
            "month_end": str(panel["month"].max()),
        }
    return panel, coverage


def _write_report(report: dict[str, Any], output: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d")
        (history_dir / f"monthly_asset_sentiment_panel_coverage_{stamp}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS))
    parser.add_argument("--finmind-path", action="append", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = [_resolve(path) for path in args.finmind_path] if args.finmind_path else DEFAULT_FINMIND_PATHS
    tickers = [part.strip() for part in str(args.tickers).split(",") if part.strip()]
    panel, coverage = build_panel(finmind_paths=paths, tickers=tickers)
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(output, index=False)
    report = {
        "schema_version": 1,
        "report_type": "group_a_plus_monthly_asset_sentiment_panel_coverage",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_monthly_sentiment_panel_no_weight_change",
        "output_panel": str(output),
        "source_files": [str(path) for path in paths],
        **coverage,
        "decision": {
            "creates_orders": False,
            "changes_target_weights": False,
            "live_llm_queries": False,
            "ready_for_harlf_readiness_input": bool(coverage.get("status") == "available"),
        },
    }
    _write_report(report, _resolve(args.report), None if args.no_history else _resolve(args.history_dir))
    print(json.dumps({"status": report["status"], "rows": report.get("row_count"), "output": str(output)}))


if __name__ == "__main__":
    main()
