#!/usr/bin/env python3
"""Backtest AEGIS-lite as a research-only shadow overlay for GroupA+.

The baseline is the latest strategy's historical target weights.  The shadow
does not change the active strategy; it only tests whether the AEGIS-inspired
VAM gate and constrained Sortino reference would have improved risk metrics.
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

from backtest_group_a_plus_policy_signal import TICKERS, _normalize
from backtest_group_a_plus_switch_policy import _metrics
from group_a_plus.runners.latest import run_latest
from scripts.evaluate.build_group_a_plus_aegis_lite_advisory import (
    TARGET_ASSETS,
    build_vam_gate,
    calculate_vam,
    sortino_reference_weights,
)


DEFAULT_DB = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "results/group_a_plus_aegis_lite_shadow_backtest_latest.json"
DEFAULT_OUTPUT_CSV = PROJECT_ROOT / "results/group_a_plus_aegis_lite_shadow_backtest_curve_latest.csv"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/aegis_lite_shadow_backtest.md"
COMMISSION_RATE = 0.001425
SLIPPAGE_RATE = 0.0005
EQUITY_ETF_SELL_TAX = 0.001
BOND_ETFS = {"00679B.TWO"}
WEIGHT_COLUMNS = {
    "0050.TW": "target_weight_0050",
    "00631L.TW": "target_weight_00631L",
    "00632R.TW": "target_weight_00632R",
    "00679B.TWO": "target_weight_00679B",
    "cash": "target_weight_cash",
}


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _load_prices(db_path: Path, start: str, end: str) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT ticker, dt, close
            FROM ohlcv
            WHERE ticker IN (SELECT * FROM UNNEST(?)) AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [list(TICKERS), start, end],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        raise ValueError(f"no OHLCV rows found for {start} ~ {end}")
    rows["dt"] = pd.to_datetime(rows["dt"]).dt.normalize()
    prices = rows.pivot(index="dt", columns="ticker", values="close").sort_index()
    return prices.reindex(columns=list(TICKERS)).ffill().dropna(how="any")


def _weights_from_latest_frame(latest_frame: pd.DataFrame, latest_report: dict[str, Any]) -> pd.DataFrame:
    regime_weights_raw = latest_report.get("base_weights") or latest_report.get("weights") or {}
    if not regime_weights_raw:
        raise ValueError("latest report has no base_weights map")
    regime_weights = {str(k): _normalize(dict(v or {})) for k, v in regime_weights_raw.items()}
    rows: list[dict[str, Any]] = []
    for dt, row in latest_frame.iterrows():
        regime = str(row.get("execution_regime"))
        weights = regime_weights.get(regime)
        if weights is None:
            raise ValueError(f"missing weights for execution_regime={regime}")
        rows.append({"date": pd.Timestamp(dt).normalize(), "execution_regime": regime, **weights})
    out = pd.DataFrame(rows).set_index("date").sort_index()
    for asset in TARGET_ASSETS:
        if asset not in out.columns:
            out[asset] = 0.0
    return out[list(TARGET_ASSETS) + ["execution_regime"]]


def _clean_weights(raw: dict[str, float]) -> dict[str, float]:
    weights = {asset: max(float(raw.get(asset, 0.0)), 0.0) for asset in TARGET_ASSETS}
    total = sum(weights.values())
    if total <= 1e-12:
        return {"0050.TW": 0.0, "00631L.TW": 0.0, "00632R.TW": 0.0, "00679B.TWO": 0.0, "cash": 1.0}
    return {asset: value / total for asset, value in weights.items()}


def build_shadow_weights(
    prices: pd.DataFrame,
    baseline_weights: pd.DataFrame,
    *,
    enable_vam: bool = True,
    enable_sortino: bool = True,
    vam_lookback_days: int,
    sortino_lookback_days: int,
    max_00631l_to_0050_vol_ratio: float,
    max_abs_deviation: float,
    max_single_asset_weight: float,
    turnover_penalty: float,
    sortino_reopt_frequency: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply AEGIS-lite rules to historical latest-strategy target weights.

    Codex 2026-08-13: this is shadow-only; the returned weights are never
    written to active GroupA+ strategy artifacts.
    """
    aligned = baseline_weights.reindex(prices.index).ffill().dropna(how="any")
    shadow_rows: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    last_sortino_key: str | None = None
    last_reference: dict[str, float] | None = None
    sortino_updates = 0
    vam_blocks = 0
    for dt, row in aligned.iterrows():
        base = _clean_weights({asset: float(row.get(asset, 0.0)) for asset in TARGET_ASSETS})
        current_prices = prices.loc[:dt]
        if enable_vam:
            try:
                vam = calculate_vam(current_prices, as_of=str(dt.date()), lookback_days=vam_lookback_days)
                gate = build_vam_gate(vam, max_00631l_to_0050_vol_ratio=max_00631l_to_0050_vol_ratio)
            except Exception as exc:
                gate = {"allow_00631l_add": True, "status": "unavailable", "reasons": [str(exc)]}
        else:
            gate = {"allow_00631l_add": True, "status": "disabled", "reasons": []}

        weights = dict(base)
        if not bool(gate.get("allow_00631l_add", True)) and base.get("00631L.TW", 0.0) > 0.0:
            shifted = float(weights.get("00631L.TW", 0.0))
            weights["00631L.TW"] = 0.0
            weights["0050.TW"] = float(weights.get("0050.TW", 0.0)) + shifted
            vam_blocks += 1
            events.append(
                {
                    "date": str(dt.date()),
                    "event": "vam_blocks_00631l",
                    "blocked_weight": shifted,
                    "reasons": list(gate.get("reasons", [])),
                }
            )

        sortino_key = dt.strftime("%Y-%m") if sortino_reopt_frequency == "monthly" else str(dt.date())
        if enable_sortino and sortino_key != last_sortino_key:
            try:
                ref = sortino_reference_weights(
                    prices.loc[:dt],
                    weights,
                    as_of=str(dt.date()),
                    lookback_days=sortino_lookback_days,
                    max_abs_deviation=max_abs_deviation,
                    max_single_asset_weight=max_single_asset_weight,
                    turnover_penalty=turnover_penalty,
                )
                last_reference = _clean_weights(ref["reference_weights"])
                last_sortino_key = sortino_key
                sortino_updates += 1
            except Exception as exc:
                events.append({"date": str(dt.date()), "event": "sortino_unavailable", "reason": str(exc)})
                last_reference = weights
                last_sortino_key = sortino_key
        weights = _clean_weights((last_reference if enable_sortino else None) or weights)
        shadow_rows.append({"date": dt, **weights})
    shadow = pd.DataFrame(shadow_rows).set_index("date").sort_index()
    metadata = {
        "vam_block_days": int(vam_blocks),
        "sortino_updates": int(sortino_updates),
        "enable_vam": bool(enable_vam),
        "enable_sortino": bool(enable_sortino),
        "event_count": int(len(events)),
        "events_sample": events[:50],
    }
    return shadow, metadata


