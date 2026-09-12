#!/usr/bin/env python3
"""Build a multi-window OOS review for the GroupA+ 500k zero-inverse replay."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.build_group_a_plus_1m_step_count_guarded_shadow_review import (
    DEFAULT_100K,
    DEFAULT_500K,
    _curve,
    _load_result,
    _resolve,
)
from scripts.evaluate.build_group_a_plus_500k_zero_inverse_replay_review import DEFAULT_ZERO_500K


DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "report/group_a_plus/latest/ppo_500k_multi_window_oos_review.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/ppo_500k_multi_window_oos_review.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/ppo_500k_multi_window_oos_review/history"

OOS_WINDOWS = {
    "full_oos_2025_2026": ("2025-01-02", "2026-08-14"),
    "2025_h1": ("2025-01-02", "2025-06-30"),
    "2025_h2": ("2025-07-01", "2025-12-31"),
    "2026_h1": ("2026-01-01", "2026-06-30"),
    "2026q3_partial": ("2026-07-01", "2026-08-14"),
    "issue_20260804_20260814": ("2026-08-04", "2026-08-14"),
}
REQUESTED_BUT_NOT_OOS = {
    "2020_covid": {
        "start": "2020-02-01",
        "end": "2020-04-30",
        "reason": "inside_2020_2024_training_window_for_these_checkpoints",
    },
    "2022_rate_hike": {
        "start": "2022-01-01",
        "end": "2022-12-31",
        "reason": "inside_2020_2024_training_window_for_these_checkpoints",
    },
    "2024_2026": {
        "start": "2024-01-01",
        "end": "2026-08-14",
        "reason": "starts_inside_training_window; use 2025_2026 for strict OOS",
    },
}


def _window_metrics(curve: pd.Series, start: str, end: str) -> dict[str, Any]:
    window = curve.loc[pd.Timestamp(start) : pd.Timestamp(end)]
    if len(window) < 2:
        return {
            "available": False,
            "points": int(len(window)),
            "start_value": None,
            "end_value": None,
            "return": None,
            "max_drawdown": None,
            "volatility": None,
            "sharpe": None,
        }
    returns = window.pct_change().replace([float("inf"), float("-inf")], pd.NA).dropna()
    running_peak = window.cummax()
    drawdown = window / running_peak - 1.0
    vol = float(returns.std(ddof=1) * (252 ** 0.5)) if len(returns) >= 2 else 0.0
    sharpe = (
        float((returns.mean() / returns.std(ddof=1)) * (252 ** 0.5))
        if len(returns) >= 2 and float(returns.std(ddof=1)) > 0.0
        else 0.0
    )
    return {
        "available": True,
        "points": int(len(window)),
        "start_date": window.index[0].date().isoformat(),
        "end_date": window.index[-1].date().isoformat(),
        "start_value": float(window.iloc[0]),
        "end_value": float(window.iloc[-1]),
        "return": float(window.iloc[-1] / window.iloc[0] - 1.0),
        "max_drawdown": float(drawdown.min()),
        "volatility": vol,
        "sharpe": sharpe,
    }


def _cmp(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    if not candidate["available"] or not baseline["available"]:
        return {"available": False}
    return {
        "available": True,
        "return_delta": float(candidate["return"] - baseline["return"]),
        "max_drawdown_delta": float(candidate["max_drawdown"] - baseline["max_drawdown"]),
        "volatility_delta": float(candidate["volatility"] - baseline["volatility"]),
        "sharpe_delta": float(candidate["sharpe"] - baseline["sharpe"]),
    }


def build_report(
    *,
    path_100k: Path,
    path_500k: Path,
    path_500k_zero_inverse: Path,
    as_of: str,
) -> dict[str, Any]:
    items = {
        "100k": _load_result(path_100k),
        "500k": _load_result(path_500k),
        "500k_zero_inverse": _load_result(path_500k_zero_inverse),
    }
    curves = {name: _curve(item) for name, item in items.items()}
    windows: dict[str, Any] = {}
    zero_wins_vs_100k = 0
    zero_loses_vs_100k = 0
    zero_wins_vs_500k = 0
    zero_loses_vs_500k = 0
    for name, (start, end) in OOS_WINDOWS.items():
        metrics = {run: _window_metrics(curve, start, end) for run, curve in curves.items()}
        zero_vs_100 = _cmp(metrics["500k_zero_inverse"], metrics["100k"])
        zero_vs_500 = _cmp(metrics["500k_zero_inverse"], metrics["500k"])
        if zero_vs_100.get("available"):
            if zero_vs_100["return_delta"] > 0:
                zero_wins_vs_100k += 1
            else:
                zero_loses_vs_100k += 1
        if zero_vs_500.get("available"):
            if zero_vs_500["return_delta"] > 0:
                zero_wins_vs_500k += 1
            else:
                zero_loses_vs_500k += 1
        windows[name] = {
            "start": start,
            "end": end,
            "metrics": metrics,
            "zero_inverse_vs_100k": zero_vs_100,
            "zero_inverse_vs_original_500k": zero_vs_500,
        }

    blockers: list[str] = []
    warnings: list[str] = []
    if zero_loses_vs_100k > 0:
        blockers.append("500k_zero_inverse_loses_to_100k_in_at_least_one_oos_window")
    if zero_loses_vs_500k > 0:
        blockers.append("500k_zero_inverse_loses_to_original_500k_in_at_least_one_oos_window")
    for stress_name in ("2026q3_partial", "issue_20260804_20260814"):
        cmp100 = windows[stress_name]["zero_inverse_vs_100k"]
        if cmp100.get("available") and cmp100["return_delta"] < 0:
            blockers.append(f"500k_zero_inverse_underperforms_100k_in_{stress_name}")
    full_cmp = windows["full_oos_2025_2026"]["zero_inverse_vs_100k"]
    if full_cmp.get("available") and full_cmp["volatility_delta"] > 0:
        warnings.append("500k_zero_inverse_full_oos_volatility_above_100k")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_ppo_500k_multi_window_oos_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked_for_latest_replacement" if blockers else "shadow_review",
        "policy": "research_only_no_latest_replacement",
        "inputs": {name: item["path"] for name, item in items.items()},
        "oos_windows": windows,
        "requested_windows_not_counted_as_oos": REQUESTED_BUT_NOT_OOS,
        "summary": {
            "zero_inverse_oos_windows_beating_100k_by_return": zero_wins_vs_100k,
            "zero_inverse_oos_windows_losing_to_100k_by_return": zero_loses_vs_100k,
            "zero_inverse_oos_windows_beating_original_500k_by_return": zero_wins_vs_500k,
            "zero_inverse_oos_windows_losing_to_original_500k_by_return": zero_loses_vs_500k,
        },
        "decision": {
            "decision": "keep_500k_zero_inverse_shadow_only",
            "replace_latest": False,
            "tune_latest": False,
            "promote_500k_zero_inverse_to_production": False,
            "blocking_reasons": blockers,
            "warning_reasons": warnings,
            "required_next_evidence": [
                "seed_sensitivity_check",
                "optional_train_window_stress_replay_not_oos_for_2020_and_2022",
                "incident_window_resilience_improvement",
            ],
        },
    }


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2%}"


def _fmt_delta(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2%}"


def _write_md(report: dict[str, Any], path: Path) -> None:
    decision = report["decision"]
    lines = [
        "# GroupA+ PPO 500k Multi-Window OOS Review",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Status: `{report['status']}`",
        f"- Decision: `{decision['decision']}`",
        f"- Policy: `{report['policy']}`",
        "",
        "## Summary",
        "",
        f"- Zero-inverse wins vs 100k by return: `{report['summary']['zero_inverse_oos_windows_beating_100k_by_return']}`",
        f"- Zero-inverse losses vs 100k by return: `{report['summary']['zero_inverse_oos_windows_losing_to_100k_by_return']}`",
        f"- Zero-inverse wins vs original 500k by return: `{report['summary']['zero_inverse_oos_windows_beating_original_500k_by_return']}`",
        f"- Zero-inverse losses vs original 500k by return: `{report['summary']['zero_inverse_oos_windows_losing_to_original_500k_by_return']}`",
        "",
        "## OOS Windows",
        "",
        "| Window | 100k ret | 500k ret | 500k zero ret | Zero vs 100k | Zero vs 500k | Zero vol |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, row in report["oos_windows"].items():
        metrics = row["metrics"]
        z100 = row["zero_inverse_vs_100k"]
        z500 = row["zero_inverse_vs_original_500k"]
        lines.append(
            f"| {name} | {_pct(metrics['100k']['return'])} | "
            f"{_pct(metrics['500k']['return'])} | "
            f"{_pct(metrics['500k_zero_inverse']['return'])} | "
            f"{_fmt_delta(z100.get('return_delta'))} | "
            f"{_fmt_delta(z500.get('return_delta'))} | "
            f"{_pct(metrics['500k_zero_inverse']['volatility'])} |"
        )
    lines.extend(
        [
            "",
            "## Not Counted As OOS",
            "",
        ]
    )
    for name, row in report["requested_windows_not_counted_as_oos"].items():
        lines.append(f"- {name}: `{row['start']}` to `{row['end']}`, reason `{row['reason']}`")
    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"- Replace latest: `{decision['replace_latest']}`",
            f"- Tune latest: `{decision['tune_latest']}`",
            f"- Promote 500k zero-inverse to production: `{decision['promote_500k_zero_inverse_to_production']}`",
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
        (history_dir / f"ppo_500k_multi_window_oos_review_{stamp}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backtest-100k", default=str(DEFAULT_100K))
    parser.add_argument("--backtest-500k", default=str(DEFAULT_500K))
    parser.add_argument("--backtest-500k-zero-inverse", default=str(DEFAULT_ZERO_500K))
    parser.add_argument("--as-of", default=datetime.now().date().isoformat())
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(
        path_100k=_resolve(args.backtest_100k),
        path_500k=_resolve(args.backtest_500k),
        path_500k_zero_inverse=_resolve(args.backtest_500k_zero_inverse),
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
                "zero_inverse_wins_vs_100k": report["summary"]["zero_inverse_oos_windows_beating_100k_by_return"],
                "zero_inverse_losses_vs_100k": report["summary"]["zero_inverse_oos_windows_losing_to_100k_by_return"],
                "output_json": str(_resolve(args.output_json)),
                "output_md": str(_resolve(args.output_md)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
