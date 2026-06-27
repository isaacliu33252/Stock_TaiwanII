#!/usr/bin/env python3
"""Sweep Group A 00632R caps on the TWII proxy 2008 stress path."""

from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from stable_baselines3 import PPO

from backtest_group_a_twii_proxy_2008 import (
    DEFAULT_END,
    DEFAULT_PAYLOAD,
    DEFAULT_START,
    _benchmark_payload,
    _resolve_group_a_model_path,
)
from generate_dual_group_signal import _env_kwargs_from_payload
from train_dual_group_2024_2026 import (
    _align_panel,
    _backtest_group,
    attach_group_a_margin_shared_features_db_first,
    attach_group_a_market_margin_shared_features_db_first,
    attach_institutional_features_db_first,
    attach_margin_features_db_first,
    payload_uses_group_a_institutional_features,
    payload_uses_group_a_margin_features,
    payload_uses_group_a_margin_shared_features,
    payload_uses_group_a_market_margin_shared_features,
)
from twii_proxy_utils import DEFAULT_TWII_MARKET_CACHE, build_group_a_twii_proxy_data


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_twii_proxy_2008_inverse_sweep.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--payload", default=str(DEFAULT_PAYLOAD))
    parser.add_argument("--model", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def _metrics_row(name: str, result: dict[str, Any]) -> dict[str, Any]:
    metrics = result["rl_metrics"]
    return {
        "variant": name,
        "final_value": float(result["final_value"]),
        "total_return": float(metrics["total_return"]),
        "annual_return": float(metrics["annual_return"]),
        "sharpe": float(metrics["sharpe"]),
        "max_drawdown": float(metrics["max_drawdown"]),
        "volatility": float(metrics["volatility"]),
        "num_trades": int(result["num_trades"]),
        "fees_paid_estimate": float(result["fees_paid_estimate"]),
        "dca_total_contributions": float(result["dca_total_contributions"]),
        "total_invested_capital": float(result["total_invested_capital"]),
        "net_profit": float(result["net_profit"]),
        "contribution_return": float(result["contribution_return"]),
        "inverse_nonzero_pva_events": sum(
            1
            for item in result.get("pva_sigmoid_history", [])
            if float(item.get("target_weights", {}).get("00632R.TW", 0.0)) > 1e-12
        ),
        "inverse_max_pva_weight": max(
            [
                float(item.get("target_weights", {}).get("00632R.TW", 0.0))
                for item in result.get("pva_sigmoid_history", [])
            ]
            or [0.0]
        ),
    }


def _prepare_stock_data(payload: dict[str, Any], tickers: list[str], start: str, end: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    stock_data, market = build_group_a_twii_proxy_data(start, end)
    if payload_uses_group_a_institutional_features(payload):
        stock_data = attach_institutional_features_db_first(stock_data, tickers, start, end)
    if payload_uses_group_a_margin_features(payload):
        stock_data = attach_margin_features_db_first(stock_data, tickers, start, end)
    if payload_uses_group_a_margin_shared_features(payload):
        stock_data = attach_group_a_margin_shared_features_db_first(stock_data, tickers, start, end)
    if payload_uses_group_a_market_margin_shared_features(payload):
        stock_data = attach_group_a_market_margin_shared_features_db_first(stock_data, tickers, start, end)
    return stock_data, market


def _payload_with_inverse_cap(payload: dict[str, Any], cap: float | None) -> dict[str, Any]:
    variant = copy.deepcopy(payload)
    if cap is not None:
        variant.setdefault("group_a_exposure_caps", {})["00632R.TW"] = float(cap)
    return variant


def main() -> None:
    args = _parse_args()
    payload_path = Path(args.payload)
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    model_path = _resolve_group_a_model_path(payload, args.model)
    tickers = list((payload.get("group_a", {}) or {}).get("tickers", ["0050.TW", "00631L.TW", "00632R.TW"]))
    initial_cash = float(payload.get("initial_cash_per_group", 1_000_000.0))
    stock_data, _ = _prepare_stock_data(payload, tickers, args.start, args.end)
    model = PPO.load(str(model_path))

    variants = [
        ("baseline_payload", None),
        ("inverse_cap_0_to_0050", 0.0),
        ("inverse_cap_005_to_0050", 0.05),
        ("inverse_cap_010_to_0050", 0.10),
        ("inverse_cap_020_to_0050", 0.20),
    ]
    rows: list[dict[str, Any]] = []
    detailed: dict[str, Any] = {}
    curves: dict[str, pd.Series] = {}
    for name, cap in variants:
        variant_payload = _payload_with_inverse_cap(payload, cap)
        env_kwargs, shared_feature_cols = _env_kwargs_from_payload(variant_payload, "group_a")
        result = _backtest_group(
            model,
            stock_data,
            tickers,
            f"GroupA_TWIIProxy2008_{name}",
            shared_feature_cols=shared_feature_cols,
            backtest_start=args.start,
            backtest_end=args.end,
            initial_cash=initial_cash,
            env_kwargs=env_kwargs,
        )
        row = _metrics_row(name, result)
        row["inverse_cap"] = cap
        rows.append(row)
        detailed[name] = {"inverse_cap": cap, "env_kwargs": env_kwargs, "result": result}
        panel_dates = pd.to_datetime(
            _align_panel(stock_data, tickers, args.start, args.end, shared_feature_cols=shared_feature_cols)["date"]
        )
        curves[name] = pd.Series(result["equity_curve"], index=panel_dates.iloc[: len(result["equity_curve"])], dtype=float)
        print(
            f"{name}: final={row['final_value']:.2f}, sharpe={row['sharpe']:.4f}, "
            f"mdd={row['max_drawdown']:.4%}, inv_events={row['inverse_nonzero_pva_events']}, "
            f"inv_max={row['inverse_max_pva_weight']:.2%}",
            flush=True,
        )

    baseline = next(row for row in rows if row["variant"] == "baseline_payload")
    for row in rows:
        row["delta_final_value"] = row["final_value"] - baseline["final_value"]
        row["delta_sharpe"] = row["sharpe"] - baseline["sharpe"]
        row["delta_max_drawdown"] = row["max_drawdown"] - baseline["max_drawdown"]
        row["delta_contribution_return"] = row["contribution_return"] - baseline["contribution_return"]

    panel = _align_panel(stock_data, tickers, args.start, args.end, shared_feature_cols=_env_kwargs_from_payload(payload, "group_a")[1])
    benchmarks = _benchmark_payload(panel, tickers, initial_cash)
    output = Path(args.output)
    if not output.is_absolute():
        output = PROJECT_ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    csv_path = output.with_suffix(".csv")
    curve_path = output.with_name(output.stem + "_curve.csv")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    curve_frame = pd.DataFrame(curves)
    curve_frame.index.name = "date"
    curve_frame.to_csv(curve_path, encoding="utf-8-sig")
    report = {
        "experiment": "group_a_twii_proxy_2008_inverse_sweep",
        "proxy_asset": "^TWII",
        "proxy_method": {
            "0050.TW": "1x TWII daily returns",
            "00631L.TW": "2x TWII daily returns",
            "00632R.TW": "-1x TWII daily returns",
        },
        "payload_path": str(payload_path.resolve()),
        "model_path": str(model_path.resolve()),
        "twii_market_cache": str(DEFAULT_TWII_MARKET_CACHE.resolve()),
        "requested_start": args.start,
        "requested_end": args.end,
        "actual_start": str(panel["date"].min().date()),
        "actual_end": str(panel["date"].max().date()),
        "limitations": [
            "Synthetic ETFs are generated from TWII daily returns rather than true ETF histories.",
            "The result is a proxy stress test, not exact historical ETF execution.",
        ],
        "benchmarks": benchmarks,
        "baseline": baseline,
        "best": {
            "best_final": max(rows, key=lambda row: row["final_value"]),
            "best_sharpe": max(rows, key=lambda row: row["sharpe"]),
            "best_mdd": max(rows, key=lambda row: row["max_drawdown"]),
        },
        "results": rows,
        "detailed_results": detailed,
        "outputs": {"json": str(output), "csv": str(csv_path), "curve_csv": str(curve_path)},
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"JSON: {output}")
    print(f"CSV:  {csv_path}")
    print(f"Curve CSV: {curve_path}")


if __name__ == "__main__":
    main()
