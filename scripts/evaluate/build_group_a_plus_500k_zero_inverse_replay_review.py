#!/usr/bin/env python3
"""Review a 500k GroupA+ replay with 00632R fully disabled."""

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
    _curve,
    _inverse_exposure,
    _load_result,
    _metrics,
    _pct,
    _period_return,
    _quarter_returns,
    _resolve,
)


DEFAULT_ZERO_500K = PROJECT_ROOT / "results/group_a_backtest_20250101_20260814_20260815_104759.json"
DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "report/group_a_plus/latest/ppo_500k_zero_inverse_replay_review.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/ppo_500k_zero_inverse_replay_review.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/ppo_500k_zero_inverse_replay_review/history"
INVERSE_TICKER = "00632R.TW"


def _inverse_exposure_with_daily_log(item: dict[str, Any]) -> dict[str, Any]:
    exposure = _inverse_exposure(item)
    daily = list(item["result"].get("daily_target_weight_history") or [])
    if not daily:
        return exposure

    field_names = [
        "decision_weights",
        "execution_pre_trade_weights",
        "base_target_weights",
        "candidate_target_weights",
        "final_target_weights",
        "close_weights",
    ]
    max_by_field: dict[str, float] = {}
    touch_dates: set[str] = set()
    for field in field_names:
        max_value = 0.0
        for row in daily:
            weights = row.get(field) or {}
            value = float(weights.get(INVERSE_TICKER, 0.0) or 0.0)
            max_value = max(max_value, value)
            if value > 1e-12:
                touch_dates.add(str(row.get("execution_date") or row.get("decision_date")))
        max_by_field[field] = max_value

    max_daily_weight = max(max_by_field.values() or [0.0])
    exposure.update(
        {
            "complete_daily_exposure_log_available": True,
            "daily_log_rows": len(daily),
            "daily_log_max_00632r_by_field": max_by_field,
            "daily_log_00632r_touch_count": len(touch_dates),
            "daily_log_first_00632r_touch_date": min(touch_dates) if touch_dates else None,
            "daily_log_last_00632r_touch_date": max(touch_dates) if touch_dates else None,
            "daily_log_max_00632r_weight": max_daily_weight,
            "governance_status": "blocked" if max_daily_weight > 1e-12 else exposure["governance_status"],
        }
    )
    return exposure


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
    metrics = {name: _metrics(item) for name, item in items.items()}
    quarter_returns = {name: _quarter_returns(curve) for name, curve in curves.items()}
    inverse = {name: _inverse_exposure_with_daily_log(item) for name, item in items.items()}
    focus = {
        "2026Q3": {name: quarter_returns[name].get("2026Q3") for name in quarter_returns},
        "2026_08_04_to_2026_08_14": {
            name: _period_return(curve, "2026-08-04", "2026-08-14")
            for name, curve in curves.items()
        },
    }

    m100 = metrics["100k"]
    m500 = metrics["500k"]
    mz = metrics["500k_zero_inverse"]
    deltas = {
        "500k_zero_inverse_minus_100k": {
            "final_value": mz["final_value"] - m100["final_value"],
            "sharpe": mz["sharpe"] - m100["sharpe"],
            "max_drawdown": mz["max_drawdown"] - m100["max_drawdown"],
            "volatility": mz["volatility"] - m100["volatility"],
            "fees_paid_estimate": mz["fees_paid_estimate"] - m100["fees_paid_estimate"],
        },
        "500k_zero_inverse_minus_500k": {
            "final_value": mz["final_value"] - m500["final_value"],
            "sharpe": mz["sharpe"] - m500["sharpe"],
            "max_drawdown": mz["max_drawdown"] - m500["max_drawdown"],
            "volatility": mz["volatility"] - m500["volatility"],
            "fees_paid_estimate": mz["fees_paid_estimate"] - m500["fees_paid_estimate"],
        },
    }

    zero_inverse_cleared = inverse["500k_zero_inverse"]["governance_status"] != "blocked"
    still_better_than_100k = mz["final_value"] > m100["final_value"] and mz["sharpe"] > m100["sharpe"]
    retains_500k_edge = mz["final_value"] >= m500["final_value"] and mz["sharpe"] >= m500["sharpe"]
    q3_weaker_than_100k = (
        focus["2026Q3"]["500k_zero_inverse"] is not None
        and focus["2026Q3"]["100k"] is not None
        and float(focus["2026Q3"]["500k_zero_inverse"]) < float(focus["2026Q3"]["100k"])
    )
    issue_weaker_than_100k = (
        focus["2026_08_04_to_2026_08_14"]["500k_zero_inverse"] is not None
        and focus["2026_08_04_to_2026_08_14"]["100k"] is not None
        and float(focus["2026_08_04_to_2026_08_14"]["500k_zero_inverse"])
        < float(focus["2026_08_04_to_2026_08_14"]["100k"])
    )

    blockers: list[str] = []
    warnings: list[str] = []
    if not zero_inverse_cleared:
        blockers.append("500k_zero_inverse_replay_still_contains_00632r_exposure")
    if not retains_500k_edge:
        blockers.append("zero_inverse_replay_does_not_retain_original_500k_edge")
    if q3_weaker_than_100k:
        blockers.append("zero_inverse_replay_underperforms_100k_in_2026q3")
    if issue_weaker_than_100k:
        blockers.append("zero_inverse_replay_underperforms_100k_in_20260804_issue_window")
    if deltas["500k_zero_inverse_minus_100k"]["volatility"] > 0:
        warnings.append("zero_inverse_replay_volatility_above_100k")
    if not inverse["500k_zero_inverse"]["complete_daily_exposure_log_available"]:
        warnings.append("complete_daily_target_weight_log_missing")

    decision = "keep_500k_zero_inverse_shadow_only"
    if zero_inverse_cleared and still_better_than_100k and not blockers:
        decision = "candidate_for_multi_window_seed_shadow"

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_ppo_500k_zero_inverse_replay_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked_for_latest_replacement" if blockers else "shadow_review",
        "policy": "research_only_no_latest_replacement",
        "inputs": {name: item["path"] for name, item in items.items()},
        "overall_metrics": metrics,
        "deltas": deltas,
        "focus_windows": focus,
        "inverse_etf_governance": inverse,
        "decision": {
            "decision": decision,
            "zero_inverse_governance_cleared": zero_inverse_cleared,
            "still_better_than_100k": still_better_than_100k,
            "retains_original_500k_edge": retains_500k_edge,
            "replace_latest": False,
            "tune_latest": False,
            "promote_500k_zero_inverse_to_production": False,
            "blocking_reasons": blockers,
            "warning_reasons": warnings,
            "required_next_evidence": [
                "complete_daily_target_weight_log",
                "multi_window_oos_replay",
                "seed_sensitivity_check",
                "incident_window_resilience_improvement",
            ],
        },
    }


