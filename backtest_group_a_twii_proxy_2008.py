#!/usr/bin/env python3
"""Stress test canonical Group A on a TWII-based synthetic 2008 path."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from stable_baselines3 import PPO

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from generate_dual_group_signal import _env_kwargs_from_payload
from train_dual_group_2024_2026 import _align_panel, _backtest_group, _buy_and_hold
from twii_proxy_utils import DEFAULT_TWII_MARKET_CACHE, build_group_a_twii_proxy_data


DEFAULT_START = "2007-07-01"
DEFAULT_END = "2010-12-31"
DEFAULT_PAYLOAD = PROJECT_ROOT / "results" / "group_a_runtime_payload_primary_20260524.json"


def _resolve_group_a_model_path(payload: dict, override: str | None) -> Path:
    if override:
        raw = Path(override)
        if raw.exists():
            return raw
        if raw.suffix != ".zip" and raw.with_suffix(".zip").exists():
            return raw.with_suffix(".zip")
        raise FileNotFoundError(f"Unable to locate Group A model override: {override}")

    group_a = payload.get("group_a", {}) or {}
    model_name = group_a.get("model_name")
    if model_name:
        candidate = PROJECT_ROOT / "models" / "portfolio" / str(model_name)
        if candidate.exists():
            return candidate
        if candidate.suffix != ".zip" and candidate.with_suffix(".zip").exists():
            return candidate.with_suffix(".zip")

    resume_model = payload.get("group_a_resume_model") or group_a.get("resume_model")
    if resume_model:
        candidate = Path(str(resume_model))
        if candidate.exists():
            return candidate

    raise FileNotFoundError("Unable to resolve Group A model path from payload")


def _benchmark_payload(panel, tickers: list[str], initial_cash: float) -> dict:
    equal_weights = np.array([1.0 / len(tickers)] * len(tickers), dtype=float)
    blend_weights = np.array([0.5, 0.5, 0.0], dtype=float)
    hold_0050 = np.array([1.0, 0.0, 0.0], dtype=float)
    hold_00631l = np.array([0.0, 1.0, 0.0], dtype=float)
    hold_00632r = np.array([0.0, 0.0, 1.0], dtype=float)
    return {
        "equal_weight": _buy_and_hold(panel, tickers, equal_weights, initial_cash),
        "blend50": _buy_and_hold(panel, tickers, blend_weights, initial_cash),
        "hold_0050": _buy_and_hold(panel, tickers, hold_0050, initial_cash),
        "hold_00631L": _buy_and_hold(panel, tickers, hold_00631l, initial_cash),
        "hold_00632R": _buy_and_hold(panel, tickers, hold_00632r, initial_cash),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Stress test Group A on a TWII proxy path.")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--payload", default=str(DEFAULT_PAYLOAD))
    parser.add_argument("--model", default=None, help="Optional explicit Group A model path")
    args = parser.parse_args()

    payload_path = Path(args.payload)
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    model_path = _resolve_group_a_model_path(payload, args.model)
    env_kwargs, shared_feature_cols = _env_kwargs_from_payload(payload, "group_a")

    stock_data, market = build_group_a_twii_proxy_data(args.start, args.end)
    tickers = list((payload.get("group_a", {}) or {}).get("tickers", ["0050.TW", "00631L.TW", "00632R.TW"]))
    initial_cash = float(payload.get("initial_cash_per_group", 1_000_000.0))
    model = PPO.load(str(model_path))

    result = _backtest_group(
        model,
        stock_data,
        tickers,
        "GroupA_TWIIProxy2008",
        shared_feature_cols=shared_feature_cols,
        backtest_start=args.start,
        backtest_end=args.end,
        initial_cash=initial_cash,
        env_kwargs=env_kwargs,
    )

    panel = _align_panel(
        stock_data,
        tickers,
        args.start,
        args.end,
        shared_feature_cols=shared_feature_cols,
    )
    benchmarks = _benchmark_payload(panel, tickers, initial_cash)

    output_dir = PROJECT_ROOT / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"group_a_twii_proxy_2008_{args.start.replace('-', '')}_{args.end.replace('-', '')}_{stamp}.json"

    payload_out = {
        "experiment": "group_a_twii_proxy_2008_stress_test",
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
        "panel_rows": int(len(panel)),
        "shared_feature_cols": shared_feature_cols,
        "shared_feature_note": "Historical LLM sentiment inputs are unavailable for 2008; shared LLM columns are zero-filled to preserve canonical observation shape.",
        "env_kwargs": env_kwargs,
        "limitations": [
            "Synthetic ETFs are generated from TWII daily returns rather than true ETF histories.",
            "Proxy open/high/low/volume are reconstructed from TWII return and volume-change features.",
            "The result is suitable for stress testing current Group A logic, not for exact historical execution claims.",
        ],
        "benchmarks": benchmarks,
        "result": result,
    }

    with open(output_file, "w", encoding="utf-8") as handle:
        json.dump(payload_out, handle, indent=2, ensure_ascii=False, default=str)

    rl = result.get("rl_metrics", {})
    hold_0050 = benchmarks["hold_0050"]["metrics"]
    blend50 = benchmarks["blend50"]["metrics"]
    print("=" * 72)
    print("Group A TWII proxy stress test complete")
    print(f"Range: {payload_out['actual_start']} ~ {payload_out['actual_end']} ({payload_out['panel_rows']} rows)")
    print(f"Final value: {result.get('final_value', 0):,.0f}")
    print(
        "RL metrics: "
        f"return={rl.get('total_return', 0):.2%}, "
        f"annual={rl.get('annual_return', 0):.2%}, "
        f"sharpe={rl.get('sharpe', 0):.3f}, "
        f"mdd={rl.get('max_drawdown', 0):.2%}"
    )
    print(
        "0050 proxy B&H: "
        f"return={hold_0050.get('total_return', 0):.2%}, "
        f"sharpe={hold_0050.get('sharpe', 0):.3f}, "
        f"mdd={hold_0050.get('max_drawdown', 0):.2%}"
    )
    print(
        "Blend50 proxy B&H: "
        f"return={blend50.get('total_return', 0):.2%}, "
        f"sharpe={blend50.get('sharpe', 0):.3f}, "
        f"mdd={blend50.get('max_drawdown', 0):.2%}"
    )
    print(f"Trades: {result.get('num_trades', 0)}, PVA hits: {result.get('pva_sigmoid_count', 0)}")
    print(f"Result: {output_file}")
    print("=" * 72)


if __name__ == "__main__":
    main()