def _trade_cost(
    current_values: dict[str, float],
    target_values: dict[str, float],
    *,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> tuple[float, float]:
    cost = 0.0
    turnover = 0.0
    for ticker in TICKERS:
        trade = float(target_values.get(ticker, 0.0)) - float(current_values.get(ticker, 0.0))
        turnover += abs(trade)
        if trade > 0.0:
            cost += trade * (commission_rate + slippage_rate)
        elif trade < 0.0:
            sell_tax = 0.0 if ticker in BOND_ETFS else equity_etf_sell_tax
            cost += abs(trade) * (commission_rate + slippage_rate + sell_tax)
    return float(cost), float(turnover)


def simulate_weight_curve(
    prices: pd.DataFrame,
    weights: pd.DataFrame,
    *,
    initial_value: float,
    commission_rate: float = COMMISSION_RATE,
    slippage_rate: float = SLIPPAGE_RATE,
    equity_etf_sell_tax: float = EQUITY_ETF_SELL_TAX,
    rebalance_threshold: float = 1e-8,
) -> tuple[pd.Series, dict[str, float]]:
    weights = weights.reindex(prices.index).ffill().dropna(how="any")
    shares = {ticker: 0.0 for ticker in TICKERS}
    cash = float(initial_value)
    previous_weights: dict[str, float] | None = None
    values: list[float] = []
    total_cost = 0.0
    total_turnover = 0.0
    rebalance_count = 0
    for dt, price_row in prices.iterrows():
        if dt not in weights.index:
            continue
        gross_value = cash + sum(float(shares[ticker]) * float(price_row[ticker]) for ticker in TICKERS)
        target_weights = _clean_weights({asset: float(weights.loc[dt, asset]) for asset in TARGET_ASSETS})
        should_rebalance = previous_weights is None or any(
            abs(target_weights[asset] - previous_weights.get(asset, 0.0)) > rebalance_threshold
            for asset in TARGET_ASSETS
        )
        if should_rebalance:
            current_values = {ticker: float(shares[ticker]) * float(price_row[ticker]) for ticker in TICKERS}
            net_value = gross_value
            cost = 0.0
            turnover = 0.0
            for _ in range(3):
                target_values = {ticker: net_value * target_weights.get(ticker, 0.0) for ticker in TICKERS}
                cost, turnover = _trade_cost(
                    current_values,
                    target_values,
                    commission_rate=commission_rate,
                    slippage_rate=slippage_rate,
                    equity_etf_sell_tax=equity_etf_sell_tax,
                )
                net_value = max(gross_value - cost, 0.0)
            shares = {
                ticker: net_value * target_weights.get(ticker, 0.0) / max(float(price_row[ticker]), 1e-12)
                for ticker in TICKERS
            }
            cash = net_value * target_weights.get("cash", 0.0)
            gross_value = net_value
            total_cost += cost
            total_turnover += turnover
            rebalance_count += 1
            previous_weights = dict(target_weights)
        values.append(float(gross_value))
    return pd.Series(values, index=weights.index[: len(values)], dtype=float), {
        "transaction_cost": float(total_cost),
        "turnover_value": float(total_turnover),
        "rebalance_count": int(rebalance_count),
    }


def build_backtest_report(
    *,
    prices: pd.DataFrame,
    baseline_weights: pd.DataFrame,
    shadow_weights: pd.DataFrame,
    shadow_metadata: dict[str, Any],
    initial_value: float,
    latest_report: dict[str, Any],
    params: dict[str, Any],
) -> tuple[dict[str, Any], pd.DataFrame]:
    baseline_curve, baseline_exec = simulate_weight_curve(prices, baseline_weights, initial_value=initial_value)
    shadow_curve, shadow_exec = simulate_weight_curve(prices, shadow_weights, initial_value=initial_value)
    curves = pd.DataFrame({"baseline_latest": baseline_curve, "aegis_lite_shadow": shadow_curve}).dropna()
    baseline_metrics = _metrics(curves["baseline_latest"], initial_value)
    shadow_metrics = _metrics(curves["aegis_lite_shadow"], initial_value)
    metric_delta = {
        key: float(shadow_metrics[key] - baseline_metrics[key])
        for key in ("final_value", "annual_return", "sharpe_ratio", "sortino_ratio", "max_drawdown")
    }
    promotion_ready = bool(
        metric_delta["final_value"] > 0.0
        and metric_delta["sortino_ratio"] > 0.0
        and metric_delta["max_drawdown"] >= -0.01
    )
    report = {
        "schema_version": 1,
        "report_type": "group_a_plus_aegis_lite_shadow_backtest",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_no_active_weight_change",
        "codex_note": "Codex 2026-08-13: AEGIS-lite shadow backtest only; active latest strategy is unchanged.",
        "inputs": {
            "actual_window": {
                "start": str(curves.index[0].date()),
                "end": str(curves.index[-1].date()),
                "rows": int(len(curves)),
            },
            "initial_value": float(initial_value),
            "active_strategy_id": latest_report.get("active_strategy_id") or latest_report.get("strategy"),
            "params": params,
        },
        "execution": {
            "baseline_latest": baseline_exec,
            "aegis_lite_shadow": shadow_exec,
            "shadow_metadata": shadow_metadata,
        },
        "metrics": {
            "baseline_latest": baseline_metrics,
            "aegis_lite_shadow": shadow_metrics,
            "delta_shadow_minus_baseline": metric_delta,
        },
        "decision": {
            "changes_latest_strategy": False,
            "changes_golden1_0531": False,
            "creates_orders": False,
            "promotion_ready": promotion_ready,
            "recommended_use": "promotion_gate_input_only" if promotion_ready else "keep_research_only",
        },
    }
    return report, curves


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    delta = report["metrics"]["delta_shadow_minus_baseline"]
    base = report["metrics"]["baseline_latest"]
    shadow = report["metrics"]["aegis_lite_shadow"]
    lines = [
        "# GroupA+ AEGIS-lite Shadow Backtest",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Window: `{report['inputs']['actual_window']['start']}` ~ `{report['inputs']['actual_window']['end']}`",
        f"- Policy: `{report['policy']}`",
        f"- Promotion ready: `{report['decision']['promotion_ready']}`",
        "",
        "## Metrics",
        "",
        "| Metric | Baseline latest | AEGIS-lite shadow | Delta |",
        "|---|---:|---:|---:|",
        f"| final_value | {base['final_value']:.2f} | {shadow['final_value']:.2f} | {delta['final_value']:.2f} |",
        f"| annual_return | {base['annual_return']:.6f} | {shadow['annual_return']:.6f} | {delta['annual_return']:.6f} |",
        f"| sharpe_ratio | {base['sharpe_ratio']:.6f} | {shadow['sharpe_ratio']:.6f} | {delta['sharpe_ratio']:.6f} |",
        f"| sortino_ratio | {base['sortino_ratio']:.6f} | {shadow['sortino_ratio']:.6f} | {delta['sortino_ratio']:.6f} |",
        f"| max_drawdown | {base['max_drawdown']:.6f} | {shadow['max_drawdown']:.6f} | {delta['max_drawdown']:.6f} |",
        "",
        "## Shadow Activity",
        "",
        f"- VAM block days: `{report['execution']['shadow_metadata']['vam_block_days']}`",
        f"- Sortino updates: `{report['execution']['shadow_metadata']['sortino_updates']}`",
        f"- Baseline rebalances: `{report['execution']['baseline_latest']['rebalance_count']}`",
        f"- Shadow rebalances: `{report['execution']['aegis_lite_shadow']['rebalance_count']}`",
        "",
        "Codex 2026-08-13: research-only output; no active strategy or golden1_0531 artifact is changed.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(report: dict[str, Any], curves: pd.DataFrame, *, output_json: Path, output_csv: Path, output_md: Path) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    curves.to_csv(output_csv, encoding="utf-8-sig")
    _write_markdown(report, output_md)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-08-13")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--vam-lookback-days", type=int, default=126)
    parser.add_argument("--sortino-lookback-days", type=int, default=63)
    parser.add_argument("--disable-vam", action="store_true")
    parser.add_argument("--disable-sortino", action="store_true")
    parser.add_argument("--max-00631l-to-0050-vol-ratio", type=float, default=2.25)
    parser.add_argument("--max-abs-deviation", type=float, default=0.15)
    parser.add_argument("--max-single-asset-weight", type=float, default=0.85)
    parser.add_argument("--turnover-penalty", type=float, default=0.02)
    parser.add_argument("--sortino-reopt-frequency", choices=["daily", "monthly"], default="monthly")
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT_CSV))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = _resolve(args.db)
    latest_report, latest_frame = run_latest(args.start, args.end, args.initial_value, db_path)
    prices = _load_prices(db_path, args.start, args.end)
    baseline_weights = _weights_from_latest_frame(latest_frame, latest_report).reindex(prices.index).ffill()
    params = {
        "enable_vam": not bool(args.disable_vam),
        "enable_sortino": not bool(args.disable_sortino),
        "vam_lookback_days": int(args.vam_lookback_days),
        "sortino_lookback_days": int(args.sortino_lookback_days),
        "max_00631l_to_0050_vol_ratio": float(args.max_00631l_to_0050_vol_ratio),
        "max_abs_deviation": float(args.max_abs_deviation),
        "max_single_asset_weight": float(args.max_single_asset_weight),
        "turnover_penalty": float(args.turnover_penalty),
        "sortino_reopt_frequency": args.sortino_reopt_frequency,
    }
    shadow_weights, shadow_metadata = build_shadow_weights(
        prices,
        baseline_weights,
        enable_vam=not bool(args.disable_vam),
        enable_sortino=not bool(args.disable_sortino),
        vam_lookback_days=args.vam_lookback_days,
        sortino_lookback_days=args.sortino_lookback_days,
        max_00631l_to_0050_vol_ratio=args.max_00631l_to_0050_vol_ratio,
        max_abs_deviation=args.max_abs_deviation,
        max_single_asset_weight=args.max_single_asset_weight,
        turnover_penalty=args.turnover_penalty,
        sortino_reopt_frequency=args.sortino_reopt_frequency,
    )
    report, curves = build_backtest_report(
        prices=prices,
        baseline_weights=baseline_weights,
        shadow_weights=shadow_weights,
        shadow_metadata=shadow_metadata,
        initial_value=args.initial_value,
        latest_report=latest_report,
        params=params,
    )
    report["inputs"]["db"] = str(db_path)
    write_outputs(
        report,
        curves,
        output_json=_resolve(args.output_json),
        output_csv=_resolve(args.output_csv),
        output_md=_resolve(args.output_md),
    )
    print(
        json.dumps(
            {
                "promotion_ready": report["decision"]["promotion_ready"],
                "final_value_delta": report["metrics"]["delta_shadow_minus_baseline"]["final_value"],
                "sortino_delta": report["metrics"]["delta_shadow_minus_baseline"]["sortino_ratio"],
                "max_drawdown_delta": report["metrics"]["delta_shadow_minus_baseline"]["max_drawdown"],
                "output_json": str(_resolve(args.output_json)),
                "output_md": str(_resolve(args.output_md)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
