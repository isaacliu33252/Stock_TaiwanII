#!/usr/bin/env python3
"""Stress test Group B on a TWII-based synthetic 2008 path."""

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
from train_dual_group_2024_2026 import (
    _align_panel,
    _backtest_group,
    _buy_and_hold,
    attach_institutional_features_db_first,
    attach_margin_features_db_first,
    payload_uses_group_b_institutional_features,
    payload_uses_group_b_margin_features,
)
from twii_proxy_utils import DEFAULT_TWII_MARKET_CACHE, build_group_b_twii_proxy_data


DEFAULT_START = "2007-07-01"
DEFAULT_END = "2010-12-31"
DEFAULT_PAYLOAD = PROJECT_ROOT / "results" / "group_b_runtime_payload_primary_20260530.json"


def _resolve_group_b_model_path(payload: dict, override: str | None) -> Path:
    if override:
        raw = Path(override)
        if raw.exists():
            return raw
        if raw.suffix != ".zip" and raw.with_suffix(".zip").exists():
            return raw.with_suffix(".zip")
        raise FileNotFoundError(f"Unable to locate Group B model override: {override}")

    group_b = payload.get("group_b", {}) or {}
    model_name = group_b.get("model_name")
    if model_name:
        candidate = PROJECT_ROOT / "models" / "portfolio" / str(model_name)
        if candidate.exists():
            return candidate
        if candidate.suffix != ".zip" and candidate.with_suffix(".zip").exists():
            return candidate.with_suffix(".zip")

    resume_model = payload.get("group_b_resume_model") or group_b.get("resume_model")
    if resume_model:
        candidate = Path(str(resume_model))
        if candidate.exists():
            return candidate

    raise FileNotFoundError("Unable to resolve Group B model path from payload")


def _benchmark_payload(panel, tickers: list[str], initial_cash: float) -> dict:
    """Buy-and-hold benchmarks for Group B."""
    n = len(tickers)
    equal_weights = np.array([1.0 / n] * n, dtype=float)
    benchmarks = {
        "equal_weight": _buy_and_hold(panel, tickers, equal_weights, initial_cash),
    }
    # Per-ticker single-hold benchmarks
    for i, t in enumerate(tickers):
        w = np.zeros(n, dtype=float)
        w[i] = 1.0
        benchmarks[f"hold_{t}"] = _buy_and_hold(panel, tickers, w, initial_cash)
    return benchmarks


