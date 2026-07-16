#!/usr/bin/env python3
"""Evaluate sequence-aware compounding regimes for 00631L.

Research-only diagnostic.  This does not update production weights, latest
strategy manifests, or execution plans.
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
from group_a_plus.integrations.leveraged_compounding_regime import (  # noqa: E402
    MEAN_REVERTING,
    TRANSITIONAL,
    TREND_PERSISTENT,
    CompoundingRegimeThresholds,
    build_compounding_features,
    classify_compounding_regime,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "00631l_leveraged_compounding_regime_20260713.json"
DEFAULT_CSV = PROJECT_ROOT / "results" / "00631l_leveraged_compounding_regime_20260713.csv"
PDF_REFERENCE = "/mnt/c/Users/isaac/Downloads/2504.20116v1.pdf"


def _resolve_end_date(db_path: Path, requested_end: str, ticker: str = "00631L.TW") -> str:
    if requested_end.lower() != "latest":
        return requested_end
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        max_dt = con.execute("SELECT MAX(dt) FROM ohlcv WHERE ticker = ?", [ticker]).fetchone()[0]
    finally:
        con.close()
    if max_dt is None:
        raise RuntimeError(f"No OHLCV rows for {ticker}")
    return pd.Timestamp(max_dt).strftime("%Y-%m-%d")


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
        raise RuntimeError(f"No OHLCV rows for {tickers} between {start} and {end}")
    rows["dt"] = pd.to_datetime(rows["dt"])
    close = rows.pivot(index="dt", columns="ticker", values="close").sort_index()
    missing = [ticker for ticker in tickers if ticker not in close.columns]
    if missing:
        raise RuntimeError(f"Missing close columns: {missing}")
    return close[tickers].dropna()


def _regime_counts(frame: pd.DataFrame) -> dict[str, int]:
    counts = frame["compounding_regime"].value_counts()
    return {
        TREND_PERSISTENT: int(counts.get(TREND_PERSISTENT, 0)),
        MEAN_REVERTING: int(counts.get(MEAN_REVERTING, 0)),
        TRANSITIONAL: int(counts.get(TRANSITIONAL, 0)),
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    db_path = Path(args.db)
    end = _resolve_end_date(db_path, args.end)
    close = _load_close(db_path, ["00631L.TW", "0050.TW"], args.start, end)
    features = build_compounding_features(close["00631L.TW"], close["0050.TW"])
    thresholds = CompoundingRegimeThresholds(
        ar1_trend_min=float(args.ar1_trend_min),
        ar1_revert_max=float(args.ar1_revert_max),
        variance_ratio_trend_min=float(args.variance_ratio_trend_min),
        variance_ratio_revert_max=float(args.variance_ratio_revert_max),
        trend_persistence_min=float(args.trend_persistence_min),
        trend_persistence_revert_max=float(args.trend_persistence_revert_max),
        reversal_speed_revert_min=float(args.reversal_speed_revert_min),
        reversal_speed_trend_max=float(args.reversal_speed_trend_max),
        drawdown_recovery_revert_min=float(args.drawdown_recovery_revert_min),
        trend_score_min=int(args.trend_score_min),
        mean_reversion_score_min=int(args.mean_reversion_score_min),
    )
    classified = classify_compounding_regime(features, thresholds=thresholds).dropna(
        subset=[
            "rolling_AR1_5d",
            "rolling_AR1_20d",
            "variance_ratio",
            "trend_persistence",
            "reversal_speed",
            "drawdown_recovery_ratio",
            "00631L_vs_0050_relative_momentum",
            "compounding_effect_20d",
            "compounding_effect_60d",
            "compounding_effect_120d",
            "realized_volatility_20d",
            "realized_volatility_60d",
            "volatility_persistence_ratio",
        ]
    )
    if classified.empty:
        raise RuntimeError("No classified rows after feature warmup")

    output_frame = classified.copy()
    output_frame.index.name = "date"
    output_frame = output_frame.reset_index()
    output_frame["date"] = pd.to_datetime(output_frame["date"]).dt.strftime("%Y-%m-%d")
    csv_path = Path(args.csv)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    output_frame.to_csv(csv_path, index=False, encoding="utf-8-sig")

    latest = output_frame.iloc[-1].to_dict()
    recent = output_frame.tail(args.recent_days)
    report = {
        "schema_version": 1,
        "report_type": "00631l_leveraged_compounding_regime",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "active_allocation_impact": "none",
        "paper_reference": {
            "path": PDF_REFERENCE,
            "user_summary": (
                "Leveraged ETF outcomes depend not only on volatility but also on return sequence "
                "dependence. Trend/positive-autocorrelation regimes can compound favorably; "
                "mean-reverting regimes can create negative compounding from de-risk/re-entry lag."
            ),
        },
        "method": (
            "Backward-looking, no-lookahead sequence diagnostics on 00631L daily returns, "
            "with 0050 relative momentum. High volatility alone is not used as a de-leveraging trigger."
        ),
        "thresholds": thresholds.__dict__,
        "window": {
            "start": str(close.index.min().date()),
            "end": str(close.index.max().date()),
            "classified_start": str(classified.index.min().date()),
            "classified_end": str(classified.index.max().date()),
            "classified_rows": int(len(classified)),
        },
        "features": [
            "rolling_AR1_5d",
            "rolling_AR1_20d",
            "variance_ratio",
            "trend_persistence",
            "reversal_speed",
            "positive_return_streak",
            "negative_return_streak",
            "drawdown_recovery_ratio",
            "00631L_vs_0050_relative_momentum",
            "compounding_effect_20d",
            "compounding_effect_60d",
            "compounding_effect_120d",
            "realized_volatility_20d",
            "realized_volatility_60d",
            "volatility_persistence_ratio",
        ],
        "regime_policy": {
            TREND_PERSISTENT: "Do not reduce 00631L for high volatility alone.",
            MEAN_REVERTING: "Prohibit new leverage or reduce rebalance frequency.",
            TRANSITIONAL: "Maintain A21.18; do not actively overlay.",
        },
        "latest": latest,
        "recent_regime_counts": _regime_counts(recent),
        "full_regime_counts": _regime_counts(output_frame),
        "csv": str(csv_path),
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2015-01-05")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--recent-days", type=int, default=20)
    parser.add_argument("--ar1-trend-min", type=float, default=0.05)
    parser.add_argument("--ar1-revert-max", type=float, default=-0.05)
    parser.add_argument("--variance-ratio-trend-min", type=float, default=1.02)
    parser.add_argument("--variance-ratio-revert-max", type=float, default=0.98)
    parser.add_argument("--trend-persistence-min", type=float, default=0.60)
    parser.add_argument("--trend-persistence-revert-max", type=float, default=0.55)
    parser.add_argument("--reversal-speed-revert-min", type=float, default=0.55)
    parser.add_argument("--reversal-speed-trend-max", type=float, default=0.45)
    parser.add_argument("--drawdown-recovery-revert-min", type=float, default=0.50)
    parser.add_argument("--trend-score-min", type=int, default=4)
    parser.add_argument("--mean-reversion-score-min", type=int, default=3)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    args = parser.parse_args()

    report = build_report(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    latest = report["latest"]
    print(f"Saved: {output}")
    print(f"CSV: {report['csv']}")
    print(
        "Latest: "
        f"{latest['date']} {latest['compounding_regime']} "
        f"policy={latest['recommended_policy']}"
    )


if __name__ == "__main__":
    main()
