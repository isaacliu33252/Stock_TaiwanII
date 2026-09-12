#!/usr/bin/env python3
"""Build a research-only market-aligned sentiment shadow snapshot.

Motivated by arXiv:2607.28127 ("FinSMART", Iacovides et al. 2026-07-30) --
see research/shadow/FINSMART_LITE_MARKET_ALIGNED_SENTIMENT_SHADOW_DESIGN_20260806.md
for the full design rationale. This does NOT train or query any LLM at test
time (the project's llm_state_reward_interface_readiness_review forbids that
outright); it reuses the existing deterministic keyword-proxy scorer
(score_text_finbert_proxy) and asks only whether today's price move for each
held ticker is directionally consistent with today's ticker-tagged news
sentiment, beyond an economically-meaningful move threshold. There is no
next-day prediction field: the 2026-08-05 diagnostic found next-day
alignment indistinguishable from zero under both directional and volatility
readings, so this snapshot is deliberately framed as a same-day, post-hoc
"was this move news-explained" diagnostic rather than a forecast.

research_only: true. production_effect: none. Never wired into
daily_signal.py or any target-weight computation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from build_finbert_sentiment_features import score_text_finbert_proxy  # noqa: E402

DEFAULT_FINMIND_PATHS = [
    PROJECT_ROOT / "news" / "finmind_stock_news_merged_full.jsonl",
    PROJECT_ROOT / "news" / "finmind_stock_news_rolling.jsonl",
    # 2330 added to the watchlist 2026-08-06; backfill only reaches
    # 2025-11-26 before hitting the FinMind API quota (HTTP 402) -- see
    # research/shadow/FINSMART_LITE_MARKET_ALIGNED_SENTIMENT_SHADOW_DESIGN_20260806.md.
    # 2025-11-27 through today is a known gap until the quota resets and the
    # remainder is backfilled; not covered by finmind_stock_news_rolling.jsonl
    # either (that rolling file predates 2330 being on the watchlist).
    PROJECT_ROOT / "news" / "finmind_stock_news_2330_2025H1_to_2026H2.jsonl",
]
DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "market_aligned_sentiment_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report" / "group_a_plus" / "market_aligned_sentiment_shadow" / "history"
DEFAULT_TICKERS = ["0050", "00631L", "00632R", "00679B", "2330"]
ALPHA_THRESHOLD = 0.005
ROLLING_WINDOW = 63
# 00679B trades on TPEx (OTC), not TWSE -- ohlcv stores it as "00679B.TWO", the
# other three as "<ticker>.TW". Getting this wrong silently drops all price
# data for whichever ticker doesn't match (found during manual verification).
TICKER_EXCHANGE_SUFFIX = {"00679B": ".TWO"}
DEFAULT_EXCHANGE_SUFFIX = ".TW"
# 2330's own OHLCV lives in external_market_ohlcv (yfinance-sourced), not the
# main ohlcv table -- confirmed during the 2608.03703 LETF-paper review
# (research/shadow/LETF_CLOSE_AUCTION_OVERSHOOT_REVERSAL_TEST_20260805.md).
# Querying the main table for 2330 silently returns zero rows, not an error.
PRICE_TABLE_OVERRIDE = {"2330": "external_market_ohlcv"}
DEFAULT_PRICE_TABLE = "ohlcv"


def _full_ticker(ticker: str) -> str:
    return f"{ticker}{TICKER_EXCHANGE_SUFFIX.get(ticker, DEFAULT_EXCHANGE_SUFFIX)}"


def _price_table(ticker: str) -> str:
    return PRICE_TABLE_OVERRIDE.get(ticker, DEFAULT_PRICE_TABLE)

NEXT_DAY_PREDICTION_NOTE = (
    "intentionally null -- 2026-08-05 diagnostic "
    "(research/shadow/FINSMART_REWARD_ALIGNMENT_DIAGNOSTIC_20260805.md) found next-day "
    "correlation indistinguishable from zero under both directional and volatility "
    "interpretations; do not add a directional next-day field without re-running that "
    "diagnostic first"
)


def load_finmind_records(paths: Path | list[Path], tickers: list[str]) -> list[dict[str, Any]]:
    """Load and union records from one or more FinMind JSONL files.

    finmind_stock_news_merged_full.jsonl is itself a periodically-refreshed
    merge that can lag behind finmind_stock_news_rolling.jsonl by weeks (seen
    2026-08-06: merged_full stops 2026-06-30, rolling covers 2026-07-27 to
    2026-08-05) -- read both and let dedupe_headlines() collapse any overlap.
    """
    path_list = [paths] if isinstance(paths, Path) else paths
    ticker_set = set(tickers)
    records = []
    for path in path_list:
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                if rec.get("finmind_stock_id") in ticker_set:
                    records.append(rec)
    return records


def dedupe_headlines(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop same-day, same-ticker re-syndications of the same story.

    FinMind aggregates multiple outlets (Yahoo/FTNN/etc.) that frequently
    re-publish an identical headline verbatim except for a trailing
    " - <source>" suffix. Keeping every copy inflates the daily mean toward
    whatever stories happened to be re-syndicated the most, rather than
    reflecting genuinely distinct coverage. Dedup key: (date, ticker, headline
    text before the last " - " separator).
    """
    seen: set[tuple[str, str, str]] = set()
    deduped = []
    for rec in records:
        title = rec.get("title", "")
        core = title.rsplit(" - ", 1)[0].strip()
        key = (rec.get("date", ""), rec.get("finmind_stock_id", ""), core)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(rec)
    return deduped


