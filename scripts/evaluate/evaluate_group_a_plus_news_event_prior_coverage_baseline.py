#!/usr/bin/env python3
"""Evaluate news event-prior buckets against a coverage-only baseline.

Research-only follow-up to arXiv:2608.14014. The question is whether the
deterministic GroupA+ event buckets carry information beyond "this ticker was
covered by news at all." This report is intentionally diagnostic and must not
drive target weights.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from group_a_plus.integrations.news_event_prior_shadow import classify_article  # noqa: E402

DEFAULT_NEWS_GLOB = "news/finmind_stock_news_*.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "news_event_prior_coverage_baseline_review.json"
DEFAULT_MD = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "news_event_prior_coverage_baseline_review.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report" / "group_a_plus" / "news_event_prior_coverage_baseline_review" / "history"
DEFAULT_TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO", "2330.TW")
HORIZONS = (1, 5, 20)
PRICE_TABLE_OVERRIDE = {"2330.TW": "external_market_ohlcv"}


def _parse_date(value: Any) -> pd.Timestamp | None:
    try:
        return pd.Timestamp(str(value)[:10]).normalize()
    except Exception:
        return None


def _iter_news_rows(news_glob: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for path in sorted(PROJECT_ROOT.glob(news_glob)):
        with path.open(encoding="utf-8-sig") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                date = str(row.get("date") or "")[:10]
                symbol = str(row.get("match_scope") or "")
                title = str(row.get("title") or "").rsplit(" - ", 1)[0].strip()
                key = (date, symbol, title)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(row)
    return rows


def _load_prices(db_path: Path, ticker: str) -> pd.Series:
    table = PRICE_TABLE_OVERRIDE.get(ticker, "ohlcv")
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        df = con.execute(f"SELECT dt, close FROM {table} WHERE ticker = ? ORDER BY dt", [ticker]).fetchdf()
    finally:
        con.close()
    if df.empty:
        return pd.Series(dtype=float)
    df["dt"] = pd.to_datetime(df["dt"]).dt.normalize()
    return df.set_index("dt")["close"].astype(float)


def _event_panel(rows: list[dict[str, Any]], tickers: tuple[str, ...]) -> pd.DataFrame:
    ticker_set = set(tickers)
    events: dict[tuple[pd.Timestamp, str], dict[str, Any]] = {}
    for row in rows:
        dt = _parse_date(row.get("date"))
        ticker = str(row.get("match_scope") or "")
        if dt is None or ticker not in ticker_set:
            continue
        article = {
            "date": str(dt.date()),
            "source": row.get("source"),
            "title": row.get("title"),
            "url": row.get("url"),
            "category": row.get("category"),
            "snippet": row.get("snippet") or "",
            "match_scope": ticker,
        }
        classified = classify_article(article)
        key = (dt, ticker)
        event = events.setdefault(
            key,
            {
                "date": dt,
                "ticker": ticker,
                "article_count": 0,
                "bucket_counts": defaultdict(int),
                "width_prior_counts": defaultdict(int),
                "direction_prior_counts": defaultdict(int),
            },
        )
        event["article_count"] += 1
        event["bucket_counts"][classified["event_bucket"]] += 1
        event["width_prior_counts"][classified["width_prior"]] += 1
        event["direction_prior_counts"][classified["direction_prior"]] += 1

    out = []
    for event in events.values():
        bucket_counts = dict(event["bucket_counts"])
        dominant_bucket = max(bucket_counts.items(), key=lambda item: item[1])[0] if bucket_counts else "unknown"
        out.append(
            {
                "date": event["date"],
                "ticker": event["ticker"],
                "article_count": int(event["article_count"]),
                "dominant_event_bucket": dominant_bucket,
                "bucket_counts": bucket_counts,
                "width_prior_counts": dict(event["width_prior_counts"]),
                "direction_prior_counts": dict(event["direction_prior_counts"]),
            }
        )
    return pd.DataFrame(out)


def _attach_forward_returns(events: pd.DataFrame, prices: dict[str, pd.Series]) -> pd.DataFrame:
    rows = []
    for row in events.to_dict("records"):
        ticker = row["ticker"]
        close = prices.get(ticker, pd.Series(dtype=float)).dropna()
        if close.empty or row["date"] not in close.index:
            continue
        loc = close.index.get_loc(row["date"])
        if not isinstance(loc, int):
            continue
        enriched = dict(row)
        for h in HORIZONS:
            if loc + h < len(close):
                ret = float(close.iloc[loc + h] / close.iloc[loc] - 1.0)
                enriched[f"ret_fwd_{h}d"] = ret
                enriched[f"abs_ret_fwd_{h}d"] = abs(ret)
            else:
                enriched[f"ret_fwd_{h}d"] = None
                enriched[f"abs_ret_fwd_{h}d"] = None
        rows.append(enriched)
    return pd.DataFrame(rows)


def _quiet_day_panel(
    prices: dict[str, pd.Series],
    events: pd.DataFrame,
    *,
    lookback_event_free_days: int = 5,
) -> pd.DataFrame:
    event_dates = {
        ticker: set(pd.to_datetime(g["date"]).dt.normalize())
        for ticker, g in events.groupby("ticker")
    } if not events.empty else {}
    rows: list[dict[str, Any]] = []
    for ticker, close in prices.items():
        close = close.dropna()
        if close.empty:
            continue
        ticker_events = event_dates.get(ticker, set())
        for i, dt in enumerate(close.index):
            if dt in ticker_events:
                continue
            recent = close.index[max(0, i - lookback_event_free_days) : i + 1]
            if any(day in ticker_events for day in recent):
                continue
            row: dict[str, Any] = {
                "date": dt,
                "ticker": ticker,
                "quiet_baseline": "quiet_no_recent_news",
            }
            for h in HORIZONS:
                if i + h < len(close):
                    ret = float(close.iloc[i + h] / close.iloc[i] - 1.0)
                    row[f"ret_fwd_{h}d"] = ret
                    row[f"abs_ret_fwd_{h}d"] = abs(ret)
                else:
                    row[f"ret_fwd_{h}d"] = None
                    row[f"abs_ret_fwd_{h}d"] = None
            rows.append(row)
    return pd.DataFrame(rows)


def _summary(frame: pd.DataFrame, group_col: str, min_events: int) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if frame.empty:
        return out
    for group, g in frame.groupby(group_col):
        item: dict[str, Any] = {"n_event_days": int(len(g))}
        for h in HORIZONS:
            ret = pd.to_numeric(g.get(f"ret_fwd_{h}d"), errors="coerce").dropna()
            abs_ret = pd.to_numeric(g.get(f"abs_ret_fwd_{h}d"), errors="coerce").dropna()
            if len(ret) < min_events:
                item[f"h{h}"] = {"status": "insufficient_data", "n": int(len(ret))}
                continue
            se = float(ret.std(ddof=1) / math.sqrt(len(ret))) if len(ret) > 1 else float("nan")
            item[f"h{h}"] = {
                "status": "ok",
                "n": int(len(ret)),
                "mean_return": float(ret.mean()),
                "median_return": float(ret.median()),
                "positive_rate": float((ret > 0).mean()),
                "mean_abs_return": float(abs_ret.mean()) if not abs_ret.empty else None,
                "t_stat_mean_return": float(ret.mean() / se) if se and np.isfinite(se) and se > 0 else None,
            }
        out[str(group)] = item
    return out


def _quiet_means(quiet_summary: dict[str, Any]) -> dict[int, dict[str, float | None]]:
    item = quiet_summary.get("quiet_no_recent_news") or {}
    out: dict[int, dict[str, float | None]] = {}
    for h in HORIZONS:
        cell = item.get(f"h{h}") or {}
        out[h] = {
            "mean_return": cell.get("mean_return"),
            "mean_abs_return": cell.get("mean_abs_return"),
        }
    return out


def _add_excess_vs_quiet(summary: dict[str, Any], quiet: dict[int, dict[str, float | None]]) -> dict[str, Any]:
    out = json.loads(json.dumps(summary))
    for item in out.values():
        for h in HORIZONS:
            cell = item.get(f"h{h}") or {}
            if cell.get("status") != "ok":
                continue
            q = quiet.get(h) or {}
            q_ret = q.get("mean_return")
            q_abs = q.get("mean_abs_return")
            cell["excess_mean_return_vs_quiet"] = (
                float(cell["mean_return"] - q_ret) if q_ret is not None and cell.get("mean_return") is not None else None
            )
            cell["excess_mean_abs_return_vs_quiet"] = (
                float(cell["mean_abs_return"] - q_abs)
                if q_abs is not None and cell.get("mean_abs_return") is not None
                else None
            )
    return out


def _baseline_means(summary: dict[str, Any], group: str) -> dict[int, dict[str, float | None]]:
    item = summary.get(group) or {}
    out: dict[int, dict[str, float | None]] = {}
    for h in HORIZONS:
        cell = item.get(f"h{h}") or {}
        out[h] = {
            "mean_return": cell.get("mean_return"),
            "mean_abs_return": cell.get("mean_abs_return"),
        }
    return out


def _add_excess_vs_coverage(summary: dict[str, Any], coverage: dict[int, dict[str, float | None]]) -> dict[str, Any]:
    out = json.loads(json.dumps(summary))
    for item in out.values():
        for h in HORIZONS:
            cell = item.get(f"h{h}") or {}
            if cell.get("status") != "ok":
                continue
            base = coverage.get(h) or {}
            base_ret = base.get("mean_return")
            base_abs = base.get("mean_abs_return")
            cell["excess_mean_return_vs_coverage"] = (
                float(cell["mean_return"] - base_ret)
                if base_ret is not None and cell.get("mean_return") is not None
                else None
            )
            cell["excess_mean_abs_return_vs_coverage"] = (
                float(cell["mean_abs_return"] - base_abs)
                if base_abs is not None and cell.get("mean_abs_return") is not None
                else None
            )
    return out


def build_review(
    *,
    news_glob: str = DEFAULT_NEWS_GLOB,
    db_path: Path = DB_PATH,
    tickers: tuple[str, ...] = DEFAULT_TICKERS,
    min_events: int = 20,
) -> dict[str, Any]:
    rows = _iter_news_rows(news_glob)
    events = _event_panel(rows, tickers)
    prices = {ticker: _load_prices(db_path, ticker) for ticker in tickers}
    event_returns = _attach_forward_returns(events, prices) if not events.empty else pd.DataFrame()
    quiet_days = _quiet_day_panel(prices, events)
    coverage = {
        "raw_news_rows": int(len(rows)),
        "event_days": int(len(events)),
        "event_days_with_returns": int(len(event_returns)),
        "quiet_days_with_returns": int(len(quiet_days)),
        "tickers": list(tickers),
        "date_min": str(event_returns["date"].min().date()) if not event_returns.empty else None,
        "date_max": str(event_returns["date"].max().date()) if not event_returns.empty else None,
        "min_events_required_per_cell": int(min_events),
    }
    quiet_baseline = _summary(quiet_days, "quiet_baseline", min_events)
    quiet = _quiet_means(quiet_baseline)
    coverage_baseline = _add_excess_vs_quiet(
        _summary(event_returns.assign(coverage_baseline="all_covered"), "coverage_baseline", min_events),
        quiet,
    )
    coverage_means = _baseline_means(coverage_baseline, "all_covered")
    by_bucket = _add_excess_vs_coverage(
        _add_excess_vs_quiet(_summary(event_returns, "dominant_event_bucket", min_events), quiet),
        coverage_means,
    )
    by_ticker = _add_excess_vs_coverage(
        _add_excess_vs_quiet(_summary(event_returns, "ticker", min_events), quiet),
        coverage_means,
    )
    blockers = []
    if coverage["event_days_with_returns"] < min_events * 3:
        blockers.append("insufficient_total_event_days_for_reliable_bucket_study")
    usable_bucket_count = sum(
        1 for item in by_bucket.values() if any((item.get(f"h{h}") or {}).get("status") == "ok" for h in HORIZONS)
    )
    if usable_bucket_count < 2:
        blockers.append("insufficient_bucket_diversity_with_min_events")
    unknown_days = int((by_bucket.get("unknown") or {}).get("n_event_days") or 0)
    unknown_share = unknown_days / coverage["event_days_with_returns"] if coverage["event_days_with_returns"] else 1.0
    if unknown_share > 0.50:
        blockers.append("event_taxonomy_unknown_share_above_50pct")
    material_bucket_edges = []
    for bucket, item in by_bucket.items():
        if bucket == "unknown":
            continue
        h5 = item.get("h5") or {}
        h20 = item.get("h20") or {}
        h5_edge = h5.get("excess_mean_return_vs_coverage")
        h20_edge = h20.get("excess_mean_return_vs_coverage")
        if h5.get("status") == "ok" and h20.get("status") == "ok" and h5_edge is not None and h20_edge is not None:
            if h5_edge >= 0.005 and h20_edge >= 0.005:
                material_bucket_edges.append(bucket)
    if not material_bucket_edges:
        blockers.append("no_event_bucket_materially_beats_coverage_baseline")
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_news_event_prior_coverage_baseline_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "research_source": "arXiv:2608.14014 news priced-in event-study review",
        "policy": "research_only_no_target_weight_change",
        "target_weight_change_allowed": False,
        "direction_trade_allowed": False,
        "news_glob": news_glob,
        "coverage": coverage,
        "quiet_baseline": quiet_baseline,
        "coverage_baseline": coverage_baseline,
        "by_event_bucket": by_bucket,
        "by_ticker": by_ticker,
        "taxonomy_quality": {
            "unknown_event_days": unknown_days,
            "unknown_share_of_event_days_with_returns": float(unknown_share),
            "usable_bucket_count": int(usable_bucket_count),
            "material_bucket_edges_vs_coverage": material_bucket_edges,
        },
        "decision": "do_not_promote_keep_shadow",
        "blockers": blockers,
        "interpretation": (
            "This report only checks whether coarse event buckets differ from coverage-only days. "
            "No news direction or event prior may affect target weights without a larger Taiwan-specific event study."
        ),
    }


def _history_path(history_dir: Path, report: dict[str, Any]) -> Path:
    date_max = ((report.get("coverage") or {}).get("date_max") or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"news_event_prior_coverage_baseline_review_{date_max}.json"


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# News Event Prior Coverage Baseline Review",
        "",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Decision: `{report.get('decision')}`",
        f"- Policy: `{report.get('policy')}`",
        f"- Target weight change allowed: `{report.get('target_weight_change_allowed')}`",
        "",
        "## Coverage",
        "",
    ]
    cov = report.get("coverage") or {}
    for key in ("raw_news_rows", "event_days", "event_days_with_returns", "date_min", "date_max", "min_events_required_per_cell"):
        lines.append(f"- {key}: `{cov.get(key)}`")
    lines.append(f"- quiet_days_with_returns: `{cov.get('quiet_days_with_returns')}`")
    lines.extend(["", "## Quiet Baseline", ""])
    quiet = ((report.get("quiet_baseline") or {}).get("quiet_no_recent_news") or {})
    for h in HORIZONS:
        cell = quiet.get(f"h{h}") or {}
        lines.append(
            "- H{h}: status=`{status}`, n=`{n}`, mean_return=`{mean}`, mean_abs_return=`{absret}`".format(
                h=h,
                status=cell.get("status"),
                n=cell.get("n"),
                mean=cell.get("mean_return"),
                absret=cell.get("mean_abs_return"),
            )
        )
    lines.extend(["", "## Blockers", ""])
    blockers = report.get("blockers") or []
    if blockers:
        lines.extend(f"- `{blocker}`" for blocker in blockers)
    else:
        lines.append("- none")
    lines.extend(["", "## Event Buckets", ""])
    for bucket, item in (report.get("by_event_bucket") or {}).items():
        lines.append(f"### {bucket}")
        lines.append(f"- event days: `{item.get('n_event_days')}`")
        for h in HORIZONS:
            cell = item.get(f"h{h}") or {}
            lines.append(
                "- H{h}: status=`{status}`, n=`{n}`, mean_return=`{mean}`, excess_return_vs_quiet=`{excess}`, "
                "excess_return_vs_coverage=`{excess_cov}`, mean_abs_return=`{absret}`, "
                "excess_abs_vs_quiet=`{excess_abs}`, excess_abs_vs_coverage=`{excess_abs_cov}`".format(
                    h=h,
                    status=cell.get("status"),
                    n=cell.get("n"),
                    mean=cell.get("mean_return"),
                    excess=cell.get("excess_mean_return_vs_quiet"),
                    excess_cov=cell.get("excess_mean_return_vs_coverage"),
                    absret=cell.get("mean_abs_return"),
                    excess_abs=cell.get("excess_mean_abs_return_vs_quiet"),
                    excess_abs_cov=cell.get("excess_mean_abs_return_vs_coverage"),
                )
            )
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--news-glob", default=DEFAULT_NEWS_GLOB)
    parser.add_argument("--min-events", type=int, default=20)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    report = build_review(news_glob=args.news_glob, min_events=args.min_events)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _write_markdown(report, Path(args.markdown))
    if not args.no_history:
        history_dir = Path(args.history_dir)
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, report).write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    cov = report["coverage"]
    print(
        f"event_days={cov['event_days_with_returns']} date_range={cov['date_min']}..{cov['date_max']} "
        f"decision={report['decision']} blockers={len(report['blockers'])}"
    )
    print(f"Output: {output}")
    print(f"Markdown: {args.markdown}")


if __name__ == "__main__":
    main()