def _write_md(report: dict[str, Any], path: Path) -> None:
    metrics = report["overall_metrics"]
    dz100 = report["deltas"]["500k_zero_inverse_minus_100k"]
    dz500 = report["deltas"]["500k_zero_inverse_minus_500k"]
    focus = report["focus_windows"]
    inverse = report["inverse_etf_governance"]
    decision = report["decision"]
    lines = [
        "# GroupA+ PPO 500k Zero-Inverse Replay Review",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Status: `{report['status']}`",
        f"- Decision: `{decision['decision']}`",
        f"- Policy: `{report['policy']}`",
        "",
        "## Overall Metrics",
        "",
        "| Run | Final value | Sharpe | MDD | Vol | Trades | Fees |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ("100k", "500k", "500k_zero_inverse"):
        row = metrics[name]
        lines.append(
            f"| {name} | {row['final_value']:,.2f} | {row['sharpe']:.3f} | "
            f"{row['max_drawdown']:.2%} | {row['volatility']:.2%} | "
            f"{row['num_trades']} | {row['fees_paid_estimate']:,.2f} |"
        )
    lines.extend(
        [
            "",
            "## Zero-Inverse Delta",
            "",
            f"- Vs 100k final value: `{dz100['final_value']:,.2f}`",
            f"- Vs 100k Sharpe: `{dz100['sharpe']:.4f}`",
            f"- Vs 100k MDD: `{dz100['max_drawdown']:.2%}`",
            f"- Vs 100k volatility: `{dz100['volatility']:.2%}`",
            f"- Vs 100k fees: `{dz100['fees_paid_estimate']:,.2f}`",
            f"- Vs original 500k final value: `{dz500['final_value']:,.2f}`",
            f"- Vs original 500k Sharpe: `{dz500['sharpe']:.4f}`",
            f"- Vs original 500k MDD: `{dz500['max_drawdown']:.2%}`",
            f"- Vs original 500k volatility: `{dz500['volatility']:.2%}`",
            f"- Vs original 500k fees: `{dz500['fees_paid_estimate']:,.2f}`",
            "",
            "## Focus Windows",
            "",
            f"- 2026Q3 100k: `{_pct(focus['2026Q3']['100k'])}`",
            f"- 2026Q3 500k: `{_pct(focus['2026Q3']['500k'])}`",
            f"- 2026Q3 500k zero-inverse: `{_pct(focus['2026Q3']['500k_zero_inverse'])}`",
            f"- 2026-08-04 to 2026-08-14 100k: `{_pct(focus['2026_08_04_to_2026_08_14']['100k'])}`",
            f"- 2026-08-04 to 2026-08-14 500k: `{_pct(focus['2026_08_04_to_2026_08_14']['500k'])}`",
            f"- 2026-08-04 to 2026-08-14 500k zero-inverse: `{_pct(focus['2026_08_04_to_2026_08_14']['500k_zero_inverse'])}`",
            "",
            "## 00632R Governance",
            "",
        ]
    )
    for name in ("100k", "500k", "500k_zero_inverse"):
        row = inverse[name]
        lines.append(
            f"- {name}: status `{row['governance_status']}`, "
            f"PVA touch count `{row['pva_logged_touch_count']}`, "
            f"PVA max target `{row['pva_logged_max_target_weight']:.4f}`, "
            f"forced exits `{row['forced_exit_count']}`, "
            f"daily log `{row['complete_daily_exposure_log_available']}`"
        )
        if row.get("complete_daily_exposure_log_available"):
            lines.append(
                f"  - daily rows `{row.get('daily_log_rows')}`, "
                f"daily max 00632R `{row.get('daily_log_max_00632r_weight', 0.0):.4f}`"
            )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"- Zero-inverse governance cleared: `{decision['zero_inverse_governance_cleared']}`",
            f"- Still better than 100k: `{decision['still_better_than_100k']}`",
            f"- Retains original 500k edge: `{decision['retains_original_500k_edge']}`",
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
        (history_dir / f"ppo_500k_zero_inverse_replay_review_{stamp}.json").write_text(
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
                "zero_inverse_governance_cleared": report["decision"]["zero_inverse_governance_cleared"],
                "still_better_than_100k": report["decision"]["still_better_than_100k"],
                "retains_original_500k_edge": report["decision"]["retains_original_500k_edge"],
                "output_json": str(_resolve(args.output_json)),
                "output_md": str(_resolve(args.output_md)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
