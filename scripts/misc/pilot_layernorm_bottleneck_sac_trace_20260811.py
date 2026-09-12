#!/usr/bin/env python3
"""Follow-up to pilot_layernorm_bottleneck_sac_20260811.py: trains ONE
LayerNorm-bottleneck SAC agent (seed=0, same config) and captures the full
position trajectory + trade history during the out-of-sample backtest, to
check whether the pilot's identical-across-seeds +14.9% result is genuine
trading behavior or a degenerate "buy near max position early, then hold"
collapse. Research-only, single seed, fast (~1 training run instead of 6).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "misc"))

import pilot_layernorm_bottleneck_sac_20260811 as base  # noqa: E402
from FinRL.v2.environments.taiwan_stock_env import TaiwanStockTradingEnv  # noqa: E402

OUTPUT = PROJECT_ROOT / "research" / "shadow" / "layernorm_bottleneck_sac_trace_20260811.json"


def main() -> None:
    train_df = base.load_ticker_df(base.TRAIN_START, base.TRAIN_END)
    test_df = base.load_ticker_df(base.TEST_START, base.TEST_END)

    print("--- training layernorm seed=0 (single run for trace) ---")
    train_out = base._train_one(0, True, train_df)
    model = train_out["model"]

    env = TaiwanStockTradingEnv(df=test_df, mode="continuous")
    obs, _ = env.reset()
    position_trace = [env.portfolio.position]
    value_trace = [env.portfolio.total_value]
    action_trace = []
    done = False
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        action_trace.append(float(action[0]))
        obs, reward, terminated, truncated, info = env.step(action)
        position_trace.append(env.portfolio.position)
        value_trace.append(env.portfolio.total_value)
        done = terminated or truncated

    trades = [
        {
            "date": t.date,
            "action": t.action,
            "price": float(t.price),
            "shares": int(t.shares),
            "position_after": int(t.position),
        }
        for t in env.trade_history
    ]

    position_trace = np.array(position_trace)
    n_position_changes = int(np.sum(np.diff(position_trace) != 0))
    unique_positions = sorted(set(int(p) for p in position_trace))

    summary = {
        "n_trades": len(trades),
        "trades": trades,
        "n_position_changes": n_position_changes,
        "unique_position_levels": unique_positions,
        "position_at_start": int(position_trace[0]),
        "position_at_end": int(position_trace[-1]),
        "position_reached_max_at_step": (
            int(np.argmax(position_trace >= env.max_position)) if (position_trace >= env.max_position).any() else None
        ),
        "action_stats": {
            "mean": float(np.mean(action_trace)),
            "std": float(np.std(action_trace)),
            "min": float(np.min(action_trace)),
            "max": float(np.max(action_trace)),
            "frac_above_0.5_buy_threshold": float(np.mean(np.array(action_trace) >= 0.5)),
        },
        "final_value": float(value_trace[-1]),
        "initial_value": float(value_trace[0]),
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

    print(f"\nWritten to {OUTPUT}")
    print(f"n_trades={summary['n_trades']}, n_position_changes={n_position_changes}")
    print(f"unique_position_levels={unique_positions}")
    print(f"position: start={summary['position_at_start']}, end={summary['position_at_end']}, "
          f"reached_max_at_step={summary['position_reached_max_at_step']}")
    print(f"action_stats={summary['action_stats']}")


if __name__ == "__main__":
    main()
