#!/usr/bin/env python3
"""Evaluate an advisory 0-3 leverage tier from ncf_2330 + ncf_00631L.

This is a research-only diagnostic. It does not change production target
weights. The goal is to check whether the two NCF models can produce a more
useful 00631L suitability label than raw probability-up alone:

  0 = unfavorable for 00631L
  1 = 0050 only
  2 = 0050 + small 00631L
  3 = suitable to raise 00631L
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from group_a_plus.governance.latest import DEFAULT_LATEST_STRATEGY  # noqa: E402
from group_a_plus.runners.latest import run_latest  # noqa: E402


START = "2025-01-02"
END = "2026-07-02"
INITIAL_VALUE = 1_000_000.0
TSMC_WEIGHT_ASSUMPTION = 0.55
PANEL_631L = PROJECT_ROOT / "results" / "ncf_00631l_panel_latest_20260630.csv"
PANEL_2330 = PROJECT_ROOT / "results" / "ncf_2330_improved_panel_latest_20260703.csv"
OUT_JSON = PROJECT_ROOT / "results" / "ncf_2330_00631l_tier_eval_20260705.json"
OUT_CSV = PROJECT_ROOT / "results" / "ncf_2330_00631l_tier_eval_20260705.csv"


@dataclass(frozen=True)
class TierSpec:
    l631_bull_min: float = 0.58
    l631_weak_max: float = 0.48
    l631_tail_high: float = 0.55
    l631_tail_low: float = 0.40
    tsmc_tail_high: float = 0.50
    tsmc_prob_weak_max: float = 0.50
    max_tier3_risk_score: int = 2
    min_tier1_risk_score: int = 6
    min_tier0_risk_score: int = 9


def _load_panel(path: Path, prefix: str) -> pd.DataFrame:
    df = pd.read_csv(path, index_col="date", parse_dates=True, encoding="utf-8-sig")
    df.index = pd.to_datetime(df.index).normalize()
    keep = [
        "prob_up_h5",
        "prob_up_h20",
        "ensemble_prob_up",
        "prob_fwd_mdd_gt5_h20",
        "forward_mdd_h20",
        "confidence",
    ]
    cols = [col for col in keep if col in df.columns]
    return df[cols].rename(columns={col: f"{prefix}_{col}" for col in cols}).sort_index()


def _load_ohlcv_close(db_path: Path, tickers: list[str], start: str, end: str) -> pd.DataFrame:
    with duckdb.connect(str(db_path), read_only=True) as con:
        df = con.execute(
            """
            SELECT ticker, dt, close
            FROM ohlcv
            WHERE ticker IN (SELECT * FROM UNNEST(?))
              AND dt BETWEEN ? AND ?
              AND close IS NOT NULL
            ORDER BY dt, ticker
            """,
            [tickers, start, end],
        ).fetchdf()
    if df.empty:
        raise RuntimeError("Missing OHLCV close data.")
    df["dt"] = pd.to_datetime(df["dt"]).dt.normalize()
    return df.pivot(index="dt", columns="ticker", values="close").sort_index()


def _load_tsmc_close(db_path: Path, start: str, end: str) -> pd.Series:
    with duckdb.connect(str(db_path), read_only=True) as con:
        df = con.execute(
            """
            SELECT dt, close
            FROM external_market_ohlcv
            WHERE provider = 'yfinance'
              AND ticker = '2330.TW'
              AND dt BETWEEN ? AND ?
              AND close IS NOT NULL
            ORDER BY dt
            """,
            [start, end],
        ).fetchdf()
    if df.empty:
        raise RuntimeError("Missing external_market_ohlcv rows for 2330.TW.")
    out = df.set_index(pd.to_datetime(df["dt"]).dt.normalize())["close"].astype(float)
    return out[~out.index.duplicated()].sort_index()


def _forward_mdd(price: pd.Series, horizon: int) -> pd.Series:
    values: list[float | None] = []
    for i in range(len(price)):
        segment = price.iloc[i : min(i + horizon + 1, len(price))]
        if len(segment) <= 1 or not pd.notna(segment.iloc[0]) or float(segment.iloc[0]) <= 0:
            values.append(None)
            continue
        values.append(float((segment / float(segment.iloc[0]) - 1.0).min()))
    return pd.Series(values, index=price.index)


def _add_price_features(frame: pd.DataFrame, db_path: Path) -> pd.DataFrame:
    start = str((frame.index.min() - pd.Timedelta(days=90)).date())
    end = str((frame.index.max() + pd.Timedelta(days=45)).date())
    prices = _load_ohlcv_close(db_path, ["0050.TW", "00631L.TW"], start, end)
    tsmc = _load_tsmc_close(db_path, start, end)
    idx = frame.index
    out = frame.copy()
    out["ret_2330_5d"] = tsmc.pct_change(5).reindex(idx)
    out["ret_0050_5d"] = prices["0050.TW"].pct_change(5).reindex(idx)
    out["ret_00631l_5d"] = prices["00631L.TW"].pct_change(5).reindex(idx)
    out["ret_0050_ex_tsmc_5d"] = (
        out["ret_0050_5d"] - TSMC_WEIGHT_ASSUMPTION * out["ret_2330_5d"]
    ) / (1.0 - TSMC_WEIGHT_ASSUMPTION)
    for horizon in (5, 20):
        for ticker in ("0050.TW", "00631L.TW"):
            aligned = prices[ticker].reindex(idx.union(prices.index)).sort_index().ffill().reindex(idx)
            out[f"fwd_{ticker}_ret_{horizon}d"] = (aligned.shift(-horizon) / aligned - 1.0).values
        out[f"fwd_00631L.TW_mdd_{horizon}d"] = _forward_mdd(
            prices["00631L.TW"].reindex(idx.union(prices.index)).sort_index().ffill().reindex(idx),
            horizon,
        ).values
        out[f"fwd_00631L_vs_0050_excess_{horizon}d"] = (
            out[f"fwd_00631L.TW_ret_{horizon}d"] - out[f"fwd_0050.TW_ret_{horizon}d"]
        )
    return out


def build_feature_frame(db_path: Path, panel_631l: Path, panel_2330: Path) -> pd.DataFrame:
    _, strategy_frame = run_latest(START, END, INITIAL_VALUE, db_path, DEFAULT_LATEST_STRATEGY)
    ncf = _load_panel(panel_631l, "l631").join(_load_panel(panel_2330, "tsmc"), how="inner")
    idx = strategy_frame.index.intersection(ncf.index).sort_values()
    frame = ncf.reindex(idx).copy()
    for col in ("execution_regime", "total_risk_score", "tail_risk_score", "ma_gap", "drawdown"):
        if col in strategy_frame.columns:
            frame[col] = strategy_frame[col].reindex(idx)
    frame["execution_regime"] = frame["execution_regime"].astype(str)
    frame["total_risk_score"] = frame["total_risk_score"].fillna(0).astype(int)
    frame["tail_risk_score"] = frame["tail_risk_score"].fillna(0).astype(int)
    return _add_price_features(frame, db_path)


def assign_tiers(frame: pd.DataFrame, spec: TierSpec) -> pd.DataFrame:
    out = frame.copy()
    tsmc_weak = (
        (out["tsmc_prob_up_h20"] < spec.tsmc_prob_weak_max)
        | (out["tsmc_prob_fwd_mdd_gt5_h20"] >= spec.tsmc_tail_high)
        | ((out["ret_2330_5d"] <= -0.02) & (out["ret_0050_ex_tsmc_5d"] <= 0.0))
    ).fillna(False)
    tsmc_narrow = (
        (out["ret_2330_5d"] > 0.0)
        & (out["ret_0050_ex_tsmc_5d"] <= 0.0)
        & ((out["ret_2330_5d"] - out["ret_0050_5d"]) > 0.01)
    ).fillna(False)
    tsmc_healthy = (
        (out[["ret_2330_5d", "ret_0050_5d", "ret_00631l_5d", "ret_0050_ex_tsmc_5d"]].min(axis=1) > 0.0)
    ).fillna(False)
    l631_weak = (
        (out["l631_prob_up_h20"] <= spec.l631_weak_max)
        | (out["l631_prob_fwd_mdd_gt5_h20"] >= spec.l631_tail_high)
    ).fillna(False)
    l631_bull = (
        (out["l631_prob_up_h20"] >= spec.l631_bull_min)
        & (out["l631_prob_fwd_mdd_gt5_h20"] <= spec.l631_tail_low)
    ).fillna(False)

    tier = pd.Series(2, index=out.index, dtype=int)
    tier.loc[
        (out["execution_regime"] == "group_a_plus_defensive")
        | ((out["total_risk_score"] >= spec.min_tier0_risk_score) & l631_weak)
        | (tsmc_weak & l631_weak)
    ] = 0
    tier.loc[
        (tier != 0)
        & (
            tsmc_narrow
            | (out["total_risk_score"] >= spec.min_tier1_risk_score)
            | l631_weak
            | (out["tail_risk_score"] >= 2)
        )
    ] = 1
    tier.loc[
        (out["execution_regime"].isin(["golden1", "group_a_plus_recovery"]))
        & tsmc_healthy
        & l631_bull
        & (out["total_risk_score"] <= spec.max_tier3_risk_score)
    ] = 3

    out["tier"] = tier
    out["tsmc_weak"] = tsmc_weak
    out["tsmc_narrow"] = tsmc_narrow
    out["tsmc_healthy"] = tsmc_healthy
    out["l631_weak"] = l631_weak
    out["l631_bull"] = l631_bull
    return out


def summarize_tiers(frame: pd.DataFrame) -> dict[str, Any]:
    labeled = frame.dropna(subset=["fwd_00631L_vs_0050_excess_20d", "fwd_00631L.TW_mdd_20d"])
    rows: dict[str, Any] = {}
    for tier, group in labeled.groupby("tier"):
        rows[str(int(tier))] = {
            "days": int(len(group)),
            "mean_00631l_ret_5d": float(group["fwd_00631L.TW_ret_5d"].mean()),
            "mean_0050_ret_5d": float(group["fwd_0050.TW_ret_5d"].mean()),
            "mean_excess_5d": float(group["fwd_00631L_vs_0050_excess_5d"].mean()),
            "mean_00631l_ret_20d": float(group["fwd_00631L.TW_ret_20d"].mean()),
            "mean_0050_ret_20d": float(group["fwd_0050.TW_ret_20d"].mean()),
            "mean_excess_20d": float(group["fwd_00631L_vs_0050_excess_20d"].mean()),
            "win_vs_0050_20d": float((group["fwd_00631L_vs_0050_excess_20d"] > 0.0).mean()),
            "bad_mdd_gt5_20d": float((group["fwd_00631L.TW_mdd_20d"] <= -0.05).mean()),
            "avg_fwd_mdd_20d": float(group["fwd_00631L.TW_mdd_20d"].mean()),
        }
    tier0 = rows.get("0", {})
    tier3 = rows.get("3", {})
    separation = {
        "tier3_minus_tier0_excess_20d": (
            float(tier3.get("mean_excess_20d", 0.0)) - float(tier0.get("mean_excess_20d", 0.0))
            if tier0 and tier3 else None
        ),
        "tier3_win_minus_tier0_win_20d": (
            float(tier3.get("win_vs_0050_20d", 0.0)) - float(tier0.get("win_vs_0050_20d", 0.0))
            if tier0 and tier3 else None
        ),
        "tier0_bad_mdd_minus_tier3_bad_mdd_20d": (
            float(tier0.get("bad_mdd_gt5_20d", 0.0)) - float(tier3.get("bad_mdd_gt5_20d", 0.0))
            if tier0 and tier3 else None
        ),
    }
    return {
        "rows": int(len(frame)),
        "labeled_rows": int(len(labeled)),
        "tier_summary": rows,
        "separation": separation,
    }


def _score(summary: dict[str, Any]) -> float:
    sep = summary["separation"]
    if sep["tier3_minus_tier0_excess_20d"] is None:
        return -999.0
    tiers = summary["tier_summary"]
    tier0_days = tiers.get("0", {}).get("days", 0)
    tier3_days = tiers.get("3", {}).get("days", 0)
    if tier0_days < 5 or tier3_days < 5:
        return -999.0
    excess = {
        int(tier): float(row["mean_excess_20d"])
        for tier, row in tiers.items()
        if int(tier) in {0, 1, 2, 3}
    }
    mdd = {
        int(tier): float(row["bad_mdd_gt5_20d"])
        for tier, row in tiers.items()
        if int(tier) in {0, 1, 2, 3}
    }
    monotonic_penalty = 0.0
    for low, high in ((0, 1), (1, 2), (2, 3)):
        if low in excess and high in excess:
            monotonic_penalty += max(0.0, excess[low] - excess[high]) * 3.0
        if low in mdd and high in mdd:
            monotonic_penalty += max(0.0, mdd[high] - mdd[low]) * 0.15
    return (
        2.0 * float(sep["tier3_minus_tier0_excess_20d"])
        + 0.10 * float(sep["tier3_win_minus_tier0_win_20d"])
        + 0.10 * float(sep["tier0_bad_mdd_minus_tier3_bad_mdd_20d"])
        - monotonic_penalty
    )


def sweep_specs(frame: pd.DataFrame) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for l_bull in (0.56, 0.58, 0.60, 0.62):
        for l_weak in (0.45, 0.48, 0.50):
            for l_tail_hi in (0.50, 0.55, 0.60):
                for t_tail_hi in (0.45, 0.50, 0.55):
                    spec = TierSpec(
                        l631_bull_min=l_bull,
                        l631_weak_max=l_weak,
                        l631_tail_high=l_tail_hi,
                        tsmc_tail_high=t_tail_hi,
                    )
                    labeled = assign_tiers(frame, spec)
                    summary = summarize_tiers(labeled)
                    results.append({
                        "score": _score(summary),
                        "spec": asdict(spec),
                        "summary": summary,
                    })
    return sorted(results, key=lambda item: item["score"], reverse=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--panel-00631l", default=str(PANEL_631L))
    parser.add_argument("--panel-2330", default=str(PANEL_2330))
    parser.add_argument("--output-json", default=str(OUT_JSON))
    parser.add_argument("--output-csv", default=str(OUT_CSV))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    frame = build_feature_frame(Path(args.db), Path(args.panel_00631l), Path(args.panel_2330))
    ranked = sweep_specs(frame)
    best = ranked[0]
    best_frame = assign_tiers(frame, TierSpec(**best["spec"]))

    out_csv = Path(args.output_csv)
    out_json = Path(args.output_json)
    best_frame.to_csv(out_csv, encoding="utf-8-sig")
    report = {
        "experiment": "ncf_2330_00631l_tier_eval",
        "period": {"start": START, "end": END},
        "inputs": {
            "panel_00631l": str(Path(args.panel_00631l).relative_to(PROJECT_ROOT)),
            "panel_2330": str(Path(args.panel_2330).relative_to(PROJECT_ROOT)),
            "db": str(Path(args.db)),
        },
        "best": best,
        "top10": ranked[:10],
        "tier_map": {
            "0": "不利 00631L",
            "1": "只適合 0050",
            "2": "可持有 0050 + 小 00631L",
            "3": "適合提高 00631L",
        },
        "notes": [
            "Research-only advisory labels; no production weight changes.",
            "Score rewards 20d 00631L-vs-0050 separation, win-rate separation, and lower tier3 drawdown risk.",
        ],
    }
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Saved JSON: {out_json}")
    print(f"Saved CSV: {out_csv}")
    print(f"Best score: {best['score']:.6f}")
    print("Best spec:")
    for key, value in best["spec"].items():
        print(f"  {key}: {value}")
    print("Tier summary:")
    for tier, row in best["summary"]["tier_summary"].items():
        print(
            f"  tier {tier}: days={row['days']}, "
            f"excess20={row['mean_excess_20d']:.4%}, "
            f"win20={row['win_vs_0050_20d']:.1%}, "
            f"bad_mdd20={row['bad_mdd_gt5_20d']:.1%}"
        )


if __name__ == "__main__":
    main()
