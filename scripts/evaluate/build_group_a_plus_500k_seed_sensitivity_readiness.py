#!/usr/bin/env python3
"""Build a readiness/blocker report for GroupA+ 500k seed sensitivity."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.build_group_a_plus_1m_step_count_guarded_shadow_review import (
    DEFAULT_100K,
    DEFAULT_500K,
    _load_result,
    _metrics,
    _resolve,
)
from scripts.evaluate.build_group_a_plus_500k_zero_inverse_replay_review import DEFAULT_ZERO_500K


DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "report/group_a_plus/latest/ppo_500k_seed_sensitivity_readiness.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/ppo_500k_seed_sensitivity_readiness.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/ppo_500k_seed_sensitivity_readiness/history"
DEFAULT_REQUIRED_SEEDS = [7, 13, 21]


def _model_path_for_seed(seed: int) -> Path:
    return PROJECT_ROOT / "models" / "portfolio" / f"group_a_500k_zero_inverse_s{seed:02d}.zip"


def _result_candidates_for_seed(seed: int) -> list[Path]:
    patterns = [
        f"group_a_500k_zero_inverse_s{seed:02d}",
        f"seed{seed}",
        f"s{seed:02d}",
    ]
    out: list[Path] = []
    for path in (PROJECT_ROOT / "results").glob("*.json"):
        name = path.name.lower()
        if "500k" in name and any(pattern in name for pattern in patterns):
            out.append(path)
    return sorted(out)


def _train_command(seed: int) -> str:
    model_name = f"group_a_500k_zero_inverse_s{seed:02d}"
    return (
        ".venv/bin/python train_dual_group_2024_2026.py "
        "--xlsx taiwan_stock_20260516_group.xlsx "
        "--group-filter group_a "
        f"--group-a-model-name {model_name} "
        "--group-a-profile default "
        "--group-a-action-schema triplet_v4 "
        "--group-a-enable-dca "
        "--group-a-enable-pva-sigmoid "
        "--group-a-00631l-max-weight 0.30 "
        "--group-a-00632r-max-weight 0.0 "
        "--group-a-pva-inverse-hedge-budget 0.0 "
        "--initial-cash 1000000 "
        "--train-start 2020-01-01 "
        "--train-end 2024-12-31 "
        "--backtest-start 2025-01-01 "
        "--backtest-end 2026-08-14 "
        "--timesteps 500000 "
        f"--seed {seed}"
    )


def build_report(
    *,
    path_100k: Path,
    path_500k: Path,
    path_500k_zero_inverse: Path,
    required_seeds: list[int],
    as_of: str,
) -> dict[str, Any]:
    items = {
        "100k_seed42": _load_result(path_100k),
        "500k_original_seed42": _load_result(path_500k),
        "500k_zero_inverse_seed42": _load_result(path_500k_zero_inverse),
    }
    metrics = {name: _metrics(item) for name, item in items.items()}
    seed_inventory: dict[str, Any] = {}
    missing: list[int] = []
    for seed in required_seeds:
        model_path = _model_path_for_seed(seed)
        result_candidates = _result_candidates_for_seed(seed)
        present = model_path.exists() and bool(result_candidates)
        if not present:
            missing.append(seed)
        seed_inventory[str(seed)] = {
            "seed": seed,
            "model_path": str(model_path),
            "model_exists": model_path.exists(),
            "result_candidates": [str(path) for path in result_candidates],
            "complete_for_sensitivity": present,
            "train_command": _train_command(seed),
        }

    baseline = metrics["100k_seed42"]
    zero = metrics["500k_zero_inverse_seed42"]
    seed42_delta = {
        "final_value": zero["final_value"] - baseline["final_value"],
        "sharpe": zero["sharpe"] - baseline["sharpe"],
        "max_drawdown": zero["max_drawdown"] - baseline["max_drawdown"],
        "volatility": zero["volatility"] - baseline["volatility"],
        "fees_paid_estimate": zero["fees_paid_estimate"] - baseline["fees_paid_estimate"],
    }
    blockers = []
    if missing:
        blockers.append("missing_required_independent_500k_zero_inverse_seed_runs")
    if seed42_delta["volatility"] > 0:
        blockers.append("seed42_zero_inverse_volatility_above_100k")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_ppo_500k_seed_sensitivity_readiness",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked_for_seed_sensitivity" if blockers else "ready_for_seed_sensitivity_analysis",
        "policy": "research_only_no_latest_replacement",
        "inputs": {name: item["path"] for name, item in items.items()},
        "required_independent_seeds": required_seeds,
        "seed_inventory": seed_inventory,
        "missing_required_seeds": missing,
        "seed42_reference_metrics": metrics,
        "seed42_zero_inverse_minus_100k": seed42_delta,
        "decision": {
            "decision": "seed_sensitivity_not_complete",
            "replace_latest": False,
            "tune_latest": False,
            "promote_500k_to_production": False,
            "blocking_reasons": blockers,
            "required_next_evidence": [
                "train_500k_zero_inverse_seed_7",
                "train_500k_zero_inverse_seed_13",
                "train_500k_zero_inverse_seed_21",
                "aggregate_seed_distribution",
                "require_no_seed_underperforms_100k_in_2026q3_or_issue_window",
            ],
        },
    }


def _write_md(report: dict[str, Any], path: Path) -> None:
    delta = report["seed42_zero_inverse_minus_100k"]
    decision = report["decision"]
    lines = [
        "# GroupA+ PPO 500k Seed Sensitivity Readiness",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Status: `{report['status']}`",
        f"- Decision: `{decision['decision']}`",
        f"- Policy: `{report['policy']}`",
        "",
        "## Seed 42 Reference",
        "",
        f"- Zero-inverse final delta vs 100k: `{delta['final_value']:,.2f}`",
        f"- Zero-inverse Sharpe delta vs 100k: `{delta['sharpe']:.4f}`",
        f"- Zero-inverse MDD delta vs 100k: `{delta['max_drawdown']:.2%}`",
        f"- Zero-inverse volatility delta vs 100k: `{delta['volatility']:.2%}`",
        f"- Zero-inverse fee delta vs 100k: `{delta['fees_paid_estimate']:,.2f}`",
        "",
        "## Required Seeds",
        "",
        "| Seed | Model exists | Result exists | Complete |",
        "|---:|---:|---:|---:|",
    ]
    for seed in report["required_independent_seeds"]:
        row = report["seed_inventory"][str(seed)]
        lines.append(
            f"| {seed} | `{row['model_exists']}` | "
            f"`{bool(row['result_candidates'])}` | `{row['complete_for_sensitivity']}` |"
        )
    lines.extend(
        [
            "",
            "## Commands To Run",
            "",
        ]
    )
    for seed in report["required_independent_seeds"]:
        lines.extend(
            [
                f"Seed `{seed}`:",
                "",
                "```text",
                report["seed_inventory"][str(seed)]["train_command"],
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "## Decision",
            "",
            f"- Replace latest: `{decision['replace_latest']}`",
            f"- Tune latest: `{decision['tune_latest']}`",
            f"- Promote 500k to production: `{decision['promote_500k_to_production']}`",
            f"- Blocking reasons: `{decision['blocking_reasons']}`",
            f"- Missing required seeds: `{report['missing_required_seeds']}`",
            "",
            "No latest strategy, live signal, execution plan, or order file was changed.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_report(report: dict[str, Any], output_json: Path, output_md: Path, history_dir: Path | None) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_md(report, output_md)
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = str(report["as_of"]).replace("-", "")
        (history_dir / f"ppo_500k_seed_sensitivity_readiness_{stamp}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backtest-100k", default=str(DEFAULT_100K))
    parser.add_argument("--backtest-500k", default=str(DEFAULT_500K))
    parser.add_argument("--backtest-500k-zero-inverse", default=str(DEFAULT_ZERO_500K))
    parser.add_argument("--required-seeds", default="7,13,21")
    parser.add_argument("--as-of", default=datetime.now().date().isoformat())
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    required_seeds = [int(seed.strip()) for seed in str(args.required_seeds).split(",") if seed.strip()]
    report = build_report(
        path_100k=_resolve(args.backtest_100k),
        path_500k=_resolve(args.backtest_500k),
        path_500k_zero_inverse=_resolve(args.backtest_500k_zero_inverse),
        required_seeds=required_seeds,
        as_of=str(args.as_of),
    )
    write_report(
        report,
        _resolve(args.output_json),
        _resolve(args.output_md),
        None if args.no_history else _resolve(args.history_dir),
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "decision": report["decision"]["decision"],
                "missing_required_seeds": report["missing_required_seeds"],
                "output_json": str(_resolve(args.output_json)),
                "output_md": str(_resolve(args.output_md)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
