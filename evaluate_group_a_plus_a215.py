#!/usr/bin/env python3
"""Train-only selection and frozen holdout evaluation for A21.5."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd

from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.runners.a213 import _run_recovery_strategy, run_a213
from group_a_plus.runners.a215 import run_a215
from tw_output_standard import OutputStandardizer, write_standard_output


SEARCH_MA_WINDOWS = tuple(range(60, 91, 5))
SEARCH_BASKETS = ("cash30", "cash40", "bond20")
EVALUATION_WINDOWS = {
    "train_2020_2024": ("2020-01-02", "2024-12-31"),
    "validation_2025_2026": ("2025-01-02", "2026-06-18"),
    "long_2020_2026": ("2020-01-02", "2026-06-18"),
}


def _train_pass(row: dict[str, Any], baseline: dict[str, float]) -> bool:
    return (
        row["final_value"] >= baseline["final_value"]
        and row["sharpe_ratio"] >= baseline["sharpe_ratio"]
        and row["max_drawdown"] >= baseline["max_drawdown"] - 1e-12
        and row["expected_tail_loss_5pct"] >= baseline["expected_tail_loss_5pct"]
    )


def _select_train_candidate(rows: list[dict[str, Any]], baseline: dict[str, float]) -> dict[str, Any]:
    passing = [row for row in rows if _train_pass(row, baseline)]
    if not passing:
        raise RuntimeError("No train-only candidate passed the four fixed gates")
    return max(passing, key=lambda row: (row["sharpe_ratio"], row["final_value"], row["max_drawdown"]))


def evaluate(db: Path, initial_value: float) -> dict[str, Any]:
    train_start, train_end = EVALUATION_WINDOWS["train_2020_2024"]
    baseline_train = run_a213(train_start, train_end, initial_value, db)[0]["metrics"]
    search_rows = []
    for ma_window in SEARCH_MA_WINDOWS:
        for basket_name in SEARCH_BASKETS:
            report, _ = _run_recovery_strategy(
                start=train_start,
                end=train_end,
                initial_value=initial_value,
                db=db,
                basket_name=basket_name,
                ma_window=ma_window,
                strategy_id=f"ma{ma_window}_{basket_name}",
                experiment="group_a_plus_a215_train_only_search",
                status="research",
            )
            search_rows.append({"ma_window": ma_window, "basket_name": basket_name, **report["metrics"]})
    selected = _select_train_candidate(search_rows, baseline_train)
    if (selected["ma_window"], selected["basket_name"]) != (80, "cash40"):
        raise RuntimeError(f"Frozen A21.5 identity changed unexpectedly: {selected}")

    evaluation_rows = []
    for window, (start, end) in EVALUATION_WINDOWS.items():
        base = run_a213(start, end, initial_value, db)[0]["metrics"]
        candidate = run_a215(start, end, initial_value, db)[0]["metrics"]
        row = {
            "window": window,
            "a213_final": base["final_value"],
            "a215_final": candidate["final_value"],
            "delta_final": candidate["final_value"] - base["final_value"],
            "delta_sharpe": candidate["sharpe_ratio"] - base["sharpe_ratio"],
            "delta_sortino": candidate["sortino_ratio"] - base["sortino_ratio"],
            "delta_mdd": candidate["max_drawdown"] - base["max_drawdown"],
            "delta_etl": candidate["expected_tail_loss_5pct"] - base["expected_tail_loss_5pct"],
        }
        row["formal_pass"] = (
            row["delta_final"] >= -1e-9 and row["delta_sharpe"] >= 0 and row["delta_mdd"] >= 0
        )
        evaluation_rows.append(row)
    formal_promotion = all(row["formal_pass"] for row in evaluation_rows)
    validation = next(row for row in evaluation_rows if row["window"] == "validation_2025_2026")
    return {
        "experiment": "group_a_plus_a215_train_selected_frozen_validation",
        "selection_policy": "Search and rank use 2020-2024 only; 2025-2026 is opened after candidate freeze.",
        "search_space": {"ma_windows": SEARCH_MA_WINDOWS, "baskets": SEARCH_BASKETS},
        "train_baseline": baseline_train,
        "train_search_rows": search_rows,
        "selected_candidate": {"strategy": "a215_cash40_mw80", **selected},
        "evaluation_rows": evaluation_rows,
        "decision": {
            "formal_promotion_pass": formal_promotion,
            "status": "promotion_ready" if formal_promotion else "research_watchlist",
            "blocking_reason": None if formal_promotion else (
                f"validation final delta is {validation['delta_final']:.2f}; strict gate requires non-negative"
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--output-prefix", default="results/group_a_plus_a215_evaluation_20260621")
    args = parser.parse_args()
    prefix = Path(args.output_prefix)
    std = OutputStandardizer("evaluate_group_a_plus_a215.py")
    try:
        report = evaluate(Path(args.db), args.initial_value)
        pd.DataFrame(report["train_search_rows"]).to_csv(
            prefix.parent / f"{prefix.name}_search.csv", index=False, encoding="utf-8-sig"
        )
        pd.DataFrame(report["evaluation_rows"]).to_csv(
            prefix.parent / f"{prefix.name}_windows.csv", index=False, encoding="utf-8-sig"
        )
        payload = std.success(report)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, str(prefix.with_suffix(".json")))


if __name__ == "__main__":
    main()
