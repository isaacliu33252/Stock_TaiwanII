#!/usr/bin/env python3
"""Aggregate GroupA+ 500k zero-inverse seed sensitivity runs."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.build_group_a_plus_1m_step_count_guarded_shadow_review import (
    DEFAULT_100K,
    _curve,
    _load_result,
    _metrics,
    _resolve,
)


DEFAULT_SEED_RUNS = {
    "42": PROJECT_ROOT / "results/group_a_backtest_20250101_20260814_20260815_104759.json",
    "7": PROJECT_ROOT / "results/group_a_backtest_20250101_20260814_20260815_112823.json",
    "13": PROJECT_ROOT / "results/group_a_backtest_20250101_20260814_20260815_115227.json",
    "21": PROJECT_ROOT / "results/group_a_backtest_20250101_20260814_20260815_121626.json",
}
DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "report/group_a_plus/latest/ppo_500k_seed_sensitivity_aggregation.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/ppo_500k_seed_sensitivity_aggregation.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/ppo_500k_seed_sensitivity_aggregation/history"
INVERSE_TICKER = "00632R.TW"


def _daily_max_inverse(item: dict[str, Any]) -> dict[str, Any]:
    daily = list(item["result"].get("daily_target_weight_history") or [])
    fields = [
        "decision_weights",
        "execution_pre_trade_weights",
        "base_target_weights",
        "candidate_target_weights",
        "final_target_weights",
        "close_weights",
    ]
    max_by_field: dict[str, float] = {}
    for field in fields:
        max_by_field[field] = max(
            (float((row.get(field) or {}).get(INVERSE_TICKER, 0.0) or 0.0) for row in daily),
            default=0.0,
        )
    pva_max = max(
        (
            float(((row.get("target_weights") or {}).get(INVERSE_TICKER, 0.0) or 0.0))
            for row in item["result"].get("pva_sigmoid_history", [])
        ),
        default=0.0,
    )
    forced = list(item["result"].get("inverse_forced_exit_history") or [])
    daily_max = max(max_by_field.values() or [0.0])
    return {
        "complete_daily_exposure_log_available": bool(daily),
        "daily_log_rows": len(daily),
        "daily_log_max_00632r_by_field": max_by_field,
        "daily_log_max_00632r_weight": daily_max,
        "pva_logged_max_00632r_target": pva_max,
        "forced_exit_count": len(forced),
        "governance_status": "blocked" if max(daily_max, pva_max, float(len(forced))) > 1e-12 else "cleared",
    }


def _window_return(curve: pd.Series, start: str, end: str) -> float | None:
    window = curve.loc[pd.Timestamp(start) : pd.Timestamp(end)]
    if len(window) < 2:
        return None
    return float(window.iloc[-1] / window.iloc[0] - 1.0)


def _stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "max": None, "mean": None, "std": None}
    return {
        "min": min(values),
        "max": max(values),
        "mean": mean(values),
        "std": pstdev(values) if len(values) > 1 else 0.0,
    }


def build_report(
    *,
    path_100k: Path,
    seed_runs: dict[str, Path],
    as_of: str,
) -> dict[str, Any]:
    baseline = _load_result(path_100k)
    baseline_metrics = _metrics(baseline)
    baseline_curve = _curve(baseline)
    baseline_windows = {
        "full_oos_2025_2026": _window_return(baseline_curve, "2025-01-02", "2026-08-14"),
        "2026q3_partial": _window_return(baseline_curve, "2026-07-01", "2026-08-14"),
        "issue_20260804_20260814": _window_return(baseline_curve, "2026-08-04", "2026-08-14"),
    }

    runs: dict[str, Any] = {}
    final_values: list[float] = []
    sharpes: list[float] = []
    mdds: list[float] = []
    vols: list[float] = []
    full_win_count = q3_win_count = issue_win_count = 0
    inverse_block_count = 0
    for seed, path in sorted(seed_runs.items(), key=lambda kv: int(kv[0])):
        item = _load_result(path)
        metrics = _metrics(item)
        curve = _curve(item)
        windows = {
            "full_oos_2025_2026": _window_return(curve, "2025-01-02", "2026-08-14"),
            "2026q3_partial": _window_return(curve, "2026-07-01", "2026-08-14"),
            "issue_20260804_20260814": _window_return(curve, "2026-08-04", "2026-08-14"),
        }
        comparisons = {
            name: (
                None
                if value is None or baseline_windows[name] is None
                else float(value - baseline_windows[name])
            )
            for name, value in windows.items()
        }
        if comparisons["full_oos_2025_2026"] is not None and comparisons["full_oos_2025_2026"] > 0:
            full_win_count += 1
        if comparisons["2026q3_partial"] is not None and comparisons["2026q3_partial"] > 0:
            q3_win_count += 1
        if comparisons["issue_20260804_20260814"] is not None and comparisons["issue_20260804_20260814"] > 0:
            issue_win_count += 1
        inverse = _daily_max_inverse(item)
        if inverse["governance_status"] == "blocked":
            inverse_block_count += 1
        final_values.append(float(metrics["final_value"]))
        sharpes.append(float(metrics["sharpe"]))
        mdds.append(float(metrics["max_drawdown"]))
        vols.append(float(metrics["volatility"]))
        runs[str(seed)] = {
            "path": str(path),
            "metrics": metrics,
            "windows": windows,
            "vs_100k": comparisons,
            "inverse_governance": inverse,
        }

    blockers: list[str] = []
    warnings: list[str] = []
    seed_count = len(seed_runs)
    if inverse_block_count:
        blockers.append("at_least_one_seed_has_00632r_exposure")
    if q3_win_count < seed_count:
        blockers.append("not_all_seeds_beat_100k_in_2026q3_partial")
    if issue_win_count < seed_count:
        blockers.append("not_all_seeds_beat_100k_in_20260804_issue_window")
    if min(sharpes or [0.0]) < float(baseline_metrics["sharpe"]):
        blockers.append("at_least_one_seed_sharpe_below_100k")
    if min(mdds or [0.0]) < float(baseline_metrics["max_drawdown"]):
        blockers.append("at_least_one_seed_mdd_worse_than_100k")
    if max(vols or [0.0]) > float(baseline_metrics["volatility"]):
        warnings.append("seed_volatility_above_100k")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_ppo_500k_seed_sensitivity_aggregation",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked_for_latest_replacement" if blockers else "shadow_review",
        "policy": "research_only_no_latest_replacement",
        "baseline_100k": {
            "path": str(path_100k),
            "metrics": baseline_metrics,
            "windows": baseline_windows,
        },
        "seed_runs": runs,
        "summary": {
            "seed_count": seed_count,
            "full_oos_win_count_vs_100k": full_win_count,
            "q3_win_count_vs_100k": q3_win_count,
            "issue_window_win_count_vs_100k": issue_win_count,
            "inverse_block_count": inverse_block_count,
            "final_value": _stats(final_values),
            "sharpe": _stats(sharpes),
            "max_drawdown": _stats(mdds),
            "volatility": _stats(vols),
        },
        "decision": {
            "decision": "keep_500k_zero_inverse_shadow_only",
            "replace_latest": False,
            "tune_latest": False,
            "promote_500k_to_production": False,
            "blocking_reasons": blockers,
            "warning_reasons": warnings,
        },
    }


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2%}"


def _write_md(report: dict[str, Any], path: Path) -> None:
    baseline = report["baseline_100k"]["metrics"]
    summary = report["summary"]
    decision = report["decision"]
    lines = [
        "# GroupA+ PPO 500k Seed Sensitivity Aggregation",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Status: `{report['status']}`",
        f"- Decision: `{decision['decision']}`",
        f"- Policy: `{report['policy']}`",
        "",
        "## Baseline",
        "",
        f"- 100k final: `{baseline['final_value']:,.2f}`",
        f"- 100k Sharpe: `{baseline['sharpe']:.3f}`",
        f"- 100k MDD: `{baseline['max_drawdown']:.2%}`",
        f"- 100k volatility: `{baseline['volatility']:.2%}`",
        "",
        "## Seed Summary",
        "",
        f"- Seed count: `{summary['seed_count']}`",
        f"- Full OOS wins vs 100k: `{summary['full_oos_win_count_vs_100k']}`",
        f"- 2026Q3 wins vs 100k: `{summary['q3_win_count_vs_100k']}`",
        f"- Issue-window wins vs 100k: `{summary['issue_window_win_count_vs_100k']}`",
        f"- Inverse governance blocks: `{summary['inverse_block_count']}`",
        f"- Final value range: `{summary['final_value']['min']:,.2f}` to `{summary['final_value']['max']:,.2f}`",
        f"- Sharpe range: `{summary['sharpe']['min']:.3f}` to `{summary['sharpe']['max']:.3f}`",
        f"- MDD range: `{summary['max_drawdown']['min']:.2%}` to `{summary['max_drawdown']['max']:.2%}`",
        f"- Volatility range: `{summary['volatility']['min']:.2%}` to `{summary['volatility']['max']:.2%}`",
        "",
        "## Seed Runs",
        "",
        "| Seed | Final | Sharpe | MDD | Vol | Full vs 100k | Q3 vs 100k | Issue vs 100k | 00632R max |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for seed, row in sorted(report["seed_runs"].items(), key=lambda kv: int(kv[0])):
        metrics = row["metrics"]
        inv = row["inverse_governance"]
        lines.append(
            f"| {seed} | {metrics['final_value']:,.2f} | {metrics['sharpe']:.3f} | "
            f"{metrics['max_drawdown']:.2%} | {metrics['volatility']:.2%} | "
            f"{_pct(row['vs_100k']['full_oos_2025_2026'])} | "
            f"{_pct(row['vs_100k']['2026q3_partial'])} | "
            f"{_pct(row['vs_100k']['issue_20260804_20260814'])} | "
            f"{inv['daily_log_max_00632r_weight']:.4f} |"
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"- Replace latest: `{decision['replace_latest']}`",
            f"- Tune latest: `{decision['tune_latest']}`",
            f"- Promote 500k to production: `{decision['promote_500k_to_production']}`",
            f"- Blocking reasons: `{decision['blocking_reasons']}`",
            f"- Warning reasons: `{decision['warning_reasons']}`",
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
        (history_dir / f"ppo_500k_seed_sensitivity_aggregation_{stamp}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backtest-100k", default=str(DEFAULT_100K))
    for seed, path in DEFAULT_SEED_RUNS.items():
        parser.add_argument(f"--seed-{seed}", default=str(path))
    parser.add_argument("--as-of", default=datetime.now().date().isoformat())
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    seed_runs = {
        seed: _resolve(getattr(args, f"seed_{seed}"))
        for seed in DEFAULT_SEED_RUNS
    }
    report = build_report(path_100k=_resolve(args.backtest_100k), seed_runs=seed_runs, as_of=str(args.as_of))
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
                "full_oos_wins_vs_100k": report["summary"]["full_oos_win_count_vs_100k"],
                "q3_wins_vs_100k": report["summary"]["q3_win_count_vs_100k"],
                "issue_wins_vs_100k": report["summary"]["issue_window_win_count_vs_100k"],
                "output_json": str(_resolve(args.output_json)),
                "output_md": str(_resolve(args.output_md)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
