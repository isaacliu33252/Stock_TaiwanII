#!/usr/bin/env python3
"""Evaluate simple exposure policies driven by the NCF advisory panel."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from FinRL.data.stock_db import DB_PATH


DEFAULT_ADVISORY = PROJECT_ROOT / "results" / "ncf_advisory_panel_latest_20260627.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / f"ncf_advisory_policy_eval_{datetime.now().strftime('%Y%m%d')}.json"


def load_advisory(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["date"], encoding="utf-8-sig")
    frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
    return frame.set_index("date").sort_index()


def load_close_prices(db_path: Path, tickers: list[str], start: str, end: str) -> pd.DataFrame:
    with duckdb.connect(str(db_path), read_only=True) as con:
        rows = con.execute(
            """
            SELECT ticker, dt, close
            FROM ohlcv
            WHERE ticker IN (SELECT * FROM UNNEST(?))
              AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [tickers, start, end],
        ).fetchdf()
    if rows.empty:
        raise RuntimeError(f"No OHLCV rows for {tickers} between {start} and {end}")
    rows["dt"] = pd.to_datetime(rows["dt"]).dt.normalize()
    return rows.pivot(index="dt", columns="ticker", values="close").sort_index()


def policy_exposure(frame: pd.DataFrame, policy: str) -> pd.Series:
    if policy == "baseline_0050":
        exposure = pd.Series(1.0, index=frame.index)
    elif policy == "bearish_reduce_20":
        exposure = pd.Series(1.0, index=frame.index)
        exposure[frame["market_direction"] == "DOWN"] = 0.80
    elif policy == "bearish_reduce_40":
        exposure = pd.Series(1.0, index=frame.index)
        exposure[frame["market_direction"] == "DOWN"] = 0.60
    elif policy == "conflict_reduce_20":
        exposure = pd.Series(1.0, index=frame.index)
        exposure[frame["conflict_flag"].astype(bool)] = 0.80
    elif policy == "high_agreement_bearish_reduce_20":
        exposure = pd.Series(1.0, index=frame.index)
        mask = (frame["market_direction"] == "DOWN") & (frame["agreement_score"] >= 0.65)
        exposure[mask] = 0.80
    elif policy == "high_agreement_bearish_reduce_40":
        exposure = pd.Series(1.0, index=frame.index)
        mask = (frame["market_direction"] == "DOWN") & (frame["agreement_score"] >= 0.65)
        exposure[mask] = 0.60
    else:
        raise ValueError(f"Unsupported policy: {policy}")
    return exposure.astype(float)


def metrics(values: pd.Series, exposure: pd.Series, *, turnover: pd.Series) -> dict[str, Any]:
    daily = values.pct_change().dropna()
    years = max((values.index[-1] - values.index[0]).days / 365.25, 1e-9)
    std = float(daily.std())
    return {
        "start": str(values.index[0].date()),
        "end": str(values.index[-1].date()),
        "rows": int(len(values)),
        "final_value": float(values.iloc[-1]),
        "total_return": float(values.iloc[-1] / values.iloc[0] - 1.0),
        "cagr": float((values.iloc[-1] / values.iloc[0]) ** (1.0 / years) - 1.0),
        "sharpe": float(daily.mean() / std * math.sqrt(252.0)) if len(daily) > 1 and std > 0 else 0.0,
        "max_drawdown": float((values / values.cummax() - 1.0).min()),
        "volatility": float(std * math.sqrt(252.0)) if len(daily) > 1 else 0.0,
        "avg_0050_exposure": float(exposure.mean()),
        "min_0050_exposure": float(exposure.min()),
        "turnover_proxy": float(turnover.sum()),
        "exposure_change_count": int((turnover > 1e-12).sum()),
    }