def score_daily_sentiment(records: list[dict[str, Any]]) -> pd.DataFrame:
    """Return a (date, ticker) -> (sentiment_score, news_intensity) panel."""
    rows = []
    for rec in records:
        score = score_text_finbert_proxy(rec.get("title", ""))["finbert_sentiment_score"]
        rows.append(
            {
                "date": rec["date"],
                "ticker": rec["finmind_stock_id"],
                "score": score,
            }
        )
    if not rows:
        return pd.DataFrame(columns=["date", "ticker", "sentiment_score", "news_intensity"])
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    grouped = df.groupby(["date", "ticker"])["score"].agg(["mean", "count"]).reset_index()
    grouped = grouped.rename(columns={"mean": "sentiment_score", "count": "news_intensity"})
    return grouped


def move_explained_by_news(sentiment_score: float, same_day_return: float, alpha_threshold: float) -> bool | None:
    """Same day, same direction, and the move clears an economically-meaningful threshold.

    A sentiment_score of exactly 0.0 means no keyword hit either way (the
    common case for a generic/no-signal headline -- score_text_finbert_proxy
    returns exactly 0.0 when positive_hits == negative_hits == 0, not
    near-zero noise). That carries no directional information, so it must
    not be silently treated as "positive < 0" -- the naive
    `(sentiment_score > 0) == (same_day_return > 0)` comparison did exactly
    that, making a neutral score agree with every down day and disagree with
    every up day (an asymmetric bug, not just imprecision).
    """
    if pd.isna(sentiment_score) or pd.isna(same_day_return):
        return None
    if abs(same_day_return) < alpha_threshold:
        return None
    if sentiment_score == 0:
        return None
    same_direction = (sentiment_score > 0) == (same_day_return > 0)
    return bool(same_direction)