def main() -> None:
    parser = argparse.ArgumentParser(description="Stress test Group B on a TWII proxy path.")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--payload", default=str(DEFAULT_PAYLOAD))
    parser.add_argument("--model", default=None, help="Optional explicit Group B model path")
    args = parser.parse_args()

    payload_path = Path(args.payload)
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    model_path = _resolve_group_b_model_path(payload, args.model)
    env_kwargs, shared_feature_cols = _env_kwargs_from_payload(payload, "group_b")

    stock_data, market = build_group_b_twii_proxy_data(args.start, args.end)
    tickers = list(
        (payload.get("group_b", {}) or {}).get(
            "tickers", ["0056.TW", "00646.TW", "00679B.TWO", "00713.TW", "00751B.TWO", "00878.TW"]
        )
    )
    initial_cash = float(payload.get("initial_cash_per_group", 1_000_000.0))

    # Force enable DJI + LLM shared features so env obs dim matches trained model
    payload["group_b_use_llm_sentiment"] = True
    payload["group_b_use_dji_features"] = True
    payload["group_b_use_institutional_features"] = False
    payload["group_b_use_margin_features"] = False

    # Patch shared_feature_cols so _env_kwargs_from_payload returns DJI + LLM columns
    if "group_b" not in payload:
        payload["group_b"] = {}
    from FinRL.portfolio_data_loader import LLM_SENTIMENT_COLUMNS
    from train_dual_group_2024_2026 import DJI_FEATURE_COLUMNS
    patched_shared_cols = list(DJI_FEATURE_COLUMNS) + list(LLM_SENTIMENT_COLUMNS)
    payload["group_b"]["shared_feature_cols"] = patched_shared_cols

    stock_data_merged = dict(stock_data)
    if payload_uses_group_b_institutional_features(payload):
        stock_data_merged = attach_institutional_features_db_first(stock_data_merged, tickers, args.start, args.end)
    if payload_uses_group_b_margin_features(payload):
        stock_data_merged = attach_margin_features_db_first(stock_data_merged, tickers, args.start, args.end)

    model = PPO.load(str(model_path))

    result = _backtest_group(
        model,
        stock_data_merged,
        tickers,
        "GroupB_TWIIProxy2008",
        shared_feature_cols=patched_shared_cols,
        backtest_start=args.start,
        backtest_end=args.end,
        initial_cash=initial_cash,
        env_kwargs=env_kwargs,
    )

    panel = _align_panel(
        stock_data_merged,
        tickers,
        args.start,
        args.end,
        shared_feature_cols=patched_shared_cols,
    )
    benchmarks = _benchmark_payload(panel, tickers, initial_cash)

    output_dir = PROJECT_ROOT / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"group_b_twii_proxy_2008_{args.start.replace('-', '')}_{args.end.replace('-', '')}_{stamp}.json"

    proxy_method = {
        t: f"{p['leverage']:.0f}x TWII daily returns (vol_scale={p['vol_scale']})"
        for t, p in {
            "0056.TW": dict(leverage=0.85, vol_scale=1.0),
            "00646.TW": dict(leverage=0.75, vol_scale=0.85),
            "00679B.TWO": dict(leverage=0.45, vol_scale=0.70),
            "00713.TW": dict(leverage=0.80, vol_scale=0.95),
            "00751B.TWO": dict(leverage=0.75, vol_scale=0.90),
            "00878.TW": dict(leverage=0.85, vol_scale=1.0),
        }.items()
    }

    payload_out = {
        "experiment": "group_b_twii_proxy_2008_stress_test",
        "proxy_asset": "^TWII",
        "proxy_method": proxy_method,
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
        "feature_gap_note": (
            "Historical institutional and margin-trading inputs are unavailable for 2008; "
            "those per-ticker features are zero-filled to preserve canonical observation shape."
        ),
        "env_kwargs": env_kwargs,
        "limitations": [
            "Synthetic ETFs are generated from TWII daily returns rather than true ETF histories.",
            "Proxy open/high/low/volume are reconstructed from TWII return and volume-change features.",
            "Leverage and vol_scale parameters are calibrated to rough empirical correlations; "
            "actual asset behaviour in 2008 may differ significantly.",
            "The result is suitable for stress testing current Group B logic, not for exact historical execution claims.",
        ],
        "benchmarks": benchmarks,
        "result": result,
    }

    with open(output_file, "w", encoding="utf-8") as handle:
        json.dump(payload_out, handle, indent=2, ensure_ascii=False, default=str)

    rl = result.get("rl_metrics", {})
    equal_bench = benchmarks.get("equal_weight", {}).get("metrics", {})
    print("=" * 72)
    print("Group B TWII proxy stress test complete")
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
        "Equal-weight B&H proxy: "
        f"return={equal_bench.get('total_return', 0):.2%}, "
        f"sharpe={equal_bench.get('sharpe', 0):.3f}, "
        f"mdd={equal_bench.get('max_drawdown', 0):.2%}"
    )
    print(f"Trades: {result.get('num_trades', 0)}, PVA hits: {result.get('pva_sigmoid_count', 0)}")
    print(f"SJM state counts: {result.get('sjm_state_counts', {})}")
    print(f"DCA count: {result.get('dca_purchase_count', 0)}, DCA contrib: {result.get('dca_total_contributions', 0):,.0f}")
    print(f"Result: {output_file}")
    print("=" * 72)


if __name__ == "__main__":
    main()