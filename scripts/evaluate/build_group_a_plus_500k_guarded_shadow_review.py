#!/usr/bin/env python3
"""Build a guarded review for the GroupA+ PPO 500k-step candidate."""

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
    DEFAULT_1M,
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


DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "report/group_a_plus/latest/ppo_500k_guarded_shadow_review.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/ppo_500k_guarded_shadow_review.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/ppo_500k_guarded_shadow_review/history"


def _candidate_overfit_risk(
    *,
    deltas: dict[str, dict[str, float]],
    q3_2026: dict[str, float | None],
    issue_window: dict[str, float | None],
    inverse: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    delta = deltas["500k_minus_100k"]
    full_window_helpful = float(delta["final_value"]) > 0.0 and float(delta["sharpe"]) > 0.0
    q3_weaker = (
        q3_2026.get("500k") is not None
        and q3_2026.get("100k") is not None
        and float(q3_2026["500k"]) < float(q3_2026["100k"])
    )
    issue_weaker = (
        issue_window.get("500k") is not None
        and issue_window.get("100k") is not None
        and float(issue_window["500k"]) < float(issue_window["100k"])
    )
    signals = {
        "full_window_final_and_sharpe_improved": full_window_helpful,
        "q3_2026_weaker_than_100k": q3_weaker,
        "issue_window_weaker_than_100k": issue_weaker,
        "volatility_higher_than_100k": float(delta["volatility"]) > 0.0,
        "fees_higher_than_100k": float(delta["fees_paid_estimate"]) > 0.0,
        "saved_logs_include_00632r_exposure": inverse["500k"]["governance_status"] == "blocked",
        "complete_daily_exposure_log_missing": not bool(inverse["500k"]["complete_daily_exposure_log_available"]),
    }
    risk_score = sum(
        1
        for key, value in signals.items()
        if key != "full_window_final_and_sharpe_improved" and value
    )
    if full_window_helpful and risk_score >= 4:
        label = "high_overfit_or_window_specific_risk"
    elif full_window_helpful and risk_score >= 2:
        label = "moderate_overfit_or_window_specific_risk"
    elif full_window_helpful:
        label = "low_risk_but_unproven"
    else:
        label = "not_a_useful_candidate"
    return {
        "label": label,
        "risk_score": risk_score,
        "signals": signals,
        "interpretation": (
            "500k improves the full-window aggregate, but weaker 2026Q3 / "
            "incident-window behavior and saved 00632R exposure make it a "
            "shadow-only candidate until zero-inverse and complete daily "
            "exposure evidence exists."
            if full_window_helpful
            else "500k does not clear the full-window benefit threshold."
        ),
        "production_implication": "do_not_replace_latest",
    }


def build_report(
    *,
    path_100k: Path,
    path_500k: Path,
    path_1m: Path,
    as_of: str,
) -> dict[str, Any]:
    items = {
        "100k": _load_result(path_100k),
        "500k": _load_result(path_500k),
        "1m": _load_result(path_1m),
    }
    curves = {name: _curve(item) for name, item in items.items()}
    metrics = {name: _metrics(item) for name, item in items.items()}
    quarter_returns = {name: _quarter_returns(curve) for name, curve in curves.items()}
    inverse = {name: _inverse_exposure(item) for name, item in items.items()}

    m100 = metrics["100k"]
    m500 = metrics["500k"]
    m1m = metrics["1m"]
    deltas = {
        "500k_minus_100k": {
            "final_value": m500["final_value"] - m100["final_value"],
            "sharpe": m500["sharpe"] - m100["sharpe"],
            "max_drawdown": m500["max_drawdown"] - m100["max_drawdown"],
            "volatility": m500["volatility"] - m100["volatility"],
            "fees_paid_estimate": m500["fees_paid_estimate"] - m100["fees_paid_estimate"],
        },
        "1m_minus_500k": {
            "final_value": m1m["final_value"] - m500["final_value"],
            "sharpe": m1m["sharpe"] - m500["sharpe"],
            "max_drawdown": m1m["max_drawdown"] - m500["max_drawdown"],
            "volatility": m1m["volatility"] - m500["volatility"],
            "fees_paid_estimate": m1m["fees_paid_estimate"] - m500["fees_paid_estimate"],
        },
    }
    issue_window = {
        name: _period_return(curve, "2026-08-04", "2026-08-14")
        for name, curve in curves.items()
    }
    q3_2026 = {name: quarter_returns[name].get("2026Q3") for name in quarter_returns}
    risk = _candidate_overfit_risk(
        deltas=deltas,
        q3_2026=q3_2026,
        issue_window=issue_window,
        inverse=inverse,
    )

    blockers: list[str] = []
    warnings: list[str] = []
    if inverse["500k"]["governance_status"] == "blocked":
        blockers.append("500k_saved_logs_include_00632r_exposure")
    if q3_2026["500k"] is not None and q3_2026["100k"] is not None and q3_2026["500k"] < q3_2026["100k"]:
        blockers.append("500k_underperforms_100k_in_2026q3_downturn_proxy")
    if issue_window["500k"] is not None and issue_window["100k"] is not None and issue_window["500k"] < issue_window["100k"]:
        blockers.append("500k_underperforms_100k_in_20260804_issue_window")
    if not inverse["500k"]["complete_daily_exposure_log_available"]:
        warnings.append("complete_daily_00632r_exposure_log_missing")
    if deltas["500k_minus_100k"]["volatility"] > 0:
        warnings.append("500k_volatility_above_100k")

    helpful = m500["final_value"] > m100["final_value"] and m500["sharpe"] > m100["sharpe"]
    decision = "keep_500k_shadow_only"
    if helpful and not blockers:
        decision = "candidate_for_zero_inverse_multi_window_shadow"

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_ppo_500k_guarded_shadow_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked_for_latest_replacement" if blockers else "shadow_review",
        "policy": "research_only_no_latest_replacement",
        "inputs": {name: item["path"] for name, item in items.items()},
        "overall_metrics": metrics,
        "deltas": deltas,
        "quarter_returns": quarter_returns,
        "focus_windows": {
            "2026Q3": q3_2026,
            "2026_08_04_to_2026_08_14": issue_window,
        },
        "inverse_etf_governance": inverse,
        "candidate_risk": risk,
        "decision": {
            "decision": decision,
            "five_hundred_k_training_steps_helpful": helpful,
            "replace_latest": False,
            "tune_latest": False,
            "promote_500k_to_production": False,
            "blocking_reasons": blockers,
            "warning_reasons": [*warnings, f"candidate_risk:{risk['label']}"],
            "required_next_evidence": [
                "zero_00632r_replay_for_500k",
                "complete_daily_target_weight_log",
                "multi_window_oos_replay",
                "seed_sensitivity_check",
                "2026q3_and_20260804_window_resilience_improvement",
            ],
        },
    }


