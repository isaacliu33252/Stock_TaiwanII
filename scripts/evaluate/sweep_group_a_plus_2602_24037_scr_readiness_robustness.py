#!/usr/bin/env python3
"""Robustness sweep for the 2602.24037 SCR readiness review."""

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

from backtest_group_a_plus_switch_policy import DB_PATH
from scripts.evaluate.build_group_a_plus_2602_24037_scr_readiness_review import (
    DEFAULT_LIVE_SIGNAL,
    DEFAULT_PDF,
    build_review,
)

DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2602_24037_scr_readiness_robustness.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/2602_24037_scr_readiness_robustness.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2602_24037_scr_readiness_robustness/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _float(value: Any, digits: int = 6) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out or out in (float("inf"), float("-inf")):
        return None
    return round(out, digits)


def build_sweep(
    *,
    pdf_path: Path = DEFAULT_PDF,
    db_path: Path = DB_PATH,
    live_signal_path: Path = DEFAULT_LIVE_SIGNAL,
    start: str = "2018-01-02",
    end: str = "latest",
    eval_starts: tuple[str, ...] = ("2023-01-03", "2024-01-02", "2025-01-02"),
    min_histories: tuple[int, ...] = (252, 504),
    k_neighbors_values: tuple[int, ...] = (15, 30, 60),
    gap_limit: float = 0.01,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for eval_start in eval_starts:
        for min_history in min_histories:
            for k_neighbors in k_neighbors_values:
                review = build_review(
                    pdf_path=pdf_path,
                    db_path=db_path,
                    live_signal_path=live_signal_path,
                    start=start,
                    end=end,
                    eval_start=eval_start,
                    min_history=min_history,
                    k_neighbors=k_neighbors,
                    gap_limit=gap_limit,
                )
                summary = review.get("summary") if isinstance(review.get("summary"), dict) else {}
                rows.append(
                    {
                        "eval_start": eval_start,
                        "min_history": min_history,
                        "k_neighbors": k_neighbors,
                        "status": review.get("status"),
                        "oos_days": summary.get("oos_days"),
                        "mean_abs_scenario_real_gap": summary.get("mean_abs_scenario_real_gap"),
                        "p90_abs_scenario_real_gap": summary.get("p90_abs_scenario_real_gap"),
                        "beta_cf_from_bias_variance_proxy": summary.get("beta_cf_from_bias_variance_proxy"),
                        "scenario_real_gap_gate_passed": summary.get("scenario_real_gap_gate_passed") is True,
                        "beta_cf_candidate_in_paper_moderate_range": review.get("decision", {}).get(
                            "beta_cf_candidate_in_paper_moderate_range"
                        )
                        is True,
                        "warning_reasons": review.get("warning_reasons"),
                    }
                )
    valid = [row for row in rows if row["status"] == "available_for_shadow_review"]
    gap_pass = [row for row in valid if row["scenario_real_gap_gate_passed"]]
    beta_ok = [row for row in valid if row["beta_cf_candidate_in_paper_moderate_range"]]
    mean_gaps = [
        float(row["mean_abs_scenario_real_gap"])
        for row in valid
        if isinstance(row.get("mean_abs_scenario_real_gap"), (int, float))
    ]
    betas = [
        float(row["beta_cf_from_bias_variance_proxy"])
        for row in valid
        if isinstance(row.get("beta_cf_from_bias_variance_proxy"), (int, float))
    ]
    summary = {
        "total_runs": len(rows),
        "valid_runs": len(valid),
        "gap_gate_pass_runs": len(gap_pass),
        "beta_moderate_runs": len(beta_ok),
        "gap_gate_pass_rate": _float(len(gap_pass) / len(valid)) if valid else None,
        "beta_moderate_rate": _float(len(beta_ok) / len(valid)) if valid else None,
        "mean_gap_min": _float(min(mean_gaps)) if mean_gaps else None,
        "mean_gap_max": _float(max(mean_gaps)) if mean_gaps else None,
        "beta_cf_min": _float(min(betas)) if betas else None,
        "beta_cf_max": _float(max(betas)) if betas else None,
        "gap_readiness_robust": bool(valid) and len(gap_pass) == len(valid),
        "beta_cf_moderate_robust": bool(valid) and len(beta_ok) == len(valid),
    }
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2602_24037_scr_readiness_robustness",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "available_for_shadow_review" if valid else "blocked",
        "policy": "research_shadow_only_no_rl_training_no_live_weight_change",
        "source_paper": "2602.24037v1",
        "parameters": {
            "start": start,
            "end": end,
            "eval_starts": list(eval_starts),
            "min_histories": list(min_histories),
            "k_neighbors_values": list(k_neighbors_values),
            "gap_limit": gap_limit,
        },
        "summary": summary,
        "rows": rows,
        "decision": {
            "sweep_complete": True,
            "best_import": "scr_readiness_and_mismatch_guard_only",
            "scr_shadow_training_allowed_by_this_sweep": False,
            "ppo_training_allowed": False,
            "model_training_allowed": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "allow_00679b_add": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def render_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# 2602.24037 SCR Readiness Robustness",
        "",
        f"Generated: `{payload['generated_at']}`",
        f"Status: `{payload['status']}`",
        "",
        "## Summary",
        "",
        f"- Total runs: `{summary['total_runs']}`",
        f"- Valid runs: `{summary['valid_runs']}`",
        f"- Gap gate pass runs: `{summary['gap_gate_pass_runs']}`",
        f"- Beta moderate runs: `{summary['beta_moderate_runs']}`",
        f"- Mean gap range: `{summary['mean_gap_min']}` to `{summary['mean_gap_max']}`",
        f"- Beta cf range: `{summary['beta_cf_min']}` to `{summary['beta_cf_max']}`",
        f"- Gap readiness robust: `{summary['gap_readiness_robust']}`",
        f"- Beta cf moderate robust: `{summary['beta_cf_moderate_robust']}`",
        "",
        "## Rows",
        "",
        "| Eval start | Min history | K | OOS days | Mean gap | P90 gap | Beta cf | Gap pass | Beta moderate |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in payload["rows"]:
        lines.append(
            "| {eval_start} | {min_history} | {k_neighbors} | {oos_days} | {mean_gap} | {p90_gap} | {beta} | {gap_pass} | {beta_ok} |".format(
                eval_start=row.get("eval_start"),
                min_history=row.get("min_history"),
                k_neighbors=row.get("k_neighbors"),
                oos_days=row.get("oos_days"),
                mean_gap=row.get("mean_abs_scenario_real_gap"),
                p90_gap=row.get("p90_abs_scenario_real_gap"),
                beta=row.get("beta_cf_from_bias_variance_proxy"),
                gap_pass=row.get("scenario_real_gap_gate_passed"),
                beta_ok=row.get("beta_cf_candidate_in_paper_moderate_range"),
            )
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            "- Keep as shadow readiness guard only.",
            "- Do not train SCR-PPO from this sweep.",
            "- Do not change target weights or rebalance.",
            "- Keep `Golden1_0531` unchanged.",
            "",
        ]
    )
    return "\n".join(lines)


def _history_path(history_dir: Path, as_of: str) -> Path:
    return history_dir / f"2602_24037_scr_readiness_robustness_{as_of.replace('-', '')}.json"


def write_sweep(payload: dict[str, Any], output: Path, output_md: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(render_markdown(payload) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        as_of = "20260828"
        _history_path(history_dir, as_of).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )


def _parse_ints(raw: str) -> tuple[int, ...]:
    return tuple(int(item.strip()) for item in raw.split(",") if item.strip())


def _parse_strings(raw: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", default=str(DEFAULT_PDF))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--start", default="2018-01-02")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--eval-starts", default="2023-01-03,2024-01-02,2025-01-02")
    parser.add_argument("--min-histories", default="252,504")
    parser.add_argument("--k-neighbors-values", default="15,30,60")
    parser.add_argument("--gap-limit", type=float, default=0.01)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    payload = build_sweep(
        pdf_path=_resolve(args.pdf),
        db_path=_resolve(args.db),
        live_signal_path=_resolve(args.live_signal),
        start=args.start,
        end=args.end,
        eval_starts=_parse_strings(args.eval_starts),
        min_histories=_parse_ints(args.min_histories),
        k_neighbors_values=_parse_ints(args.k_neighbors_values),
        gap_limit=args.gap_limit,
    )
    write_sweep(payload, _resolve(args.output), _resolve(args.output_md), None if args.no_history else _resolve(args.history_dir))
    print(f"2602.24037 SCR readiness robustness: {_resolve(args.output)}")
    print(json.dumps({"status": payload["status"], "summary": payload["summary"], "decision": payload["decision"]}, indent=2))


if __name__ == "__main__":
    main()
