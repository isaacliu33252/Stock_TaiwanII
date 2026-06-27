#!/usr/bin/env python3
"""Evaluate Group A runtime sweep candidates on recent OOS and 2008 TWII proxy."""

from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from stable_baselines3 import PPO

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
DEFAULT_SWEEP = PROJECT_ROOT / "results" / "group_a_Golden1_0531_pva_micro_sweep_20260531.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_Golden1_0531_dual_objective_20260531.json"
CRASH_START = "2007-07-01"
CRASH_END = "2010-12-31"


def _resolve(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else (PROJECT_ROOT / candidate).resolve()


def _summary(result: dict[str, Any]) -> dict[str, Any]:
    metrics = result["rl_metrics"]
    return {
        "final_value": float(result["final_value"]),
        "annual_return": float(metrics["annual_return"]),
        "sharpe": float(metrics["sharpe"]),
        "max_drawdown": float(metrics["max_drawdown"]),
        "volatility": float(metrics["volatility"]),
        "num_trades": int(result["num_trades"]),
        "fees_paid_estimate": float(result["fees_paid_estimate"]),
        "pva_sigmoid_count": int(result["pva_sigmoid_count"]),
        "dca_total_contributions": float(result["dca_total_contributions"]),
    }


def _delta(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    return {
        "final_value": float(current["final_value"] - baseline["final_value"]),
        "annual_return": float(current["annual_return"] - baseline["annual_return"]),
        "sharpe": float(current["sharpe"] - baseline["sharpe"]),
        "max_drawdown": float(current["max_drawdown"] - baseline["max_drawdown"]),
        "volatility": float(current["volatility"] - baseline["volatility"]),
        "num_trades": int(current["num_trades"] - baseline["num_trades"]),
        "fees_paid_estimate": float(current["fees_paid_estimate"] - baseline["fees_paid_estimate"]),
    }


def _trial_env(base_env: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    env = copy.deepcopy(base_env)
    env.update(overrides)
    return env


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload", default=str(DEFAULT_PAYLOAD))
    parser.add_argument("--sweep", default=str(DEFAULT_SWEEP))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--top-n", type=int, default=12)
    parser.add_argument("--max-extra-crash-trades", type=int, default=25)
    args = parser.parse_args()

    payload_path = _resolve(args.payload)
    sweep_path = _resolve(args.sweep)
    output_path = _resolve(args.output)
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    sweep = json.loads(sweep_path.read_text(encoding="utf-8"))

    group = payload["group_a"]
    tickers = list(group["tickers"])
    initial_cash = float(payload.get("initial_cash_per_group", 1_000_000.0))
    model_path = PROJECT_ROOT / "models" / "portfolio" / f"{group['model_name']}.zip"
    model = PPO.load(str(model_path))
    base_env, shared_feature_cols = _env_kwargs_from_payload(payload, "group_a")

    window = sweep["window"]
    recent_start = str(window["backtest_start"])
    recent_end = str(window["backtest_end"])
    load_start = str(window["train_start"])
    download_end = str(window["download_end"])
    llm_path = _llm_sentiment_path_from_payload(payload, "group_a") if payload.get("group_a_use_llm_sentiment") else None

    recent_data = load_stock_data_db_first(tickers, load_start, download_end)
    if payload_uses_group_a_institutional_features(payload):
        recent_data = attach_institutional_features_db_first(recent_data, tickers, load_start, download_end)
    recent_data = attach_market_features_db_first(
        recent_data,
        tickers,
        load_start,
        download_end,
        include_llm_sentiment=bool(payload.get("group_a_use_llm_sentiment", False)),
        llm_sentiment_path=llm_path,
    )

    crash_data, _ = build_group_a_twii_proxy_data(CRASH_START, CRASH_END)
    if payload_uses_group_a_institutional_features(payload):
        crash_data = attach_institutional_features_db_first(crash_data, tickers, CRASH_START, CRASH_END)

    selected: list[dict[str, Any]] = [{"name": "Golden1_0531", "overrides": {}}]
    seen: set[str] = set()
    for run in sweep.get("runs", []):
        if not run.get("eligible"):
            continue
        overrides = dict(run["overrides"])
        key = json.dumps(overrides, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        selected.append({"name": f"candidate_{len(selected):02d}", "overrides": overrides})
        if len(selected) > int(args.top_n):
            break

    variants: list[dict[str, Any]] = []
    for item in selected:
        env = _trial_env(base_env, item["overrides"])
        print(f"Evaluate {item['name']}: {item['overrides']}")
        recent = _summary(
            _backtest_group(
                model,
                recent_data,
                tickers,
                f"{item['name']}_recent",
                shared_feature_cols=shared_feature_cols,
                backtest_start=recent_start,
                backtest_end=recent_end,
                initial_cash=initial_cash,
                env_kwargs=env,
            )
        )
        crash = _summary(
            _backtest_group(
                model,
                crash_data,
                tickers,
                f"{item['name']}_crash",
                shared_feature_cols=shared_feature_cols,
                backtest_start=CRASH_START,
                backtest_end=CRASH_END,
                initial_cash=initial_cash,
                env_kwargs=env,
            )
        )
        variants.append({"name": item["name"], "overrides": item["overrides"], "recent_oos": recent, "crash_proxy_2008": crash})

    baseline = variants[0]
    for variant in variants:
        variant["delta_vs_Golden1_0531"] = {
            "recent_oos": _delta(variant["recent_oos"], baseline["recent_oos"]),
            "crash_proxy_2008": _delta(variant["crash_proxy_2008"], baseline["crash_proxy_2008"]),
        }
        crash_trade_limit = baseline["crash_proxy_2008"]["num_trades"] + int(args.max_extra_crash_trades)
        variant["dual_objective_eligible"] = bool(
            variant["recent_oos"]["final_value"] >= baseline["recent_oos"]["final_value"]
            and variant["recent_oos"]["sharpe"] >= baseline["recent_oos"]["sharpe"]
            and variant["recent_oos"]["max_drawdown"] >= baseline["recent_oos"]["max_drawdown"]
            and variant["crash_proxy_2008"]["max_drawdown"] >= baseline["crash_proxy_2008"]["max_drawdown"]
            and variant["crash_proxy_2008"]["num_trades"] <= crash_trade_limit
        )

    eligible = [item for item in variants if item["dual_objective_eligible"]]
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
        "experiment": "group_a_Golden1_0531_runtime_dual_objective",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "baseline": "Golden1_0531",
        "payload": str(payload_path),
        "sweep": str(sweep_path),
        "model_path": str(model_path),
        "recent_window": {"start": recent_start, "end": recent_end},
        "crash_window": {"start": CRASH_START, "end": CRASH_END},
        "eligibility_rule": {
            "recent_final_value": "not worse than Golden1_0531",
            "recent_sharpe": "not worse than Golden1_0531",
            "recent_max_drawdown": "not worse than Golden1_0531",
            "crash_max_drawdown": "not worse than Golden1_0531",
            "max_extra_crash_trades": int(args.max_extra_crash_trades),
        },
        "eligible_count": len(eligible),
        "best": next((item for item in ranked if item["dual_objective_eligible"]), None),
        "ranked": ranked,
        "variants": variants,
    }
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {output_path}")
    print(f"Dual-objective eligible candidates: {len(eligible)}")
    if output["best"]:
        print(f"Best: {output['best']['name']} {output['best']['overrides']}")


if __name__ == "__main__":
    main()