def _write_md(report: dict[str, Any], path: Path) -> None:
    metrics = report["overall_metrics"]
    delta = report["deltas"]["500k_minus_100k"]
    one_m_delta = report["deltas"]["1m_minus_500k"]
    decision = report["decision"]
    focus = report["focus_windows"]
    inverse = report["inverse_etf_governance"]
    risk = report["candidate_risk"]
    lines = [
        "# GroupA+ PPO 500k Guarded Shadow Review",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Status: `{report['status']}`",
        f"- Decision: `{decision['decision']}`",
        f"- Policy: `{report['policy']}`",
        "",
        "## Overall Metrics",
        "",
        "| Steps | Final value | Sharpe | MDD | Vol | Trades | Fees |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ("100k", "500k", "1m"):
        row = metrics[name]
        lines.append(
            f"| {name} | {row['final_value']:,.2f} | {row['sharpe']:.3f} | "
            f"{row['max_drawdown']:.2%} | {row['volatility']:.2%} | "
            f"{row['num_trades']} | {row['fees_paid_estimate']:,.2f} |"
        )
    lines.extend(
        [
            "",
            "## 500k Delta Vs 100k",
            "",
            f"- Final value: `{delta['final_value']:,.2f}`",
            f"- Sharpe: `{delta['sharpe']:.4f}`",
            f"- MDD: `{delta['max_drawdown']:.2%}`",
            f"- Volatility: `{delta['volatility']:.2%}`",
            f"- Fees: `{delta['fees_paid_estimate']:,.2f}`",
            "",
            "## 1M Delta Vs 500k",
            "",
            f"- Final value: `{one_m_delta['final_value']:,.2f}`",
            f"- Sharpe: `{one_m_delta['sharpe']:.4f}`",
            f"- MDD: `{one_m_delta['max_drawdown']:.2%}`",
            f"- Volatility: `{one_m_delta['volatility']:.2%}`",
            f"- Fees: `{one_m_delta['fees_paid_estimate']:,.2f}`",
            "",
            "## Focus Windows",
            "",
            f"- 2026Q3 100k: `{_pct(focus['2026Q3']['100k'])}`",
            f"- 2026Q3 500k: `{_pct(focus['2026Q3']['500k'])}`",
            f"- 2026Q3 1M: `{_pct(focus['2026Q3']['1m'])}`",
            f"- 2026-08-04 to 2026-08-14 100k: `{_pct(focus['2026_08_04_to_2026_08_14']['100k'])}`",
            f"- 2026-08-04 to 2026-08-14 500k: `{_pct(focus['2026_08_04_to_2026_08_14']['500k'])}`",
            f"- 2026-08-04 to 2026-08-14 1M: `{_pct(focus['2026_08_04_to_2026_08_14']['1m'])}`",
            "",
            "## 00632R Governance",
            "",
        ]
    )
    for name in ("100k", "500k", "1m"):
        row = inverse[name]
        lines.append(
            f"- {name}: status `{row['governance_status']}`, "
            f"PVA touch count `{row['pva_logged_touch_count']}`, "
            f"PVA max target `{row['pva_logged_max_target_weight']:.4f}`, "
            f"forced exits `{row['forced_exit_count']}`"
        )
    lines.extend(
        [
            "",
            "## Candidate Risk",
            "",
            f"- Label: `{risk['label']}`",
            f"- Risk score: `{risk['risk_score']}`",
            f"- Signals: `{risk['signals']}`",
            f"- Interpretation: `{risk['interpretation']}`",
            "",
            "## Decision",
            "",
            f"- 500k helpful on full-window final value / Sharpe: `{decision['five_hundred_k_training_steps_helpful']}`",
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
        (history_dir / f"ppo_500k_guarded_shadow_review_{stamp}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backtest-100k", default=str(DEFAULT_100K))
    parser.add_argument("--backtest-500k", default=str(DEFAULT_500K))
    parser.add_argument("--backtest-1m", default=str(DEFAULT_1M))
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
        path_1m=_resolve(args.backtest_1m),
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
                "five_hundred_k_training_steps_helpful": report["decision"]["five_hundred_k_training_steps_helpful"],
                "output_json": str(_resolve(args.output_json)),
                "output_md": str(_resolve(args.output_md)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
