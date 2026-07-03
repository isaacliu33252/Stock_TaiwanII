#!/usr/bin/env python3
"""Event sentiment attribution shadow report for Group A+.

This imports the useful idea from event-driven sentiment research: do not trust
news sentiment until it is attributed against forward returns.  The report
joins watchlist news, per-article sentiment proxies, and DuckDB OHLCV forward
returns at 1D/5D/20D horizons.  It is research-only and does not change live
allocation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from backtest_group_a_plus_policy_signal import TICKERS
from backtest_group_a_plus_switch_policy import DB_PATH
from build_finbert_sentiment_features import score_text_finbert_proxy
from group_a_plus.integrations.finbert import load_finbert_daily_snapshot
from group_a_plus.integrations.lm_dictionary_sentiment import (
    load_dictionaries,
    resolve_dictionary_dir,
    score_texts,
)
from group_a_plus.paths import PROJECT_ROOT
from tw_output_standard import OutputStandardizer, write_standard_output


DEFAULT_WATCHLIST_NEWS = PROJECT_ROOT / "report/group_a_plus/latest/watchlist_news.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "results/event_sentiment_attribution_shadow_latest_20260701.json"
DEFAULT_BENCHMARK = "0050.TW"
DEFAULT_HORIZONS = (1, 5, 20)


def _parse_horizons(value: str) -> tuple[int, ...]:
    horizons = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    if not horizons or any(h <= 0 for h in horizons):
        raise ValueError("horizons must be positive integers")
    return horizons


def _parse_date(value: Any) -> pd.Timestamp | None:
    if not isinstance(value, str) or not value.strip():
        return None
    parsed = pd.to_datetime(value[:10], errors="coerce")
    if pd.isna(parsed):
        return None
    return pd.Timestamp(parsed).normalize()


def _normalise_text(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value).strip().lower())
    text = re.sub(r"https?://\S+", "", text)
    return text


def article_content_hash(article: dict[str, Any]) -> str:
    blob = " ".join(str(article.get(key) or "") for key in ("title", "snippet"))
    return hashlib.sha1(_normalise_text(blob).encode("utf-8")).hexdigest()[:16]


def load_watchlist_articles(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    articles = [dict(article) for article in payload.get("articles", []) if isinstance(article, dict)]
    return payload, articles


def load_close_prices(
    db_path: Path,
    tickers: list[str],
    *,
    start: str,
    end: str,
) -> pd.DataFrame:
    placeholders = ", ".join(["?"] * len(tickers))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            f"""
            SELECT dt, ticker, close
            FROM ohlcv
            WHERE ticker IN ({placeholders}) AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [*tickers, start, end],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        raise RuntimeError(f"No OHLCV rows for {tickers} between {start} and {end}")
    rows["dt"] = pd.to_datetime(rows["dt"])
    prices = rows.pivot(index="dt", columns="ticker", values="close").sort_index()
    return prices.astype(float)


def _resolve_article_symbol(article: dict[str, Any], default_symbol: str) -> str:
    scope = str(article.get("match_scope") or "")
    if scope in TICKERS:
        return scope
    return default_symbol


def _forward_return(
    prices: pd.DataFrame,
    *,
    symbol: str,
    event_date: pd.Timestamp,
    horizon: int,
) -> dict[str, Any]:
    if symbol not in prices.columns:
        return {"status": "unavailable", "reason": "missing_symbol"}
    loc = prices.index.searchsorted(event_date)
    if loc >= len(prices.index):
        return {"status": "unavailable", "reason": "event_after_price_window"}
    base = prices.iloc[loc][symbol]
    target_loc = loc + horizon
    if target_loc >= len(prices.index):
        return {
            "status": "immature",
            "event_trade_date": str(prices.index[loc].date()),
            "available_rows_after_event": int(len(prices.index) - loc - 1),
        }
    target = prices.iloc[target_loc][symbol]
    if pd.isna(base) or pd.isna(target) or float(base) <= 0.0:
        return {"status": "unavailable", "reason": "missing_price"}
    return {
        "status": "ok",
        "event_trade_date": str(prices.index[loc].date()),
        "target_trade_date": str(prices.index[target_loc].date()),
        "return": float(target / base - 1.0),
    }


def _lm_article_score(text: str, dictionaries: dict[str, set[str]]) -> dict[str, Any]:
    if not dictionaries:
        return {"status": "unavailable", "risk_score": 0.0}
    score = score_texts([text], dictionaries)
    if score["token_count"] == 0:
        status = "no_english_tokens"
    elif score["positive_count"] + score["negative_count"] == 0:
        status = "no_dictionary_hits"
    else:
        status = "ok"
    return {"status": status, **score}


