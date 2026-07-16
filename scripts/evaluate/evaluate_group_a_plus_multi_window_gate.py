#!/usr/bin/env python3
"""Aggregate GroupA+ candidate evidence across multiple windows/results."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def _load_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(_resolve(path).read_text(encoding="utf-8"))
    return payload.get("data", payload) if isinstance(payload.get("data"), dict) else payload


def _window_label(report: dict[str, Any], path: Path) -> str:
    window = report.get("window") or {}
    if isinstance(window, dict) and window.get("start") and window.get("end"):
        return f"{window['start']}_{window['end']}"
    fold = report.get("fold") or {}
    test_window = fold.get("test_window") if isinstance(fold, dict) else None
    if isinstance(test_window, list) and len(test_window) == 2:
        return f"{test_window[0]}_{test_window[1]}"
    return path.stem


def _metric_row(
    *,
    path: Path,
    experiment: str,
    window: str,
    baseline_name: str,
    candidate_name: str,
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    baseline_final = float(baseline.get("final_value", 0.0) or 0.0)
    baseline_sharpe = float(baseline.get("sharpe_ratio", 0.0) or 0.0)
    baseline_mdd = float(baseline.get("max_drawdown", 0.0) or 0.0)
    candidate_final = float(candidate.get("final_value", 0.0) or 0.0)
    candidate_sharpe = float(candidate.get("sharpe_ratio", 0.0) or 0.0)
    candidate_mdd = float(candidate.get("max_drawdown", 0.0) or 0.0)
    candidate_rebalances = candidate.get("rebalance_count", candidate.get("num_rebalances"))
    baseline_rebalances = baseline.get("rebalance_count", baseline.get("num_rebalances"))
    return {
        "path": str(path),
        "experiment": experiment,
        "window": window,
        "baseline": baseline_name,
        "candidate": candidate_name,
        "baseline_final_value": baseline_final,
        "candidate_final_value": candidate_final,
        "delta_final_value": candidate_final - baseline_final,
        "delta_final_pct": (candidate_final / baseline_final - 1.0) if baseline_final else None,
        "baseline_sharpe_ratio": baseline_sharpe,
        "candidate_sharpe_ratio": candidate_sharpe,
        "delta_sharpe": candidate_sharpe - baseline_sharpe,
        "baseline_max_drawdown": baseline_mdd,
        "candidate_max_drawdown": candidate_mdd,
        "delta_max_drawdown": candidate_mdd - baseline_mdd,
        "baseline_rebalances": baseline_rebalances,
        "candidate_rebalances": candidate_rebalances,
        "delta_rebalances": (
            int(candidate_rebalances) - int(baseline_rebalances)
            if candidate_rebalances is not None and baseline_rebalances is not None
            else None
        ),
    }


def _extract_rows(path: str | Path) -> list[dict[str, Any]]:
    resolved = _resolve(path)
    report = _load_json(resolved)
    experiment = str(report.get("experiment") or report.get("report_type") or resolved.stem)
    window = _window_label(report, resolved)
    rows: list[dict[str, Any]] = []

    fold = report.get("fold")
    if isinstance(fold, dict) and isinstance(fold.get("test_sharpe"), dict):
        baseline_name = "static_best_frozen"
        benchmark_names = {baseline_name, "a207", "ma20"}
        names = sorted(set(fold.get("test_sharpe", {})) & set(fold.get("test_final_value", {})) & set(fold.get("test_mdd", {})))
        baseline = {
            "final_value": fold["test_final_value"].get(baseline_name),
            "sharpe_ratio": fold["test_sharpe"].get(baseline_name),
            "max_drawdown": fold["test_mdd"].get(baseline_name),
        }
        for name in names:
            if name in benchmark_names:
                continue
            candidate = {
                "final_value": fold["test_final_value"].get(name),
                "sharpe_ratio": fold["test_sharpe"].get(name),
                "max_drawdown": fold["test_mdd"].get(name),
            }
            rows.append(
                _metric_row(
                    path=resolved,
                    experiment=experiment,
                    window=window,
                    baseline_name=baseline_name,
                    candidate_name=name,
                    baseline=baseline,
                    candidate=candidate,
                )
            )
        return rows

    if isinstance(report.get("current_active_metrics"), dict) and isinstance(report.get("shadow_2008_candidate_metrics"), dict):
        rows.append(
            _metric_row(
                path=resolved,
                experiment=experiment,
                window=window,
                baseline_name="current_active",
                candidate_name="shadow_2008_candidate",
                baseline=report["current_active_metrics"],
                candidate=report["shadow_2008_candidate_metrics"],
            )
        )
        return rows

    baseline_metrics = None
    baseline_name = "baseline"
    if isinstance(report.get("baseline"), dict):
        baseline = report["baseline"]
        baseline_metrics = baseline.get("metrics") if isinstance(baseline.get("metrics"), dict) else baseline
    if baseline_metrics is None and isinstance(report.get("metrics"), dict):
        baseline_metrics = report["metrics"]
        baseline_name = str(report.get("strategy") or "self_metrics")

    if isinstance(baseline_metrics, dict):
        summary = report.get("summary") or {}
        if isinstance(summary, dict):
            for key in ("best_by_final_value", "best_by_max_drawdown", "best_by_sharpe"):
                value = summary.get(key)
                if isinstance(value, dict):
                    metrics = value.get("metrics") if isinstance(value.get("metrics"), dict) else value
                    rows.append(
                        _metric_row(
                            path=resolved,
                            experiment=experiment,
                            window=window,
                            baseline_name=baseline_name,
                            candidate_name=key,
                            baseline=baseline_metrics,
                            candidate=metrics,
                        )
                    )
    return rows


def evaluate_multi_window(
    result_paths: list[str | Path],
    *,
    min_pass_ratio: float = 1.0,
    max_final_drawdown_pct: float = 0.02,
    min_sharpe_delta: float = 0.0,
    require_mdd_nonworse: bool = True,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for path in result_paths:
        rows.extend(_extract_rows(path))

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["candidate"])].append(row)

    candidates = []
    for name, items in sorted(grouped.items()):
        pass_rows = []
        for row in items:
            final_ok = float(row["delta_final_pct"] or 0.0) >= -float(max_final_drawdown_pct)
            sharpe_ok = float(row["delta_sharpe"]) >= float(min_sharpe_delta)
            mdd_ok = (float(row["delta_max_drawdown"]) >= 0.0) if require_mdd_nonworse else True
            row["window_pass"] = bool(final_ok and sharpe_ok and mdd_ok)
            row["window_fail_reasons"] = [
                reason
                for reason, ok in (
                    ("final_value_drag", final_ok),
                    ("sharpe_delta", sharpe_ok),
                    ("max_drawdown_worse", mdd_ok),
                )
                if not ok
            ]
            if row["window_pass"]:
                pass_rows.append(row)
        pass_ratio = len(pass_rows) / len(items) if items else 0.0
        candidates.append(
            {
                "candidate": name,
                "window_count": len(items),
                "pass_count": len(pass_rows),
                "pass_ratio": pass_ratio,
                "worst_delta_final_pct": min(float(row["delta_final_pct"] or 0.0) for row in items) if items else None,
                "worst_delta_sharpe": min(float(row["delta_sharpe"]) for row in items) if items else None,
                "worst_delta_max_drawdown": min(float(row["delta_max_drawdown"]) for row in items) if items else None,
                "decision": "multi_window_pass" if pass_ratio >= min_pass_ratio else "research_only_multi_window_unstable",
                "rows": items,
            }
        )

    overall_pass = any(item["decision"] == "multi_window_pass" for item in candidates)
    return {
        "report_type": "group_a_plus_multi_window_gate",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "active_allocation_impact": "none",
        "decision": "candidate_available" if overall_pass else "research_only_no_multi_window_pass",
        "criteria": {
            "min_pass_ratio": float(min_pass_ratio),
            "max_final_drawdown_pct": float(max_final_drawdown_pct),
            "min_sharpe_delta": float(min_sharpe_delta),
            "require_mdd_nonworse": bool(require_mdd_nonworse),
        },
        "source_files": [str(_resolve(path)) for path in result_paths],
        "row_count": len(rows),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "rows": rows,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", nargs="+", required=True)
    parser.add_argument("--min-pass-ratio", type=float, default=1.0)
    parser.add_argument("--max-final-drawdown-pct", type=float, default=0.02)
    parser.add_argument("--min-sharpe-delta", type=float, default=0.0)
    parser.add_argument("--allow-worse-mdd", action="store_true")
    parser.add_argument("--output", default="results/group_a_plus_multi_window_gate_latest.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = evaluate_multi_window(
        args.results,
        min_pass_ratio=args.min_pass_ratio,
        max_final_drawdown_pct=args.max_final_drawdown_pct,
        min_sharpe_delta=args.min_sharpe_delta,
        require_mdd_nonworse=not args.allow_worse_mdd,
    )
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Multi-window gate: {output}")
    print(f"Decision: {report['decision']}")
    for candidate in report["candidates"]:
        print(
            f"  {candidate['candidate']}: {candidate['decision']} "
            f"pass={candidate['pass_count']}/{candidate['window_count']} "
            f"worst_final={candidate['worst_delta_final_pct']:.4f} "
            f"worst_sharpe={candidate['worst_delta_sharpe']:.4f}"
        )


if __name__ == "__main__":
    main()
