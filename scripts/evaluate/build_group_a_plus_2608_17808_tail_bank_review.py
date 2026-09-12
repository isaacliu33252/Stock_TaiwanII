#!/usr/bin/env python3
"""Build fixed tail-bank review for 2608.17808-inspired GroupA+ shadows.

This is a research-only coverage check.  It summarizes existing Riccati/MV
shadow tuning reports across fixed out-of-sample, stress, and recent windows.
It never changes live strategy weights, golden weights, guards, signals, or
orders.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_17808_tail_bank_review.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_17808_tail_bank_review.md"
DEFAULT_CANDIDATES = (
    "cap631_tail2_dd10_vol125_beta05=results/tune_2608_17808_cap631_tail2_dd10_vol125_beta05_20260902.json",
    "cap631_tail2_dd10_vol125_beta10=results/tune_2608_17808_cap631_tail2_dd10_vol125_20260902.json",
    "cap631_tail_drawdown_vol_beta05=results/tune_2608_17808_cap631_tail_drawdown_vol_beta05_20260902.json",
    "both_tail_drawdown_vol_beta05=results/tune_2608_17808_both_tail_drawdown_vol_beta05_20260902.json",
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _candidate_items(raw_candidates: list[str]) -> list[tuple[str, Path]]:
    items: list[tuple[str, Path]] = []
    for raw in raw_candidates:
        label, sep, path_text = raw.partition("=")
        if not sep:
            path = Path(raw)
            label = path.stem
        else:
            path = Path(path_text)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        items.append((label.strip(), path))
    return items


def summarize_candidate(label: str, path: Path) -> dict[str, Any]:
    source = _load_json(path)
    windows = source.get("windows", [])
    rows: list[dict[str, Any]] = []
    for item in windows:
        delta = item.get("delta_vs_baseline", {})
        baseline_metrics = item.get("baseline", {}).get("metrics", {})
        guarded_metrics = item.get("riccati_mv_cap_to_cash", {}).get("metrics", {})
        rows.append(
            {
                "label": item.get("label"),
                "kind": item.get("kind"),
                "start": item.get("window", {}).get("start"),
                "end": item.get("window", {}).get("end"),
                "rows": int(item.get("window", {}).get("rows") or 0),
                "confirmation_days": int(item.get("confirmation_days") or 0),
                "cap_event_days": int(item.get("cap_event_days") or 0),
                "delta_final_value": _float(delta.get("final_value")),
                "delta_sharpe_ratio": _float(delta.get("sharpe_ratio")),
                "delta_max_drawdown": _float(delta.get("max_drawdown")),
                "delta_worst_20d_return": _float(delta.get("worst_20d_return")),
                "baseline_final_value": _float(baseline_metrics.get("final_value")),
                "guarded_final_value": _float(guarded_metrics.get("final_value")),
            }
        )

    window_count = len(rows)
    total_cap_days = sum(row["cap_event_days"] for row in rows)
    positive_final = sum(1 for row in rows if row["delta_final_value"] > 0.0)
    positive_sharpe = sum(1 for row in rows if row["delta_sharpe_ratio"] > 0.0)
    positive_mdd = sum(1 for row in rows if row["delta_max_drawdown"] > 0.0)
    nonnegative_tail = sum(1 for row in rows if row["delta_worst_20d_return"] >= 0.0)
    worst_final = min((row["delta_final_value"] for row in rows), default=0.0)
    worst_sharpe = min((row["delta_sharpe_ratio"] for row in rows), default=0.0)
    worst_mdd = min((row["delta_max_drawdown"] for row in rows), default=0.0)
    source_decision = source.get("decision", {})
    broad_tail_pass = (
        window_count > 0
        and positive_final >= window_count - 1
        and positive_sharpe >= window_count - 1
        and positive_mdd >= window_count - 1
        and nonnegative_tail == window_count
        and worst_final >= -100.0
        and bool(source_decision.get("promotion_allowed")) is True
    )
    return {
        "label": label,
        "source_path": str(path.relative_to(PROJECT_ROOT) if path.is_relative_to(PROJECT_ROOT) else path),
        "source_generated_at": source.get("generated_at"),
        "source_decision": source_decision,
        "confirmation": source.get("confirmation", {}),
        "spec": source.get("spec", {}),
        "window_count": window_count,
        "total_cap_event_days": total_cap_days,
        "positive_final_value_windows": positive_final,
        "positive_sharpe_windows": positive_sharpe,
        "positive_max_drawdown_windows": positive_mdd,
        "nonnegative_worst_20d_windows": nonnegative_tail,
        "worst_delta_final_value": worst_final,
        "worst_delta_sharpe_ratio": worst_sharpe,
        "worst_delta_max_drawdown": worst_mdd,
        "broad_tail_coverage_pass": broad_tail_pass,
        "windows": rows,
    }


def _score(candidate: dict[str, Any]) -> tuple[float, float, float, float]:
    return (
        _float(candidate["worst_delta_final_value"]),
        _float(candidate["worst_delta_max_drawdown"]),
        _float(candidate["worst_delta_sharpe_ratio"]),
        -float(candidate["total_cap_event_days"]),
    )


def build_report(candidates: list[tuple[str, Path]]) -> dict[str, Any]:
    summaries = [summarize_candidate(label, path) for label, path in candidates if path.exists()]
    missing = [{"label": label, "path": str(path)} for label, path in candidates if not path.exists()]
    best = max(summaries, key=_score) if summaries else None
    any_pass = any(item["broad_tail_coverage_pass"] for item in summaries)
    decision = "eligible_for_manual_review_not_auto_promote" if any_pass else "do_not_promote_keep_shadow"
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2608_17808_tail_bank_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": "arXiv:2608.17808",
        "policy": "research_only_no_weight_change",
        "changes_latest_strategy": False,
        "changes_golden1_0531": False,
        "changes_golden2_0830": False,
        "method": "fixed_tail_bank_review_of_existing_current_policy_re_evaluation_sweeps",
        "decision": {
            "promotion_allowed": any_pass,
            "decision": decision,
            "best_stability_candidate": best["label"] if best else None,
            "no_further_auto_tuning_recommended": not any_pass,
            "reason": (
                "No candidate has broad positive edge across fixed out-of-sample, stress, and recent windows."
                if not any_pass
                else "At least one candidate passed broad tail-bank coverage; manual review is still required."
            ),
        },
        "coverage_threshold": {
            "positive_final_value_windows_min": "window_count - 1",
            "positive_sharpe_windows_min": "window_count - 1",
            "positive_max_drawdown_windows_min": "window_count - 1",
            "nonnegative_worst_20d_windows_min": "window_count",
            "worst_delta_final_value_min": -100.0,
            "requires_source_promotion_allowed": True,
        },
        "missing_candidates": missing,
        "candidates": summaries,
    }


def _fmt_float(value: Any, digits: int = 2) -> str:
    return f"{_float(value):.{digits}f}"


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# 2608.17808 Tail Bank Review",
        "",
        f"- Policy: `{report['policy']}`",
        f"- Decision: `{report['decision']['decision']}`",
        f"- Best stability candidate: `{report['decision']['best_stability_candidate']}`",
        f"- No target-weight change: `{not report['changes_latest_strategy']}`",
        f"- No further auto tuning recommended: `{report['decision']['no_further_auto_tuning_recommended']}`",
        "",
        "## Candidate Summary",
        "",
        "| candidate | cap days | FV+ | Sharpe+ | MDD+ | tail nonneg | worst FV | worst Sharpe | worst MDD | pass |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in report["candidates"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item["label"]),
                    str(item["total_cap_event_days"]),
                    f"{item['positive_final_value_windows']}/{item['window_count']}",
                    f"{item['positive_sharpe_windows']}/{item['window_count']}",
                    f"{item['positive_max_drawdown_windows']}/{item['window_count']}",
                    f"{item['nonnegative_worst_20d_windows']}/{item['window_count']}",
                    _fmt_float(item["worst_delta_final_value"], 2),
                    _fmt_float(item["worst_delta_sharpe_ratio"], 6),
                    _fmt_float(item["worst_delta_max_drawdown"], 6),
                    str(item["broad_tail_coverage_pass"]),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Window Details", ""])
    for item in report["candidates"]:
        lines.extend(
            [
                f"### {item['label']}",
                "",
                "| window | kind | cap days | dFV | dSharpe | dMDD | dWorst20D |",
                "|---|---|---:|---:|---:|---:|---:|",
            ]
        )
        for row in item["windows"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(row["label"]),
                        str(row["kind"]),
                        str(row["cap_event_days"]),
                        _fmt_float(row["delta_final_value"], 2),
                        _fmt_float(row["delta_sharpe_ratio"], 6),
                        _fmt_float(row["delta_max_drawdown"], 6),
                        _fmt_float(row["delta_worst_20d_return"], 6),
                    ]
                )
                + " |"
            )
        lines.append("")
    if report["missing_candidates"]:
        lines.extend(["## Missing Candidates", ""])
        for item in report["missing_candidates"]:
            lines.append(f"- `{item['label']}`: `{item['path']}`")
        lines.append("")
    lines.append("No target-weight change. This review is a research-only diagnostic gate.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_outputs(report: dict[str, Any], output: Path, markdown: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, markdown)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", action="append", dest="candidates", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()

    raw_candidates = args.candidates if args.candidates is not None else list(DEFAULT_CANDIDATES)
    report = build_report(_candidate_items(raw_candidates))
    write_outputs(report, Path(args.output), Path(args.markdown))
    print(f"decision={report['decision']['decision']} best={report['decision']['best_stability_candidate']}")
    for item in report["candidates"]:
        print(
            f"{item['label']}: cap_days={item['total_cap_event_days']} "
            f"FV+={item['positive_final_value_windows']}/{item['window_count']} "
            f"Sharpe+={item['positive_sharpe_windows']}/{item['window_count']} "
            f"MDD+={item['positive_max_drawdown_windows']}/{item['window_count']} "
            f"worstFV={item['worst_delta_final_value']:.2f}"
        )
    print(f"Output: {Path(args.output).resolve()}")
    print(f"Markdown: {Path(args.markdown).resolve()}")


if __name__ == "__main__":
    main()
