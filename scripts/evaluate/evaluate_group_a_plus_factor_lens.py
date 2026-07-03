#!/usr/bin/env python3
"""Alphalens-inspired diagnostics for GroupA+ NCF advisory factors."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from FinRL.data.stock_db import DB_PATH
from group_a_plus.integrations.factor_lens import (
    event_study_forward_returns,
    ic_decay,
    make_single_asset_factor_data,
    summarize_factor,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "results" / f"group_a_plus_factor_lens_{datetime.now().strftime('%Y%m%d')}.json"


def resolve_latest_advisory_panel() -> Path:
    pipeline_files = sorted(
        (PROJECT_ROOT / "results").glob("ncf_daily_pipeline_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for pipeline_file in pipeline_files:
        payload = json.loads(pipeline_file.read_text(encoding="utf-8"))
        candidate = payload.get("outputs", {}).get("advisory_panel")
        if candidate:
            path = Path(candidate)
            if path.exists():
                return path

    candidates = sorted(
        (PROJECT_ROOT / "results").glob("ncf_advisory_panel_latest_*.csv"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if candidates:
        return candidates[0]
    raise FileNotFoundError("No ncf_advisory_panel_latest_*.csv found under results/")


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


def build_factor_series(advisory: pd.DataFrame) -> dict[str, pd.Series]:
    factors: dict[str, pd.Series] = {}
    if "market_probability_up" in advisory:
        market_prob = advisory["market_probability_up"].astype(float)
        factors["ncf_market_probability_up"] = market_prob
        if "agreement_score" in advisory:
            agreement = advisory["agreement_score"].astype(float)
            factors["ncf_signed_market_score"] = (market_prob - 0.5) * 2.0 * agreement
    if "dynamic_00631l_prob_up" in advisory:
        factors["ncf_00631l_prob_up"] = advisory["dynamic_00631l_prob_up"].astype(float)
    if "dynamic_00632r_prob_up" in advisory:
        factors["ncf_00632r_inverse_market_up"] = 1.0 - advisory["dynamic_00632r_prob_up"].astype(float)
    if {"dynamic_00631l_prob_up", "dynamic_00632r_prob_up"}.issubset(advisory.columns):
        factors["ncf_cross_ticker_market_up"] = (
            advisory["dynamic_00631l_prob_up"].astype(float)
            + (1.0 - advisory["dynamic_00632r_prob_up"].astype(float))
        ) / 2.0
    return {name: series.dropna() for name, series in factors.items()}


def build_event_masks(advisory: pd.DataFrame) -> dict[str, pd.Series]:
    masks: dict[str, pd.Series] = {}
    if {"market_direction", "agreement_score"}.issubset(advisory.columns):
        agreement = advisory["agreement_score"].astype(float)
        masks["high_agreement_bullish"] = (advisory["market_direction"] == "UP") & (agreement >= 0.65)
        masks["high_agreement_bearish"] = (advisory["market_direction"] == "DOWN") & (agreement >= 0.65)
    if "conflict_flag" in advisory:
        masks["conflict_flag"] = advisory["conflict_flag"].astype(bool)
    return masks


def evaluate_factor_series(
    factors: dict[str, pd.Series],
    price: pd.Series,
    *,
    asset: str,
    horizons: tuple[int, ...],
    quantiles: int,
    rolling_window: int,
    decay_max_lag: int = 20,
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for name, factor in factors.items():
        factor_data = make_single_asset_factor_data(
            factor,
            price,
            asset=asset,
            horizons=horizons,
            quantiles=quantiles,
        )
        summary = summarize_factor(factor_data, rolling_window=rolling_window)
        summary["ic_decay"] = ic_decay(factor, price, max_lag=decay_max_lag)
        results[name] = summary
    return results


def evaluate_events(
    events: dict[str, pd.Series],
    price: pd.Series,
    *,
    horizons: tuple[int, ...],
) -> dict[str, Any]:
    return {
        name: event_study_forward_returns(mask, price, horizons=horizons)
        for name, mask in events.items()
    }


def parse_horizons(value: str) -> tuple[int, ...]:
    horizons = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    if not horizons:
        raise ValueError("At least one horizon is required")
    return horizons


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--advisory-panel", default=None)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--asset", default="0050.TW")
    parser.add_argument("--horizons", default="1,5,20")
    parser.add_argument("--quantiles", type=int, default=5)
    parser.add_argument("--rolling-window", type=int, default=63)
    parser.add_argument("--decay-max-lag", type=int, default=20)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    advisory_path = Path(args.advisory_panel) if args.advisory_panel else resolve_latest_advisory_panel()
    if not advisory_path.is_absolute():
        advisory_path = PROJECT_ROOT / advisory_path
    advisory = load_advisory(advisory_path)
    horizons = parse_horizons(args.horizons)
    end_date = advisory.index.max() + timedelta(days=max(horizons) * 3)
    prices = load_close_prices(
        Path(args.db),
        [args.asset],
        advisory.index.min().strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d"),
    )
    price = prices[args.asset].dropna()
    factors = build_factor_series(advisory)
    events = build_event_masks(advisory)
    factor_results = evaluate_factor_series(
        factors,
        price,
        asset=args.asset,
        horizons=horizons,
        quantiles=int(args.quantiles),
        rolling_window=int(args.rolling_window),
        decay_max_lag=int(args.decay_max_lag),
    )
    event_results = evaluate_events(events, price, horizons=horizons)
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "method_note": (
            "Lightweight Alphalens-style diagnostics. IC is Spearman correlation "
            "between advisory factor values and subsequent asset forward returns."
        ),
        "advisory_panel": str(advisory_path),
        "db": str(Path(args.db)),
        "asset": args.asset,
        "window": {
            "start": str(advisory.index.min().date()),
            "end": str(advisory.index.max().date()),
            "rows": int(len(advisory)),
        },
        "horizons": list(horizons),
        "decay_max_lag": int(args.decay_max_lag),
        "factors": factor_results,
        "events": event_results,
    }

    output = Path(args.output)
    if not output.is_absolute():
        output = PROJECT_ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Saved: {output}")
    print("Factor IC summary:")
    for name, result in factor_results.items():
        ic = ", ".join(f"{key}={value:.4f}" for key, value in result["ic"].items() if value is not None)
        icir = ", ".join(f"{key}={value:.3f}" for key, value in result.get("ic_ir", {}).items() if value is not None)
        spread = ", ".join(
            f"{key}={value:.4%}" for key, value in result["quantile_spread"].items() if value is not None
        )
        gate = result.get("gate", {})
        gate_str = "PASS" if gate.get("passed") else "FAIL"
        print(f"  {name}: IC[{ic}] ICIR[{icir}] spread[{spread}] gate={gate_str}")
    print("Event summary:")
    for name, result in event_results.items():
        print(f"  {name}: events={result['event_count']}")


if __name__ == "__main__":
    main()
