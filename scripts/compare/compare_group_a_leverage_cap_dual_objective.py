#!/usr/bin/env python3
"""Compare Group A leverage-cap variants on recent real data and 2008 TWII proxy."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from stable_baselines3 import PPO

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from generate_dual_group_signal import _env_kwargs_from_payload
from train_dual_group_2024_2026 import (
    _backtest_group,
    attach_institutional_features_db_first,
    attach_market_features_db_first,
    load_stock_data_db_first,
    payload_uses_group_a_institutional_features,
)
from twii_proxy_utils import build_group_a_twii_proxy_data


DEFAULT_PAYLOAD = PROJECT_ROOT / "results" / "group_a_runtime_payload_primary_20260524.json"
DEFAULT_MODEL = PROJECT_ROOT / "models" / "portfolio" / "group_a_microopt_b060_p030_20260521_233524.zip"
RECENT_START = "2024-01-02"
RECENT_END = "2026-05-21"
CRASH_START = "2007-07-01"
CRASH_END = "2010-12-31"
LEVERAGE_CAPS = [0.20, 0.25, 0.30]


def _summary(result: dict) -> dict:
    rl = result["rl_metrics"]
    return {
        "final_value": float(result["final_value"]),
        "total_invested_capital": float(result["total_invested_capital"]),
        "net_profit": float(result["net_profit"]),
        "contribution_return": float(result["contribution_return"]),
        "annual_return": float(rl["annual_return"]),
        "sharpe": float(rl["sharpe"]),
        "max_drawdown": float(rl["max_drawdown"]),
        "volatility": float(rl["volatility"]),
        "num_trades": int(result["num_trades"]),
        "dca_purchase_count": int(result["dca_purchase_count"]),
        "dca_total_contributions": float(result["dca_total_contributions"]),
        "pva_sigmoid_count": int(result["pva_sigmoid_count"]),
        "final_weights": result.get("final_weights"),
    }


def main() -> None:
    payload = json.loads(DEFAULT_PAYLOAD.read_text(encoding="utf-8"))
    model = PPO.load(str(DEFAULT_MODEL))
    env_kwargs, shared_feature_cols = _env_kwargs_from_payload(payload, "group_a")

    tickers = list(payload.get("group_a", {}).get("tickers", ["0050.TW", "00631L.TW", "00632R.TW"]))
    initial_cash = float(payload.get("initial_cash_per_group", 1_000_000.0))
    llm_cfg = payload.get("group_a_llm_sentiment_config", {}) or {}

    recent_stock_data = load_stock_data_db_first(tickers, RECENT_START, RECENT_END)
    if payload_uses_group_a_institutional_features(payload):
        recent_stock_data = attach_institutional_features_db_first(recent_stock_data, tickers, RECENT_START, RECENT_END)
    recent_stock_data = attach_market_features_db_first(
        recent_stock_data,
        tickers,
        RECENT_START,
        RECENT_END,
        include_llm_sentiment=bool(llm_cfg.get("enabled")),
        llm_sentiment_path=llm_cfg.get("path"),
    )
    crash_stock_data, _ = build_group_a_twii_proxy_data(CRASH_START, CRASH_END)
    if payload_uses_group_a_institutional_features(payload):
        crash_stock_data = attach_institutional_features_db_first(crash_stock_data, tickers, CRASH_START, CRASH_END)

    variants: list[dict] = []
    for cap in LEVERAGE_CAPS:
        variant_env = deepcopy(env_kwargs)
        variant_env["leverage_cap"] = float(cap)
        recent_result = _backtest_group(
            model,
            recent_stock_data,
            tickers,
            f"recent_cap{int(cap * 100):02d}",
            shared_feature_cols=shared_feature_cols,
            backtest_start=RECENT_START,
            backtest_end=RECENT_END,
            initial_cash=initial_cash,
            env_kwargs=variant_env,
        )
        crash_result = _backtest_group(
            model,
            crash_stock_data,
            tickers,
            f"crash_cap{int(cap * 100):02d}",
            shared_feature_cols=shared_feature_cols,
            backtest_start=CRASH_START,
            backtest_end=CRASH_END,
            initial_cash=initial_cash,
            env_kwargs=variant_env,
        )
        variants.append(
            {
                "leverage_cap": float(cap),
                "env_overrides": {"leverage_cap": float(cap)},
                "recent_real_2024_2026": _summary(recent_result),
                "crash_proxy_2008": _summary(crash_result),
            }
        )

    baseline = next(item for item in variants if abs(item["leverage_cap"] - 0.30) < 1e-9)
    for variant in variants:
        for window_key in ("recent_real_2024_2026", "crash_proxy_2008"):
            current = variant[window_key]
            base = baseline[window_key]
            current["delta_vs_cap30"] = {
                "final_value": float(current["final_value"] - base["final_value"]),
                "contribution_return": float(current["contribution_return"] - base["contribution_return"]),
                "sharpe": float(current["sharpe"] - base["sharpe"]),
                "max_drawdown": float(current["max_drawdown"] - base["max_drawdown"]),
            }

    best_recent = max(
        variants,
        key=lambda item: (
            item["recent_real_2024_2026"]["contribution_return"],
            item["recent_real_2024_2026"]["sharpe"],
            item["recent_real_2024_2026"]["max_drawdown"],
        ),
    )
    best_crash = max(
        variants,
        key=lambda item: (
            item["crash_proxy_2008"]["max_drawdown"],
            item["crash_proxy_2008"]["contribution_return"],
            item["crash_proxy_2008"]["sharpe"],
        ),
    )

    out = {
        "experiment": "group_a_leverage_cap_dual_objective_compare_20260524",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "payload_path": str(DEFAULT_PAYLOAD.resolve()),
        "model_path": str(DEFAULT_MODEL.resolve()),
        "shared_feature_cols": shared_feature_cols,
        "base_env_kwargs": env_kwargs,
        "recent_window": {"start": RECENT_START, "end": RECENT_END},
        "crash_window": {"start": CRASH_START, "end": CRASH_END},
        "leverage_caps_tested": LEVERAGE_CAPS,
        "baseline_cap30": baseline,
        "best_recent_real": best_recent,
        "best_crash_proxy": best_crash,
        "variants": variants,
        "note": (
            "Recent-real comparison uses cached real 2024-2026 Group A data with market/LLM features. "
            "Crash comparison uses TWII-based synthetic proxy data for 2008 stress testing."
        ),
    }

    output_path = PROJECT_ROOT / "results" / "group_a_leverage_cap_dual_objective_20260524.json"
    output_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=" * 72)
    print("Group A leverage-cap dual-objective comparison complete")
    print(f"Recent best: cap={best_recent['leverage_cap']:.2f}")
    print(
        "  recent contribution_return="
        f"{best_recent['recent_real_2024_2026']['contribution_return']:.4f}, "
        f"sharpe={best_recent['recent_real_2024_2026']['sharpe']:.4f}, "
        f"mdd={best_recent['recent_real_2024_2026']['max_drawdown']:.4f}"
    )
    print(f"Crash best: cap={best_crash['leverage_cap']:.2f}")
    print(
        "  crash contribution_return="
        f"{best_crash['crash_proxy_2008']['contribution_return']:.4f}, "
        f"sharpe={best_crash['crash_proxy_2008']['sharpe']:.4f}, "
        f"mdd={best_crash['crash_proxy_2008']['max_drawdown']:.4f}"
    )
    print(f"Result: {output_path}")
    print("=" * 72)


if __name__ == "__main__":
    main()