def simulate_policy(
    advisory: pd.DataFrame,
    prices: pd.DataFrame,
    policy: str,
    *,
    risk_ticker: str = "0050.TW",
    defensive_ticker: str | None = None,
    initial_value: float = 1_000_000.0,
) -> tuple[pd.Series, pd.DataFrame, dict[str, Any]]:
    frame = advisory.join(prices, how="inner")
    if risk_ticker not in frame:
        raise RuntimeError(f"Missing risk ticker price: {risk_ticker}")
    risk_ret = frame[risk_ticker].pct_change().fillna(0.0)
    defensive_ret = pd.Series(0.0, index=frame.index)
    if defensive_ticker:
        if defensive_ticker not in frame:
            raise RuntimeError(f"Missing defensive ticker price: {defensive_ticker}")
        defensive_ret = frame[defensive_ticker].pct_change().fillna(0.0)

    raw_exposure = policy_exposure(frame, policy)
    # Use yesterday's advisory for today's exposure decision.
    exposure = raw_exposure.shift(1).fillna(1.0).clip(0.0, 1.0)
    turnover = exposure.diff().abs().fillna(0.0)
    daily_ret = exposure * risk_ret + (1.0 - exposure) * defensive_ret
    values = initial_value * (1.0 + daily_ret).cumprod()
    detail = pd.DataFrame(
        {
            "0050_exposure": exposure,
            "defensive_exposure": 1.0 - exposure,
            "strategy_return": daily_ret,
            "value": values,
            "turnover": turnover,
            "market_direction_lag1": frame["market_direction"].shift(1),
            "agreement_score_lag1": frame["agreement_score"].shift(1),
            "conflict_flag_lag1": frame["conflict_flag"].shift(1),
        },
        index=frame.index,
    )
    return values, detail, metrics(values, exposure, turnover=turnover)


def evaluate_policies(
    advisory: pd.DataFrame,
    prices: pd.DataFrame,
    policies: list[str],
    *,
    defensive_ticker: str | None = None,
    initial_value: float = 1_000_000.0,
) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
    results: dict[str, Any] = {}
    details: dict[str, pd.DataFrame] = {}
    for policy in policies:
        values, detail, result = simulate_policy(
            advisory,
            prices,
            policy,
            defensive_ticker=defensive_ticker,
            initial_value=initial_value,
        )
        result["policy"] = policy
        result["defensive_ticker"] = defensive_ticker or "cash"
        results[policy] = result
        details[policy] = detail
    baseline = results.get("baseline_0050")
    if baseline:
        for result in results.values():
            result["delta_total_return_vs_baseline"] = float(result["total_return"] - baseline["total_return"])
            result["delta_sharpe_vs_baseline"] = float(result["sharpe"] - baseline["sharpe"])
            result["delta_max_drawdown_vs_baseline"] = float(result["max_drawdown"] - baseline["max_drawdown"])
    return results, details


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--advisory-panel", default=str(DEFAULT_ADVISORY))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--details-output", default=None)
    parser.add_argument("--defensive-ticker", default=None, help="Optional defensive sleeve, e.g. 00679B.TWO. Default: cash.")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument(
        "--policies",
        default=(
            "baseline_0050,bearish_reduce_20,bearish_reduce_40,"
            "conflict_reduce_20,high_agreement_bearish_reduce_20,high_agreement_bearish_reduce_40"
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    advisory_path = Path(args.advisory_panel)
    if not advisory_path.is_absolute():
        advisory_path = PROJECT_ROOT / advisory_path
    advisory = load_advisory(advisory_path)
    tickers = ["0050.TW"]
    if args.defensive_ticker:
        tickers.append(args.defensive_ticker)
    prices = load_close_prices(
        Path(args.db),
        tickers,
        advisory.index.min().strftime("%Y-%m-%d"),
        advisory.index.max().strftime("%Y-%m-%d"),
    )
    policies = [item.strip() for item in args.policies.split(",") if item.strip()]
    results, details = evaluate_policies(
        advisory,
        prices,
        policies,
        defensive_ticker=args.defensive_ticker,
        initial_value=float(args.initial_value),
    )

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "advisory_panel": str(advisory_path),
        "window": {
            "start": str(advisory.index.min().date()),
            "end": str(advisory.index.max().date()),
            "rows": int(len(advisory)),
        },
        "method_note": "Uses prior-day NCF advisory to set next-day 0050 exposure. Reduced exposure goes to cash unless --defensive-ticker is set.",
        "policies": results,
        "ranking_by_sharpe": sorted(results, key=lambda name: results[name]["sharpe"], reverse=True),
    }

    output = Path(args.output)
    if not output.is_absolute():
        output = PROJECT_ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.details_output:
        detail_path = Path(args.details_output)
        if not detail_path.is_absolute():
            detail_path = PROJECT_ROOT / detail_path
        detail_path.parent.mkdir(parents=True, exist_ok=True)
        wide = pd.concat({name: detail for name, detail in details.items()}, axis=1)
        wide.to_csv(detail_path, encoding="utf-8-sig")

    print(f"Saved: {output}")
    print("Policy summary:")
    for name in report["ranking_by_sharpe"]:
        row = results[name]
        print(
            f"  {name}: return={row['total_return']:.2%} "
            f"sharpe={row['sharpe']:.3f} mdd={row['max_drawdown']:.2%} "
            f"avg_exp={row['avg_0050_exposure']:.2f} turnover={row['turnover_proxy']:.2f}"
        )


if __name__ == "__main__":
    main()
