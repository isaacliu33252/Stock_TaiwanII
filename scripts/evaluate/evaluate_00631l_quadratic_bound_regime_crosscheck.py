#!/usr/bin/env python3
"""Cross-check the 00631L compounding-regime classifier against arXiv:2301.03186.

Research-only diagnostic. Does not update production weights, latest
strategy manifests, execution plans, or the compounding-regime guard itself.

Background
----------
`group_a_plus/integrations/leveraged_compounding_regime.py` labels each date
TREND_PERSISTENT / MEAN_REVERTING / TRANSITIONAL from backward-looking
autocorrelation-style features, on the theory (arXiv:2504.20116) that
sequence dependence -- not volatility alone -- drives 00631L compounding
outcomes. That classifier currently runs advisory-only in production (see
GROUP_A_PLUS_00631L_LEVERAGED_COMPOUNDING_REGIME_HANDOFF_20260713.md).

Brown (2023, arXiv:2301.03186) gives a closed-form quadratic lower bound on
a daily-reset leveraged ETF's cumulative log-return, as a function only of
the mean (m1) and mean-square (m2) of the underlying's daily log-returns --
no path/order information. Because the ETF's actual cumulative log-return is
itself a sum of a nonlinear function of each day's return (order-invariant:
multiplication commutes), the two ideas are not in conflict. The regime
label can only add value if it is a leading indicator of what FORWARD (m1,
m2) will look like -- i.e. positive-autocorrelation regimes forecast future
return statistics that land on the favorable side of the 2301.03186 bound,
and mean-reverting regimes forecast the unfavorable side.

This script tests that specific hypothesis: for each classified date, look
at the FORWARD `--horizon`-day window's realized (m1, m2) of the 0050
benchmark, score it with the 2301.03186 closed-form lower bound, and check
whether the regime label predicts which side of the bound the forward
window lands on -- and whether that, in turn, tracks the ETF's actual
forward excess return over the benchmark.
"""

from __future__ import annotations

import argparse
import json
import sys
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
from group_a_plus.integrations.leveraged_compounding_regime import (  # noqa: E402
    MEAN_REVERTING,
    TRANSITIONAL,
    TREND_PERSISTENT,
    build_compounding_features,
    classify_compounding_regime,
)
from group_a_plus.integrations.letf_quadratic_bound import (  # noqa: E402
    quadratic_lower_bound_log_return,
    remark2_lower_bound_coeffs,
)

DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "00631l_quadratic_bound_regime_crosscheck_20260810.json"
DEFAULT_CSV = PROJECT_ROOT / "results" / "00631l_quadratic_bound_regime_crosscheck_20260810.csv"
PDF_REFERENCE = "/mnt/c/Users/isaac/Downloads/2301.03186.pdf"
REGIME_ORDER = [TREND_PERSISTENT, MEAN_REVERTING, TRANSITIONAL]


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


