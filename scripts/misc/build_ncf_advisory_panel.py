#!/usr/bin/env python3
"""Build a historical NCF advisory panel from 00631L/00632R prediction panels."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from FinRL.data.stock_db import DB_PATH
from group_a_plus.integrations.ncf import (
    ncf_cross_ticker_consistency,
    ncf_dynamic_horizon_signal,
)


DEFAULT_631L_PANEL = PROJECT_ROOT / "results" / "ncf_00631l_panel_2025_v7_full.csv"
DEFAULT_632R_PANEL = PROJECT_ROOT / "results" / "ncf_00632r_panel_2025_v6_interactions.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "ncf_advisory_panel_00631l_00632r.csv"
DEFAULT_TICKERS = ("0050.TW", "00631L.TW", "00632R.TW")


def load_panel(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, index_col="date", parse_dates=True, encoding="utf-8-sig")
    df.index = pd.to_datetime(df.index).normalize()
    return df.sort_index()


def _row_signal(row: pd.Series, ticker: str) -> dict[str, Any]:
    horizon_prob_up = {
        h: float(row[f"prob_up_h{h}"])
        for h in ("1", "5", "20")
        if f"prob_up_h{h}" in row and pd.notna(row[f"prob_up_h{h}"])
    }
    prob = float(row.get("ensemble_prob_up", row.get("h20_prob_up", 0.5)))
    confidence = float(row.get("confidence", abs(prob - 0.5) * 2.0))
    return {
        "ticker": ticker,
        "calibrated_prob_up": prob,
        "confidence": confidence,
        "horizon_prob_up": horizon_prob_up,
        # The panel does not carry training-period val AUC by row; dynamic
        # weighting can still use multi-year priors.
        "horizon_val_auc": {},
    }


def build_advisory_panel(panel_631l: pd.DataFrame, panel_632r: pd.DataFrame) -> pd.DataFrame:
    common_idx = panel_631l.index.intersection(panel_632r.index).sort_values()
    rows: list[dict[str, Any]] = []
    for dt in common_idx:
        sig_l = _row_signal(panel_631l.loc[dt], "00631L.TW")
        sig_r = _row_signal(panel_632r.loc[dt], "00632R.TW")
        dyn_l = ncf_dynamic_horizon_signal(sig_l, blend_live_auc=0.0)
        dyn_r = ncf_dynamic_horizon_signal(sig_r, blend_live_auc=0.0)
        cross = ncf_cross_ticker_consistency(sig_l, sig_r, use_dynamic_horizon=True)
        rows.append(
            {
                "date": dt,
                "dynamic_00631l_prob_up": dyn_l["probability_up"],
                "dynamic_00631l_direction": dyn_l["direction"],
                "dynamic_00631l_confidence": dyn_l["confidence"],
                "dynamic_00632r_prob_up": dyn_r["probability_up"],
                "dynamic_00632r_direction": dyn_r["direction"],
                "dynamic_00632r_confidence": dyn_r["confidence"],
                "market_direction": cross["market_direction"],
                "market_probability_up": cross["market_probability_up"],
                "agreement_score": cross["agreement_score"],
                "conflict_flag": cross["conflict_flag"],
                "cross_ticker_confidence": cross["confidence"],
                "raw_00631l_ensemble_prob_up": sig_l["calibrated_prob_up"],
                "raw_00632r_ensemble_prob_up": sig_r["calibrated_prob_up"],
                "is_live_00631l": bool(panel_631l.loc[dt].get("is_live", False)),
                "is_live_00632r": bool(panel_632r.loc[dt].get("is_live", False)),
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).set_index("date").sort_index()


def load_close_prices(db_path: Path, tickers: tuple[str, ...], start: str, end: str) -> pd.DataFrame:
    with duckdb.connect(str(db_path), read_only=True) as con:
        df = con.execute(
            """
            SELECT ticker, dt, close
            FROM ohlcv
            WHERE ticker IN (SELECT * FROM UNNEST(?))
              AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [list(tickers), start, end],
        ).fetchdf()
    if df.empty:
        return pd.DataFrame()
    df["dt"] = pd.to_datetime(df["dt"]).dt.normalize()
    return df.pivot(index="dt", columns="ticker", values="close").sort_index()


def add_forward_returns(
    advisory: pd.DataFrame,
    close_prices: pd.DataFrame,
    horizons: tuple[int, ...] = (5, 20),
) -> pd.DataFrame:
    out = advisory.copy()
    prices = close_prices.reindex(out.index.union(close_prices.index)).sort_index().ffill()
    for ticker in close_prices.columns:
        aligned = prices[ticker].reindex(out.index)
        for h in horizons:
            out[f"fwd_{ticker}_ret_{h}d"] = (aligned.shift(-h) / aligned - 1.0).values
    if "fwd_0050.TW_ret_5d" in out.columns:
        out["market_up_5d"] = out["fwd_0050.TW_ret_5d"] > 0.0
    if "fwd_0050.TW_ret_20d" in out.columns:
        out["market_up_20d"] = out["fwd_0050.TW_ret_20d"] > 0.0
    return out


def summarize_advisory_panel(panel: pd.DataFrame) -> dict[str, Any]:
    labeled = panel.dropna(subset=["fwd_0050.TW_ret_5d", "fwd_0050.TW_ret_20d"], how="all")
    high_agree = labeled[labeled["agreement_score"] >= 0.65]
    conflict = labeled[labeled["conflict_flag"] == True]  # noqa: E712
    bearish = high_agree[high_agree["market_direction"] == "DOWN"]
    bullish = high_agree[high_agree["market_direction"] == "UP"]

    def _mean_ret(df: pd.DataFrame, col: str) -> float | None:
        return None if df.empty or col not in df else float(df[col].mean())

    return {
        "rows": int(len(panel)),
        "labeled_rows": int(len(labeled)),
        "high_agreement_rows": int(len(high_agree)),
        "conflict_rows": int(len(conflict)),
        "high_agreement_bearish_rows": int(len(bearish)),
        "high_agreement_bullish_rows": int(len(bullish)),
        "bearish_mean_0050_ret_5d": _mean_ret(bearish, "fwd_0050.TW_ret_5d"),
        "bearish_mean_0050_ret_20d": _mean_ret(bearish, "fwd_0050.TW_ret_20d"),
        "bullish_mean_0050_ret_5d": _mean_ret(bullish, "fwd_0050.TW_ret_5d"),
        "bullish_mean_0050_ret_20d": _mean_ret(bullish, "fwd_0050.TW_ret_20d"),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel-00631l", default=str(DEFAULT_631L_PANEL))
    parser.add_argument("--panel-00632r", default=str(DEFAULT_632R_PANEL))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    panel_l = load_panel(Path(args.panel_00631l))
    panel_r = load_panel(Path(args.panel_00632r))
    advisory = build_advisory_panel(panel_l, panel_r)
    if advisory.empty:
        raise SystemExit("No overlapping panel dates.")

    start = advisory.index.min().strftime("%Y-%m-%d")
    end = (advisory.index.max() + pd.Timedelta(days=45)).strftime("%Y-%m-%d")
    prices = load_close_prices(Path(args.db), DEFAULT_TICKERS, start, end)
    advisory = add_forward_returns(advisory, prices)

    out = Path(args.output)
    if not out.is_absolute():
        out = PROJECT_ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    advisory.to_csv(out, encoding="utf-8-sig")

    summary = summarize_advisory_panel(advisory)
    print(f"Saved: {out}")
    print("Summary:")
    for key, value in summary.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