def rolling_alpha_corr(sentiment: pd.Series, returns: pd.Series, window: int) -> float | None:
    df = pd.concat([sentiment.rename("s"), returns.rename("r")], axis=1).dropna().tail(window)
    if len(df) < max(20, window // 3):
        return None
    corr = df["s"].corr(df["r"])
    return float(corr) if pd.notna(corr) else None


def _load_price_returns(db_path: Path, ticker: str) -> pd.Series:
    table = _price_table(ticker)  # fixed internal literal, never user/CLI-controlled -- safe to interpolate
    con = duckdb.connect(str(db_path), read_only=True)
    df = con.execute(f"SELECT dt, close FROM {table} WHERE ticker = ? ORDER BY dt", [_full_ticker(ticker)]).fetchdf()
    con.close()
    df["dt"] = pd.to_datetime(df["dt"])
    return df.set_index("dt")["close"].pct_change().rename("ret")


def build_market_aligned_sentiment_shadow(
    *,
    sentiment_panel: pd.DataFrame,
    price_returns: dict[str, pd.Series],
    tickers: list[str],
    as_of: pd.Timestamp,
    alpha_threshold: float = ALPHA_THRESHOLD,
    rolling_window: int = ROLLING_WINDOW,
) -> dict[str, Any]:
    per_ticker: dict[str, Any] = {}
    for ticker in tickers:
        ret_series = price_returns.get(ticker, pd.Series(dtype=float))
        tk_sentiment = sentiment_panel[sentiment_panel["ticker"] == ticker].set_index("date")
        sentiment_series = tk_sentiment["sentiment_score"] if not tk_sentiment.empty else pd.Series(dtype=float)
        intensity_series = tk_sentiment["news_intensity"] if not tk_sentiment.empty else pd.Series(dtype=float)

        same_day_score = float(sentiment_series.get(as_of, float("nan"))) if not sentiment_series.empty else float("nan")
        same_day_intensity = int(intensity_series.get(as_of, 0)) if not intensity_series.empty else 0
        same_day_return = float(ret_series.get(as_of, float("nan")))

        corr = rolling_alpha_corr(sentiment_series, ret_series, rolling_window)

        per_ticker[_full_ticker(ticker)] = {
            "same_day_sentiment_score": None if pd.isna(same_day_score) else round(same_day_score, 6),
            "same_day_news_intensity": same_day_intensity,
            "same_day_return": None if pd.isna(same_day_return) else round(same_day_return, 6),
            "move_explained_by_news": move_explained_by_news(same_day_score, same_day_return, alpha_threshold),
            f"rolling_{rolling_window}d_sentiment_return_corr": None if corr is None else round(corr, 4),
        }

    return {
        "schema_version": 1,
        "status": "available",
        "research_only": True,
        "production_effect": "none",
        "date": str(as_of.date()),
        "alpha_threshold": alpha_threshold,
        "rolling_window_days": rolling_window,
        "per_ticker": per_ticker,
        "next_day_prediction": None,
        "next_day_prediction_note": NEXT_DAY_PREDICTION_NOTE,
    }


def run_and_write(
    *,
    finmind_paths: list[Path] | None = None,
    db_path: Path | None = None,
    tickers: list[str] | None = None,
    as_of: str | None = None,
    alpha_threshold: float = ALPHA_THRESHOLD,
    rolling_window: int = ROLLING_WINDOW,
    output_path: Path | None = None,
    history_dir: Path | None = None,
) -> dict[str, Any]:
    """Load, score, build, and write the shadow snapshot in one call --
    the shared entry point for both the CLI (main()) and
    run_ncf_daily_pipeline.py's best-effort pipeline step.

    as_of, when given, is used verbatim even if no news exists for that date
    (fields correctly come back null rather than falling back to the latest
    available date) -- matching this codebase's anti-staleness-masking
    convention (see run_ncf_daily_pipeline.py's crash_alert `as_of` check):
    a caller asking for "today" must not silently receive an older day's
    sentiment mislabeled as today's.
    """
    finmind_paths = finmind_paths or DEFAULT_FINMIND_PATHS
    db_path = db_path or DB_PATH
    tickers = tickers or DEFAULT_TICKERS
    output_path = output_path or DEFAULT_OUTPUT
    history_dir = history_dir or DEFAULT_HISTORY_DIR

    records = load_finmind_records(finmind_paths, tickers)
    deduped = dedupe_headlines(records)
    sentiment_panel = score_daily_sentiment(deduped)

    price_returns = {ticker: _load_price_returns(db_path, ticker) for ticker in tickers}

    if as_of:
        as_of_ts = pd.Timestamp(as_of)
    else:
        as_of_ts = sentiment_panel["date"].max() if not sentiment_panel.empty else pd.Timestamp.today().normalize()

    payload = build_market_aligned_sentiment_shadow(
        sentiment_panel=sentiment_panel,
        price_returns=price_returns,
        tickers=tickers,
        as_of=as_of_ts,
        alpha_threshold=alpha_threshold,
        rolling_window=rolling_window,
    )
    payload["raw_headline_count"] = len(records)
    payload["deduped_headline_count"] = len(deduped)
    payload["dropped_duplicate_count"] = len(records) - len(deduped)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    history_dir.mkdir(parents=True, exist_ok=True)
    history_path = history_dir / f"{as_of_ts.date()}.json"
    history_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--finmind-path",
        nargs="+",
        default=[str(p) for p in DEFAULT_FINMIND_PATHS],
    )
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS)
    parser.add_argument("--as-of", default=None, help="YYYY-MM-DD; defaults to the latest date with news data.")
    parser.add_argument("--alpha-threshold", type=float, default=ALPHA_THRESHOLD)
    parser.add_argument("--rolling-window", type=int, default=ROLLING_WINDOW)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    args = parser.parse_args()

    payload = run_and_write(
        finmind_paths=[Path(p) for p in args.finmind_path],
        db_path=Path(args.db),
        tickers=args.tickers,
        as_of=args.as_of,
        alpha_threshold=args.alpha_threshold,
        rolling_window=args.rolling_window,
        output_path=Path(args.output),
        history_dir=Path(args.history_dir),
    )

    print(f"date={payload['date']} dropped_duplicates={payload['dropped_duplicate_count']}/{payload['raw_headline_count']}")
    print(f"Output: {args.output}")
    print(f"History: {Path(args.history_dir) / (payload['date'] + '.json')}")


if __name__ == "__main__":
    main()