def _regime_summary(rows: pd.DataFrame, regime: str) -> dict[str, Any]:
    subset = rows[rows["compounding_regime"] == regime]
    n = int(len(subset))
    if n == 0:
        return {"n": 0}
    hit = (subset["paper_favorable"] == subset["actual_favorable"]).mean()
    corr = (
        float(subset["paper_margin"].corr(subset["actual_margin"]))
        if n >= 3 and subset["paper_margin"].std() > 0 and subset["actual_margin"].std() > 0
        else None
    )
    return {
        "n": n,
        "mean_paper_margin": float(subset["paper_margin"].mean()),
        "mean_actual_margin": float(subset["actual_margin"].mean()),
        "paper_favorable_rate": float(subset["paper_favorable"].mean()),
        "actual_favorable_rate": float(subset["actual_favorable"].mean()),
        "regime_predicts_actual_direction_hit_rate": float(hit),
        "certified_bound_windows_frac": float(subset["certified"].mean()),
        "corr_paper_vs_actual_margin": corr,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    db_path = Path(args.db)
    end = _resolve_end_date(db_path, args.end)
    close = _load_close(db_path, ["00631L.TW", "0050.TW"], args.start, end)

    log_ret_00631l = np.log(close["00631L.TW"]).diff()
    log_ret_0050 = np.log(close["0050.TW"]).diff()

    features = build_compounding_features(close["00631L.TW"], close["0050.TW"])
    classified = classify_compounding_regime(features).dropna(
        subset=["rolling_AR1_5d", "rolling_AR1_20d", "variance_ratio", "trend_persistence", "reversal_speed"]
    )
    if classified.empty:
        raise RuntimeError("No classified rows after feature warmup")

    y0 = float(np.log(1.0 - args.min_daily_move))
    coeffs = remark2_lower_bound_coeffs(leverage=args.leverage, y0=y0)

    dates = log_ret_0050.index
    horizon = int(args.horizon)
    l0 = float(args.l0)

    records = []
    for dt in classified.index:
        pos = dates.searchsorted(dt)
        fwd_start = pos + 1
        fwd_end = fwd_start + horizon
        if fwd_end > len(dates):
            continue
        fwd_0050 = log_ret_0050.iloc[fwd_start:fwd_end]
        fwd_00631l = log_ret_00631l.iloc[fwd_start:fwd_end]
        if fwd_0050.isna().any() or fwd_00631l.isna().any():
            continue

        m1 = float(fwd_0050.mean())
        m2 = float((fwd_0050**2).mean())
        cum_0050 = float(fwd_0050.sum())
        cum_00631l_actual = float(fwd_00631l.sum())

        paper_lb_cum = quadratic_lower_bound_log_return(m1=m1, m2=m2, n=horizon, coeffs=coeffs)
        paper_margin = paper_lb_cum - l0 * cum_0050
        actual_margin = cum_00631l_actual - l0 * cum_0050
        certified = bool(fwd_0050.min() >= y0)

        records.append(
            {
                "date": str(dt.date()),
                "compounding_regime": classified.loc[dt, "compounding_regime"],
                "forward_m1_0050": m1,
                "forward_m2_0050": m2,
                "forward_cum_log_return_0050": cum_0050,
                "forward_cum_log_return_00631l_actual": cum_00631l_actual,
                "paper_lower_bound_cum_log_return": paper_lb_cum,
                "paper_margin": paper_margin,
                "actual_margin": actual_margin,
                "paper_favorable": bool(paper_margin >= 0.0),
                "actual_favorable": bool(actual_margin >= 0.0),
                "certified": certified,
            }
        )

    if not records:
        raise RuntimeError("No (classified date, complete forward window) pairs available")

    rows = pd.DataFrame.from_records(records)
    csv_path = Path(args.csv)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    rows.to_csv(csv_path, index=False, encoding="utf-8-sig")

    overall_corr = (
        float(rows["paper_margin"].corr(rows["actual_margin"]))
        if rows["paper_margin"].std() > 0 and rows["actual_margin"].std() > 0
        else None
    )

    report = {
        "schema_version": 1,
        "report_type": "00631l_quadratic_bound_regime_crosscheck",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "research_only": True,
        "production_effect": "none",
        "paper_reference": {
            "path": PDF_REFERENCE,
            "citation": "Brown (2023), arXiv:2301.03186",
            "hypothesis_tested": (
                "The live (default-threshold) compounding_regime classifier is a "
                "leading indicator of forward (m1, m2) landing on the favorable "
                "side of the 2301.03186 closed-form quadratic lower bound, and "
                "that favorable/unfavorable split tracks 00631L's actual forward "
                "excess return over l0 * 0050."
            ),
        },
        "params": {
            "leverage": args.leverage,
            "l0": l0,
            "horizon_days": horizon,
            "min_daily_move_floor": args.min_daily_move,
            "y0": y0,
            "quadratic_bound_coeffs_a0_b0_c0": [coeffs.a, coeffs.b, coeffs.c],
        },
        "window": {
            "start": str(close.index.min().date()),
            "end": str(close.index.max().date()),
            "sample_rows": int(len(rows)),
        },
        "overall": {
            "n": int(len(rows)),
            "mean_paper_margin": float(rows["paper_margin"].mean()),
            "mean_actual_margin": float(rows["actual_margin"].mean()),
            "paper_favorable_rate": float(rows["paper_favorable"].mean()),
            "actual_favorable_rate": float(rows["actual_favorable"].mean()),
            "regime_predicts_actual_direction_hit_rate": float(
                (rows["paper_favorable"] == rows["actual_favorable"]).mean()
            ),
            "certified_bound_windows_frac": float(rows["certified"].mean()),
            "corr_paper_vs_actual_margin": overall_corr,
        },
        "by_regime": {regime: _regime_summary(rows, regime) for regime in REGIME_ORDER},
        "csv": str(csv_path),
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2015-01-05")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--horizon", type=int, default=20, help="Forward window length in trading days")
    parser.add_argument("--leverage", type=float, default=2.0)
    parser.add_argument("--l0", type=float, default=1.0, help="Benchmark multiple to compare 00631L against")
    parser.add_argument(
        "--min-daily-move",
        type=float,
        default=0.10,
        help="Daily downside floor as a positive fraction (0.10 => -10%%, TW daily limit)",
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    args = parser.parse_args()

    report = build_report(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved: {output}")
    print(f"CSV: {report['csv']}")
    print(f"Overall hit rate: {report['overall']['regime_predicts_actual_direction_hit_rate']:.3f}")
    for regime in REGIME_ORDER:
        summary = report["by_regime"][regime]
        if summary["n"] == 0:
            print(f"{regime}: n=0")
            continue
        print(
            f"{regime}: n={summary['n']} "
            f"paper_favorable_rate={summary['paper_favorable_rate']:.3f} "
            f"actual_favorable_rate={summary['actual_favorable_rate']:.3f} "
            f"hit_rate={summary['regime_predicts_actual_direction_hit_rate']:.3f}"
        )


if __name__ == "__main__":
    main()