def build_article_attributions(
    articles: list[dict[str, Any]],
    prices: pd.DataFrame,
    *,
    benchmark: str,
    horizons: tuple[int, ...],
    default_symbol: str = DEFAULT_BENCHMARK,
    lm_dictionary_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    resolved_lm_dir = resolve_dictionary_dir(lm_dictionary_dir)
    dictionaries = load_dictionaries(resolved_lm_dir) if resolved_lm_dir else {}
    seen_hashes: set[str] = set()
    records: list[dict[str, Any]] = []
    for article in articles:
        event_date = _parse_date(article.get("date"))
        if event_date is None:
            continue
        text = " ".join(str(article.get(key) or "") for key in ("title", "snippet"))
        content_hash = article_content_hash(article)
        duplicate = content_hash in seen_hashes
        seen_hashes.add(content_hash)
        symbol = _resolve_article_symbol(article, default_symbol)
        finbert = score_text_finbert_proxy(text)
        lm = _lm_article_score(text, dictionaries)

        horizon_rows: dict[str, Any] = {}
        for horizon in horizons:
            asset = _forward_return(prices, symbol=symbol, event_date=event_date, horizon=horizon)
            bench = _forward_return(prices, symbol=benchmark, event_date=event_date, horizon=horizon)
            row = {
                "asset": asset,
                "benchmark": bench,
                "relative_return": None,
                "sentiment_direction_match": None,
            }
            if asset.get("status") == "ok" and bench.get("status") == "ok":
                relative = float(asset["return"] - bench["return"])
                sentiment_score = float(finbert["finbert_sentiment_score"])
                row["relative_return"] = relative
                row["sentiment_direction_match"] = (
                    None
                    if abs(sentiment_score) < 1e-12
                    else bool((sentiment_score > 0 and relative > 0) or (sentiment_score < 0 and relative < 0))
                )
            horizon_rows[f"h{horizon}"] = row

        records.append(
            {
                "date": str(event_date.date()),
                "symbol": symbol,
                "benchmark": benchmark,
                "source": article.get("source"),
                "title": article.get("title"),
                "url": article.get("url"),
                "match_scope": article.get("match_scope"),
                "matched_keywords": article.get("matched_keywords") or [],
                "content_hash": content_hash,
                "duplicate_content_hash": duplicate,
                "finbert_proxy": finbert,
                "lm_dictionary": lm,
                "horizons": horizon_rows,
                "active_allocation_impact": "none",
            }
        )
    return records


def aggregate_attributions(records: list[dict[str, Any]], horizons: tuple[int, ...]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "article_count": int(len(records)),
        "duplicate_content_hash_count": int(sum(1 for row in records if row.get("duplicate_content_hash"))),
        "active_allocation_impact": "none",
    }
    for horizon in horizons:
        key = f"h{horizon}"
        rows = [row["horizons"][key] for row in records if key in row.get("horizons", {})]
        matured = [row for row in rows if row.get("relative_return") is not None]
        matches = [row["sentiment_direction_match"] for row in matured if row.get("sentiment_direction_match") is not None]
        rel = np.asarray([row["relative_return"] for row in matured], dtype=float) if matured else np.asarray([])
        out[key] = {
            "matured_count": int(len(matured)),
            "immature_count": int(sum(1 for row in rows if row.get("asset", {}).get("status") == "immature")),
            "mean_relative_return": float(rel.mean()) if len(rel) else None,
            "median_relative_return": float(np.median(rel)) if len(rel) else None,
            "positive_relative_rate": float(np.mean(rel > 0.0)) if len(rel) else None,
            "sentiment_direction_match_rate": float(np.mean(matches)) if matches else None,
        }
    return out


def build_report(
    *,
    watchlist_news_path: Path,
    db_path: Path,
    start: str,
    end: str,
    benchmark: str,
    horizons: tuple[int, ...],
    default_symbol: str,
    lm_dictionary_dir: str | Path | None = None,
) -> dict[str, Any]:
    watchlist, articles = load_watchlist_articles(watchlist_news_path)
    tickers = sorted(set(TICKERS) | {benchmark, default_symbol})
    prices = load_close_prices(db_path, tickers, start=start, end=end)
    records = build_article_attributions(
        articles,
        prices,
        benchmark=benchmark,
        horizons=horizons,
        default_symbol=default_symbol,
        lm_dictionary_dir=lm_dictionary_dir,
    )
    signal_date = watchlist.get("signal_date") or end
    return {
        "schema_version": 1,
        "report_type": "event_sentiment_attribution_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": {
            "inspiration_source": (
                "C:\\Users\\isaac\\Downloads\\Sentiment-Analysis-in-Event-Driven-Stock-Price-Movement-Prediction-master"
                "\\Sentiment-Analysis-in-Event-Driven-Stock-Price-Movement-Prediction-master"
            ),
            "watchlist_news": str(watchlist_news_path),
            "watchlist_signal_date": signal_date,
            "db_path": str(db_path),
            "price_window": {
                "requested_start": start,
                "requested_end": end,
                "actual_start": str(prices.index[0].date()),
                "actual_end": str(prices.index[-1].date()),
                "price_rows": int(len(prices)),
            },
            "benchmark": benchmark,
            "horizons": list(horizons),
            "tickers": tickers,
        },
        "daily_sentiment_snapshots": {
            "finbert": load_finbert_daily_snapshot(signal_date, signal_date),
        },
        "aggregate": aggregate_attributions(records, horizons),
        "articles": records,
        "method_note": (
            "Research-only event sentiment attribution. It checks whether selected "
            "watchlist news sentiment aligns with later relative returns. This "
            "report does not affect live allocation."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watchlist-news", default=str(DEFAULT_WATCHLIST_NEWS))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-06-30")
    parser.add_argument("--benchmark", default=DEFAULT_BENCHMARK)
    parser.add_argument("--default-symbol", default=DEFAULT_BENCHMARK)
    parser.add_argument("--horizons", default="1,5,20")
    parser.add_argument("--lm-dictionary-dir", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    std = OutputStandardizer("evaluate_event_sentiment_attribution_shadow")
    try:
        report = build_report(
            watchlist_news_path=Path(args.watchlist_news),
            db_path=Path(args.db),
            start=args.start,
            end=args.end,
            benchmark=args.benchmark,
            horizons=_parse_horizons(args.horizons),
            default_symbol=args.default_symbol,
            lm_dictionary_dir=args.lm_dictionary_dir,
        )
        payload = std.success(report)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"event sentiment attribution shadow: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
