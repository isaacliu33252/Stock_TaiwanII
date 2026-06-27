#!/usr/bin/env python3
"""Standalone wrapper for segmented-model backtests."""

import argparse
import json
from datetime import datetime

from train_segments import (
    GROUP_A_BASE_NAME,
    GROUP_B_BASE_NAME,
    TOTAL_SEGS,
    PROJECT_ROOT,
    backtest_all,
    calculate_backtest_metrics,
)


def main():
    parser = argparse.ArgumentParser(description="載入分段模型並回測 2025-01-01 ~ 2026-05-20")
    parser.add_argument(
        "--model-a",
        default=f"{GROUP_A_BASE_NAME}_s{TOTAL_SEGS:02d}",
        help="Group A 模型名稱（不含 .zip）",
    )
    parser.add_argument(
        "--model-b",
        default=f"{GROUP_B_BASE_NAME}_s{TOTAL_SEGS:02d}",
        help="Group B 模型名稱（不含 .zip）",
    )
    parser.add_argument(
        "--blend",
        type=float,
        default=None,
        help="A 組比例（0~100）。例如 50 表示 50%% A + 50%% B",
    )
    args = parser.parse_args()

    result = backtest_all(args.model_a, args.model_b)

    out = PROJECT_ROOT / "results" / f"backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)

    print(f"\n回測結果: {out}")
    for label, res in [("Group A", result["result_a"]), ("Group B", result["result_b"])]:
        metrics = res["rl_metrics"]
        print(f"\n{label}:")
        print(f"  最終價值: {res['final_value']:,.0f}")
        print(f"  報酬率:   {metrics['total_return'] * 100:.2f}%")
        print(f"  Sharpe:   {metrics['sharpe']:.3f}")
        print(f"  Max DD:   {metrics['max_drawdown'] * 100:.2f}%")

    if args.blend is not None:
        blend_a = args.blend / 100.0
        blend_b = 1.0 - blend_a
        eq_a = result["result_a"]["equity_curve"]
        eq_b = result["result_b"]["equity_curve"]
        min_len = min(len(eq_a), len(eq_b))
        blended = [eq_a[i] * blend_a + eq_b[i] * blend_b for i in range(min_len)]
        blended_metrics = calculate_backtest_metrics(blended)
        print(f"\nBlend ({int(blend_a * 100)}% A + {int(blend_b * 100)}% B):")
        print(f"  最終價值: {blended[-1]:,.0f}")
        print(f"  報酬率:   {blended_metrics['total_return'] * 100:.2f}%")
        print(f"  Sharpe:   {blended_metrics['sharpe']:.3f}")
        print(f"  Max DD:   {blended_metrics['max_drawdown'] * 100:.2f}%")


if __name__ == "__main__":
    main()
