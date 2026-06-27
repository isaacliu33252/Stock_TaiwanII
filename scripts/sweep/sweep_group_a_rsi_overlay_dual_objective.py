#!/usr/bin/env python3
"""Sweep shadow-only Group A RSI overlay candidates on recent OOS and 2008 proxy."""

from __future__ import annotations

import argparse
import copy
import itertools
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from stable_baselines3 import PPO

from evaluate_group_a_runtime_candidates_dual_objective import _delta, _summary
from generate_dual_group_signal import _env_kwargs_from_payload, _llm_sentiment_path_from_payload
from train_dual_group_2024_2026 import (
    _backtest_group,
    attach_institutional_features_db_first,
    attach_market_features_db_first,
    load_stock_data_db_first,
    payload_uses_group_a_institutional_features,
)
from twii_proxy_utils import build_group_a_twii_proxy_data


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_PAYLOAD = PROJECT_ROOT / "results" / "group_a_backtest_20250101_20260525_20260526_193252.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_Golden1_0531_rsi_overlay_sweep_20260531.json"
RECENT_START = "2025-01-02"
RECENT_END = "2026-05-25"
CRASH_START = "2007-07-01"
CRASH_END = "2010-12-31"


def _resolve(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else (PROJECT_ROOT / candidate).resolve()


def _float_grid(raw: str) -> list[float]:
    return [float(item.strip()) for item in raw.split(",") if item.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload", default=str(DEFAULT_PAYLOAD))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--oversold-threshold-grid", default="25,30,35")
    parser.add_argument("--overbought-threshold-grid", default="65,70,75")
    parser.add_argument("--oversold-0050-boost-grid", default="0.05,0.10")
    parser.add_argument("--overbought-leverage-scale-grid", default="0.25,0.50,0.75")
    args = parser.parse_args()

    payload_path = _resolve(args.payload)
    output_path = _resolve(args.output)
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    group = payload["group_a"]
    tickers = list(group["tickers"])
    initial_cash = float(payload.get("initial_cash_per_group", 1_000_000.0))
    model_path = PROJECT_ROOT / "models" / "portfolio" / f"{group['model_name']}.zip"
    model = PPO.load(str(model_path))
    base_env, shared_feature_cols = _env_kwargs_from_payload(payload, "group_a")
    llm_path = _llm_sentiment_path_from_payload(payload, "group_a") if payload.get("group_a_use_llm_sentiment") else None

    recent_data = load_stock_data_db_first(tickers, "2020-01-01", RECENT_END)
    if payload_uses_group_a_institutional_features(payload):
        recent_data = attach_institutional_features_db_first(recent_data, tickers, "2020-01-01", RECENT_END)
    recent_data = attach_market_features_db_first(
        recent_data,
        tickers,
        "2020-01-01",
        RECENT_END,
        include_llm_sentiment=bool(payload.get("group_a_use_llm_sentiment", False)),
        llm_sentiment_path=llm_path,
    )
    crash_data, _ = build_group_a_twii_proxy_data(CRASH_START, CRASH_END)
    if payload_uses_group_a_institutional_features(payload):
        crash_data = attach_institutional_features_db_first(crash_data, tickers, CRASH_START, CRASH_END)

    grids = {
        "rsi_overlay_oversold_threshold": _float_grid(args.oversold_threshold_grid),
        "rsi_overlay_overbought_threshold": _float_grid(args.overbought_threshold_grid),
        "rsi_overlay_oversold_0050_boost": _float_grid(args.oversold_0050_boost_grid),
        "rsi_overlay_overbought_leverage_scale": _float_grid(args.overbought_leverage_scale_grid),
    }
    variants: list[dict[str, Any]] = []
    trials = [("Golden1_0531", {})]
    for values in itertools.product(*(grids[key] for key in grids)):
        overrides = dict(zip(grids, values))
        overrides["rsi_overlay_enabled"] = True
        name = (
            f"rsi_os{overrides['rsi_overlay_oversold_threshold']:g}"
            f"_ob{overrides['rsi_overlay_overbought_threshold']:g}"
            f"_boost{overrides['rsi_overlay_oversold_0050_boost']:.2f}"
            f"_lev{overrides['rsi_overlay_overbought_leverage_scale']:.2f}"
        )
        trials.append((name, overrides))

    for name, overrides in trials:
        print(f"Evaluate {name}")
        env = copy.deepcopy(base_env)
        env.update(overrides)
        recent = _summary(
            _backtest_group(
                model, recent_data, tickers, f"{name}_recent",
                shared_feature_cols=shared_feature_cols,
                backtest_start=RECENT_START, backtest_end=RECENT_END,
                initial_cash=initial_cash, env_kwargs=env,
            )
        )
        crash = _summary(
            _backtest_group(
                model, crash_data, tickers, f"{name}_crash",
                shared_feature_cols=shared_feature_cols,
                backtest_start=CRASH_START, backtest_end=CRASH_END,
                initial_cash=initial_cash, env_kwargs=env,
            )
        )
        variants.append({"name": name, "overrides": overrides, "recent_oos": recent, "crash_proxy_2008": crash})

    baseline = variants[0]
    for variant in variants:
        variant["delta_vs_Golden1_0531"] = {
            "recent_oos": _delta(variant["recent_oos"], baseline["recent_oos"]),
            "crash_proxy_2008": _delta(variant["crash_proxy_2008"], baseline["crash_proxy_2008"]),
        }
        variant["dual_objective_eligible"] = bool(
            variant["recent_oos"]["final_value"] >= baseline["recent_oos"]["final_value"]
            and variant["recent_oos"]["sharpe"] >= baseline["recent_oos"]["sharpe"]
            and variant["recent_oos"]["max_drawdown"] >= baseline["recent_oos"]["max_drawdown"]
            and variant["crash_proxy_2008"]["max_drawdown"] >= baseline["crash_proxy_2008"]["max_drawdown"]
            and variant["crash_proxy_2008"]["num_trades"] <= baseline["crash_proxy_2008"]["num_trades"] + 25
        )
    ranked = sorted(
        variants,
        key=lambda item: (
            item["dual_objective_eligible"],
            item["recent_oos"]["sharpe"],
            item["recent_oos"]["final_value"],
            item["crash_proxy_2008"]["max_drawdown"],
        ),
        reverse=True,
    )
    output = {
        "experiment": "group_a_Golden1_0531_rsi_overlay_dual_objective_sweep",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "baseline": baseline,
        "grids": grids,
        "eligible_count": sum(bool(item["dual_objective_eligible"]) for item in variants[1:]),
        "best_shadow_candidate": next(
            (item for item in ranked if item["name"] != "Golden1_0531" and item["dual_objective_eligible"]),
            None,
        ),
        "ranked": ranked,
        "note": "Golden1_0531 remains frozen. RSI overlay candidates are shadow-only.",
    }
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {output_path}")
    print(f"Eligible shadow candidates: {output['eligible_count']}")
    if output["best_shadow_candidate"]:
        print(f"Best shadow candidate: {output['best_shadow_candidate']['name']}")


if __name__ == "__main__":
    main()
