#!/usr/bin/env python3
"""Evaluate a deep-hedging-lite 00631L overlay shadow for GroupA+.

Research-only implementation inspired by arXiv 2512.12420. This does not
train or import an RL actor. It tests whether simple bounded/cost-aware
00631L overlay rules can survive transaction costs, position caps, and
rebalance cadence before any heavier RL work is considered.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "results/deep_hedging_lite_overlay_shadow_20260717.json"
DEFAULT_WINDOWS = [
    ("2018_correction", "2018-01-02", "2018-12-28"),
    ("2020_covid", "2020-01-02", "2020-06-30"),
    ("2022_rate_hike", "2022-01-03", "2022-10-31"),
    ("2025_2026", "2025-01-02", "2026-07-17"),
]
TICKERS = ("0050.TW", "00631L.TW")


def _load_prices(db_path: Path, start: str, end: str, warmup_days: int = 320) -> pd.DataFrame:
    start_ts = pd.Timestamp(start) - pd.Timedelta(days=warmup_days)
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT dt, ticker, close
            FROM ohlcv
            WHERE ticker IN (SELECT * FROM UNNEST(?))
              AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [list(TICKERS), str(start_ts.date()), end],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        raise RuntimeError(f"No OHLCV rows for {TICKERS} from {start_ts.date()} to {end}")
    rows["dt"] = pd.to_datetime(rows["dt"]).dt.normalize()
    panel = rows.pivot(index="dt", columns="ticker", values="close").sort_index().ffill()
    return panel.dropna(how="any")


def _features(prices: pd.DataFrame) -> pd.DataFrame:
    close = prices["0050.TW"].astype(float)
    ret1 = close.pct_change()
    ma60 = close.rolling(60).mean()
    ma200 = close.rolling(200).mean()
    drawdown = close / close.rolling(252, min_periods=60).max() - 1.0
    rv20 = ret1.rolling(20).std() * np.sqrt(252.0)
    rv120 = ret1.rolling(120, min_periods=60).std() * np.sqrt(252.0)
    return pd.DataFrame(
        {
            "ma_gap": close / ma200 - 1.0,
            "ma60_ma200": ma60 / ma200 - 1.0,
            "drawdown": drawdown,
            "ret_5d": close.pct_change(5),
            "rv20": rv20,
            "rv_ratio": rv20 / rv120,
        },
        index=prices.index,
    )


def _deep_hedging_lite_weight(feat: pd.DataFrame, cap_00631l: float) -> pd.Series:
    """A transparent pre-RL overlay rule.

    20% 00631L only when trend/risk are acceptable.
    10% when risk is elevated.
    0% under deep drawdown / volatility shock / trend break.
    """
    w = pd.Series(cap_00631l, index=feat.index, dtype=float)
    elevated = (
        (feat["drawdown"] <= -0.06)
        | (feat["ret_5d"] <= -0.035)
        | (feat["rv_ratio"] >= 1.20)
        | (feat["ma60_ma200"] <= 0.0)
    )
    severe = (
        (feat["drawdown"] <= -0.10)
        | (feat["ret_5d"] <= -0.06)
        | (feat["rv_ratio"] >= 1.60)
        | (feat["ma_gap"] <= -0.03)
    )
    w.loc[elevated] = min(0.10, cap_00631l)
    w.loc[severe] = 0.0
    return w.fillna(0.0)


def _cadence_hold(weights: pd.Series, cadence: int) -> pd.Series:
    out = weights.copy()
    last = float(out.iloc[0])
    for i, idx in enumerate(out.index):
        if i == 0 or i % cadence == 0:
            last = float(weights.loc[idx])
        out.loc[idx] = last
    return out


def _simulate(
    prices: pd.DataFrame,
    *,
    start: str,
    end: str,
    weights_00631l: pd.Series,
    cost_bps: float,
) -> pd.Series:
    rets = prices.pct_change().fillna(0.0)
    weights_00631l = weights_00631l.reindex(prices.index).ffill().fillna(0.0).clip(0.0, 0.20)
    weights_0050 = (1.0 - weights_00631l).clip(0.0, 1.0)
    gross = weights_0050.shift(1).fillna(weights_0050.iloc[0]) * rets["0050.TW"] + weights_00631l.shift(1).fillna(weights_00631l.iloc[0]) * rets["00631L.TW"]
    turnover = weights_00631l.diff().abs().fillna(weights_00631l.iloc[0])
    net = gross - turnover * (cost_bps / 10000.0)
    return net.loc[(net.index >= pd.Timestamp(start)) & (net.index <= pd.Timestamp(end))]


def _metrics(returns: pd.Series) -> dict[str, Any]:
    r = returns.dropna()
    if r.empty:
        return {}
    wealth = (1.0 + r).cumprod()
    dd = wealth / wealth.cummax() - 1.0
    ann_ret = float(wealth.iloc[-1] ** (252.0 / len(r)) - 1.0)
    ann_vol = float(r.std(ddof=1) * np.sqrt(252.0)) if len(r) > 1 else 0.0
    losses = -r.to_numpy(dtype=float)
    var95 = float(np.quantile(losses, 0.95))
    es95 = float(losses[losses >= var95].mean())
    return {
        "rows": int(len(r)),
        "cumulative_return": float(wealth.iloc[-1] - 1.0),
        "annualized_return": ann_ret,
        "annualized_volatility": ann_vol,
        "sharpe": None if ann_vol == 0 else float(ann_ret / ann_vol),
        "max_drawdown": float(dd.min()),
        "expected_shortfall_loss_95": es95,
        "starr_95": None if es95 == 0 else float(ann_ret / es95),
    }


def _evaluate_window(name: str, start: str, end: str, cadence: int, cost_bps: float) -> dict[str, Any]:
    prices = _load_prices(DB_PATH, start, end)
    feat = _features(prices)
    base_20 = pd.Series(0.20, index=prices.index)
    no_add = pd.Series(0.0, index=prices.index)
    lite = _cadence_hold(_deep_hedging_lite_weight(feat, 0.20), cadence)
    strategies = {
        "no_add_0050_only": no_add,
        "golden1_frozen_50_20_30_proxy": base_20,
        "deep_hedging_lite_cost_aware": lite,
    }
    summaries = {}
    for key, weights in strategies.items():
        returns = _simulate(prices, start=start, end=end, weights_00631l=weights, cost_bps=cost_bps)
        summaries[key] = _metrics(returns)
        summaries[key]["avg_00631l_weight"] = float(weights.loc[(weights.index >= pd.Timestamp(start)) & (weights.index <= pd.Timestamp(end))].mean())
        summaries[key]["turnover_00631l"] = float(weights.loc[(weights.index >= pd.Timestamp(start)) & (weights.index <= pd.Timestamp(end))].diff().abs().fillna(0.0).sum())
    best_by_starr = max(
        summaries,
        key=lambda k: summaries[k].get("starr_95") if summaries[k].get("starr_95") is not None else -np.inf,
    )
    return {
        "window": name,
        "start": start,
        "end": end,
        "cadence_days": cadence,
        "cost_bps_per_abs_weight_change": cost_bps,
        "strategies": summaries,
        "best_by_starr95": best_by_starr,
        "lite_beats_golden1_starr95": (
            (summaries["deep_hedging_lite_cost_aware"].get("starr_95") or -np.inf)
            > (summaries["golden1_frozen_50_20_30_proxy"].get("starr_95") or -np.inf)
        ),
        "lite_beats_no_add_starr95": (
            (summaries["deep_hedging_lite_cost_aware"].get("starr_95") or -np.inf)
            > (summaries["no_add_0050_only"].get("starr_95") or -np.inf)
        ),
    }


def build_report(windows: list[tuple[str, str, str]], cadence: int, cost_bps: float) -> dict[str, Any]:
    rows = [_evaluate_window(name, start, end, cadence, cost_bps) for name, start, end in windows]
    lite_wins_golden = sum(1 for row in rows if row["lite_beats_golden1_starr95"])
    lite_wins_no_add = sum(1 for row in rows if row["lite_beats_no_add_starr95"])
    promote = bool(lite_wins_golden == len(rows) and lite_wins_no_add == len(rows))
    return {
        "schema_version": 1,
        "report_type": "deep_hedging_lite_overlay_shadow",
        "status": "research_only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2512.12420.pdf",
            "imported_concepts": ["costs", "position_caps", "rebalance_cadence", "deterministic_replay"],
            "not_imported": ["actor_critic_rl_policy"],
        },
        "parameters": {
            "cadence_days": cadence,
            "cost_bps_per_abs_weight_change": cost_bps,
            "max_00631l_weight": 0.20,
        },
        "windows": rows,
        "aggregate": {
            "windows": len(rows),
            "lite_wins_golden1_starr95": lite_wins_golden,
            "lite_wins_no_add_starr95": lite_wins_no_add,
        },
        "decision": {
            "promote_to_live": promote,
            "target_weight_change_allowed": False,
            "allow_00631l_add": False,
            "summary": (
                "Research-only. Deep-hedging-lite must beat both golden1 proxy and no-add across all windows after costs before promotion."
            ),
        },
    }


def _parse_window(raw: str) -> tuple[str, str, str]:
    parts = raw.split("=", 2)
    if len(parts) != 3:
        raise ValueError("--window must use name=start=end")
    return parts[0], parts[1], parts[2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window", action="append", default=[], help="name=start=end; may repeat")
    parser.add_argument("--cadence", type=int, default=20)
    parser.add_argument("--cost-bps", type=float, default=18.0)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    windows = [_parse_window(item) for item in args.window] if args.window else DEFAULT_WINDOWS
    report = build_report(windows, cadence=int(args.cadence), cost_bps=float(args.cost_bps))
    output = Path(args.output)
    if not output.is_absolute():
        output = PROJECT_ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Shadow report: {output}")
    print(json.dumps({"aggregate": report["aggregate"], "decision": report["decision"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
