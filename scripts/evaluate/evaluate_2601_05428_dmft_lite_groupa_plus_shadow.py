#!/usr/bin/env python3
"""DMFT-lite shadow test for arXiv:2601.05428v1 and GroupA+.

Research-only evaluator. It does not modify latest strategy, golden1_0531,
live signals, execution plans, or orders.
"""

from __future__ import annotations

import argparse
import json
import math
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

from backtest_group_a_plus_switch_policy import DB_PATH, _metrics  # noqa: E402

GROUPA_TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO")
DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "results/2601_05428_dmft_lite_groupa_plus_shadow.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/2601_05428_dmft_lite_groupa_plus_shadow.md"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _parse_tickers(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _load_ohlcv(db_path: Path, tickers: tuple[str, ...], start: str, end: str) -> pd.DataFrame:
    placeholders = ", ".join(["?"] * len(tickers))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            f"""
            SELECT dt, ticker, close, volume
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
    rows["dt"] = pd.to_datetime(rows["dt"]).dt.normalize()
    close = rows.pivot(index="dt", columns="ticker", values="close").sort_index()
    volume = rows.pivot(index="dt", columns="ticker", values="volume").sort_index()
    common = close.dropna(subset=list(tickers)).index.intersection(volume.dropna(subset=list(tickers)).index)
    close = close.reindex(common).astype(float)
    volume = volume.reindex(common).astype(float)
    return pd.concat({"close": close, "volume": volume}, axis=1)


def _rebalance_dates(index: pd.DatetimeIndex, frequency: str) -> pd.DatetimeIndex:
    frame = pd.DataFrame(index=index)
    if frequency == "monthly":
        groups = frame.groupby([frame.index.year, frame.index.month])
    elif frequency == "quarterly":
        groups = frame.groupby([frame.index.year, frame.index.quarter])
    elif frequency == "semiannual":
        groups = frame.groupby([frame.index.year, ((frame.index.month - 1) // 6)])
    else:
        raise ValueError(f"Unsupported rebalance frequency: {frequency}")
    return pd.DatetimeIndex([group.index[0] for _, group in groups])


def _zscore(values: pd.Series) -> pd.Series:
    values = pd.to_numeric(values, errors="coerce")
    std = float(values.std(ddof=0))
    if not math.isfinite(std) or std <= 1e-12:
        return pd.Series(0.0, index=values.index)
    return (values - float(values.mean())) / std


def _normalize(weights: dict[str, float], tickers: tuple[str, ...]) -> dict[str, float]:
    clipped = {ticker: max(float(weights.get(ticker, 0.0) or 0.0), 0.0) for ticker in tickers}
    cash = max(float(weights.get("cash", 0.0) or 0.0), 0.0)
    total = sum(clipped.values()) + cash
    if total <= 0:
        return {**{ticker: 0.0 for ticker in tickers}, "cash": 1.0}
    return {**{ticker: value / total for ticker, value in clipped.items()}, "cash": cash / total}


def _build_weights(
    panel: pd.DataFrame,
    *,
    tickers: tuple[str, ...],
    frequency: str,
    min_history: int,
    adv_lookback: int,
    min_adv: float,
    momentum_lookback: int,
    momentum_skip: int,
    vol_lookback: int,
    drawdown_lookback: int,
    tilt_strength: float,
    multiplier_min: float,
    multiplier_max: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    close = panel["close"][list(tickers)]
    volume = panel["volume"][list(tickers)]
    dollar_volume = close * volume
    adv = dollar_volume.rolling(adv_lookback, min_periods=max(5, adv_lookback // 2)).mean()
    returns = close.pct_change()
    volatility = returns.rolling(vol_lookback, min_periods=max(20, vol_lookback // 2)).std()
    peak = close.rolling(drawdown_lookback, min_periods=max(20, drawdown_lookback // 2)).max()
    drawdown = close / peak - 1.0
    mom = close.shift(momentum_skip) / close.shift(momentum_skip + momentum_lookback) - 1.0
    available_history = close.notna().cumsum()
    rebalance_dates = _rebalance_dates(close.index, frequency)

    weights_by_date: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for dt in rebalance_dates:
        pos = close.index.get_loc(dt)
        signal_pos = max(int(pos) - 1, 0)
        signal_dt = close.index[signal_pos]
        eligible = [
            ticker
            for ticker in tickers
            if available_history.loc[signal_dt, ticker] >= min_history
            and float(adv.loc[signal_dt, ticker] or 0.0) >= min_adv
            and math.isfinite(float(mom.loc[signal_dt, ticker] or float("nan")))
            and math.isfinite(float(volatility.loc[signal_dt, ticker] or float("nan")))
        ]
        if not eligible:
            weights_by_date.append({"date": dt, **{ticker: 0.0 for ticker in tickers}, "cash": 1.0})
            diagnostics.append({"date": dt, "signal_date": signal_dt, "eligible_count": 0, "eligible": []})
            continue
        base = 1.0 / len(eligible)
        z_mom = _zscore(mom.loc[signal_dt, eligible])
        z_inv_vol = _zscore(-volatility.loc[signal_dt, eligible])
        z_resilience = _zscore(drawdown.loc[signal_dt, eligible])
        composite = (z_mom + z_inv_vol + z_resilience) / 3.0
        raw = {}
        multipliers = {}
        for ticker in eligible:
            multiplier = float(np.clip(1.0 + tilt_strength * float(composite.loc[ticker]), multiplier_min, multiplier_max))
            multipliers[ticker] = multiplier
            raw[ticker] = base * multiplier
        total_raw = sum(raw.values())
        weights = {ticker: (raw.get(ticker, 0.0) / total_raw if total_raw > 0 else 0.0) for ticker in tickers}
        weights["cash"] = 0.0
        weights_by_date.append({"date": dt, **weights})
        diagnostics.append(
            {
                "date": dt,
                "signal_date": signal_dt,
                "eligible_count": len(eligible),
                "eligible": eligible,
                "multipliers": multipliers,
            }
        )
    weight_frame = pd.DataFrame(weights_by_date).set_index("date").sort_index()
    diagnostic_frame = pd.DataFrame(diagnostics).set_index("date").sort_index()
    return weight_frame, diagnostic_frame


def _constant_equal_weights(index: pd.DatetimeIndex, tickers: tuple[str, ...], frequency: str) -> pd.DataFrame:
    dates = _rebalance_dates(index, frequency)
    rows = []
    for dt in dates:
        rows.append({"date": dt, **{ticker: 1.0 / len(tickers) for ticker in tickers}, "cash": 0.0})
    return pd.DataFrame(rows).set_index("date").sort_index()


def _simulate(
    close: pd.DataFrame,
    weights: pd.DataFrame,
    *,
    tickers: tuple[str, ...],
    initial_value: float,
    transaction_cost_bps: float,
) -> tuple[pd.Series, dict[str, float]]:
    weights = weights.sort_index()
    shares = {ticker: 0.0 for ticker in tickers}
    cash = float(initial_value)
    values = []
    total_cost = 0.0
    total_turnover = 0.0
    rebalance_count = 0
    active_weights = None
    cost_rate = float(transaction_cost_bps) / 10_000.0
    for dt, price_row in close.iterrows():
        gross_value = cash + sum(shares[ticker] * float(price_row[ticker]) for ticker in tickers)
        if dt in weights.index:
            target = _normalize(weights.loc[dt].to_dict(), tickers)
            current_values = {ticker: shares[ticker] * float(price_row[ticker]) for ticker in tickers}
            current_values["cash"] = cash
            target_values = {ticker: gross_value * target.get(ticker, 0.0) for ticker in (*tickers, "cash")}
            turnover = sum(abs(target_values[ticker] - current_values.get(ticker, 0.0)) for ticker in tickers)
            cost = turnover * cost_rate
            net_value = max(gross_value - cost, 0.0)
            shares = {ticker: net_value * target.get(ticker, 0.0) / max(float(price_row[ticker]), 1e-12) for ticker in tickers}
            cash = net_value * target.get("cash", 0.0)
            gross_value = net_value
            total_cost += cost
            total_turnover += turnover
            rebalance_count += 1
            active_weights = target
        values.append(gross_value)
    return pd.Series(values, index=close.index, dtype=float), {
        "transaction_cost": float(total_cost),
        "turnover_value": float(total_turnover),
        "rebalance_count": int(rebalance_count),
        "last_weights": active_weights or {},
    }


def _weights_for_eval_window(weights: pd.DataFrame, eval_index: pd.DatetimeIndex) -> pd.DataFrame:
    prior = weights.loc[weights.index <= eval_index[0]]
    rows = weights.loc[weights.index >= eval_index[0]].copy()
    if len(prior):
        start_row = prior.iloc[[-1]].copy()
        start_row.index = pd.DatetimeIndex([eval_index[0]])
        rows = pd.concat([start_row, rows.loc[rows.index > eval_index[0]]])
    elif len(rows) == 0 or rows.index[0] != eval_index[0]:
        rows = pd.concat([weights.iloc[[0]].set_axis(pd.DatetimeIndex([eval_index[0]])), rows])
    return rows[~rows.index.duplicated(keep="last")].sort_index()


def _run_variant(panel: pd.DataFrame, args: argparse.Namespace, frequency: str, tilt_strength: float) -> dict[str, Any]:
    tickers = _parse_tickers(args.tickers)
    close_full = panel["close"][list(tickers)]
    eval_start = pd.Timestamp(args.start)
    eval_end = pd.Timestamp(args.end)
    close = close_full.loc[(close_full.index >= eval_start) & (close_full.index <= eval_end)]
    dmft_weights_full, diagnostics_full = _build_weights(
        panel,
        tickers=tickers,
        frequency=frequency,
        min_history=args.min_history,
        adv_lookback=args.adv_lookback,
        min_adv=args.min_adv,
        momentum_lookback=args.momentum_lookback,
        momentum_skip=args.momentum_skip,
        vol_lookback=args.vol_lookback,
        drawdown_lookback=args.drawdown_lookback,
        tilt_strength=tilt_strength,
        multiplier_min=args.multiplier_min,
        multiplier_max=args.multiplier_max,
    )
    dmft_weights = _weights_for_eval_window(dmft_weights_full, close.index)
    equal_weights = _constant_equal_weights(close_full.index, tickers, frequency)
    equal_weights = _weights_for_eval_window(equal_weights, close.index)
    dmft_curve, dmft_cost = _simulate(
        close,
        dmft_weights,
        tickers=tickers,
        initial_value=args.initial_value,
        transaction_cost_bps=args.transaction_cost_bps,
    )
    equal_curve, equal_cost = _simulate(
        close,
        equal_weights,
        tickers=tickers,
        initial_value=args.initial_value,
        transaction_cost_bps=args.transaction_cost_bps,
    )
    dmft_metrics = _metrics(dmft_curve, args.initial_value)
    equal_metrics = _metrics(equal_curve, args.initial_value)
    diagnostics = diagnostics_full.loc[(diagnostics_full.index >= eval_start) & (diagnostics_full.index <= eval_end)]
    eligible_counts = diagnostics["eligible_count"].value_counts().sort_index().to_dict()
    return {
        "frequency": frequency,
        "tilt_strength": float(tilt_strength),
        "dmft_lite": {"metrics": dmft_metrics, "costs": dmft_cost},
        "equal_weight": {"metrics": equal_metrics, "costs": equal_cost},
        "deltas_vs_equal_weight": {
            "final_value": float(dmft_metrics["final_value"] - equal_metrics["final_value"]),
            "sharpe_ratio": float(dmft_metrics["sharpe_ratio"] - equal_metrics["sharpe_ratio"]),
            "max_drawdown": float(dmft_metrics["max_drawdown"] - equal_metrics["max_drawdown"]),
            "turnover_value": float(dmft_cost["turnover_value"] - equal_cost["turnover_value"]),
        },
        "eligibility": {
            "eligible_count_distribution": {str(int(k)): int(v) for k, v in eligible_counts.items()},
            "min_eligible_count": int(diagnostics["eligible_count"].min()) if len(diagnostics) else 0,
            "median_eligible_count": float(diagnostics["eligible_count"].median()) if len(diagnostics) else 0.0,
        },
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    tickers = _parse_tickers(args.tickers)
    load_start = args.warmup_start or args.start
    panel = _load_ohlcv(_resolve(args.db), tickers, load_start, args.end)
    close = panel["close"][list(tickers)]
    eval_close = close.loc[(close.index >= pd.Timestamp(args.start)) & (close.index <= pd.Timestamp(args.end))]
    variants = []
    for frequency in args.frequencies.split(","):
        frequency = frequency.strip()
        if not frequency:
            continue
        for tilt in [float(item.strip()) for item in args.tilt_strengths.split(",") if item.strip()]:
            variants.append(_run_variant(panel, args, frequency, tilt))
    promotion_ready = any(
        item["deltas_vs_equal_weight"]["final_value"] > 0
        and item["deltas_vs_equal_weight"]["sharpe_ratio"] > 0
        and item["deltas_vs_equal_weight"]["max_drawdown"] >= 0
        and item["eligibility"]["min_eligible_count"] >= 3
        for item in variants
    )
    return {
        "schema_version": 1,
        "report_type": "2601_05428_dmft_lite_groupa_plus_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": "arXiv:2601.05428v1 Dynamic Inclusion and Bounded Multi-Factor Tilts for Robust Portfolio Construction",
        "policy": "research_only_no_groupa_plus_live_change",
        "load_window": {"start": str(close.index[0].date()), "end": str(close.index[-1].date()), "rows": int(len(close))},
        "window": {"start": str(eval_close.index[0].date()), "end": str(eval_close.index[-1].date()), "rows": int(len(eval_close))},
        "tickers": list(tickers),
        "local_method": {
            "name": "DMFT-lite",
            "factors": ["126d momentum skipping 21d", "inverse 63d realized volatility", "126d drawdown resilience"],
            "eligibility": {
                "min_history": int(args.min_history),
                "min_adv": float(args.min_adv),
                "adv_lookback": int(args.adv_lookback),
            },
            "bounds": {"multiplier_min": float(args.multiplier_min), "multiplier_max": float(args.multiplier_max)},
            "transaction_cost_bps": float(args.transaction_cost_bps),
        },
        "variants": variants,
        "decision_for_groupa_plus": {
            "changes_latest_strategy": False,
            "changes_golden1_0531": False,
            "creates_orders": False,
            "recommended_use": "research_only",
            "promotion_ready": bool(promotion_ready),
            "reason": (
                "Only consider promotion if DMFT-lite improves final value, Sharpe, and drawdown with at least 3 eligible assets. "
                "The paper itself is designed for larger cross-sectional universes; GroupA+'s 4-ETF universe is structurally small."
            ),
        },
    }


def _write_md(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# 2601.05428v1 DMFT-lite GroupA+ Shadow",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Policy: `{report['policy']}`",
        f"- Window: `{report['window']}`",
        f"- Tickers: `{', '.join(report['tickers'])}`",
        "",
        "## Variant Results",
        "",
        "| Frequency | Tilt | Final Delta | Sharpe Delta | MDD Delta | DMFT Final | EW Final | Min Eligible | Promotion Gate |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in report["variants"]:
        delta = item["deltas_vs_equal_weight"]
        dmft = item["dmft_lite"]["metrics"]
        equal = item["equal_weight"]["metrics"]
        gate = (
            delta["final_value"] > 0
            and delta["sharpe_ratio"] > 0
            and delta["max_drawdown"] >= 0
            and item["eligibility"]["min_eligible_count"] >= 3
        )
        lines.append(
            f"| {item['frequency']} | {item['tilt_strength']:.2f} | {delta['final_value']:.2f} | "
            f"{delta['sharpe_ratio']:.4f} | {delta['max_drawdown']:.4f} | "
            f"{dmft['final_value']:.2f} | {equal['final_value']:.2f} | "
            f"{item['eligibility']['min_eligible_count']} | {gate} |"
        )
    decision = report["decision_for_groupa_plus"]
    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"- Promotion ready: `{decision['promotion_ready']}`",
            f"- Recommended use: `{decision['recommended_use']}`",
            "- No latest strategy, golden1_0531, live signal, execution plan, or order file was changed.",
            "",
            "## Interpretation",
            "",
            decision["reason"],
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--tickers", default=",".join(GROUPA_TICKERS))
    parser.add_argument("--start", default="2020-01-02")
    parser.add_argument("--end", default="2026-08-13")
    parser.add_argument("--warmup-start", default="2020-01-02")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--frequencies", default="monthly,quarterly,semiannual")
    parser.add_argument("--tilt-strengths", default="0.10,0.20,0.35")
    parser.add_argument("--min-history", type=int, default=252)
    parser.add_argument("--adv-lookback", type=int, default=20)
    parser.add_argument("--min-adv", type=float, default=0.0)
    parser.add_argument("--momentum-lookback", type=int, default=126)
    parser.add_argument("--momentum-skip", type=int, default=21)
    parser.add_argument("--vol-lookback", type=int, default=63)
    parser.add_argument("--drawdown-lookback", type=int, default=126)
    parser.add_argument("--multiplier-min", type=float, default=0.70)
    parser.add_argument("--multiplier-max", type=float, default=1.30)
    parser.add_argument("--transaction-cost-bps", type=float, default=10.0)
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(args)
    output_json = _resolve(args.output_json)
    output_md = _resolve(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_md(report, output_md)
    print(
        json.dumps(
            {
                "promotion_ready": report["decision_for_groupa_plus"]["promotion_ready"],
                "output_json": str(output_json),
                "output_md": str(output_md),
                "window": report["window"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
