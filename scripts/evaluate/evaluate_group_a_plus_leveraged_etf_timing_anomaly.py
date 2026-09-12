#!/usr/bin/env python3
"""Evaluate leveraged ETF timing-anomaly diagnostics for GroupA+.

Research-only. This script does not modify latest strategy weights, golden1,
daily signals, execution plans, or order files.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from group_a_plus.integrations.leveraged_etf_timing_anomaly import (  # noqa: E402
    TimingAnomalyThresholds,
    rolling_timing_anomaly,
    summarize_timing_anomaly,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_leveraged_etf_timing_anomaly_2604_27287.json"
DEFAULT_CSV = PROJECT_ROOT / "results" / "group_a_plus_leveraged_etf_timing_anomaly_2604_27287.csv"
DEFAULT_MD = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "leveraged_etf_timing_anomaly_2604_27287.md"


def _resolve_end_date(db_path: Path, requested_end: str, ticker: str) -> str:
    if requested_end.lower() != "latest":
        return requested_end
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        value = con.execute("SELECT MAX(dt) FROM ohlcv WHERE ticker = ?", [ticker]).fetchone()[0]
    finally:
        con.close()
    if value is None:
        raise RuntimeError(f"No OHLCV rows for {ticker}")
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _load_close(db_path: Path, tickers: list[str], start: str, end: str) -> pd.DataFrame:
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
        raise RuntimeError("No OHLCV rows loaded")
    rows["dt"] = pd.to_datetime(rows["dt"])
    close = rows.pivot(index="dt", columns="ticker", values="close").sort_index()
    missing = [ticker for ticker in tickers if ticker not in close.columns]
    if missing:
        raise RuntimeError(f"Missing close columns: {missing}")
    return close[tickers].dropna()


def _json_default(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _build_asset_review(
    close: pd.DataFrame,
    *,
    etf: str,
    underlying: str,
    target_leverage: float,
    thresholds: TimingAnomalyThresholds,
    rolling_window: int,
) -> tuple[dict[str, Any], pd.DataFrame]:
    full = summarize_timing_anomaly(
        close[etf],
        close[underlying],
        target_leverage=target_leverage,
        thresholds=thresholds,
    )
    rolling = rolling_timing_anomaly(
        close[etf],
        close[underlying],
        target_leverage=target_leverage,
        thresholds=thresholds,
        window=rolling_window,
    )
    latest = {} if rolling.empty else rolling.iloc[-1].to_dict()
    recent_warning_count = 0
    if not rolling.empty and "warnings" in rolling:
        recent_warning_count = int(rolling.tail(20)["warnings"].map(bool).sum())
    decision = "keep_shadow_no_weight_change"
    latest_cov = latest.get("covariance_ratio_underlying_return")
    latest_has_warning = bool(latest.get("warnings"))
    if (
        full["covariance_ratio_underlying_return"] <= thresholds.negative_covariance_warning
        or (latest_cov is not None and float(latest_cov) <= thresholds.negative_covariance_warning)
        or latest_has_warning
    ):
        decision = "shadow_warning_for_manual_00631l_or_00632r_review"
    review = {
        "asset": etf,
        "underlying": underlying,
        "target_leverage": target_leverage,
        "full_sample": full,
        "latest_rolling": latest,
        "recent_20d_rolling_warning_count": recent_warning_count,
        "decision": decision,
    }
    if not rolling.empty:
        rolling = rolling.copy()
        rolling.insert(0, "asset", etf)
    return review, rolling


def build_report(args: argparse.Namespace) -> tuple[dict[str, Any], pd.DataFrame]:
    db_path = Path(args.db)
    end = _resolve_end_date(db_path, args.end, "0050.TW")
    assets = {"00631L.TW": 2.0, "00632R.TW": -1.0}
    close = _load_close(db_path, ["0050.TW", *assets.keys()], args.start, end)
    thresholds = TimingAnomalyThresholds(
        min_abs_underlying_return=float(args.min_abs_underlying_return),
        ratio_winsor_quantile=float(args.ratio_winsor_quantile),
        negative_covariance_warning=float(args.negative_covariance_warning),
        tracking_error_warning=float(args.tracking_error_warning),
        volatility_drag_warning=float(args.volatility_drag_warning),
    )
    reviews = {}
    rolling_frames = []
    for etf, leverage in assets.items():
        review, rolling = _build_asset_review(
            close,
            etf=etf,
            underlying="0050.TW",
            target_leverage=leverage,
            thresholds=thresholds,
            rolling_window=int(args.rolling_window),
        )
        reviews[etf] = review
        if not rolling.empty:
            rolling_frames.append(rolling)
    rolling_out = pd.concat(rolling_frames).reset_index() if rolling_frames else pd.DataFrame()
    if not rolling_out.empty:
        rolling_out["date"] = pd.to_datetime(rolling_out["date"]).dt.strftime("%Y-%m-%d")

    any_live_ready = False
    report = {
        "schema_version": 1,
        "report_type": "group_a_plus_leveraged_etf_timing_anomaly",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "research_source": "arXiv:2604.27287v1 A Levered ETF Anomaly Explained",
        "source_pdf": "/mnt/c/Users/isaac/Downloads/2604.27287v1.pdf",
        "policy": "research_only_no_weight_change",
        "decision": "do_not_promote_keep_shadow",
        "changes_latest_strategy": False,
        "changes_golden1_0531": False,
        "window": {
            "start": str(close.index.min().date()),
            "end": str(close.index.max().date()),
            "rows": int(len(close)),
            "rolling_window": int(args.rolling_window),
        },
        "thresholds": thresholds.__dict__,
        "asset_reviews": reviews,
        "promotion_gate": {
            "eligible_for_live_strategy": any_live_ready,
            "requirements_before_live": [
                "multi-window backtest must show better final value, Sharpe, and max drawdown after costs",
                "negative covariance warning must predict future 00631L/00632R underperformance out-of-sample",
                "signed promotion review required before any target-weight or execution-guard wiring",
            ],
        },
    }
    return report, rolling_out


def _fmt_pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "n/a"


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Leveraged ETF Timing Anomaly Review",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Source: `{report['research_source']}`",
        f"- Policy: `{report['policy']}`",
        f"- Decision: `{report['decision']}`",
        f"- Latest strategy changed: `{report['changes_latest_strategy']}`",
        "",
        "## Findings",
    ]
    for asset, review in report["asset_reviews"].items():
        full = review["full_sample"]
        latest = review["latest_rolling"]
        lines.extend(
            [
                "",
                f"### {asset}",
                "",
                f"- Average effective leverage: `{full['average_effective_leverage']:.3f}` vs target `{full['target_leverage']:.1f}`",
                f"- Ratio-return covariance: `{_fmt_pct(full['covariance_ratio_underlying_return'])}` annualized",
                f"- Arithmetic gap vs ideal constant leverage: `{_fmt_pct(full['arithmetic_gap_vs_ideal'])}`",
                f"- Volatility drag estimate: `{_fmt_pct(full['volatility_drag_estimate'])}`",
                f"- Full-sample warnings: `{', '.join(full['warnings']) if full['warnings'] else 'none'}`",
                f"- Latest rolling warnings: `{', '.join(latest.get('warnings', [])) if latest and latest.get('warnings') else 'none' if latest else 'n/a'}`",
                f"- Decision: `{review['decision']}`",
            ]
        )
    lines.extend(
        [
            "",
            "## GroupA+ Import Decision",
            "",
            "The useful import is a shadow diagnostic only: track realized effective leverage, volatility drag, and the covariance between effective leverage and 0050 returns before considering 00631L/00632R exposure changes.",
            "",
            "Do not wire this directly into latest strategy, golden1_0531, daily signals, execution plans, or orders without a separate multi-window promotion backtest.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2015-01-05")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--rolling-window", type=int, default=252)
    parser.add_argument("--min-abs-underlying-return", type=float, default=0.0005)
    parser.add_argument("--ratio-winsor-quantile", type=float, default=0.95)
    parser.add_argument("--negative-covariance-warning", type=float, default=-0.005)
    parser.add_argument("--tracking-error-warning", type=float, default=0.20)
    parser.add_argument("--volatility-drag-warning", type=float, default=-0.02)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--markdown", default=str(DEFAULT_MD))
    args = parser.parse_args()

    report, rolling = build_report(args)
    output = Path(args.output)
    csv = Path(args.csv)
    markdown = Path(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    csv.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=_json_default) + "\n", encoding="utf-8")
    rolling.to_csv(csv, index=False, encoding="utf-8-sig")
    markdown.write_text(render_markdown(report), encoding="utf-8")
    print(f"Saved: {output}")
    print(f"CSV: {csv}")
    print(f"Markdown: {markdown}")
    print(f"Decision: {report['decision']}")


if __name__ == "__main__":
    main()
